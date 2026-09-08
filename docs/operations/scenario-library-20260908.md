# Create and open scenarios, September 8, 2026

Status: implemented, tested, published, and provenance-verified on `development`.
The public site has not been updated. A live Azure read reported
`AADSTS700082` because the dedicated operator session expired after the
tenant's 12-hour inactivity window. Cached account identity is not evidence
of current Azure access. No Azure resource was changed in this work.

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

## Remaining release step

The operator can renew the dedicated Azure session from an ordinary Delta
terminal using the [existing login handoff](agent-driven-deployment.md#one-interactive-authorization).
Only Microsoft sign-in and MFA require operator action. The candidate's CI,
published digest, and provenance are verified. After renewed login, the agent
can read current Azure state, perform the authorized image-only update, and
run public checks.

Do not replay historical numbered gates. Preserve current budgets, secrets,
Auth0, DNS, database, scaling, and probes. The previous last-recorded live
image is identified in the [September 6 layout checkpoint](conference-layout-20260906.md);
read current Azure state before relying on it for an update or rollback.
The public readiness endpoint returned `ready` on September 8 while this
candidate was being prepared.
