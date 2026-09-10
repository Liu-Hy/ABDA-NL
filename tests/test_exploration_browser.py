"""Browser acceptance with real static assets and engine data, without a server.

All requests are intercepted inside Playwright. No model endpoint or shared
demo launcher is used, making these checks safe alongside another demo.
"""
from copy import deepcopy
import json
import mimetypes
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from app.scenario.loader import scenario_from_dict
from app.scenario.portable import export_scenario
from app.scenario.state import compute_state_bundle


pytestmark = pytest.mark.skipif(
    os.getenv("ABDA_BROWSER_TESTS") != "1", reason="set ABDA_BROWSER_TESTS=1 to run browser acceptance"
)
STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


@pytest.fixture
def explorer_browser():
    from playwright.sync_api import expect, sync_playwright

    scenario = {
        "title": "Two routes to a decision", "description": "Synthetic browser acceptance",
        "facts": {"p1": {"description": "First record"}, "p2": {"description": "Second record"}},
        "assumptions": {"a": {"description": "The source is reliable", "active": True}},
        "propositions": {"p": {"description": "Evidence is available"}},
        "conclusions": {"c": {"description": "The claim holds", "negated_description": "The claim does not hold"}},
        "rules": {
            "r1": {"type": "strict", "premises": ["p1"], "conclusion": "p"},
            "r2": {"type": "strict", "premises": ["p2"], "conclusion": "p"},
            "top": {"type": "defeasible", "premises": ["p", "a"], "conclusion": "c"},
            "objection": {"type": "defeasible", "premises": ["p2"], "conclusion": "-c"},
        },
        "sources": [{"filename": "record.txt", "text": "Complete source text. The first and second records disagree."}],
    }
    bundle = compute_state_bundle(scenario_from_dict(scenario))
    runtime = {"requests": [], "chat_requests": [], "held": [], "hold_chat": False, "chat_status": 200,
               "bundle": bundle, "user": "researcher-a", "errors": [], "unexpected": []}
    config = {"llm_enabled": True, "llm_auth_required": True, "byok_enabled": True,
              "default_profile": "balanced", "profiles": [{"id": "balanced", "label": "Balanced", "description": "Test model"}],
              "byok_providers": [{"id": "openrouter", "label": "OpenRouter", "default_model": "test-model",
                                  "models": [{"id": "test-model", "label": "Test model"}]}]}
    response = {"message": "The claim is undecided. See the exact evidence below.", "model": "test-model",
                "billing_source": "trial", "cost_microusd": 1, "latency_ms": 1,
                "evidence": [{"kind": "source", "source": "record.txt", "quote": "Complete source text.", "start": 0, "end": 21, "verified": True},
                             {"kind": "rule", "id": "top", "verified": True},
                             {"kind": "source", "source": "fake.txt", "quote": "UNVERIFIED", "verified": False}]}
    runtime["response"] = response

    def route_request(route):
        request = route.request
        url = urlsplit(request.url)
        path = url.path
        runtime["requests"].append(path)
        if url.hostname != "abda.test":
            runtime["unexpected"].append(request.url)
            route.abort()
            return
        payload = None
        status = 200
        if path == "/config":
            payload = config
        elif path == "/api/auth/session":
            payload = {"authenticated": bool(runtime["user"]), "auth_mode": "dev",
                       "user": {"id": runtime["user"], "email": "test@example.edu"} if runtime["user"] else None}
        elif path == "/scenarios":
            payload = {"scenarios": [{"id": "test", "title": scenario["title"]}]}
        elif path == "/state":
            payload = runtime["bundle"]
        elif path == "/api/trial":
            payload = {"active": True, "available_microusd": 5000000, "granted_microusd": 5000000, "spent_microusd": 0}
        elif path == "/api/projects":
            payload = {"projects": []}
        elif path == "/api/scenarios/export":
            data = request.post_data_json
            payload = export_scenario(data["scenario"], None)
        elif path.endswith("/chat"):
            runtime["chat_requests"].append(request.post_data_json)
            if runtime["hold_chat"]:
                runtime["held"].append(route)
                return
            status = runtime["chat_status"]
            payload = response if status == 200 else {"detail": {"code": "llm_unavailable", "message": "Both model routes failed"}}
        elif path == "/favicon.ico":
            route.fulfill(status=204)
            return
        else:
            asset = STATIC / (path.lstrip("/") or "index.html")
            if asset.is_file() and asset.resolve().is_relative_to(STATIC.resolve()):
                route.fulfill(status=200, body=asset.read_bytes(), content_type=mimetypes.guess_type(asset.name)[0] or "application/octet-stream")
                return
            runtime["unexpected"].append(path)
            route.fulfill(status=404, body="Not found")
            return
        route.fulfill(status=status, content_type="application/json", body=json.dumps(payload))

    with sync_playwright() as playwright:
        browser = getattr(playwright, os.getenv("ABDA_BROWSER_ENGINE", "chromium")).launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
        context.route("**/*", route_request)
        page = context.new_page()
        page.on("pageerror", lambda error: runtime["errors"].append(str(error)))
        page.goto("http://abda.test/")
        expect(page.locator("#scenario-name")).to_have_text(scenario["title"])
        expect(page.locator("#chat-send-btn")).to_be_enabled()
        yield page, runtime
        assert runtime["errors"] == []
        assert runtime["unexpected"] == []
        context.close()
        browser.close()


def test_question_insertion_preserves_draft_and_requires_explicit_submit(explorer_browser):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    draft = page.locator("#chat-input")
    draft.fill("Compare these positions carefully.")
    draft.evaluate("input => input.setSelectionRange(8, 13)")
    first = page.locator('[data-context-kind="rule"][data-context-id="r1"]')
    second = page.locator('[data-context-kind="rule"][data-context-id="r2"]')
    desc = first.get_attribute("data-desc")
    first.click()
    assert draft.input_value() == 'Compare \n\nCan you explain "' + desc + '"?\n\nthese positions carefully.'
    second.focus()
    second.press("Enter")
    expect(page.locator(".chat-context-chip")).to_have_count(2)
    assert "these positions carefully." in draft.input_value()
    assert runtime["chat_requests"] == []
    assert "/api/scenarios/export" not in runtime["requests"]
    expect(page.locator(".chat-msg-user")).to_have_count(0)
    draft.fill("How do the two selected rules differ?")
    page.locator("#chat-send-btn").click()
    expect(page.locator(".chat-msg-assistant")).to_contain_text("The claim is undecided")
    assert len(runtime["chat_requests"]) == 1
    sent = runtime["chat_requests"][0]
    assert sent["messages"][-1]["content"] == "How do the two selected rules differ?"
    assert sent["context_refs"] == [{"kind": "rule", "id": "r1"}, {"kind": "rule", "id": "r2"}]
    expect(page.locator(".chat-context-chip")).to_have_count(0)
    page.locator(".chat-evidence summary").click()
    expect(page.locator(".chat-evidence")).to_contain_text("Complete source text.")
    expect(page.locator(".chat-evidence")).not_to_contain_text("UNVERIFIED")
    page.get_by_role("button", name="Inspect rule top", exact=True).click()
    expect(page.locator("#derivation-body")).to_contain_text("Saved scenario at the time of this answer")


def test_draft_remains_editable_without_access_and_during_pending_request(explorer_browser):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    page.evaluate("() => { state.trial.available_microusd = 0; renderChatAccess(); }")
    page.locator(".rule-info").first.click()
    expect(page.locator("#chat-input")).to_be_editable()
    expect(page.locator("#chat-send-btn")).to_be_disabled()
    assert runtime["chat_requests"] == []
    page.evaluate("() => { state.trial.available_microusd = 5000000; renderChatAccess(); }")
    runtime["hold_chat"] = True
    page.locator("#chat-send-btn").click()
    expect(page.locator(".chat-msg-loading")).to_be_visible()
    page.wait_for_function("state.chatMessages.some(message => message.role === 'user')")
    page.locator("#chat-input").fill("Next question")
    page.locator('[data-context-id="r1"]').click()
    next_draft = page.locator("#chat-input").input_value()
    expect(page.locator("#chat-send-btn")).to_be_disabled()
    page.wait_for_timeout(50)
    assert len(runtime["held"]) == 1
    runtime["held"].pop().fulfill(status=200, content_type="application/json", body=json.dumps(runtime["response"]))
    expect(page.locator(".chat-msg-loading")).to_have_count(0)
    assert page.locator("#chat-input").input_value() == next_draft
    expect(page.locator(".chat-context-chip")).to_have_count(1)
    assert len(runtime["chat_requests"]) == 1


def test_history_export_snapshot_fork_reload_and_account_isolation(explorer_browser):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    effective = deepcopy(runtime["bundle"]["scenario"])
    effective["assumptions"]["a"]["active"] = False
    effective_bundle = compute_state_bundle(scenario_from_dict(effective))
    page.evaluate("""bundle => {
        state.diff_ops = [{op: 'set_assumption_active', id: 'a', active: false}];
        setBundle(bundle); indexBundle(); renderAll();
        state.llmAccess.apiKey = 'secret-provider-placeholder';
        state.authSession.user.private_token = 'secret-bearer-placeholder';
    }""", effective_bundle)
    page.locator("#chat-input").fill("Which conclusion changed?")
    page.locator("#chat-send-btn").click()
    expect(page.locator(".chat-msg-assistant")).to_contain_text("The claim is undecided")
    page.locator("#chat-input").fill("Saved unfinished follow-up")
    with page.expect_download() as download_info:
        page.locator("#conversation-export").click()
    exported = json.loads(Path(download_info.value.path()).read_text())
    raw = json.dumps(exported)
    assert "secret-provider-placeholder" not in raw and "secret-bearer-placeholder" not in raw
    record = exported["conversation"]
    snapshot = record["snapshots"][record["messages"][0]["snapshot_id"]]
    assert snapshot["scenario"]["scenario"]["assumptions"]["a"]["active"] is False
    assert snapshot["scenario"]["scenario"]["sources"][0]["text"].startswith("Complete source text.")
    assert snapshot["pending_ops"] == [{"op": "set_assumption_active", "id": "a", "active": False}]
    assert compute_state_bundle(scenario_from_dict(snapshot["scenario"]["scenario"]))["af"] == snapshot["af"]
    page.reload()
    expect(page.locator("#chat-messages")).to_contain_text("Which conclusion changed?")
    expect(page.locator("#chat-input")).to_have_value("Saved unfinished follow-up")
    page.get_by_role("button", name="Edit and fork with current scenario", exact=True).click()
    expect(page.locator("#chat-input")).to_have_value("Which conclusion changed?")
    expect(page.locator("#conversation-select option")).to_have_count(2)
    assert page.evaluate("activeConversation().fork_of.new_question_scenario") == "current"
    original_id = record["id"]
    page.locator("#conversation-select").select_option(original_id)
    expect(page.locator("#chat-input")).to_have_value("Saved unfinished follow-up")
    runtime["user"] = "researcher-b"
    page.evaluate("""() => { state.authSession.user = {id: 'researcher-b', email: 'other@example.edu'}; renderAccountUI(); }""")
    expect(page.locator("#chat-messages")).not_to_contain_text("Which conclusion changed?")
    expect(page.locator("#chat-input")).to_have_value("")
    page.locator("#chat-input").fill("Other account draft")
    assert "Which conclusion changed?" not in page.evaluate("localStorage.getItem('abda-conversations-v1:researcher-b')")
    page.evaluate("""() => { state.authSession = {authenticated: false, auth_mode: 'dev', user: null}; renderAccountUI(); }""")
    expect(page.locator("#chat-input")).to_have_value("")
    expect(page.locator("#conversation-storage-note")).to_contain_text("this tab while signed out")


def test_individual_derivations_preserve_shared_top_rules_and_navigation(explorer_browser):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    bundle = runtime["bundle"]
    candidates = [arg for arg in bundle["af"]["arguments"] if arg["conclusion"] == "c"]
    assert len(candidates) == 2 and candidates[0]["top_rule"] == candidates[1]["top_rule"]
    page.locator('[data-inspect-conclusion="c"]').click()
    select = page.locator("#derivation-argument-select")
    expect(select.locator("option")).to_have_count(len(bundle["af"]["arguments"]))
    select.select_option(candidates[0]["id"])
    expect(page.locator(".derivation-summary")).to_contain_text(candidates[0]["id"])
    expect(page.locator("#derivation-body")).to_contain_text("Incoming attacks")
    expect(page.locator("#derivation-body")).to_contain_text("p, a => c [top]")
    other = page.locator(f'[data-inspect-argument="{candidates[1]["id"]}"]')
    page.get_by_text("Other derivations of this exact conclusion", exact=True).click()
    other.click()
    expect(select).to_have_value(candidates[1]["id"])
    top = page.locator('[data-locate-kind="rule"][data-locate-id="top"]').first
    top.click()
    expect(page.locator('#kb-content [data-element-id="top"]')).to_have_class(re.compile("explorer-highlight"))
    page.locator("#view-af-btn").click()
    expect(page.locator("#modal-af .modal-title")).to_have_text("Conclusion overview")
    page.locator("#af-inspect-all").click()
    expect(page.locator("#modal-derivation")).to_be_visible()
    assert runtime["chat_requests"] == []


def test_provider_failure_preserves_question_and_non_llm_actions(explorer_browser):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    runtime["chat_status"] = 503
    page.locator("#chat-input").fill("Why is this undecided?")
    page.locator("#chat-send-btn").click()
    expect(page.locator("#chat-degraded-note")).to_be_visible()
    expect(page.locator("#chat-input")).to_have_value("Why is this undecided?")
    expect(page.locator("#chat-send-btn")).to_be_enabled()
    page.locator('[data-inspect-conclusion="c"]').click()
    expect(page.locator("#derivation-body")).to_contain_text("computed by ABDA")
    page.keyboard.press("Escape")
    runtime["chat_status"] = 200
    page.locator("#chat-send-btn").click()
    expect(page.locator("#chat-degraded-note")).to_be_hidden()
    assert len(runtime["chat_requests"]) == 2


def test_mobile_stale_context_retains_text_and_makes_no_model_request(explorer_browser):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    page.set_viewport_size({"width": 390, "height": 844})
    page.locator(".rule-info").first.click()
    expect(page.locator("#chat-input")).to_be_focused()
    draft = page.locator("#chat-input").input_value()
    rect = page.locator("#chat-input").bounding_box()
    assert rect and 0 <= rect["y"] < 844
    page.evaluate("""() => { state.bundle = structuredClone(state.bundle); state.bundle.scenario.title = 'Changed'; renderAll(); }""")
    expect(page.locator(".chat-context-stale")).to_have_count(1)
    page.locator("#chat-send-btn").click()
    assert runtime["chat_requests"] == []
    expect(page.locator("#chat-input")).to_have_value(draft)
    expect(page.locator("#global-status")).to_contain_text("earlier scenario state")
    page.locator(".chat-context-chip button").click()
    expect(page.locator(".chat-context-chip")).to_have_count(0)


def test_exploration_controls_and_derivation_inspector_accessibility(explorer_browser, tmp_path):
    from axe_playwright_python.sync_playwright import Axe
    from playwright.sync_api import expect

    page, _ = explorer_browser
    page.locator(".rule-info").first.click()
    for label in ["question context", "derivation inspector"]:
        if label == "derivation inspector":
            page.locator('[data-inspect-conclusion="c"]').click()
            expect(page.locator("#derivation-argument-select")).to_be_focused()
        result = Axe().run(page, options={"runOnly": {"type": "tag", "values": ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]}})
        assert result.violations_count == 0, f"{label}: {result.generate_report()}"
        page.screenshot(path=str(tmp_path / f"{label.replace(' ', '-')}.png"), full_page=True)
    page.keyboard.press("Escape")
    expect(page.locator('[data-inspect-conclusion="c"]')).to_be_focused()


def test_new_delete_and_storage_failure_are_explicit(explorer_browser):
    from playwright.sync_api import expect

    page, _ = explorer_browser
    page.locator("#chat-input").fill("A saved draft")
    original_id = page.evaluate("conversationStore.activeId")
    page.locator("#conversation-new").click()
    expect(page.locator("#chat-input")).to_have_value("")
    page.locator("#conversation-select").select_option(original_id)
    expect(page.locator("#chat-input")).to_have_value("A saved draft")
    page.once("dialog", lambda dialog: dialog.accept())
    page.locator("#conversation-delete").click()
    stored = page.evaluate("JSON.parse(localStorage.getItem('abda-conversations-v1:researcher-a'))")
    assert original_id not in {record["id"] for record in stored["records"]}
    page.evaluate("""() => { Storage.prototype.setItem = () => { throw new DOMException('Full', 'QuotaExceededError'); }; }""")
    page.locator("#chat-input").fill("Still editable when storage is full")
    expect(page.locator("#conversation-storage-note")).to_contain_text("History could not be saved")
    expect(page.locator("#chat-input")).to_have_value("Still editable when storage is full")
