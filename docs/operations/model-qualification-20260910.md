# Model and feature qualification, September 10, 2026

This preserves the earlier hosted release evidence. The subsequent review
corrections withhold GLM and qualify seven models with 945 observations; see the
[current review guide](../demo-revision-review-guide.md) for that assessment,
its source boundary, and the final $67.664447 evaluation total.

The release pool contains eight models: Claude Sonnet 5, Claude Opus 5,
GPT-5.6 Terra, GPT-5.6 Sol, Gemini 3.8 Flash, Gemini 3.1 Pro Preview,
GLM 5.3, and Kimi K3. Funded access, BYOK, and optional MCP server LLM tools
share this pool. The default remains the stable `balanced` profile identifier,
now selecting Sonnet 5. Every funded route uses Azure or GCP with the same
canonical model configured on OpenRouter for qualifying provider failures.

| Model | Funded provider | Input / output USD per million tokens |
| --- | --- | --- |
| Claude Sonnet 5 | Azure Foundry | 2.00 / 10.00 |
| Claude Opus 5 | Azure Foundry, scoped deployment | 5.00 / 25.00 |
| GPT-5.6 Terra | Azure Foundry | 2.00 / 12.00 |
| GPT-5.6 Sol | Azure Foundry | 4.00 / 20.00 |
| Gemini 3.8 Flash | GCP Vertex | 1.50 / 7.50 |
| Gemini 3.1 Pro Preview | GCP Vertex | 2.00 / 12.00 |
| GLM 5.3 | Azure Foundry | 2.10 / 6.60 |
| Kimi K3 | Azure Foundry | 3.30 / 16.50 |

These are the catalog's verified input/output rates used for this release,
not cache rates, benchmark task costs, or reconciled invoices. Gemini Pro's
conservative input limit is 200,000 tokens. Flash reservations use gross
prices rather than assuming promotional credits. Provider inventory, tariffs,
and public benchmark sources are in the [deployment record](model-deployment-plan-20260909.md).
Public benchmarks guided selection; paid testing evaluated ABDA features and
prompts rather than recreating a general model leaderboard. Kimi and GLM add
family choice. GLM is optional and does not displace Gemini Pro on value.

Haiku, GPT-5.6 Luna, and Gemini 3.5 Flash-Lite are excluded. DeepSeek V4 Flash
0731 remains an internal candidate after repeated material source, refinement,
reviewer, and provider failures. Its deployment is retained but the public
menu does not expose it. The previously public Sonnet 4.6 is superseded.

The accepted evidence covers 45 cases, three repetitions, and all eight models,
for 1,080 observations across grounded chat, item questions, corpus questions,
sensitivity, adding and modifying rules, facts, assumptions, refinement,
semantic review, and current authoring context. It includes all six bundled
scenarios and custom, imported, renamed, ambiguous, adversarial, and edge cases.
Every actual answer and rejected draft was inspected. Exact full-request and
response duplicates reuse an identified review with evidence hash bindings.

The final runtime source is `234ffc97522b5d82e0a4a4d05082d88a4ab0c173`,
with fingerprint `3fbbfeffa6fae65ad7bc79e6f32fc131cb56a51c0d833c46cc0cb90285150ce9`.
The original 43-case composite qualified 1,032 observations. A scope audit added
rule suspension and changed preference ordering, exercised three times for
every model. Seven models passed these additional cases without prompt changes.
GLM gave one wrong optional prediction about restoring the disabled rule.
Its original answer remains preserved as a material failure.

The only subsequent prompt change is one general sentence for GLM chat:
“When discussing a different configuration, account for the stated preference
blocks; opposing conclusions do not imply equal strength or an undecided outcome.”
All 21 GLM chat cases were then rerun three times, yielding 63 accepted
observations. The wrong restoration prediction did not recur. All 1,017 retained
observations, including every non-chat feature and the other seven models' chat,
were replayed offline with identical complete requests and deterministic results.
Those retained observations cover 1,425 logical calls. Guidance checks across all
63 catalog-model/feature combinations confirm that only GLM chat changed.

All 1,080 selected observations passed AI agent answer-by-answer assessment for material correctness. This was not human review. The
original automatic results remain separate: 1,057 passed and 23 require explicit
assessment. Twenty-one are narrow phrase-matching false negatives. One Sonnet
answer correctly quotes both reference documents and additionally quotes an
actual current-state heading; the corpus-only scorer rejects the heading.
One GLM assumption omits a requested optional category. Its uncertainty,
description, source, effective activation, and preference strength are correct;
applying the requested category produces an identical argumentation framework.
That grouping-metadata omission remains a visible, nonblocking limitation.
No raw score, operation, or provider response is rewritten to hide these cases.

Prompt changes address recorded failures with short general rules. Chat context
puts each instantiated argument's label beside its configured rule. The explicit
accepted-defeater list is enabled only for Sonnet 5 and the internal DeepSeek
candidate, where diagnosed causal mistakes justified it; other passing prompts
keep their previous representation.
Quote handling preserves exact source spans across adjacent retrieval chunks,
supported boundary typography, explicit prefix citations, and paragraph boundaries.
Corrected forward-reference meanings reach the reviewer before its call.
Minor counts, terminology, explanatory precision, and presentation issues remain
recorded where the answer's outcome and operative cause are correct. No further
tuning is needed for release under the user's stated tolerance for minor errors.

Lifetime CloudBank test spending is $65.361387, with zero pending reservations
and $34.638613 remaining under the original $100 cap. The 48 added sensitivity
observations cost $0.746802 across 49 successful physical calls. The final GLM
regression cost $0.340694 across 64 successful Azure calls. The separate funded
MCP question/proposal probe cost $0.048024 within the same lifetime budget.
Paid OpenRouter calls remain zero. Test processes excluded OpenRouter and personal
direct-provider credentials and used the original persistent ledger across
retries, resumed work, diagnostics, and MCP.

The admitted catalog SHA-256 remains
`2a0090bbac38e18cbe189c8b088faba86154baeace1624fa3c9eb63bc6dc8c88`.
Catalog promotion changed admission, display, the default profile mapping,
and verified flags only. Model request IDs, adapters, reasoning settings,
context/output limits, tariffs, credential references, verified funded resource
and project bindings, and the other models' prompts stay identical to their
qualified evidence.

The final 1,080-observation assessment is
`artifacts/model-qualification-20260909/composite-eight-model-final-release-assessment-20260910.json`,
SHA-256 `49ed425d36fdff108f425351c9767dd5be54f30eba62d943dfa189a618a20df6`.
Root independently verified all 96 input artifact hashes, all 1,080 unique
observations, all 88 complete feature cells, and the settled original ledger.

The retained-path proof is
`artifacts/model-qualification-20260909/glm-guidance-unchanged-path-compatibility-20260910.json`,
SHA-256 `00f223faa9e3502a5e946f97d11a76652945f5eff90978bfe8f32df6a8dbed10`.
The final GLM raw report SHA-256 is
`ea4a6a5d02e14d218187c24c19622d311b7bd617e2e00acb89eca8703738bb20`;
its combined explicit review SHA-256 is
`b802b5f7d4968646bb390dbba282b1b0a00af2792e43127ee230e181de05f8b6`.
The earlier 1,032-observation composite remains preserved with SHA-256
`67c327916526c127ce6c603e8734c2479844991e5383da72c031a0a693770a6d`.
Exact receipts and raw evidence remain under `artifacts/model-qualification-20260909/`
and `artifacts/evals/` in the workspace. The [evaluation record](evaluation-baseline-20260909.md)
records their lineage, limits, and preserved failures.

This is iterative application qualification, not an independent locked blind
holdout or a new general-model ranking. The two added sensitivity cases were
unseen before their first run; one then informed the GLM reminder. Deployment,
OIDC sign-in, and external subscribed-client acceptance have separate evidence.
