#!/usr/bin/env python3
"""Capture a public, deterministic screenshot pack for an offline presentation."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from html import escape
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit
from zipfile import ZIP_DEFLATED, ZipFile


ORIGIN = "https://demo.abda-nl.org"
SCENARIO = "popov_v_hayashi"
TOGGLE = {"op": "toggle-assumption", "id": "equity_compromise_open"}
GET_PATHS = frozenset({
    "/", "/style.css", "/app.js", "/workspace.js", "/config", "/scenarios",
    "/api/auth/session", "/vendor/dagre.min.js", "/vendor/marked.min.js",
    "/vendor/purify.min.js", "/favicon.ico",
})
FRAMES = (
    ("01-overview", "Read the scenario",
     "Popov v. Hayashi: natural-language conclusions, facts, assumptions, and rules. "
     "The argumentation engine computes the labels; this view does not use an LLM."),
    ("02-explanation", "Inspect a supporting argument",
     "Explain opens a deterministic argument for Popov's legitimate claim. "
     "Its support branch is expanded where available."),
    ("03-preview", "Preview a what-if change",
     "Activating the optional equity-compromise assumption previews the changed "
     "conclusion labels before the user applies the edit."),
    ("04-modified", "Apply the reversible change",
     "The equal-division conclusion becomes undecided under competing equity rules. "
     "The modified-state indicator distinguishes this exploration from the baseline."),
    ("05-graph", "Inspect the argument graph",
     "After Reset restores the baseline, View Graph shows arguments and attacks "
     "relevant to the key conclusions."),
    ("06-aspic", "Inspect the formal representation",
     "Show ASPIC- exposes the current scenario's formal rule representation. "
     "The screenshots end here; they are not an interactive or model-powered demo."),
)


def allowed_request(method: str, url: str, body: str | None = None) -> bool:
    """Allow only the anonymous assets and exact in-memory scenario computation."""
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https" or parsed.netloc != "demo.abda-nl.org"
        or parsed.query or parsed.fragment
    ):
        return False
    if method == "GET":
        return parsed.path in GET_PATHS
    if method != "POST" or parsed.path != "/state":
        return False
    try:
        payload = json.loads(body or "")
    except (ValueError, TypeError):
        return False
    return payload in (
        {"scenario_id": SCENARIO, "diff_ops": []},
        {"scenario_id": SCENARIO, "diff_ops": [TOGGLE]},
    )


def render_gallery(captured_at: str) -> str:
    navigation = " ".join(
        f'<a href="#{slug}">{index}</a>'
        for index, (slug, _, _) in enumerate(FRAMES, 1)
    )
    slides = "\n".join(
        f'<section id="{slug}"><h2>{index}. {escape(title)}</h2>'
        f'<p>{escape(description)}</p>'
        f'<a href="{slug}.png"><img src="{slug}.png" '
        f'alt="{escape(title, quote=True)}: {escape(description, quote=True)}"></a>'
        '<p><a href="#top">Back to navigation</a></p></section>'
        for index, (slug, title, description) in enumerate(FRAMES, 1)
    )
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self' file:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>ABDA-NL offline presentation backup</title>
<style>
body{font:18px/1.5 system-ui,sans-serif;margin:0;color:#17263c;background:#f4f6f9}
header,main{max-width:1440px;margin:auto;padding:1rem}
header{border-bottom:2px solid #a9bfd8}nav a{display:inline-block;padding:.3rem 1rem}
a{color:#134a89}a:focus-visible{outline:3px solid #ad5500;outline-offset:3px}
section{scroll-margin-top:1rem;margin:2rem 0 3rem}img{width:100%;height:auto;border:1px solid #8694a6}
.notice{background:#fff1c2;padding:.6rem}h1{font-size:1.7rem}h2{font-size:1.3rem}
@media print{header nav,section>p:last-child{display:none}section{break-inside:avoid}}
</style></head><body><header id="top">
<h1>ABDA-NL: argumentation in natural language</h1>
<p class="notice">Offline screenshot backup, not a live interactive session.
No sign-in, private project, model call, or usage charge was captured.</p>
<p>Public example captured at """ + escape(captured_at) + """ from
<a href="https://demo.abda-nl.org">demo.abda-nl.org</a>.
Open this file locally; an internet connection is not required to view the images.</p>
<nav aria-label="Screenshot navigation">""" + navigation + "</nav></header><main>" + slides + "</main></body></html>\n"


def capture(output: Path) -> Path:
    from playwright.sync_api import expect, sync_playwright

    archive = output.with_name(output.name + ".zip")
    if output.exists() or archive.exists():
        raise ValueError("choose a new output directory and archive name; nothing is overwritten")
    output.mkdir(parents=True, mode=0o700)
    captured_at = datetime.now(timezone.utc).isoformat()
    counters = {"requests": 0, "blocked": 0, "page_errors": 0}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                viewport={"width": 1440, "height": 900}, reduced_motion="reduce",
                service_workers="block", accept_downloads=False,
            )

            def guard(route):
                request = route.request
                counters["requests"] += 1
                if counters["requests"] > 40 or not allowed_request(
                    request.method, request.url, request.post_data
                ):
                    counters["blocked"] += 1
                    route.abort()
                else:
                    route.continue_()

            context.route("**/*", guard)
            page = context.new_page()
            page.set_default_timeout(15_000)
            page.on("pageerror", lambda _: counters.update(page_errors=counters["page_errors"] + 1))
            response = page.goto(ORIGIN, wait_until="domcontentloaded", timeout=30_000)
            if response is None or response.status != 200:
                raise AssertionError("the public explorer did not load")
            expect(page.locator("#scenario-select")).to_have_value(SCENARIO)
            expect(page.locator('[data-explain-id="popov_legit_claim"]')).to_be_visible()
            if page.evaluate("state.authSession.authenticated") is not False:
                raise AssertionError("capture requires an anonymous browser context")
            # Use the real keyboard control so both accepted claims fit in view.
            divider = page.locator("#h-resize-left")
            divider.press("ArrowDown")
            divider.press("ArrowDown")

            def screenshot(index: int) -> None:
                page.screenshot(path=output / (FRAMES[index][0] + ".png"), animations="disabled")

            screenshot(0)
            page.locator('[data-explain-id="popov_legit_claim"]').click()
            expect(page.locator("#modal-game .game-picker-card").first).to_be_visible()
            page.locator("#modal-game .game-picker-card").first.click()
            expect(page.locator("#modal-game .game-tree")).to_be_visible()
            supports = page.locator("#modal-game .game-supports-toggle").first
            if supports.count():
                supports.click()
                expect(supports).to_have_attribute("aria-expanded", "true")
            screenshot(1)
            page.keyboard.press("Escape")

            page.locator('.facts-filter[data-filter="assumptions"]').click()
            assumption = page.locator('[data-asm-id="equity_compromise_open"]')
            expect(assumption).not_to_be_checked()
            assumption.check()
            expect(page.locator("#modal-suspend-impact .modal-content")).to_be_visible()
            expect(page.locator("#suspend-impact-list")).to_contain_text("equal_division")
            screenshot(2)
            page.locator("#suspend-impact-apply-btn").click()
            expect(page.locator("#modified-indicator")).to_be_visible()
            if page.evaluate("state.bundle.af.labels_by_proposition.equal_division") != "undecided":
                raise AssertionError("the rehearsed equity outcome no longer matches")
            page.locator('[data-explain-id="equal_division"]').scroll_into_view_if_needed()
            screenshot(3)
            page.locator("#reset-btn").click()
            expect(page.locator("#modified-indicator")).to_be_hidden()
            if page.evaluate("state.diff_ops.length") != 0:
                raise AssertionError("Reset did not restore the baseline")

            page.locator("#view-af-btn").click()
            expect(page.locator("#af-svg-scroll svg")).to_be_visible()
            page.locator('[data-af-zoom="fit"]').click()
            screenshot(4)
            page.keyboard.press("Escape")
            page.locator("#aspic-btn").click()
            expect(page.locator("#aspic-pre")).to_contain_text("popov_legit_claim")
            page.locator("#aspic-pre .aspic-comment").filter(has_text="# Block").first.evaluate(
                "element => element.scrollIntoView({block: 'start'})"
            )
            screenshot(5)
            context.close()
            if counters["blocked"] or counters["page_errors"]:
                raise AssertionError("unexpected network activity or page error during capture")

            (output / "index.html").write_text(render_gallery(captured_at), encoding="utf-8")
            # Verify local images and navigation with networking disabled.
            offline = browser.new_context(offline=True)
            offline_page = offline.new_page()
            offline_page.set_default_timeout(15_000)
            offline_page.goto((output / "index.html").resolve().as_uri())
            expect(offline_page.locator("section")).to_have_count(len(FRAMES))
            offline_page.wait_for_function(
                "[...document.images].length === 6 && "
                "[...document.images].every(image => image.complete && image.naturalWidth > 0)"
            )
            offline_page.get_by_role("link", name="3", exact=True).click()
            if urlsplit(offline_page.url).fragment != FRAMES[2][0]:
                raise AssertionError("offline navigation failed")
            offline.close()
        finally:
            browser.close()

    manifest = {
        "captured_at": captured_at, "public_origin": ORIGIN, "scenario": SCENARIO,
        "authenticated": False, "model_called": False, "project_saved": False,
        "offline_verified": True, "request_count": counters["requests"],
        "files": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in sorted(output.iterdir()) if path.is_file()},
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    with ZipFile(archive, "x", ZIP_DEFLATED) as bundle:
        for path in sorted(output.iterdir()):
            bundle.write(path, arcname="abda-nl-offline-backup/" + path.name)
    return archive


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="new output directory")
    args = parser.parse_args()
    try:
        archive = capture(args.output)
    except Exception as exc:
        print(f"capture failed ({type(exc).__name__}); no cloud or account change was requested", file=sys.stderr)
        return 1
    print(f"offline_archive: {archive}")
    print(f"screenshots: {len(FRAMES)}")
    print("offline_loading: verified")
    print("model_called: false")
    print("result: CONFERENCE_OFFLINE_SCREENSHOT_PACK_CREATED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
