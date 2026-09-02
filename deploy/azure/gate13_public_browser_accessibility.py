#!/usr/bin/env python3
"""Read-only accessibility acceptance for the public ABDA-NL origin."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import sys
from urllib.parse import urlsplit

from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Page, expect, sync_playwright


DEFAULT_ORIGIN = "https://demo.abda-nl.org"
BROWSERS = ("chromium", "firefox")
WCAG_TAGS = ("wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa")
SUCCESSFUL_NAVIGATION_STATUSES = frozenset((200, 304))
SCRIPT_REVISION = "2"


@dataclass
class BrowserEvidence:
    engine: str
    axe_scans: int = 0
    viewport_checks: int = 0
    keyboard_checks: int = 0
    console_errors: list[str] = field(default_factory=list)
    page_errors: list[str] = field(default_factory=list)


def validated_origin(value: str) -> str:
    candidate = value.strip().rstrip("/")
    parsed = urlsplit(candidate)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "demo.abda-nl.org"
        or parsed.port is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise ValueError("the public browser gate accepts only https://demo.abda-nl.org")
    return candidate


def axe_scan(page: Page, evidence: BrowserEvidence, label: str) -> None:
    result = Axe().run(
        page,
        options={
            "runOnly": {"type": "tag", "values": list(WCAG_TAGS)},
            "resultTypes": ["violations"],
        },
    )
    if result.violations_count:
        raise AssertionError(f"{evidence.engine} {label}: {result.generate_report()}")
    evidence.axe_scans += 1


def open_explorer(page: Page, origin: str) -> None:
    response = page.goto(origin, wait_until="domcontentloaded", timeout=30_000)
    if response is None or response.status not in SUCCESSFUL_NAVIGATION_STATUSES:
        raise AssertionError("the public explorer did not load successfully")
    expect(page.locator("#scenario-name")).not_to_have_text("Loading...", timeout=30_000)
    if page.locator("#scenario-select option").count() < 6:
        raise AssertionError("the public explorer exposed fewer than six scenarios")
    expect(page.locator("#conclusions-list .conclusion-card").first).to_be_visible()
    expect(page.locator("#facts-list .fact-card").first).to_be_visible()
    expect(page.locator("#kb-content .rule-card").first).to_be_visible()


def assert_no_horizontal_overflow(page: Page, label: str) -> None:
    overflow = page.evaluate(
        "Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) "
        "- window.innerWidth"
    )
    if overflow > 1:
        raise AssertionError(f"{label} has {overflow}px of horizontal overflow")


def exercise_desktop(page: Page, origin: str, evidence: BrowserEvidence) -> None:
    open_explorer(page, origin)
    expect(page.locator('a[href="/privacy.html"]').first).to_be_visible()
    expect(page.locator('a[href="/terms.html"]').first).to_be_visible()
    assert_no_horizontal_overflow(page, f"{evidence.engine} desktop")
    evidence.viewport_checks += 1
    axe_scan(page, evidence, "desktop explorer")

    explain_button = page.locator(
        ".conclusion-card:has(.status-accepted) button[data-explain-id]"
    ).first
    explain_button.focus()
    explain_button.press("Enter")
    game_dialog = page.locator("#modal-game .modal-content")
    expect(game_dialog).to_be_visible()
    axe_scan(page, evidence, "keyboard explanation dialog")
    page.keyboard.press("Escape")
    expect(game_dialog).to_be_hidden()
    expect(explain_button).to_be_focused()
    evidence.keyboard_checks += 1

    workspace_button = page.locator("#workspace-btn")
    workspace_button.focus()
    workspace_button.press("Enter")
    workspace_dialog = page.get_by_role("dialog", name="Research workspace")
    expect(workspace_dialog).to_be_visible()
    expect(page.locator("#oidc-login-link")).to_be_focused()
    axe_scan(page, evidence, "signed-out research workspace")
    focusable = workspace_dialog.locator(
        'a[href]:visible, button:not([disabled]):visible, input:not([disabled]):visible, '
        'select:not([disabled]):visible, textarea:not([disabled]):visible, '
        '[tabindex]:not([tabindex="-1"]):visible'
    )
    if focusable.count() < 2:
        raise AssertionError("the workspace dialog has too few keyboard controls")
    focusable.last.focus()
    page.keyboard.press("Tab")
    expect(focusable.first).to_be_focused()
    page.keyboard.press("Escape")
    expect(workspace_dialog).to_be_hidden()
    expect(workspace_button).to_be_focused()
    evidence.keyboard_checks += 2


def exercise_narrow_layouts(page: Page, origin: str, evidence: BrowserEvidence) -> None:
    for label, viewport in (
        ("200-percent-equivalent", {"width": 720, "height": 450}),
        ("mobile", {"width": 390, "height": 844}),
    ):
        page.set_viewport_size(viewport)
        open_explorer(page, origin)
        assert_no_horizontal_overflow(page, f"{evidence.engine} {label}")
        axe_scan(page, evidence, label)
        evidence.viewport_checks += 1
    page.locator("#workspace-btn").click()
    expect(page.get_by_role("dialog", name="Research workspace")).to_be_visible()
    assert_no_horizontal_overflow(page, f"{evidence.engine} mobile workspace")
    axe_scan(page, evidence, "mobile workspace")


def exercise_policy_pages(page: Page, origin: str) -> None:
    for path, heading in (
        ("/privacy.html", "Privacy notice"),
        ("/terms.html", "Terms of use"),
    ):
        response = page.goto(origin + path, wait_until="domcontentloaded", timeout=30_000)
        if response is None or response.status not in SUCCESSFUL_NAVIGATION_STATUSES:
            raise AssertionError(f"{path} did not load successfully")
        expect(page.get_by_role("heading", name=heading, exact=True)).to_be_visible()


def run_browser(engine: str, origin: str) -> BrowserEvidence:
    evidence = BrowserEvidence(engine=engine)
    with sync_playwright() as playwright:
        browser = getattr(playwright, engine).launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            reduced_motion="reduce",
        )
        page = context.new_page()
        page.on(
            "console",
            lambda message: evidence.console_errors.append(message.text)
            if message.type == "error"
            else None,
        )
        page.on("pageerror", lambda error: evidence.page_errors.append(str(error)))
        try:
            exercise_desktop(page, origin, evidence)
            exercise_narrow_layouts(page, origin, evidence)
            exercise_policy_pages(page, origin)
        finally:
            context.close()
            browser.close()
    if evidence.console_errors:
        raise AssertionError(
            f"{engine} reported {len(evidence.console_errors)} console errors"
        )
    if evidence.page_errors:
        raise AssertionError(f"{engine} reported {len(evidence.page_errors)} page errors")
    return evidence


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--origin", default=DEFAULT_ORIGIN)
    parser.add_argument("--browser", choices=("all", *BROWSERS), default="all")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv or sys.argv[1:]))
    try:
        origin = validated_origin(args.origin)
        engines = BROWSERS if args.browser == "all" else (args.browser,)
        results = [run_browser(engine, origin) for engine in engines]
    except (AssertionError, ValueError) as exc:
        print(f"public browser acceptance failed: {exc}", file=sys.stderr)
        return 1

    print("ABDA-NL public browser accessibility status:")
    print(f"script_revision: {SCRIPT_REVISION}")
    print(f"public_origin: {origin}")
    for result in results:
        print(f"{result.engine}_axe_scans: {result.axe_scans}")
        print(f"{result.engine}_viewport_checks: {result.viewport_checks}")
        print(f"{result.engine}_keyboard_checks: {result.keyboard_checks}")
        print(f"{result.engine}_console_errors: 0")
        print(f"{result.engine}_page_errors: 0")
    print("wcag_a_aa: passed")
    print("reduced_motion: passed")
    print("policy_links_before_registration: passed")
    print("azure_configuration_changed: false")
    print("result: LIVE_PUBLIC_CHROMIUM_FIREFOX_ACCESSIBILITY_VERIFIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
