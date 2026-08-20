"""Real-browser smoke test for the interactions described in the paper."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest


BROWSER_TESTS = (os.getenv("ABDA_BROWSER_TESTS") or "").strip() == "1"
pytestmark = pytest.mark.skipif(
    not BROWSER_TESTS,
    reason="set ABDA_BROWSER_TESTS=1 after installing the Chromium runtime",
)


def _available_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture(scope="module")
def live_demo(tmp_path_factory):
    root = Path(__file__).resolve().parents[1]
    run_dir = tmp_path_factory.mktemp("browser-smoke")
    log_path = run_dir / "server.log"
    port = _available_port()
    environment = os.environ.copy()
    environment.update(
        {
            "ABDA_ENABLE_LLM": "1",
            "ABDA_LLM_BACKEND": "ollama",
            "ABDA_OLLAMA_MODEL": "browser-smoke",
            "PYTHONUNBUFFERED": "1",
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
        deadline = time.monotonic() + 30
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


def test_paper_demo_reader_path(live_demo):
    from playwright.sync_api import expect, sync_playwright

    console_errors: list[str] = []
    page_errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on(
            "console",
            lambda message: console_errors.append(message.text)
            if message.type == "error"
            else None,
        )
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        try:
            page.goto(live_demo, wait_until="networkidle")
            expect(page.locator("#scenario-name")).to_have_text("Popov v. Hayashi")
            assert page.locator("#scenario-select option").count() == 6
            expect(page.locator("#conclusions-list .conclusion-card").first).to_be_visible()
            expect(page.locator("#facts-list .fact-card").first).to_be_visible()
            expect(page.locator("#kb-content .rule-card").first).to_be_visible()
            expect(page.locator("#right-panel")).to_be_visible()

            explain = page.locator(
                ".conclusion-card:has(.status-accepted) button[data-explain-id]"
            ).first
            expect(explain).to_be_visible()
            explain.click()
            expect(page.locator("#modal-game .modal-content")).to_be_visible()
            picker = page.locator("#modal-game .game-picker-card").first
            if picker.count():
                picker.click()
            expect(page.locator("#modal-game .game-tree")).to_be_visible()
            page.locator("#modal-game .modal-close").click()

            page.locator('.facts-filter[data-filter="assumptions"]').click()
            assumption = page.locator("#facts-list input[data-asm-id]").first
            expect(assumption).to_be_visible()
            assumption.click()
            expect(page.locator("#modal-suspend-impact .modal-content")).to_be_visible()
            page.locator("#suspend-impact-apply-btn").click()
            expect(page.locator("#modified-indicator")).to_be_visible()

            page.locator('.kb-tab[data-tab="conflicts"]').click()
            expect(page.locator("#kb-content .pref-conflict-card").first).to_be_visible()

            page.locator("#view-af-btn").click()
            expect(page.locator("#af-svg-scroll svg")).to_be_visible()
            page.locator("#modal-af .modal-close").click()

            page.locator("#aspic-btn").click()
            expect(page.locator("#aspic-pre")).not_to_have_text("")
            page.locator("#modal-aspic .modal-close").click()

            page.locator("#save-btn").click()
            expect(page.locator("#modal-save .modal-content")).to_be_visible()
            page.locator("#modal-save .modal-close").click()

            page.locator('.llm-only[onclick="openEditModal(\'add-rule\')"]').click()
            expect(page.locator("#modal-edit .modal-content")).to_be_visible()

            assert console_errors == []
            assert page_errors == []
        finally:
            browser.close()


def test_assistant_output_cannot_execute_script(live_demo):
    from playwright.sync_api import sync_playwright

    payload = """# Safe heading

<img src="/probe" onerror="window.__abdaScriptProbe=1">
<script>window.__abdaScriptProbe=2</script>
[unsafe link](javascript:window.__abdaScriptProbe=3)
"""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(live_demo, wait_until="networkidle")
            page.evaluate(
                """payload => {
                    window.__abdaScriptProbe = 0;
                    state.chatMessages = [{role: 'assistant', content: payload}];
                    state.chatPending = false;
                    renderChat();
                }""",
                payload,
            )
            page.wait_for_timeout(100)
            assert page.locator("#chat-messages h1").text_content() == "Safe heading"
            assert page.locator("#chat-messages script").count() == 0
            assert page.locator("#chat-messages [onerror]").count() == 0
            assert page.locator('a[href^="javascript:"]').count() == 0
            assert page.evaluate("window.__abdaScriptProbe") == 0
        finally:
            browser.close()
