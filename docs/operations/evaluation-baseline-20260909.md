# Application baseline findings, September 9, 2026

The baseline was stopped after repeatable application defects appeared. It does
not qualify a model for release. All 81 attempted case observations were reviewed
against the saved scenario states, including the actual answers, proposed edits,
reviewer messages, and rejected drafts. There were 74 distinct complete semantic
payloads; identical payloads share an inspection note, with a separate evidence
hash binding for every observation.

The preserved evidence is in `artifacts/evals/`:

- `terra-sol-full-20260909.json` and its checkpoint contain the unchanged baseline.
- `terra-sol-full-answer-reviews-20260909.json` binds the inspection annotations.
- `terra-sol-full-reviewed-20260909.json` keeps automatic checks separate from
  inspection and remains unaccepted.
- `terra-sol-full-20260909.oracles.json` records every case's current scenario,
  requested edit or question, and deterministic labels.
- `terra-sol-full-20260909.stop-receipt.json` records the deliberate dispatch pause.

| Observed case | Demonstrated issue | Justified correction |
| --- | --- | --- |
| `fire-corpus-quote`, Terra repetition 2 | Both drafts quote the correct source words with line breaks joined into spaces. The runtime rejects them and displays a grounding refusal. | Match whitespace-equivalent quotations while retaining exact original source spans and offsets. Do not rewrite a passing general chat prompt. |
| `modify-rule-explicitly-reverse-conclusion`, Terra repetitions 1 and 2 | The conclusion reverses correctly, but descriptive provenance is replaced by a filename. The instruction explicitly requests changing only the conclusion. | Distinguish a requested field edit from a field mentioned in a preservation or exclusion clause. |
| `modify-existing-long-rule-id`, Terra repetitions 1 and 2 | The proposal correctly preserves `source` and `active`, but the reviewer warns that those fields changed. Its input omits the existing values. | Supply complete current rule fields, including provenance, activation, category, and negated meaning, before comparison. |
| `fried-chicken-multiple-selected-items`, Terra repetition 2 | The answer gives the correct undecided label but says neither equal-preference argument defeats the other. The graph contains mutual rebut defeats. The old context strips literal polarity and merges distinct argument identities. | Supply signed conclusions, exact argument identities, current argument labels, and the distinction between a defeat edge and its grounded outcome. |
| `missing-reference-does-not-license-a-quote`, Terra repetition 1 | The correct phrase "No handbook is attached" fails a narrow concept list. The answer refuses the quotation and explains the scenario boundary. | Add this absence wording to the rubric. Keep the independent prohibition on invented document citations. No model prompt change is justified. |

One case exhausts provider retries after HTTP 429 responses. This is availability
evidence, not evidence of a prompt defect. The last refinement case is deliberately
interrupted before its next dispatch by the operator budget pause. Neither event
supports prompt tuning.

The corrected shared context needs full regression across affected models and
features before admission. The general prompt templates are retained. Passing
baseline cases, including document instruction resistance, changed scenario
meanings, stale history, pending references, selected arguments, and unapplied
refinement, do not justify independent wording changes.

The original smoke report records 16 successful Azure calls and $0.503896. The stopped
baseline made 120 physical Azure attempts, with 109 successes and 11 rate-limit
failures, and used $1.014940. A subsequent pricing audit raised the conservative
Sol cache-write rate from $5 to $6.25 per million tokens. The 63,213 cache-write
tokens require a $0.079019 upward correction after rounding each call. The
original reports remain unchanged; `sol-cache-pricing-correction-20260909.json`
records each corrected calculation and its hash is bound to a separate,
idempotent ledger adjustment. This adjustment is not counted as a provider call.

After that reconciliation and before further testing, the lifetime ledger records
$1.597855 spent, no pending reservations, and $98.402145 remaining. The operator
pause stays in force until the corrected sources are ready for another bounded
run. These figures come from provider usage and configured prices, not a cloud
invoice. Every physical attempt in these two runs used the configured Azure
Foundry CloudBank route; none used GCP, a personal Gemini project, or OpenRouter.

Slurm job `21932095` completed successfully after 5 minutes 25 seconds. Its single
GPU reservation was necessary to use the available allocation for a network
workload; it exited as soon as the safe stop had reconciled the current request.

## Seven additional routes, September 10 UTC

After the context and validation fixes passed their focused tests, Slurm job
`21932318` ran six availability cases once for each of seven additional routes.
The single serial process had a shared $6 run limit within the same lifetime
ledger. It used the same minimal allocation and completed in 3 minutes 24 seconds.
No source files changed during that run. The report's implementation fingerprint
is `e8f2e912143913d327e047604677f2c0166c6e2f9f358e31ed7e7a254e72826a`.

All 42 observations were inspected, including 36 distinct complete semantic
payloads and drafts rejected by application validation. The original report is
`artifacts/evals/pool-availability-20260909.json`. The matching
`pool-availability-answer-reviews-20260909.json` and
`pool-availability-reviewed-20260909.json` preserve identified inspection notes
and failed assessments. Availability alone does not qualify a model for release.

| Route | Automatic cases | Physical attempts | Recorded cost |
| --- | --- | --- | --- |
| Claude Sonnet 5 | 6 of 6 | 8 successful | $0.422116 |
| Claude Opus 5 | 6 of 6 | 8 successful | $1.058462 |
| DeepSeek V4 Flash 0731 | 6 of 6 | 8 successful | $0.050621 |
| GLM 5.3 | 0 of 6 | 12 HTTP 429 failures | $0 |
| Kimi K3 | 0 of 6 | 12 HTTP 429 failures | $0 |
| Gemini 3.1 Pro Preview | 6 of 6 | 8 successful | $0.250042 |
| Gemini 3.8 Flash | 6 of 6 | 8 successful | $0.191254 |

These 64 physical attempts contain 40 successful calls and 24 rate-limit failures
that the provider accounting contract treats as zero charge. Azure routes used
the configured Azure Foundry endpoints. Both Gemini routes used the verified
CloudBank Vertex project through its existing application default credentials.
No call used OpenRouter or a personal Gemini project. This run consumed
$1.972495. Including the earlier runs and separate Sol pricing correction, the
lifetime ledger now records $3.570350 spent, zero pending reservations, and
$96.429650 remaining. These totals are conservative usage-based estimates,
not an invoice.

| Observed behavior | Evidence | Justified follow-up |
| --- | --- | --- |
| Unsupported provenance on a new observation | Sonnet, Opus, DeepSeek, and Gemini Flash attribute a newly stipulated calibrated temporary monitor to the community airshed letter. That text describes earlier excursions at an existing school-district station and does not establish this new observation. Gemini Pro correctly identifies user instruction as the origin. | Require actual supplied support for the exact statement before assigning a corpus filename. A related topic is insufficient. User-stipulated facts and assumptions use user origin or omit the source unless supplied text establishes their specific details. |
| Unsupported patient-specific assumption | Sonnet cites `wikipedia_ppi.txt` for a new H2 alternative assumption, although that file never mentions H2 antagonists. Other answers use actual general ACC/AHA guidance, which still does not establish the newly stipulated individual patient's suitability. Gemini Pro uses user origin. | Apply the same provenance rule to new assumptions. Preserve an explicitly requested source and existing metadata unless the user asks to change it. |
| Reversed Popov decision wording | DeepSeek describes Hayashi's and Popov's opposing decisions as two "no return" conclusions. Its principal equal-strength conclusion is correct. | Retain the semantic failure. The shared chat prompt contains a false worked example saying rules favouring Hayashi support returning the ball. Correct that example to support letting Hayashi keep it. No other chat wording or model-specific tuning is justified yet. |
| GLM and Kimi cannot complete availability checks | Every attempt receives HTTP 429 between 02:43:19 and 02:43:28 UTC. | Retest provider availability after the independently authorized capacity increase. Rate limits do not justify prompt tuning. |

The repeated provenance failures justify a narrow change to proposer instruction
7 and the corresponding tool-schema source descriptions for rules, facts, and
assumptions. The old rule schema encouraged citing a filename "when possible";
the corrected schema requires actual support. Suite version 7 adds a user-origin
check to the two affected smoke cases, without changing the preserved baseline
reports. The proposer introduction also now describes the actual workflow:
reviewer notes are advisory, and changes take effect only after the user clicks
Apply. The old claim that reviewer approval recomputes the scenario was false.
The reviewer policy against second-guessing user-stipulated domain premises is
unchanged.

Both Fireworks-backed Azure deployments were increased from capacity 10 to 100
at 02:47:15 UTC, after all failed attempts had ended. Each now has 100 requests
and 100,000 tokens per minute. The model versions, SKU, and guardrail stayed the
same. The before/after receipt is
[fireworks-capacity-20260910.json](model-deployment-plan-20260909/fireworks-capacity-20260910.json).
Their application behavior remains untested until a later successful run.

The focused proposer, schema, evaluation, and state-evidence checks passed 57
tests after the provenance change. Every affected model and feature still needs
the planned complete qualification under the corrected shared sources. Passing
source translation, narrow metadata preservation, and reviewer inversion checks
do not justify additional prompt rewrites.

## GLM and Kimi follow-up

Slurm job `21932609` repeated the same six availability cases once per route after
both Fireworks deployments reached capacity 100. The serial run had one $2 cap
within the existing ledger. It completed successfully in 4 minutes 34 seconds,
with source fingerprint
`b19aab6551107546fb93813e5803115460e7247def1a649671f92515b7e06575`
unchanged throughout. All 12 observations, comprising 11 distinct complete
semantic payload groups, received inspection annotations. The original and
reviewed reports are `artifacts/evals/fireworks-availability-20260909.json` and
`artifacts/evals/fireworks-availability-reviewed-20260909.json`.

GLM passed 2 of 6 cases. Its chat correctly keeps the opposing Popov decisions
distinct, and its narrow NBA modification and corresponding reviewer preserve
all unrequested fields. The add-rule, add-fact, and add-assumption calls fail
after consuming 2,048 output tokens each. The inverted-rule reviewer fails at
1,024 output tokens. These are the respective request limits.

Kimi passed 4 of 6 cases. Its new fact and patient assumption correctly use user
origin, and it preserves the existing NBA rule and detects the reversed fire
rule. Its Popov proposal is faithful, but the subsequent reviewer fails at
1,024 output tokens. Its chat is a separate semantic failure: it calls Popov
clearly stronger by inventing an ordering from his accepted qualified right.
The actual scenario accepts both legitimate claims and defeats both one-sided
decision rules through the even-handedness undercuts.

The compatible adapter does not forward the catalog's configured low reasoning
effort for either model. The output-limit pattern warrants verifying that
provider contract and correcting the adapter before judging whether additional
prompt tuning is needed. The saved failure records include normalized provider
usage but lack the rejected completion and finish reason, so truncation is a
supported hypothesis rather than a verified explanation. A later bounded replay
must preserve safe parser diagnostics and retain these original failures.

There were no HTTP 429 responses. GLM made 7 physical attempts, with 3 successes
and 4 parsing failures, costing $0.249213. Kimi made 8 attempts, with 7 successes
and 1 parsing failure, costing $0.461881. Failed responses supplied usage, so
their recorded costs were settled from that usage rather than retaining the
larger reserved maximum. The run consumed $0.711094. The lifetime ledger now
records $4.281444 spent, zero pending reservations, and $95.718556 remaining.
All 15 physical attempts used CloudBank Azure routes. No OpenRouter generation
occurred.

The next capacity increase was verified after this run, at 02:58:33 UTC:
GLM and Kimi each have 250 requests and 250,000 tokens per minute, while Terra,
Sol, Sonnet 5, and DeepSeek each have 500 requests and 500,000 tokens per minute.
The source, model versions, and other deployment settings did not change. The
receipt is
[moderate-throughput-20260910.json](model-deployment-plan-20260909/moderate-throughput-20260910.json).

## Adapter replay with unchanged output limits

The provider patch forwards the configured low reasoning effort and uses Kimi's
supported required-tool mode with exactly one advertised and returned function.
It also exposes safe parser diagnostics to the synthetic evaluator. No chat or
proposer prompt changed between the two Fireworks runs, and their proposal and
review limits stayed at 2,048 and 1,024 tokens.

Slurm job `21932865` completed the bounded $2 replay in 1 minute 38 seconds. All
12 automatic cases and all 12 complete visible-payload inspections pass. GLM
made 8 successful physical calls, costing $0.230179. Kimi made 9 successful
physical calls, including one application repair of a raw identifier in chat,
costing $0.389515. It no longer claims Popov is clearly stronger. Both models
now complete the previously failing proposer and reviewer stages within the
unchanged limits, so no cap increase or additional prompt tuning is justified.

The original and separately reviewed reports are
`artifacts/evals/fireworks-low-effort-20260909.json` and
`artifacts/evals/fireworks-low-effort-reviewed-20260909.json`. Their implementation
fingerprint is
`e1134180fc5cf4da8540d625f746b6cc65764283cf46528c0556f57cafa272b6`,
unchanged during the run. The replay used $0.619694. The lifetime ledger now
records $4.901138 spent, zero pending reservations, and $95.098862 remaining.
All calls used CloudBank Azure; no OpenRouter generation occurred. These smoke
passes still require full feature qualification before public admission.

## First complete-suite attempt, stopped at case boundaries

The first four-worker run used the corrected reasoning settings, evaluator
pacing, and a shared 180-second application deadline per case. Slurm job
`21933016` was stopped after a shared application exception appeared. It
completed normally in 4 minutes 54 seconds, with every current provider request
settled and no pending reservations. All nine reports retain the unchanged
source fingerprint
`26ef5764c1ffca7418617c9f0de8fa95ca77be664e165ee2d076cdaecd424e46`.

The batch preserved 169 observations: 54 Opus, 45 Sonnet, 50 Terra, and 20 Gemini
Pro. Queued routes made no requests. It made 224 successful physical provider
calls (201 Azure and 23 Vertex), costing $8.444906. Application errors occurred
after successful, billable responses; there were no provider failures. The
lifetime ledger now records $13.346044 spent, zero pending reservations, and
$86.653956 remaining. Original reports and checkpoints are in
`artifacts/evals/full-qualification-20260909/`. The sibling manifest, complete
scenario/AF oracle file, stop receipt, and stop-completion receipt preserve the
execution and accounting evidence.

Sonnet returns a fact identifier inside the fact object, omitting the required
top-level identifier, in a pending-reference case. The application raises
`KeyError` before the normal validation and bounded correction loop. This
demonstrates a shared structural-validation defect at the model-output boundary.
The same problem affects a refinement case. The appropriate first correction
is application validation of the returned shape before field access, retaining
the model's original payload for diagnosis.

Sonnet also produces an unnecessary reviewer note on a valid combination of
existing fire-scenario premises, and an issue on an explicitly requested strict
hypothetical rule. These remain recorded semantic-review failures for a targeted
decision after complete answer inspection. No passing prompt is changed merely
because an unrelated case fails.

Opus's greenhouse answer says, "The scenario accepts the conclusion that the
greenhouse should be ventilated," and explains the correct window, sensor, and
unattacked inference chain. The evaluator recognizes only the inflection
"accepted", causing an automatic false negative. The corrected label check
recognizes present-tense forms while retaining negative controls for negation
and swapped labels. An offline comparison is bound to the original response and
report hashes in `artifacts/evals/opus-label-rubric-recheck-20260909.json`; the
original report is unchanged and incomplete. This correction needs no model
prompt change or additional paid call.

## Bounded replay of inspected failures

Slurm job `21933304` completed one diagnostic pass over 25 observed model-case
pairs in 3 minutes 51 seconds. The source was commit
`caec7025784713210abe12ec46a3b7e20e751b04`, fingerprint
`3aca185407ee645e1deda54ceb96ee37d6020a0082856abca2ab7833d2154d4d`.
All four reports confirm unchanged source during execution. The pass used
separate route limits whose sum was $5, in addition to the persistent lifetime
$100 limit. It made 55 successful physical calls (53 Azure and 2 Vertex),
costing $2.859686. Every call settled. The ledger records $16.205730 spent,
zero pending reservations, and $83.794270 remaining. No paid OpenRouter call
occurred. The manifest, original reports, checkpoints, and completion receipt
use the `artifacts/evals/targeted-replay-20260909` prefix.

Sonnet's pending-reference fact promotion now completes after two rejected
drafts and a valid third draft. Its refinement still exhausts the three allowed
attempts, with a structured application error instead of `KeyError`. The
correction feedback calls a nested fact error an error at `<root>`, which is
ambiguous relative to the complete tool envelope. Exact validation paths are
the next application correction. Two Sonnet reviewer notes also misstate an
explicit request to preserve source metadata as a request to rewrite it.
These remain material failures requiring correction before full qualification.

The Opus crispiness explanation now identifies the accepted undercut as the
decisive step. It opens with "It's accepted" in response to one selected
conclusion. The evaluator previously required the literal's description and
label in the same clause. A narrow scoring correction recognizes this direct
answer only for one matching selected item, without overriding an explicit
contradictory label or guessing among multiple items. Negative controls cover
negation, the wrong label, an unselected target, and ambiguous selections.
The offline receipt `artifacts/evals/opus-pronoun-rubric-recheck-20260909.json`
binds the exact original answer and report. No new model call or model prompt
change was needed for this scoring correction.

The user clarified that minor imprecision should be documented without
blocking an otherwise useful feature. Original strict-review verdicts remain
unchanged. The separate `claude-policy-reassessment.json` receipt in the replay
directory records that calibration explicitly. The diagnostic pass does not
replace full model-by-feature qualification with three repetitions.
