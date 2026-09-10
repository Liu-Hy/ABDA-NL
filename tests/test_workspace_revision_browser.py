"""Real-browser checks for dialog ordering, private Restore, and publication consent."""
from datetime import datetime, timezone

import pytest

from test_browser_e2e import BROWSER_ENGINE, BROWSER_TESTS, live_browser_server as browser_server
from test_scenario_submissions import PICNIC

live_browser_server = browser_server
pytestmark = pytest.mark.skipif(not BROWSER_TESTS, reason="set ABDA_BROWSER_TESTS=1 for isolated browser tests")


def ready(page, server, email="author@example.org", name="Example Author"):
    assert page.request.post(f"{server}/api/auth/dev/login", data={"email": email, "display_name": name}).ok
    page.goto(server, wait_until="domcontentloaded")
    page.locator("#conclusions-list .conclusion-card").first.wait_for()


def saved_project(page, server):
    response = page.request.post(f"{server}/api/projects/import", data={
        "name": "Private picnic", "description": "Private project note", "scenario": PICNIC,
    })
    assert response.ok
    return response.json()


def test_modal_stack_overrides_dom_order_and_restores_focus(live_browser_server):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            ready(page, live_browser_server)
            page.locator("#workspace-btn").focus()
            page.evaluate("() => openModal('modal-example-review', '#example-review-close')")
            page.evaluate("() => openWorkspace('projects')")
            expect(page.locator("#modal-example-review")).to_have_attribute("inert", "")
            expect(page.locator("#modal-workspace")).not_to_have_attribute("inert", "")
            assert page.evaluate("() => Number(getComputedStyle(byId('modal-workspace')).zIndex) > Number(getComputedStyle(byId('modal-example-review')).zIndex)")
            assert page.evaluate("() => modalFocusableElements(byId('modal-workspace')).every(element => !byId('project-create-form').contains(element) && element.tabIndex >= 0)")
            page.locator("#project-copy-panel > summary").focus()
            page.keyboard.press("Tab")
            expect(page.locator("#modal-workspace .modal-close")).to_be_focused()
            page.keyboard.press("Shift+Tab")
            expect(page.locator("#project-copy-panel > summary")).to_be_focused()
            for _ in range(12):
                page.keyboard.press("Tab")
                assert page.evaluate("() => byId('modal-workspace').contains(document.activeElement)"), page.evaluate(
                    "() => ({active: document.activeElement.outerHTML, focusable: modalFocusableElements(byId('modal-workspace')).map(e => e.id || e.tagName), stack: [...modalStack]})")
            page.keyboard.press("Escape")
            expect(page.locator("#modal-workspace")).not_to_be_visible()
            expect(page.locator("#modal-example-review")).not_to_have_attribute("inert", "")
            expect(page.locator("#example-review-close")).to_be_focused()
            page.keyboard.press("Escape")
            expect(page.locator("#workspace-btn")).to_be_focused()
            assert page.evaluate("() => !document.querySelector('main').inert")
        finally:
            browser.close()


@pytest.mark.parametrize("operation", ["restore", "publication"])
def test_late_project_refresh_cannot_override_a_new_account_or_view(live_browser_server, operation):
    """Complete the real mutation, change identity/view during its refresh, then release it."""
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page()
        page.on("dialog", lambda dialog: dialog.accept())
        try:
            ready(page, live_browser_server, "curator@example.org", "Curator")
            saved = saved_project(page, live_browser_server)
            if operation == "restore":
                assert page.request.delete(f"{live_browser_server}/api/projects/{saved['id']}?expected_version=1").ok
                page.evaluate("() => openWorkspace('projects')")
                page.locator("#projects-archived-filter").click()
                expect(page.locator('[data-project-action="restore"]')).to_be_visible()
            else:
                page.evaluate("id => loadProject(id)", saved["id"])
                page.evaluate("() => openWorkspace('projects')")
                page.evaluate("() => beginExampleSubmission()")
                page.locator("#example-public-consent").check()
            page.evaluate("""() => {
                const original = refreshProjects;
                refreshProjects = async options => {
                    document.body.dataset.followupPending = 'yes';
                    await new Promise(resolve => { window.__releaseProjectRefresh = resolve; });
                    return original(options);
                };
            }""")
            page.evaluate("""operation => {
                window.__pendingOperation = operation === 'restore'
                  ? restoreArchivedProject(document.querySelector('[data-project-action="restore"]'))
                  : handleExampleDecision({target: document.querySelector('[data-example-action="submit"]')});
            }""", operation)
            expect(page.locator("body")).to_have_attribute("data-followup-pending", "yes")
            if operation == "restore":
                assert page.request.get(f"{live_browser_server}/api/projects/{saved['id']}").json()["version"] == 3
                assert page.request.post(f"{live_browser_server}/api/auth/dev/login", data={"email": "next-account@example.org"}).ok
                page.evaluate("""async () => {
                    state.authSession = await apiRequest('/api/auth/session');
                    renderAccountUI();
                }""")
            else:
                assert any(item["category"] == "community" for item in page.request.get(f"{live_browser_server}/scenarios").json()["scenarios"])
                assert page.request.post(f"{live_browser_server}/api/auth/view-mode", data={"normal_user_view": True}).ok
                page.evaluate("""async () => {
                    const account = state.authSession.user.id;
                    applyAccountViewSession(await apiRequest('/api/auth/session'), account);
                }""")
            page.evaluate("""() => {
                requestCloseModal('modal-workspace');
                showGlobalStatus('The current view is ready.', 'info');
            }""")
            page.evaluate("""async () => {
                window.__releaseProjectRefresh();
                await window.__pendingOperation;
            }""")
            expect(page.locator("#modal-workspace")).not_to_be_visible()
            expect(page.locator("#global-status")).to_contain_text("The current view is ready.")
            expect(page.locator("#global-status button:not(.status-dismiss)")).to_have_count(0)
            assert page.evaluate("curation.publishedNotice") is None
        finally:
            browser.close()


def test_errors_and_action_statuses_do_not_expire(live_browser_server):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page()
        try:
            ready(page, live_browser_server)
            page.clock.install()
            page.evaluate("() => showGlobalStatus('A recoverable error', 'error')")
            page.clock.fast_forward(15000)
            expect(page.locator("#global-status")).to_be_visible()
            page.get_by_role("button", name="Dismiss notification").click()
            expect(page.locator("#global-status")).not_to_be_visible()
            page.evaluate("() => showGlobalStatus('Saved', 'success')")
            page.clock.fast_forward(5100)
            expect(page.locator("#global-status")).not_to_be_visible()
            page.evaluate("() => showGlobalStatus('Published', 'success', {label: 'Open example', onClick: () => document.body.dataset.actionChecked = 'yes'})")
            page.clock.fast_forward(15000)
            page.get_by_role("button", name="Open example").click()
            expect(page.locator("body")).to_have_attribute("data-action-checked", "yes")
        finally:
            browser.close()


def test_project_share_expiry_archive_and_private_restore(live_browser_server):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.on("dialog", lambda dialog: dialog.accept())
        try:
            ready(page, live_browser_server)
            saved = saved_project(page, live_browser_server)
            balance = page.request.get(f"{live_browser_server}/api/trial").json()
            page.evaluate("() => openWorkspace('projects')")
            expect(page.locator("#project-copy-panel")).not_to_have_attribute("open", "")
            page.locator(f'#project-list [data-project-id="{saved["id"]}"][data-project-action="open"]').click()
            expect(page.locator("#scenario-name")).to_have_text(saved["name"])
            expect(page.locator("#modal-workspace")).not_to_be_visible()
            page.evaluate("() => openWorkspace('projects')")
            page.locator("#current-project-card .project-menu > summary").click()
            page.locator('#current-project-card [data-project-action="share"]').click()
            page.locator("#project-share-expiry").select_option("1")
            with page.expect_response(lambda response: response.url.endswith("/shares") and response.request.method == "POST") as created:
                page.locator('[data-project-action="share-create"]').click()
            share = created.value.json()
            expires = datetime.fromisoformat(share["expires_at"])
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            assert 23 * 3600 < (expires - datetime.now(timezone.utc)).total_seconds() < 25 * 3600
            expect(page.locator("#latest-share-url")).to_have_value(share["url"])
            page.locator("#current-project-card .project-menu > summary").click()
            page.locator('#current-project-card [data-project-action="archive"]').click()
            expect(page.locator(f'#project-list [data-project-card="{saved["id"]}"]')).to_have_count(0)
            page.locator("#projects-archived-filter").click()
            card = page.locator(f'[data-project-card="{saved["id"]}"]')
            expect(card).to_contain_text("Archived")
            card.get_by_role("button", name="Restore privately").click()
            expect(card).to_have_count(0)
            token = share["url"].split("#share=", 1)[1]
            assert page.request.post(f"{live_browser_server}/api/shares/resolve", data={"token": token}).status == 404
            page.locator("#projects-active-filter").click()
            expect(page.locator(f'[data-project-card="{saved["id"]}"]')).to_contain_text("Version 3")
            assert page.request.get(f"{live_browser_server}/api/trial").json() == balance
        finally:
            browser.close()


def test_public_metadata_consent_and_inline_approval(live_browser_server):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        author = browser.new_page(viewport={"width": 1280, "height": 900})
        admin = browser.new_page(viewport={"width": 1280, "height": 900})
        errors = []
        author.on("pageerror", lambda error: errors.append(str(error)))
        admin.on("pageerror", lambda error: errors.append(str(error)))
        try:
            ready(author, live_browser_server)
            saved = saved_project(author, live_browser_server)
            author.evaluate("id => loadProject(id)", saved["id"])
            author.evaluate("() => openWorkspace('projects')")
            author.locator("#current-project-card .project-menu > summary").click()
            author.locator('#current-project-card [data-project-action="suggest-example"]').click()
            expect(author.locator("#example-public-title")).to_have_value("Private picnic")
            expect(author.locator("#example-full-snapshot")).not_to_have_attribute("open", "")
            expect(author.locator("#example-snapshot-summary")).to_contain_text("published in full", ignore_case=True)
            expect(author.locator("#example-attribute-author")).not_to_be_checked()
            author.locator("#example-public-consent").check()
            author.locator("#example-public-title").fill("A public picnic")
            expect(author.locator("#example-public-consent")).not_to_be_checked()
            author.locator("#example-public-summary").fill("A short public summary.")
            author.locator("#example-author-note").fill("A private note to the reviewer")
            author.locator("#example-attribute-author").check()
            author.locator("#example-public-consent").check()
            author.set_viewport_size({"width": 390, "height": 844})
            consent = author.locator("#example-public-consent").bounding_box()
            action = author.locator('[data-example-action="submit"]').bounding_box()
            assert consent and action and consent["y"] >= 0 and action["y"] + action["height"] <= 844
            with author.expect_response(lambda response: response.url.endswith("/api/scenario-submissions") and response.request.method == "POST") as submitted:
                author.locator('[data-example-action="submit"]').click()
            item = submitted.value.json()
            assert item["public_summary"] == "A short public summary."
            expect(author.locator("#examples-list")).to_contain_text("Awaiting review")
            ready(admin, live_browser_server, "curator@example.org", "Curator")
            loaded_scenario = admin.evaluate("state.scenario_id")
            admin.evaluate("() => openWorkspace('examples')")
            expect(admin.locator("#examples-filter-segments")).to_contain_text("Awaiting review 1")
            expect(admin.locator("#examples-list")).to_contain_text("Example Author")
            admin.get_by_role("button", name="Review", exact=True).click()
            expect(admin.locator("#example-author-note")).to_have_value("A private note to the reviewer")
            admin.locator('[data-example-action="approve"]').click()
            expect(admin.locator("#example-publish-confirmation")).to_be_visible()
            assert not any(value["category"] == "community" for value in admin.request.get(f"{live_browser_server}/scenarios").json()["scenarios"])
            admin.locator('[data-example-action="cancel-publish"]').click()
            expect(admin.locator('[data-example-action="approve"]')).to_be_focused()
            admin.locator('[data-example-action="approve"]').click()
            admin.locator('[data-example-action="confirm-publish"]').click()
            expect(admin.locator("#modal-example-review")).not_to_be_visible()
            expect(admin.locator('[data-example-filter="pending"]')).to_have_attribute("aria-pressed", "true")
            public = next(value for value in admin.request.get(f"{live_browser_server}/scenarios").json()["scenarios"] if value["category"] == "community")
            assert public["attribution_name"] == "Example Author"
            assert public["description"] == PICNIC["description"]
            assert "private note" not in str(public).lower()
            public_option = admin.locator(f'[data-scenario-key="example:{public["id"]}"]')
            expect(public_option).to_have_count(1)
            expect(admin.locator("#examples-status")).not_to_have_class("workspace-status status-error")
            admin.keyboard.press("Escape")
            admin.locator("#scenario-menu-btn").click()
            expect(public_option).to_be_visible()
            expect(public_option).to_contain_text("A public picnic")
            expect(admin.locator(f'[data-scenario-key="example:{loaded_scenario}"]')).to_have_attribute("aria-selected", "true")
            assert admin.evaluate("state.scenario_id") == loaded_scenario
            assert not errors
        finally:
            browser.close()


def test_public_catalog_refresh_ignores_older_responses_and_account_changes(live_browser_server):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER_ENGINE).launch(headless=True)
        page = browser.new_page()
        try:
            ready(page, live_browser_server)
            result = page.evaluate("""async () => {
                const original = apiRequest;
                const initial = state.scenarios;
                const latest = initial.map(item => ({...item, title: item.title + ' refreshed'}));
                const loaded = state.scenario_id;
                const bundle = state.bundle;
                const session = state.authSession;
                const pending = [];
                apiRequest = (path, options) => path === '/scenarios'
                  ? new Promise(resolve => pending.push(resolve)) : original(path, options);
                try {
                    const oldRefresh = refreshPublicExampleList();
                    const newRefresh = refreshPublicExampleList();
                    pending[1]({scenarios: latest});
                    await newRefresh;
                    pending[0]({scenarios: initial});
                    await oldRefresh;
                    const latestWon = state.scenarios === latest;
                    const oldAccountRefresh = refreshPublicExampleList();
                    state.authSession = {...session, user: {...session.user, id: 'another-browser-account'}};
                    renderCurationAccess();
                    pending[2]({scenarios: initial});
                    await oldAccountRefresh;
                    return {latestWon, accountFenced: state.scenarios === latest,
                        loadedUnchanged: state.scenario_id === loaded && state.bundle === bundle};
                } finally {
                    apiRequest = original;
                    state.authSession = session;
                    renderCurationAccess();
                }
            }""")
            assert result == {"latestWon": True, "accountFenced": True, "loadedUnchanged": True}
        finally:
            browser.close()
