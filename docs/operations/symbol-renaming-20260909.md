# Safe scenario symbol renaming

Status: deployed and verified at https://demo.abda-nl.org on September 9,
2026 (America/Chicago). The renewed Azure session allowed an agent-operated
image-only update. No manual deployment step remains for this change.

## Scope and user experience

Statements and rules expose a Rename shortcut in their existing details.
One optional Rename symbol panel serves both Guided and Rule text views,
including larger scenarios without guided rows. Automatic identifiers remain
the default, and unfinished guided drafts can be renamed without an API call.
Enter applies a name; Cancel rename or Escape in the input cancels it.

Names are case-sensitive, limited to 100 ASCII identifier characters, and
unique across facts, assumptions, intermediate propositions, key conclusions,
and rules. Reserved object-property names are rejected. Error feedback is
announced and associated with the input. Long identifiers wrap on narrow screens.

## Atomicity and meaning preservation

The transformation clones the current draft before changing one dictionary
key and its exact logical references. It handles positive and negative literals
in every premise and conclusion, including rule undercuts. It never performs
substring replacement in meanings, background, attribution, or corpus text.
Metadata, priorities, suspended state, and key-conclusion membership survive.

Pending pasted glossary or changed rule text must be applied or previewed first
so the symbol list is current. A pending new name disables Preview and saving
until applied or cancelled. Successful renames invalidate the previous preview.
No project is written until the existing version-checked Save & open action.
Existing public snapshots, other projects, and source examples are not edited.

No API, database schema, provider routing, trial quota, authentication rule,
deployment setting, or corpus requirement changes. Corpus remains optional.
The previous unified-editor image remains schema-compatible with renamed
projects and is the rollback target if this UI-only release needs recovery.

## Verification

The unit suite executes the actual browser transform in Node, not a separately
implemented Python substitute. It covers incomplete drafts, no-ops, missing
or ambiguous symbols, all-section collisions, reserved and malformed names,
maximum length, exact negative references, unchanged prose, and metadata.
All symbols in each of the six bundled scenarios are renamed and inverted;
ABDA labels are compared under the same symbol mapping.

Browser coverage exercises manual creation, accessible field errors and
cancellation, mobile layout, project edits, undercuts, all metadata kinds,
pending document text, synchronized rule text, optional glossary application,
versioned saving, portable export/reimport, and the larger text-only editor.

Local backend acceptance: 1,017 passed and 45 optional browser/PostgreSQL tests
skipped. All 33 transform cases and 11 existing offline-editor tests passed.
The complete Chromium suite passed all 44 cases. The three new cases also
passed in Firefox and in a final focused Chromium run, including 100-character
symbols on a narrow screen. Ruff, application security lint, JavaScript syntax,
and whitespace checks passed. CI runs the complete three-engine browser and
PostgreSQL suites separately before deployment.

## Published release

- Source: `c6123d125c1a8310fb92867b390893e3bb191584`.
- Tag: `service-image-symbols-20260909-c6123d1`.
- Image: `ghcr.io/liu-hy/abda-nl@sha256:a5edbbae91c9eb0ed2afcba2e4e179b9388ea858d75c71f14206d04425c50d59`.
- [Source CI](https://github.com/Liu-Hy/ABDA-NL/actions/runs/34397909333)
  and [tag CI](https://github.com/Liu-Hy/ABDA-NL/actions/runs/34397926312)
  passed. Python 3.10 and 3.13 each recorded 1,017 passed and 45 opt-in
  tests skipped. Chromium, Firefox, and WebKit each passed all 44 browser
  tests. Restricted-role PostgreSQL and deployment-artifact checks passed.
- [CodeQL](https://github.com/Liu-Hy/ABDA-NL/actions/runs/34397909239)
  and [image publication](https://github.com/Liu-Hy/ABDA-NL/actions/runs/34397926357)
  passed. Runtime and development dependency audits found no known
  vulnerabilities. Exact-container smoke, PDF extraction, security scanning,
  SBOM generation, and provenance signing passed.
- Independent anonymous registry verification checked manifest and config
  hashes, Linux/amd64, the exact source revision, source repository, and
  GPL-3.0-only label. Independent attestation verification required the
  exact source digest and tag, expected publishing workflow, and hosted runner.
- Stable main remains unchanged on both public remotes at
  `e4be41c72f34dd555147a2de221d84b3fd735c9f`.

## Live deployment and acceptance

The earlier `AADSTS700082` management-token expiry was resolved by the
operator's renewed login. The agent verified the exact account, tenant,
subscription, and a real Container Apps read before changing anything.
The previous healthy revision was `abda-nl-stg-web--editor-7b0b9fd`.

- New healthy revision: `abda-nl-stg-web--symbols-c6123d1`, with one ready
  replica and zero restarts at acceptance. Single-revision mode retained
  the old revision until the replacement was ready.
- Structural before/after comparison proved that only the container image
  and revision suffix changed. Application configuration, environment,
  workload profile, identity, secret references, and saved migration-job
  properties were unchanged. No migration ran.
- All three changed public assets, HTML, scenario JavaScript, and CSS,
  matched the reviewed source bytes. Canonical HTTP payload hashes for
  all six bundled scenarios were unchanged.
- The external release checker passed at `2026-09-09T20:12:18Z`: TLS, HTTP
  redirection, liveness, readiness, policies, security headers, public config,
  protected metrics, database pool, and budget invariants. Both the custom
  and generated Azure origins were ready.
- Trial settings remain 100 users, $5 each, $500 total. OpenRouter failover
  remains enabled with its $500 cap. The database pool reported one checked-out
  connection out of five. No provider call was made for deployment acceptance.
- Chromium and Firefox each passed six general accessibility scans, three
  viewport checks, and three keyboard checks. An initial Chromium pass
  reported one unspecified console error. An instrumented repeat passed
  all the same checks with no console, page, HTTP, or failed-request errors;
  the error was not reproduced and no application change was made for it.
- Both browsers also passed three additional editor/import accessibility
  scans, mobile overflow checks, keyboard focus return, and anonymous
  rename/save restrictions. The served rename transform correctly updated
  positive references and negative rule undercuts, rejected four invalid or
  colliding names, and preserved document prose and its input. These checks
  reported no browser errors.
- Live acceptance used public data and isolated anonymous browser contexts.
  No authentication was bypassed and no real private project was changed.
  Authenticated create, rename, save, conflict, and portable round-trip
  behavior were already covered by the exact-source three-browser CI suite.

The [previous unified-editor image](unified-scenario-editor-20260908.md)
remains the compatible rollback target. No separate manual browser gate is
required for this UI-only release. Corpus remains optional, and administrator
publication behavior is unchanged.
