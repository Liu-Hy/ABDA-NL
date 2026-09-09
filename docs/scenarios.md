# Your own scenarios

Select **New / Open** beside the scenario selector. Sign in to save private
work. Creating, importing, editing, previewing, and exporting scenarios do not
require an API key, trial activation, or a model call.

## One editor, two ways to start

**New scenario** starts with a guided editor. **Import scenario** loads existing
materials into that same editor. Switching entry points does not discard the
draft or create a second copy.

1. Give the scenario a title and optional background.
2. In **Statements & glossary**, write each statement in plain English. A
   **Fact** is given, an **Assumption** is defeasible, and a **Claim** follows
   from rules. Check **Key conclusion** on claims to feature in the explorer.
   These descriptions are the glossary, not a duplicate set of labels.
3. Connect statements with rules. **If** and **+ Condition** specify premises
   joined by AND. **Conclude** specifies what follows. **Usually (defeasible)**
   permits competing arguments; **Always (strict)** makes a strict rule.
   Negative choices use explicit negation. Removing all conditions creates
   an empty-premise rule.
4. Optionally add **Reference documents**. Review their text before saving.
   They provide AI context and citations, not extra logical facts or rules.
5. Select **Preview** to see actual ABDA results and rules in plain language.
   Then **Save & open** saves a private project and opens it for exploration.
   Editing anything invalidates the preview until you check it again.

**Try a small example** starts a new draft with two competing picnic rules.
**Clear draft** starts over after confirmation. **Symbol & details** preserves
identifiers, categories, attribution, and explicit negative meanings.
**Priority & details** exposes defeasible priority and active state. Higher
numbered priorities are stronger.

### Choose or rename symbols

Automatic names work without any extra setup. To choose a readable identifier,
open **Symbol & details** on a statement, or **Priority & details** on a rule,
and select **Rename**. Alternatively, expand **Rename symbol** inside the
knowledge base in either Guided or Rule text view. Select the existing symbol,
enter its new name, and select **Rename** (or press Enter in the name field).

Names use 1 to 100 letters, digits, or underscores, beginning with a letter or
underscore. They are case-sensitive and must be unique across all statements
and rules. Reserved object-property names are rejected. A leading minus is
negation, not part of the name you enter.

This changes the symbol everywhere it is used by the logic, including negative
literals and rule undercuts. It preserves meanings, key-conclusion choices,
priorities, active states, and attribution. Background and reference-document
text are not searched or rewritten. The change stays in this draft until
**Preview**, then **Save & open**. Published examples retain their snapshots.

Invalid names leave the draft unchanged. **Cancel rename**, or Escape while
typing the name, cancels that pending change. Preview and saving wait until
the pending name is applied or cancelled. Apply a pasted glossary or preview
changed rule text before renaming, so the symbol list represents that content.
Renaming also works in an unfinished guided draft and in larger scenarios
that use Rule text instead of the guided rows.

Closing the editor keeps its draft in this browser tab. Refreshing or signing
out clears it. Saved projects persist under **My projects**.

## Import one file or several materials

Choose files or drop them together into **Import scenario**. Check file roles,
then select **Load into editor**:

- **Complete scenario**: ABDA-NL YAML/JSON, including a downloaded export.
- **ASPIC- rules**: a .txt or .aspic knowledge base.
- **Glossary**: optional definitions in text, flat YAML, or flat JSON.
- **Reference document**: optional text, Markdown, or text-based PDF.

Use one complete scenario or one rule-text file, optionally one glossary,
and reference documents. Generic .txt files require an explicit role. No
document is silently interpreted as rules.

All files must pass before replacing the draft. A failed file leaves the
previous draft and current exploration intact. Import creates a separate
private project, never overwrites an example or existing project, and never
executes document instructions. Each file is at most 1 MB and text uses UTF-8.

Legacy standalone YAML may name corpus files without containing their text.
Attach those documents in the same import. Legacy versions 1 and 2 remain
readable, but source-linked exports may require their original built-in
example. New version 3 exports have no such dependency. YAML aliases,
executable tags, duplicate fields, unsafe paths, and excessive nesting are
rejected. ZIP archives and Word files are not supported.

## Rule text is a view, not a separate workflow

Select **Rule text** inside **Knowledge base** for propositional ASPIC-.
**Guided** returns to the same statements and rules. Keep stable symbols to
preserve their meanings and metadata. Invalid text never replaces a valid
draft. Existing key-conclusion choices are preserved; newly derived claims
receive inferred choices which you can change.

Example rules:

```text
-> sunny
-> windy

sunny => outside [sunshine]

windy => -outside [wind]
```

Optional definitions under **Load or paste a glossary**:

```text
sunny = The forecast is sunny
windy = A strong wind is expected
outside = We should hold the picnic outside
-outside = We should not hold the picnic outside
```

**Apply meanings** updates the same statement descriptions. Unlisted meanings
are retained; unknown symbols are rejected.

The arrow -> is strict, => is defeasible, and a leading minus is explicit
negation. Premises are comma-separated. Empty-premise positive declarations
create facts or assumptions. Named rules may also have empty premises.
Omitted rule names are generated. Rule text is limited to 100 KB and
250 declarations; a glossary is limited to 200 KB.

Native ABDA files use blank lines between defeasible preference blocks,
with later blocks stronger. In the example, wind has higher priority.
Explicit **# Block N** markers, used by the editor and **Show ASPIC-**, override
blank-line grouping. **# [suspended]** preserves inactive defeasible rules and
assumptions. Unsupported dialects, variables, and disjunction are rejected.

## Reference documents and complete portability

Upload text, Markdown, or text-based PDFs, or paste text directly. URLs are
optional HTTPS attribution metadata and are never fetched. Review extraction,
especially tables and figures. The saved corpus is reference text.

A scenario supports 20 references including bundled documents and curated
context, 250,000 characters per reference, and 750 KB of UTF-8 reference text
overall. Uploaded PDFs are limited to 40 pages and approximately 99,000
extracted characters. Trusted bundled PDFs export in full, including the
existing 44-page Popov reference. Scenario data and all embedded documents
must fit the 1 MB portable file limit. Saving rejects excessive content rather
than silently truncating exports. Safe PDF uploads require POSIX resource
limits; text upload and paste remain available on other platforms.

**Download current scenario** creates one self-contained **version 3 JSON**
file containing:

- Facts, assumptions, rules, priorities, active states, and key conclusions.
- Full glossary meanings, background, categories, and attribution.
- Complete reference text, including all bundled corpus documents.
- Existing curated corpus context, separately named **ABDA-curated-context.txt**.

PDFs are represented by full extracted text, not original binary files,
page layout, or figures. User-uploaded PDFs already use this text-only storage
model. Bundled PDFs are not replaced by excerpts or summaries during export.

Import this file on another compatible ABDA-NL installation with no matching
built-in scenario, corpus directory, or connection to the original server.
Re-export retains the embedded documents. Downloads include unsaved changes
in the current exploration, but do not save those changes to its project.
Save and open an unfinished editor draft before downloading it.

The envelope uses format "abda-nl-scenario", version 3, a null source_scenario_id,
and a scenario object following [the schema](../app/schemas/scenario.schema.json).
Corpus file references are empty and sources contain all text. Glossary
meanings remain in description and negated_description fields.

Downloads omit private project IDs, account details, chat, API keys, share
tokens, MCP credentials, and trial information. Deliberately authored personal
content remains part of the scenario. Downloading a share never changes its
owner's project.

AI requests use bounded, question-relevant excerpts. Selection is not exhaustive,
but complete text remains stored and exported. The ABDA engine determines
conclusion labels. Funded or BYOK accounting applies only to AI requests.

## Edit saved work

Open a private project and select **Edit scenario** in the toolbar. The same
editor updates its statements, rules, glossary, and documents together.
**Save & open** checks the project version and rejects stale edits instead
of overwriting newer work. Outstanding rule toggles in the current exploration
are included in the editor draft.

For examples and shared views, **Sources & glossary** is read-only. Save a
private copy before editing. Active share links expose updated saved content;
published examples keep their separately reviewed snapshots. Include only
material you have permission to share.

## Suggest or publish a preloaded example

Open your private project, then open **Workspace > Projects**. Select
**Suggest as example**, inspect the snapshot, check the public-sharing consent,
and select **Submit for review**. No model call or trial credit is required.
The preview includes the project name and the scenario itself, but not the
private project description, account email, chat history, or credentials.
The preview also includes the full text of attached references and their source
URLs. Remove sensitive or restricted material before submitting it.

Follow the request under **Workspace > Examples**. You can withdraw a pending
request. If a revision is needed, edit and save the project before submitting
a new snapshot. A retry of the same project version does not create a duplicate.
Each account can have five pending requests and fifty submissions in total.

Scenario administrators see **Publish as example** on their own projects.
They can also review submitted snapshots under **Examples > Awaiting review**,
then approve or decline them. A short reason is required when declining or
removing a published example. This role does not grant access to other private
projects. Review status is shown in the application; no notification email is
sent for each submission.

Published snapshots appear under **Community examples** in the main scenario
selector, alongside the unchanged included examples. They support the same
deterministic analysis, AI tools, downloads, private copies, and MCP reads.
Publication does not change the source private project. Later edits or
archiving do not update or remove its public snapshot. An administrator can
remove it from the public catalog without changing existing private copies.
Account suspension hides its published snapshots; permanent account deletion
removes its submissions. Downloaded copies cannot be recalled.
