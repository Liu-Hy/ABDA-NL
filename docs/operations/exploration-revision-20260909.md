# Exploration and conversation implementation

The September 9 review's frontend improvements are implemented in the working
checkout. This record describes the behavior and local acceptance, not a hosted
deployment or paid-model acceptance.

The question button inserts the existing generated question into the composer.
It preserves every character in an existing draft, inserts at the cursor, and
adds removable context items carrying the selected rule or claim's identity.
The composer remains editable without model access and while an answer is
pending. Only Ask or Enter sends a question. Context from a changed scenario is
marked and must be removed or selected again before submission.

The conclusion overview keeps its compact grouping. Inspect opens an individual
derivation, including all direct premises, proper subarguments, applied rules,
formal label, and incoming and outgoing attacks. Derivations sharing a
conclusion or top rule remain separate. Rule and premise links connect natural
language to exact formal syntax and locate the corresponding element in the
explorer. Recomputing a scenario closes a current inspector because argument
identifiers belong to one computed state. Saved evidence opens an inspector
against its original snapshot instead.

Chat supports New, a saved-conversation selector, Delete, and JSON export.
Signed-in history is saved in this browser under the account's internal ID.
Signed-out history remains in the current tab. Account changes detach pending
responses and clear the displayed history and draft. Signing out preserves
local history for the same account's next sign-in, as described in the privacy
notice. Storage failures are visible and suggest export or deletion; history is
not silently truncated. Provider keys, session tokens, share tokens, and the
application's account object are not serialized.

Before sending, each question captures the effective scenario and pending
operations through the existing portable export endpoint. Snapshots contain
complete source text and the computed argumentation framework. Identical
snapshots within a conversation are reused. Export therefore stays meaningful
after a project or the unsaved scenario changes. Each question can download
its portable scenario snapshot separately.

Edit and fork creates a separate conversation, retains earlier turns with
their original snapshots, and places the selected question in an editable
draft. Its label explicitly selects the current scenario for the new question.
It does not silently restore or mutate a historical scenario. Separate visual
tabs are represented by the compact conversation selector in this version.

Answers expose expandable backend-verified evidence. Source excerpts are
rendered as literal text. Verified formal references navigate to the saved
scenario's rules and arguments. A provider failure keeps the question and
shows that deterministic exploration and manual editing remain available.
Choosing Ask explicitly retries; there is no automatic browser retry.

The unused minimap function, event handlers, and styles have been removed.

## Local acceptance

`tests/test_exploration_browser.py` runs a real browser against intercepted
requests and actual deterministic engine data. It launches no web server and
makes no provider calls. It covers question insertion, keyboard activation,
draft preservation, explicit submission, multiple context identities,
in-flight editing, unavailable access, verified evidence, full scenario export,
history persistence, forking, account isolation, exact derivation navigation,
provider failure and recovery, narrow layouts, and accessibility.

The final Chromium selection passed 19 checks (eight browser workflows and
11 static contracts). Firefox passed the first seven workflows; its three
layout-sensitive cases passed again after the final composer layout adjustment.
The accessibility scans found no WCAG A/AA violations in the selected question
context or the individual derivation dialog. Ruff and whitespace checks passed.
WebKit acceptance remains unavailable on this host because the browser's GTK,
ICU, and media dependencies are absent. No host packages were installed.

The shared Delta launcher was left on the other active demo during these
checks. Hosted browser acceptance and live provider behavior are separate
integration steps for the full release.
