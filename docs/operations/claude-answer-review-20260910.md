# Saved Claude answer review

Every recorded Sonnet 5 and Opus 5 answer from the stopped full qualification
run was inspected against the saved scenario, signed argument graph, source
documents, and requested edit. The review includes intermediate proposals,
correction attempts, reviewer feedback, and final operations. It assesses
grounding, semantic fidelity, usefulness, and presentation separately from the
automatic rubric. Identical visible payloads were grouped for inspection, then
each observation received an explicit annotation bound to its own evidence hash.

| Model | Observations inspected | Initial strict approval | Initial strict failure |
| --- | ---: | ---: | ---: |
| Claude Sonnet 5 | 45 | 33 | 12 |
| Claude Opus 5 | 54 | 43 | 11 |

This stopped run does not establish qualification. Both reviewed reports retain
`application_accepted: false`, and original failures remain in the evidence.
One Opus answer correctly says the scenario "accepts" ventilation; the original
automatic label check expected "accepted" and failed. That answer passes manual
inspection, while the original automatic result is preserved as a rubric issue.

The observed defects fall into specific groups:

- Two Sonnet responses placed the required fact identifier inside its payload,
  causing an application `KeyError` before validation. Missing envelopes now
  enter the existing correction loop.
- An Opus rule used the same identifier for itself and its new pending premise.
  The validator now rejects that collision so the premise can later become a
  fact or assumption.
- Both models received false duplicate advisories for a requested strict rule
  matching a defeasible rule's premises and conclusion. Deterministic duplicate
  normalization now also compares type, strength, and activity.
- Reviewer feedback objected to explicitly requested inference shortcuts,
  deliberate preservation of original source metadata, and accurate default
  `user instruction` provenance. These are distinct from a real polarity error
  or the genuine pending-premise collision. Prompt corrections are limited to
  these observed scope failures.
- Sonnet and Opus compressed two ecology derivations into a single category
  and then made incorrect exhaustive argument counts. Opus also overstated an
  equal-strength rebuttal as independently sufficient to reject an argument
  whose defeat actually depended on an accepted undercut. The route-specific
  chat guidance addresses those observed explanation failures.

The unchanged original report hashes are:

| Report | SHA-256 |
| --- | --- |
| `cloudbank-claude-sonnet-5.json` | `e80e1c58062a551217e71c91103a72025e03869c914a99f3b8d53a7a65e44d55` |
| `cloudbank-claude-opus-5.json` | `6db976d37ceb639f6b34be898fe4612b51573b4f18b1e1df5036e437b360125e` |

All files below are under
`artifacts/evals/full-qualification-20260909/`:

- `claude-sonnet-answer-reviews.json` and `claude-opus-answer-reviews.json`
  contain the 99 exact-hash annotations.
- `cloudbank-claude-sonnet-5.claude-reviewed.json` and
  `cloudbank-claude-opus-5.claude-reviewed.json` preserve the separate automatic
  and manual results.
- `claude-review-receipt.json` lists every failed observation, its evidence hash,
  and the concrete reason, plus the original report hashes.

The original source fingerprint is
`26ef5764c1ffca7418617c9f0de8fa95ca77be664e165ee2d076cdaecd424e46`.
The paired oracles remain at
`artifacts/evals/full-qualification-20260909.oracles.json`.

The three application boundary corrections and their saved-response regression
tests are recorded in [proposer-envelope-20260910.md](proposer-envelope-20260910.md).
The combined edit, validator, routing/billing, and API regression passed 209
tests. This inspection and its offline regressions made no paid model calls.

The user subsequently clarified that minor imprecision and harmless advisory
notes should be documented without blocking an otherwise correct feature.
The original verdicts above remain unchanged. Separate calibrated reviews make
the original fire argument-count observations and Opus's V1 causal-precision
caveat nonblocking because the current labels and material explanations are
correct. This yields 34 approved and 11 failed original Sonnet observations,
and 46 approved and 8 failed original Opus observations under that clarified
policy.

The one-pass diagnostic replay used commit `caec702`, source fingerprint
`3aca185407ee645e1deda54ceb96ee37d6020a0082856abca2ab7833d2154d4d`.
All 21 Claude replay cases and every intermediate response were inspected:

| Model | Replay cases | Approved under clarified policy | Substantive failures |
| --- | ---: | ---: | ---: |
| Claude Sonnet 5 | 12 | 9 | 3 |
| Claude Opus 5 | 9 | 9 | 0 |

Sonnet still produced two false assertions that the user should rewrite source
metadata despite requesting a conclusion-only edit. A fact refinement exhausted
three malformed nested envelopes. The latter now fails safely through the
validator rather than raising `KeyError`. Another fact case succeeded on its
third corrected attempt, with that extra cost and latency preserved in its
annotation. Opus's truthful but unnecessary suggestion to check coexistence of
strict and defeasible rules is a nonblocking caveat under the clarified policy.
Its selected-crispiness response is semantically correct; the original automatic
label check missed the unambiguous opening "It's accepted."

The replay cost was $0.849032 for Sonnet and $1.870799 for Opus. These are
diagnostic results, not full qualification. Exact-hash annotations, unchanged
source reports, and separate calibrated reports are under
`artifacts/evals/targeted-replay-20260909/`. The file
`claude-policy-reassessment.json` records each policy-driven verdict change
without replacing the initial annotations. No further prompt changes were made
as part of this inspection.
