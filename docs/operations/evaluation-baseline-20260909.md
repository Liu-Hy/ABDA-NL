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
