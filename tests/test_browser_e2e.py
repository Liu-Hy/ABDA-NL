"""Real-browser acceptance for the public research workspace."""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest


BROWSER_TESTS = (os.getenv("ABDA_BROWSER_TESTS") or "").strip() == "1"
BROWSER_ENGINE = (os.getenv("ABDA_BROWSER_ENGINE") or "chromium").strip().lower()
if BROWSER_ENGINE not in {"chromium", "firefox", "webkit"}:
    raise ValueError("ABDA_BROWSER_ENGINE must be chromium, firefox, or webkit")
pytestmark = pytest.mark.skipif(
    not BROWSER_TESTS,
    reason="set ABDA_BROWSER_TESTS=1 after installing the selected browser runtime",
)


def _available_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture
def live_browser_server(tmp_path):
    root = Path(__file__).resolve().parents[1]
    # Accounts and rate-limit windows belong to one test, not to the suite.
    # Fast CI browsers otherwise exhaust the real login limit across tests.
    state_root = tmp_path
    log_path = state_root / "server.log"
    port = _available_port()
    environment = os.environ.copy()
    for name in tuple(environment):
        if name.startswith(("AZURE_", "ANTHROPIC_", "OPENAI_", "OPENROUTER_", "GOOGLE_", "GCP_")):
            environment.pop(name)
    environment.update(
        {
            # Local operator dotfiles must not override the disposable test
            # database or make provider credentials available to browser checks.
            "PYTHON_DOTENV_DISABLED": "1",
            "XDG_STATE_HOME": str(state_root),
            "ABDA_ENVIRONMENT": "development",
            "ABDA_AUTH_MODE": "dev",
            "ABDA_SCENARIO_ADMIN_EMAILS": "curator@example.org",
            "ABDA_COMMUNITY_CATALOG_ENABLED": "true",
            "ABDA_DATABASE_URL": f"sqlite+pysqlite:///{state_root / 'browser.db'}",
            "ABDA_AUTO_CREATE_DB": "1",
            "ABDA_SESSION_SECRET": "browser-session-secret-with-32-characters",
            "ABDA_MCP_TOKEN_PEPPER": "browser-mcp-pepper-with-32-characters",
            "ABDA_ENABLE_LLM": "1",
            "ABDA_LLM_BACKEND": "ollama",
            "ABDA_LLM_REQUIRE_AUTH": "1",
            "ABDA_LLM_ALLOW_BYOK": "1",
            "ABDA_OPENROUTER_FAILOVER_ENABLED": "0",
            "ABDA_ABUSE_PROTECTION_ENABLED": "1",
            "ABDA_ANONYMOUS_REQUESTS_PER_MINUTE": "500",
            "ABDA_MUTATION_REQUESTS_PER_MINUTE": "500",
            "ABDA_LLM_REQUESTS_PER_MINUTE": "50",
            "ABDA_TRUSTED_HOSTS": "127.0.0.1,localhost",
        }
    )
    command = [
        sys.executable,
        "-m",
        "app.cli.serve",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--no-browser",
        "--llm",
    ]
    with log_path.open("w+b") as output:
        process = subprocess.Popen(
            command,
            cwd=root,
            env=environment,
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        base_url = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 40
        try:
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    output.flush()
                    tail = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
                    raise RuntimeError(f"browser server exited during startup:\n{tail}")
                try:
                    with urllib.request.urlopen(
                        f"{base_url}/health/ready", timeout=1
                    ) as response:
                        if response.status == 200:
                            break
                except (OSError, urllib.error.URLError):
                    pass
                time.sleep(0.15)
            else:
                raise RuntimeError("browser server did not become ready")
            yield base_url
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def _axe_report(page, label: str) -> None:
    from axe_playwright_python.sync_playwright import Axe

    result = Axe().run(
        page,
        options={
            "runOnly": {
                "type": "tag",
                "values": [
                    "wcag2a",
                    "wcag2aa",
                    "wcag21a",
                    "wcag21aa",
                    "wcag22aa",
                ],
            },
            "resultTypes": ["violations"],
        },
    )
    assert result.violations_count == 0, f"{label}:\n{result.generate_report()}"


def _save_browser_evidence(page, name: str) -> None:
    artifact_root = Path(
        os.getenv("ABDA_BROWSER_ARTIFACT_DIR") or "artifacts/browser"
    )
    artifact_root.mkdir(parents=True, exist_ok=True)
    page.screenshot(
        path=artifact_root / f"{BROWSER_ENGINE}-{name}.png",
        full_page=True,
    )


def _wait_for_demo_ready(page) -> None:
    page.wait_for_function(
        """() => {
            const name = document.querySelector('#scenario-name');
            const conclusion = document.querySelector(
              '#conclusions-list .conclusion-card',
            );
            return name
              && name.textContent.trim()
              && name.textContent.trim() !== 'Loading...'
              && conclusion;
        }"""
    )


def _goto_ready_demo(page, url: str) -> None:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    for attempt in range(2):
        try:
            page.goto(url, wait_until="domcontentloaded")
            _wait_for_demo_ready(page)
            return
        except PlaywrightTimeoutError:
            if attempt > 0:
                raise
            # Firefox has twice timed out at a different late-suite navigation
            # while the same server served every preceding test. Retry only
            # after an independent readiness check proves this is a browser
            # navigation stall rather than an application outage.
            with urllib.request.urlopen(f"{url}/health/ready", timeout=2) as response:
                if response.status != 200:
                    raise
            page.goto("about:blank", wait_until="commit", timeout=5_000)


def _reload_ready_demo(page) -> None:
    page.reload(wait_until="domcontentloaded")
    _wait_for_demo_ready(page)


def test_scenario_library_build_download_import_and_reopen(live_browser_server):
    from uuid import uuid4
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            assert page.request.post(f"{live_browser_server}/api/auth/dev/login", data={"email": f"{uuid4().hex}@example.org"}).ok
            _goto_ready_demo(page, live_browser_server)
            page.locator("#scenario-library-btn").click()
            page.locator("#scenario-builder-title").fill("My own picnic")
            page.locator("#statement_1-text").fill("The forecast is sunny")
            page.locator("#statement_2-text").fill("We should hold the picnic outside")
            rule = page.locator(".scenario-rule-card").first
            rule.locator("[data-literal]").nth(0).select_option("statement_1")
            rule.locator("[data-literal]").nth(1).select_option("statement_2")
            _axe_report(page, "new scenario builder")
            _save_browser_evidence(page, "scenario-builder")
            with page.expect_response(lambda response: response.url.endswith("/api/projects/import") and response.request.method == "POST") as created:
                _preview_editor(page)
                page.locator("#scenario-library-submit").click()
            project = created.value.json()
            expect(page.locator("#scenario-name")).to_have_text("My own picnic")
            expect(page.locator("#context-indicator")).to_have_text("Private project")
            expect(page.locator("#conclusions-list")).to_contain_text("Accepted")
            assert project["source_scenario_id"] is None
            assert page.request.get(f"{live_browser_server}/api/trial").json()["active"] is False
            page.locator("input.rule-active-toggle").uncheck()
            page.locator("#suspend-impact-apply-btn").click()
            expect(page.locator("#conclusions-list")).to_contain_text("Absent")
            page.locator("#scenario-library-btn").click()
            with page.expect_download() as modified_download:
                page.locator("#scenario-download-current").click()
            modified = json.loads(Path(modified_download.value.path()).read_text())
            assert modified["scenario"]["rules"]["rule_3"]["active"] is False
            assert page.request.get(f"{live_browser_server}/api/projects/{project['id']}").json()["scenario"]["rules"]["rule_3"]["active"] is True
            page.locator("#scenario-library-cancel").click()
            page.locator("#reset-btn").click()
            expect(page.locator("#conclusions-list")).to_contain_text("Accepted")
            expect(page.locator("#modified-indicator")).to_be_hidden()
            page.locator("#scenario-library-btn").click()
            with page.expect_download() as download:
                page.locator("#scenario-download-current").click()
            downloaded = json.loads(Path(download.value.path()).read_text())
            assert set(downloaded) == {"format", "version", "source_scenario_id", "scenario"}
            assert downloaded["scenario"] == project["scenario"]
            page.locator("#scenario-tab-file").click()
            page.locator("#scenario-file-input").set_input_files({
                "name": "picnic.abda.json", "mimeType": "application/json", "buffer": json.dumps(downloaded).encode(),
            })
            _load_editor_files(page)
            page.locator("#scenario-builder-title").fill("Picnic imported copy")
            _axe_report(page, "validated scenario import")
            _save_browser_evidence(page, "scenario-import")
            with page.expect_response(lambda response: response.url.endswith("/api/projects/import") and response.request.method == "POST") as imported:
                _preview_editor(page)
                page.locator("#scenario-library-submit").click()
            copy = imported.value.json()
            assert copy["id"] != project["id"]
            assert copy["scenario"] == {**project["scenario"], "title": "Picnic imported copy"}
            expect(page.locator("#context-indicator")).to_have_text("Private project")
            _reload_ready_demo(page)
            page.locator("#scenario-library-btn").click()
            page.locator("#scenario-my-projects").click()
            page.get_by_role("button", name="Open", exact=True).first.click()
            expect(page.locator("#scenario-select")).to_have_value("__current_project__")
            assert not errors
        finally:
            browser.close()




def test_exported_aspic_preserves_bundled_argumentation(live_browser_server):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page()
        try:
            assert page.request.post(f'{live_browser_server}/api/auth/dev/login', data={'email': 'aspic-roundtrip@example.org'}).ok
            _goto_ready_demo(page, live_browser_server)
            for item in page.request.get(f'{live_browser_server}/scenarios').json()['scenarios']:
                original = page.request.get(f'{live_browser_server}/scenarios/{item["id"]}').json()
                draft = page.evaluate('scenario => { loadScenarioDraft(scenario); return {scenario: scenarioFromBuilder(), rules: scenarioRuleText(scenario)}; }', original['scenario'])
                assert draft['scenario'] == original['scenario'], item['id']
                edited = page.request.post(f'{live_browser_server}/api/projects/editor/preview', data={
                    **draft, 'source_scenario_id': item['id'],
                })
                assert edited.ok, edited.text()
                assert edited.json()['scenario'] == original['scenario'], item['id']
                assert edited.json()['af'] == original['af'], item['id']
                syntax = page.evaluate('scenario => buildAspicText(scenario)', original['scenario'])
                imported = page.request.post(f'{live_browser_server}/api/projects/import/aspic', data={
                    'title': original['scenario']['title'], 'rules': syntax,
                    'conclusions': ','.join(original['scenario']['conclusions']),
                })
                assert imported.ok, (item['id'], imported.text())
                # Inspect through a disposable private project in the isolated test database.
                saved = page.request.post(f'{live_browser_server}/api/projects/import', data={
                    'name': 'Roundtrip', 'scenario': imported.json()['scenario'],
                })
                assert saved.ok, saved.text()
                assert saved.json()['af']['labels_by_proposition'] == original['af']['labels_by_proposition'], item['id']
        finally:
            browser.close()


def _preview_editor(page):
    from playwright.sync_api import expect
    page.locator('#scenario-preview-btn').click()
    expect(page.locator('#scenario-editor-preview')).to_be_visible()
    expect(page.locator('#scenario-library-submit')).to_be_enabled()


def _load_editor_files(page):
    from playwright.sync_api import expect
    page.locator('#scenario-load-files').click()
    expect(page.locator('#scenario-library-status')).to_contain_text('Materials loaded together')


def _rename_editor_symbol(page, old, new):
    from playwright.sync_api import expect
    if page.locator('#scenario-symbol-renamer').get_attribute('open') is None:
        page.locator('#scenario-symbol-renamer > summary').click()
    page.locator('#scenario-rename-from').select_option(old)
    page.locator('#scenario-rename-to').fill(new)
    page.locator('#scenario-rename-apply').click()
    expect(page.locator('#scenario-library-status')).to_contain_text(f'Renamed {old} to {new}')
    expect(page.locator('#scenario-rename-to')).to_have_value(new)


def test_symbol_rename_incomplete_creation_validation_and_cancel(live_browser_server):
    from playwright.sync_api import expect, sync_playwright
    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 900})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        try:
            _goto_ready_demo(page, live_browser_server)
            page.locator('#scenario-library-btn').click()
            page.locator('#scenario-symbol-renamer > summary').click()
            expect(page.locator('#scenario-rename-to')).to_be_disabled()
            expect(page.locator('#scenario-rename-apply')).to_be_disabled()
            page.locator('#scenario-library-cancel').click()
            assert page.request.post(f'{live_browser_server}/api/auth/dev/login', data={'email': 'rename-new@example.org'}).ok
            _reload_ready_demo(page)
            page.locator('#scenario-library-btn').click()
            # Symbols can be chosen before the title, meanings or rule are complete.
            page.locator('.scenario-statement-details').first.locator('summary').click()
            page.get_by_role('button', name='Rename symbol statement_1', exact=True).click()
            page.locator('#scenario-rename-to').fill('forecast')
            page.locator('#scenario-rename-to').press('Enter')
            expect(page.locator('#forecast-text')).to_be_visible()
            page.locator('#forecast-text').fill('The forecast is sunny')
            page.locator('#statement_2-text').fill('We should hold the picnic outside')
            page.locator('#scenario-builder-title').fill('Readable symbols')
            _rename_editor_symbol(page, 'statement_2', 'picnic')
            rule = page.locator('.scenario-rule-card').first
            rule.locator('[data-literal]').nth(0).select_option('forecast')
            rule.locator('[data-literal]').nth(1).select_option('picnic')
            rule.locator('summary').click()
            page.get_by_role('button', name='Rename symbol rule_3', exact=True).click()
            page.locator('#scenario-rename-to').fill('weather_rule')
            page.locator('#scenario-rename-apply').click()
            _preview_editor(page)
            baseline = page.evaluate('scenarioFromBuilder(false)')
            page.locator('#scenario-symbol-renamer > summary').click()
            page.locator('#scenario-rename-from').select_option('forecast')
            for invalid in ['weather_rule', '-sunny', '__proto__']:
                page.locator('#scenario-rename-to').fill(invalid)
                page.locator('#scenario-rename-apply').click()
                assert page.evaluate('scenarioFromBuilder(false)') == baseline
                expect(page.locator('#scenario-rename-to')).to_have_attribute('aria-invalid', 'true')
                expect(page.locator('#scenario-library-submit')).to_be_disabled()
                expect(page.locator('#scenario-preview-btn')).to_be_disabled()
            page.locator('#scenario-rename-to').press('Escape')
            expect(page.locator('#scenario-rename-to')).not_to_have_attribute('aria-invalid', 'true')
            expect(page.locator('#modal-scenario-library')).to_have_class(re.compile('visible'))
            expect(page.locator('#scenario-library-submit')).to_be_enabled()
            _rename_editor_symbol(page, 'forecast', 'sunny')
            expect(page.locator('#scenario-library-submit')).to_be_disabled()
            expect(page.locator('#scenario-editor-preview')).to_be_hidden()
            _rename_editor_symbol(page, 'sunny', 's' * 100)
            page.locator('.scenario-statement-details').first.locator('summary').click()
            for width in [1440, 390]:
                page.set_viewport_size({'width': width, 'height': 900})
                _axe_report(page, f'symbol rename at {width}px')
                assert page.locator('#modal-scenario-library .modal-content').evaluate('el => el.scrollWidth <= el.clientWidth + 1')
            _save_browser_evidence(page, 'symbol-rename-mobile')
            _rename_editor_symbol(page, 's' * 100, 'sunny')
            _preview_editor(page)
            with page.expect_response(lambda r: r.url.endswith('/api/projects/import') and r.request.method == 'POST') as created:
                page.locator('#scenario-library-submit').click()
            project = created.value.json()
            assert project['scenario']['rules']['weather_rule']['premises'] == ['sunny']
            assert project['scenario']['rules']['weather_rule']['conclusion'] == 'picnic'
            assert project['af']['labels_by_proposition']['picnic'] == 'accepted'
            assert not errors
        finally:
            browser.close()


def test_symbol_rename_private_metadata_undercuts_and_portability(live_browser_server):
    from playwright.sync_api import expect, sync_playwright
    original = {
        'title': 'Private rename', 'description': 'p and r in this text are not rewritten.',
        'facts': {'p': {'description': 'Evidence', 'category': 'Record', 'source': 'note.txt'}, 'p1': {'description': 'Other evidence'}},
        'assumptions': {'a': {'description': 'Reliable', 'negated_description': 'Unreliable', 'block': 3, 'active': False}},
        'propositions': {'q': {'description': 'Intermediate', 'negated_description': 'No intermediate'}},
        'conclusions': {'c': {'description': 'Decision', 'negated_description': 'No decision'}},
        'rules': {
            'r': {'type': 'defeasible', 'premises': ['p'], 'conclusion': 'q', 'block': 2, 'active': False,
                  'negated_description': 'r is defeated', 'category': 'Record', 'source': 'note.txt'},
            'u': {'type': 'defeasible', 'premises': ['p1', '-a'], 'conclusion': '-r', 'block': 3},
            's': {'type': 'strict', 'premises': ['q'], 'conclusion': '-c'},
        },
        'sources': [{'filename': 'note.txt', 'text': 'Reference p and r.\n', 'url': 'https://example.org/p'}],
    }
    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        try:
            assert page.request.post(f'{live_browser_server}/api/auth/dev/login', data={'email': 'rename-private@example.org'}).ok
            created = page.request.post(f'{live_browser_server}/api/projects/import', data={'name': original['title'], 'scenario': original})
            assert created.ok, created.text()
            project = created.json()
            _goto_ready_demo(page, live_browser_server)
            page.locator('#workspace-btn').click()
            page.locator('#workspace-tab-projects').click()
            page.locator('#project-list').get_by_role('button', name='Open', exact=True).click()
            expect(page.locator('#scenario-name')).to_have_text(original['title'])
            page.locator('#scenario-materials-btn').click()
            page.locator('#scenario-glossary-panel > summary').click()
            page.locator('#scenario-glossary-text').fill('p = Updated evidence')
            expect(page.locator('#scenario-rename-to')).to_be_disabled()
            page.locator('#scenario-apply-glossary').click()
            expect(page.locator('#p-text')).to_have_value('Updated evidence')
            page.locator('#scenario-sources-summary').click()
            page.locator('#library-sources-new-text-0').fill('Pending reference p and -r.\n')
            changes = [('p', 'evidence'), ('a', 'reliable'), ('q', 'intermediate'), ('c', 'decision'), ('r', 'inference'), ('s', 'strict_rule')]
            for old, new in changes:
                _rename_editor_symbol(page, old, new)
            draft = page.evaluate('scenarioFromBuilder(false)')
            assert draft['facts']['p1']['description'] == 'Other evidence'
            assert draft['facts']['evidence']['description'] == 'Updated evidence'
            assert draft['facts']['evidence']['source'] == 'note.txt'
            assert draft['assumptions']['reliable'] == project['scenario']['assumptions']['a']
            assert draft['propositions']['intermediate'] == project['scenario']['propositions']['q']
            assert draft['conclusions']['decision'] == project['scenario']['conclusions']['c']
            assert draft['rules']['u']['premises'] == ['p1', '-reliable']
            assert draft['rules']['u']['conclusion'] == '-inference'
            assert draft['rules']['strict_rule']['conclusion'] == '-decision'
            for field in ['active', 'block', 'negated_description', 'category', 'source']:
                assert draft['rules']['inference'][field] == project['scenario']['rules']['r'][field]
            expect(page.locator('#library-sources-new-text-0')).to_have_value('Pending reference p and -r.\n')
            # Renaming is local until Save & open, and both editor views agree.
            assert page.request.get(f'{live_browser_server}/api/projects/{project["id"]}').json()['version'] == 1
            page.locator('#scenario-mode-text').click()
            expect(page.locator('#scenario-rule-text')).to_have_value(re.compile('-inference'))
            page.locator('#scenario-rule-text').fill(page.locator('#scenario-rule-text').input_value() + '\n# Preserve metadata')
            expect(page.locator('#scenario-rename-to')).to_be_disabled()
            page.locator('#scenario-mode-guided').click()
            _preview_editor(page)
            with page.expect_response(lambda r: r.url.endswith('/api/projects/' + project['id']) and r.request.method == 'PUT') as updated:
                page.locator('#scenario-library-submit').click()
            saved = updated.value.json()
            assert saved['version'] == 2
            mapping = dict(changes)
            assert saved['af']['labels_by_proposition'] == {
                ('-' if key.startswith('-') else '') + mapping.get(key.removeprefix('-'), key.removeprefix('-')): label
                for key, label in project['af']['labels_by_proposition'].items()
            }
            page.locator('#scenario-library-btn').click()
            with page.expect_download() as download:
                page.locator('#scenario-download-current').click()
            envelope = json.loads(Path(download.value.path()).read_text())
            assert envelope['version'] == 3 and envelope['scenario'] == saved['scenario']
            assert envelope['scenario']['sources'][0]['text'] == 'Pending reference p and -r.\n'
            page.locator('#scenario-tab-file').click()
            page.locator('#scenario-file-input').set_input_files({'name': 'renamed.json', 'mimeType': 'application/json', 'buffer': json.dumps(envelope).encode()})
            _load_editor_files(page)
            assert page.evaluate('scenarioFromBuilder(false)') == saved['scenario']
            assert not errors
        finally:
            browser.close()


def test_symbol_rename_in_large_rule_text_editor(live_browser_server):
    from playwright.sync_api import expect, sync_playwright
    raw = {'title': 'Large symbol catalog', 'facts': {f'p{i}': {'description': f'Evidence {i}'} for i in range(101)},
           'conclusions': {'c': {'description': 'Decision'}}, 'rules': {'r': {'type': 'defeasible', 'premises': ['p0'], 'conclusion': 'c'}}}
    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page()
        try:
            assert page.request.post(f'{live_browser_server}/api/auth/dev/login', data={'email': 'rename-large@example.org'}).ok
            _goto_ready_demo(page, live_browser_server)
            page.locator('#scenario-library-btn').click()
            page.locator('#scenario-tab-file').click()
            page.locator('#scenario-file-input').set_input_files({'name': 'large.json', 'mimeType': 'application/json', 'buffer': json.dumps(raw).encode()})
            _load_editor_files(page)
            expect(page.locator('#scenario-mode-guided')).to_be_disabled()
            expect(page.locator('#scenario-rule-text')).to_be_visible()
            _rename_editor_symbol(page, 'p0', 'evidence_zero')
            expect(page.locator('#scenario-rule-text')).to_have_value(re.compile('evidence_zero => c'))
            _preview_editor(page)
            expect(page.locator('#scenario-preview-results')).to_contain_text('accepted')
        finally:
            browser.close()


def test_three_part_scenario_import_materials_and_portable_export(live_browser_server):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 900})
        reader = browser.new_page(viewport={'width': 390, 'height': 844})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('dialog', lambda dialog: dialog.accept())
        try:
            assert page.request.post(f'{live_browser_server}/api/auth/dev/login', data={'email': 'materials@example.org'}).ok
            _goto_ready_demo(page, live_browser_server)
            page.locator('#scenario-library-btn').click()
            assert page.locator('#scenario-tab-aspic').count() == 0
            page.locator('#scenario-tab-file').click()
            page.locator('#scenario-file-input').set_input_files([
                {'name': 'Picnic.aspic', 'mimeType': 'text/plain', 'buffer': b'-> sunny\n-> windy\n\nsunny => outside [sunshine]\n\nwindy => -outside [wind]'},
                {'name': 'glossary.txt', 'mimeType': 'text/plain', 'buffer': b'sunny = The forecast is sunny\nwindy = A strong wind is expected\noutside = We should hold the picnic outside'},
                {'name': 'weather.md', 'mimeType': 'text/markdown', 'buffer': b'The picnic forecast is valid only before noon. <script>bad()</script>'},
            ])
            _load_editor_files(page)
            expect(page.locator('#scenario-builder-title')).to_have_value('Picnic')
            expect(page.locator('#sunny-text')).to_have_value('The forecast is sunny')
            page.locator('#scenario-sources-summary').click()
            expect(page.locator('#library-sources-new-text-0')).to_have_value(re.compile('before noon'))
            page.locator('#library-sources-new-url-0').fill('https://example.org/weather')
            # Entry and representation changes retain all three parts of one draft.
            page.locator('#scenario-tab-new').click()
            page.locator('#scenario-mode-text').click()
            expect(page.locator('#scenario-rule-text')).to_have_value(re.compile('# Block 2'))
            page.locator('#scenario-rule-text').fill(page.locator('#scenario-rule-text').input_value() + '\n# A harmless comment')
            page.locator('#scenario-mode-guided').click()
            expect(page.locator('#sunny-text')).to_have_value('The forecast is sunny')
            expect(page.locator('#library-sources-new-text-0')).to_have_value(re.compile('before noon'))
            _preview_editor(page)
            expect(page.locator('#scenario-preview-results')).to_contain_text('rejected')
            _axe_report(page, 'unified scenario and complete materials preview')
            _save_browser_evidence(page, 'unified-scenario-preview')
            page.set_viewport_size({'width': 390, 'height': 844})
            _axe_report(page, 'mobile unified scenario preview')
            assert page.locator('#modal-scenario-library .modal-content').evaluate('el => el.scrollWidth <= el.clientWidth')
            _save_browser_evidence(page, 'mobile-unified-scenario')
            with page.expect_response(lambda r: r.url.endswith('/api/projects/import') and r.request.method == 'POST') as created:
                page.locator('#scenario-library-submit').click()
            project = created.value.json()
            assert project['scenario']['sources'][0]['filename'] == 'weather.md'
            expect(page.locator('#scenario-name')).to_have_text('Picnic')
            page.set_viewport_size({'width': 1440, 'height': 900})
            page.locator('#scenario-materials-btn').click()
            expect(page.locator('#scenario-editor-heading')).to_have_text('Edit private scenario')
            page.locator('#sunny-text').fill('The morning forecast is sunny')
            page.locator('#library-sources-new-text-0').fill('Corrected forecast: dry until noon.')
            _preview_editor(page)
            with page.expect_response(lambda r: r.url.endswith('/api/projects/' + project['id']) and r.request.method == 'PUT') as saved:
                page.locator('#scenario-library-submit').click()
            updated = saved.value.json()
            assert updated['version'] == 2
            assert updated['scenario']['facts']['sunny']['description'] == 'The morning forecast is sunny'
            assert updated['af']['labels_by_proposition'] == project['af']['labels_by_proposition']
            page.locator('#scenario-library-btn').click()
            with page.expect_download() as downloaded:
                page.locator('#scenario-download-current').click()
            document = json.loads(Path(downloaded.value.path()).read_text())
            assert document['version'] == 3 and document['source_scenario_id'] is None
            assert document['scenario']['sources'] == updated['scenario']['sources']
            page.locator('#scenario-tab-file').click()
            page.locator('#scenario-file-input').set_input_files({'name': 'scenario.json', 'mimeType': 'application/json', 'buffer': json.dumps(document).encode()})
            _load_editor_files(page)
            expect(page.locator('#library-sources-new-text-0')).to_have_value('Corrected forecast: dry until noon.')
            page.locator('#scenario-library-cancel').click()
            shared = page.request.post(f'{live_browser_server}/api/projects/{project["id"]}/shares', data={}).json()
            _goto_ready_demo(reader, shared['url'])
            reader.locator('#scenario-materials-btn').click()
            expect(reader.locator('#materials-save')).to_be_hidden()
            expect(reader.locator('#materials-glossary')).to_have_attribute('readonly', '')
            reader.locator('#materials-source-editor summary').click()
            expect(reader.locator('#materials-source-editor pre')).to_have_text('Corrected forecast: dry until noon.')
            _axe_report(reader, 'read-only shared reference documents')
            page.evaluate('clearScenarioMaterials()')
            assert page.evaluate('scenarioLibrary.target === null && !scenarioLibrary.dirty')
            assert page.locator('#library-sources-new textarea').count() == 0
            assert not errors
        finally:
            browser.close()


@pytest.mark.parametrize('failed_load', [False, True])
def test_download_recovers_when_library_opens_during_scenario_load(live_browser_server, failed_load):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page()
        try:
            _goto_ready_demo(page, live_browser_server)
            page.wait_for_function('!hasPendingStateRequest()')
            previous = page.locator('#scenario-select').input_value()
            target = 'nba_rebuild' if previous != 'nba_rebuild' else 'fire_prevention'
            pending = []
            page.route('**/state', lambda route: pending.append(route))
            page.locator('#scenario-select').select_option(target)
            page.locator('#scenario-library-btn').click()
            expect(page.locator('#scenario-download-current')).to_be_disabled()
            assert len(pending) == 1
            if failed_load:
                pending[0].fulfill(status=503, content_type='application/json', body='{"detail":"Test outage"}')
            else:
                pending[0].continue_()
            expect(page.locator('#scenario-download-current')).to_be_enabled()
            with page.expect_download() as downloaded:
                page.locator('#scenario-download-current').click()
            portable = json.loads(Path(downloaded.value.path()).read_text())
            assert portable['source_scenario_id'] is None
            expected = page.request.get(f'{live_browser_server}/scenarios/{previous if failed_load else target}').json()['scenario']
            assert portable['scenario']['rules'] == expected['rules']
            assert {entry['filename'] for entry in portable['scenario']['sources']} >= set(expected['corpus'])
        finally:
            browser.close()


def test_reviewed_community_examples_in_browser(live_browser_server):
    from playwright.sync_api import expect, sync_playwright

    scenario = {
        "title": "Picnic", "description": "A useful public teaching example.",
        "sources": [{"filename": "reference.txt", "text": "Shareable reference text. <script>bad()</script>"}],
        "facts": {"sunny": {"description": "It is sunny"}},
        "conclusions": {"outside": {"description": "Hold the picnic outside"}},
        "rules": {"r1": {"type": "defeasible", "premises": ["sunny"], "conclusion": "outside"}},
    }
    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        author = browser.new_page(viewport={"width": 1200, "height": 900})
        admin = browser.new_page(viewport={"width": 1200, "height": 900})
        reader = browser.new_page(viewport={"width": 390, "height": 844})
        errors = []
        for page in [author, admin, reader]:
            page.on("pageerror", lambda error: errors.append(str(error)))
        admin.on("dialog", lambda dialog: dialog.accept())
        try:
            assert author.request.post(f"{live_browser_server}/api/auth/dev/login", data={"email": "author@example.org"}).ok
            created = author.request.post(f"{live_browser_server}/api/projects/import", data={
                "name": "Community picnic", "description": "Private research note", "scenario": scenario,
            }).json()
            _goto_ready_demo(author, live_browser_server)
            author.locator("#scenario-library-btn").click()
            author.locator("#scenario-my-projects").click()
            author.locator(f'[data-project-id="{created["id"]}"][data-project-action="open"]').click()
            expect(author.locator("#scenario-name")).to_have_text("Community picnic")
            author.locator("#scenario-library-btn").click()
            author.locator("#scenario-my-projects").click()
            author.get_by_role("button", name="Suggest as example", exact=True).click()
            expect(author.locator("#example-review-snapshot")).not_to_contain_text("Private research note")
            expect(author.locator("#example-review-snapshot")).to_contain_text('Reference documents (published in full)')
            author.locator('#example-review-snapshot .source-card summary').click()
            expect(author.locator('#example-review-snapshot .source-card pre')).to_contain_text('Shareable reference text.')
            expect(author.get_by_role("button", name="Submit for review", exact=True)).to_be_disabled()
            _axe_report(author, "author public snapshot consent")
            _save_browser_evidence(author, "example-consent")
            author.locator("#example-public-consent").check()
            author.get_by_role("button", name="Submit for review", exact=True).click()
            expect(author.locator("#examples-list")).to_contain_text("Awaiting review")
            assert reader.request.get(f"{live_browser_server}/scenarios").json()["scenarios"][-1]["category"] != "community"

            assert admin.request.post(f"{live_browser_server}/api/auth/dev/login", data={"email": "curator@example.org"}).ok
            _goto_ready_demo(admin, live_browser_server)
            admin.locator("#scenario-library-btn").click()
            admin.locator("#scenario-example-submissions").click()
            expect(admin.locator("#examples-list")).to_contain_text("Community picnic")
            _axe_report(admin, "administrator scenario review queue")
            admin.get_by_role("button", name="Review snapshot", exact=True).click()
            expect(admin.locator("#example-review-snapshot")).to_contain_text("It is sunny")
            _axe_report(admin, "administrator snapshot decision")
            _save_browser_evidence(admin, "example-review")
            admin.set_viewport_size({"width": 390, "height": 844})
            _axe_report(admin, "mobile administrator snapshot decision")
            assert admin.locator("#modal-example-review .modal-content").evaluate("element => element.scrollWidth <= element.clientWidth")
            admin.set_viewport_size({"width": 1200, "height": 900})
            admin.get_by_role("button", name="Approve & publish", exact=True).click()
            expect(admin.locator("#modal-example-review")).not_to_have_class(re.compile("visible"))
            _goto_ready_demo(reader, live_browser_server)
            option = reader.locator('#scenario-select optgroup[label="Community examples"] option')
            expect(option).to_have_count(1)
            public_id = option.get_attribute("value")
            reader.locator("#scenario-select").select_option(public_id)
            expect(reader.locator("#conclusions-list")).to_contain_text("Accepted")
            reader.locator("#scenario-library-btn").click()
            with reader.expect_download() as downloaded:
                reader.locator("#scenario-download-current").click()
            portable = json.loads(Path(downloaded.value.path()).read_text())
            assert portable["source_scenario_id"] is None
            assert portable["scenario"]["title"] == "Community picnic"
            assert portable['scenario']['sources'] == scenario['sources']
            assert "Private research note" not in str(portable)
            reader.locator("#scenario-library-cancel").click()
            _axe_report(reader, "mobile community example")

            # A direct administrator publication uses the same consent preview.
            own = admin.request.post(f"{live_browser_server}/api/projects/import", data={
                "name": "Administrator picnic", "scenario": scenario,
            }).json()
            admin.locator("#workspace-tab-projects").click()
            admin.locator("#projects-refresh-btn").click()
            admin.locator(f'[data-project-id="{own["id"]}"][data-project-action="open"]').click()
            expect(admin.locator("#scenario-name")).to_have_text("Administrator picnic")
            admin.locator("#scenario-library-btn").click()
            admin.locator("#scenario-my-projects").click()
            admin.get_by_role("button", name="Publish as example", exact=True).click()
            admin.locator("#example-public-consent").check()
            admin.get_by_role("button", name="Publish example", exact=True).click()
            expect(admin.locator("#examples-list")).to_contain_text("Published")

            admin.locator("#examples-filter").select_option("published")
            card = admin.locator("#examples-list .project-card").filter(has_text="Community picnic")
            card.get_by_role("button", name="View snapshot", exact=True).click()
            admin.get_by_role("button", name="Remove from examples", exact=True).click()
            expect(admin.locator("#example-review-status")).to_contain_text("short reason")
            admin.locator("#example-review-note").fill("Updating the teaching example.")
            admin.get_by_role("button", name="Remove from examples", exact=True).click()
            expect(admin.locator("#modal-example-review")).not_to_have_class(re.compile("visible"))
            assert reader.request.get(f"{live_browser_server}/scenarios/{public_id}").status == 404
            assert not errors
        finally:
            browser.close()


def test_scenario_library_signed_out_and_small_screen(live_browser_server):
    from uuid import uuid4
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844}, reduced_motion="reduce")
        try:
            _goto_ready_demo(page, live_browser_server)
            page.locator("#scenario-library-btn").click()
            expect(page.locator("#scenario-signin-required")).to_be_visible()
            expect(page.locator("#scenario-library-submit")).to_be_disabled()
            page.locator("#scenario-tab-new").focus()
            page.keyboard.press("ArrowRight")
            expect(page.locator("#scenario-tab-file")).to_be_focused()
            expect(page.locator("#scenario-file-input")).to_be_disabled()
            page.keyboard.press("Escape")
            expect(page.locator("#scenario-library-btn")).to_be_focused()
            assert page.request.post(f"{live_browser_server}/api/auth/dev/login", data={"email": f"{uuid4().hex}@example.org"}).ok
            _reload_ready_demo(page)
            page.locator("#scenario-library-btn").click()
            page.locator("#scenario-starter-btn").click()
            for width in [390, 780, 1440]:
                page.set_viewport_size({"width": width, "height": 900})
                _axe_report(page, f"scenario builder at {width}px")
                assert page.locator("#modal-scenario-library .scenario-library-content").evaluate("e => e.scrollWidth <= e.clientWidth + 1")
            page.set_viewport_size({"width": 390, "height": 844})
            _save_browser_evidence(page, "scenario-builder-mobile")
            _preview_editor(page)
            page.locator("#scenario-library-submit").click()
            expect(page.locator("#scenario-name")).to_have_text("Planning a picnic")
            expect(page.locator("#conclusions-list")).to_contain_text("Undecided")
            page.locator("#scenario-library-btn").click()
            page.locator("#scenario-tab-file").click()
            _axe_report(page, "mobile file picker")
        finally:
            browser.close()


def test_scenario_import_failures_leave_current_work_untouched(live_browser_server):
    from uuid import uuid4
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page()
        try:
            assert page.request.post(f"{live_browser_server}/api/auth/dev/login", data={"email": f"{uuid4().hex}@example.org"}).ok
            _goto_ready_demo(page, live_browser_server)
            before = page.locator("#scenario-name").inner_text()
            page.locator("#scenario-library-btn").click()
            page.locator("#scenario-tab-file").click()
            picker = page.locator("#scenario-file-input")
            picker.set_input_files({"name": "bad.yaml", "mimeType": "text/yaml", "buffer": b"title: ["})
            page.locator("#scenario-load-files").click()
            expect(page.locator("#scenario-library-status")).to_contain_text("Cannot read")
            expect(page.locator("#scenario-library-submit")).to_be_disabled()
            picker.set_input_files({"name": "huge.json", "mimeType": "application/json", "buffer": b"x" * 1_000_001})
            expect(page.locator("#scenario-library-status")).to_contain_text("at most 1 MB")
            picker.set_input_files({"name": "bad-utf8.yaml", "mimeType": "text/yaml", "buffer": b"\xff\xfe"})
            page.locator("#scenario-load-files").click()
            expect(page.locator("#scenario-library-status")).to_contain_text("UTF-8")
            picker.set_input_files({"name": "unknown.yaml", "mimeType": "text/yaml", "buffer": b"title: Unknown\nconclusions: {}\nrules:\n  r1: {type: defeasible, premises: [missing], conclusion: missing}"})
            page.locator("#scenario-load-files").click()
            expect(page.locator("#scenario-library-status")).to_contain_text("unknown identifier")
            expect(page.locator("#scenario-name")).to_have_text(before)
            assert page.request.get(f"{live_browser_server}/api/projects").json()["projects"] == []
            page.locator("#scenario-library-cancel").click()
            expect(page.locator("#scenario-name")).to_have_text(before)
        finally:
            browser.close()


def test_builder_deleted_statement_does_not_rebind_a_rule(live_browser_server):
    from uuid import uuid4
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page()
        try:
            assert page.request.post(f"{live_browser_server}/api/auth/dev/login", data={"email": f"{uuid4().hex}@example.org"}).ok
            _goto_ready_demo(page, live_browser_server)
            page.locator("#scenario-library-btn").click()
            page.locator("#scenario-starter-btn").click()
            row = page.locator(".scenario-statement-card").first
            removed_id = row.get_attribute("data-statement-id")
            row.get_by_role("button").click()
            page.locator("#scenario-add-statement").click()
            page.locator(".scenario-statement-row input").last.fill("An unrelated new statement")
            assert page.locator(".scenario-rule-card [data-literal]").first.input_value() == removed_id
            page.locator("#scenario-preview-btn").click()
            expect(page.locator("#scenario-library-status")).to_contain_text("Choose an existing statement")
            expect(page.locator("#context-indicator")).to_have_text("Example")
            page.locator("#scenario-library-cancel").click()
            page.locator("#scenario-library-btn").click()
            expect(page.locator("#scenario-builder-title")).to_have_value("Planning a picnic")
        finally:
            browser.close()


def test_scenario_library_late_create_does_not_replace_another_view(live_browser_server):
    from uuid import uuid4
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page()
        pending = []
        try:
            assert page.request.post(f"{live_browser_server}/api/auth/dev/login", data={"email": f"{uuid4().hex}@example.org"}).ok
            _goto_ready_demo(page, live_browser_server)
            page.route("**/api/projects/import", lambda route: pending.append(route))
            page.locator("#scenario-library-btn").click()
            page.locator("#scenario-starter-btn").click()
            _preview_editor(page)
            page.locator("#scenario-library-submit").click()
            expect(page.locator("#scenario-library-submit")).to_have_text("Saving...")
            page.locator("#scenario-library-cancel").click()
            options = page.locator("#scenario-select option").evaluate_all("items => items.map(item => ({id: item.value, name: item.textContent}))")
            target = next(item for item in options if item["id"] != "popov_v_hayashi")
            page.locator("#scenario-select").select_option(target["id"])
            expect(page.locator("#scenario-name")).to_have_text(target["name"])
            assert len(pending) == 1
            response = pending[0].fetch()
            assert response.status == 201
            pending[0].fulfill(response=response)
            expect(page.locator("#global-status")).to_contain_text("Open it from My projects")
            expect(page.locator("#scenario-name")).to_have_text(target["name"])
            assert len(page.request.get(f"{live_browser_server}/api/projects").json()["projects"]) == 1
        finally:
            browser.close()


def test_scenario_file_failure_preserves_draft_and_escapes_text(live_browser_server):
    from uuid import uuid4
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page()
        try:
            assert page.request.post(f"{live_browser_server}/api/auth/dev/login", data={"email": f"{uuid4().hex}@example.org"}).ok
            _goto_ready_demo(page, live_browser_server)
            page.on("dialog", lambda dialog: dialog.accept())
            page.locator("#scenario-library-btn").click()
            page.locator("#scenario-tab-file").click()
            payload = {"title": "<svg onload=alert(1)>", "description": "<img src=x onerror=alert(1)>", "conclusions": {}, "rules": {}}
            picker = page.locator("#scenario-file-input")
            picker.set_input_files({"name": "safe.json", "mimeType": "application/json", "buffer": json.dumps(payload).encode()})
            _load_editor_files(page)
            expect(page.locator("#scenario-builder-title")).to_have_value(payload["title"])
            expect(page.locator("#scenario-builder-description")).to_have_value(payload["description"])
            assert page.locator("#scenario-builder-form img, #scenario-builder-form svg").count() == 0
            picker.set_input_files({"name": "bad.yaml", "mimeType": "text/yaml", "buffer": b"title: ["})
            page.locator("#scenario-load-files").click()
            expect(page.locator("#scenario-library-status")).to_contain_text("Cannot read")
            expect(page.locator("#scenario-builder-title")).to_have_value(payload["title"])
            expect(page.locator("#scenario-library-submit")).to_be_disabled()
        finally:
            browser.close()


def test_unified_editor_raw_validation_stale_save_and_atomic_files(live_browser_server):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page()
        page.on('dialog', lambda dialog: dialog.accept())
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        try:
            assert page.request.post(f'{live_browser_server}/api/auth/dev/login', data={'email': 'editor-races@example.org'}).ok
            _goto_ready_demo(page, live_browser_server)
            page.locator('#scenario-library-btn').click()
            page.locator('#scenario-mode-text').click()
            expect(page.locator('#scenario-rule-text')).to_have_value('')
            page.locator('#scenario-builder-title').fill('Text-first scenario')
            page.locator('#scenario-rule-text').fill('-> evidence\nevidence => claim [reason]')
            page.locator('#scenario-glossary-panel summary').click()
            page.locator('#scenario-glossary-text').fill('evidence = Available evidence\nclaim = Our claim')
            page.locator('#scenario-mode-guided').click()
            expect(page.locator('#claim-text')).to_have_value('Our claim')
            expect(page.locator('#scenario-library-submit')).to_be_disabled()
            page.locator('#scenario-mode-text').click()
            syntax = page.locator('#scenario-rule-text').input_value()
            page.locator('#scenario-rule-text').fill('this is not ASPIC')
            page.locator('#scenario-mode-guided').click()
            expect(page.locator('#scenario-library-status')).to_contain_text('Check ASPIC- line')
            expect(page.locator('#scenario-rule-text-panel')).to_be_visible()
            assert page.evaluate('scenarioLibrary.statements.find(s => s.id === "claim").description') == 'Our claim'
            page.locator('#scenario-rule-text').fill(syntax)
            page.locator('#scenario-mode-guided').click()
            expect(page.locator('#claim-text')).to_be_visible()
            # A document failure after a valid KB must leave the whole draft intact.
            page.locator('#scenario-tab-file').click()
            page.locator('#scenario-file-input').set_input_files([
                {'name': 'replacement.json', 'mimeType': 'application/json', 'buffer': b'{"title":"Replacement","rules":{},"conclusions":{}}'},
                {'name': 'bad.pdf', 'mimeType': 'application/pdf', 'buffer': b'not a PDF'},
            ])
            page.locator('#scenario-load-files').click()
            expect(page.locator('#scenario-library-status')).to_contain_text('Your previous draft is unchanged')
            expect(page.locator('#scenario-builder-title')).to_have_value('Text-first scenario')
            _preview_editor(page)
            with page.expect_response(lambda r: r.url.endswith('/api/projects/import') and r.request.method == 'POST') as response:
                page.locator('#scenario-library-submit').click()
            project = response.value.json()
            expect(page.locator('#scenario-name')).to_have_text('Text-first scenario')
            page.locator('#scenario-materials-btn').click()
            page.locator('#claim-text').fill('My unsaved wording')
            _preview_editor(page)
            changed = page.request.put(f'{live_browser_server}/api/projects/{project["id"]}', data={'expected_version': 1, 'name': 'Concurrent save'})
            assert changed.ok
            page.locator('#scenario-library-submit').click()
            expect(page.locator('#scenario-library-status')).to_contain_text('has not replaced newer work')
            expect(page.locator('#claim-text')).to_have_value('My unsaved wording')
            assert page.request.get(f'{live_browser_server}/api/projects/{project["id"]}').json()['name'] == 'Concurrent save'
            assert not errors
        finally:
            browser.close()


def test_conclusion_cards_do_not_clip_wrapped_text(live_browser_server):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        try:
            for width, height in ((1440, 900), (1000, 720), (390, 844)):
                page = browser.new_page(viewport={"width": width, "height": height})
                _goto_ready_demo(page, live_browser_server)
                divider = page.locator("#h-resize-left")
                if divider.is_visible():
                    divider.press("Home")
                sizes = page.locator(".conclusion-card .conclusion-label").evaluate_all(
                    "labels => labels.map(label => ({visible: label.clientHeight, "
                    "content: label.scrollHeight}))"
                )
                assert len(sizes) >= 8
                assert all(size["content"] <= size["visible"] + 1 for size in sizes)
                page.close()
        finally:
            browser.close()


def test_assistant_markdown_is_inert_in_real_browser(live_browser_server):
    from playwright.sync_api import expect, sync_playwright

    payload = """# Safe heading

**Bold text** and [unsafe link](javascript:window.__abdaXssFired=1).

<a href="https://example.org/research" onclick="window.__abdaXssFired=2">safe external</a>
<img src="/xss-probe" onerror="window.__abdaXssFired=3">
<svg><a href="javascript:window.__abdaXssFired=4"><text>SVG probe</text></a></svg>
<math><mtext><img src="/math-probe" onerror="window.__abdaXssFired=5"></mtext></math>
<xmp></xmp><img src="/context-probe" onerror="window.__abdaXssFired=6">
<script>window.__abdaXssFired=7</script>
"""
    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page()
        try:
            _goto_ready_demo(page, live_browser_server)
            page.evaluate(
                """payload => {
                    window.__abdaXssFired = 0;
                    state.chatMessages = [{role: 'assistant', content: payload}];
                    state.chatPending = false;
                    renderChat();
                }""",
                payload,
            )
            expect(page.locator("#chat-messages h1")).to_have_text("Safe heading")
            expect(page.locator("#chat-messages strong")).to_have_text("Bold text")
            unsafe_link = page.get_by_role("link", name="unsafe link")
            assert unsafe_link.count() == 0
            safe_link = page.get_by_role("link", name="safe external")
            expect(safe_link).to_have_attribute("href", "https://example.org/research")
            expect(safe_link).to_have_attribute("rel", "nofollow noopener noreferrer")
            expect(safe_link).to_have_attribute("referrerpolicy", "no-referrer")
            assert page.locator(
                "#chat-messages script, #chat-messages style, #chat-messages svg, "
                "#chat-messages math, #chat-messages iframe, #chat-messages img, "
                "#chat-messages form, #chat-messages input, #chat-messages button"
            ).count() == 0
            assert page.locator(
                "#chat-messages [onerror], #chat-messages [onclick], "
                "#chat-messages [onload]"
            ).count() == 0
            page.wait_for_timeout(100)
            assert page.evaluate("window.__abdaXssFired") == 0
        finally:
            browser.close()


def test_oidc_logout_uses_fetch_origin_under_no_referrer_policy(
    live_browser_server,
):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page()
        observed: dict[str, str] = {}

        def intercept_logout(route):
            observed["origin"] = route.request.headers.get("origin", "")
            observed["method"] = route.request.method
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {"logout_url": f"{live_browser_server}/logout-complete"}
                ),
            )

        page.route("**/api/auth/logout", intercept_logout)
        page.route(
            "**/logout-complete",
            lambda route: route.fulfill(
                status=200,
                content_type="text/html",
                body="<!doctype html><title>Signed out</title><p>Signed out</p>",
            ),
        )
        try:
            _goto_ready_demo(page, live_browser_server)
            page.evaluate(
                """() => {
                    state.authSession = {
                      authenticated: true,
                      auth_mode: 'oidc',
                      login_url: '/auth/login',
                      user: {
                        id: 'browser-oidc-user',
                        email: 'browser-oidc@example.edu',
                        email_verified: true,
                        display_name: 'Browser OIDC',
                      },
                    };
                    renderAccountUI();
                }"""
            )
            page.locator("#workspace-btn").click()
            expect(page.locator("#account-signed-in")).to_be_visible()
            page.locator("#logout-btn").click()
            page.wait_for_url(f"{live_browser_server}/logout-complete")

            assert observed == {
                "method": "POST",
                "origin": live_browser_server,
            }
        finally:
            browser.close()


def test_argument_game_resolves_all_defenses_and_detects_a_cycle(
    live_browser_server,
):
    from playwright.sync_api import expect, sync_playwright

    def load_game(page, *, arguments, attacks, labels, root, conclusion):
        page.evaluate(
            """payload => {
                const rules = {};
                const descriptions = {};
                for (const argument of payload.arguments) {
                    rules[argument.top_rule] = {
                        type: 'defeasible',
                        premises: [],
                        conclusion: argument.conclusion,
                    };
                    descriptions[argument.conclusion] = argument.conclusion_nl;
                }
                state.bundle = {
                    scenario: {
                        title: 'Browser game semantic acceptance',
                        description: '',
                        facts: {},
                        assumptions: {},
                        propositions: {},
                        conclusions: {
                            [payload.conclusion]: {
                                description: descriptions[payload.conclusion],
                            },
                        },
                        rules,
                    },
                    af: {
                        arguments: payload.arguments,
                        attacks: payload.attacks,
                        labels_by_proposition: payload.labels,
                    },
                };
                state.descMap = descriptions;
                state.negDescMap = {};
                state.ruleIds = new Set(Object.keys(rules));
                openExplainModal(payload.conclusion);
                startGameWithRoot(payload.root);
            }""",
            {
                "arguments": arguments,
                "attacks": attacks,
                "labels": labels,
                "root": root,
                "conclusion": conclusion,
            },
        )

    def argument(identifier, conclusion, label):
        return {
            "id": identifier,
            "top_rule": f"rule_{identifier}",
            "conclusion": conclusion,
            "conclusion_nl": conclusion.replace("_", " "),
            "label": label,
            "sub_arguments": [],
        }

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page()
        try:
            _goto_ready_demo(page, live_browser_server)

            load_game(
                page,
                arguments=[
                    argument("root", "claim", "in"),
                    argument("counter_one", "counter_one", "out"),
                    argument("counter_two", "counter_two", "out"),
                    argument("defense_one", "defense_one", "in"),
                    argument("defense_two", "defense_two", "in"),
                ],
                attacks=[
                    {"from": "counter_one", "to": "root", "type": "rebut"},
                    {"from": "counter_two", "to": "root", "type": "rebut"},
                    {
                        "from": "defense_one",
                        "to": "counter_one",
                        "type": "rebut",
                    },
                    {
                        "from": "defense_two",
                        "to": "counter_two",
                        "type": "rebut",
                    },
                ],
                labels={
                    "claim": "accepted",
                    "counter_one": "rejected",
                    "counter_two": "rejected",
                    "defense_one": "accepted",
                    "defense_two": "accepted",
                },
                root="root",
                conclusion="claim",
            )

            page.locator('[data-move="cb"][data-arg="counter_one"]').click()
            page.locator('[data-move="htb"][data-arg="defense_one"]').click()
            page.locator('[data-resolve="uncontested"]').click()
            assert page.evaluate("gameNodes[gameRootId].resolution") is None
            expect(
                page.locator('[data-move="cb"][data-arg="counter_two"]')
            ).to_be_visible()

            page.locator('[data-move="cb"][data-arg="counter_two"]').click()
            page.locator('[data-move="htb"][data-arg="defense_two"]').click()
            page.locator('[data-resolve="uncontested"]').click()
            assert page.evaluate("gameNodes[gameRootId].resolution") == "conceded"
            expect(
                page.locator(
                    "#gnode-gn1 > .game-node-inner > .game-node-status "
                    "> .badge-accepted"
                )
            ).to_be_visible()

            load_game(
                page,
                arguments=[
                    argument("cycle_root", "cycle_claim", "undec"),
                    argument("cycle_counter", "cycle_counter", "undec"),
                ],
                attacks=[
                    {
                        "from": "cycle_counter",
                        "to": "cycle_root",
                        "type": "rebut",
                    },
                    {
                        "from": "cycle_root",
                        "to": "cycle_counter",
                        "type": "rebut",
                    },
                ],
                labels={
                    "cycle_claim": "undecided",
                    "cycle_counter": "undecided",
                },
                root="cycle_root",
                conclusion="cycle_claim",
            )

            page.locator('[data-move="cb"][data-arg="cycle_counter"]').click()
            page.locator('[data-cycle-htb="cycle_root"]').click()
            assert page.evaluate("gameNodes[gameRootId].resolution") == "undecided"
            expect(
                page.locator(
                    "#gnode-gn1 > .game-node-inner > .game-node-status "
                    "> .badge-undecided"
                )
            ).to_be_visible()
            expect(page.locator(".game-node-cycle")).to_be_visible()
        finally:
            browser.close()


def test_user_authored_content_is_escaped_in_real_browser(live_browser_server):
    from playwright.sync_api import expect, sync_playwright

    project_probe = '<img src="/project-probe" onerror="window.__abdaXssFired=10">'
    content_probe = '<img src="/content-probe" onerror="window.__abdaXssFired=11">'
    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page()
        try:
            _goto_ready_demo(page, live_browser_server)
            page.evaluate("window.__abdaXssFired = 0")
            page.locator("#workspace-btn").click()
            page.locator("#dev-login-email").fill("content-safety@example.edu")
            page.locator("#dev-login-name").fill("Content Safety")
            page.locator('#dev-login-form button[type="submit"]').click()
            expect(page.locator("#account-signed-in")).to_be_visible()
            page.locator("#workspace-tab-projects").click()
            page.locator("#project-name-input").fill(project_probe)
            page.locator("#project-description-input").fill(project_probe)
            page.locator("#project-create-btn").click()
            expect(page.locator("#context-indicator")).to_have_text("Private project")
            expect(page.locator("#current-project-card h3").first).to_contain_text(
                project_probe
            )
            assert page.locator('img[src="/project-probe"]').count() == 0
            page.keyboard.press("Escape")

            page.evaluate(
                """probe => {
                    const scenario = state.bundle.scenario;
                    const conclusion = Object.values(scenario.conclusions || {})[0];
                    const fact = Object.values(scenario.facts || {})[0];
                    const rule = Object.values(scenario.rules || {})[0];
                    if (conclusion) conclusion.description = probe;
                    if (fact) {
                      fact.description = probe;
                      fact.category = probe;
                      fact.source = probe;
                    }
                    if (rule) {
                      rule.category = probe;
                      rule.source = probe;
                    }
                    for (const argument of state.bundle.af.arguments || []) {
                      argument.conclusion_nl = probe;
                    }
                    indexBundle();
                    renderAll();
                }""",
                content_probe,
            )
            expect(page.locator("#conclusions-list")).to_contain_text(content_probe)
            expect(page.locator("#facts-list")).to_contain_text(content_probe)
            expect(page.locator("#kb-content")).to_contain_text(content_probe)
            assert page.locator('img[src="/content-probe"]').count() == 0
            assert page.locator("[onerror], [onclick], [onload]").count() == 0

            page.locator("#view-af-btn").click()
            page.locator("#af-modal-body .af-node").first.hover()
            expect(page.locator("#af-tooltip")).to_contain_text(content_probe)
            assert page.locator('#af-modal-body img[src="/content-probe"]').count() == 0
            page.keyboard.press("Escape")

            page.locator("#conclusions-list .btn-explain:not([disabled])").first.click()
            expect(page.locator("#modal-game")).to_contain_text(content_probe)
            assert page.locator('#modal-game img[src="/content-probe"]').count() == 0
            page.keyboard.press("Escape")

            page.evaluate(
                """probe => {
                    _renderProposal({
                      op: {
                        op: 'add-fact',
                        id: 'content_safety_probe',
                        fact: {
                          description: probe,
                          category: probe,
                          source: probe,
                        },
                      },
                      review_issues: [{severity: 'warning', message: probe}],
                    });
                }""",
                content_probe,
            )
            expect(page.locator("#edit-preview")).to_contain_text(content_probe)
            assert page.locator('#edit-preview img[src="/content-probe"]').count() == 0

            page.locator("#aspic-btn").click()
            expect(page.locator("#aspic-pre")).to_contain_text(content_probe)
            assert page.locator('#modal-aspic img[src="/content-probe"]').count() == 0
            page.keyboard.press("Escape")

            assert page.locator("[onerror], [onclick], [onload]").count() == 0
            page.wait_for_timeout(100)
            assert page.evaluate("window.__abdaXssFired") == 0
        finally:
            browser.close()


def test_mobile_item_question_reveals_chat(live_browser_server):
    from playwright.sync_api import expect, sync_playwright

    response = {
        "message": "This is a route-mocked mobile explanation.",
        "model": "browser-test-model",
        "billing_source": "trial",
        "cost_microusd": 0,
        "latency_ms": 1,
    }
    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        context = browser.new_context(
            viewport={"width": 390, "height": 844},
            reduced_motion="reduce",
        )
        page = context.new_page()
        page.route(
            "**/chat",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(response),
            ),
        )
        try:
            _goto_ready_demo(page, live_browser_server)
            page.evaluate(
                """() => {
                    state.authSession = {
                      authenticated: true,
                      auth_mode: 'dev',
                      user: {email: 'mobile-browser@example.edu'},
                    };
                    state.trial = {
                      active: true,
                      available_microusd: 5000000,
                    };
                    state.llmAccess.mode = 'funded';
                }"""
            )
            question = page.locator(".rule-info[data-desc]").first
            expect(question).to_be_visible()
            question.click()
            expect(page.locator("#chat-input")).to_have_value(re.compile('Can you explain'))
            expect(page.locator("#chat-messages")).not_to_contain_text("This is a route-mocked mobile explanation.")
            geometry = page.evaluate(
                """() => {
                    const panel = document.getElementById('right-panel')
                      .getBoundingClientRect();
                    const input = document.getElementById('chat-input')
                      .getBoundingClientRect();
                    return {
                      panelTop: panel.top,
                      panelBottom: panel.bottom,
                      inputTop: input.top,
                      inputBottom: input.bottom,
                      viewportHeight: window.innerHeight,
                    };
                }"""
            )
            assert 0 <= geometry["panelTop"] < geometry["viewportHeight"]
            assert geometry["panelBottom"] > 0
            assert 0 <= geometry["inputTop"]
            assert geometry["inputBottom"] <= geometry["viewportHeight"]
        finally:
            context.close()
            browser.close()


def test_switching_byok_provider_clears_the_previous_provider_key(
    live_browser_server,
):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page()
        try:
            _goto_ready_demo(page, live_browser_server)
            page.locator("#ai-access-btn").click()
            page.locator('input[name="ai-mode"][value="byok"]').check()

            provider_select = page.locator("#byok-provider-select")
            providers = provider_select.locator("option").evaluate_all(
                "options => options.map(option => option.value)",
            )
            assert len(providers) >= 2
            initial_provider = provider_select.input_value()
            next_provider = next(
                provider for provider in providers if provider != initial_provider
            )

            key_input = page.locator("#byok-api-key")
            reveal_button = page.locator("#byok-reveal-btn")
            key_input.fill("first-provider-only-secret")
            reveal_button.click()
            expect(key_input).to_have_attribute("type", "text")
            page.locator("#ai-access-form button[type=submit]").click()
            assert page.evaluate("state.llmAccess.apiKey") != ""

            provider_select.select_option(next_provider)

            expect(key_input).to_have_value("")
            expect(key_input).to_have_attribute("type", "password")
            expect(reveal_button).to_have_text("Show")
            expect(reveal_button).to_have_attribute("aria-pressed", "false")
            expect(page.locator("#ai-access-status")).to_contain_text(
                "previous provider key was cleared"
            )
            assert page.evaluate("state.llmAccess.apiKey") == ""

            page.locator("#ai-access-form button[type=submit]").click()
            expect(page.locator("#ai-access-status")).to_contain_text(
                "Paste a provider API key"
            )
        finally:
            browser.close()


def test_authenticated_workspace_keeps_each_successful_partial_refresh(
    live_browser_server,
):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page()
        try:
            _goto_ready_demo(page, live_browser_server)
            page.locator("#workspace-btn").click()
            page.locator("#dev-login-email").fill("partial-refresh@example.edu")
            page.locator("#dev-login-form button[type=submit]").click()
            expect(page.locator("#account-signed-in")).to_be_visible()

            page.evaluate(
                """async () => {
                    const original = apiRequest;
                    const activeTrial = {
                      active: true,
                      granted_microusd: 5000000,
                      spent_microusd: 1000,
                      reserved_microusd: 0,
                      available_microusd: 4999000,
                    };
                    state.trial = null;
                    apiRequest = (path, options = {}) => {
                      if (path === '/api/trial') return Promise.resolve(activeTrial);
                      if (path === '/api/projects') {
                        return Promise.reject(new Error('project refresh unavailable'));
                      }
                      return original(path, options);
                    };
                    await refreshAuthenticatedWorkspace({quiet: true});
                    window.__trialAfterPartialRefresh = state.trial;

                    state.projects = [];
                    apiRequest = (path, options = {}) => {
                      if (path === '/api/trial') {
                        return Promise.reject(new Error('trial refresh unavailable'));
                      }
                      if (path === '/api/projects') {
                        return Promise.resolve({projects: [{
                          id: 'partial-refresh-project',
                          name: 'Project from partial refresh',
                          description: '',
                          source_scenario_id: state.scenario_id,
                          version: 1,
                          created_at: new Date().toISOString(),
                          updated_at: new Date().toISOString(),
                        }]});
                      }
                      return original(path, options);
                    };
                    await refreshAuthenticatedWorkspace({quiet: true});
                }"""
            )

            assert page.evaluate("window.__trialAfterPartialRefresh.active") is True
            assert page.evaluate("state.projects.length") == 1
            expect(page.locator("#project-list")).to_contain_text(
                "Project from partial refresh"
            )
        finally:
            browser.close()


def test_authenticated_workspace_renders_a_fast_partial_refresh_immediately(
    live_browser_server,
):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page()
        try:
            _goto_ready_demo(page, live_browser_server)
            page.locator("#workspace-btn").click()
            page.locator("#dev-login-email").fill("fast-partial-refresh@example.edu")
            page.locator("#dev-login-form button[type=submit]").click()
            page.locator("#account-signed-in").wait_for(state="visible")

            page.evaluate(
                """async () => {
                    const original = apiRequest;
                    const delayedProjects = new Promise(resolve => {
                      window.__releaseDelayedProjects = resolve;
                    });
                    state.trial = null;
                    apiRequest = (path, options = {}) => {
                      if (path === '/api/trial') {
                        return Promise.resolve({
                          active: true,
                          granted_microusd: 5000000,
                          spent_microusd: 2000,
                          reserved_microusd: 0,
                          available_microusd: 4998000,
                        });
                      }
                      if (path === '/api/projects') return delayedProjects;
                      return original(path, options);
                    };
                    window.__partialRefreshPromise = refreshAuthenticatedWorkspace({quiet: true});
                    await Promise.resolve();
                    await Promise.resolve();
                }"""
            )

            assert page.evaluate("state.trial?.available_microusd") == 4_998_000
            page.evaluate("window.__releaseDelayedProjects({projects: []})")
            page.evaluate("window.__partialRefreshPromise")
        finally:
            browser.close()


def test_logout_discards_an_in_flight_private_workspace_refresh(
    live_browser_server,
):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page()
        try:
            _goto_ready_demo(page, live_browser_server)
            page.locator("#workspace-btn").click()
            page.locator("#dev-login-email").fill("stale-refresh@example.edu")
            page.locator("#dev-login-form button[type=submit]").click()
            expect(page.locator("#account-signed-in")).to_be_visible()

            page.evaluate(
                """() => {
                    const original = apiRequest;
                    window.__resolveStaleProjects = null;
                    window.__staleProjectsStarted = false;
                    apiRequest = (path, options = {}) => {
                      if (path === '/api/projects' && !window.__staleProjectsStarted) {
                        window.__staleProjectsStarted = true;
                        return new Promise(resolve => {
                          window.__resolveStaleProjects = resolve;
                        });
                      }
                      return original(path, options);
                    };
                    window.__staleWorkspaceRefresh = refreshAuthenticatedWorkspace({quiet: true});
                }"""
            )
            page.wait_for_function("window.__resolveStaleProjects !== null")
            # Match submission ordering: restore signed-in history, then append
            # private content to the active conversation's shared message array.
            page.evaluate("conversationStore.ready")
            page.evaluate(
                """() => {
                    state.projects = [{
                      id: 'stale-private-project',
                      name: 'Old account private project',
                      description: '',
                      source_scenario_id: 'popov_v_hayashi',
                      version: 1,
                      created_at: '2026-01-01T00:00:00Z',
                      updated_at: '2026-01-01T00:00:00Z',
                    }];
                    state.chatMessages.push({
                      role: 'user',
                      content: 'Old account private chat',
                    });
                    saveConversationDraft();
                    renderProjectsUI();
                    renderChat();
                }"""
            )
            expect(page.get_by_text("Old account private project")).to_be_attached()
            expect(page.get_by_text("Old account private chat")).to_be_attached()

            with page.expect_navigation(wait_until="domcontentloaded"):
                page.locator("#logout-btn").click()
            _wait_for_demo_ready(page)

            assert page.evaluate("state.authSession.authenticated") is False
            assert page.evaluate("state.projects.length") == 0
            assert page.evaluate("state.chatMessages.length") == 0
            assert page.evaluate("typeof window.__resolveStaleProjects") == "undefined"
            assert "Old account private project" not in page.locator("body").inner_text()
            assert "Old account private chat" not in page.locator("body").inner_text()
        finally:
            browser.close()


def test_switching_scenarios_preserves_an_in_flight_answer_in_its_conversation(
    live_browser_server,
):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page()
        try:
            _goto_ready_demo(page, live_browser_server)
            page.locator("#workspace-btn").click()
            page.locator("#dev-login-email").fill("stale-chat@example.edu")
            page.locator("#dev-login-form button[type=submit]").click()
            expect(page.locator("#account-signed-in")).to_be_visible()
            page.locator("#trial-activate-btn").click()
            expect(page.locator("#trial-balance-label")).to_contain_text("$5.00")
            page.keyboard.press("Escape")

            page.evaluate(
                """() => {
                    window.__resolveStaleChat = null;
                    apiPostChat = () => new Promise(resolve => {
                      window.__resolveStaleChat = resolve;
                    });
                    window.__staleChatRequest = sendChatMessage(
                      'Question that belongs only to the old scenario',
                    );
                }"""
            )
            page.wait_for_function("() => window.__resolveStaleChat !== null")
            expect(page.locator("#chat-messages").get_by_text(
                "Question that belongs only to the old scenario", exact=True,
            )).to_be_attached()

            page.locator("#scenario-select").select_option("fire_prevention")
            expect(page.locator("#scenario-name")).to_have_text("Prescribed Burn")

            page.evaluate(
                """async () => {
                    window.__resolveStaleChat({
                      billing_source: 'cloudbank',
                      cost_microusd: 1,
                      message: 'Private answer from the old scenario',
                      model: 'test-model',
                      latency_ms: 1,
                    });
                    await window.__staleChatRequest;
                }"""
            )

            expect(page.locator("#scenario-name")).to_have_text("Prescribed Burn")
            assert page.evaluate("state.chatMessages.length") == 0
            assert page.evaluate("state.chatPending") is False
            assert "Private answer from the old scenario" not in page.locator("#chat-messages").inner_text()
            saved = page.evaluate("conversationStore.records.find(record => record.messages.some(message => message.content === 'Private answer from the old scenario'))")
            assert saved["messages"][-1]["earlier_state"] is True
            page.locator("#conversation-select").select_option(saved["id"])
            expect(page.locator("#chat-messages")).to_contain_text("Private answer from the old scenario")
            expect(page.locator("#chat-messages")).to_contain_text("earlier scenario saved with this question")
        finally:
            browser.close()


def test_editing_the_current_scenario_labels_an_in_flight_answer_as_earlier_state(
    live_browser_server,
):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page()
        try:
            _goto_ready_demo(page, live_browser_server)
            page.locator("#workspace-btn").click()
            page.locator("#dev-login-email").fill("edited-chat-context@example.edu")
            page.locator("#dev-login-form button[type=submit]").click()
            expect(page.locator("#account-signed-in")).to_be_visible()
            page.locator("#trial-activate-btn").click()
            expect(page.locator("#trial-balance-label")).to_contain_text("$5.00")
            page.keyboard.press("Escape")

            page.evaluate(
                """() => {
                    window.__resolveEditedContextChat = null;
                    apiPostChat = () => new Promise(resolve => {
                      window.__resolveEditedContextChat = resolve;
                    });
                    window.__editedContextChatRequest = sendChatMessage(
                      'Question about the state before an edit',
                    );
                }"""
            )
            page.wait_for_function("() => window.__resolveEditedContextChat !== null")

            page.evaluate(
                """async () => {
                    const assumptionId = Object.keys(state.bundle.scenario.assumptions)[0];
                    if (!assumptionId) throw new Error('test scenario needs an assumption');
                    await applyOps([{op: 'toggle-assumption', id: assumptionId}]);
                }"""
            )
            assert page.evaluate("state.diff_ops.length") == 1

            page.evaluate(
                """async () => {
                    window.__resolveEditedContextChat({
                      billing_source: 'cloudbank',
                      cost_microusd: 1,
                      message: 'Answer computed from the state before the edit',
                      model: 'test-model',
                      latency_ms: 1,
                    });
                    await window.__editedContextChatRequest;
                }"""
            )

            expect(page.locator("#chat-messages")).to_contain_text(
                "Answer computed from the state before the edit"
            )
            expect(page.locator("#chat-messages")).to_contain_text(
                "earlier scenario saved with this question"
            )
            assert page.evaluate("state.chatPending") is False
        finally:
            browser.close()


def test_reopening_the_editor_discards_an_older_proposal_response(
    live_browser_server,
):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page()
        try:
            _goto_ready_demo(page, live_browser_server)
            page.locator("#workspace-btn").click()
            page.locator("#dev-login-email").fill("stale-proposal@example.edu")
            page.locator("#dev-login-form button[type=submit]").click()
            expect(page.locator("#account-signed-in")).to_be_visible()
            page.locator("#trial-activate-btn").click()
            expect(page.locator("#trial-balance-label")).to_contain_text("$5.00")
            page.keyboard.press("Escape")

            page.evaluate(
                """() => {
                    const original = window.fetch.bind(window);
                    window.__resolveStaleProposal = null;
                    window.fetch = (path, options = {}) => {
                      if (path === '/propose') {
                        return new Promise(resolve => {
                          window.__resolveStaleProposal = () => resolve({
                            ok: true,
                            status: 200,
                            json: async () => ({
                              op: {
                                op: 'add-fact',
                                id: 'old_private_fact',
                                fact: {description: 'Old private proposal'},
                              },
                              latency_ms: 1,
                              proposer_attempts: 1,
                              review_issues: [],
                            }),
                          });
                        });
                      }
                      return original(path, options);
                    };
                }"""
            )
            page.locator('[data-edit-task="add-fact"]').first.click()
            page.locator("#edit-instruction").fill("Create an old proposal")
            page.locator('[data-edit-action="propose"]').click()
            page.wait_for_function("() => window.__resolveStaleProposal !== null")

            page.keyboard.press("Escape")
            page.locator('[data-edit-task="add-assumption"]').first.click()
            expect(page.locator("#edit-modal-title")).to_have_text("Add Assumption")
            page.evaluate(
                """async () => {
                    window.__resolveStaleProposal();
                    await new Promise(resolve => window.setTimeout(resolve, 0));
                }"""
            )

            assert page.evaluate("editState.task") == "add-assumption"
            assert page.evaluate("editState.lastProposal") is None
            expect(page.locator("#edit-preview")).to_have_text("")
            expect(page.locator('[data-edit-action="propose"]')).to_be_visible()
            assert "Old private proposal" not in page.locator("body").inner_text()
        finally:
            browser.close()


def test_editing_the_scenario_discards_an_in_flight_proposal_response(
    live_browser_server,
):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page()
        try:
            _goto_ready_demo(page, live_browser_server)
            page.locator("#workspace-btn").click()
            page.locator("#dev-login-email").fill("edited-proposal-context@example.edu")
            page.locator("#dev-login-form button[type=submit]").click()
            expect(page.locator("#account-signed-in")).to_be_visible()
            page.locator("#trial-activate-btn").click()
            expect(page.locator("#trial-balance-label")).to_contain_text("$5.00")
            page.keyboard.press("Escape")

            page.evaluate(
                """() => {
                    const original = window.fetch.bind(window);
                    window.__resolveEditedContextProposal = null;
                    window.fetch = (path, options = {}) => {
                      if (path === '/propose') {
                        return new Promise(resolve => {
                          window.__resolveEditedContextProposal = () => resolve({
                            ok: true,
                            status: 200,
                            json: async () => ({
                              op: {
                                op: 'add-fact',
                                id: 'old_context_fact',
                                fact: {description: 'Proposal from the old state'},
                              },
                              billing_source: 'cloudbank',
                              latency_ms: 1,
                              proposer_attempts: 1,
                              review_issues: [],
                            }),
                          });
                        });
                      }
                      return original(path, options);
                    };
                }"""
            )
            page.locator('[data-edit-task="add-fact"]').first.click()
            page.locator("#edit-instruction").fill("Create a proposal")
            page.locator('[data-edit-action="propose"]').click()
            page.wait_for_function("() => window.__resolveEditedContextProposal !== null")

            page.evaluate(
                """async () => {
                    const assumptionId = Object.keys(state.bundle.scenario.assumptions)[0];
                    if (!assumptionId) throw new Error('test scenario needs an assumption');
                    await applyOps([{op: 'toggle-assumption', id: assumptionId}]);
                    window.__resolveEditedContextProposal();
                    await new Promise(resolve => window.setTimeout(resolve, 0));
                }"""
            )

            assert page.evaluate("editState.lastProposal") is None
            expect(page.locator("#edit-preview")).to_have_text("")
            expect(page.locator("#edit-status")).to_contain_text(
                "The scenario changed before this proposal arrived"
            )
            assert "Proposal from the old state" not in page.locator("body").inner_text()
        finally:
            browser.close()


def test_slower_project_open_cannot_replace_the_latest_selection(
    live_browser_server,
):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page()
        try:
            _goto_ready_demo(page, live_browser_server)
            page.evaluate(
                """() => {
                    const original = window.fetch.bind(window);
                    const makeProject = (id, name) => {
                      const scenario = structuredClone(state.bundle.scenario);
                      scenario.title = name;
                      return {
                        id,
                        name,
                        description: '',
                        source_scenario_id: state.scenario_id,
                        scenario,
                        af: structuredClone(state.bundle.af),
                        version: 1,
                        created_at: new Date().toISOString(),
                        updated_at: new Date().toISOString(),
                      };
                    };
                    window.__resolveSlowProject = null;
                    window.fetch = (path, options = {}) => {
                      if (path === '/api/projects/slow-project') {
                        return new Promise(resolve => {
                          window.__resolveSlowProject = () => resolve(new Response(
                            JSON.stringify(makeProject('slow-project', 'Slow project')),
                            {status: 200, headers: {'Content-Type': 'application/json'}},
                          ));
                        });
                      }
                      if (path === '/api/projects/latest-project') {
                        return Promise.resolve(new Response(
                          JSON.stringify(makeProject('latest-project', 'Latest project')),
                          {status: 200, headers: {'Content-Type': 'application/json'}},
                        ));
                      }
                      return original(path, options);
                    };
                    window.__slowProjectOpen = loadProject('slow-project');
                }"""
            )
            page.wait_for_function("() => window.__resolveSlowProject !== null")

            page.evaluate(
                """async () => {
                    await loadProject('latest-project');
                }"""
            )
            expect(page.locator("#context-indicator")).to_have_text("Private project")
            expect(page.locator("#scenario-name")).to_have_text("Latest project")

            page.evaluate(
                """async () => {
                    window.__resolveSlowProject();
                    await window.__slowProjectOpen;
                }"""
            )

            assert page.evaluate("state.activeProject.id") == "latest-project"
            expect(page.locator("#scenario-name")).to_have_text("Latest project")
        finally:
            browser.close()


def test_project_change_discards_an_in_flight_share_secret(live_browser_server):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page()
        try:
            _goto_ready_demo(page, live_browser_server)
            page.locator("#workspace-btn").click()
            page.locator("#dev-login-email").fill("stale-share@example.edu")
            page.locator("#dev-login-form button[type=submit]").click()
            expect(page.locator("#account-signed-in")).to_be_visible()
            page.locator("#workspace-tab-projects").click()

            page.evaluate(
                """() => {
                    const original = window.fetch.bind(window);
                    const makeProject = (id, name) => ({
                      id,
                      name,
                      description: '',
                      source_scenario_id: state.scenario_id,
                      scenario: structuredClone(state.bundle.scenario),
                      af: structuredClone(state.bundle.af),
                      version: 1,
                      created_at: new Date().toISOString(),
                      updated_at: new Date().toISOString(),
                    });
                    window.__shareProjectA = makeProject('project-a', 'Project A');
                    window.__shareProjectB = makeProject('project-b', 'Project B');
                    setViewContext('project', window.__shareProjectA);
                    state.diff_ops = [];
                    renderProjectsUI();
                    window.__resolveOldShare = null;
                    window.fetch = (path, options = {}) => {
                      if (
                        path === '/api/projects/project-a/shares'
                        && options.method === 'POST'
                      ) {
                        return new Promise(resolve => {
                          window.__resolveOldShare = () => resolve(new Response(
                            JSON.stringify({
                              id: 'old-share',
                              url: `${window.location.origin}/#share=private-old-secret`,
                            }),
                            {status: 200, headers: {'Content-Type': 'application/json'}},
                          ));
                        });
                      }
                      if (path === '/api/projects/project-b/shares') {
                        return Promise.resolve(new Response(
                          JSON.stringify({share_links: []}),
                          {status: 200, headers: {'Content-Type': 'application/json'}},
                        ));
                      }
                      return original(path, options);
                    };
                    window.__oldShareRequest = createProjectShare();
                }"""
            )
            page.wait_for_function("() => window.__resolveOldShare !== null")
            page.evaluate(
                """() => {
                    setViewContext('project', window.__shareProjectB);
                    renderProjectsUI();
                    window.__resolveOldShare();
                }"""
            )
            page.evaluate("() => window.__oldShareRequest")

            assert page.evaluate("state.activeProject.id") == "project-b"
            assert page.evaluate("state.latestShare") is None
            assert "private-old-secret" not in page.locator("body").inner_text()
        finally:
            browser.close()


def test_slower_share_refresh_cannot_restore_a_revoked_link(live_browser_server):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page()
        try:
            _goto_ready_demo(page, live_browser_server)
            page.locator("#workspace-btn").click()
            page.locator("#dev-login-email").fill("stale-share-list@example.edu")
            page.locator("#dev-login-form button[type=submit]").click()
            expect(page.locator("#account-signed-in")).to_be_visible()
            page.locator("#workspace-tab-projects").click()

            page.evaluate(
                """() => {
                    const original = window.fetch.bind(window);
                    const project = {
                      id: 'share-list-project',
                      name: 'Share list project',
                      description: '',
                      source_scenario_id: state.scenario_id,
                      scenario: structuredClone(state.bundle.scenario),
                      af: structuredClone(state.bundle.af),
                      version: 1,
                      created_at: new Date().toISOString(),
                      updated_at: new Date().toISOString(),
                    };
                    setViewContext('project', project);
                    state.diff_ops = [];
                    setBundle({scenario: project.scenario, af: project.af});
                    renderProjectsUI();
                    let shareListRequest = 0;
                    window.__resolveOldShareList = null;
                    window.fetch = (path, options = {}) => {
                      if (
                        path === '/api/projects/share-list-project/shares'
                        && !options.method
                      ) {
                        shareListRequest += 1;
                        if (shareListRequest === 1) {
                          return new Promise(resolve => {
                            window.__resolveOldShareList = () => resolve(new Response(
                              JSON.stringify({share_links: [{
                                id: 'already-revoked-share',
                                created_at: new Date().toISOString(),
                                expires_at: null,
                                revoked_at: null,
                                active: true,
                              }]}),
                              {status: 200, headers: {'Content-Type': 'application/json'}},
                            ));
                          });
                        }
                        return Promise.resolve(new Response(
                          JSON.stringify({share_links: []}),
                          {status: 200, headers: {'Content-Type': 'application/json'}},
                        ));
                      }
                      return original(path, options);
                    };
                    window.__oldShareListRequest = refreshProjectShares();
                }"""
            )
            page.wait_for_function("() => window.__resolveOldShareList !== null")
            page.evaluate("() => refreshProjectShares()")
            expect(page.locator("#current-project-card")).not_to_contain_text("Revoke")

            page.evaluate(
                """async () => {
                    window.__resolveOldShareList();
                    await window.__oldShareListRequest;
                }"""
            )

            expect(page.locator("#current-project-card")).not_to_contain_text("Revoke")
        finally:
            browser.close()


def test_project_change_cannot_be_replaced_by_an_older_save_response(
    live_browser_server,
):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page()
        try:
            _goto_ready_demo(page, live_browser_server)
            page.locator("#workspace-btn").click()
            page.locator("#dev-login-email").fill("stale-save@example.edu")
            page.locator("#dev-login-form button[type=submit]").click()
            expect(page.locator("#account-signed-in")).to_be_visible()

            page.evaluate(
                """() => {
                    const original = window.fetch.bind(window);
                    const makeProject = (id, name) => {
                      const scenario = structuredClone(state.bundle.scenario);
                      scenario.title = name;
                      return {
                        id,
                        name,
                        description: '',
                        source_scenario_id: state.scenario_id,
                        scenario,
                        af: structuredClone(state.bundle.af),
                        version: 1,
                        created_at: new Date().toISOString(),
                        updated_at: new Date().toISOString(),
                      };
                    };
                    window.__saveProjectA = makeProject('save-a', 'Save A');
                    window.__saveProjectB = makeProject('save-b', 'Save B');
                    setViewContext('project', window.__saveProjectA);
                    state.diff_ops = [{op: 'test-only-change'}];
                    renderAll();
                    window.__resolveOldSave = null;
                    window.fetch = (path, options = {}) => {
                      if (path === '/api/projects/save-a' && options.method === 'PUT') {
                        return new Promise(resolve => {
                          const updated = structuredClone(window.__saveProjectA);
                          updated.version = 2;
                          window.__resolveOldSave = () => resolve(new Response(
                            JSON.stringify(updated),
                            {status: 200, headers: {'Content-Type': 'application/json'}},
                          ));
                        });
                      }
                      return original(path, options);
                    };
                    window.__oldSaveRequest = saveProjectChanges();
                }"""
            )
            page.wait_for_function("() => window.__resolveOldSave !== null")
            page.evaluate(
                """() => {
                    setViewContext('project', window.__saveProjectB);
                    state.diff_ops = [];
                    renderAll();
                    window.__resolveOldSave();
                }"""
            )
            page.evaluate("() => window.__oldSaveRequest")

            assert page.evaluate("state.activeProject.id") == "save-b"
            expect(page.locator("#scenario-name")).to_have_text("Save B")
        finally:
            browser.close()


def test_project_change_cannot_be_replaced_by_an_older_archive_response(
    live_browser_server,
):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page()
        try:
            _goto_ready_demo(page, live_browser_server)
            page.locator("#workspace-btn").click()
            page.locator("#dev-login-email").fill("stale-archive@example.edu")
            page.locator("#dev-login-form button[type=submit]").click()
            expect(page.locator("#account-signed-in")).to_be_visible()

            page.evaluate(
                """() => {
                    const original = window.fetch.bind(window);
                    const makeProject = (id, name) => {
                      const scenario = structuredClone(state.bundle.scenario);
                      scenario.title = name;
                      return {
                        id,
                        name,
                        description: '',
                        source_scenario_id: state.scenario_id,
                        scenario,
                        af: structuredClone(state.bundle.af),
                        version: 1,
                        created_at: new Date().toISOString(),
                        updated_at: new Date().toISOString(),
                      };
                    };
                    window.__archiveProjectA = makeProject('archive-a', 'Archive A');
                    window.__archiveProjectB = makeProject('archive-b', 'Archive B');
                    setViewContext('project', window.__archiveProjectA);
                    state.scenario_id = window.__archiveProjectA.source_scenario_id;
                    state.baseline = window.__archiveProjectA.scenario;
                    state.diff_ops = [];
                    setBundle({
                      scenario: window.__archiveProjectA.scenario,
                      af: window.__archiveProjectA.af,
                    });
                    renderAll();
                    window.confirm = () => true;
                    window.__resolveArchiveProjectList = null;
                    window.fetch = (path, options = {}) => {
                      if (
                        path.startsWith('/api/projects/archive-a?')
                        && options.method === 'DELETE'
                      ) {
                        return Promise.resolve(new Response(null, {status: 204}));
                      }
                      if (path === '/api/projects' && !options.method) {
                        return new Promise(resolve => {
                          window.__resolveArchiveProjectList = () => resolve(new Response(
                            JSON.stringify({projects: [window.__archiveProjectB]}),
                            {status: 200, headers: {'Content-Type': 'application/json'}},
                          ));
                        });
                      }
                      return original(path, options);
                    };
                    window.__oldArchiveRequest = archiveProject(
                      'archive-a',
                      'Archive A',
                      1,
                    );
                }"""
            )
            page.wait_for_function("() => window.__resolveArchiveProjectList !== null")
            page.evaluate(
                """() => {
                    setViewContext('project', window.__archiveProjectB);
                    state.scenario_id = window.__archiveProjectB.source_scenario_id;
                    state.baseline = window.__archiveProjectB.scenario;
                    state.diff_ops = [];
                    setBundle({
                      scenario: window.__archiveProjectB.scenario,
                      af: window.__archiveProjectB.af,
                    });
                    renderAll();
                    window.__resolveArchiveProjectList();
                }"""
            )
            page.evaluate("() => window.__oldArchiveRequest")

            assert page.evaluate("state.activeProject.id") == "archive-b"
            expect(page.locator("#scenario-name")).to_have_text("Archive B")
        finally:
            browser.close()


def test_project_edit_is_blocked_while_its_save_is_in_flight(live_browser_server):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page()
        try:
            _goto_ready_demo(page, live_browser_server)
            page.locator("#workspace-btn").click()
            page.locator("#dev-login-email").fill("save-in-flight@example.edu")
            page.locator("#dev-login-form button[type=submit]").click()
            expect(page.locator("#account-signed-in")).to_be_visible()

            page.evaluate(
                """() => {
                    const original = window.fetch.bind(window);
                    const project = {
                      id: 'save-in-flight',
                      name: 'Save in flight',
                      description: '',
                      source_scenario_id: state.scenario_id,
                      scenario: structuredClone(state.bundle.scenario),
                      af: structuredClone(state.bundle.af),
                      version: 1,
                      created_at: new Date().toISOString(),
                      updated_at: new Date().toISOString(),
                    };
                    setViewContext('project', project);
                    state.diff_ops = [{op: 'existing-rendered-change'}];
                    setBundle({scenario: project.scenario, af: project.af});
                    renderAll();
                    window.__stateCallsDuringSave = 0;
                    window.__resolvePendingSave = null;
                    apiPostState = () => {
                      window.__stateCallsDuringSave += 1;
                      return Promise.resolve(structuredClone(state.bundle));
                    };
                    window.fetch = (path, options = {}) => {
                      if (path === '/api/projects/save-in-flight' && options.method === 'PUT') {
                        return new Promise(resolve => {
                          const updated = structuredClone(project);
                          updated.version = 2;
                          window.__resolvePendingSave = () => resolve(new Response(
                            JSON.stringify(updated),
                            {status: 200, headers: {'Content-Type': 'application/json'}},
                          ));
                        });
                      }
                      return original(path, options);
                    };
                    window.__pendingProjectSave = saveProjectChanges();
                }"""
            )
            page.wait_for_function("() => window.__resolvePendingSave !== null")

            page.evaluate("() => applyOps([{op: 'edit-during-save'}])")

            assert page.evaluate("window.__stateCallsDuringSave") == 0
            assert page.evaluate("state.diff_ops.length") == 1
            expect(page.locator("#global-status")).to_contain_text(
                "Wait for the current project save"
            )

            page.evaluate(
                """async () => {
                    window.__resolvePendingSave();
                    await window.__pendingProjectSave;
                }"""
            )
            assert page.evaluate("state.activeProject.version") == 2
            assert page.evaluate("state.diff_ops.length") == 0
        finally:
            browser.close()


def test_project_save_waits_for_an_in_flight_state_computation(live_browser_server):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page()
        try:
            _goto_ready_demo(page, live_browser_server)
            page.locator("#workspace-btn").click()
            page.locator("#dev-login-email").fill("compute-before-save@example.edu")
            page.locator("#dev-login-form button[type=submit]").click()
            expect(page.locator("#account-signed-in")).to_be_visible()
            # Finish the asynchronous login refresh before installing the
            # computation fixture and asserting a later global status message.
            expect(page.locator("#global-status")).to_contain_text(
                "Signed in to the local development workspace."
            )

            page.evaluate(
                """() => {
                    const original = window.fetch.bind(window);
                    const project = {
                      id: 'compute-before-save',
                      name: 'Compute before save',
                      description: '',
                      source_scenario_id: state.scenario_id,
                      scenario: structuredClone(state.bundle.scenario),
                      af: structuredClone(state.bundle.af),
                      version: 1,
                      created_at: new Date().toISOString(),
                      updated_at: new Date().toISOString(),
                    };
                    setViewContext('project', project);
                    state.diff_ops = [{op: 'existing-rendered-change'}];
                    setBundle({scenario: project.scenario, af: project.af});
                    renderAll();
                    window.__projectSaveCalls = 0;
                    window.__resolvePendingComputation = null;
                    apiPostState = () => new Promise(resolve => {
                      window.__resolvePendingComputation = () => resolve(
                        structuredClone(state.bundle),
                      );
                    });
                    window.fetch = (path, options = {}) => {
                      if (path === '/api/projects/compute-before-save' && options.method === 'PUT') {
                        window.__projectSaveCalls += 1;
                      }
                      return original(path, options);
                    };
                    window.__pendingComputation = applyOps([
                      {op: 'new-computation-before-save'},
                    ]);
                }"""
            )
            page.wait_for_function("() => window.__resolvePendingComputation !== null")

            page.evaluate("() => saveProjectChanges()")

            assert page.evaluate("window.__projectSaveCalls") == 0
            expect(page.locator("#global-status")).to_contain_text(
                "Wait for the current change"
            )

            page.evaluate(
                """async () => {
                    window.__resolvePendingComputation();
                    await window.__pendingComputation;
                }"""
            )
            assert page.evaluate("hasPendingStateRequest()") is False
        finally:
            browser.close()


def test_view_change_cannot_be_replaced_by_an_older_project_create_response(
    live_browser_server,
):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page()
        try:
            _goto_ready_demo(page, live_browser_server)
            page.locator("#workspace-btn").click()
            page.locator("#dev-login-email").fill("stale-create@example.edu")
            page.locator("#dev-login-form button[type=submit]").click()
            expect(page.locator("#account-signed-in")).to_be_visible()
            page.locator("#workspace-tab-projects").click()

            page.evaluate(
                """() => {
                    const original = window.fetch.bind(window);
                    window.__resolveOldCreate = null;
                    window.fetch = (path, options = {}) => {
                      if (path === '/api/projects' && options.method === 'POST') {
                        return new Promise(resolve => {
                          const scenario = structuredClone(state.bundle.scenario);
                          scenario.title = 'Older created project';
                          window.__resolveOldCreate = () => resolve(new Response(
                            JSON.stringify({
                              id: 'older-created-project',
                              name: 'Older created project',
                              description: '',
                              source_scenario_id: state.scenario_id,
                              scenario,
                              af: structuredClone(state.bundle.af),
                              version: 1,
                              created_at: new Date().toISOString(),
                              updated_at: new Date().toISOString(),
                            }),
                            {status: 200, headers: {'Content-Type': 'application/json'}},
                          ));
                        });
                      }
                      return original(path, options);
                    };
                }"""
            )
            page.locator("#project-name-input").fill("Older created project")
            page.locator("#project-create-btn").click()
            page.wait_for_function("() => window.__resolveOldCreate !== null")

            page.evaluate(
                """() => {
                    const scenario = structuredClone(state.bundle.scenario);
                    scenario.title = 'New current view';
                    setViewContext('example');
                    state.scenario_id = 'new-current-view';
                    state.baseline = scenario;
                    state.bundle = {scenario, af: structuredClone(state.bundle.af)};
                    state.diff_ops = [];
                    renderAll();
                    window.__resolveOldCreate();
                }"""
            )
            page.wait_for_function(
                "() => !document.querySelector('#project-create-btn').disabled"
            )

            assert page.evaluate("state.viewKind") == "example"
            assert page.evaluate("state.activeProject") is None
            assert page.evaluate("state.scenario_id") == "new-current-view"
            expect(page.locator("#scenario-name")).to_have_text("New current view")
        finally:
            browser.close()


def test_closing_workspace_discards_a_late_mcp_token(live_browser_server):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page()
        try:
            _goto_ready_demo(page, live_browser_server)
            page.locator("#workspace-btn").click()
            page.locator("#dev-login-email").fill("late-token@example.edu")
            page.locator("#dev-login-form button[type=submit]").click()
            expect(page.locator("#account-signed-in")).to_be_visible()
            page.locator("#workspace-tab-mcp").click()

            page.evaluate(
                """() => {
                    const original = window.fetch.bind(window);
                    window.__resolveLateToken = null;
                    window.fetch = (path, options = {}) => {
                      if (path === '/api/mcp/tokens' && options.method === 'POST') {
                        return new Promise(resolve => {
                          window.__resolveLateToken = () => resolve(new Response(
                            JSON.stringify({
                              id: 'late-token',
                              token: 'abda_mcp_private_late_secret',
                              codex_config: 'private late Codex config',
                              claude_command: 'private late Claude command',
                            }),
                            {status: 200, headers: {'Content-Type': 'application/json'}},
                          ));
                        });
                      }
                      return original(path, options);
                    };
                }"""
            )
            page.locator("#mcp-token-name").fill("Late token")
            page.locator("#mcp-token-form button[type=submit]").click()
            page.wait_for_function("() => window.__resolveLateToken !== null")
            page.keyboard.press("Escape")
            expect(page.locator("#modal-workspace .modal-content")).to_be_hidden()

            page.evaluate("() => window.__resolveLateToken()")
            page.wait_for_function(
                "() => !document.querySelector('#mcp-token-form button[type=submit]').disabled"
            )
            page.locator("#workspace-btn").click()
            page.locator("#workspace-tab-mcp").click()

            expect(page.locator("#mcp-secret-panel")).to_be_hidden()
            expect(page.locator("#mcp-secret-value")).to_have_value("")
            expect(page.locator("#mcp-codex-config")).to_have_text("")
            expect(page.locator("#mcp-claude-command")).to_have_text("")
            assert "private_late_secret" not in page.locator("body").inner_text()
        finally:
            browser.close()


def test_slower_mcp_refresh_cannot_restore_a_revoked_credential(
    live_browser_server,
):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page()
        try:
            _goto_ready_demo(page, live_browser_server)
            page.locator("#workspace-btn").click()
            page.locator("#dev-login-email").fill("stale-token-list@example.edu")
            page.locator("#dev-login-form button[type=submit]").click()
            expect(page.locator("#account-signed-in")).to_be_visible()
            page.locator("#workspace-tab-mcp").click()

            page.evaluate(
                """() => {
                    const original = window.fetch.bind(window);
                    let tokenListRequest = 0;
                    window.__resolveOldTokenList = null;
                    window.fetch = (path, options = {}) => {
                      if (path === '/api/mcp/tokens' && !options.method) {
                        tokenListRequest += 1;
                        if (tokenListRequest === 1) {
                          return new Promise(resolve => {
                            window.__resolveOldTokenList = () => resolve(new Response(
                              JSON.stringify({tokens: [{
                                id: 'revoked-token',
                                name: 'Already revoked',
                                token_prefix: 'abda_mcp_old',
                                scopes: ['projects:read'],
                                expires_at: new Date(Date.now() + 86400000).toISOString(),
                                last_used_at: null,
                                active: true,
                              }]}),
                              {status: 200, headers: {'Content-Type': 'application/json'}},
                            ));
                          });
                        }
                        return Promise.resolve(new Response(
                          JSON.stringify({tokens: []}),
                          {status: 200, headers: {'Content-Type': 'application/json'}},
                        ));
                      }
                      return original(path, options);
                    };
                    window.__oldTokenListRequest = refreshMCPTokens();
                }"""
            )
            page.wait_for_function("() => window.__resolveOldTokenList !== null")
            page.evaluate("() => refreshMCPTokens()")
            expect(page.locator("#mcp-token-list")).to_contain_text(
                "No agent credentials yet."
            )

            page.evaluate(
                """async () => {
                    window.__resolveOldTokenList();
                    await window.__oldTokenListRequest;
                }"""
            )

            expect(page.locator("#mcp-token-list")).to_contain_text(
                "No agent credentials yet."
            )
            assert page.locator('[data-mcp-action="revoke"]').count() == 0
        finally:
            browser.close()


def test_trial_activation_wins_over_an_older_workspace_refresh(
    live_browser_server,
):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page()
        try:
            _goto_ready_demo(page, live_browser_server)
            page.locator("#workspace-btn").click()
            page.evaluate(
                """() => {
                    const original = window.fetch.bind(window);
                    window.__resolveOldTrial = null;
                    window.fetch = (path, options = {}) => {
                      if (
                        path === '/api/trial'
                        && !options.method
                        && window.__resolveOldTrial === null
                      ) {
                        return new Promise(resolve => {
                          window.__resolveOldTrial = () => resolve(new Response(
                            JSON.stringify({
                              enabled: true,
                              active: false,
                              granted_microusd: 0,
                              spent_microusd: 0,
                              reserved_microusd: 0,
                              available_microusd: 0,
                            }),
                            {status: 200, headers: {'Content-Type': 'application/json'}},
                          ));
                        });
                      }
                      if (path === '/api/trial/activate' && options.method === 'POST') {
                        return Promise.resolve(new Response(
                          JSON.stringify({
                            enabled: true,
                            active: true,
                            granted_microusd: 5000000,
                            spent_microusd: 0,
                            reserved_microusd: 0,
                            available_microusd: 5000000,
                          }),
                          {status: 200, headers: {'Content-Type': 'application/json'}},
                        ));
                      }
                      return original(path, options);
                    };
                }"""
            )
            page.locator("#dev-login-email").fill("trial-race@example.edu")
            page.locator("#dev-login-form button[type=submit]").click()
            expect(page.locator("#account-signed-in")).to_be_visible()
            page.wait_for_function("() => window.__resolveOldTrial !== null")

            page.locator("#trial-activate-btn").click()
            expect(page.locator("#trial-balance-label")).to_contain_text("$5.00")
            page.evaluate("() => window.__resolveOldTrial()")
            page.wait_for_timeout(0)

            assert page.evaluate("state.trial.active") is True
            expect(page.locator("#trial-balance-label")).to_contain_text("$5.00")
            expect(page.locator("#trial-balance")).to_be_visible()
        finally:
            browser.close()


def test_failed_rapid_edit_restores_the_last_rendered_operation_set(
    live_browser_server,
):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page()
        try:
            _goto_ready_demo(page, live_browser_server)
            page.evaluate(
                """() => {
                    const renderedBundle = state.bundle;
                    let callCount = 0;
                    window.__resolveFirstEdit = null;
                    window.__renderedBundle = renderedBundle;
                    apiPostState = () => {
                      callCount += 1;
                      if (callCount === 1) {
                        return new Promise(resolve => {
                          window.__resolveFirstEdit = () => resolve(renderedBundle);
                        });
                      }
                      return Promise.reject(new Error('newer computation failed'));
                    };
                    window.__firstEdit = applyOps([{op: 'first-pending-edit'}]);
                }"""
            )
            page.wait_for_function("() => window.__resolveFirstEdit !== null")
            page.evaluate(
                """async () => {
                    await applyOps([{op: 'second-failing-edit'}]);
                    window.__resolveFirstEdit();
                    await window.__firstEdit;
                }"""
            )

            assert page.evaluate("state.bundle === window.__renderedBundle") is True
            assert page.evaluate("state.diff_ops.length") == 0
        finally:
            browser.close()


def test_failed_example_load_keeps_the_existing_private_project(
    live_browser_server,
):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page()
        try:
            _goto_ready_demo(page, live_browser_server)
            page.evaluate(
                """() => {
                    const scenario = structuredClone(state.bundle.scenario);
                    scenario.title = 'Private project before failure';
                    window.__projectBeforeFailedLoad = {
                      id: 'project-before-failure',
                      name: 'Project before failure',
                      description: '',
                      source_scenario_id: state.scenario_id,
                      scenario,
                      af: structuredClone(state.bundle.af),
                      version: 1,
                      created_at: new Date().toISOString(),
                      updated_at: new Date().toISOString(),
                    };
                    setViewContext('project', window.__projectBeforeFailedLoad);
                    state.baseline = scenario;
                    state.diff_ops = [];
                    setBundle({scenario, af: structuredClone(state.bundle.af)});
                    renderAll();
                    apiPostState = () => Promise.reject(
                      new Error('example computation failed'),
                    );
                }"""
            )

            page.evaluate("() => loadScenario('fire_prevention')")

            assert page.evaluate("state.viewKind") == "project"
            assert page.evaluate("state.activeProject.id") == "project-before-failure"
            expect(page.locator("#context-indicator")).to_have_text("Private project")
            expect(page.locator("#scenario-name")).to_have_text("Project before failure")
            expect(page.locator("#scenario-name")).to_have_attribute(
                "title", "Scenario: Private project before failure"
            )
        finally:
            browser.close()


def test_non_json_state_failure_reports_the_http_status(live_browser_server):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page()
        try:
            _goto_ready_demo(page, live_browser_server)
            result = page.evaluate(
                """async () => {
                    const original = window.fetch.bind(window);
                    window.fetch = (path, options = {}) => {
                      if (path === '/state' && options.method === 'POST') {
                        return Promise.resolve(new Response(
                          'upstream temporarily unavailable',
                          {status: 502, headers: {'Content-Type': 'text/plain'}},
                        ));
                      }
                      return original(path, options);
                    };
                    try {
                      await apiPostState(state.scenario_id, [], undefined, null);
                      return {message: 'request unexpectedly succeeded', status: null};
                    } catch (error) {
                      return {message: error.message, status: error.status ?? null};
                    }
                }"""
            )

            assert result == {"message": "POST /state: 502", "status": 502}
        finally:
            browser.close()


def test_research_workspace_in_browser(live_browser_server):
    from playwright.sync_api import expect, sync_playwright

    console_errors: list[str] = []
    page_errors: list[str] = []
    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            reduced_motion="reduce",
        )
        page = context.new_page()
        page.on(
            "console",
            lambda message: console_errors.append(message.text)
            if message.type == "error"
            else None,
        )
        page.on("pageerror", lambda error: page_errors.append(str(error)))

        try:
            _goto_ready_demo(page, live_browser_server)
            expect(page.locator("#scenario-name")).not_to_have_text("Loading...")
            assert page.locator("#scenario-select option").count() >= 6
            expect(page.locator("#conclusions-list .conclusion-card").first).to_be_visible()
            expect(page.locator("#facts-list .fact-card").first).to_be_visible()
            expect(page.locator("#kb-content .rule-card").first).to_be_visible()
            _axe_report(page, "initial explorer")

            conclusion_key = page.locator('.concl-filter[data-filter="key"]')
            conclusion_accepted = page.locator(
                '.concl-filter[data-filter="accepted"]'
            )
            expect(conclusion_key).to_have_attribute("aria-pressed", "true")
            conclusion_accepted.click()
            expect(conclusion_key).to_have_attribute("aria-pressed", "false")
            expect(conclusion_accepted).to_have_attribute("aria-pressed", "true")
            conclusion_key.click()

            facts_button = page.locator('.facts-filter[data-filter="facts"]')
            assumptions_button = page.locator(
                '.facts-filter[data-filter="assumptions"]'
            )
            assumptions_button.click()
            expect(facts_button).to_have_attribute("aria-pressed", "false")
            expect(assumptions_button).to_have_attribute("aria-pressed", "true")
            facts_button.click()

            all_rules_button = page.locator('.kb-tab[data-tab="all"]')
            conflicts_button = page.locator('.kb-tab[data-tab="conflicts"]')
            conflicts_button.click()
            expect(all_rules_button).to_have_attribute("aria-pressed", "false")
            expect(conflicts_button).to_have_attribute("aria-pressed", "true")
            all_rules_button.click()
            expect(page.get_by_label("Search rules", exact=True)).to_be_visible()

            explorer_separator = page.get_by_role(
                "separator", name="Resize explorer and chat panels"
            )
            before_resize = int(explorer_separator.get_attribute("aria-valuenow"))
            explorer_separator.focus()
            explorer_separator.press("ArrowLeft")
            expect(explorer_separator).to_have_attribute(
                "aria-valuenow", str(before_resize - 5)
            )
            explorer_separator.press("ArrowRight")
            expect(explorer_separator).to_have_attribute(
                "aria-valuenow", str(before_resize)
            )
            for label, grow_key, shrink_key in (
                ("Resize conclusions and facts panels", "ArrowRight", "ArrowLeft"),
                ("Resize evidence and rules panels", "ArrowDown", "ArrowUp"),
                (
                    "Resize chat history and message composer",
                    "ArrowUp",
                    "ArrowDown",
                ),
            ):
                handle = page.get_by_role("separator", name=label)
                expect(handle).to_have_attribute("tabindex", "0")
                expect(handle).to_have_attribute("aria-valuenow", re.compile(r"^\d+$"))
                before = int(handle.get_attribute("aria-valuenow"))
                handle.focus()
                handle.press(grow_key)
                expect(handle).to_have_attribute("aria-valuenow", str(before + 5))
                handle.press(shrink_key)
                expect(handle).to_have_attribute("aria-valuenow", str(before))

            explain_button = page.locator(
                ".conclusion-card:has(.status-accepted) button[data-explain-id]"
            ).first
            expect(explain_button).to_be_visible()
            explain_button.focus()
            explain_button.press("Enter")
            game_dialog = page.locator("#modal-game .modal-content")
            expect(game_dialog).to_be_visible()
            _axe_report(page, "argument explanation picker")
            picker_card = page.locator("#modal-game .game-picker-card").first
            expect(picker_card).to_be_visible()
            expect(picker_card).to_have_attribute("type", "button")
            picker_card.focus()
            picker_card.press("Enter")
            expect(page.locator("#modal-game .game-tree")).to_be_visible()
            _axe_report(page, "argument explanation tree")
            supports_toggle = page.locator("#modal-game .game-supports-toggle").first
            if supports_toggle.count():
                expect(supports_toggle).to_have_attribute("aria-expanded", "false")
                supports_toggle.focus()
                supports_toggle.press("Enter")
                expect(supports_toggle).to_have_attribute("aria-expanded", "true")
            page.keyboard.press("Escape")
            expect(game_dialog).to_be_hidden()
            expect(explain_button).to_be_focused()

            workspace_button = page.locator("#workspace-btn")
            page.locator("#dev-login-form").evaluate("element => { element.hidden = true; }")
            page.locator("#oidc-login-link").evaluate("element => { element.hidden = false; }")
            workspace_button.focus()
            workspace_button.press("Enter")
            expect(page.get_by_role("dialog", name="Research workspace")).to_be_visible()
            expect(page.locator("#oidc-login-link")).to_be_focused()
            page.keyboard.press("Escape")
            expect(workspace_button).to_be_focused()
            page.locator("#oidc-login-link").evaluate("element => { element.hidden = true; }")
            page.locator("#dev-login-form").evaluate("element => { element.hidden = false; }")

            workspace_button.focus()
            workspace_button.press("Enter")
            dialog = page.get_by_role("dialog", name="Research workspace")
            expect(dialog).to_be_visible()
            expect(page.locator("#dev-login-email")).to_be_focused()
            _axe_report(page, "signed-out workspace")

            page.locator("#dev-login-email").fill("browser-acceptance@example.edu")
            page.locator("#dev-login-name").fill("Browser Acceptance")
            page.locator("#dev-login-form button[type=submit]").click()
            expect(page.locator("#account-signed-in")).to_be_visible()
            expect(page.locator("#account-email")).to_have_text(
                "browser-acceptance@example.edu"
            )
            page.locator("#trial-activate-btn").click()
            expect(page.locator("#trial-balance-label")).to_contain_text("$5.00")

            account_tab = page.locator("#workspace-tab-account")
            account_tab.focus()
            account_tab.press("ArrowRight")
            expect(page.locator("#workspace-tab-projects")).to_be_focused()
            expect(page.locator("#workspace-panel-projects")).to_be_visible()
            page.locator("#project-name-input").fill("Browser acceptance project")
            page.locator("#project-description-input").fill(
                "Created through the real browser workspace"
            )
            page.locator("#project-create-btn").click()
            expect(page.locator("#context-indicator")).to_have_text("Private project")
            expect(page.locator("#global-status")).to_contain_text(
                "Created private project"
            )

            page.locator("#workspace-btn").click()
            page.locator("#workspace-tab-projects").click()
            page.locator('[data-project-action="share-create"]').click()
            share_input = page.locator("#latest-share-url")
            expect(share_input).to_be_visible()
            share_url = share_input.input_value()
            assert "/#share=" in share_url

            shared_context = browser.new_context(viewport={"width": 1440, "height": 900})
            try:
                shared_page = shared_context.new_page()
                _goto_ready_demo(shared_page, share_url)
                expect(shared_page.locator("#context-indicator")).to_have_text(
                    "Shared read-only"
                )
                access_note = shared_page.locator("#chat-access-note")
                expect(access_note).to_have_text(
                    "Chat and edits are disabled in a shared read-only view."
                )
                assert access_note.locator("button").count() == 0
                shared_page.locator(".rule-info").first.click()
                expect(shared_page.locator("#chat-input")).to_have_value(re.compile('Can you explain'))
                expect(shared_page.locator("#chat-send-btn")).to_be_disabled()
                expect(shared_page.locator("#modal-workspace .modal-content")).to_be_hidden()
            finally:
                shared_context.close()
            page.keyboard.press("Escape")
            expect(dialog).to_be_hidden()
            assert page.locator("#latest-share-url").count() == 0

            ai_access_button = page.locator("#ai-access-btn")
            ai_access_button.click()
            expect(page.locator("#workspace-panel-ai")).to_be_visible()
            page.locator('input[name="ai-mode"][value="byok"]').check()
            page.locator("#byok-provider-select").select_option("openrouter")
            configuration = page.request.get(f"{live_browser_server}/config").json()
            provider = next(item for item in configuration["byok_providers"] if item["id"] == "openrouter")
            approved_models = [item["id"] for item in provider["models"]]
            assert approved_models
            model_select = page.locator("#byok-model-select")
            assert model_select.locator("option").evaluate_all(
                "options => options.map(option => option.value)",
            ) == approved_models
            model_select.select_option(approved_models[0])
            page.locator("#byok-api-key").fill("browser-only-placeholder-key")
            page.locator("#ai-access-form button[type=submit]").click()
            expect(page.locator("#ai-access-status")).to_contain_text(
                "applied to this browser tab"
            )
            assert page.evaluate("state.llmAccess.provider") == "openrouter"
            assert page.evaluate("state.llmAccess.model") == approved_models[0]
            expect(page.locator("#byok-api-key")).to_have_attribute("type", "password")
            _axe_report(page, "signed-in AI access workspace")

            page.locator("#workspace-tab-mcp").click()
            page.locator("#mcp-token-name").fill("Browser acceptance token")
            page.locator("#mcp-token-form button[type=submit]").click()
            expect(page.locator("#mcp-secret-panel")).to_be_visible()
            expect(page.locator("#mcp-secret-value")).to_have_value(
                re.compile(r"^abda_mcp_")
            )
            expect(page.locator("#mcp-codex-config")).to_contain_text(
                "ABDA_NL_MCP_TOKEN"
            )
            _axe_report(page, "one-time MCP credential workspace")

            page.keyboard.press("Escape")
            expect(dialog).to_be_hidden()
            expect(ai_access_button).to_be_focused()
            expect(page.locator("#mcp-secret-panel")).to_be_hidden()
            expect(page.locator("#mcp-secret-value")).to_have_value("")
            expect(page.locator("#mcp-codex-config")).to_have_text("")
            expect(page.locator("#mcp-claude-command")).to_have_text("")

            add_fact_button = page.locator('[data-edit-task="add-fact"]').first
            add_fact_button.focus()
            add_fact_button.press("Enter")
            edit_dialog = page.locator("#modal-edit .modal-content")
            expect(edit_dialog).to_be_visible()
            expect(page.locator("#edit-instruction")).to_be_focused()
            _axe_report(page, "natural language edit dialog")
            page.keyboard.press("Escape")
            expect(edit_dialog).to_be_hidden()
            expect(add_fact_button).to_be_focused()

            page.locator('.facts-filter[data-filter="assumptions"]').click()
            assumption = page.locator("#facts-list input[data-asm-id]").first
            assumption.focus()
            assumption.press("Space")
            impact_dialog = page.locator("#modal-suspend-impact .modal-content")
            expect(impact_dialog).to_be_visible()
            _axe_report(page, "suspension impact preview")
            page.locator("#suspend-impact-apply-btn").click()
            expect(page.locator("#modified-indicator")).to_be_visible()

            page.locator("#view-af-btn").focus()
            page.locator("#view-af-btn").press("Enter")
            expect(page.locator("#modal-af .modal-content")).to_be_visible()
            graph_scroll = page.locator("#af-svg-scroll")
            expect(graph_scroll.locator("svg")).to_be_visible()
            expect(graph_scroll).to_have_attribute("tabindex", "0")
            expect(graph_scroll).to_have_attribute("role", "region")
            expect(graph_scroll).to_have_attribute(
                "aria-label", "Scrollable argument graph"
            )
            expect(graph_scroll).to_have_attribute(
                "aria-describedby", "af-graph-summary"
            )
            expect(page.locator("#af-graph-summary")).to_contain_text(
                "For a text explanation"
            )
            graph_svg = graph_scroll.locator("svg")
            expect(graph_svg).to_have_attribute("role", "img")
            expect(graph_svg.locator("title")).to_have_text("ABDA-NL argument graph")
            scope_control = page.locator(".af-scope-control")
            expect(scope_control).to_have_attribute("role", "group")
            key_scope = page.locator('[data-af-scope="key"]')
            all_scope = page.locator('[data-af-scope="all"]')
            expect(key_scope).to_have_attribute("aria-pressed", "true")
            expect(all_scope).to_have_attribute("aria-pressed", "false")
            all_scope.click()
            expect(page.locator('[data-af-scope="key"]')).to_have_attribute(
                "aria-pressed", "false"
            )
            expect(page.locator('[data-af-scope="all"]')).to_have_attribute(
                "aria-pressed", "true"
            )
            expect(page.locator(".af-zoom-controls")).to_have_attribute(
                "role", "group"
            )
            expect(page.locator('[data-af-zoom="out"]')).to_have_attribute(
                "aria-label", "Zoom out"
            )
            expect(page.locator("#af-zoom-readout")).to_have_attribute(
                "aria-live", "polite"
            )
            graph_scroll.focus()
            expect(graph_scroll).to_be_focused()
            _axe_report(page, "argument graph")
            page.keyboard.press("Escape")
            page.locator("#aspic-btn").focus()
            page.locator("#aspic-btn").press("Enter")
            expect(page.locator("#aspic-pre")).not_to_have_text("")
            _axe_report(page, "ASPIC view")
            page.keyboard.press("Escape")

            _reload_ready_demo(page)
            expect(page.locator("#scenario-name")).not_to_have_text("Loading...")
            page.locator("#ai-access-btn").click()
            expect(page.locator("#byok-api-key")).to_have_value("")
            expect(page.locator("#mcp-secret-panel")).to_be_hidden()
            page.keyboard.press("Escape")

            page.set_viewport_size({"width": 720, "height": 450})
            _reload_ready_demo(page)
            expect(page.locator("#scenario-name")).not_to_have_text("Loading...")
            zoom_overflow = page.evaluate(
                "Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) "
                "- window.innerWidth"
            )
            assert zoom_overflow <= 1
            _axe_report(page, "200 percent zoom equivalent")

            page.set_viewport_size({"width": 390, "height": 844})
            _reload_ready_demo(page)
            expect(page.locator("#scenario-name")).not_to_have_text("Loading...")
            expect(page.locator(".compact-switch")).to_be_visible()
            expect(page.locator("#aspic-btn")).to_be_visible()
            overflow = page.evaluate(
                "Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) "
                "- window.innerWidth"
            )
            assert overflow <= 1
            page.locator("#aspic-btn").click()
            expect(page.locator("#aspic-pre")).not_to_have_text("")
            aspic_width_ratio = page.locator("#modal-aspic .modal-content").evaluate(
                "element => element.getBoundingClientRect().width / window.innerWidth"
            )
            assert aspic_width_ratio >= 0.9
            page.keyboard.press("Escape")
            page.locator("#workspace-btn").click()
            expect(dialog).to_be_visible()
            _axe_report(page, "mobile workspace")
            _save_browser_evidence(page, "mobile-workspace")
            with page.expect_navigation(wait_until="domcontentloaded"):
                page.locator("#logout-btn").click()
            _wait_for_demo_ready(page)
            session = page.evaluate(
                "async () => (await fetch('/api/auth/session')).json()"
            )
            assert session["authenticated"] is False
            page.locator("#workspace-btn").click()
            expect(dialog).to_be_visible()
            expect(page.locator("#account-signed-out")).to_be_visible()
            assert console_errors == []
            assert page_errors == []
        except Exception:
            _save_browser_evidence(page, "failure")
            raise
        finally:
            context.close()
            browser.close()
