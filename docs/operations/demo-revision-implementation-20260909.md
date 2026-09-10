# Demo revision implementation, September 9, 2026

This record tracks implementation of the approved
[review](../demo-revision-review-20260909.md). The starting revision was
`85bd4ae75d09a55fb65d1cd254d2ab1d833e8e18` on `development`.
The review is preserved as the investigation record. Implementation is in progress.

## Accepted scope and current work

- Selected question items become editable drafts with removable context references.
- Conversations have browser-local, account-scoped history, snapshot export,
  deletion, and explicit forks. Snapshots preserve unsaved scenario operations.
- An individual derivation inspector links premises, subarguments, formal rules,
  computed labels, and attacks without merging distinct derivations.
- Quoted evidence is checked against actual supplied source spans. Formal context
  references are validated against the current scenario before a model call.
- The five named administrators receive an idempotent $50 lifetime grant in a
  separate $250 pool, preserving spent and reserved amounts. Public trial and
  OpenRouter emergency limits remain independent.
- Funded requests use Azure or GCP, followed by the same model on OpenRouter only
  after a qualifying provider failure. CloudBank gets at most one retry.
- A single qualified catalog controls funded access, BYOK, and MCP admission.
- Every selected model must pass application-specific feature tests. Prompts are
  tuned when and only when recorded testing identifies a need.
- Evaluation uses one persistent $100 CloudBank budget across processes, retries,
  resumed runs, and tuning. Test processes do not receive OpenRouter credentials.
- Subscribed Codex and Claude Code workflows need complete create, edit, apply,
  and readback evidence. Their ordinary MCP tools work with zero ABDA model credit.

Haoyang subsequently removed Claude Haiku, GPT-5.6 Luna, and Gemini 3.5 Flash-Lite
from the candidate pool and requested 2 or 3 stronger economical alternatives.
Those three models are excluded from planned paid testing. Public benchmarks
guide model selection; application tests do not recreate general benchmarks.

Haoyang also requested Gemini 3.1 Pro. It is now a candidate alongside Gemini
3.8 Flash. The live September 9 [LiveBench table](https://livebench.ai/)
shows Pro High at 77.0 and $0.286 per successful task, compared with GLM 5.3
at 76.1 and $0.450. These task costs retain the benchmark's own reasoning
settings and are distinct from Azure/GCP token tariffs. GLM is an optional
family choice, not the strongest value choice in this comparison.

## Verification and deployment state

The frontend's initial Chromium selection passed 19 tests. Firefox also passed
the intercepted workflows and accessibility scan. WebKit cannot launch on this
host because system libraries are absent. No host packages were changed.

Azure inventory confirmed sufficient existing GlobalStandard quota. New Terra,
Sol, and DeepSeek V4 Flash 0731 deployments succeeded in the funded resource.
A Luna deployment was also created before Haoyang removed it from the selection;
it is unpublished and has received no inference traffic in this work.
Initial Sonnet 5 and Opus 5 deployment attempts required additional provider metadata.
No candidate has been promoted merely because its deployment exists.

After Haoyang approved the UIUC organization details and Anthropic terms,
Sonnet 5 was deployed successfully with a pinned model version. An existing
Opus 5 deployment in the same CloudBank subscription is being reused through
private, model-specific Azure settings. After Haoyang approved Fireworks
enablement, its feature registration completed and GLM 5.3 and Kimi K3 were
deployed successfully as DataZoneStandard, capacity 10 each. Their prices and
the prepared requests are recorded in the
[deployment plan](model-deployment-plan-20260909.md).

DeepSeek's verified Azure input/output prices are $0.44/$1.32 per million
tokens. Grok 4.6 remains on hold because neither its live SKU metadata nor
Azure's public price inventory establishes a price for this exact version.
No inference has been sent to Grok. Gemini 3.1 Pro's standard GCP prices are
$2/$12 below 200,000 input tokens. The implementation caps conservative input
estimates at 200,000 to avoid the higher context tier. Flash's advertised
50 percent promotion is a credits-back offer, so reservations use its gross
$1.50/$7.50 rates until actual rebates can be reconciled. See
[Google's pricing terms](https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing).

The initial Terra and Sol availability smoke passed all 12 inspected cases
and 16 physical response checks. It cost $0.503896 from CloudBank, with no
OpenRouter calls, failed requests, or prompt tuning. Full repeated feature
qualification remains required; the smoke alone does not admit a model.

The repeated baseline was stopped after inspection found application defects in
quotation whitespace matching, narrow rule edits, and the formal state supplied
to the reviewer and chat model. The 81 attempted observations were inspected.
After an audited $0.079019 correction for Sol cache-write prices, those first
two runs cost $1.597855. Their 136 physical attempts used Azure; none used GCP
or OpenRouter. The original receipts are preserved. Subsequent availability
checks exercised all seven additional candidates, including successful calls
to both Gemini models through the funded Vertex project. The GLM and Kimi
replay passed all 12 inspected cases after the adapter began forwarding the
configured low reasoning effort and Kimi's supported required-tool setting.
Their prompts and output allowances stayed unchanged during that replay.
After the completed availability runs, the lifetime ledger records $4.901138
spent, no pending reservations, and $95.098862 remaining. Full repeated feature
qualification remains pending. The detailed, dated findings are in the
[evaluation record](evaluation-baseline-20260909.md). Costs use reported token
usage and conservative tariffs; they are not reconciled cloud invoices.

The credential sanity check following
[Haoyang's setup tutorial](https://github.com/Liu-Hy/cloudbank-llm-setup)
corrected an earlier diagnostic mistake: the personal `gcloud` login and ADC
are separate credentials. Existing ADC refreshes successfully, belongs to a
verified CloudBank identity, and has prediction and service-use permissions on
the configured `access-...` project. Its quota project matches, project billing
is enabled, and both Google APIs are enabled. The application independently
pins this project in the Vertex URL, ADC quota setting, and quota header.
The personal "Gemini API" project is excluded. No new login is required locally.

Azure endpoint and key pairs were compared privately with current resource
metadata and keys. The default resource and scoped Opus resource both belong to
the pinned CloudBank subscription. Their configured deployment names resolve.
The credential probes made no inference calls or configuration changes.
A subsequent launcher check found a separate local configuration gap: the
ABDA-specific Claude provider field was unset, allowing the development server
to default to the legacy direct Anthropic client for requests without explicit
model options. The private local override now selects Foundry, all prior fields
are preserved in place and in a protected backup, and `demo restart` passed.
Hosted managed routing and isolated paid evaluations already selected CloudBank.
Gemini's funded availability is confirmed; its full repeated feature
qualification remains pending.

The shared Delta launcher was serving JURA at the start. It now serves ABDA-NL
for the real subscribed-client MCP checks. The local database was backed up
with SQLite's backup API and passed an integrity check before migration.
Paid inference tests use an isolated database and Slurm allocation, independent
of the demo's account and credit records.

The subscribed-client MCP acceptance is complete for actual Codex and Claude
Code sessions, including creation, editing, application, readback, account
isolation, token revocation, and unchanged ABDA credit. See the
[acceptance record](mcp-client-acceptance-20260909.md).

The hosted service has not yet received this revision or the administrator
credit migration. A compatible recovery image is being built from `2f1483f`
before the two-phase rollout described in the
[rollout plan](revision-rollout-20260909.md). That image retains the previously
qualified public model while new candidates undergo qualification.

Sanitized, dated provider inventory and deployment receipts are stored under
`artifacts/model-qualification-20260909/`. Paid evaluation receipts use
`artifacts/evals/`; these are separate from public trial and administrator grants.
