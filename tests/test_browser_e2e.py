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


@pytest.fixture(scope="module")
def live_browser_server(tmp_path_factory):
    root = Path(__file__).resolve().parents[1]
    state_root = tmp_path_factory.mktemp("browser-state")
    log_path = state_root / "server.log"
    port = _available_port()
    environment = os.environ.copy()
    environment.update(
        {
            "XDG_STATE_HOME": str(state_root),
            "ABDA_ENVIRONMENT": "development",
            "ABDA_AUTH_MODE": "dev",
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
    page.goto(url, wait_until="domcontentloaded")
    _wait_for_demo_ready(page)


def _reload_ready_demo(page) -> None:
    page.reload(wait_until="domcontentloaded")
    _wait_for_demo_ready(page)


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
                    if (state.bundle.af.arguments?.[0]) {
                      state.bundle.af.arguments[0].conclusion_nl = probe;
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
            page.wait_for_timeout(100)
            assert page.evaluate("window.__abdaXssFired") == 0
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
                expect(shared_page.locator("#global-status")).to_contain_text(
                    "Chat and edits are disabled in a shared read-only view."
                )
                expect(shared_page.locator("#modal-workspace .modal-content")).to_be_hidden()
            finally:
                shared_context.close()
            page.keyboard.press("Escape")

            ai_access_button = page.locator("#ai-access-btn")
            ai_access_button.click()
            expect(page.locator("#workspace-panel-ai")).to_be_visible()
            page.locator('input[name="ai-mode"][value="byok"]').check()
            page.locator("#byok-provider-select").select_option("openrouter")
            page.locator("#byok-model-select").select_option("gemini-3.7-flash")
            page.locator("#byok-api-key").fill("browser-only-placeholder-key")
            page.locator("#ai-access-form button[type=submit]").click()
            expect(page.locator("#ai-access-status")).to_contain_text(
                "applied to this browser tab"
            )
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
            overflow = page.evaluate(
                "Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) "
                "- window.innerWidth"
            )
            assert overflow <= 1
            page.locator("#workspace-btn").click()
            expect(dialog).to_be_visible()
            _axe_report(page, "mobile workspace")
            _save_browser_evidence(page, "mobile-workspace")
            page.locator("#logout-btn").click()
            expect(page.locator("#global-status")).to_contain_text("Signed out")
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
