# Conference layout and offline backup, September 6, 2026

Status: image-only repair deployed, public release and browser checks passed,
and the offline screenshot backup generated from the repaired public service.
No operator Cloud Shell command or additional browser account test is needed.

## Current application identity

- Source: `9c02a804a20e6f2083610846c9da70f6f1af051a`.
- Image: `ghcr.io/liu-hy/abda-nl@sha256:4ce7efdb7abd25a0252f1fe634941529d7188c18e62a98e5b60ea88e88940d9a`.
- Tag: `service-image-conference-layout-20260906-9c02a80`.
- Healthy revision: `abda-nl-stg-web--layout-9c02a80`.
- Public origin: `https://demo.abda-nl.org`.
- Previous compatible image: `sha256:b7025d4322e05a698e79eb120a233c68cf638d5cdd44c8f58223681ff15ae1c5`.

This supersedes only the application image and revision in the earlier
[public promotion record](public-release-20260906.md). Its 100-user trial,
$5 grant, $500 total cap, and enabled $500 OpenRouter outage boundary remain
unchanged. Stable `main` and the paper inputs were not edited.

## Defect and repair

Visual inspection of the first offline capture revealed vertically clipped
conclusion labels. A fresh public browser confirmed three cards with 46 pixels
of label content but only 30 pixels of available label height. The flex column
was shrinking cards that also used `overflow: hidden` for rounded corners.

Adding `flex-shrink: 0` to `.conclusion-card` lets each card retain its content
height while the existing conclusion list scrolls normally. The complete
application diff from the preceding deployed source is this one CSS line.
No backend, dependency, schema, prompt, or billing code changed.

The regression test checks every conclusion label at 1440 by 900, 1000 by 720,
and 390 by 844, with the evidence panel reduced to its minimum height where
the divider is visible. The new test runs in Chromium, Firefox, and WebKit.

## Build and deployment evidence

- [Development CI](https://github.com/Liu-Hy/ABDA-NL/actions/runs/34053160810)
  and [tag CI](https://github.com/Liu-Hy/ABDA-NL/actions/runs/34053161007)
  passed all eight jobs each. Python 3.13 recorded 890 passed and 30 skipped;
  the separate Chromium browser job passed 29 real-browser tests. Python 3.10,
  PostgreSQL, Firefox, WebKit, secret scanning, and deployment artifacts passed.
- [CodeQL](https://github.com/Liu-Hy/ABDA-NL/actions/runs/34053160843) passed.
- [Image publication](https://github.com/Liu-Hy/ABDA-NL/actions/runs/34053160952)
  passed source tests, dependency audits, exact-image smoke, container scans,
  retained license checks, SBOM generation, and provenance attestation.
- Anonymous registry reads verified the manifest and config hashes, Linux
  amd64 platform, exact source label, repository label, and GPL-3.0-only label.
  Independent `gh attestation verify` accepted the expected GitHub workflow
  and hosted runner. The verified statement names the exact image digest and
  resolves its source dependency to `9c02a804a20e6f2083610846c9da70f6f1af051a`.
- The agent read live Azure state, saved a private before-state snapshot,
  checked the healthy current revision and absence of conflicting deployments
  or running migration jobs, then submitted one image-only update. It waited
  for the new revision to become both latest and ready. The revision reported
  Healthy and Provisioned. A canonical before/after comparison preserved the
  configurable application contract except image and revision suffix.

The first post-deployment metrics read omitted Azure CLI's `--show-values`
option and therefore returned no credential. The already healthy deployment
was not repeated. A corrected, captured-output read loaded only the metrics
credential into private process memory, then completed the external checker at
`2026-09-06T19:02:28.361747+00:00`.

HTTPS, security headers, readiness, liveness, policy pages, safe configuration,
protected metrics, public caps, and database-pool checks passed. Trial spend
remained 447,085 microUSD and emergency spend remained 149 microUSD. There was
one activated account and no uncertain charged reservation. The pool reported
two checked-out connections out of five while browser checks were running.
The checker also required reconciled, idle budget reservations.

Fresh public Chromium and Firefox acceptance each passed six WCAG scans,
three viewport checks, and three keyboard checks with zero page or console
errors. A public CSS download matched the tested source bytes exactly.
Earlier verified authentication, BYOK, MCP, privacy, sanitized-log, and alert
evidence remains applicable because those paths did not change. No model call,
migration, secret rotation, budget change, Auth0 edit, DNS edit, or database
resource change was performed in this repair.

## Offline backup artifact

The tracked generator is
[`deploy/capture_conference_fallback.py`](../../deploy/capture_conference_fallback.py).
It uses a new anonymous browser and restricts outgoing requests to the fixed
public assets, anonymous session read, and exact Popov baseline or equity-toggle
computation. Eighteen unit tests cover that boundary and the static gallery.

The final capture was made at `2026-09-06T19:02:26.924059+00:00`, after the new
revision became ready. It made 13 allowed requests, saved six screenshots,
checked the actual undecided equity outcome and Reset behavior, and verified
local gallery loading and navigation with networking disabled. The images
were visually reviewed. The final ZIP passed CRC and per-file SHA-256 checks.

Local artifact in the Delta checkout:

```text
artifacts/conference/20260906-layout-9c02a80.zip
SHA-256: 24bb3eda49bb22a77170bf8f408c555adff33fd81ef2c9a58e68d9a20cae2351
```

Extract the ZIP on the presentation laptop and open
`abda-nl-offline-backup/index.html`. No server or internet is needed. The
gallery explicitly identifies screenshots rather than simulating a live demo.
It contains no private project, login session, provider credential, or model
answer. The generator is committed; captures remain in gitignored local
`artifacts/`, not in the source repository or public web application.

Copying this backup to the actual presentation computer, Safari and assistive
technology checks, the laptop tunnel, the two narrated rehearsals, the recovery
tabletop, and any required institutional policy review still need the relevant
people or hardware. This artifact is not a substitute for those checks.
