# Scenario reconstruction implementation, September 10, 2026

The three knowledge bases reproduce the consolidated
[proposal](../scenario-reconstruction-proposal-20260910.md). Their About descriptions
were then rewritten under the owner's later request for plain English background.
All other YAML fields remain identical to the proposal. Popov and both Fried
Chicken knowledge bases are unchanged, with new About paragraphs too. This work
changes bundled content and its tests, without changing the engine or format.

| Scenario | Implemented distinction | Baseline arguments / attacks |
| --- | --- | --- |
| PPI Therapy | Continuing acid suppression is separate from keeping omeprazole or substituting pantoprazole. Bone risk supports reassessment, not automatic discontinuation. | 15 / 9 |
| Prescribed Burn | Treatment this cycle is separate from permission and proceeding on the planned day. The latter requires permission. | 17 / 6 |
| NBA Rebuild | Tanking and competing are exclusive season postures. Stacking veterans is a separate choice requiring an applicable acquisition plan. Lottery flattening attacks the extra-losses inference, not pick value. | 19 / 15 |

The two erroneous medical corpus references now identify omeprazole as the PPI
tested in COGENT. The trial's limited ability to rule out cardiovascular effects
is retained. [COGENT paper](https://pubmed.ncbi.nlm.nih.gov/20925534/).

The burn corpus now attributes categorical permit withholding to the scenario's
fictional state program. Its former attribution to "most state SMPs" contradicted
the consolidated proposal. The general PM2.5 background is explicitly dated to
the 2024 standards revision. All corpus filenames remain unchanged.
[EPA's account of that revision](https://www.epa.gov/particle-pollution-designations/particle-pollution-designations-2024-revised-annual-pm-naaqs-where).

These remain simplified, fictional teaching cases with illustrative source
summaries. Reconstruction and passing formal tests do not establish independent
clinical, regulatory, or basketball expertise for the corpus.

## Deterministic acceptance

[Behavioral tests](../../tests/test_reconstructed_scenarios.py) were authored
before replacing the content or regenerating `expected_labels.yaml`. The old
baselines failed the new argument-count expectations; the reconstructed content
passes 93 checks: 25 table states, 64 combined-toggle/preference cases, three
baseline graph counts, and the sequential recent-burn teaching example.

The combination checks preserve ongoing acid suppression, prohibit simultaneously
accepted exclusive options, prevent a strong treatment preference from bypassing
the absent/rejected burn permit, and prevent an unavailable acquisition from
becoming applicable through preference changes. Permission guarantees remain
bounded by the authored permit premise and its block, as the proposal explains.
Turning an assumption off means absent support, not an asserted negation.

All six bundled scenarios pass `validate_scenario --all`. A focused 283-test run
passed loader, serialization, argument context, edit validation, native-client
helper, and scenario exchange checks. The existing portability tests verify
complete corpus text and unchanged reasoning after import with the bundled
catalog unavailable. The final behavioral/evaluation-unit run passed 111 tests.
Ruff and whitespace checks passed for the changed test/helper files.

## Evaluation and compatibility

[The current evaluation suite](../../evals/llm_suite.yaml) is version 10 with
52 cases. Twenty use these scenarios; three additional cases check reference-only
questions and selective source display. All case setup, context identifiers, and
declared engine expectations were checked without a model call. Current MCP
client instructions and fixtures now use `permit_window_open` and
`burn_permitted`; disabling the window leaves permission absent.

The medical sensitivity case is now `medical-cogent-toggle`. NBA modification
cases operate on `stack_for_window` and preserve its acquisition prerequisite.
The suspended-permit case now distinguishes unsupported permission and burn-day
action from undecided treatment. Four new cases cover the unavailable medical
substitute, exceedance despite treatment priority, NBA strategy exclusivity,
and an unavailable acquisition despite increased preference.

The parent task qualifies model behavior using the original shared CloudBank
evaluation ledger. The [review guide](../demo-revision-review-guide.md) records
the final source, model checks and observed prompt corrections. Reconstruction
alone does not establish model correctness.
An added H2-blocker assumption alone does not derive a replacement treatment;
an explicit connecting rule would also be needed. No such rule was added.

No stored project, share, or published submission was migrated or rewritten.
Their saved knowledge bases remain their own snapshots. Version-3 exports with
embedded source text retain that text. A limitation of the existing storage
design is that server projects and submissions can retain bundled corpus
filenames instead of embedded text. Those references resolve to the corrected
current text, so historical corpus immutability is not guaranteed for every
saved object. Stronger source persistence would require separate infrastructure
work beyond this content-only reconstruction.

Historical operations/evaluation receipts and the supplied proposal/response
remain unchanged. The consolidated proposal used here has SHA-256
`0f332911d59b655af9288ca5219bbcc4d144b971e5312b6a3615d9ff1da069c5`.
