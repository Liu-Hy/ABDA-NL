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
use your authored statements, rules, and computed argumentation state. They
do not borrow another example's corpus. The same applies to MCP project tools.
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
The import does not upload attachments or open paths named in a file. Local
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

## Suggest or publish a preloaded example

Open your private project, then open **Workspace > Projects**. Select
**Suggest as example**, inspect the snapshot, check the public-sharing consent,
and select **Submit for review**. No model call or trial credit is required.
The preview includes the project name and the scenario itself, but not the
private project description, account email, chat history, or credentials.
Remove sensitive material from the scenario before submitting it.

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
