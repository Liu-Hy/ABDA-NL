# Decision 0005: Browser workspace and accessible project continuity

Date: 2026-08-17

## Status

Accepted.

## Decision

ABDA-NL keeps the paper-demo explorer as the primary screen and adds one
research workspace for account, project, model-access, and MCP tasks. Bundled
examples remain anonymously readable. Saving, trial credit, sharing, and MCP
credentials require a verified account in a public deployment.

A private project is a working baseline, not only a snapshot for display.
Project-specific state, chat, and proposal endpoints load the owned project,
check its optimistic version, apply temporary operations, and use the original
bundled corpus. Saving writes the validated current scenario as the next project
version. Project corpus references must exactly match the immutable bundled
source, which prevents user-controlled file paths from reaching the corpus
loader.

The browser offers two model-access modes. Funded access uses an approved
profile and trial credit. BYOK sends a provider key only inside the current
model request. The key stays in JavaScript memory, never enters browser storage,
cookies, URLs, projects, share links, logs, or the database, and is cleared on
sign-out or reload.

Share links resolve from bearer tokens in URL fragments and present a read-only
view. The shared view disables all deterministic and LLM mutations. A signed-in
recipient may create a validated private copy without gaining access to the
owner's project.

All dialogs expose dialog semantics, trap keyboard focus while open, close with
Escape, and restore focus to their opener. The shell includes a skip link,
visible focus styles, live status announcements, reduced-motion behavior,
keyboard-focusable scrolling regions, sufficient text contrast, and narrow
screen reflow. Desktop and mobile browser workflows, plus WCAG A and AA scans,
are acceptance gates for this interface.

## Rationale

One workspace keeps account administration out of the argumentation workflow
while making durable capabilities discoverable. Treating a reopened project as
its own baseline prevents a serious semantic error where a user sees saved edits
but model calls reason over the original example.

An in-memory BYOK boundary gives registered researchers unlimited self-funded
usage without turning ABDA-NL into a credential vault. Read-only fragment links
support research sharing without exposing bearer tokens to access logs or giving
recipients mutation authority.

## Consequences

- The legacy filesystem save remains a local development API only. The public
  interface saves private database projects.
- Project model calls require the bundled source corpus to remain available.
- A project version conflict requires the user to reopen the project before
  saving again.
- Automated accessibility scans are retained as regression evidence, while
  manual keyboard and screen-reader checks remain part of release readiness.

The explorer's conclusion, evidence, and rule filters expose named button
groups and programmatic pressed state instead of communicating selection by
color alone. Search and scrollable content regions have explicit accessible
names. Each layout divider is a focusable ARIA separator that supports arrow
keys, Home, End, and a larger Shift plus arrow step while retaining pointer
dragging. Current project context and unsaved-change state use polite status
announcements.

On 2026-09-04, the first WebKit CI run exposed a serious Axe
`scrollable-region-focusable` violation in the argument graph. The graph
viewport is now a labeled keyboard-focusable region with a visible focus
outline. The follow-up
[CI run](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33858011215)
passed the complete browser journey in Chromium, Firefox, and Playwright
WebKit at source `17ef6593de0bcb9fdc213915bda83e3cf38a03bd`. The matching
[CodeQL run](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33858011673) also
passed. This automated WebKit evidence reduces Safari-engine risk but does not
replace the presentation-hardware Safari and screen-reader checks.

Source `24abcf9576dc9033a902d27a8f9b6381fee85f4e` passed the complete
[CI run](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33860765344), including
Chromium, Firefox, and Playwright WebKit, both Python versions, restricted-role
PostgreSQL, dependency audits, packaging, and the production-container smoke.
Its matching
[CodeQL run](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33860765335) passed
the enforced zero-result check.

Source `5819e8ffb291704e6ce299bda9136fff363aaddf` makes the argument graph
itself more understandable without vision. It exposes the selected graph scope
as pressed state, names every zoom control, announces zoom changes, and links
the scroll region and SVG image to a concise text summary. Its complete
[CI run](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33862091560) passed both
Python versions, restricted-role PostgreSQL, packaging, the production
container, Chromium, Firefox, Playwright WebKit, and the full history secret
scan. The matching
[CodeQL run](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33862091557) passed
the enforced zero-result check.
