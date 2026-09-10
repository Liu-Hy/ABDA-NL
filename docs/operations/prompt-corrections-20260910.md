# Prompt corrections from inspected feature outputs

The first repeated qualification batch was stopped with its original reports
unaccepted. These changes address specific inspected responses. They do not
change model-selection benchmarks, generation limits, or acceptance thresholds.

## Reviewer alignment

Sonnet 5 incorrectly called two faithfully requested rules suspicious bridges:
`review-clean-fire-rule:1` (evidence `9122cfd49abc5861ea40955dde3b880255fdbca3d097c997e284d98d48b6e11f`)
and `review-respects-explicit-user-category-and-strictness:1` (evidence
`2d8eaf3b76b7decd823d48fd5d7ccf7e79f1df7ea09fe950c703932430779062`).
Gemini 3.1 Pro also questioned the explicitly requested, positive support rule
in `propose-popov-support-rule:1` and suggested rebuttal between compatible
claims. The previous shared reviewer instruction encouraged this broad warning.

The shared correction restricts this concern to a dependency the Proposer
invented instead of translating the user's request. Reusing existing literals
or combining premises is not itself a mis-encoding. It distinguishes decision
conclusions from facts, assumptions, and intermediate propositions. Explicitly
requested inferences are respected. Duplicate-rule detection and warnings for
wrong premises, polarity, or edit targets remain in place.

Other inspected Sonnet advisories called a supported forward reference a
dangling premise, demanded a rewrite of source metadata the user expressly
preserved, and described a strict rule as a duplicate of a defeasible rule.
The reviewer now receives explicit scope guidance for the first two cases.
Duplicate comparisons require matching formal type, strength, and activation
as well as premises and conclusion; the deterministic helper is aligned too.

Opus also called the supported `user instruction` source label an invented
source in both Popov support-rule repetitions and in new sensor rules. The
reviewer instructions now explicitly recognize this default for user-stipulated
content. It does not imply that a corpus document supports the new inference,
and an explicitly chosen source still takes precedence.

## Claude explanation precision

Sonnet 5's `fire-baseline-recommendation:1` said there were three decision arguments. Opus 5's
corresponding explanation counted two pro-burn arguments. The supplied graph
contains three distinct pro-burn derivations and one opposing derivation.
Ecology and culture are two useful themes, but they are not an argument count.
Both Claude 5 models now receive a short reminder to count graph identities
and to distinguish thematic grouping from distinct derivations.

Opus 5's `fried-chicken-v1-item-question:1` correctly accepted crispiness but
said either rebuttal or undercut would independently defeat sogginess. In this
variant the rules have equal preference; the accepted undercut is decisive.
Only Opus receives the additional reminder to distinguish accepted defeating
arguments from equal-strength rebuttal and to avoid unsupported counterfactuals.

These additions are selected from the catalog model identity through billing,
retry, recording, and same-model fallback wrappers. Unaffected models receive
the byte-identical chat prompt. The shared chat template is unchanged.

## Terra defeat terminology

Terra's `fried-chicken-multiple-selected-items:1` correctly left both ordering
conclusions undecided but said neither default argument defeats the other.
The saved graph has defeat edges in both directions (evidence
`d63a3a915a0530bd79ab98a8393dc6861cc2d3b205af5d4d02950b43d8787e2d`).
Terra alone receives a short reminder to distinguish mutual defeat from a
winning argument and to say neither prevails when both remain undecided.

In `unattacked-selected-argument:1`, Terra correctly explained the selected
unattacked fact but generalized that support and no accepted attacker suffice
for acceptance. An undecided defeating attacker is a counterexample. Its
guidance now states the grounded criterion: all defeating attackers must be
rejected. The observed fact explanation and computed labels were already correct.

## Verification status

The original observations and all failed drafts remain evidence. Focused
wrapper tests check scope and identical prompts for unaffected models. Paid
replay must inspect actual new outputs before these corrections are accepted;
full repeated model-by-feature qualification remains required afterward.
