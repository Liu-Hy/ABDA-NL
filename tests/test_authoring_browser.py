"""Authoring workflows against a disposable service with no funded providers."""
from __future__ import annotations

import json
import os
from copy import deepcopy
from uuid import uuid4

import pytest

from test_browser_e2e import BROWSER_ENGINE, _axe_report, _save_browser_evidence
from test_browser_e2e import live_browser_server as live_browser_server  # noqa: F401

pytestmark = pytest.mark.skipif(
    os.getenv("ABDA_BROWSER_TESTS") != "1", reason="set ABDA_BROWSER_TESTS=1"
)


@pytest.fixture
def authoring_page(live_browser_server, request):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page(viewport={"width": 1200, "height": 900}, reduced_motion="reduce")
        errors = []
        network = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("response", lambda response: network.append({"path": response.url.removeprefix(live_browser_server), "status": response.status}))
        page.on("requestfailed", lambda failed: network.append({"path": failed.url.removeprefix(live_browser_server), "failed": failed.failure}))
        assert page.request.post(
            live_browser_server + "/api/auth/dev/login", data={"email": f"{uuid4().hex}@example.org"}
        ).ok
        page.goto(live_browser_server, wait_until="domcontentloaded")
        try:
            expect(page.locator("#scenario-name")).not_to_have_text("Loading...", timeout=15_000)
            expect(page.locator("#conclusions-list .conclusion-card").first).to_be_visible()
        except AssertionError as error:
            _save_browser_evidence(page, request.node.name + "-setup-failure")
            status = page.locator("#global-status").text_content()
            raise AssertionError(f"Demo setup failed; status: {status}; browser errors: {errors}; network: {network}") from error
        try:
            yield page, live_browser_server
            assert not errors
        finally:
            browser.close()


def _open_editor(page, mode="new"):
    page.locator("#scenario-menu-btn").click()
    page.locator({"new": "#scenario-library-btn", "file": "#scenario-import-btn", "edit": "#scenario-edit-btn"}[mode]).click()


def _choose(picker, text, *, negative=False):
    if picker.locator(".authoring-literal-chip").is_visible():
        picker.locator(".authoring-literal-chip").click()
    field = picker.get_by_role("combobox")
    field.fill(text)
    field.press("ArrowDown")
    field.press("Enter")
    if negative:
        picker.get_by_role("checkbox").check()


def _seed_scenario():
    return {
        "title": "Imported river decision",
        "description": "The background is retained when editing.",
        "facts": {"rain": {"description": "Heavy rain is forecast"}},
        "conclusions": {"close": {"description": "Close the river path"}},
        "rules": {"weather_rule": {"premises": ["rain"], "conclusion": "close", "type": "defeasible", "block": 1}},
        "sources": [],
    }


def _queue(page, scenario, name="portable.txt"):
    page.locator("#scenario-file-input").set_input_files(
        {"name": name, "mimeType": "text/plain", "buffer": json.dumps(scenario).encode()}
    )
    from playwright.sync_api import expect
    expect(page.locator("#scenario-load-files")).to_be_enabled()
    expect(page.locator("#scenario-import-status")).to_contain_text("suggested roles")


def test_empty_draft_inline_errors_readable_ids_and_one_step_save(authoring_page):
    from playwright.sync_api import expect

    page, base = authoring_page
    _open_editor(page)
    expect(page.locator("#scenario-editor-heading")).to_have_text("New scenario")
    expect(page.locator("[data-statement-id]")).to_have_count(0)
    expect(page.locator("[data-builder-rule-id]")).to_have_count(0)
    expect(page.locator("#scenario-library-submit")).to_have_text("Check & save")
    page.locator("#scenario-add-statement").click()
    page.locator("#scenario-library-submit").click()
    expect(page.locator("#scenario-error-summary")).to_contain_text("2 problems")
    expect(page.locator("#scenario-builder-title")).to_have_attribute("aria-invalid", "true")
    page.get_by_role("button", name="Go to problem: Give your scenario a title.").click()
    expect(page.locator("#scenario-builder-title")).to_be_focused()
    page.locator("#scenario-builder-title").fill("My own picnic")
    statement = page.locator("[data-statement-id]").first
    statement.locator("input[type=text]").fill("The forecast is sunny")
    page.locator("#scenario-add-statement").click()
    expect(page.locator('[data-statement-id="forecast_sunny"]')).to_have_count(1)
    claim = page.locator("[data-statement-id]").last
    claim.locator("input[type=text]").fill("We should hold the picnic outside")
    claim.locator("select").select_option("proposition")
    claim.get_by_role("checkbox", name="Key conclusion").check()
    page.locator("#scenario-add-rule").click()
    rule = page.locator("[data-builder-rule-id]").first
    _choose(rule.locator("[data-literal]").nth(0), "forecast")
    _choose(rule.locator("[data-literal]").nth(1), "picnic")
    expect(page.locator('[data-builder-rule-id="rule_forecast_sunny"]')).to_have_count(1)
    forecast = page.locator('[data-statement-id="forecast_sunny"]')
    forecast.locator("input[type=text]").fill("The sky will remain clear today")
    page.locator("#scenario-builder-title").click()
    expect(forecast).to_have_count(1)
    expect(rule.locator(".authoring-rule-preview")).to_contain_text("sky will remain clear")
    expect(page.locator("#scenario-error-summary")).to_be_hidden()
    _axe_report(page, "guided authoring with searchable literals")
    with page.expect_response(lambda response: response.url.endswith("/api/projects/import") and response.request.method == "POST") as created:
        page.locator("#scenario-library-submit").click()
    saved = created.value.json()
    expect(page.locator("#scenario-name")).to_have_text("My own picnic")
    assert saved["scenario"]["rules"]["rule_forecast_sunny"]["premises"] == ["forecast_sunny"]
    assert saved["scenario"]["rules"]["rule_forecast_sunny"]["conclusion"] == "hold_picnic_outside"
    assert page.request.get(base + "/api/trial").json()["active"] is False


def test_content_import_receipts_and_editor_discard_preserve_entry_snapshot(authoring_page):
    from playwright.sync_api import expect

    page, base = authoring_page
    _open_editor(page, "file")
    expect(page.locator("#scenario-file-input")).to_be_focused()
    scenario = _seed_scenario()
    _queue(page, scenario, "misleading-rules.txt")
    expect(page.get_by_role("combobox", name="File role: misleading-rules.txt")).to_have_value("scenario")
    with page.expect_response(lambda response: response.url.endswith("/api/projects/import") and response.request.method == "POST") as created:
        page.locator("#scenario-open-file-project").click()
    saved = created.value.json()
    expect(page.locator("#scenario-name")).to_have_text(scenario["title"])
    # The editor opens the current working scenario, including an unsaved explorer change.
    page.evaluate("""() => {
      const scenario = structuredClone(state.bundle.scenario);
      scenario.description = 'Unsaved exploration background';
      setBundle({...state.bundle, scenario});
      state.diff_ops = [{op:'modify_rule', rule_id:'weather_rule', rule:scenario.rules.weather_rule}];
      renderAll();
    }""")
    _open_editor(page, "edit")
    expect(page.locator("#scenario-editor-heading")).to_have_text("Edit: " + scenario["title"])
    expect(page.locator("#scenario-editor-outcome")).to_contain_text(f"version {saved['version']}")
    expect(page.locator("#scenario-editor-navigation")).to_be_hidden()
    expect(page.locator("#scenario-start-actions")).to_be_hidden()
    expect(page.locator("#scenario-background-details")).to_have_attribute("open", "")
    expect(page.locator('[data-statement-id="rain"]')).to_have_count(1)
    page.locator("#scenario-builder-description").fill("Editor-only replacement")
    page.once("dialog", lambda dialog: dialog.accept())
    page.locator("#scenario-discard-changes").click()
    expect(page.locator("#scenario-builder-description")).to_have_value("Unsaved exploration background")
    assert page.request.get(base + "/api/projects/" + saved["id"]).json()["scenario"]["description"] == scenario["description"]
    page.set_viewport_size({"width": 390, "height": 844})
    _axe_report(page, "narrow edit mode")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    _save_browser_evidence(page, "authoring-edit-narrow")


def test_ambiguous_prose_confirmation_atomic_import_and_warning_save(authoring_page):
    from playwright.sync_api import expect

    page, base = authoring_page
    _open_editor(page, "file")
    _queue(page, _seed_scenario())
    page.locator("#scenario-load-files").click()
    expect(page.locator("#scenario-import-files")).to_contain_text("✓ Loaded into editor")
    expect(page.locator("#scenario-import-files")).to_contain_text("KB upload")
    prior = page.locator("#scenario-builder-title").input_value()
    page.locator("#scenario-file-input").set_input_files({
        "name": "notes.txt", "mimeType": "text/plain", "buffer": b"In conversation, more rain => we might close the long river path."
    })
    expect(page.locator("#scenario-import-files")).to_contain_text("not clearly formal rules")
    page.locator("#scenario-load-files").click()
    expect(page.locator("#scenario-import-status")).to_contain_text("Choose or confirm")
    page.get_by_role("checkbox", name="Use the suggested role").check()
    page.locator("#scenario-load-files").click()
    expect(page.locator("#scenario-import-files")).to_contain_text("✓ Loaded into editor")
    expect(page.locator("#scenario-builder-title")).to_have_value(prior)
    assert page.evaluate("scenarioLibrary.base.sources[0].text").startswith("In conversation")
    # A late invalid file leaves the entire existing editor draft unchanged.
    before = page.evaluate("JSON.stringify(scenarioLibrary.base)")
    page.locator("#scenario-file-input").set_input_files([
        {"name": "valid.txt", "mimeType": "text/plain", "buffer": b"A valid reference."},
        {"name": "empty.txt", "mimeType": "text/plain", "buffer": b""},
    ])
    expect(page.locator("#scenario-import-status")).to_contain_text("suggested roles")
    while page.locator("#scenario-import-files input[type=checkbox]:not(:checked)").count():
        page.locator("#scenario-import-files input[type=checkbox]:not(:checked)").first.check()
    page.locator("#scenario-load-files").click()
    expect(page.locator("#scenario-import-status")).to_contain_text("previous editor draft is unchanged")
    assert page.evaluate("JSON.stringify(scenarioLibrary.base)") == before
    # Server warnings require a second decision while retaining the valid checked draft.
    def add_warning(route):
        response = route.fetch()
        payload = response.json()
        payload["warnings"] = ["Review this imported source before saving."]
        route.fulfill(response=response, json=payload)
    page.route("**/api/projects/editor/preview", add_warning)
    page.locator("#scenario-builder-title").fill("Warning-aware save")
    page.locator("#scenario-library-submit").click()
    expect(page.locator("#scenario-file-warnings")).to_contain_text("Review this imported source")
    expect(page.locator("#scenario-library-submit")).to_have_text("Save & open")
    assert page.request.get(base + "/api/projects").json()["projects"] == []
    page.locator("#scenario-library-submit").click()
    expect(page.locator("#scenario-name")).to_have_text("Warning-aware save")


def test_source_table_reader_edit_replace_and_capacity(authoring_page):
    from playwright.sync_api import expect

    page, _base = authoring_page
    _open_editor(page)
    page.locator("#scenario-builder-title").fill("Retained document review")
    page.locator("#scenario-sources-panel > summary").click()
    page.get_by_role("button", name="Paste document text", exact=True).click()
    page.locator("#library-sources-new-edit-name").fill("record.txt")
    page.locator("#library-sources-new-edit-text").fill("Original source text. 中文 also remains intact.")
    page.get_by_role("button", name="Keep document", exact=True).click()
    table = page.locator("#library-sources-new .authoring-documents")
    expect(table).to_contain_text("record.txt")
    expect(table).to_contain_text("characters")
    expect(table).to_contain_text("KB UTF-8")
    expect(page.locator("#library-sources-new-capacity")).to_have_attribute("value", "49")
    page.get_by_role("button", name="Open record.txt", exact=True).click()
    expect(page.locator("#source-reader-text")).to_have_text("Original source text. 中文 also remains intact.")
    page.locator("#source-reader-edit").click()
    expect(page.locator("#modal-sources-reader")).to_be_hidden()
    expect(page.locator("#library-sources-new-edit-text")).to_be_focused()
    page.locator("#library-sources-new-edit-text").fill("Corrected retained text.")
    page.get_by_role("button", name="Keep document", exact=True).click()
    assert page.evaluate("librarySources.new.value()[0].text") == "Corrected retained text."
    with page.expect_file_chooser() as chooser:
        page.get_by_role("button", name="Replace record.txt", exact=True).click()
    chooser.value.set_files({
        "name": "replacement.md", "mimeType": "text/markdown", "buffer": b"# Replacement\nExact updated source text."
    })
    expect(table).to_contain_text("replacement.md")
    expect(table).not_to_contain_text("record.txt")
    page.set_viewport_size({"width": 390, "height": 844})
    _axe_report(page, "retained source table at narrow width")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    _save_browser_evidence(page, "authoring-sources-narrow")
    page.get_by_role("button", name="Remove replacement.md", exact=True).click()
    expect(page.locator("#library-sources-new-capacity")).to_have_attribute("value", "0")


def test_search_groups_negation_undercuts_and_stable_atomic_rename(authoring_page):
    from playwright.sync_api import expect

    page, _base = authoring_page
    _open_editor(page, "file")
    scenario = _seed_scenario()
    scenario["assumptions"] = {"safe": {"description": "The river is safe", "active": True}}
    scenario["rules"]["safety"] = {"premises": ["safe"], "conclusion": "-weather_rule", "type": "defeasible"}
    scenario["facts"].update({f"record_{index}": {"description": f"Background record {index}"} for index in range(25)})
    _queue(page, scenario)
    page.locator("#scenario-load-files").click()
    expect(page.locator("#scenario-import-files")).to_contain_text("✓ Loaded into editor")
    expect(page.locator(".authoring-statement-group > summary").first).to_have_text("Facts (26)")
    expect(page.locator('[data-statement-id="rain"]')).not_to_have_attribute("open", "")
    page.locator("#scenario-builder-filter").fill("record 23")
    expect(page.locator("[data-statement-id]:visible")).to_have_count(1)
    page.locator("#scenario-builder-filter").fill("")
    rule = page.locator('[data-builder-rule-id="safety"]')
    rule.locator(":scope > summary").click()
    picker = rule.locator("[data-literal]").last
    picker.locator(".authoring-literal-chip").click()
    expect(picker.get_by_role("group", name="Rule does not apply", exact=True)).to_be_visible()
    picker.get_by_role("combobox").press("Escape")
    expect(picker.locator(".authoring-literal-chip")).to_be_visible()
    expect(page.locator("#modal-scenario-library")).to_be_visible()
    assert page.evaluate("scenarioLibrary.rules.find(rule => rule.id === 'safety').conclusion") == "-weather_rule"
    picker.locator(".authoring-literal-chip").click()
    picker.get_by_role("combobox").fill("close")
    picker.get_by_role("combobox").press("ArrowDown")
    picker.get_by_role("combobox").press("Enter")
    picker.get_by_role("checkbox").check()
    assert page.evaluate("scenarioLibrary.rules.find(rule => rule.id === 'safety').conclusion") == "-close"
    # Restore an undercut by search, then perform the existing atomic manual rename.
    _choose(picker, "weather_rule")
    expect(picker.locator(".authoring-literal-chip")).to_contain_text("does not apply")
    page.locator("#scenario-symbol-renamer > summary").click()
    page.locator("#scenario-rename-from").select_option("weather_rule")
    page.locator("#scenario-rename-to").fill("forecast_rule")
    page.locator("#scenario-rename-apply").click()
    assert page.evaluate("scenarioLibrary.rules.find(rule => rule.id === 'safety').conclusion") == "-forecast_rule"
    assert page.evaluate("scenarioLibrary.statements.some(item => item.id === 'rain')")
    # Large scenario falls back explicitly without truncating the retained draft.
    large = deepcopy(scenario)
    large["facts"].update({f"extra_{index}": {"description": f"Extra record {index}"} for index in range(110)})
    page.evaluate("scenario => { loadScenarioDraft(scenario); setScenarioMode('guided'); renderScenarioLibraryAccess(); }", large)
    expect(page.locator("#scenario-guided-limit")).to_be_visible()
    expect(page.locator("#scenario-guided-limit")).to_contain_text("No content was removed")
    expect(page.locator("#scenario-rule-text-panel")).to_be_visible()
    assert page.evaluate("scenarioLibrary.statements.length") == 138
