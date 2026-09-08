# Unified scenario editor and self-contained exchange

Status: implementation and local acceptance completed; image publication and
live rollout evidence will be recorded below after verification.

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

Pending verification of the source-bound image and healthy replacement revision.
