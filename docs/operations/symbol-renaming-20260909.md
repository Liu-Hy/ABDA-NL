# Safe scenario symbol renaming

Status: implementation and local verification complete on the development
branch. Publication checks are pending. The previous unified-editor image
remains the live baseline until a verified replacement is deployed.

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

## Publication and deployment

The existing Azure management refresh token expired before this change.
Publishing a tested image does not require that token. The final image-only
deployment requires the operator to renew the dedicated Delta Azure session.
No credential is copied into the repository or requested in chat.
