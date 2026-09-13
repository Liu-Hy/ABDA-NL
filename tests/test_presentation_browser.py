"""Presentation mode uses the existing controls and preserves deterministic work."""
import os

import pytest

from tests.test_browser_e2e import live_browser_server as _live_browser_server, _goto_ready_demo, _axe_report
from tests.test_exploration_browser import explorer_browser as _explorer_browser, _hold_proposals_ignoring_abort, _proposal_response


pytestmark = pytest.mark.skipif(os.getenv("ABDA_BROWSER_TESTS") != "1", reason="browser acceptance is opt-in")
live_browser_server = _live_browser_server
explorer_browser = _explorer_browser


def _turn_off(page):
    page.locator("#ai-access-btn").click()
    page.locator("#ai-menu").get_by_role("menuitemradio", name="AI off", exact=True).click()


def _access_settings(page):
    page.locator("#workspace-btn").click()
    page.locator("#account-menu").get_by_role("menuitem", name="AI access...", exact=True).click()


def test_ai_off_is_synchronized_preserves_work_and_is_scoped_to_the_tab(explorer_browser):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    page.locator("#chat-input").fill("Keep this unfinished question.")
    page.locator("#resize-handle").press("ArrowLeft")
    page.wait_for_function("""() => {
        const el = document.querySelector('#left-panel');
        return Math.abs(el.getBoundingClientRect().width / el.parentElement.getBoundingClientRect().width * 100 - parseFloat(el.style.width)) < .1;
    }""")
    original_width = page.locator("#left-panel").bounding_box()["width"]
    page.evaluate("flushConversationWrites()")
    before = page.evaluate("({bundle: state.bundle, diff: state.diff_ops, messages: state.chatMessages})")
    _turn_off(page)
    expect(page.locator("#ai-access-btn")).to_have_text("AI off")
    expect(page.locator("#ai-access-btn")).to_be_focused()
    expect(page.locator("#chat-input")).to_be_hidden()
    page.wait_for_function("""() => {
        const el = document.querySelector('#left-panel');
        return Math.abs(el.getBoundingClientRect().width - el.parentElement.getBoundingClientRect().width) < 2;
    }""")
    assert page.locator("#left-panel").bounding_box()["width"] > original_width
    assert page.locator("#left-panel").evaluate("el => Math.abs(el.getBoundingClientRect().width - el.parentElement.getBoundingClientRect().width) < 2")
    expect(page.locator("#conclusions-list .btn-explain").first).to_be_visible()
    assert page.evaluate("({bundle: state.bundle, diff: state.diff_ops, messages: state.chatMessages})") == before
    page.locator("#conclusions-list .btn-explain").first.click()
    expect(page.locator("#modal-game")).to_be_visible()
    page.keyboard.press("Escape")
    _access_settings(page)
    expect(page.locator("#workspace-tab-ai")).to_be_visible()
    expect(page.locator('input[name="ai-mode"][value="off"]')).to_be_checked()
    expect(page.locator("#funded-settings")).to_be_hidden()
    _axe_report(page, "AI off access settings")
    page.locator('input[name="ai-mode"][value="funded"]').check()
    page.locator("#ai-access-form button[type=submit]").click()
    expect(page.locator("#ai-access-form button[type=submit]")).to_be_focused()
    expect(page.locator("#ai-access-btn")).not_to_have_text("AI off")
    page.keyboard.press("Escape")
    expect(page.locator("#chat-input")).to_have_text("Keep this unfinished question.")
    page.wait_for_function("width => Math.abs(document.querySelector('#left-panel').getBoundingClientRect().width - width) < 2", arg=original_width)
    assert abs(page.locator("#left-panel").bounding_box()["width"] - original_width) < 2
    _access_settings(page)
    page.locator('input[name="ai-mode"][value="off"]').check()
    page.locator("#ai-access-form button[type=submit]").click()
    expect(page.locator("#ai-access-btn")).to_have_text("AI off")
    page.keyboard.press("Escape")
    page.reload()
    expect(page.locator("#ai-access-btn")).to_have_text("AI off")
    expect(page.locator("#chat-input")).to_be_hidden()
    other = page.context.new_page()
    try:
        other.goto("https://abda.test/")
        expect(other.locator("#chat-input")).to_be_visible()
        expect(other.locator("#ai-access-btn")).not_to_have_text("AI off")
    finally:
        other.close()
    page.locator("#ai-access-btn").click()
    page.locator("#ai-menu").get_by_role("menuitemradio", name="Balanced", exact=True).click()
    expect(page.locator("#chat-input")).to_have_text("Keep this unfinished question.")
    assert runtime["chat_requests"] == []


def test_ai_off_cancels_pending_chat_and_ignores_a_late_answer(explorer_browser):
    from playwright.sync_api import expect

    page, runtime = explorer_browser
    page.evaluate("""() => {
        const original = window.fetch;
        window.fetch = (path, options) => String(path).endsWith('/chat')
            ? new Promise(resolve => { window.pendingChat = {resolve, signal: options.signal}; })
            : original(path, options);
    }""")
    page.locator("#chat-input").fill("Explain the claim.")
    page.locator("#chat-send-btn").click()
    page.wait_for_function("window.pendingChat")
    _turn_off(page)
    assert page.evaluate("window.pendingChat.signal.aborted") is True
    expect(page.locator("#ai-access-btn")).to_be_focused()
    page.evaluate("window.pendingChat.resolve(new Response(JSON.stringify({message: 'Obsolete answer', model: 'test'})))")
    page.locator("#ai-access-btn").click()
    page.locator("#ai-menu").get_by_role("menuitemradio", name="Balanced", exact=True).click()
    expect(page.locator("#chat-input")).to_have_text("Explain the claim.")
    expect(page.locator("#chat-send-btn")).to_be_enabled()
    expect(page.locator("#chat-messages")).not_to_contain_text("Obsolete answer")
    assert runtime["chat_requests"] == []


def test_ai_off_cancels_proposals_without_losing_the_instruction(explorer_browser):
    from playwright.sync_api import expect

    page, _ = explorer_browser
    _hold_proposals_ignoring_abort(page)
    page.evaluate("openEditModal('add-fact')")
    page.locator("#edit-instruction").fill("Add a new observation.")
    page.locator('[data-edit-action="propose"]').click()
    page.wait_for_function("window.__proposalCalls.length === 1")
    # A modal normally covers the menu. Exercise the cancellation boundary
    # directly as well, including a transport that resolves after abort.
    page.evaluate("setPresentationNoAI(true)")
    assert page.evaluate("window.__proposalCalls[0].signal.aborted") is True
    page.evaluate("body => window.__proposalCalls[0].resolve(new Response(JSON.stringify(body)))", _proposal_response())
    expect(page.locator("#edit-instruction")).to_have_value("Add a new observation.")
    expect(page.locator("#edit-preview")).to_be_empty()
    expect(page.locator("#edit-status")).to_contain_text("AI is off")
    assert page.evaluate("state.diff_ops") == []


@pytest.mark.parametrize("live_browser_server", [False, True], indirect=True)
def test_manual_presentation_works_with_real_server_and_without_sign_in(live_browser_server):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, os.getenv("ABDA_BROWSER_ENGINE", "chromium")).launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors, model_calls = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: model_calls.append(request.url) if request.url.endswith(("/chat", "/propose")) else None)
        try:
            _goto_ready_demo(page, live_browser_server)
            config = page.request.get(f"{live_browser_server}/config").json()
            if config["llm_enabled"]:
                _turn_off(page)
            expect(page.locator("#ai-access-btn")).to_have_text("AI off")
            expect(page.locator("#chat-input")).to_be_hidden()
            page.locator("#ai-access-btn").click()
            expect(page.locator("#ai-menu").get_by_role("menuitemradio", name="AI off", exact=True)).to_have_attribute("aria-checked", "true")
            page.keyboard.press("Escape")
            _access_settings(page)
            expect(page.locator('input[name="ai-mode"][value="off"]')).to_be_checked()
            if not config["llm_enabled"]:
                expect(page.locator('input[name="ai-mode"][value="funded"]')).to_be_disabled()
                expect(page.locator("#ai-off-description")).to_contain_text("disabled on this server")
            page.keyboard.press("Escape")
            page.locator('[data-explain-id="popov_legit_claim"]').click()
            expect(page.locator("#modal-game")).to_be_visible()
            page.keyboard.press("Escape")
            page.locator('.facts-filter[data-filter="assumptions"]').click()
            page.locator('[data-asm-id="equity_compromise_open"]').check()
            page.locator("#suspend-impact-apply-btn").click()
            expect(page.locator("#modified-indicator")).to_be_visible()
            assert page.evaluate("state.bundle.af.labels_by_proposition.equal_division") == "undecided"
            page.locator("#reset-btn").click()
            expect(page.locator("#modified-indicator")).to_be_hidden()
            page.locator("#view-af-btn").click()
            expect(page.locator("#af-modal-body .af-node").first).to_be_visible()
            page.keyboard.press("Escape")
            page.locator("#aspic-btn").click()
            expect(page.locator("#aspic-pre")).to_contain_text("Strict rules")
            page.keyboard.press("Escape")
            for width in (390, 1440):
                page.set_viewport_size({"width": width, "height": 900})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
                expect(page.locator("#ai-access-btn")).to_be_visible()
            assert errors == []
            assert model_calls == []
        finally:
            browser.close()
