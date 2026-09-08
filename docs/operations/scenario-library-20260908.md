# Create and open scenarios, September 8, 2026

Status: deployed at `https://demo.abda-nl.org`; release and public browser
acceptance passed. The healthy revision is
`abda-nl-stg-web--scenarios-54a0885`.

The initial deployment attempt waited for renewed authorization after a live
Azure read reported `AADSTS700082`, the tenant's 12-hour inactivity expiry.
The operator completed Microsoft sign-in and MFA. A subsequent live Container
Apps read verified renewed access, in addition to the cached identity check.
The agent then completed the image-only deployment without a manual gate batch.

## User experience

The new **New / Open** button sits next to the example selector. It offers:

- **New scenario**: a title, optional background, statement rows, and guided
  if/then rules. A small editable picnic example helps users get started.
  Statement meanings and connections are supplied by the user, not inferred
  by a paid model. Explicit negation, assumptions, strict rules, and multiple
  conditions are available without writing identifiers or YAML.
- **Open file**: a file picker or drop area for ABDA-NL YAML and JSON, followed
  by validation, a summary, and one **Import & open** action.
- **My projects**: the existing saved-project list.
- **Download current scenario**: a portable JSON copy of the current scenario,
  including unsaved deterministic edits, without account, chat, credential,
  billing, or sharing metadata.

Creation and import save a new private project and require sign-in, but not
trial activation or model access. Bundled examples and existing projects are
never overwritten. An unfinished builder stays in tab memory on dismissal;
reload or sign-out clears it. See the [user guide](../scenarios.md).

## Integration and safety decisions

- Reuse the existing project schema, ownership, computation limits, optimistic
  saves, sharing, and MCP authorization. No database migration is needed.
- New scenarios have no bundled source directory. Chat and reviewed edit
  proposals use the authored vocabulary and computed state, without reading
  another example's corpus. HTTP and MCP paths support the same behavior.
  Optional AI requests retain the usual billing and quota controls.
- Reset now handles a private project with no bundled source identifier.
- Preview requires a verified account and same-origin request. It is bounded
  to 1 MB of UTF-8 input and does not create a project. The data-only YAML
  loader rejects aliases, duplicate fields, custom tags, and excessive nesting.
  Scenario references and deterministic analyzability are checked before
  import. Standalone local corpus references are excluded with a warning.
- Delayed previews cannot reactivate an older file. Delayed project creation
  cannot overwrite an exploration that the user switched to in the meantime.
  Removing a statement invalidates rules that refer to it instead of silently
  redirecting those rules to a different statement.
- Browser acceptance now gives each test its own server and database. The
  larger suite otherwise shares one real login rate-limit window and can
  reject later tests on fast CI workers. Production limits are unchanged.

## Source and verification

- Initial feature checkpoint: `b228fb8508887e75a0eaefb7fcc53fac48b40170`.
- Complete candidate: `54a0885fcca3c14df5515dcf987a4ed2a5453df4`.
- Candidate tag: `service-image-scenario-library-20260908-54a0885`.
- Both checkpoints are on `Liu-Hy/ABDA-NL` development. Neither stable `main`
  branch nor the paper inputs changed.
- Local Python suite: 922 passed, 36 skipped. The separate Chromium browser
  suite passed all 35 tests with per-test server/database isolation.
- Local normal and security Ruff checks, JavaScript syntax, and diff checks
  passed. Both hash-locked dependency audits found no known vulnerabilities.
- New browser coverage exercises creation, exact export/import, saved-project
  reopening, unsaved export, Reset, invalid files, unchanged existing work,
  stale responses, escaped file content, keyboard operation, and responsive
  WCAG A/AA checks at 390, 780, and 1440 pixels.

The [image publication workflow](https://github.com/Liu-Hy/ABDA-NL/actions/runs/34275436707)
passed source verification, dependency audits, exact-image smoke, container
security checks, SBOM generation, and provenance publication. Independent
anonymous registry reads verified both manifest and config hashes, Linux
amd64, and the exact source, repository, and GPL-3.0-only labels:

```text
ghcr.io/liu-hy/abda-nl@sha256:53b52df17dbcee808d901c0d6119cf21f49dab13b69b3e3f41a1d61d0f27dc3f
```

Independent `gh attestation verify` accepted the expected
`publish-service-image.yml` signer and a GitHub-hosted runner. The verified
statement binds this digest to `54a0885fcca3c14df5515dcf987a4ed2a5453df4`.
[CodeQL](https://github.com/Liu-Hy/ABDA-NL/actions/runs/34275436612) passed.

[Development CI](https://github.com/Liu-Hy/ABDA-NL/actions/runs/34275436616)
and [tag CI](https://github.com/Liu-Hy/ABDA-NL/actions/runs/34275436765)
both passed all eight jobs: Python 3.10, Python 3.13, PostgreSQL, Chromium,
Firefox, WebKit, deployment artifacts, and secret scanning. Browser checks
include automated accessibility scans; they do not establish real-device or
assistive-technology acceptance by themselves.

The initial image from `b228fb8` is superseded, not a deployment target. Its CI
found cross-test login throttling, and the subsequent integration review
completed custom-scenario AI context and Reset support. Do not promote that
intermediate artifact just because its image publication passed.

## Live deployment and acceptance

The agent confirmed the exact subscription, tenant, and account, checked that
no deployment or manual migration job was running, and verified the healthy
previous revision `abda-nl-stg-web--layout-9c02a80`. A pre-deployment external
release check passed at `2026-09-08T20:47:15.259441+00:00`.

One Container App image update selected the published digest above and suffix
`scenarios-54a0885`. The new revision became both latest and latest-ready,
reported Healthy and Provisioned, and had one running, ready replica with zero
restarts at inspection. A private before/after comparison proved that the
application contract changed only in the image and revision suffix. Identity,
environment references, configuration, secret references, scaling, probes,
and all other template fields were preserved. No migration, provider call,
Auth0 change, DNS change, budget adjustment, or database resource change ran.

The external release checker passed again at
`2026-09-08T20:49:08.610708+00:00`: HTTPS, HTTP redirection, readiness, liveness,
security headers, policy pages, safe configuration, protected metrics, budget
invariants, and the database pool. It verified the retained 100-user trial,
$5 grant, $500 total cap, and enabled $500 OpenRouter outage boundary. Trial
spend remained 447,085 microUSD and emergency spend remained 149 microUSD;
there was one activated trial, no pending or uncertain charged reservations,
and one checked-out database connection out of five at inspection.

Public Chromium and Firefox checks each passed the existing six accessibility
scans, three viewport checks, and three keyboard checks, with zero console or
page errors. Additional live scenario-library checks in each browser passed:

- Both dialog tabs at 1440, 780, and 390 pixels, six WCAG A/AA scans per engine,
  without horizontal overflow.
- Sign-in guidance, disabled anonymous creation/import, tab-keyboard controls,
  Escape dismissal, and focus restoration.
- Starter-file download and current-example export, checking the versioned
  envelope, exact expected fields, and source-example provenance.
- Anonymous preview and import requests rejected with HTTP 401.
- Exact deployed bytes for `index.html`, `app.js`, `workspace.js`,
  `scenarios.js`, and `style.css` matching the tested source.

The public checks did not borrow a real login, modify any user's project, or
call a model. Authenticated create/import, persistence, Reset, custom-scenario
AI context, and MCP integration are covered by the source CI evidence above.
No new small manual acceptance gate is required. Users can refresh the public
page and select **New / Open** when ready to try their own scenario.

The compatible previous image remains recorded in the
[September 6 layout checkpoint](conference-layout-20260906.md). Historical
numbered gates must not be replayed against the new release. Future routine
updates use the [agent-driven handoff](agent-driven-deployment.md); Azure
session expiry may require renewed operator sign-in, not a new deployment
architecture or a copy of credentials in chat.
