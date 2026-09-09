"""Exercise the actual browser rename transform against ABDA semantics."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from app.scenario.catalog import load_bundled_scenario
from app.scenario.loader import scenario_from_dict
from app.scenario.serialize import scenario_to_dict
from app.scenario.state import compute_state_bundle


ROOT = Path(__file__).resolve().parents[1]
SECTIONS = ('facts', 'assumptions', 'propositions', 'conclusions', 'rules')
RUNNER = """
const fs = require('node:fs'), vm = require('node:vm');
const request = JSON.parse(fs.readFileSync(0, 'utf8'));
const source = fs.readFileSync(process.argv[1], 'utf8');
const result = vm.runInNewContext(source + `
  const before = JSON.stringify(request.scenario);
  let renamed = request.scenario, error = null;
  try {
    for (const [from, to] of request.renames)
      renamed = renameScenarioSymbol(renamed, from, to);
  } catch (failure) { error = failure.message; }
  ({scenario: renamed, error, inputUnchanged: before === JSON.stringify(request.scenario)});
`, {request, structuredClone}, {timeout: 5000});
process.stdout.write(JSON.stringify(result));
"""


@pytest.fixture(scope='module')
def node_runtime():
    node = shutil.which('node')
    if node:
        return node
    # The local optional browser test installation supplies its own Node.
    spec = importlib.util.find_spec('playwright')
    if spec and spec.origin:
        node = Path(spec.origin).parent / 'driver' / 'node'
        if node.is_file():
            return str(node)
    pytest.skip('Install Node or the optional Playwright test runtime')


def rename(node, scenario, *renames):
    result = subprocess.run(
        [node, '-e', RUNNER, str(ROOT / 'app/static/scenarios.js')],
        input=json.dumps({'scenario': scenario, 'renames': renames}),
        capture_output=True, text=True, timeout=10, check=True,
    )
    receipt = json.loads(result.stdout)
    assert receipt['inputUnchanged']
    return receipt


def test_exact_references_and_metadata_survive_rename(node_runtime):
    raw = {
        'title': 'Symbols p and r', 'description': 'The prose p and r is not code.',
        'facts': {'p': {'description': 'p evidence', 'category': 'p', 'source': 'p.txt'},
                  'p1': {'description': 'Another fact'}},
        'assumptions': {'a': {'description': 'Assumption', 'negated_description': 'Not reliable', 'block': 3, 'active': False}},
        'propositions': {'q': {'description': 'Intermediate'}},
        'conclusions': {'c': {'description': 'Decision', 'negated_description': 'No decision'}},
        'rules': {
            'r': {'type': 'defeasible', 'premises': ['p', '-a'], 'conclusion': 'q', 'block': 4, 'active': False,
                  'source': 'p.txt', 'category': 'Evidence', 'negated_description': 'r is unreliable'},
            'u': {'type': 'strict', 'premises': ['-p', 'r', '-r', 'p1'], 'conclusion': '-r'},
            's': {'type': 'strict', 'premises': ['q'], 'conclusion': '-c'},
            'empty': {'type': 'defeasible', 'premises': [], 'conclusion': 'c', 'block': 2},
        },
        'corpus': [], 'sources': [{'filename': 'p.txt', 'text': 'p and -r remain literal reference text.\n', 'url': 'https://example.org/p'}],
    }
    changes = [('p', 'evidence'), ('a', 'reliable'), ('q', 'intermediate'), ('c', 'decision'), ('r', 'inference'), ('s', 'strict_rule')]
    receipt = rename(node_runtime, raw, *changes)
    assert receipt['error'] is None
    result = receipt['scenario']
    mapping = dict(changes)
    def literal(value):
        base = value.removeprefix('-')
        return ('-' if value.startswith('-') else '') + mapping.get(base, base)
    expected = deepcopy(raw)
    for section in SECTIONS:
        expected[section] = {mapping.get(key, key): value for key, value in expected[section].items()}
    for rule in expected['rules'].values():
        rule['premises'] = [literal(value) for value in rule['premises']]
        rule['conclusion'] = literal(rule['conclusion'])
    assert result == expected
    scenario_from_dict(result)
    assert rename(node_runtime, result, *[(new, old) for old, new in reversed(changes)])['scenario'] == raw


@pytest.mark.parametrize('name', ['', '-p', '1p', 'two words', 'a-b', 'a.b', 'p\n', 'p\r', 'p\t', 'p/q', 'é', '<script>', 'a' * 101,
                                  '__proto__', 'constructor', 'prototype', 'toString', 'hasOwnProperty', 'valueOf', '__defineGetter__'])
def test_invalid_names_are_atomic(node_runtime, name):
    raw = {'title': 'Unchanged', 'facts': {'p': {'description': 'Evidence'}}, 'rules': {}}
    result = rename(node_runtime, raw, ('p', name))
    assert result['error'] and result['scenario'] == raw


@pytest.mark.parametrize('section', SECTIONS)
def test_collisions_across_all_sections_are_rejected(node_runtime, section):
    raw = {'facts': {'p': {'description': 'Evidence'}}, 'rules': {}}
    raw.setdefault(section, {})['used'] = {}
    result = rename(node_runtime, raw, ('p', 'used'))
    assert 'already used' in result['error'] and result['scenario'] == raw


def test_incomplete_drafts_noops_and_maximum_length(node_runtime):
    raw = {'title': '', 'facts': {'p': {'description': ''}},
           'rules': {'r': {'premises': ['', 'p', '-p'], 'conclusion': ''}}}
    assert rename(node_runtime, raw, ('p', 'p'))['scenario'] == raw
    result = rename(node_runtime, raw, ('p', '_' + 'x' * 99))
    assert result['error'] is None and len(next(iter(result['scenario']['facts']))) == 100
    assert result['scenario']['rules']['r']['premises'][0] == ''
    assert rename(node_runtime, raw, ('missing', 'new'))['error']
    raw['conclusions'] = {'p': {'description': 'Ambiguous'}}
    assert rename(node_runtime, raw, ('p', 'new'))['error']


@pytest.mark.parametrize('scenario_id', ['popov_v_hayashi', 'fire_prevention', 'medical_ppi', 'nba_rebuild', 'fried_chicken_v1', 'fried_chicken_v2'])
def test_renaming_every_bundled_symbol_preserves_reasoning(node_runtime, scenario_id):
    original = scenario_to_dict(load_bundled_scenario(scenario_id))
    changes = [(key, 'renamed_' + key) for section in SECTIONS for key in original[section]]
    receipt = rename(node_runtime, original, *changes)
    assert receipt['error'] is None
    result = receipt['scenario']
    old_af = compute_state_bundle(scenario_from_dict(original))['af']
    new_af = compute_state_bundle(scenario_from_dict(result))['af']
    assert new_af['labels_by_proposition'] == {
        ('-renamed_' + key[1:] if key.startswith('-') else 'renamed_' + key): value
        for key, value in old_af['labels_by_proposition'].items()
    }
    for section in SECTIONS:
        for key, metadata in original[section].items():
            assert {k: v for k, v in result[section]['renamed_' + key].items() if k not in {'premises', 'conclusion'}} == {
                k: v for k, v in metadata.items() if k not in {'premises', 'conclusion'}
            }
    restored = rename(node_runtime, result, *[(new, old) for old, new in reversed(changes)])
    assert restored['scenario'] == original
