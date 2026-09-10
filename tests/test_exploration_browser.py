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

from app.scenario.loader import load_scenario, scenario_from_dict
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
            payload = response if status == 200 else runtime.get("chat_error", {"detail": {"code": "llm_unavailable", "message": "Both model routes failed"}})
        elif path.endswith("/propose"):
            status = runtime.get("propose_status", 503)
            payload = runtime.get("propose_error", {"detail": {"code": "llm_unavailable", "message": "Both model routes failed"}})
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
        page.goto("https://abda.test/")
        expect(page.locator("#scenario-name")).to_have_text(scenario["title"])
        expect(page.locator("#chat-send-btn")).to_be_enabled()
        _wait_for_history(page)
        yield page, runtime
        assert runtime["errors"] == []
        assert runtime["unexpected"] == []
        context.close()
        browser.close()


def _wait_for_history(page, owner="researcher-a"):
    page.wait_for_function("owner => conversationStore.owner === owner", arg=owner)
    page.evaluate("() => conversationStore.ready")


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
    page.evaluate("() => flushConversationWrites()")
    assert "Which conclusion changed?" not in json.dumps(page.evaluate("() => conversationHistory.list('researcher-b')"))
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
    expect(select).to_have_value(candidates[0]["id"])
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


def test_provider_failure_drafts_reuse_immutable_snapshot_encoding(explorer_browser):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    runtime["chat_status"] = 503
    page.locator("#chat-input").fill("A question whose request fails")
    page.locator("#chat-send-btn").click()
    expect(page.locator("#chat-degraded-note")).to_be_visible()
    page.evaluate("() => flushConversationWrites()")
    page.evaluate("""async () => {
        const digest = crypto.subtle.digest.bind(crypto.subtle);
        window.__historyDigestCalls = 0;
        crypto.subtle.digest = (...args) => {
            window.__historyDigestCalls++;
            return digest(...args);
        };
        for (const text of ['Revised draft', 'Another draft', 'Final saved draft']) {
            document.querySelector('#chat-input').value = text;
            saveConversationDraft();
            await flushConversationWrites();
        }
    }""")
    assert page.evaluate("window.__historyDigestCalls") == 0
    saved = page.evaluate("() => conversationHistory.list('researcher-a')")
    record = saved["records"][0]["record"]
    assert record["draft"] == "Final saved draft"
    assert len(record["snapshots"]) == 1
    snapshot = next(iter(record["snapshots"].values()))
    assert snapshot["scenario"]["scenario"]["sources"][0]["text"].startswith("Complete source text.")


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
    page.get_by_role("button", name=re.compile("^Remove .* from question context$")).click()
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
    page.wait_for_function("id => !conversationStore.records.some(record => record.id === id)", arg=original_id)
    stored = page.evaluate("() => conversationHistory.list('researcher-a')")
    assert original_id not in {item["record"]["id"] for item in stored["records"]}
    page.evaluate("""() => {
        window.__historySave = conversationHistory.save;
        conversationHistory.save = async () => { throw new DOMException('Full', 'QuotaExceededError'); };
    }""")
    page.locator("#chat-input").fill("Still editable when storage is full")
    expect(page.locator("#conversation-storage-note")).to_contain_text("History could not be saved")
    expect(page.locator("#chat-input")).to_have_value("Still editable when storage is full")
    expect(page.locator("#conversation-export-all")).to_be_visible()
    with page.expect_download() as recovery:
        page.locator("#conversation-export-all").click()
    exported = json.loads(Path(recovery.value.path()).read_text())
    assert any(record["draft"] == "Still editable when storage is full" for record in exported["conversations"])
    page.evaluate("() => { conversationHistory.save = window.__historySave; }")
    page.locator("#conversation-retry-save").click()
    expect(page.locator("#conversation-retry-save")).to_be_hidden()


def test_cross_tab_history_keeps_concurrent_edits_and_deleted_records_stay_deleted(explorer_browser):
    from playwright.sync_api import expect

    page, _ = explorer_browser
    page.locator("#chat-input").fill("Original shared draft")
    page.evaluate("() => flushConversationWrites()")
    original_id = page.evaluate("conversationStore.activeId")
    other = page.context.new_page()
    other.goto("https://abda.test/")
    expect(other.locator("#chat-input")).to_have_value("Original shared draft")
    try:
        page.locator("#chat-input").fill("Version from the first tab")
        page.evaluate("clearTimeout(conversationStore.timer)")
        other.locator("#chat-input").fill("Version from the second tab")
        other.evaluate("clearTimeout(conversationStore.timer)")
        page.evaluate("() => flushConversationWrites()")
        other.evaluate("() => flushConversationWrites()")
        saved = page.evaluate("() => conversationHistory.list('researcher-a')")
        assert {item["record"]["draft"] for item in saved["records"]} == {
            "Version from the first tab", "Version from the second tab",
        }
        expect(other.locator("#conversation-storage-note")).to_contain_text("Both versions were kept")
        expect(page.locator("#conversation-select option")).to_have_count(2)
        stale = next(item for item in saved["records"] if item["record"]["id"] == original_id)
        page.locator("#conversation-select").select_option(original_id)
        page.once("dialog", lambda dialog: dialog.accept())
        page.locator("#conversation-delete").click()
        page.wait_for_function("id => conversationStore.deleted.has(id)", arg=original_id)
        result = other.evaluate("payload => conversationHistory.save('researcher-a', payload.record, payload.revision)", stale)
        assert result["deleted"] is True
        other.reload()
        _wait_for_history(other)
        saved = other.evaluate("() => conversationHistory.list('researcher-a')")
        assert original_id not in {item["record"]["id"] for item in saved["records"]}
        assert "Version from the second tab" in json.dumps(saved)
    finally:
        other.close()


def test_creating_conversations_in_two_tabs_does_not_overwrite_other_history(explorer_browser):
    from playwright.sync_api import expect

    page, _ = explorer_browser
    other = page.context.new_page()
    other.goto("https://abda.test/")
    _wait_for_history(other)
    try:
        page.locator("#chat-input").fill("First independent conversation")
        other.locator("#chat-input").fill("Second independent conversation")
        page.evaluate("() => flushConversationWrites()")
        other.evaluate("() => flushConversationWrites()")
        page.locator("#chat-input").press("End")
        page.locator("#chat-input").type(" updated")
        page.evaluate("() => flushConversationWrites()")
        saved = page.evaluate("() => conversationHistory.list('researcher-a')")
        assert {item["record"]["draft"] for item in saved["records"]} == {
            "First independent conversation updated", "Second independent conversation",
        }
        expect(page.locator("#conversation-select option")).to_have_count(2)
    finally:
        other.close()


@pytest.mark.parametrize("transition", ["reset", "new", "delete", "account", "signout", "remote_delete"])
def test_late_answers_keep_the_captured_history_without_resurrection_or_account_leaks(explorer_browser, transition):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    runtime["hold_chat"] = True
    page.locator("#chat-input").fill("Question about the captured scenario")
    page.locator("#chat-send-btn").click()
    page.wait_for_function("activeConversation().messages.length === 1")
    page.evaluate("() => flushConversationWrites()")
    original_id = page.evaluate("conversationStore.activeId")
    if transition == "reset":
        page.locator("#reset-btn").click()
    elif transition == "new":
        page.locator("#conversation-new").click()
    elif transition == "delete":
        page.once("dialog", lambda dialog: dialog.accept())
        page.locator("#conversation-delete").click()
        page.wait_for_function("id => conversationStore.deleted.has(id)", arg=original_id)
    elif transition == "remote_delete":
        page.evaluate("id => conversationHistory.remove('researcher-a', id)", original_id)
    else:
        page.evaluate("user => { state.authSession = {authenticated: !!user, user: user ? {id: user} : null}; renderAccountUI(); }",
                      "researcher-b" if transition == "account" else None)
    page.wait_for_timeout(50)
    assert len(runtime["held"]) == 1
    runtime["held"].pop().fulfill(status=200, content_type="application/json", body=json.dumps(runtime["response"]))
    page.wait_for_function("!conversationStore.records.some(record => record.pending)")
    page.evaluate("() => flushConversationWrites()")
    if transition in {"reset", "new"}:
        expect(page.locator("#chat-messages")).not_to_contain_text(runtime["response"]["message"])
        page.locator("#conversation-select").select_option(original_id)
        expect(page.locator("#chat-messages")).to_contain_text(runtime["response"]["message"])
        expect(page.locator("#chat-messages")).to_contain_text("earlier scenario saved with this question")
        page.reload()
        expect(page.locator("#chat-messages")).to_contain_text(runtime["response"]["message"])
    else:
        awaitable = page.evaluate("() => conversationHistory.list('researcher-a')")
        assert runtime["response"]["message"] not in json.dumps(awaitable)
        expect(page.locator("#chat-messages")).not_to_contain_text(runtime["response"]["message"])


def test_legacy_migration_shared_source_dedup_and_empty_drafts(explorer_browser):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    portable = export_scenario(runtime["bundle"]["scenario"], None)
    snapshot = {"scenario": portable, "af": runtime["bundle"]["af"], "pending_ops": [], "captured_at": "2026-09-10T00:00:00Z"}
    record = {"id": "legacy-record", "title": "Legacy discussion", "draft": "Unsent legacy draft", "context_refs": [],
              "messages": [{"role": "user", "content": "Saved legacy question", "snapshot_id": "s1"}],
              "snapshots": {"s1": snapshot}}
    page.evaluate("record => localStorage.setItem('abda-conversations-v1:researcher-a', JSON.stringify({version:1,active_id:record.id,records:[record]}))", record)
    page.reload()
    expect(page.locator("#chat-input")).to_have_value("Unsent legacy draft")
    assert page.evaluate("localStorage.getItem('abda-conversations-v1:researcher-a')") is None
    with page.expect_download() as download:
        page.locator("#conversation-export").click()
    exported = json.loads(Path(download.value.path()).read_text())["conversation"]
    assert exported["snapshots"]["s1"] == snapshot
    assert scenario_from_dict(exported["snapshots"]["s1"]["scenario"]["scenario"])
    # A tab running the old assets may write v1 again after migration. Keep its
    # later edits without overwriting the already migrated record.
    late_legacy = deepcopy(record)
    late_legacy["draft"] = "Later edit from an older tab"
    page.evaluate("record => localStorage.setItem('abda-conversations-v1:researcher-a', JSON.stringify({version:1,active_id:record.id,records:[record]}))", late_legacy)
    page.reload()
    _wait_for_history(page)
    migrated = page.evaluate("() => conversationHistory.list('researcher-a')")
    assert {item["record"]["draft"] for item in migrated["records"]} == {
        "Unsent legacy draft", "Later edit from an older tab",
    }
    page.evaluate("""async () => {
        const original = structuredClone(activeConversation());
        for (let index = 0; index < 8; index++) {
            const record = structuredClone(original);
            record.id = `distinct-${index}`;
            record.snapshots.s1.scenario.scenario.title = `Scenario edit ${index}`;
            await conversationHistory.save('researcher-a', record, 0);
        }
    }""")
    parts = page.evaluate("""() => new Promise(resolve => {
      const opening = indexedDB.open('abda-conversations',1);
      opening.onsuccess = () => {
        const read = opening.result.transaction('blobs').objectStore('blobs').getAll();
        read.onsuccess = () => { opening.result.close(); resolve(read.result); };
      };
    })""")
    assert sum("Complete source text." in part["data"] for part in parts) == 1
    page.locator("#conversation-new").click()
    for _ in range(4):
        page.locator("#conversation-new").click()
    assert page.evaluate("conversationStore.records.filter(record => !conversationHasContent(record)).length") == 1


def test_stale_refresh_limit_and_forked_context_keep_editable_text(explorer_browser):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    rule = page.locator('[data-context-kind="rule"][data-context-id="r1"]')
    rule.click()
    original = page.locator("#chat-input").input_value()
    page.evaluate("() => { state.bundle = structuredClone(state.bundle); state.bundle.scenario.title = 'Changed'; renderAll(); }")
    rule.click()
    expect(page.locator("#chat-input")).to_have_value(original)
    expect(page.locator(".chat-context-chip")).to_have_count(1)
    expect(page.locator(".chat-context-stale")).to_have_count(0)
    page.locator("#chat-send-btn").click()
    expect(page.locator(".chat-msg-assistant")).to_contain_text("The claim is undecided")
    page.get_by_role("button", name="Edit and fork with current scenario", exact=True).click()
    expect(page.locator(".chat-context-stale")).to_have_count(1)
    page.get_by_role("button", name="Refresh rule r1 for the current scenario").click()
    expect(page.locator(".chat-context-stale")).to_have_count(0)
    page.evaluate("() => { for (let i = 0; i < 24; i++) addQuestionDraft('Extra context', 'rule', `extra-${i}`); }")
    expect(page.locator(".chat-context-chip")).to_have_count(24)
    expect(page.locator("#global-status")).to_contain_text("up to 24 context items")
    assert len(runtime["chat_requests"]) == 1


def test_saved_context_uses_compact_state_signatures_without_losing_reload_identity(explorer_browser):
    from playwright.sync_api import expect

    page, _ = explorer_browser
    page.locator('[data-context-kind="rule"][data-context-id="r1"]').click()
    page.locator('[data-context-kind="rule"][data-context-id="r2"]').click()
    page.evaluate("() => flushConversationWrites()")
    saved = page.evaluate("() => conversationHistory.list('researcher-a')")
    refs = saved["records"][0]["record"]["context_refs"]
    assert len(refs) == 2
    assert refs[0]["scenario_signature"] == refs[1]["scenario_signature"]
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", refs[0]["scenario_signature"])
    page.reload()
    _wait_for_history(page)
    page.evaluate("() => currentScenarioSignature().promise")
    expect(page.locator(".chat-context-chip")).to_have_count(2)
    expect(page.locator(".chat-context-stale")).to_have_count(0)


def test_evidence_roles_cost_notice_and_announcements_do_not_conflate_assurance(explorer_browser):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    runtime["response"]["billing_uncertain"] = True
    runtime["response"]["evidence"] = [
        {"kind": "source", "source": "record.txt", "quote": "Quotation", "start": 0, "end": 9, "verified": True, "evidence_role": "quotation"},
        {"kind": "source", "source": "record.txt", "quote": "Context", "start": 9, "end": 16, "verified": True, "evidence_role": "context"},
        {"kind": "source", "source": "record.txt", "quote": "Legacy", "start": 16, "end": 22, "verified": True},
    ]
    page.locator("#chat-input").fill("Inspect the evidence")
    page.locator("#chat-send-btn").click()
    expect(page.locator("#chat-messages")).to_contain_text("Cost conservatively assessed")
    page.locator(".chat-evidence summary").click()
    expect(page.locator(".chat-evidence")).to_contain_text("Quotation matched")
    expect(page.locator(".chat-evidence")).to_contain_text("Suggested reading context")
    expect(page.locator(".chat-evidence")).to_contain_text("Supplied source excerpt")
    page.evaluate("""() => {
        window.__announcementChanges = 0;
        new MutationObserver(() => window.__announcementChanges++).observe(
            document.querySelector('#chat-announcement'), {childList:true,subtree:true});
        renderChat(); renderAll(); renderChat();
    }""")
    assert page.evaluate("window.__announcementChanges") == 0
    assert page.locator("#chat-messages").get_attribute("aria-live") is None


def test_changed_label_cue_survives_reduced_motion_and_unrelated_render(explorer_browser):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    updated = deepcopy(runtime["bundle"]["scenario"])
    updated["rules"]["objection"]["active"] = False
    bundle = compute_state_bundle(scenario_from_dict(updated))
    page.evaluate("bundle => { setBundle(bundle, {pulseLabels:true}); indexBundle(); renderAll(); }", bundle)
    card = page.locator('[data-element-kind="conclusion"][data-element-id="c"]')
    expect(card).to_contain_text("Status changed")
    page.wait_for_timeout(1000)
    page.evaluate("renderAll()")
    expect(card).to_contain_text("Status changed")


def test_explain_uses_actual_derivation_attacks_instead_of_sibling_edges(explorer_browser):
    from playwright.sync_api import expect

    page, _ = explorer_browser
    scenario = {
        "title": "Different branches of one top rule", "facts": {"f": {"description": "A verified record"}},
        "propositions": {"p": {"description": "A premise"}}, "conclusions": {"c": {"description": "The conclusion"}},
        "rules": {
            "ra": {"type": "defeasible", "premises": ["f"], "conclusion": "p"},
            "rb": {"type": "strict", "premises": ["f"], "conclusion": "p"},
            "top": {"type": "strict", "premises": ["p"], "conclusion": "c"},
            "attack": {"type": "defeasible", "premises": ["f"], "conclusion": "-ra"},
            "defense": {"type": "strict", "premises": ["f"], "conclusion": "ra"},
        },
    }
    bundle = compute_state_bundle(scenario_from_dict(scenario))
    roots = [arg for arg in bundle["af"]["arguments"] if arg["conclusion"] == "c"]
    unattacked = next(arg for arg in roots if "rb" in arg["rules_used"])
    attacked = next(arg for arg in roots if "ra" in arg["rules_used"])
    attacker = next(arg for arg in bundle["af"]["arguments"] if arg["top_rule"] == "attack")
    assert {edge["to"] for edge in bundle["af"]["attacks"] if edge["from"] == attacker["id"]} >= {attacked["id"]}
    assert not any(edge["to"] == unattacked["id"] for edge in bundle["af"]["attacks"])
    page.evaluate("bundle => { setBundle(bundle); indexBundle(); renderAll(); openExplainModal('c'); }", bundle)
    expect(page.locator(".game-picker-card")).to_have_count(2)
    page.locator(f'.game-picker-card[data-arg-id="{unattacked["id"]}"]').click()
    assert page.evaluate("getGameCBs(gameNodes[gameRootId])") == []
    page.evaluate("openExplainModal('c')")
    page.locator(f'.game-picker-card[data-arg-id="{attacked["id"]}"]').click()
    page.locator(f'[data-move="cb"][data-arg="{attacker["id"]}"]').click()
    expect(page.locator(".game-attack-info")).to_contain_text("undercuts rule [ra]")


@pytest.mark.parametrize("example", ["fire_prevention", "fried_chicken_v1", "fried_chicken_v2", "medical_ppi", "nba_rebuild", "popov_v_hayashi"])
def test_inspector_initial_literal_is_correct_for_every_bundled_example(explorer_browser, example):
    from playwright.sync_api import expect

    page, _ = explorer_browser
    bundle = compute_state_bundle(load_scenario(STATIC.parents[1] / "examples" / example / "scenario.yaml"))
    page.evaluate("bundle => { setBundle(bundle); indexBundle(); renderAll(); }", bundle)
    for literal in bundle["scenario"]["conclusions"]:
        matches = [arg for arg in bundle["af"]["arguments"] if arg["conclusion"] == literal]
        page.evaluate("literal => openDerivationForConclusion(literal)", literal)
        if matches:
            selected = page.locator("#derivation-argument-select").input_value()
            assert selected in {arg["id"] for arg in matches}
            expect(page.locator(".derivation-summary code")).to_have_text(literal)
        else:
            expect(page.locator("#derivation-argument-select")).to_have_value("")
            expect(page.locator("#derivation-body")).to_contain_text("No derivation uses this element")
        page.keyboard.press("Escape")


def test_proposal_preview_exposes_changed_metadata_and_unavailable_review(explorer_browser):
    from playwright.sync_api import expect

    page, _ = explorer_browser
    page.evaluate("""() => {
        const rule = state.bundle.scenario.rules.top;
        rule.active = false; rule.block = 2; rule.source = 'Old memo';
        rule.negated_description = 'Old negation';
        openEditModal('modify-rule', 'top');
        const replacement = {...rule, active:true, block:1, negated_description:'New negation'};
        delete replacement.source;
        _renderProposal({ op: {op: 'modify-rule', id:'top', rule: replacement},
            reviewed:false, review_issues:[{severity:'warning',message:'The advisory review was unavailable.'}] });
    }""")
    preview = page.locator("#edit-preview")
    expect(preview).to_contain_text("Status: Inactive → Active")
    expect(preview).to_contain_text("Preference block: 2 → 1")
    expect(preview).to_contain_text("Source: Old memo → None")
    expect(preview).to_contain_text("Negated description: Old negation → New negation")
    expect(preview).to_contain_text("Advisory review unavailable")


@pytest.mark.parametrize("billing_uncertain", [False, True])
def test_total_failures_show_only_confirmed_conservative_assessments(explorer_browser, billing_uncertain):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    detail = {"code": "llm_unavailable", "message": "Both model routes failed"}
    if billing_uncertain:
        detail["billing_uncertain"] = True
    runtime["chat_status"] = 503
    runtime["chat_error"] = {"detail": detail}
    runtime["propose_error"] = {"detail": detail}
    page.locator("#chat-input").fill("Keep this question after an outage")
    page.locator("#chat-send-btn").click()
    expect(page.locator("#chat-degraded-note")).to_be_visible()
    expect(page.locator("#chat-input")).to_have_value("Keep this question after an outage")
    chat = page.locator(".chat-msg-assistant")
    if billing_uncertain:
        expect(chat).to_contain_text("Cost conservatively assessed")
        expect(page.locator("#chat-announcement")).to_contain_text("Cost conservatively assessed")
    else:
        expect(chat).not_to_contain_text("Cost conservatively assessed")
    assert "$" not in chat.inner_text()
    page.evaluate("openEditModal('modify-rule', 'top')")
    instruction = "Keep this edit instruction after an outage"
    page.locator("#edit-instruction").fill(instruction)
    page.locator('[data-edit-action="propose"]').click()
    expect(page.locator("#edit-status")).to_contain_text("Both model routes failed")
    if billing_uncertain:
        expect(page.locator("#edit-status")).to_contain_text("Cost conservatively assessed")
    else:
        expect(page.locator("#edit-status")).not_to_contain_text("Cost conservatively assessed")
    expect(page.locator("#edit-instruction")).to_have_value(instruction)
    assert page.evaluate("editState.lastProposal") is None
    expect(page.locator("#edit-preview")).to_be_empty()
    assert "$" not in page.locator("#edit-status").inner_text()
