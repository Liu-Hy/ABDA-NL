# Safe scenario symbol renaming

Status: implemented, tested, and published on the personal development branch
on September 9, 2026. Not deployed. The previous unified-editor image remains
live because the dedicated Azure management session requires renewed login.

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

## Published candidate

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

## Deployment hold and resume

A real read-only Container Apps query returned `AADSTS700082`, an expired
management refresh token. Cached account metadata is not treated as proof
of an authorized live session. No Azure mutation was attempted.

Public liveness and readiness both returned HTTP 200. The live editor asset
still matched `7b0b9fd7a7a6fdf21577a6963cac60905fa82dde` byte for byte, and
the live interface still marked reference documents optional. The
[previous release record](unified-scenario-editor-20260908.md) identifies its
image and last verified revision, `abda-nl-stg-web--editor-7b0b9fd`.

The sole operator prerequisite is to run this command in a regular Delta
terminal and complete the Microsoft browser sign-in and MFA:

```bash
bash /u/haoyang/ABDA-NL/deploy/azure/agent-azure-session.sh login
```

Do not send a password, token, or MFA code to the agent. After renewal, the
agent must recheck the exact identity and settled live state, deploy the
published digest as an image-only update, compare configuration and saved
job properties, and run the automated public acceptance checks. No schema
migration, Auth0 edit, provider call, or separate manual browser gate is
required for this change. The site must not be described as upgraded until
those live checks pass.
