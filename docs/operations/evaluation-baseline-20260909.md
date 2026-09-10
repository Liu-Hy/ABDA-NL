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

## Completed full baseline and evidence-bound review

After precise validation-path feedback and reviewer change summaries were
added, a three-case Sonnet diagnostic completed all requested operations.
Slurm job `21933576` made nine successful Azure calls for $0.368893 under a
$1 phase cap. The pending fact refinement recovered after one malformed draft;
the remaining source advisory did not invent a requested rewrite and was
nonblocking under the user's clarified policy. Original drafts and the exact
review are retained in `artifacts/evals/sonnet-contract-replay-20260909/`.

The complete nine-model baseline then tested all 43 cases three times per
model, covering all six bundled scenarios and custom/imported authoring
states. It completed 1,161 observations at commit
`0a79a1b2f7f4734ec2a0befc55e57f846bc78eaf`, implementation fingerprint
`164b2292c49ee12580c2299f977a980ca9116a2f0a143a2b490e1344eb580cb8`.
The user-requested pause and the allocation runtime boundary both preserved
completed rows for exact resume. No row was discarded or rerun merely to
change its wording.

The baseline cost $28.470868. Its 1,635 physical attempts comprised 1,279
Azure and 356 Vertex attempts, all recorded as CloudBank funded. Three
DeepSeek transport failures had uncertain post-dispatch billing; their full
conservative reservations, totaling $0.084406, remain charged in the ledger.
Every route's settled ledger agrees with its report. At this baseline's
completion the lifetime ledger, including all earlier diagnostics and the
documented upward cache-price correction, stood at $45.045491 spent, zero
pending, and $54.954509 remaining. These are historical completion totals,
not a claim that subsequent regression work is free. No paid OpenRouter
generation was permitted. Provider audit evidence and local conservative
accounting are distinct from cloud invoice reconciliation.

Every actual answer, tool payload, rejected draft and reviewer issue received
an explicit evidence-bound inspection. Repeated semantic payloads reused an
inspection only after their complete request sequences were also verified
identical. The complete accounting receipt is
`artifacts/evals/full-qualification-final-20260909.completion.json`; original
reports, checkpoints, request bindings and reviews are in the corresponding
directory.

Terra, Sol, Gemini Pro and Gemini Flash had no material answer-review failure.
Sixteen exact phrase variants across seven routes caused concept or label
matcher failures despite correct inspected answers. Separate offline
adjudication artifacts bind each observation, complete request/response hash,
answer text hash and explicit phrase witness. They preserve the original
automatic verdicts and cannot override provider errors, schema failures,
quotation grounding, source provenance or failed semantic reviews. The
derived Terra, Sol and Flash gates pass at the recorded baseline fingerprint;
Gemini Pro's original reviewed gate already passes. Those findings do not
automatically qualify a later implementation.

The baseline retained material failures in the other routes. Sonnet sometimes
invented source provenance or a source-rewrite request and attributed a
rejection to a rejected argument. DeepSeek also showed unsupported provenance
and a causal error, alongside one actual provider outage. GLM lost explicitly
requested edit fields. Kimi had unsupported provenance and a quotation
validation refusal. Opus's three strict-rule failures exposed a contract
mismatch between the advertised optional activation field and the application
schema. Optional null text from DeepSeek required defensive compatibility,
while its original tool schema had specified a string rather than null.

These observations justified the narrowly scoped changes integrated at
`8f83ac948e1583d5f90317aab94d405530937f0d`. Shared deterministic fixes preserve
strict-rule semantics, improve schema feedback and repair quotation locality
and short-quote pairing. New proposer guidance is limited to the models with
observed provenance or field-preservation failures. Passing prompts remain
unchanged. The source manifest and integration receipt bind each changed file
and retain the previous fingerprint. Fresh full regression for the four
affected models remains separate from the preserved baseline; supplemental
live checks and complete offline replay are required to support reuse of the
unaffected paths.

## First complete regression after the baseline fixes

Slurm job `21934860` completed the four affected model suites at commit
`8f83ac948e1583d5f90317aab94d405530937f0d`, fingerprint
`875ed63e55c8d8eb73b48d7b377fbd6a8abcb85d0f5fa70dab8a07a675a8d250`.
All 516 observations, including every intermediate draft, were preserved and
inspected. The phase cost $8.086039 across 749 logical calls and 761 physical
attempts, all using Azure with recorded CloudBank billing. Its completion
receipt records $53.131530 in lifetime charges, zero pending reservations,
and $46.868470 remaining.

The 13 failed physical attempts all belonged to DeepSeek. Eleven affected
logical calls recovered on their permitted provider retry; one exhausted both
attempts. Their uncertain post-dispatch billing retains $0.261980 of full
reservations. The original audit did not retain the HTTP transport subtype,
and its failed-attempt latency field is zero. Logical request durations are
consistent with the configured transport timeout, but they do not establish
an exact exception class or an HTTP status. This distinction is recorded in
`deepseek-transport-failure-summary.json` beside the original reports.

Sonnet still gave three materially incorrect rejection causes. GLM retained
two explicit-field omissions and one quotation-related application refusal.
Kimi had one quotation-related application refusal. The source phrases in
these quotation cases differed only in initial capitalization or terminal
punctuation, so the remedy was deterministic restoration to the exact source
span before the unchanged strict validator. A separate independent review
checked all 13 changed drafts in the offline typography replay. No model
prompt was changed merely to force a typographic preference.

The next scoped changes were integrated at
`b4648deed9e27c2ae81bbbb08a8a7240428ca10d`, fingerprint
`affbd6747e138f27c161897c3d4aeca0f986767ff1f58935c95b2b3ca23c8d4c`.
Sonnet and DeepSeek receive directly computed accepted-defeater context.
DeepSeek's demonstrated provenance and review-direction problems receive
short targeted guidance. GLM's existing explicit-field instruction is
replaced by one general reminder to include requested optional fields and
preserve pending fields during refinement. The application also attaches
validated forward-premise notes before invoking its reviewer, so the reviewer
can inspect the same notes already present in the final preview.

Original report gates remain unchanged. Seven exact lexical false negatives
in this regression have separate bound adjudications. These do not waive
field checks, quote checks, provider errors or material semantic failures.
The phase accounting and source receipts use the
`artifacts/evals/post-fix-qualification-20260910` prefix. The next three-model
full regression and the supplemental checks use their own run IDs, while
sharing the same persistent lifetime ledger.

## Second complete regression

Slurm job `21935316` completed the Sonnet, DeepSeek and GLM suites at the
`affbd674` fingerprint in 24 minutes and 49 seconds. All 387 observations
and 552 logical calls are preserved. The 557 physical attempts comprised
549 successes and eight failures, all through Azure with recorded CloudBank
billing. This round cost $4.010931. Its completion snapshot is $57.142461
in lifetime charges, zero pending reservations and $42.857539 remaining.
The receipt is
`artifacts/evals/second-fix-qualification-20260910.completion.json`.

Every response and intermediate draft was inspected. Sonnet and GLM each
have 127 of 129 manually accepted observations; both retain two material
causal errors. DeepSeek has 121 of 129 accepted observations, with retained
provider, quotation-validation, reviewer and requested-source failures.
Correct final labels do not excuse a direct false assertion that a rejected
attacker or an inactive premise caused the result. Harmless duplication,
informal counts and unnecessary nonblocking advisories remain documented
without prompting additional tuning.

The GLM activation and strength fixes now hold in all three repetitions of
the critical assumption cases. One omitted category is nonblocking metadata
under the user's policy, but its original automatic field check remains
false. One delivered answer also contains two exact source quotations and
an additional unattributed quotation from actual application context; the
overbroad evaluator quote check remains false separately. Neither exception
is disguised as a lexical matcher repair. Only three explicitly inspected
phrase variants, two for GLM and one for Sonnet, receive the existing narrow
offline lexical adjudication. All current derived model gates remain false
where material failures persist.

DeepSeek's two errors carrying status 400 used requests byte-identical to a
successful middle repetition. The saved metadata does not establish the
provider error code, content-filter result or exact wire response status.
The adapter correctly treats a generic status 400 as nonretryable and
ineligible for fallback. An offline payload reconstruction also confirms
that this Azure route sends no thinking or reasoning-effort field, despite
the catalog's default `low` value. The effective Azure default is therefore
unverified, and these results must not be described as a tested low-effort
configuration. The bounded classification and request-equality evidence are
in `deepseek-status400-and-effective-settings-audit.json` beside the reports.

The following supplemental allocation, job `21935612`, completed all 30
requested strict-rule, quotation and forward-reference observations. All
56 physical attempts succeeded, comprising 38 Azure and 18 Vertex calls.
Independent inspection reviewed every final result and intermediate draft,
accepting all 30 observations under the clarified tolerance while retaining
minor advisories. The source
stayed at the same fingerprint throughout. The supplement cost $1.171291.

The same allocation then executed one separately capped funded MCP probe.
Its two real Azure Terra calls produced the correct undecided burn
explanation and the requested `inspection_complete` fact proposal, costing
$0.017851 and $0.030173 respectively. The probe verified exact account/cap
settlement, no implicit Apply, project archive, token revocation and rejected
reuse of the revoked capability. It exercised MCP JSON-RPC through the
current checkout's in-process ASGI application with real provider HTTPS.
It does not establish hosted-endpoint or external subscription-client
acceptance, which have separate evidence. Its receipt stores request hashes
and complete visible responses; the pinned probe source reconstructs the
requests.

The combined supplement and MCP phase cost $1.219315. At completion the
lifetime ledger stood at $58.361776, with no pending reservations and
$41.638224 remaining. All funded runs remain separate in the ledger, and
no paid OpenRouter generation occurred. The complete accounting receipt uses
the `artifacts/evals/second-fix-supplemental-20260910.completion.json` path;
the exact funded MCP receipt is
`artifacts/evals/mcp-funded-eab9fb5a450bddd8.paid.json`.

## Final chat context qualification and evidence reuse

Commit `a2001f6` changes the chat conclusion summary to distinguish current
arguments and their labels from inactive or merely declared rules. It also
corrects explicit filename-prefix quotation attribution. The provider
settings and prompt templates remain unchanged. The frozen implementation
fingerprint is
`502b8637bdc35d9aba5b1fee5fb0609ea3998cba1294ff91a9e696a1018ae6dd`.

Slurm job `21935822` ran all 19 chat cases three times on each of the eight
intended public models, for 456 observations. DeepSeek remains an unadmitted
candidate because its earlier material failures persist. The eight route
caps total $20 within the same lifetime $100 ledger. Rebuilding every planned
request offline found no missing response path and bounded the largest four
concurrent reservations at $1.166948. Archived matching chat calls cost
$7.567062; this is a forecast basis rather than a promise about new usage.
The manifest and reservation receipt use the
`artifacts/evals/chat-context-qualification-20260910.manifest.json` and
`artifacts/evals/chat-context-request-bounds-20260910.json` paths.

The separate composite map binds all 576 editing and reviewer observations
to their original paid reports and explicit manual reviews. Replaying all
975 captured logical calls through the final application produced exactly
identical complete requests and deterministic results. Twenty-four paid
supplemental observations replace earlier strict-rule or forward-reference
paths, including all three Opus strict-rule failures. Every prior failed
report and rejected draft remains preserved. The only selected non-chat raw
automatic failure is GLM's omitted optional category in
`assumption-retains-uncertain-status:1`, which requires an explicit
nonblocking release assessment rather than a changed field score.

This proof also records the earlier routing accounting change. Removing
only the added committed-cost aggregation yields the same routing AST,
including provider invocation, retry and fallback branches. All selected
observation response costs already equal their physical ledger totals.
Provider/client source and model catalog bytes are identical across the
reused paths. The complete evidence map is
`artifacts/model-qualification-20260909/composite-eight-model-evidence-map-20260910.json`.
The map was prepared before the 456 final chat answers were inspected. The
completed review and explicit nonblocking assessments are bound in the final
composite receipt below. The map does not change original automatic gates or
admit a model by itself.

The final chat allocation completed successfully in 13 minutes and 11
seconds. All 466 physical calls succeeded, comprising 352 Azure and 114
Vertex calls. The 456 observations cost $5.912115. Every report matched its
checkpoint, every recorded request/response hash verified, and each route's
cost matched its settled lifetime-ledger entries. The final ledger snapshot
is $64.273891 spent, zero pending and $35.726109 remaining. No paid
OpenRouter generation occurred.

All 456 new chat observations were explicitly reviewed and materially
accepted. The former Sonnet/GLM current-cause mistakes did not recur. The
raw automatic results remain 439 passes and 17 failures: 16 precisely bound
phrase-matcher misses and one Sonnet quotation of an actual current-state
heading that the corpus-only evaluator misclassifies. The heading is
present in the captured requests, the two source quotations are exact, and
the extra phrase is not attributed to either source. Root recorded a
separate nonblocking scope assessment, preserving the original grounding
check. The phrase-only cases use the existing offline adjudication helper;
none required another paid call or prompt change.

Together with the 576 proven non-chat observations, the release evidence
covers 43 cases with three repetitions on each of eight models, or 1,032
observations. The original counts remain 1,014 automatic passes and 18
explicitly assessed exceptions. Sixteen are literal matcher limitations;
the other two are the Sonnet heading scope and GLM's optional grouping
category. Root independently checked that including the requested GLM
category leaves the complete argument framework unchanged, while the
effective activation, preference block, meaning and source already match.
Neither original field nor grounding scores are rewritten.

The source-bound composite receipt is
`artifacts/model-qualification-20260909/composite-eight-model-release-assessment-20260910.json`.
It combines exact reuse, final live answers, complete manual reviews and
the two explicit assessments. It does not claim a general model ranking
or erase earlier provider and application failures. Catalog admission and
deployment remain separate actions controlled by the release owner.

At this checkpoint, the paid sensitivity cases changed assumptions. Existing
preference conflicts, explicit negation, and inactive rules appeared in the
tested context, but the 43-case suite did not include a dedicated live question
after changing a rule's suspension or preference ordering. The final scope
audit identified that coverage gap and prompted the supplement below. Cases
labeled `regression` were part of iterative qualification, not a separately
locked blind test set.

## Rule suspension, preference changes and final GLM regression

Two new artifact-only cases tested that gap on all eight models with three
repetitions, producing 48 observations. One suspended the fire scenario's
permit-to-permission rule while retaining its active permit assumption. The
engine changed permission from accepted to rejected because the accepted
prudential opposition became unopposed; the inactive forecast did not cause
the rejection. The other raised the home-ordering default above the
restaurant default in the first fried-chicken scenario. Home ordering became
accepted, the restaurant argument became rejected, and its rule remained
enabled. Root independently applied both exact changes, checked every label
and verified that the original scenarios were unchanged.

All 48 observations and 49 physical calls completed under the original
CloudBank ledger for $0.746802. The calls comprised 37 Azure and 12 Vertex
requests. The suite and reports remain in
`artifacts/evals/sensitivity-rule-preference-20260910*`. Forty-seven answers
were materially accepted. GLM's second fire answer correctly described the
changed state but incorrectly predicted an undecided permission outcome if
the suspended rule were restored. The original baseline has a stronger
permit rule, so permission would be accepted. That counterfactual error
remains a material failure in the original report and review.

That evidence justified one short GLM-only chat reminder to account for
configured preference blocks when discussing another configuration. It adds
no scenario example or specific answer. Root checked all 63 model/feature
guidance combinations: only GLM chat changed. The committed source is
`234ffc97522b5d82e0a4a4d05082d88a4ab0c173`, with implementation fingerprint
`3fbbfeffa6fae65ad7bc79e6f32fc131cb56a51c0d833c46cc0cb90285150ce9`.
All 21 GLM chat cases, the original 19 plus the two new sensitivity cases,
were then tested three times. This was a full affected-feature regression,
not a repeated attempt to obtain one favorable answer.

The 63-observation GLM allocation completed in eight minutes and two seconds.
All 64 physical calls used Azure and succeeded, costing $0.340694. Every
complete answer and draft was inspected, with root independently reviewing
the 15 observations most relevant to the earlier causal and counterfactual
errors. All 63 were materially accepted, and the wrong restoration
prediction did not recur. Four automatic phrase-matcher misses remain in the
raw report and have exact-answer adjudications. Minor formal wording and
presentation caveats are explicitly retained under the user's stated
tolerance; they did not justify further tuning.

The other 1,017 selected observations were replayed offline under the final
source with network connections disabled. All 1,425 complete logical request
sequences and deterministic application results were identical. This covers
all 576 non-chat observations and 441 chat observations for the seven
unaffected models, including their 42 new sensitivity answers. The proof is
`artifacts/model-qualification-20260909/glm-guidance-unchanged-path-compatibility-20260910.json`.
Original report, review and request hashes are bound throughout the source
lineage. The eight newly inspected lexical decisions, four from the seven
unaffected models' sensitivity cases and four from the GLM regression, use
the existing bounded helper; its 16 negative-control tests pass.

The final release assessment covers 45 cases, three repetitions and eight
models, totaling 1,080 observations: 504 chat and 576 non-chat. It retains
1,057 original automatic passes, 21 exact lexical adjudications and the two
earlier explicit nonblocking assessments (GLM's optional grouping category
and Sonnet's quotation of supplied current-state text). There are no missing
observations or material failures among the selected final evidence. The
earlier GLM failure, all prior failed runs and every original automatic flag
remain unchanged. The final receipt is
`artifacts/model-qualification-20260909/composite-eight-model-final-release-assessment-20260910.json`,
SHA-256 `49ed425d36fdff108f425351c9767dd5be54f30eba62d943dfa189a618a20df6`.

The settled lifetime ledger records $65.361387 spent, zero pending and
$34.638613 remaining under the unchanged $100 cap. No paid OpenRouter calls
occurred. The two new sensitivity cases were unseen checks on first
execution, followed by an explicitly documented GLM regression after a
demonstrated failure. This is application qualification with an iterative
development history, not a claim of a universal untouched holdout, general
model ranking or guaranteed correctness of future answers. Hosted rollout
and native-client acceptance retain their separately scoped receipts.


## Traceability correction after the consolidated review

The GLM proposer provenance reminder has direct failure evidence, in addition
to its separately diagnosed explicit-field omissions. In
`artifacts/evals/full-qualification-final-20260909/cloudbank-glm-5.3.json`,
`propose-fire-monitor-fact:1` attributes the newly stipulated temporary monitor
to documents about an existing monitor (evidence hash
`9d063ecef9229a30091ef6d22858f9f4187ce0c980699aa3fb57da2c76ec6627`).
`propose-medical-alternative-assumption:2` attributes the new patient-specific
assumption to general drug-class guidance (evidence hash
`26abb3670a84a23b6eee358ab473fcb355930f401347afd8dbfae78d96ec3fed`).
The original agent assessments mark both as unsupported provenance. The report
SHA-256 is `09d9d8a6d141d6c2581c4f4a4adaac05398109d4227ce07de98f100e5ec1f5db`;
its `glm-evaluation-answer-reviews.json` SHA-256 is
`779861659c4cc29ae21eb511e31068dbf6a8a00bb2e0f5819004410724c98577`.
These immutable records justify retaining the short shared provenance rule.
Earlier wording that summarized only GLM field loss was incomplete. No new
prompt tuning or inference was needed to establish this provenance.
