# Unified scenario editor and self-contained exchange

Status: deployed and verified at https://demo.abda-nl.org on September 8,
2026 (America/Chicago). No manual deployment step remains for this change.

## Design and correctness

New scenario and Import scenario initialize the same draft. Guided statements
and rule text are views inside the knowledge base, not separate workflows.
Statement descriptions are the glossary. Documents are shared across both
views and remain AI context, never unreviewed logical facts or rules.

The editor handles private project updates through the existing optimistic
version check. A changed view, stale version, invalid rule, or failed file
does not replace newer saved work. Drafts are cleared on account changes.
Import stages all selected materials before changing the draft. The preview
uses the existing ABDA engine and requires no model call or trial activation.
Any draft edit invalidates the save preview.

Rule-text conversion preserves surviving identifiers, meanings, negative
meanings, categories, attribution, priorities, suspension, and focus choices.
Native ABDA blank-line preference groups are interpreted in increasing strength;
explicit viewer block markers override blank-line grouping. The ASPIC- viewer
now emits assumption priorities as well as rule priorities.

## Self-contained exports

Version 3 JSON carries the complete normalized scenario and reference text,
with no source-server dependency. All bundled corpus files are embedded, and
curated context is retained separately as ABDA-curated-context.txt. PDFs carry
full extracted text, not their binary file, page layout, or figures. This is
consistent with the existing text-only storage of uploaded PDFs. The exporter
does not substitute excerpts or curated summaries for full document text.

Only the trusted catalog manifest can resolve server files. No arbitrary paths
or URLs are read. Immutable bundled extraction is serialized and cached.
User PDF uploads retain their isolated worker and existing resource limits.
An anonymous export request operates only on the supplied browser scenario
and public bundled files, never on private project identifiers. Same-origin
and rate-limit protections apply; private preview and saving require verified
authentication. Payloads and credentials are not logged.

References are bounded by 20 documents, 250,000 characters each, and 750 KB of
UTF-8 text in total. Normalization also proves that all content, including
bundled files, fits the 1 MB portable export limit. This is checked before a
project is saved. The document-preview limit is 40 requests per minute per user,
allowing a complete 20-document batch without an unavoidable mid-batch throttle.
Upload limits remain 1 MB per file, 40 PDF pages, and the existing bounded worker.

Versions 1 and 2 still import with their historical provenance semantics;
only version 3 guarantees independence from built-in materials. New imports
and exports do not require a schema migration or an object-storage service.

## Compatibility and rollout scope

Database head remains 20260908_0005. Once references exceed old parser limits,
the previous material image is not a compatible rollback target. Recover with
this source or a newer compatible image, never by stripping user documents.
All six bundled HTTP scenario payloads remain unchanged.

This release is on the personal development branch. Stable main and the
camera-ready repository remain untouched. Deployment is an image-only update;
it does not change secrets, Auth0, DNS, scaling, probes, admin roles, trial
limits, routing, or the saved migration job.

## Verification

Tests cover all six examples exported with full reference text and restored
against an empty catalog. They compare all facts, rules, meanings, priorities,
full document text, and computed AFs. A separate HTTP test imports, saves,
reopens, and re-exports Popov without access to its original built-in data.
Browser tests cover text-first authoring, guided/text switching, linked
glossaries, multi-file atomicity, preview invalidation, stale saves, private
materials, sharing, downloads, accessibility, and mobile layout.

See [the scenario guide](../scenarios.md) for user-facing instructions.

## Publication and live receipt

- Application source: `7b0b9fd7a7a6fdf21577a6963cac60905fa82dde`.
- Image: `ghcr.io/liu-hy/abda-nl@sha256:142e19069253fc629fa0b5ee2ef4c54f40374ba0ad1fdeb688c4efd527debced`.
- Healthy revision: `abda-nl-stg-web--editor-7b0b9fd`, one ready replica,
  zero restarts at acceptance. Previous revision:
  `abda-nl-stg-web--materials-995c83c`.
- [Source CI](https://github.com/Liu-Hy/ABDA-NL/actions/runs/34292771963)
  and [tag CI](https://github.com/Liu-Hy/ABDA-NL/actions/runs/34292789727)
  passed. Python acceptance recorded 984 passed and 42 opt-in tests skipped;
  separate Chromium, Firefox, and WebKit jobs each passed all 41 browser tests.
  Restricted-role PostgreSQL acceptance also passed independently.
- [CodeQL](https://github.com/Liu-Hy/ABDA-NL/actions/runs/34292772054)
  and [image publication](https://github.com/Liu-Hy/ABDA-NL/actions/runs/34292789775)
  passed. Dependency audits reported no known vulnerabilities. Exact-container
  smoke included PDF extraction. Container security, SBOM, and signed
  provenance checks passed.
- Anonymous registry access verified the image and configuration hashes,
  Linux/amd64 platform, source commit, and GPL-3.0-only label. Independent
  attestation verification required this exact source, the expected publisher
  workflow, and a hosted runner.
- Structural before/after comparison proved that only the web image and
  revision suffix changed. The environment, identity, application configuration,
  and saved migration-job properties were identical. No migration ran.
- All nine checked public application assets matched the reviewed source
  bytes. Canonical HTTP payload hashes for all six bundled scenarios remained
  unchanged.
- Exported all six scenarios through the live HTTPS API, then imported each
  into an empty local catalog with original-source lookups prohibited. All
  facts, rules, meanings, full reference text, and computed AFs matched.
  Re-export produced the identical version 3 envelope. The Popov export
  contained five documents and 195,065 bytes of reference text, including
  the full extracted text of its longer PDF.
- Live private-preview endpoints rejected anonymous requests with 401.
  Cross-origin editor and export requests were rejected with 403. Export
  responses used no-store caching. Both public HTTPS origins remained ready.
- Live Chromium and Firefox each passed the existing six accessibility scans,
  three viewport checks, and three keyboard checks. Each also passed three
  new editor/import scans, a real version 3 browser download, mobile overflow
  checks, anonymous editing restrictions, and read-only public glossaries.
  Neither browser reported a page or console error.
- The external release checker passed at `2026-09-09T00:06:52Z`: TLS, HTTP
  redirection, readiness, liveness, security headers, policies, public config,
  protected metrics, database pool, and budget invariants. Trial settings remain
  100 users, $5 each, $500 total. OpenRouter failover remains enabled with a
  $500 cap. No model provider was called during live rollout verification.
- No real account, private project, or identity-provider setting was modified
  by these checks. Stable main was verified unchanged on both public remotes
  at `e4be41c72f34dd555147a2de221d84b3fd735c9f`.

Authenticated creation, import, edit, save conflicts, sharing, and offline
HTTP persistence were exercised against isolated test accounts in CI. Live
checks did not impersonate an operator or require another email sign-in.
