# Malformed proposer envelope replay

The stopped full qualification run recorded two Sonnet failures in which a
structured fact response placed `id` inside `fact` and omitted the required
top-level `id`. `diff_op_from_tool_input` indexed that missing key before the
deterministic validator could inspect the response, producing `KeyError`.

The preserved observations are:

| Case | Evidence SHA-256 |
| --- | --- |
| `fact-promotes-pending-reference:1` | `bd15a26a35c9ce288595b97edee01113b8567fdaee70de3b16f23cf81931700d` |
| `refine-pending-fact-is-not-already-applied:1` | `6b401da5db3ce3c771cd08f72f9b904ec445746e2f1776cae3e7e8265ab43409` |

Both are in the original
`artifacts/evals/full-qualification-20260909/cloudbank-claude-sonnet-5.json`.
Their fact meanings and intended sources were appropriate. The failures concern
the required response shape and application handling.

Envelope extraction now preserves a missing identifier or payload as a missing
value, allowing the existing validator to produce blocking feedback and request
a corrected proposal. It does not infer an identifier from a nested field.
Malformed `new_premise_notes` containers likewise become a blocking validation
issue instead of raising an iteration error or disappearing. Canonical payloads
and the existing explicit modify-rule identifier coercion retain their behavior.

Offline tests replay the exact nested-identifier shape through the full
proposer, deterministic validator, metering, and failover wrappers. They check
a valid second response, exhaustion after three malformed responses, usage and
cost for every physical attempt, zero outstanding local reservations, no
OpenRouter invocation, and no scenario mutation before Apply. They also cover
missing payloads for all four edit tasks and correction of malformed premise
metadata. No paid inference or prompt change is part of this fix.

## Clarifying correction feedback

The next diagnostic confirmed that malformed responses enter the bounded
correction loop. One Sonnet fact proposal recovered on its third attempt, but
a fact refinement exhausted all three attempts. Its first refinement repeated
the identifier both at top level and inside `fact`; subsequent drafts kept the
nested identifier and dropped the required top-level field. The feedback had
reported an extra property at `<root>`, meaning the root of the fact payload,
which was ambiguous relative to the tool input.

Schema errors now use the complete payload path, such as `/fact` or
`/fact/description`. Missing top-level identifiers are reported even when the
payload is also malformed. On a schema failure, one general instruction states
that `id` and the payload object are sibling fields. This applies to all edit
types and models, only during correction. It adds no scenario-specific example
or new proposer prompt branch. The original failing refinement is retained as
evidence `3d219e39ec0b98141d58fd5feae1a5e259f70f3054e2036f3661adc8b152463b`.

The same saved run exposed two further deterministic boundary issues:

| Observation | Evidence SHA-256 | Correction |
| --- | --- | --- |
| Sonnet `propose-strict-rule-with-negative-premise:1` | `bec212318c81a6dcdc917972ecf7dba540cdb91c2994eb9c488c2294527ce22f` | A strict rule with the same premises and conclusion as a defeasible rule is not automatically a duplicate. Duplicate normalization now also compares type, block, and activity, including their schema defaults. |
| Opus `propose-fried-chicken-forward-reference:1` | `ff9fa81a761f9c57728bcb39e5285e75ab6341415299b0f5acd05c85ebda42c1` | The proposed rule and its new pending premise both used `dinein_open`. That premise could never be promoted to a fact while the rule occupied its identifier. The validator now requests a distinct rule identifier through the existing bounded correction loop. |

The collision check applies only to an added rule whose previously undeclared
premise has the same base identifier as that new rule. References to existing
rule names, including negative undercut literals and existing modify-rule
references, retain their behavior. A replay of the exact Opus payload verifies
a corrected second proposal, billing for both proposals and the reviewer, no
backup-provider call, no premature mutation, and successful later materialization
of the pending premise. The duplicate tests also exercise strict, stronger,
weaker, inactive, and actually identical rules through review and Apply.
