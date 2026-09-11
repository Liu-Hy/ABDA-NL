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


def _draft_text(page):
    return page.evaluate("chatComposer.snapshot().text")


def _expect_draft(page, text):
    page.wait_for_function("text => chatComposer.snapshot().text === text", arg=text)


def _conversation_action(page, action):
    if not page.locator(".conversation-actions").evaluate("menu => menu.open"):
        page.locator(".conversation-actions > summary").click()
    page.locator(f"#{action}").click()


def _expand_sources(page):
    if not page.locator(".chat-evidence").evaluate("details => details.open"):
        page.locator(".chat-evidence > summary").click()


def _capture_exploration(page, tmp_path, name, *, full_page=True):
    directory = Path(os.getenv("ABDA_BROWSER_ARTIFACT_DIR", str(tmp_path)))
    directory.mkdir(parents=True, exist_ok=True)
    engine = os.getenv("ABDA_BROWSER_ENGINE", "chromium")
    page.screenshot(path=str(directory / f"{engine}-{name}.png"), full_page=full_page)


def _rewrite_prose_keep_references(page, text):
    # Select and delete only prose nodes through the real keyboard path.
    while page.locator("#chat-input").evaluate("input => [...input.childNodes].some(node => node.nodeType === 3 && node.length)"):
        page.locator("#chat-input").evaluate("""input => {
          const node=[...input.childNodes].filter(node=>node.nodeType===3 && node.length).at(-1);
          const range=document.createRange(); range.selectNodeContents(node);
          const selected=window.getSelection(); selected.removeAllRanges(); selected.addRange(range);
          input.focus();
        }""")
        page.keyboard.press("Backspace")
    page.locator("#chat-input").evaluate("""input => {
      const range=document.createRange(); range.setStart(input,0); range.collapse(true);
      const selected=window.getSelection(); selected.removeAllRanges(); selected.addRange(range); input.focus();
    }""")
    page.keyboard.insert_text(text + "\n")
    page.locator("#chat-input").evaluate("""input => {
      const token=input.querySelector('.chat-reference-token'); const range=document.createRange(); range.setStartAfter(token); range.collapse(true);
      const selected=window.getSelection(); selected.removeAllRanges(); selected.addRange(range); input.focus();
    }""")
    page.keyboard.insert_text("\n")


def test_question_insertion_preserves_draft_and_requires_explicit_submit(explorer_browser, tmp_path):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    draft = page.locator("#chat-input")
    draft.fill("Compare these positions carefully.")
    draft.evaluate("""input => { const range=document.createRange(); range.setStart(input.firstChild,8); range.setEnd(input.firstChild,13); const selection=window.getSelection(); selection.removeAllRanges(); selection.addRange(range); }""")
    first = page.locator('[data-context-kind="rule"][data-context-id="r1"]')
    second = page.locator('[data-context-kind="rule"][data-context-id="r2"]')
    desc = first.get_attribute("data-desc")
    first.click()
    assert draft.evaluate("() => chatComposer.snapshot().text") == 'Compare "' + desc + '" these positions carefully.'
    second.focus()
    second.press("Enter")
    expect(page.locator(".chat-reference-token")).to_have_count(2)
    assert "these positions carefully." in draft.evaluate("() => chatComposer.snapshot().text")
    assert runtime["chat_requests"] == []
    assert "/api/scenarios/export" not in runtime["requests"]
    expect(page.locator(".chat-msg-user")).to_have_count(0)
    second_desc = second.get_attribute("data-desc")
    _rewrite_prose_keep_references(page, "How do the two selected rules differ?")
    _capture_exploration(page, tmp_path, "chat-inline-reference-composer")
    page.locator("#chat-send-btn").click()
    expect(page.locator(".chat-msg-assistant")).to_contain_text("The claim is undecided")
    assert len(runtime["chat_requests"]) == 1
    sent = runtime["chat_requests"][0]
    assert sent["messages"][-1]["content"] == f'How do the two selected rules differ?\n"{desc}"\n"{second_desc}"'
    assert sent["context_refs"] == [{"kind": "rule", "id": "r1"}, {"kind": "rule", "id": "r2"}]
    expect(page.locator(".chat-reference-token")).to_have_count(0)
    _expand_sources(page)
    expect(page.locator(".chat-evidence")).to_contain_text("Complete source text.")
    expect(page.locator(".chat-evidence")).not_to_contain_text("UNVERIFIED")
    _capture_exploration(page, tmp_path, "chat-saved-references-and-evidence")
    expect(page.locator(".chat-formal-context")).to_have_count(0)
    page.locator(".chat-msg-user").get_by_role("button", name=re.compile("^Inspect rule r1:")).click()
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
    page.locator('[data-context-id="r1"]').click()
    next_draft = _draft_text(page)
    focused_reference = page.locator('#chat-input .chat-reference-label').nth(1)
    focused_reference.focus()
    expect(page.locator("#chat-send-btn")).to_be_disabled()
    page.wait_for_timeout(50)
    assert len(runtime["held"]) == 1
    runtime["held"].pop().fulfill(status=200, content_type="application/json", body=json.dumps(runtime["response"]))
    expect(page.locator(".chat-msg-loading")).to_have_count(0)
    assert _draft_text(page) == next_draft
    expect(focused_reference).to_be_focused()
    expect(page.locator(".chat-reference-token")).to_have_count(2)
    focused_reference.press('Enter')
    expect(page.locator(".chat-reference-token")).to_have_count(1)
    assert _draft_text(page) == next_draft
    assert len(runtime["chat_requests"]) == 1



def test_stop_aborts_http_request_and_preserves_the_question(explorer_browser):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    expect(page.locator('#chat-panel-title')).to_have_text('Chat & Explore')
    expect(page.locator('.scenario-suggestions')).to_have_count(0)
    context_button = page.locator('[data-context-kind="rule"][data-context-id="r1"]')
    expect(context_button.locator('svg.ai-context-icon')).to_have_count(1)
    assert context_button.text_content() == ''
    context_button.click()
    original = page.evaluate('chatComposer.snapshot()')
    assert original['text'] == '"' + context_button.get_attribute('data-desc') + '"'
    runtime['hold_chat'] = True
    page.evaluate('''() => {
        const original = apiPostChat;
        apiPostChat = (...args) => { window.__chatSignal = args[3]; return original(...args); };
    }''')
    with page.expect_request('**/chat'):
        page.locator('#chat-send-btn').click()
    expect(page.locator('#chat-cancel-btn')).to_be_visible()
    expect(page.locator('#chat-send-btn')).to_be_hidden()
    page.locator('#chat-cancel-btn').focus()
    page.locator('#chat-cancel-btn').press('Enter')
    assert page.evaluate('window.__chatSignal.aborted') is True
    expect(page.locator('#chat-cancel-btn')).to_be_hidden()
    expect(page.locator('#chat-send-btn')).to_be_visible()
    expect(page.locator('#chat-send-btn')).to_be_enabled()
    expect(page.locator('#chat-input')).to_be_focused()
    expect(page.locator('.chat-msg-loading')).to_have_count(0)
    expect(page.locator('#chat-messages')).to_contain_text('Answer stopped')
    expect(page.locator('#chat-degraded-note')).to_be_hidden()
    assert page.evaluate('chatComposer.snapshot()') == original
    assert page.evaluate('chatRequests.size') == 0
    # Delivering the server response after the browser abort cannot revive it.
    runtime['held'].pop().fulfill(status=200, content_type='application/json', body=json.dumps(runtime['response']))
    page.evaluate('() => flushConversationWrites()')
    expect(page.locator('#chat-messages')).not_to_contain_text('The claim is undecided')
    page.reload()
    _wait_for_history(page)
    _expect_draft(page, original['text'])
    expect(page.locator('#chat-messages')).to_contain_text('Answer stopped')
    expect(page.locator('.chat-msg-loading')).to_have_count(0)
    assert len(runtime['chat_requests']) == 1


def test_stopped_late_answer_cannot_replace_new_draft_or_finish_new_request(explorer_browser):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    page.evaluate('''() => {
        window.__chatCalls = [];
        apiPostChat = (...args) => new Promise(resolve => {
            window.__chatCalls.push({resolve, signal: args[3]});
        });
    }''')
    page.locator('#chat-input').fill('First question')
    page.locator('#chat-send-btn').click()
    page.wait_for_function('window.__chatCalls.length === 1')
    page.locator('#chat-input').fill('A newer question')
    page.locator('#chat-cancel-btn').click()
    _expect_draft(page, 'A newer question')
    page.locator('#chat-send-btn').click()
    page.wait_for_function('window.__chatCalls.length === 2')
    page.evaluate('''response => window.__chatCalls[0].resolve({...response, message: 'Obsolete late response'})''', runtime['response'])
    expect(page.locator('.chat-msg-loading')).to_be_visible()
    expect(page.locator('#chat-cancel-btn')).to_be_visible()
    expect(page.locator('#chat-messages')).not_to_contain_text('Obsolete late response')
    assert page.evaluate('window.__chatCalls[0].signal.aborted') is True
    assert page.evaluate('window.__chatCalls[1].signal.aborted') is False
    page.evaluate('''response => window.__chatCalls[1].resolve({...response, message: 'Current response'})''', runtime['response'])
    expect(page.locator('#chat-messages')).to_contain_text('Current response')
    expect(page.locator('.chat-msg-loading')).to_have_count(0)
    assert [message['content'] for message in page.evaluate('state.chatMessages') if message['role'] == 'user'] == [
        'First question', 'A newer question',
    ]
    page.evaluate('() => flushConversationWrites()')
    page.reload()
    expect(page.locator('#chat-messages')).to_contain_text('Current response')
    expect(page.locator('#chat-messages')).not_to_contain_text('Obsolete late response')
    assert runtime['chat_requests'] == []


def test_stop_during_scenario_capture_sends_no_model_request(explorer_browser):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    page.evaluate('''() => {
        const original = captureConversationSnapshot;
        captureConversationSnapshot = async (...args) => {
            const snapshot = await original(...args);
            return new Promise(resolve => { window.__finishSnapshot = () => resolve(snapshot); });
        };
    }''')
    page.locator('#chat-input').fill('Keep this unsent question')
    page.locator('#chat-send-btn').click()
    page.wait_for_function('typeof window.__finishSnapshot === "function"')
    page.locator('#chat-cancel-btn').click()
    page.evaluate('window.__finishSnapshot()')
    expect(page.locator('#chat-send-btn')).to_be_enabled()
    expect(page.locator('.chat-msg-user')).to_have_count(0)
    expect(page.locator('.chat-msg-loading')).to_have_count(0)
    _expect_draft(page, 'Keep this unsent question')
    assert runtime['chat_requests'] == []
    assert page.evaluate('chatRequests.size') == 0


@pytest.mark.parametrize("project", [False, True])
def test_proposal_cancel_aborts_the_http_request_without_changing_the_scenario(explorer_browser, project):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    held = []
    page.route("**/propose", lambda route: held.append(route))
    page.evaluate("""project => {
        if (project) state.activeProject = {id: 'project-a', version: 7};
        const original = window.fetch;
        window.fetch = (path, options) => {
            if (String(path).endsWith('/propose')) window.__proposalSignal = options.signal;
            return original(path, options);
        };
        openEditModal('add-fact');
    }""", project)
    page.locator("#edit-instruction").fill("Add a new fact after my review")
    path = "/api/projects/project-a/propose" if project else "/propose"
    with page.expect_request(lambda request: urlsplit(request.url).path == path):
        page.locator('[data-edit-action="propose"]').click()
    expect(page.locator("#edit-status")).to_contain_text("Proposing")
    with page.expect_event("requestfailed", predicate=lambda request: urlsplit(request.url).path == path, timeout=5000):
        page.locator('[data-edit-action="cancel"]').click()
    assert page.evaluate("window.__proposalSignal.aborted") is True
    assert page.evaluate("activeProposalRequest") is None
    assert page.evaluate("editState.inFlight") is False
    expect(page.locator("#modal-edit")).to_be_hidden()
    assert len(held) == 1
    payload = held[0].request.post_data_json
    assert payload.get("expected_version" if project else "scenario_id") == (7 if project else "test")
    held.pop().fulfill(status=200, content_type="application/json", body=json.dumps(_proposal_response("Obsolete proposal")))
    page.evaluate("openEditModal('add-fact')")
    expect(page.locator("#edit-status")).to_be_empty()
    expect(page.locator("#edit-preview")).to_be_empty()
    expect(page.locator('[data-edit-action="propose"]')).to_be_enabled()
    assert page.evaluate("state.diff_ops") == []
    assert runtime["chat_requests"] == []


def _proposal_response(description="Current proposed fact", billing_source="trial"):
    return {"op": {"op": "add-fact", "id": "new_fact", "fact": {"description": description}},
            "reviewed": True, "review_issues": [], "latency_ms": 1, "proposer_attempts": 1,
            "billing_source": billing_source}


def _hold_proposals_ignoring_abort(page):
    # Keep responses independently resolvable, including a transport that ignores abort.
    page.evaluate("""() => {
        window.__proposalCalls = [];
        window.__proposalRefreshes = [];
        const original = window.fetch;
        window.fetch = (path, options) => String(path).endsWith('/propose')
            ? new Promise((resolve, reject) => window.__proposalCalls.push({resolve, reject, signal: options.signal}))
            : original(path, options);
        refreshTrialBalanceQuietly = () => window.__proposalRefreshes.push(state.authSession.user?.id);
    }""")


@pytest.mark.parametrize(("close_action", "late_outcome"), [
    ("cancel", "success"), ("close", "http-error"), ("escape", "network-error"), ("reopen", "success"),
])
def test_cancelled_proposal_cannot_replace_or_finish_a_new_request(explorer_browser, close_action, late_outcome):
    from playwright.sync_api import expect

    page, _ = explorer_browser
    _hold_proposals_ignoring_abort(page)
    page.evaluate("""() => {
        state.llmAccess.mode = 'byok'; state.llmAccess.apiKey = 'test-only-key';
        openEditModal('add-fact');
    }""")
    page.locator("#edit-instruction").fill("Old proposal instruction")
    page.locator('[data-edit-action="propose"]').click()
    page.wait_for_function("window.__proposalCalls.length === 1")
    if close_action == "cancel":
        page.locator('[data-edit-action="cancel"]').click()
    elif close_action == "close":
        page.locator("#modal-edit .modal-close").click()
    elif close_action == "escape":
        page.keyboard.press("Escape")
    page.evaluate("openEditModal('add-fact')")
    page.locator("#edit-instruction").fill("New proposal instruction")
    page.locator('[data-edit-action="propose"]').click()
    page.wait_for_function("window.__proposalCalls.length === 2")
    assert page.evaluate("window.__proposalCalls[0].signal.aborted") is True
    assert page.evaluate("window.__proposalCalls[1].signal.aborted") is False
    page.evaluate("""({outcome, body}) => {
        const old = window.__proposalCalls[0];
        if (outcome === 'network-error') old.reject(new Error('Obsolete network error'));
        else old.resolve(new Response(JSON.stringify(outcome === 'success' ? body :
            {detail: {code: 'llm_unavailable', message: 'Obsolete provider error'}}),
            {status: outcome === 'success' ? 200 : 503}));
    }""", {"outcome": late_outcome, "body": _proposal_response("Obsolete proposal", "byok")})
    expect(page.locator("#edit-status")).to_contain_text("Proposing")
    expect(page.locator("#edit-status")).not_to_contain_text("Obsolete")
    expect(page.locator("#edit-preview")).to_be_empty()
    expect(page.locator("#edit-instruction")).to_have_value("New proposal instruction")
    expect(page.locator('[data-edit-action="propose"]')).to_be_disabled()
    assert page.evaluate("activeProposalRequest.controller.signal === window.__proposalCalls[1].signal") is True
    page.evaluate("body => window.__proposalCalls[1].resolve(new Response(JSON.stringify(body)))",
                  _proposal_response(billing_source="byok"))
    expect(page.locator("#edit-preview")).to_contain_text("Current proposed fact")
    expect(page.locator('[data-edit-action="apply"]')).to_be_enabled()
    assert page.evaluate("activeProposalRequest") is None
    assert page.evaluate("window.__proposalRefreshes") == []
    assert page.evaluate("state.diff_ops") == []


@pytest.mark.parametrize("return_to_original_account", [False, True])
def test_proposal_cancellation_and_balance_refresh_stay_with_the_original_account(explorer_browser, return_to_original_account):
    from playwright.sync_api import expect

    page, _ = explorer_browser
    _hold_proposals_ignoring_abort(page)
    page.evaluate("""() => {
        window.__delayedProposalRefreshes = [];
        const original = window.setTimeout;
        window.setTimeout = (callback, delay, ...args) => delay === 1500
            ? window.__delayedProposalRefreshes.push(() => callback(...args))
            : original(callback, delay, ...args);
        openEditModal('add-fact');
    }""")
    page.locator("#edit-instruction").fill("Old account instruction")
    page.locator('[data-edit-action="propose"]').click()
    page.wait_for_function("window.__proposalCalls.length === 1")
    page.evaluate("""() => {
        state.authSession.user = {id: 'researcher-b', email: 'other@example.edu'};
        renderAccountUI();
    }""")
    _wait_for_history(page, "researcher-b")
    expect(page.locator("#modal-edit")).to_be_hidden()
    assert page.evaluate("window.__proposalCalls[0].signal.aborted") is True
    current_account = "researcher-b"
    if return_to_original_account:
        page.evaluate("""() => {
            state.authSession.user = {id: 'researcher-a', email: 'test@example.edu'};
            renderAccountUI();
        }""")
        current_account = "researcher-a"
        _wait_for_history(page, current_account)
    page.evaluate("openEditModal('add-fact')")
    page.locator("#edit-instruction").fill("Current account instruction")
    page.locator('[data-edit-action="propose"]').click()
    page.wait_for_function("window.__proposalCalls.length === 2")
    page.evaluate("""body => {
        window.__proposalCalls[0].resolve(new Response(JSON.stringify(body)));
        window.__delayedProposalRefreshes.forEach(callback => callback());
    }""", _proposal_response("Previous account proposal"))
    expect(page.locator("#edit-status")).to_contain_text("Proposing")
    expect(page.locator("#edit-preview")).to_be_empty()
    expect(page.locator("#edit-instruction")).to_have_value("Current account instruction")
    expect(page.locator('[data-edit-action="propose"]')).to_be_disabled()
    assert page.evaluate("window.__proposalRefreshes") == []
    assert page.evaluate("window.__proposalCalls[1].signal.aborted") is False
    page.evaluate("body => window.__proposalCalls[1].resolve(new Response(JSON.stringify(body)))", _proposal_response())
    expect(page.locator("#edit-preview")).to_contain_text("Current proposed fact")
    assert page.evaluate("window.__proposalRefreshes") == [current_account]
    assert page.evaluate("activeProposalRequest") is None
    assert page.evaluate("state.diff_ops") == []


def _project_summary(project_id, name, *, archived=True, version=2):
    return {"id": project_id, "name": name, "description": "", "version": version,
            "archived_at": "2026-09-11T00:00:00Z" if archived else None,
            "created_at": "2026-09-10T00:00:00Z", "updated_at": "2026-09-11T00:00:00Z",
            "source_scenario_id": "test", "submissions": [], "active_share_count": 0}


def _mock_project_deletion_api(page, runtime):
    runtime.update({"private_active": [_project_summary("active", "Active project", archived=False)],
                    "private_archived": [_project_summary("archive-a", "First archived project"),
                                         _project_summary("archive-b", "Second archived project")],
                    "project_deletions": [], "project_delete_held": [], "hold_project_delete": False})

    def handle(route):
        request = route.request
        url = urlsplit(request.url)
        if url.path == "/api/projects/archived/delete":
            targets = request.post_data_json["projects"]
            runtime["project_deletions"].append(targets)
            if runtime["hold_project_delete"]:
                runtime["project_delete_held"].append(route)
                return
            if runtime.get("project_delete_conflict"):
                route.fulfill(status=409, content_type="application/json", body=json.dumps(
                    {"detail": {"code": "project_version_conflict", "message": "The project changed."}}))
                return
            deleted = {project["id"] for project in targets}
            runtime["private_archived"] = [project for project in runtime["private_archived"] if project["id"] not in deleted]
            payload = {"deleted_ids": sorted(deleted), "deleted_count": len(deleted)}
        else:
            assert url.path == "/api/projects"
            payload = {"projects": runtime["private_archived"] if url.query == "archived=true" else runtime["private_active"]}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

    page.route("**/api/projects**", handle)


def _open_archived_projects(page):
    from playwright.sync_api import expect

    page.evaluate("openWorkspace('projects')")
    page.locator("#projects-archived-filter").click()
    expect(page.locator("#projects-archived-filter")).to_have_attribute("aria-pressed", "true")


def test_archived_deletion_keyboard_narrow_confirmation_and_exact_displayed_targets(explorer_browser, tmp_path):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    _mock_project_deletion_api(page, runtime)
    page.set_viewport_size({"width": 390, "height": 844})
    _open_archived_projects(page)
    expect(page.locator("#project-list .project-card")).to_have_count(2)
    first_checkbox = page.get_by_role("checkbox", name="Select First archived project for deletion")
    first_delete = page.locator("#projects-delete-selected")
    expect(first_delete).to_be_disabled()
    first_checkbox.focus()
    first_checkbox.press("Space")
    expect(first_checkbox).to_be_checked()
    expect(page.locator("#projects-selected-count")).to_have_text("1 selected")
    messages = []
    page.once("dialog", lambda dialog: (messages.append(dialog.message), dialog.dismiss()))
    first_delete.focus()
    first_delete.press("Enter")
    assert runtime["project_deletions"] == []
    assert 'First archived project' in messages[0] and 'cannot be undone' in messages[0]
    assert 'Submitted and published scenario snapshots will remain' in messages[0]
    _capture_exploration(page, tmp_path, "archived-project-deletion-390")
    assert page.locator("#workspace-panel-projects").evaluate("panel => panel.scrollWidth <= panel.clientWidth")
    page.once("dialog", lambda dialog: dialog.accept())
    first_delete.press("Space")
    expect(page.locator("#projects-status")).to_contain_text('Permanently deleted "First archived project"')
    expect(page.locator("#project-list .project-card")).to_have_count(1)
    assert runtime["project_deletions"] == [[{"id": "archive-a", "expected_version": 2}]]

    def confirm_batch(dialog):
        messages.append(dialog.message)
        # Another tab archives a project while this confirmation is displayed.
        runtime["private_archived"].append(_project_summary("new-archive", "Newly archived elsewhere"))
        dialog.accept()

    page.once("dialog", confirm_batch)
    page.locator("#projects-delete-all").focus()
    page.locator("#projects-delete-all").press("Enter")
    expect(page.locator("#projects-status")).to_contain_text("Permanently deleted 1 archived scenario")
    expect(page.locator("#project-list")).to_contain_text("Newly archived elsewhere")
    assert "all 1 currently listed archived private scenario" in messages[-1]
    assert "Scenarios archived later are not included" in messages[-1]
    assert runtime["project_deletions"][-1] == [{"id": "archive-b", "expected_version": 2}]
    assert [project["id"] for project in runtime["private_active"]] == ["active"]
    assert page.evaluate("state.diff_ops") == []
    page.locator("#projects-active-filter").click()
    expect(page.locator("#project-list")).to_contain_text("Active project")
    expect(page.locator("#projects-delete-all")).to_be_hidden()
    expect(page.locator('[data-project-select]')).to_have_count(0)


def test_bulk_project_deletion_conflict_refreshes_without_retry_or_partial_success(explorer_browser):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    _mock_project_deletion_api(page, runtime)
    _open_archived_projects(page)
    expect(page.locator("#project-list .project-card")).to_have_count(2)

    def restore_elsewhere(dialog):
        restored = runtime["private_archived"].pop()
        restored["archived_at"] = None
        restored["version"] += 1
        runtime["private_active"].append(restored)
        runtime["project_delete_conflict"] = True
        dialog.accept()

    page.once("dialog", restore_elsewhere)
    page.locator("#projects-delete-all").click()
    expect(page.locator("#projects-status")).to_contain_text("Nothing was deleted")
    expect(page.locator("#projects-status")).to_contain_text("Review the refreshed list")
    expect(page.locator("#project-list")).to_contain_text("First archived project")
    expect(page.locator("#project-list")).not_to_contain_text("Second archived project")
    expect(page.locator("#projects-delete-all")).to_be_enabled()
    assert len(runtime["project_deletions"]) == 1
    assert [project["id"] for project in runtime["private_archived"]] == ["archive-a"]
    page.locator("#projects-active-filter").click()
    expect(page.locator("#project-list")).to_contain_text("Second archived project")


def test_archived_selection_supports_multiple_items_and_discards_changed_versions(explorer_browser):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    _mock_project_deletion_api(page, runtime)
    runtime["private_archived"].append(_project_summary("archive-c", "Third archived project"))
    _open_archived_projects(page)
    first = page.locator('[data-project-select="archive-a"]')
    second = page.locator('[data-project-select="archive-b"]')
    first.check()
    second.check()
    expect(page.locator("#projects-selected-count")).to_have_text("2 selected")
    # A background refresh cannot silently extend consent to a newer version.
    runtime["private_archived"][0]["version"] = 4
    page.locator("#projects-refresh-btn").click()
    expect(first).not_to_be_checked()
    expect(second).to_be_checked()
    expect(page.locator("#projects-selected-count")).to_have_text("1 selected")
    first.check()
    messages = []
    page.once("dialog", lambda dialog: (messages.append(dialog.message), dialog.accept()))
    page.locator("#projects-delete-selected").click()
    expect(page.locator("#projects-status")).to_contain_text("Permanently deleted 2 archived scenarios")
    assert "2 selected archived private scenarios" in messages[0]
    assert runtime["project_deletions"] == [[
        {"id": "archive-a", "expected_version": 4}, {"id": "archive-b", "expected_version": 2},
    ]]
    expect(page.locator("#project-list")).to_contain_text("Third archived project")
    expect(page.locator("#projects-selected-count")).to_have_text("0 selected")
    expect(page.locator("#projects-delete-selected")).to_be_disabled()
    page.locator('[data-project-select="archive-c"]').check()
    page.locator("#projects-active-filter").click()
    page.locator("#projects-archived-filter").click()
    expect(page.locator('[data-project-select="archive-c"]')).not_to_be_checked()


@pytest.mark.parametrize(("current_account", "old_status"), [("researcher-b", 200), ("researcher-a", 409)])
def test_late_project_deletion_cannot_change_a_new_accounts_pending_action(explorer_browser, current_account, old_status):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    _mock_project_deletion_api(page, runtime)
    runtime["hold_project_delete"] = True
    page.on("dialog", lambda dialog: dialog.accept())
    _open_archived_projects(page)
    expect(page.locator("#project-list .project-card")).to_have_count(2)
    page.locator("#projects-delete-all").click()
    expect(page.locator("#projects-delete-all")).to_be_disabled()
    page.evaluate("""() => {
        state.authSession.user = {id: 'researcher-b', email: 'other@example.edu'};
        renderAccountUI();
    }""")
    _wait_for_history(page, "researcher-b")
    expect(page.locator("#projects-status")).to_be_empty()
    if current_account == "researcher-a":
        page.evaluate("""() => {
            state.authSession.user = {id: 'researcher-a', email: 'test@example.edu'};
            renderAccountUI();
        }""")
        _wait_for_history(page, current_account)
    runtime["user"] = current_account
    runtime["private_archived"] = [_project_summary("current-archive", "Current account project")]
    _open_archived_projects(page)
    expect(page.locator("#project-list")).to_contain_text("Current account project")
    page.locator("#projects-delete-all").click()
    expect(page.locator("#projects-delete-all")).to_be_disabled()
    assert len(runtime["project_delete_held"]) == 2
    old = runtime["project_delete_held"].pop(0)
    old.fulfill(status=old_status, content_type="application/json", body=json.dumps(
        {"deleted_ids": ["archive-a", "archive-b"], "deleted_count": 2} if old_status == 200 else
        {"detail": {"code": "project_version_conflict", "message": "Old account conflict"}}))
    expect(page.locator("#projects-status")).to_have_text("Deleting archived scenarios...")
    expect(page.locator("#project-list")).to_contain_text("Current account project")
    expect(page.locator("#projects-delete-all")).to_be_disabled()
    assert page.evaluate("projectDeletionRequest.account") == current_account
    runtime["private_archived"] = []
    runtime["project_delete_held"].pop().fulfill(status=200, content_type="application/json", body=json.dumps(
        {"deleted_ids": ["current-archive"], "deleted_count": 1}))
    expect(page.locator("#projects-status")).to_contain_text("Permanently deleted 1 archived scenario")
    expect(page.locator("#project-list")).to_contain_text("No archived scenarios")
    expect(page.locator("#projects-delete-all")).to_be_disabled()
    assert page.evaluate("projectDeletionRequest") is None


def test_unsupported_legacy_archive_count_keeps_selected_delete_available(explorer_browser):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    _mock_project_deletion_api(page, runtime)
    runtime["private_archived"] = [_project_summary(f"legacy-{index}", f"Legacy project {index}") for index in range(501)]
    _open_archived_projects(page)
    expect(page.locator("#project-count")).to_have_text("501 scenarios")
    expect(page.locator("#projects-delete-all")).to_be_disabled()
    expect(page.locator("#projects-delete-limit")).to_be_visible()
    page.locator('[data-project-select]').first.check()
    expect(page.locator('#projects-delete-selected')).to_be_enabled()
    assert runtime["project_deletions"] == []


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
        _conversation_action(page, "conversation-export")
    exported = json.loads(Path(download_info.value.path()).read_text())
    raw = json.dumps(exported)
    assert "secret-provider-placeholder" not in raw and "secret-bearer-placeholder" not in raw
    record = exported["conversation"]
    expect(page.locator(".conversation-turn-controls summary")).to_have_count(0)
    expect(page.locator(".conversation-turn-controls")).not_to_contain_text("Snapshot")
    snapshot = record["snapshots"][record["messages"][0]["snapshot_id"]]
    assert snapshot["scenario"]["scenario"]["assumptions"]["a"]["active"] is False
    assert snapshot["scenario"]["scenario"]["sources"][0]["text"].startswith("Complete source text.")
    assert snapshot["pending_ops"] == [{"op": "set_assumption_active", "id": "a", "active": False}]
    assert compute_state_bundle(scenario_from_dict(snapshot["scenario"]["scenario"]))["af"] == snapshot["af"]
    page.reload()
    expect(page.locator("#chat-messages")).to_contain_text("Which conclusion changed?")
    _expect_draft(page, "Saved unfinished follow-up")
    page.get_by_role("button", name="Edit and fork", exact=True).click()
    _expect_draft(page, "Which conclusion changed?")
    expect(page.locator("#conversation-select option")).to_have_count(2)
    assert page.evaluate("activeConversation().fork_of.new_question_scenario") == "current"
    original_id = record["id"]
    page.locator("#conversation-select").select_option(original_id)
    _expect_draft(page, "Saved unfinished follow-up")
    runtime["user"] = "researcher-b"
    page.evaluate("""() => { state.authSession.user = {id: 'researcher-b', email: 'other@example.edu'}; renderAccountUI(); }""")
    expect(page.locator("#chat-messages")).not_to_contain_text("Which conclusion changed?")
    _expect_draft(page, "")
    page.locator("#chat-input").fill("Other account draft")
    page.evaluate("() => flushConversationWrites()")
    assert "Which conclusion changed?" not in json.dumps(page.evaluate("() => conversationHistory.list('researcher-b')"))
    page.evaluate("""() => { state.authSession = {authenticated: false, auth_mode: 'dev', user: null}; renderAccountUI(); }""")
    _expect_draft(page, "")
    expect(page.locator("#conversation-select")).to_have_attribute("title", re.compile("this tab while signed out"))
    page.locator('.conversation-actions > summary').click()
    expect(page.locator('#conversation-storage-description')).to_contain_text('this tab while signed out')


def _answer_chat_draft(page, runtime, answer, question=None):
    from playwright.sync_api import expect

    if question is not None:
        page.locator('#chat-input').fill(question)
    runtime['response']['message'] = answer
    page.locator('#chat-send-btn').click()
    expect(page.locator('.chat-msg-assistant:not(.chat-msg-loading)').last).to_contain_text(answer)
    expect(page.locator('.chat-msg-loading')).to_have_count(0)


@pytest.mark.parametrize('width', [1440, 390])
def test_retry_branches_exact_question_history_and_context_without_changing_the_current_view(explorer_browser, tmp_path, width):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    page.set_viewport_size({'width': width, 'height': 900})
    original_bundle = deepcopy(runtime['bundle'])
    _answer_chat_draft(page, runtime, 'Earlier answer to retain', 'Earlier question')
    page.evaluate("() => { activeConversation().messages.push({role: 'assistant', content: 'Local cancelled request notice', local_notice: true}); renderChat(); }")
    page.locator('#chat-input').fill('Please explain this exact rule.')
    page.locator('[data-context-kind="rule"][data-context-id="r1"]').click()
    _answer_chat_draft(page, runtime, 'Selected old answer to preserve')
    _answer_chat_draft(page, runtime, 'Later old answer to preserve', 'Later question')
    page.locator('#chat-input').fill('Keep my unfinished parent draft.')
    page.locator('[data-context-kind="rule"][data-context-id="r2"]').click()
    parent_draft = page.evaluate('chatComposer.snapshot()')
    parent = page.evaluate('activeConversation()')
    selected_index = 3
    selected = parent['messages'][selected_index]
    saved = parent['snapshots'][selected['snapshot_id']]
    assert saved['scenario_id'] == 'test'
    assert saved['source_scenario_id'] == 'test'
    assert saved['scenario']['scenario']['sources'][0]['text'].startswith('Complete source text.')

    current_bundle = deepcopy(original_bundle)
    current_bundle['scenario']['title'] = 'A different current scenario'
    current_bundle['scenario']['rules']['r1']['description'] = 'A different current rule description'
    page.evaluate('''bundle => {
        state.scenario_id = 'current-other'; state.activeProject = null;
        state.viewKind = 'example'; state.diff_ops = [];
        state.scenarios.push({id: 'current-other', title: bundle.scenario.title});
        setBundle(bundle); indexBundle(); renderAll();
        state.config.profiles.push({id: 'retry-model', label: 'Retry model'});
        state.llmAccess.profile = 'retry-model'; renderAccessSummary();
    }''', current_bundle)
    preflights = []

    def replay(route):
        payload = route.request.post_data_json
        preflights.append(payload)
        bundle = original_bundle if payload['scenario_id'] == 'test' else current_bundle
        route.fulfill(content_type='application/json', body=json.dumps(bundle))

    page.route('**/state', replay)
    controls = page.locator('.conversation-turn-controls')
    expect(controls).to_have_count(3)
    expect(page.locator('.chat-msg-assistant .conversation-turn-controls')).to_have_count(0)
    expect(controls.locator('summary')).to_have_count(0)
    for toolbar in controls.all():
        expect(toolbar.locator('button')).to_have_count(2)
        expect(toolbar).not_to_contain_text('Snapshot')
        for selector, label in [('.conversation-edit-turn', 'Edit and fork'), ('.conversation-retry-turn', 'Retry')]:
            button = toolbar.locator(selector)
            expect(button).to_have_accessible_name(label)
            expect(button).to_have_attribute('title', label)
            expect(button.locator('svg')).to_have_count(1)
            assert button.inner_text().strip() == ''
            box = button.bounding_box()
            assert box is not None and 24 <= box['width'] <= 40 and 24 <= box['height'] <= 40
    retry = controls.nth(1).get_by_role('button', name='Retry', exact=True)
    controls.nth(1).get_by_role('button', name='Edit and fork', exact=True).focus()
    page.keyboard.press('Tab')
    expect(retry).to_be_focused()
    _capture_exploration(page, tmp_path, f'compact-turn-actions-{width}')
    _capture_exploration(page, tmp_path, f'compact-turn-actions-{width}-viewport', full_page=False)
    runtime['response']['message'] = 'New retry answer'
    page.keyboard.press('Enter')
    expect(page.locator('.chat-msg-assistant').last).to_contain_text('New retry answer')
    assert len(runtime['chat_requests']) == 4
    request = runtime['chat_requests'][-1]
    assert request['scenario_id'] == 'test'
    assert request['diff_ops'] == saved['pending_ops']
    assert request['context_refs'] == selected['context_refs']
    assert request['llm'] == {'profile': 'retry-model'}
    assert request['messages'] == [
        {'role': message['role'], 'content': message['content']}
        for message in parent['messages'][:selected_index + 1] if not message.get('local_notice')
    ]
    assert preflights == [{'scenario_id': 'test', 'diff_ops': saved['pending_ops']}]
    branch = page.evaluate('activeConversation()')
    assert branch['id'] != parent['id']
    assert branch['messages'][-2]['content'] == selected['content']
    assert branch['messages'][-2]['context_refs'] == selected['context_refs']
    assert branch['snapshots'][branch['messages'][-2]['snapshot_id']]['scenario'] == saved['scenario']
    assert branch['messages'][-1]['earlier_state'] is True
    expect(page.locator('#chat-messages')).not_to_contain_text('Selected old answer to preserve')
    expect(page.locator('#chat-messages')).not_to_contain_text('Later old answer to preserve')
    assert page.evaluate('state.scenario_id') == 'current-other'
    assert page.evaluate('state.bundle.scenario') == current_bundle['scenario']
    preserved = page.evaluate('id => conversationStore.records.find(record => record.id === id)', parent['id'])
    assert preserved['messages'] == parent['messages']
    assert preserved['snapshots'] == parent['snapshots']
    page.locator('#conversation-select').select_option(parent['id'])
    assert page.evaluate('chatComposer.snapshot()') == parent_draft
    expect(page.locator('#chat-messages')).to_contain_text('Selected old answer to preserve')
    expect(page.locator('#chat-messages')).to_contain_text('Later old answer to preserve')


def test_retry_uses_the_saved_private_route_version_and_working_operations(explorer_browser):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    original_bundle = deepcopy(runtime['bundle'])
    original_bundle['scenario']['assumptions']['a']['active'] = False
    original_bundle = compute_state_bundle(scenario_from_dict(original_bundle['scenario']))
    runtime['bundle'] = original_bundle
    project = {'id': 'original-private', 'version': 7, 'source_scenario_id': None}
    ops = [{'op': 'set_assumption_active', 'id': 'a', 'active': False}]
    page.evaluate('''payload => {
        state.activeProject = payload.project; state.viewKind = 'project';
        state.diff_ops = payload.ops; setBundle(payload.bundle); indexBundle(); renderAll();
    }''', {'project': project, 'ops': ops, 'bundle': original_bundle})
    _answer_chat_draft(page, runtime, 'Original private answer', 'Question about the saved private working state')
    parent = page.evaluate('activeConversation()')
    page.locator('#chat-input').fill('Private draft to keep')
    page.evaluate('''() => {
        state.activeProject = {id: 'different-private', version: 20};
        state.diff_ops = []; state.bundle = structuredClone(state.bundle);
        state.bundle.scenario.title = 'Different private scenario'; renderAll();
    }''')
    preflights = []

    def replay(route):
        preflights.append({'path': urlsplit(route.request.url).path, 'body': route.request.post_data_json})
        route.fulfill(content_type='application/json', body=json.dumps(original_bundle))

    page.route('**/api/projects/original-private/state', replay)
    page.route('**/api/projects/original-private', lambda route: route.fulfill(
        content_type='application/json', body=json.dumps({**project, **original_bundle})))
    runtime['response']['message'] = 'Retried private answer'
    page.get_by_role('button', name='Retry', exact=True).click()
    expect(page.locator('.chat-msg-assistant').last).to_contain_text('Retried private answer')
    assert preflights == [{'path': '/api/projects/original-private/state',
                           'body': {'expected_version': 7, 'diff_ops': ops}}]
    assert runtime['requests'].count('/api/projects/original-private/chat') == 2
    assert '/api/projects/different-private/chat' not in runtime['requests']
    request = runtime['chat_requests'][-1]
    assert request['expected_version'] == 7 and request['diff_ops'] == ops
    assert request['messages'] == [{'role': 'user', 'content': parent['messages'][0]['content']}]
    assert page.evaluate('state.activeProject') == {'id': 'different-private', 'version': 20}
    assert page.evaluate('state.diff_ops') == []
    page.locator('#conversation-select').select_option(parent['id'])
    _expect_draft(page, 'Private draft to keep')
    expect(page.locator('#chat-messages')).to_contain_text('Original private answer')
    assert not any(path.endswith(('/import', '/review')) for path in runtime['requests'])


@pytest.mark.parametrize('failure', ['scenario-changed', 'source-changed', 'private-version', 'private-unavailable', 'snapshot-missing'])
def test_retry_blocks_unavailable_or_changed_original_context_before_inference(explorer_browser, failure):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    if failure.startswith('private-'):
        page.evaluate("() => { state.activeProject = {id: 'original-private', version: 7}; state.viewKind = 'project'; }")
    _answer_chat_draft(page, runtime, 'Answer to retain', 'Original question to retry')
    page.locator('#chat-input').fill('Do not replace this unsent draft')
    if failure == 'snapshot-missing':
        page.evaluate('() => { activeConversation().snapshots = {}; }')
    parent = page.evaluate('activeConversation()')
    original_count = page.locator('#conversation-select option').count()
    changed = deepcopy(runtime['bundle'])
    if failure == 'scenario-changed':
        changed['scenario']['rules']['r1']['description'] = 'The original rule changed'
    if failure == 'source-changed':
        changed['scenario']['sources'][0]['text'] += ' The source has been revised.'
    if failure.startswith('private-'):
        status = 409 if failure == 'private-version' else 404
        error = {'detail': {'code': 'project_version_conflict' if status == 409 else 'project_not_found',
                            'message': 'The original scenario is unavailable or changed'}}
        page.route('**/api/projects/original-private/state', lambda route: route.fulfill(
            status=status, content_type='application/json', body=json.dumps(error)))
        page.route('**/api/projects/original-private', lambda route: route.fulfill(
            status=status, content_type='application/json', body=json.dumps(error)))
    else:
        page.route('**/state', lambda route: route.fulfill(content_type='application/json', body=json.dumps(changed)))
    page.evaluate('() => retryConversationAt(0)')
    expect(page.locator('#global-status')).to_contain_text(re.compile('fork', re.I))
    assert len(runtime['chat_requests']) == 1
    assert page.evaluate('conversationStore.activeId') == parent['id']
    expect(page.locator('#conversation-select option')).to_have_count(original_count)
    assert page.evaluate('activeConversation().messages') == parent['messages']
    _expect_draft(page, 'Do not replace this unsent draft')
    expect(page.locator('.chat-msg-loading')).to_have_count(0)


@pytest.mark.parametrize('changed', [False, True])
def test_legacy_retry_compares_complete_snapshot_and_keeps_exact_words_without_segments(explorer_browser, changed):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    portable = export_scenario(runtime['bundle']['scenario'], None)
    snapshot = {'scenario': portable, 'af': runtime['bundle']['af'], 'pending_ops': [],
                'view_kind': 'example', 'project_id': None, 'project_version': None,
                'captured_at': '2026-09-10T00:00:00Z'}
    question = '  My exact earlier wording.\nNo added question frame.  '
    page.evaluate('''payload => {
        const record = activeConversation();
        record.messages = [{role: 'user', content: payload.question, snapshot_id: 'legacy',
                            context_refs: [{kind: 'rule', id: 'r1'}]},
                           {role: 'assistant', content: 'Old answer', snapshot_id: 'legacy'}];
        record.snapshots = {legacy: payload.snapshot}; useConversation(record); renderChat();
    }''', {'question': question, 'snapshot': snapshot})
    parent = page.evaluate('activeConversation()')
    page.locator('#chat-input').fill('Legacy parent draft')
    if changed:
        updated = deepcopy(runtime['bundle'])
        updated['scenario']['sources'][0]['text'] = 'Different source text'
        page.route('**/state', lambda route: route.fulfill(content_type='application/json', body=json.dumps(updated)))
    runtime['response']['message'] = 'New legacy retry answer'
    page.evaluate('() => retryConversationAt(0)')
    if changed:
        assert runtime['chat_requests'] == []
        assert page.evaluate('conversationStore.activeId') == parent['id']
        _expect_draft(page, 'Legacy parent draft')
        expect(page.locator('#global-status')).to_contain_text(re.compile('fork', re.I))
    else:
        expect(page.locator('.chat-msg-assistant').last).to_contain_text('New legacy retry answer')
        assert len(runtime['chat_requests']) == 1
        assert runtime['chat_requests'][0]['messages'] == [{'role': 'user', 'content': question}]
        assert runtime['chat_requests'][0]['context_refs'] == [{'kind': 'rule', 'id': 'r1'}]
        assert page.evaluate('activeConversation().messages[0].content') == question
        page.locator('#conversation-select').select_option(parent['id'])
        _expect_draft(page, 'Legacy parent draft')
        expect(page.locator('#chat-messages')).to_contain_text('Old answer')


@pytest.mark.parametrize('change_account', [False, True])
def test_retry_preparation_deduplicates_clicks_and_cannot_cross_accounts(explorer_browser, change_account):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    _answer_chat_draft(page, runtime, 'Original answer', 'Retry this question')
    parent = page.evaluate('activeConversation()')
    page.locator('#chat-input').fill('Keep the parent draft')
    held = []
    page.route('**/state', lambda route: held.append(route))
    page.evaluate('''() => {
        window.__firstRetry = retryConversationAt(0);
        window.__secondRetry = retryConversationAt(0);
    }''')
    expect(page.get_by_role('button', name='Retry', exact=True)).to_be_disabled()
    expect(page.get_by_role('button', name='Edit and fork', exact=True)).to_be_disabled()
    page.wait_for_timeout(50)
    assert len(held) == 1
    if change_account:
        runtime['user'] = 'researcher-b'
        page.evaluate("() => { state.authSession.user = {id: 'researcher-b', email: 'other@example.edu'}; renderAccountUI(); }")
        page.locator('#chat-input').fill('New account draft')
    runtime['response']['message'] = 'Only one retry answer'
    held.pop().fulfill(content_type='application/json', body=json.dumps(runtime['bundle']))
    page.evaluate('() => Promise.allSettled([window.__firstRetry, window.__secondRetry])')
    if change_account:
        assert len(runtime['chat_requests']) == 1
        expect(page.locator('#chat-messages')).not_to_contain_text('Original answer')
        expect(page.locator('#chat-messages')).not_to_contain_text('Only one retry answer')
        _expect_draft(page, 'New account draft')
        assert page.evaluate('conversationStore.owner') == 'researcher-b'
    else:
        assert len(runtime['chat_requests']) == 2
        expect(page.locator('.chat-msg-assistant').last).to_contain_text('Only one retry answer')
        expect(page.locator('#conversation-select option')).to_have_count(2)
        page.locator('#conversation-select').select_option(parent['id'])
        _expect_draft(page, 'Keep the parent draft')
        assert page.evaluate('activeConversation().messages') == parent['messages']


@pytest.mark.parametrize('current_draft', ['', 'A different draft typed during retry preparation'])
def test_cancelled_retry_preflight_keeps_the_current_parent_draft_without_sending(explorer_browser, current_draft):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    _answer_chat_draft(page, runtime, 'The parent answer remains', 'The original question')
    parent = page.evaluate('activeConversation()')
    page.locator('#chat-input').fill('Draft from before retry preparation')
    held = []
    page.route('**/state', lambda route: held.append(route))
    with page.expect_request('**/state'):
        page.evaluate('() => { window.__retryPreparation = retryConversationAt(0); }')
    expect(page.get_by_role('button', name='Retry', exact=True)).to_be_disabled()
    expect(page.locator('#chat-cancel-btn')).to_be_visible()
    page.locator('#chat-input').fill(current_draft)
    page.locator('#chat-cancel-btn').focus()
    page.keyboard.press('Enter')
    expect(page.locator('.chat-msg-loading')).to_have_count(0)
    _expect_draft(page, current_draft)
    assert len(held) == 1
    held.pop().fulfill(content_type='application/json', body=json.dumps(runtime['bundle']))
    page.evaluate('() => window.__retryPreparation')
    assert len(runtime['chat_requests']) == 1
    assert page.evaluate('conversationStore.activeId') == parent['id']
    assert page.evaluate('activeConversation().messages') == parent['messages']
    expect(page.locator('#conversation-select option')).to_have_count(1)
    expect(page.locator('#chat-messages')).not_to_contain_text('Answer stopped')
    _expect_draft(page, current_draft)
    page.evaluate('() => flushConversationWrites()')
    page.unroute('**/state')
    page.reload()
    _wait_for_history(page)
    _expect_draft(page, current_draft)
    assert page.evaluate('activeConversation().messages') == parent['messages']


def test_retry_cancellation_preserves_both_branches_and_newer_drafts(explorer_browser):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    _answer_chat_draft(page, runtime, 'Original answer remains', 'Question to retry and stop')
    parent = page.evaluate('activeConversation()')
    page.locator('#chat-input').fill('Parent draft stays here')
    runtime['hold_chat'] = True
    page.evaluate('''() => {
        const original = apiPostChat;
        apiPostChat = (...args) => { window.__retryChatSignal = args[3]; return original(...args); };
    }''')
    with page.expect_request('**/chat'):
        page.get_by_role('button', name='Retry', exact=True).click()
    expect(page.locator('#chat-cancel-btn')).to_be_visible()
    page.wait_for_function("activeConversation().id !== " + json.dumps(parent['id']))
    branch = page.evaluate('activeConversation().id')
    page.locator('#chat-input').fill('New draft typed while retry is pending')
    page.locator('#chat-cancel-btn').focus()
    page.keyboard.press('Enter')
    assert page.evaluate('window.__retryChatSignal.aborted') is True
    expect(page.locator('.chat-msg-loading')).to_have_count(0)
    _expect_draft(page, 'New draft typed while retry is pending')
    assert len(runtime['chat_requests']) == 2 and len(runtime['held']) == 1
    runtime['held'].pop().fulfill(content_type='application/json', body=json.dumps({**runtime['response'], 'message': 'Obsolete retry answer'}))
    page.evaluate('() => flushConversationWrites()')
    expect(page.locator('#chat-messages')).not_to_contain_text('Obsolete retry answer')
    expect(page.locator('#chat-messages')).to_contain_text('Answer stopped')
    page.locator('#conversation-select').select_option(parent['id'])
    _expect_draft(page, 'Parent draft stays here')
    assert page.evaluate('activeConversation().messages') == parent['messages']
    page.locator('#conversation-select').select_option(branch)
    page.reload()
    _wait_for_history(page)
    _expect_draft(page, 'New draft typed while retry is pending')
    expect(page.locator('#chat-messages')).not_to_contain_text('Obsolete retry answer')
    expect(page.locator('#chat-messages')).to_contain_text('Answer stopped')


def test_individual_derivations_preserve_shared_top_rules_and_navigation(explorer_browser):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    bundle = runtime["bundle"]
    candidates = [arg for arg in bundle["af"]["arguments"] if arg["conclusion"] == "c"]
    assert len(candidates) == 2 and candidates[0]["top_rule"] == candidates[1]["top_rule"]
    page.locator('[data-inspect-conclusion="c"]').click()
    select = page.locator("#derivation-argument-select")
    expect(select.locator("option")).to_have_count(len(candidates))
    assert select.locator("option").evaluate_all("options => options.map(option => option.value)") == [
        argument["id"] for argument in candidates
    ]
    expect(select).to_have_value(candidates[0]["id"])
    page.locator("#derivation-show-all").check()
    expect(select.locator("option")).to_have_count(len(bundle["af"]["arguments"]))
    expect(select).to_have_value(candidates[0]["id"])
    page.locator("#derivation-show-all").uncheck()
    expect(select.locator("option")).to_have_count(len(candidates))
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
    expect(page.locator("#modal-af .modal-title")).to_have_text("Conclusion graph")
    node = page.locator('#modal-af .af-node[data-af-lit="c"]')
    expect(node).to_have_attribute("role", "button")
    node.focus()
    page.keyboard.press("Enter")
    expect(page.locator("#modal-derivation")).to_be_visible()
    expect(page.locator("#modal-af")).to_be_hidden()
    expect(select.locator("option")).to_have_count(len(candidates))
    assert page.evaluate("inspectorState.bundle.af.arguments.find(argument => argument.id === inspectorState.argId).conclusion") == "c"
    assert runtime["chat_requests"] == []


def test_provider_failure_preserves_question_and_non_llm_actions(explorer_browser):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    runtime["chat_status"] = 503
    page.locator("#chat-input").fill("Why is this undecided?")
    page.locator("#chat-send-btn").click()
    expect(page.locator("#chat-degraded-note")).to_be_visible()
    _expect_draft(page, "Why is this undecided?")
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
            chatComposer.restore({text});
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


def test_mobile_stale_context_retains_text_and_makes_no_model_request(explorer_browser, tmp_path):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    page.set_viewport_size({"width": 390, "height": 844})
    page.locator(".rule-info").first.click()
    expect(page.locator("#chat-input")).to_be_focused()
    draft = _draft_text(page)
    rect = page.locator("#chat-input").bounding_box()
    assert rect and 0 <= rect["y"] < 844
    page.evaluate("""() => { state.bundle = structuredClone(state.bundle); state.bundle.scenario.title = 'Changed'; renderAll(); }""")
    expect(page.locator(".chat-reference-stale")).to_have_count(1)
    refresh = page.locator('#chat-input .chat-reference-refresh')
    refresh.focus()
    page.evaluate('() => renderChat()')
    expect(refresh).to_be_focused()
    page.locator("#chat-send-btn").click()
    assert runtime["chat_requests"] == []
    _expect_draft(page, draft)
    expect(page.locator("#global-status")).to_contain_text("earlier scenario state")
    _capture_exploration(page, tmp_path, "chat-stale-reference-phone")
    page.get_by_role("button", name=re.compile("^Remove .* from question context$")).click()
    expect(page.locator(".chat-reference-token")).to_have_count(0)


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
    _expect_draft(page, "")
    page.locator("#conversation-select").select_option(original_id)
    _expect_draft(page, "A saved draft")
    page.once("dialog", lambda dialog: dialog.accept())
    _conversation_action(page, "conversation-delete")
    page.wait_for_function("id => !conversationStore.records.some(record => record.id === id)", arg=original_id)
    stored = page.evaluate("() => conversationHistory.list('researcher-a')")
    assert original_id not in {item["record"]["id"] for item in stored["records"]}
    page.evaluate("""() => {
        window.__historySave = conversationHistory.save;
        conversationHistory.save = async () => { throw new DOMException('Full', 'QuotaExceededError'); };
    }""")
    page.locator("#chat-input").fill("Still editable when storage is full")
    expect(page.locator("#conversation-storage-note")).to_contain_text("History could not be saved")
    _expect_draft(page, "Still editable when storage is full")
    expect(page.locator("#conversation-recovery-export")).to_be_visible()
    with page.expect_download() as recovery:
        page.locator("#conversation-recovery-export").click()
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
    _expect_draft(other, "Original shared draft")
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
        _conversation_action(page, "conversation-delete")
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
    if transition == "reset":
        effective = deepcopy(runtime["bundle"]["scenario"])
        effective["assumptions"]["a"]["active"] = False
        effective_bundle = compute_state_bundle(scenario_from_dict(effective))
        page.evaluate("""bundle => {
            state.diff_ops = [{op: 'set_assumption_active', id: 'a', active: false}];
            setBundle(bundle); indexBundle(); renderAll();
        }""", effective_bundle)
    page.locator("#chat-input").fill("Question about the captured scenario")
    page.locator("#chat-send-btn").click()
    page.wait_for_function("activeConversation().messages.length === 1")
    page.evaluate("() => flushConversationWrites()")
    original_id = page.evaluate("conversationStore.activeId")
    if transition == "reset":
        page.locator("#reset-btn").click()
        expect(page.locator("#reset-btn")).to_be_hidden()
        assert page.evaluate("conversationStore.activeId") == original_id
        assert page.evaluate("state.bundle.scenario.assumptions.a.active") is True
        captured = page.evaluate("activeConversation().snapshots[activeConversation().messages[0].snapshot_id]")
        assert captured["scenario"]["scenario"]["assumptions"]["a"]["active"] is False
        assert captured["pending_ops"] == [{"op": "set_assumption_active", "id": "a", "active": False}]
    elif transition == "new":
        page.locator("#conversation-new").click()
    elif transition == "delete":
        page.once("dialog", lambda dialog: dialog.accept())
        _conversation_action(page, "conversation-delete")
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
        if transition == "new":
            expect(page.locator("#chat-messages")).not_to_contain_text(runtime["response"]["message"])
            page.locator("#conversation-select").select_option(original_id)
        else:
            assert page.evaluate("conversationStore.activeId") == original_id
            assert page.evaluate("activeConversation().messages.at(-1).earlier_state") is True
        expect(page.locator("#chat-messages")).to_contain_text(runtime["response"]["message"])
        expect(page.locator("#chat-messages")).to_contain_text("earlier scenario saved with this question")
        page.reload()
        expect(page.locator("#chat-messages")).to_contain_text(runtime["response"]["message"])
    else:
        awaitable = page.evaluate("() => conversationHistory.list('researcher-a')")
        assert runtime["response"]["message"] not in json.dumps(awaitable)
        expect(page.locator("#chat-messages")).not_to_contain_text(runtime["response"]["message"])


def test_legacy_migration_shared_source_dedup_and_empty_drafts(explorer_browser):
    page, runtime = explorer_browser
    portable = export_scenario(runtime["bundle"]["scenario"], None)
    snapshot = {"scenario": portable, "af": runtime["bundle"]["af"], "pending_ops": [], "captured_at": "2026-09-10T00:00:00Z"}
    record = {"id": "legacy-record", "title": "Legacy discussion", "draft": "Unsent legacy draft", "context_refs": [],
              "messages": [{"role": "user", "content": "Saved legacy question", "snapshot_id": "s1"}],
              "snapshots": {"s1": snapshot}}
    page.evaluate("record => localStorage.setItem('abda-conversations-v1:researcher-a', JSON.stringify({version:1,active_id:record.id,records:[record]}))", record)
    page.reload()
    _expect_draft(page, "Unsent legacy draft")
    assert page.evaluate("localStorage.getItem('abda-conversations-v1:researcher-a')") is None
    with page.expect_download() as download:
        _conversation_action(page, "conversation-export")
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
    original = _draft_text(page)
    page.evaluate("() => { state.bundle = structuredClone(state.bundle); state.bundle.scenario.title = 'Changed'; renderAll(); }")
    rule.click()
    _expect_draft(page, original)
    expect(page.locator(".chat-reference-token")).to_have_count(1)
    expect(page.locator(".chat-reference-stale")).to_have_count(0)
    page.locator("#chat-send-btn").click()
    expect(page.locator(".chat-msg-assistant")).to_contain_text("The claim is undecided")
    page.get_by_role("button", name="Edit and fork", exact=True).click()
    expect(page.locator(".chat-reference-stale")).to_have_count(1)
    page.get_by_role("button", name="Refresh rule r1 for the current scenario").click()
    expect(page.locator(".chat-reference-stale")).to_have_count(0)
    page.evaluate("() => { for (let i = 0; i < 24; i++) addQuestionDraft('Extra context', 'rule', `extra-${i}`); }")
    expect(page.locator(".chat-reference-token")).to_have_count(24)
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
    expect(page.locator(".chat-reference-token")).to_have_count(2)
    expect(page.locator(".chat-reference-stale")).to_have_count(0)


def test_evidence_roles_cost_notice_and_announcements_do_not_conflate_assurance(explorer_browser):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    runtime["response"]["billing_uncertain"] = True
    runtime["response"]["evidence"] = [
        {"kind": "source", "source": "record.txt", "quote": "Complete source text.", "start": 0, "end": 21, "verified": True, "evidence_role": "quotation"},
        {"kind": "source", "source": "record.txt", "quote": "Context", "start": 9, "end": 16, "verified": True, "evidence_role": "context"},
        {"kind": "source", "source": "record.txt", "quote": "Legacy", "start": 16, "end": 22, "verified": True},
        {"kind": "rule", "id": "top", "verified": True},
    ]
    page.locator("#chat-input").fill("Inspect the evidence")
    page.locator("#chat-send-btn").click()
    expect(page.locator("#chat-messages")).to_contain_text("Cost conservatively assessed")
    expect(page.locator(".chat-source-card > blockquote")).to_have_text(["Complete source text.", "Context", "Legacy"])
    expect(page.locator(".chat-source-card > blockquote").first).to_be_visible()
    context = page.locator(".chat-source-context")
    assert context.evaluate("details => details.open") is False
    context.locator("summary").click()
    expect(context.locator("blockquote")).to_contain_text("The first and second records disagree.")
    expect(context.locator("mark")).to_have_text("Complete source text.")
    expect(page.locator(".chat-formal-context")).to_have_count(0)
    expect(page.locator(".chat-evidence")).to_contain_text("Quotation matched")
    expect(page.locator(".chat-evidence")).to_contain_text("Suggested reading context")
    expect(page.locator(".chat-evidence")).to_contain_text("Supplied source excerpt")
    # Older archives retain evidence without recreating the repetitive footer.
    page.evaluate("() => { delete activeConversation().messages[0].context_refs; renderChat(); }")
    expect(page.locator(".chat-formal-context")).to_have_count(0)
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
    _expect_draft(page, "Keep this question after an outage")
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


def test_composer_ime_confirmation_does_not_send_a_question(explorer_browser):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    draft = page.locator('#chat-input')
    draft.fill('请解释这个结论')
    draft.dispatch_event('keydown', {'key': 'Enter', 'isComposing': True})
    draft.dispatch_event('compositionstart', {'data': '结论'})
    draft.dispatch_event('keydown', {'key': 'Enter', 'isComposing': False})
    assert runtime['chat_requests'] == []
    expect(page.locator('.chat-msg-user')).to_have_count(0)
    draft.dispatch_event('compositionend', {'data': '结论'})
    draft.press('Enter')
    expect(page.locator('.chat-msg-assistant')).to_contain_text('The claim is undecided')
    assert len(runtime['chat_requests']) == 1
    assert runtime['chat_requests'][0]['messages'][-1]['content'] == '请解释这个结论'


def test_atomic_reference_conversion_remove_and_undo_are_local(explorer_browser):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    page.locator('#chat-input').fill('My careful question. ')
    page.locator('[data-context-kind="rule"][data-context-id="r1"]').click()
    original = _draft_text(page)
    label = page.locator('#chat-input .chat-reference-label')
    label.focus()
    label.press('Space')
    expect(page.locator('#chat-input .chat-reference-token')).to_have_count(0)
    assert _draft_text(page) == original
    assert page.evaluate('state.chatContextRefs') == []
    expect(page.locator('#chat-composer-notice')).to_contain_text('Reference converted to text')
    page.get_by_role('button', name='Undo', exact=True).click()
    expect(page.locator('#chat-input .chat-reference-token')).to_have_count(1)
    remove = page.get_by_role('button', name='Remove rule r1 from question context')
    remove.focus()
    page.evaluate('() => renderAll()')
    expect(remove).to_be_focused()
    remove.press('Enter')
    expect(page.locator('#chat-input .chat-reference-token')).to_have_count(0)
    assert _draft_text(page).startswith('My careful question. ')
    assert _draft_text(page) == 'My careful question. '
    page.locator('#chat-input').press('Control+z')
    expect(page.locator('#chat-input .chat-reference-token')).to_have_count(1)
    assert _draft_text(page) == original
    page.locator('#chat-input').press('Control+Shift+z')
    expect(page.locator('#chat-input .chat-reference-token')).to_have_count(0)
    assert runtime['chat_requests'] == []


def test_composer_clipboard_plaintext_and_selection_across_reference(explorer_browser):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    page.locator('[data-context-kind="rule"][data-context-id="r1"]').click()
    original = _draft_text(page)
    copied = page.locator('#chat-input').evaluate("""input => {
      const range=document.createRange(); range.selectNodeContents(input);
      const selection=window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
      const event=new ClipboardEvent('copy',{clipboardData:new DataTransfer(),bubbles:true,cancelable:true});
      input.dispatchEvent(event);
      return {text:event.clipboardData.getData('text/plain'),html:event.clipboardData.getData('text/html')};
    }""")
    assert copied == {'text': original, 'html': ''}
    page.keyboard.press('Backspace')
    _expect_draft(page, '')
    assert page.evaluate('state.chatContextRefs') == []
    page.locator('#chat-input').press('Control+z')
    _expect_draft(page, original)
    expect(page.locator('#chat-input .chat-reference-token')).to_have_count(1)
    page.locator('#chat-input').fill('Before ')
    page.locator('#chat-input').press('End')
    page.locator('#chat-input').evaluate("""input => {
      const event=new ClipboardEvent('paste',{clipboardData:new DataTransfer(),bubbles:true,cancelable:true});
      event.clipboardData.setData('text/plain','<b>Plain words</b>');
      event.clipboardData.setData('text/html','<img src="https://not-allowed.test/secret">');
      input.dispatchEvent(event);
    }""")
    _expect_draft(page, 'Before <b>Plain words</b>')
    expect(page.locator('#chat-input img, #chat-input b')).to_have_count(0)
    assert runtime['chat_requests'] == []


def test_source_reader_uses_saved_unicode_coordinates_after_current_source_changes(explorer_browser, tmp_path):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    original = '😀 Intro. Exact quotation. Its qualification remains visible.'
    runtime['bundle']['scenario']['sources'][0]['text'] = original
    runtime['bundle']['scenario']['sources'][0]['url'] = 'https://private.example.edu/source-metadata'
    runtime['bundle']['scenario']['sources'].append({'filename': 'appendix.txt', 'text': 'Supporting appendix.'})
    page.evaluate('bundle => { state.bundle=structuredClone(bundle); renderAll(); }', runtime['bundle'])
    start = original.index('Exact quotation.')
    runtime['response']['evidence'] = [{'kind': 'source', 'source': 'record.txt', 'quote': 'Exact quotation.',
                                       'start': start, 'end': start + len('Exact quotation.'), 'verified': True, 'evidence_role': 'quotation'}]
    page.locator('#chat-input').fill('Quote the record')
    page.locator('#chat-send-btn').click()
    expect(page.locator('.chat-source-card mark')).to_have_text('Exact quotation.')
    expect(page.locator('.chat-source-card blockquote')).to_contain_text('qualification')
    page.evaluate("() => { state.bundle=structuredClone(state.bundle); state.bundle.scenario.sources[0].text='Different current private source'; renderAll(); }")
    page.get_by_role('button', name='Open record.txt in Sources').click()
    expect(page.locator('#modal-sources-reader')).to_be_visible()
    expect(page.locator('#source-reader-text')).to_have_text(original)
    expect(page.locator('#source-reader-text mark')).to_have_text('Exact quotation.')
    expect(page.locator('#source-reader-state')).to_contain_text('Saved scenario')
    expect(page.locator('#source-reader-metadata')).to_contain_text('https://private.example.edu/source-metadata')
    appendix = page.locator('.source-reader-document').filter(has_text='appendix.txt')
    appendix.focus()
    appendix.press('Enter')
    expect(appendix).to_be_focused()
    expect(page.locator('#source-reader-text')).to_have_text('Supporting appendix.')
    cited_source = page.locator('.source-reader-document').filter(has_text='record.txt')
    cited_source.focus()
    cited_source.press('Enter')
    expect(cited_source).to_be_focused()
    expect(page.locator('#source-reader-text')).to_have_text(original)
    expect(page.locator('#source-reader-text mark')).to_have_text('Exact quotation.')
    _capture_exploration(page, tmp_path, "sources-reader-saved-quotation")
    page.evaluate("() => { state.authSession={authenticated:false}; syncConversationIdentity(); }")
    expect(page.locator('#modal-sources-reader')).not_to_be_visible()
    for element in ['source-reader-documents', 'source-reader-text', 'source-reader-excerpt', 'source-reader-metadata', 'source-reader-position']:
        expect(page.locator(f'#{element}')).to_be_empty()
    expect(page.locator('#sources-reader-title')).to_have_text('Sources and glossary')
    assert len(runtime['chat_requests']) == 1


def test_ambiguous_source_location_is_not_highlighted_and_search_is_literal(explorer_browser):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    text = 'Repeated (claim). Another line. Repeated (claim).'
    runtime['bundle']['scenario']['sources'][0]['text'] = text
    page.evaluate('bundle => { state.bundle=structuredClone(bundle); renderAll(); }', runtime['bundle'])
    runtime['response']['evidence'] = [{'kind': 'source', 'source': 'record.txt', 'quote': 'Repeated (claim).',
                                       'start': 200, 'end': 217, 'verified': True, 'evidence_role': 'context'}]
    page.locator('#chat-input').fill('Show context')
    page.locator('#chat-send-btn').click()
    expect(page.locator('.chat-source-card')).to_contain_text('Location in the saved document could not be confirmed.')
    expect(page.locator('.chat-source-card mark')).to_have_count(0)
    page.get_by_role('button', name='Open record.txt in Sources').click()
    expect(page.locator('#source-reader-text mark')).to_have_count(0)
    expect(page.locator('#source-reader-excerpt')).to_contain_text('Repeated (claim).')
    page.locator('#source-reader-search').fill('(claim).')
    expect(page.locator('#source-reader-position')).to_have_text('Search match 1 of 2')
    page.locator('#source-reader-next').click()
    expect(page.locator('#source-reader-position')).to_have_text('Search match 2 of 2')
    expect(page.locator('#source-reader-text mark')).to_have_text('(claim).')
    assert len(runtime['chat_requests']) == 1


def test_no_documents_retains_formal_context_and_reader_clears_on_account_change(explorer_browser):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    runtime['bundle']['scenario']['sources'] = []
    runtime['response']['evidence'] = []
    page.evaluate('bundle => { state.bundle=structuredClone(bundle); renderAll(); }', runtime['bundle'])
    expect(page.locator('#chat-no-documents')).to_be_visible()
    page.evaluate("addQuestionDraft('First record','fact','p1')")
    page.locator('#chat-send-btn').click()
    expect(page.locator('.chat-msg-user .chat-formal-reference')).to_contain_text('First record')
    expect(page.locator('.chat-formal-context')).to_have_count(0)
    expect(page.locator('.chat-evidence')).to_have_count(0)
    page.evaluate('openSourcesReader()')
    expect(page.locator('#source-reader-documents')).to_contain_text('No reference documents attached')
    page.locator('#source-reader-glossary-tab').click()
    expect(page.locator('#source-reader-glossary')).to_contain_text('First record')
    page.evaluate("() => { state.authSession={authenticated:false}; syncConversationIdentity(); }")
    expect(page.locator('#modal-sources-reader')).not_to_be_visible()
    expect(page.locator('#source-reader-glossary')).to_be_empty()
    expect(page.locator('#source-reader-text')).to_be_empty()


def test_inline_formal_links_use_exact_saved_arguments_and_skip_code(explorer_browser):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    argument = runtime['bundle']['af']['arguments'][0]
    runtime['response']['message'] = f"See [r1], [-c], and [{argument['id']}]. `[r2]` is code. [unknown] stays text."
    runtime['response']['evidence'] = []
    page.locator('#chat-input').fill('Inspect these identities')
    page.locator('#chat-send-btn').click()
    answer = page.locator('.chat-msg-assistant')
    expect(answer.get_by_role('button', name=re.compile('^Inspect rule r1:'))).to_have_count(1)
    expect(answer.get_by_role('button', name=re.compile('^Inspect conclusion -c:'))).to_have_count(1)
    expect(answer.locator('code')).to_have_text('[r2]')
    expect(answer.get_by_role('button', name=re.compile('^Inspect rule r2:'))).to_have_count(0)
    answer.get_by_role('button', name=re.compile(f"^Inspect argument {argument['id']}:")).click()
    expect(page.locator('#derivation-body')).to_contain_text('Saved scenario at the time of this answer')
    assert page.evaluate('inspectorState.argId') == argument['id']
    assert len(runtime['chat_requests']) == 1


def test_caret_crosses_reference_atomically_and_backspace_preserves_prose(explorer_browser):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    page.locator('#chat-input').fill('Consider ')
    page.locator('[data-context-kind="rule"][data-context-id="r1"]').click()
    page.locator('#chat-input').evaluate("""input => {
      const token=input.querySelector('.chat-reference-token'); const range=document.createRange(); range.setStartAfter(token); range.collapse(true);
      const selection=window.getSelection(); selection.removeAllRanges(); selection.addRange(range); input.focus();
    }""")
    page.keyboard.press('ArrowLeft')
    page.keyboard.press('Backspace')
    expect(page.locator('#chat-input .chat-reference-token')).to_have_count(1)
    assert _draft_text(page).startswith('Consider"')
    page.keyboard.press('ArrowRight')
    page.keyboard.press('Backspace')
    expect(page.locator('#chat-input .chat-reference-token')).to_have_count(0)
    _expect_draft(page, 'Consider')
    page.keyboard.press('Control+z')
    expect(page.locator('#chat-input .chat-reference-token')).to_have_count(1)
    assert runtime['chat_requests'] == []


def test_composition_commits_text_and_shift_enter_preserves_exact_prose(explorer_browser):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    draft = page.locator('#chat-input')
    draft.fill('  α')
    draft.press('End')
    draft.press('Shift+Enter')
    _expect_draft(page, '  α\n')
    page.keyboard.insert_text('β  ')
    _expect_draft(page, '  α\nβ  ')
    assert runtime['chat_requests'] == []
    draft.dispatch_event('compositionstart', {'data': '结论'})
    draft.evaluate("input => { input.firstChild.data += '结论'; }")
    draft.dispatch_event('input', {'inputType': 'insertCompositionText', 'data': '结论', 'isComposing': True})
    draft.dispatch_event('keydown', {'key': 'Enter', 'isComposing': True})
    assert runtime['chat_requests'] == []
    draft.dispatch_event('compositionend', {'data': '结论'})
    _expect_draft(page, '  α\nβ  结论')
    page.locator('#chat-send-btn').click()
    expect(page.locator('.chat-msg-assistant')).to_contain_text('The claim is undecided')
    assert runtime['chat_requests'][0]['messages'][-1]['content'] == '  α\nβ  结论'
    message = page.evaluate('activeConversation().messages[0]')
    assert ''.join(segment['text'] for segment in message['segments']) == message['content']


def test_legacy_reference_draft_and_fork_keep_original_words_without_matching(explorer_browser):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    portable = export_scenario(runtime['bundle']['scenario'], None)
    snapshot = {'scenario': portable, 'af': runtime['bundle']['af'], 'pending_ops': [], 'captured_at': '2026-09-10T00:00:00Z'}
    record = {'id': 'legacy-references', 'title': 'Earlier question', 'draft': 'Compare these two rules.',
              'context_refs': [{'kind': 'rule', 'id': 'r1', 'description': 'First rule', 'scenario_signature': '', 'view_key': ''},
                               {'kind': 'rule', 'id': 'r2', 'description': 'Second rule', 'scenario_signature': '', 'view_key': ''}],
              'messages': [{'role': 'user', 'content': 'My exact earlier wording.', 'snapshot_id': 's1',
                            'context_refs': [{'kind': 'rule', 'id': 'r1'}, {'kind': 'rule', 'id': 'r2'}]}],
              'snapshots': {'s1': snapshot}}
    page.evaluate("record => localStorage.setItem('abda-conversations-v1:researcher-a',JSON.stringify({version:1,active_id:record.id,records:[record]}))", record)
    page.reload()
    _expect_draft(page, 'Compare these two rules.\n"First rule"\n"Second rule"')
    expect(page.locator('#chat-input .chat-reference-token')).to_have_count(2)
    assert page.evaluate('activeConversation().messages[0].content') == 'My exact earlier wording.'
    page.get_by_role('button', name='Edit and fork', exact=True).click()
    assert _draft_text(page).startswith('My exact earlier wording.\n')
    assert [item['id'] for item in page.evaluate('state.chatContextRefs')] == ['r1', 'r2']
    expect(page.locator('#chat-input .chat-reference-stale')).to_have_count(2)
    assert page.evaluate("conversationStore.records.find(record=>record.id==='legacy-references').messages[0].content") == 'My exact earlier wording.'
    assert runtime['chat_requests'] == []
