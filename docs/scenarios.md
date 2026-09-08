# Your own scenarios

Select **New / Open** next to the example selector. Creating or importing a
scenario requires a signed-in account because it becomes a private project.
On a local installation, use the development sign-in in Workspace. Neither
flow requires an API key, an activated trial, or an LLM call.

## Start with your own idea

1. In **New scenario**, give the scenario a title.
2. Write your statements. A **Fact** is given, an **Assumption** can be
   challenged, and a **Conclusion** is a claim you want to explore. Use
   **+ Statement** for more rows and choose each row's kind.
3. Connect statements with rules. Select a condition after **If**, and the
   statement that follows after **Conclude**. **+ Condition** joins conditions
   with AND. The **Not:** choices denote explicit negation of a statement.
   **Usually (defeasible)** permits competing arguments; **Always (strict)**
   makes the rule strict. Use **+ Rule** to add another connection.
4. Choose **Create & open**. ABDA validates and computes the scenario before
   saving it as a private project. If a rule cannot be analyzed, your draft
   stays available for correction and your current exploration stays open.

**Try a small example** fills the builder with two competing reasons about an
outdoor picnic. Change the wording and connections to make it your own. No
model invents connections or silently translates your input.

You can then toggle assumptions and defeasible rules, explore arguments, set
preferences, and save changes. The existing AI-assisted editing tools are
available when you configure model access. The builder is for creating a new
scenario, not replacing a saved project's entire structure.

For scenarios without bundled source documents, AI chat and edit proposals
use your authored statements, rules, glossary, attached reference text, and
computed argumentation state. They do not borrow another example's corpus.
The same applies to MCP project tools.
These optional AI requests use the usual funded or BYOK billing route.

Closing the dialog keeps its unfinished builder draft in this tab. Refreshing,
closing the tab, or signing out discards it. Private projects persist and can
be reopened through **New / Open > My projects**.

## Open an existing file

In **Open file**, choose or drop one `.yaml`, `.yml`, or `.json` file, up to
1 MB and encoded as UTF-8. Supported inputs are:

- A standard ABDA-NL `scenario.yaml` file, using the repository schema.
- A JSON object with the same scenario fields.
- A file downloaded from **Download current scenario** or **Download a starter
  file** in this dialog.

The preview checks syntax, identifiers, rule references, and whether ABDA can
construct the argumentation framework within its safety limits. It does not
save a project. Review the counts and any warnings, choose a private project
name, then select **Import & open**. Reimporting always makes a separate copy.

PDFs, Word documents, ZIP archives, and general prose are not scenario files.
The scenario-file picker does not interpret documents as rules or open paths
named in a file. Use the separate **Reference documents** section for context. Local
corpus references in standalone files are excluded with a warning. Exports of
bundled examples retain their checked bundled-source reference. YAML aliases,
custom object tags, duplicate fields, and excessively nested data are refused.

Minimal YAML example:

```yaml
title: Planning a picnic
facts:
  sunny:
    description: The forecast is sunny
conclusions:
  outside:
    description: We should hold the picnic outside
rules:
  sunshine:
    type: defeasible
    premises: [sunny]
    conclusion: outside
```

## Bring ASPIC- rules, a glossary, and reference documents

These are three distinct parts of a scenario:

- Rules determine the argumentation structure and computed conclusions.
- The glossary explains the symbols in natural language. It uses the same
  descriptions shown in the interface, not a second set of conflicting labels.
- Reference documents provide context for AI explanations and edit proposals.
  They do not automatically become logical facts or rules.

In **New / Open > ASPIC-**, enter a title and paste rules, or load a `.txt` or
`.aspic` file. Paste the glossary or load a UTF-8 `.txt`, `.yaml`, `.yml`, or
`.json` file. **Try a small ASPIC- example** fills both fields.

Rules:

```text
-> sunny
-> windy
sunny => outside [sunshine]
windy => -outside [wind]
```

Glossary:

```text
sunny = The forecast is sunny
windy = A strong wind is expected
outside = We should hold the picnic outside
-outside = We should not hold the picnic outside
```

`->` is strict, `=>` is defeasible, and `-` means explicit negation.
Comma-separated premises are joined with AND. An empty-premise positive
statement declares a fact (`-> sunny`) or an assumption (`=> reliable [reliable]`).
Named empty-premise rules are also supported. Rule names are optional and
generated when omitted. Symbols use ASCII letters, digits, and underscores,
starting with a letter or underscore. This importer supports the propositional
notation displayed by **Show ASPIC-**, not arbitrary ASPIC dialects, variables,
disjunction, or first-order formulas.

Glossaries can also be flat YAML/JSON maps, such as `sunny: The forecast is sunny`.
An explicit glossary overrides definitions in `# symbol = "meaning"` comments.
`# Block N` priority markers and `# [suspended]` defeasible lines are preserved.
Other comments are ignored. Unsupported rule syntax is rejected, not guessed.
If needed, enter comma-separated key conclusion symbols in the optional field.
Otherwise, review the inferred conclusions and missing-definition warnings.
Use **Check rules & glossary**, then **Import & open**. Rule text is limited to
100 KB and 250 statements/rules; a glossary is limited to 200 KB.

### Attach the corpus

The optional **Reference documents** section is available in all three tabs.
Upload `.txt`, `.md`, or text-based `.pdf` files, or choose **+ Paste document
text**. Review and correct the extracted text before saving. A source URL can
be recorded for attribution, but is not fetched. To use an online document,
download it yourself or paste a relevant excerpt, then include its source URL.

Limits are 10 documents, 1 MB per uploaded file, 40 pages per PDF, 100,000
characters per document, and 400 KB of UTF-8 reference text in total. Scenario
data and references together must also fit the 1 MB portable-file limit.
Original PDFs are not retained. Figures, tables, and layout may not extract accurately;
scanned or encrypted PDFs need a text version. PDF extraction requires a POSIX
host with process resource limits. Text upload/paste remains available elsewhere.

AI requests select bounded, question-relevant excerpts from the saved text using
lexical matching. This is not exhaustive document search or a guarantee that all
qualifications were included. Chat and both edit-proposal stages receive this
context and the glossary; the ABDA engine still determines conclusion labels.
Normal funded or BYOK accounting applies only when making an AI request.

### Edit, share, and carry the materials with you

After opening a private project, choose **Sources & glossary** in the toolbar.
Edit definitions, add/remove documents, or load a replacement glossary. A partial
glossary updates the listed definitions and preserves others. **Save to project**
uses the project's version check, so it cannot overwrite a newer concurrent
save. Save any outstanding rule changes first when prompted.

For examples and shared views, this panel is read-only. Save a private copy to
make changes. Attached text is part of the project: active share links expose
it, exports include it, and public-example submissions include its full text
after explicit consent. Only include material you have permission to share.
Previously published snapshots do not change when you edit the private project.

**Download current scenario** includes the rules, glossary, and reference text
in one portable JSON file (format version 2 when documents are attached).
Versions 1 and 2 can be imported. Plain rule text is useful for authoring, but
portable JSON is the complete round-trip format for background, focus labels,
metadata, engine settings, and documents. Unsaved drafts stay only in this tab
and are cleared on sign-out or reload.

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

## Take your scenario with you

**Download current scenario** exports the currently displayed scenario,
including unsaved rule or assumption changes. It does not save those changes
to your existing private project. Use **Save changes** for that.

The download contains the scenario, format version, and any bundled example
reference. It excludes the application account, private project IDs, chat,
provider keys, trial information, MCP credentials, and share tokens. Any
personal material you deliberately wrote into facts or descriptions is still
part of the scenario, so handle the downloaded file accordingly. Downloads
from a read-only share are copies and never change the owner's project.

The versioned JSON envelope is `format: "abda-nl-scenario"`, `version: 1`,
`source_scenario_id` (nullable), and `scenario`. The scenario field follows
[`scenario.schema.json`](../app/schemas/scenario.schema.json). Downloaded
files can be reopened on another ABDA-NL installation with the same schema;
a bundled-source reference requires that bundled example to exist there.
