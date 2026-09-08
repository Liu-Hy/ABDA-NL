"""Editor semantics and server-independent, full-text scenario interchange."""

from copy import deepcopy
import json

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.scenario import catalog
from app.scenario.aspic_import import import_aspic
from app.scenario.editor import edit_scenario
from app.scenario.exchange import ScenarioFileError, parse_scenario_file
from app.scenario.loader import scenario_from_dict
from app.scenario.portable import export_scenario
from app.scenario.serialize import scenario_to_dict
from app.scenario.state import compute_state_bundle
from app.services.projects import normalize_project_scenario


def test_native_blank_lines_preserve_defeasible_preferences():
    text = '-> sunny\n-> windy\n\nsunny => outside [sunshine]\n\nwindy => -outside [wind]'
    scenario, _ = import_aspic('Picnic', text, '', 'outside')
    assert scenario['rules']['sunshine']['block'] == 1
    assert scenario['rules']['wind']['block'] == 2
    assert compute_state_bundle(scenario_from_dict(scenario))['af']['labels_by_proposition']['outside'] == 'rejected'
    explicit, _ = import_aspic('Picnic', '# Block 1\n' + text, '', 'outside')
    assert explicit['rules']['wind']['block'] == 1
    assert compute_state_bundle(scenario_from_dict(explicit))['af']['labels_by_proposition']['outside'] == 'undecided'


def test_rule_text_keeps_metadata_but_updates_logic():
    raw = {'title': 'Picnic', 'description': 'Background',
           'facts': {'p': {'description': 'Evidence', 'category': 'Weather', 'source': 'paper.txt'}},
           'assumptions': {'a': {'description': 'Reliable', 'block': 3, 'active': False}},
           'propositions': {'q': {'description': 'Intermediate'}, 'unused': {'description': 'Not asserted'}},
           'conclusions': {'c': {'description': 'Decision', 'negated_description': 'No decision'}},
           'rules': {'r': {'type': 'defeasible', 'premises': ['p'], 'conclusion': 'q', 'block': 2,
                           'source': 'paper.txt', 'negated_description': 'Unreliable rule'},
                     's': {'type': 'strict', 'premises': ['q'], 'conclusion': 'c'}},
           'sources': [{'filename': 'paper.txt', 'text': 'Complete paper body', 'url': 'https://example.org/paper'}]}
    before = deepcopy(raw)
    updated, _ = edit_scenario(raw, '# Block 1\n-> p\n# Block 3\n# [suspended] => a [a]\n# Block 2\np => q [r]\n# Block 1\nq -> c [s]', '')
    assert scenario_to_dict(scenario_from_dict(updated)) == scenario_to_dict(scenario_from_dict(raw))
    assert raw == before
    edited, _ = edit_scenario(raw, '# Block 1\n-> p\np => -c [r]', 'p = Updated evidence')
    assert edited['facts']['p']['description'] == 'Updated evidence'
    assert edited['rules']['r']['conclusion'] == '-c'
    assert edited['rules']['r']['source'] == 'paper.txt'
    assert edited['sources'] == raw['sources'] and edited['description'] == raw['description']


@pytest.mark.parametrize('scenario_id', ['popov_v_hayashi', 'fire_prevention', 'medical_ppi', 'nba_rebuild', 'fried_chicken_v1', 'fried_chicken_v2'])
def test_all_examples_export_and_reimport_without_any_builtin_materials(scenario_id, tmp_path, monkeypatch):
    original = scenario_to_dict(catalog.load_bundled_scenario(scenario_id))
    original['sources'] = [{'filename': 'additional.txt', 'text': 'User-supplied exact text.\n', 'url': 'https://example.org/source'}]
    exported = export_scenario(original, scenario_id)
    assert exported['version'] == 3 and exported['source_scenario_id'] is None
    documents = {item['filename']: item['text'] for item in exported['scenario']['sources']}
    root = catalog.bundled_scenario_directory(scenario_id)
    for filename in original['corpus']:
        if filename.endswith('.txt'):
            assert documents[filename] == (root / 'corpus' / filename).read_text()
        else:
            from pypdf import PdfReader
            # Every page, including the 44-page document beyond upload limits.
            import re
            full = '\n\n'.join(page.extract_text() or '' for page in PdfReader(root / 'corpus' / filename).pages)
            assert documents[filename] == re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '\n', full)
    if (root / 'corpus_summary.yaml').exists():
        assert documents['ABDA-curated-context.txt'] == (root / 'corpus_summary.yaml').read_text()
    # The receiving installation has no corresponding example or files.
    monkeypatch.setattr(catalog, 'EXAMPLES_ROOT', tmp_path)
    def unavailable(*args, **kwargs):
        raise AssertionError('An import must not consult the original server or catalog')
    monkeypatch.setattr(catalog, 'load_bundled_scenario', unavailable)
    monkeypatch.setattr('app.services.projects.load_bundled_scenario', unavailable)
    restored, source_id, warnings = parse_scenario_file(json.dumps(exported, ensure_ascii=False))
    assert source_id is None and not warnings
    normalized = normalize_project_scenario(restored, source_id)
    assert normalized == exported['scenario']
    for section in ['facts', 'assumptions', 'propositions', 'conclusions', 'rules']:
        assert normalized[section] == original[section]
    assert normalized['description'] == original['description']
    assert normalized['sources'][-1] == original['sources'][0]
    assert compute_state_bundle(scenario_from_dict(normalized))['af'] == compute_state_bundle(scenario_from_dict(original))['af']
    assert export_scenario(normalized, None) == exported
    from app.llm.corpus import build_corpus_block
    context = build_corpus_block(None, [], normalized['title'], sources=normalized['sources'])
    assert all(filename in context for filename in documents)


def test_portable_files_reject_external_dependencies_and_missing_content():
    with pytest.raises(ScenarioFileError, match='embed'):
        parse_scenario_file(json.dumps({'format': 'abda-nl-scenario', 'version': 3, 'source_scenario_id': 'missing', 'scenario': {'title': 'Test'}}))
    with pytest.raises(ValueError, match='missing'):
        export_scenario({'title': 'Test', 'corpus': ['missing.txt']}, None)


def test_editor_and_export_api_boundaries():
    scenario = {'title': 'Portable', 'rules': {}, 'conclusions': {},
                'sources': [{'filename': 'note.txt', 'text': 'Complete stored reference.'}]}
    with TestClient(app) as client:
        body = {'scenario': scenario}
        assert client.post('/api/projects/editor/preview', json=body).status_code == 401
        assert client.post('/api/scenarios/export', json=body, headers={'Origin': 'https://evil.example'}).status_code == 403
        response = client.post('/api/scenarios/export', json=body)
        assert response.status_code == 200 and response.json()['scenario']['sources'] == scenario['sources']
        assert response.headers['cache-control'] == 'no-store'
        client.post('/api/auth/dev/login', json={'email': 'editor-test@example.org'})
        before = client.get('/api/projects').json()
        assert client.post('/api/projects/editor/preview', json=body, headers={'Origin': 'https://evil.example'}).status_code == 403
        result = client.post('/api/projects/editor/preview', json=body)
        assert result.status_code == 200 and 'af' in result.json()
        assert client.get('/api/projects').json() == before


def test_http_roundtrip_reopens_project_with_no_catalog(tmp_path, monkeypatch):
    with TestClient(app) as client:
        original = client.get('/scenarios/popov_v_hayashi').json()
        result = client.post('/api/scenarios/export', json={
            'scenario': original['scenario'], 'source_scenario_id': 'popov_v_hayashi'})
        assert result.status_code == 200
        envelope = result.json()
        monkeypatch.setattr(catalog, 'EXAMPLES_ROOT', tmp_path)
        def absent(*args, **kwargs):
            raise AssertionError('Receiving server must not read an original example')
        monkeypatch.setattr(catalog, 'load_bundled_scenario', absent)
        monkeypatch.setattr('app.services.projects.load_bundled_scenario', absent)
        client.post('/api/auth/dev/login', json={'email': 'portable-receiver@example.org'})
        preview = client.post('/api/projects/import/preview', json={'text': json.dumps(envelope)})
        assert preview.status_code == 200, preview.text
        assert preview.json()['source_scenario_id'] is None
        saved = client.post('/api/projects/import', json={
            'name': 'Independent copy', 'scenario': preview.json()['scenario']})
        assert saved.status_code == 201, saved.text
        reopened = client.get('/api/projects/' + saved.json()['id']).json()
        assert reopened['scenario'] == envelope['scenario']
        assert reopened['af'] == original['af']
        second = client.post('/api/scenarios/export', json={'scenario': reopened['scenario']})
        assert second.status_code == 200 and second.json() == envelope
