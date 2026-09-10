# Model and feature qualification, September 10, 2026

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

These are the catalog's verified standard input/output rates for this release,
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

The accepted evidence covers 43 cases, three repetitions, and all eight models,
for 1,032 observations across grounded chat, item questions, corpus questions,
sensitivity, adding and modifying rules, facts, assumptions, refinement,
semantic review, and current authoring context. It includes all six bundled
scenarios and custom, imported, renamed, ambiguous, adversarial, and edge cases.
All actual answers and rejected drafts were inspected. Exact full-request and
response duplicates reuse an identified review; hash bindings prove that reuse.

The final 456 chat observations were generated against commit `a2001f68596e8fba436a9bf4b252f8f8f020abd9`,
with fingerprint `502b8637bdc35d9aba5b1fee5fb0609ea3998cba1294ff91a9e696a1018ae6dd`.
The 576 non-chat observations were replayed offline to prove that all 576
complete request sequences, covering 975 logical calls, and their deterministic
application results remain identical on that source. Twenty-four supplemental observations replace the earlier strict
rule and forward-reference paths. Earlier failures remain preserved.

All 1,032 observations passed manual material-correctness review. The original
automatic results remain separate: 1,014 passed and 18 require an explicit
assessment. Sixteen are narrow phrase-matching false negatives. One Sonnet
answer correctly quotes both reference documents and additionally quotes an
actual current-state heading; the corpus-only scorer rejects the heading.
One GLM assumption omits a requested optional category. Its uncertainty,
description, source, effective activation, and preference strength are correct;
applying the requested category produces an identical argumentation framework.
That grouping-metadata omission remains a visible, nonblocking limitation.
No raw score, operation, or provider response is rewritten to hide these cases.

Prompt changes remain short and address recorded failures. The final chat
context correction puts each instantiated argument's label and accepted
defeaters beside its configured rule, keeping potential undercutters distinct
from current causes. Quote handling preserves exact source spans, including
adjacent retrieval chunks, supported boundary typography, explicit prefix
citations, and paragraph boundaries. Corrected forward-reference meanings reach
the reviewer before its call. Minor counts, terminology, and general explanatory
precision remain documented where they do not change a correct answer.
No additional tuning was needed after the final review.

Lifetime CloudBank test spending is $64.273891, with zero pending reservations
and $35.726109 remaining under the original $100 cap. The final chat phase cost
$5.912115 and completed 466 successful physical calls: 352 Azure and 114 Vertex.
The separate real funded MCP question/proposal probe cost $0.048024 within the
same lifetime budget. Paid OpenRouter calls remain zero. Test processes excluded
OpenRouter and personal direct-provider credentials and used the original
persistent ledger across retries, resumed work, diagnostics, and MCP.

The catalog promotion changes admission, display, the default profile mapping,
and verified flags only. Model request IDs, adapters, reasoning settings,
context/output limits, tariffs, credentials, and prompt files stay identical
to the qualified source. Exact qualification receipts are retained under
`artifacts/model-qualification-20260909/` and `artifacts/evals/` in the workspace.
The [evaluation record](evaluation-baseline-20260909.md) records their lineage,
limits, and preserved failures. Deployment and authenticated client acceptance
are recorded separately from model qualification.

The composite release assessment is `artifacts/model-qualification-20260909/composite-eight-model-release-assessment-20260910.json`,
SHA-256 `67c327916526c127ce6c603e8734c2479844991e5383da72c031a0a693770a6d`.
Root independently verified all 59 source artifact hashes, 1,032 unique reviewed
observations, 88 complete accepted feature cells, and the settled original ledger.
The admitted catalog SHA-256 is `2a0090bbac38e18cbe189c8b088faba86154baeace1624fa3c9eb63bc6dc8c88`.
