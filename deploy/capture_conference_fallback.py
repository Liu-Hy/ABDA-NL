#!/usr/bin/env python3
"""Capture an anonymous, deterministic screenshot pack for an offline presentation."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from html import escape
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit
from zipfile import ZIP_DEFLATED, ZipFile


ORIGIN = "https://demo.abda-nl.org"
SCENARIO = "popov_v_hayashi"
TOGGLE = {"op": "toggle-assumption", "id": "equity_compromise_open"}
GET_PATHS = frozenset({
    "/", "/style.css", "/chat-exploration.css", "/ui-shell.css", "/authoring.css",
    "/workspace.css", "/app.js", "/conversation-storage.js", "/composer.js",
    "/exploration.js", "/source-reader.js", "/workspace.js", "/scenarios.js",
    "/materials.js", "/curation.js", "/ui-shell.js", "/argument-navigation.js",
    "/config", "/scenarios",
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
    ("05-graph", "Inspect the conclusion graph",
     "After Reset restores the baseline, Conclusion graph groups arguments by "
     "their conclusions and displays the relevant attacks."),
    ("06-aspic", "Inspect the formal representation",
     "ASPIC- text exposes the current scenario's formal rule representation. "
     "The screenshots end here; they are not an interactive or model-powered demo."),
)


def validate_base_url(value: str) -> str:
    """Accept the hosted origin or a literal loopback HTTP origin with a port."""
    if not isinstance(value, str) or any(char.isspace() or ord(char) < 32 for char in value):
        raise ValueError("base URL must be a canonical hosted or loopback origin")
    parsed = urlsplit(value)
    if parsed.path not in {"", "/"} or "?" in value or "#" in value:
        raise ValueError("base URL cannot include a path, query, or fragment")
    origin = value.removesuffix("/")
    if origin == ORIGIN:
        return origin
    port = parsed.port
    if (
        parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "::1"}
        or port is None or not 1 <= port <= 65535
    ):
        raise ValueError("local captures require an HTTP loopback address with an explicit port")
    host = "[::1]" if parsed.hostname == "::1" else "127.0.0.1"
    if origin != f"http://{host}:{port}":
        raise ValueError("base URL cannot contain credentials or an alternate host spelling")
    return origin


def allowed_request(
    method: str, url: str, body: str | None = None, *, base_url: str = ORIGIN,
) -> bool:
    """Allow only the anonymous assets and exact in-memory scenario computation."""
    try:
        origin = urlsplit(validate_base_url(base_url))
        parsed = urlsplit(url)
    except (TypeError, ValueError):
        return False
    if (
        parsed.scheme != origin.scheme or parsed.netloc != origin.netloc
        or "?" in url or "#" in url or any(char.isspace() or ord(char) < 32 for char in url)
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


def render_gallery(captured_at: str, base_url: str = ORIGIN) -> str:
    origin = validate_base_url(base_url)
    origin_note = (
        "Captured from the public service."
        if origin == ORIGIN else
        "Captured from a local candidate. This does not show that the public service was updated."
    )
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
<p>Included Popov example captured at """ + escape(captured_at) + """ from
<code>""" + escape(origin) + "</code>. " + origin_note + """
Open this file locally; an internet connection is not required to view the images.</p>
<nav aria-label="Screenshot navigation">""" + navigation + "</nav></header><main>" + slides + "</main></body></html>\n"


def capture_tool_source() -> dict:
    """Identify this capture checkout, without claiming it identifies a server."""
    script = Path(__file__).resolve()
    try:
        revision = subprocess.run(
            ["git", "-C", str(script.parent.parent), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        dirty = bool(subprocess.run(
            ["git", "-C", str(script.parent.parent), "status", "--porcelain", "--untracked-files=no"],
            check=True, capture_output=True, text=True, timeout=5,
        ).stdout.strip())
    except (OSError, subprocess.SubprocessError):
        revision, dirty = None, None
    return {
        "capture_tool_revision": revision,
        "capture_tool_worktree_dirty": dirty,
        "capture_tool_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
    }


def capture(output: Path, base_url: str = ORIGIN) -> Path:
    base_url = validate_base_url(base_url)
    archive = output.with_name(output.name + ".zip")
    if output.exists() or archive.exists():
        raise ValueError("choose a new output directory and archive name; nothing is overwritten")
    from playwright.sync_api import expect, sync_playwright

    output.mkdir(parents=True, mode=0o700)
    captured_at = datetime.now(timezone.utc).isoformat()
    tool_source = capture_tool_source()
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
                    request.method, request.url, request.post_data, base_url=base_url,
                ):
                    counters["blocked"] += 1
                    route.abort()
                else:
                    route.continue_()

            context.route("**/*", guard)
            page = context.new_page()
            page.set_default_timeout(15_000)
            page.on("pageerror", lambda _: counters.update(page_errors=counters["page_errors"] + 1))
            response = page.goto(base_url, wait_until="domcontentloaded", timeout=30_000)
            if response is None or response.status != 200:
                raise AssertionError("the anonymous explorer did not load")
            expect(page.locator("#scenario-name")).to_have_text("Popov v. Hayashi")
            expect(page.locator('[data-explain-id="popov_legit_claim"]')).to_be_visible()
            if page.evaluate("state.scenario_id") != SCENARIO:
                raise AssertionError("capture requires the included Popov example")
            if page.evaluate("state.authSession.authenticated") is not False:
                raise AssertionError("capture requires an anonymous browser context")
            # Reserve room, then frame the accepted claims within the key list.
            divider = page.locator("#h-resize-left")
            divider.press("ArrowDown")
            divider.press("ArrowDown")
            expect(page.locator('.concl-filter[data-filter="key"]')).to_have_attribute("aria-pressed", "true")
            page.locator('[data-explain-id="hayashi_legit_claim"]').evaluate(
                "button => button.closest('.conclusion-card').scrollIntoView({block: 'end', inline: 'nearest', behavior: 'instant'})"
            )
            for claim in ("popov_legit_claim", "hayashi_legit_claim"):
                expect(page.locator(f'[data-explain-id="{claim}"]')).to_be_in_viewport(ratio=1)

            def screenshot(index: int) -> None:
                page.screenshot(path=output / (FRAMES[index][0] + ".png"), animations="disabled")

            screenshot(0)
            page.locator('[data-explain-id="popov_legit_claim"]').click()
            expect(page.locator("#modal-game .modal-content")).to_be_visible()
            picker = page.locator("#modal-game .game-picker-card").first
            if picker.count():
                picker.click()
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
            formal_claim = page.locator("#aspic-pre .aspic-name").filter(has_text="[cs6]")
            formal_claim.evaluate("element => element.scrollIntoView({block: 'center'})")
            expect(formal_claim).to_be_in_viewport(ratio=1)
            screenshot(5)
            context.close()
            if counters["blocked"] or counters["page_errors"]:
                raise AssertionError("unexpected network activity or page error during capture")

            (output / "index.html").write_text(render_gallery(captured_at, base_url), encoding="utf-8")
            # Verify local images and navigation with networking disabled.
            offline = browser.new_context(offline=True)
            offline_page = offline.new_page()
            offline_page.set_default_timeout(15_000)
            offline_page.goto((output / "index.html").resolve().as_uri(), wait_until="load")
            expect(offline_page.locator("section")).to_have_count(len(FRAMES))
            expect(offline_page.locator("img")).to_have_count(len(FRAMES))
            if not offline_page.locator("img").evaluate_all(
                "images => images.every(image => image.complete && image.naturalWidth > 0)"
            ):
                raise AssertionError("offline images did not load")
            offline_page.get_by_role("link", name="3", exact=True).click()
            if urlsplit(offline_page.url).fragment != FRAMES[2][0]:
                raise AssertionError("offline navigation failed")
            offline.close()
        finally:
            browser.close()

    manifest = {
        "captured_at": captured_at, "captured_origin": base_url, "scenario": SCENARIO,
        "capture_kind": "public_service" if base_url == ORIGIN else "local_candidate",
        **tool_source,
        "source_note": "Capture-tool checkout only; the served application revision is not asserted.",
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
    parser.add_argument(
        "--base-url", type=validate_base_url, default=ORIGIN,
        help="hosted origin (default), or HTTP 127.0.0.1 / [::1] with an explicit port",
    )
    args = parser.parse_args()
    try:
        archive = capture(args.output, base_url=args.base_url)
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
