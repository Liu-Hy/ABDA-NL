# Demo revision implementation, September 9, 2026

The current independent-review brief is concentrated in the
[requirements](../demo-revision-contract.md) and
[review guide](../demo-revision-review-guide.md). This file retains implementation
history and evidence pointers; its completion assessments do not establish that
every design interpretation was explicitly approved by the user.

This record tracks implementation of the approved
[review](../demo-revision-review-20260909.md). The starting revision was
`85bd4ae75d09a55fb65d1cd254d2ab1d833e8e18` on `development`.
The review is preserved as the investigation record. Implementation, paid
qualification, deployment, and automated acceptance are complete.

## September 10 completed release

Commit `00d773123e1e04481c68ebad7b10d6a93e70da86` admits eight qualified models:
Sonnet 5, Opus 5, GPT-5.6 Terra and Sol, Gemini 3.8 Flash and 3.1 Pro Preview,
GLM 5.3, and Kimi K3. The stable `balanced` profile now selects Sonnet 5.
DeepSeek is held out after repeated material source, refinement, reviewer, and
provider failures. Haiku, Luna, and Flash-Lite remain excluded.

The [qualification summary](model-qualification-20260910.md) binds 1,080 accepted
observations to 45 cases, three repetitions, eight models, and all eleven
application feature groups. The 456-observation chat suite ran against
`a2001f6`. A later audit added 48 sensitivity observations covering rule suspension
and preference changes. One GLM counterfactual ignored unequal preferences,
so a single general GLM-only reminder was added in final runtime commit
`234ffc97522b5d82e0a4a4d05082d88a4ab0c173`. Its complete 63-observation chat
regression passed. Exact offline request/result replay proves compatibility for
1,017 retained observations across all non-chat features and other models. All provider outputs and earlier failures remain
preserved. Twenty-one phrase-matching adjudications and two explicit nonblocking
assessments are separate from the original automatic scores.

The final chat context supplies the status of each instantiated argument and
its accepted defeaters beside its configured rule. It distinguishes potential
undercutters from current causes. Quote handling preserves original source
spans across adjacent retrieval chunks, supported boundary typography, explicit
prefix citations, and paragraph boundaries. Corrected forward-reference meanings
reach the reviewer before its call. Prompt changes address recorded failures
with short general rules. No further tuning is needed after the final GLM review.

Catalog promotion changes only admission, display, verified flags, and the
balanced profile mapping. Models, request IDs, adapters, reasoning settings,
limits, tariffs, and other models' prompts are unchanged from their qualified source.
The admitted implementation fingerprint is
`3fbbfeffa6fae65ad7bc79e6f32fc131cb56a51c0d833c46cc0cb90285150ce9`.

Lifetime CloudBank testing cost $65.361387, with zero pending and $34.638613
remaining under the original $100 cap. This includes retries, resumed runs,
diagnostics, tuning, and the $0.048024 funded in-process MCP probe. No paid
OpenRouter tests ran. The 48 added sensitivity observations used 49 successful calls, costing
$0.746802. The final GLM regression used 64 successful Azure calls, costing
$0.340694. Earlier Azure and verified CloudBank Vertex evidence remains preserved.

The compatible hosted recovery completed at 06:40 UTC on September 10 with
schema 0006, the registered administrator's $50 lifetime grant, four future
entitlements, preserved spending and reservations, and automatic named
activation. Both web and manual job use compatible code. Its
[receipt](hosted-recovery-rollout-result-20260910.md) preserves exact image and
accounting evidence. All eight hosted primary configurations and the referenced
OpenRouter key now pass read-only readiness checks. The final image is healthy
at `https://demo.abda-nl.org` in revision `abda-nl-stg-web--qualified-eight-0910`.
The manual job uses the same image, previous replicas have drained, and the
post-deployment ledger proof is identical to the pre-deployment proof. The
[final rollout receipt](hosted-final-rollout-result-20260910.md) binds those checks.
Exact-source CI, image security policy, both cryptographic provenance checks,
and hosted public browser checks passed. Actual subscribed Codex and Claude
Code clients each completed the six-tool hosted workflow, including a versioned
edit and readback. Separate owner-browser checks confirmed the original saved
projects and complete scenario and argument graph. Ownership, stale and invalid
writes, missing server-LLM scope, repeated revocation, and cleanup passed.
Both synthetic accounts are suspended and unverified, their projects are
archived, all four tokens are revoked, and raw temporary token and cookie files
are removed. All seven accounting tables remain unchanged. The
[hosted native-client receipt](hosted-native-mcp-acceptance-result-20260910.md)
preserves the successful phases and earlier failed harness attempts separately.
The registered administrator's own browser sign-in remains a personal
acceptance check; database and account-route verification are complete.

The existing local development login remains available. Its private
`ABDA_LLM_REQUIRE_AUTH=1` override enables funded quota deduction for signed-in
users; the prior false setting routed correctly but skipped trial deduction.
All other private configuration is preserved, including enabled fallback.
The launcher restarted on final source `234ffc9` at 08:21 UTC. Final served
assets and all eight model menus match source, health checks pass, and anonymous
private trial access returns HTTP 401. Comprehensive UI acceptance remains
applicable because the entire static tree and catalog are byte-identical to
the tested `00d7731` source. See the [local acceptance record](local-demo-acceptance-20260910.md).
The [UI requirements audit](ui-requirements-acceptance-20260910.md) maps every
accepted frontend requirement to its exact evidence and records the limits of
browser-local history, current-scenario forks, and injected-outage coverage.
CI-only commit `07928fc307c6fe73c6177af8e566d915f2e002fd` adds the eight existing
exploration workflows to browser CI. All 52 tests now pass in each of Chromium,
Firefox, and WebKit. Both Python versions pass 1,454 tests with 53 skips,
restricted-role PostgreSQL acceptance passes, and CodeQL reports zero findings.
Application and test files are unchanged from the deployed runtime. The
[CI addendum](ui-browser-ci-addendum-20260910.md) preserves this separate proof.

The earlier chronological verification notes below describe their recorded
checkpoints and are superseded by this integration status.

## Accepted scope

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
- Every selected model passed application-specific feature qualification.
  Prompts were tuned when and only when recorded testing identified a need.
- Evaluation uses one persistent $100 CloudBank budget across processes, retries,
  resumed runs, and tuning. Test processes do not receive OpenRouter credentials.
- Subscribed Codex and Claude Code workflows have complete hosted create, edit,
  apply, and readback evidence. Their ordinary MCP tools work with zero ABDA model credit.

Haoyang subsequently removed Claude Haiku, GPT-5.6 Luna, and Gemini 3.5 Flash-Lite
from the candidate pool and requested 2 or 3 stronger economical alternatives.
Those three models are excluded from qualification and public admission. Public benchmarks
guide model selection; application tests do not recreate general benchmarks.

Haoyang also requested Gemini 3.1 Pro. It is now qualified and admitted alongside Gemini
3.8 Flash. The live September 9 [LiveBench table](https://livebench.ai/)
shows Pro High at 77.0 and $0.286 per successful task, compared with GLM 5.3
at 76.1 and $0.450. These task costs retain the benchmark's own reasoning
settings and are distinct from Azure/GCP token tariffs. GLM is an optional
family choice, not the strongest value choice in this comparison.

## Earlier verification and deployment checkpoints

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
After the completed availability runs, the lifetime ledger recorded $4.901138
spent. The first full-suite attempt was then stopped at safe case boundaries
after inspection exposed further application and prompt defects. All 169
observations were inspected, including rejected drafts and reviewer advisories.
That stop brought the ledger to $13.346044 spent. A subsequent 25-case diagnostic
cost $2.859686, bringing the total to $16.205730 with no pending reservations
and $83.794270 remaining. It passed 22 material-correctness reviews; three
Sonnet cases require another bounded replay after clearer schema feedback and
reviewer change summaries. Minor imprecision is recorded without blocking
otherwise correct features, following Haoyang's clarification.
The fixes cover malformed edit envelopes, incorrect
duplicate detection, a rule/pending-premise name collision, conflicting reviewer
instructions, and scoped explanation guidance for the affected models. A
focused diagnostic replay precedes full repeated qualification. See the
[prompt corrections](prompt-corrections-20260910.md) and
[edit-boundary record](proposer-envelope-20260910.md).
The detailed, dated findings are in the
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
credit migration. A compatible recovery image from `2df719b` passed source,
container, security, and provenance checks. Its full CI passed 1,273 tests
with 53 opt-in skips on each supported Python version and 44 browser tests
on each of Chromium, Firefox, and WebKit. Protected rollout requests are
prepared, but the newly discovered fixes require a new candidate image.
The two-phase rollout is described in the
[rollout plan](revision-rollout-20260909.md). That image retains the previously
qualified public model while new candidates undergo qualification.

Sanitized, dated provider inventory and deployment receipts are stored under
`artifacts/model-qualification-20260909/`. Paid evaluation receipts use
`artifacts/evals/`; these are separate from public trial and administrator grants.
