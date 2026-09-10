# Review of the demo revision ideas

For an independent code review, start with the two consolidated documents:
[requirements](demo-revision-contract.md) and
[review guide](demo-revision-review-guide.md). They distinguish user intent,
engineering choices, and evidence limits. This file preserves the investigation
and subsequent implementation reports; its status labels are dated
self-assessments, not independent approval.

## Implementation update, September 10, 2026

Haoyang subsequently authorized implementation and parallel subagents. The
current implementation is on `development`; the original investigation below
is retained as a dated record. Its status labels describe the September 9
checkout, not the current implementation. The stable paper branch is separate.

| Area | Implemented and verified | Acceptance status |
| --- | --- | --- |
| Editable question button and selected context | `?` inserts an editable question, preserves existing text, and carries removable item references. Only explicit submission calls a model. | Complete. Local and hosted browser checks passed. |
| Conversations and derivation navigation | Browser-local account-scoped history, New/Delete/export, edit-and-fork, portable scenario snapshots, and an inspector for individual derivations are implemented. Unused minimap code is removed. | Complete. Served-browser acceptance and final-source CI passed. |
| Source evidence | Answers expose exact supplied source spans. Validation covers changed wording, local attribution, adjacent retrieval chunks, supported boundary typography, explicit prefix citations, and paragraph boundaries. | Complete. Paid answer review, served-browser acceptance, and final image checks passed. |
| Five $50 administrator grants | Hosted schema 0006 and reconciliation are complete. The registered administrator has a $50 lifetime grant with spending preserved; the other four identities have entitlements for future verified registration. Restricted-role checks prove conservation and idempotency. | Database and account-route verification complete. The administrator's own browser sign-in remains a personal acceptance check. |
| CloudBank and fallback | Azure/GCP primary routing, at most one CloudBank retry, same-model OpenRouter fallback after qualifying failures, complete attempt accounting, and non-LLM recovery are implemented. All eight hosted primary configurations and the referenced fallback key passed read-only readiness checks. | Complete. Final hosted image is healthy; injected outage checks passed. No paid OpenRouter testing. |
| Shared model pool | Eight models are qualified and admitted in commit `00d7731`, including Gemini 3.1 Pro, Kimi, and GLM. Funded access, BYOK, and optional MCP LLM tools share the pool. DeepSeek remains internal after material feature failures. Haiku, Luna, and Flash-Lite are excluded. | Complete. All eight models appear in the final hosted and local menus. |
| Prompt and feature qualification | The accepted composite covers 1,080 reviewed observations, 45 cases with three repetitions across eight models and all eleven feature groups. Public benchmarks guide selection. Short general prompt rules and application fixes address observed failures. A final GLM-only preference reminder passed its complete 63-observation chat regression. | Complete. Original failures and assessed limitations remain preserved. |
| Subscribed MCP clients | Actual Codex and Claude Code subscriptions completed six-tool workflows against the hosted endpoint with zero ABDA credit. Owner browser readback, stale and invalid writes, ownership and scope denial, revocation, and fixture cleanup passed. A separate funded in-process MCP question/proposal probe also passed. | Complete. Both subscriptions and authenticated browser readback passed. |

The shared CloudBank ledger records $65.361387 spent, zero outstanding
reservations, and $34.638613 remaining under the original $100 lifetime cap.
This is conservative application accounting, not a reconciled provider invoice.
All paid qualification is complete. The accepted composite retains 1,057 original
automatic passes, twenty-one bound phrase-matching adjudications, and two explicit
nonblocking assessments. Earlier failed drafts and original automatic flags
remain unchanged. The [qualification summary](operations/model-qualification-20260910.md)
explains coverage, exact evidence hashes, source compatibility, and limitations.

The compatible hosted recovery completed at 06:40 UTC on September 10. Its
[receipt](operations/hosted-recovery-rollout-result-20260910.md) records the
healthy image, schema, quota transfer, and deterministic acceptance checks.
The final eight-model image from `234ffc9` is healthy on the hosted demo after
exact-source CI, image security policy, and both provenance checks passed.
The [final rollout receipt](operations/hosted-final-rollout-result-20260910.md)
binds the image, preserved settings, and hosted ledger inspection, which is
identical to the pre-deployment proof.
The [hosted native-client receipt](operations/hosted-native-mcp-acceptance-result-20260910.md)
records both successful subscription workflows, separate browser verification,
unchanged accounting, and complete temporary-access cleanup. Earlier harness
failures remain preserved with their original verdicts.
The local demo also runs this source. Its
existing development login is retained, with per-user funded quota accounting
enabled through its private configuration.

Current details are in the [implementation record](operations/demo-revision-implementation-20260909.md),
[evaluation record](operations/evaluation-baseline-20260909.md),
[exploration record](operations/exploration-revision-20260909.md),
[final UI acceptance](operations/ui-requirements-acceptance-20260910.md),
[local subscribed-client acceptance](operations/mcp-client-acceptance-20260909.md),
and [phased rollout plan](operations/revision-rollout-20260909.md).

## Original September 9 investigation

Most of the concrete UI revisions are implemented. The strongest remaining
opportunities are deliberate context selection in chat and better navigation
between natural-language claims, formal rules, and individual argument
derivations.

The September 9 supplement below investigates Haoyang's six additional
requests against `Requirements.docx`, the implementation, current public
provider information, and read-only Azure configuration. It adds quota,
routing, model-selection, evaluation, and MCP work to the UI recommendations.
All additions are proposed work. This review changes only this document.

This review was completed on September 9, 2026 against `development` commit
`85bd4ae75d09a55fb65d1cd254d2ab1d833e8e18`. Its source is Haoyang's
[Revision_Ideas_COMMA_2026 Google Doc](https://docs.google.com/document/d/1HCpgeP2e-SsCQw4VqSjHgINHQBaxOG28z61u9JHmbkU/edit).
The findings concern this checkout and the hosted demo observed during the
review. The stable paper branch, `main`, is separate, as explained in the
[repository README](../README.md).

The tables preserve the gdoc's original indices and order. Its Demo section
contains two items numbered **3**, so their author labels distinguish them.
Recommendations below are proposed work, not claims of completed implementation.

The implementation findings are:

| Gdoc index | Original idea | Status and evidence |
| --- | --- | --- |
| **Demo 1 [Agent A]** | Make “Chat” visible in the panel heading. | **Implemented.** The heading is “Chat & Exploration.” See the [chat panel](../app/static/index.html#L118). |
| **Demo 3 [Agent C]** | Improve conversation management with tabs, editing and forking, automatic saving, export, and context insertion through the item button. | **Not implemented.** Chat uses one in-memory message list. It has no independent New conversation control, conversation tabs, editing and forking, durable transcript storage, or transcript export. Clicking `?` immediately submits a question and clears the composer. Project saving and scenario export do not save the conversation. See [chat handling](../app/static/app.js#L1315), [submission behavior](../app/static/app.js#L1462), and [export scope](scenarios.md#L171). |
| **Demo 2 [Agent A]** | Show that the scenario has changed from baseline, with a change count and Reset. | **Implemented.** The toolbar shows “Modified from baseline: N changes,” with Reset available. Private projects use an “Unsaved” indicator. The count is the number of pending operations. See [renderModifiedIndicator](../app/static/app.js#L749). |
| **Demo 3 [Agent A]** | Highlight conclusions when recomputation changes their labels. | **Implemented.** Changed conclusion cards receive a 750 ms pulse. This was observed after activating the equity assumption. See [label comparison](../app/static/app.js#L636) and [animation](../app/static/style.css#L247). |
| **Demo 4 [Agent A]** | Finish the minimap or remove the flag that could enable it accidentally. | **Addressed through removal.** `MINIMAP_ENABLED` is gone, and the rendered interface does not include the minimap. The unused `renderMinimap` function and related code/styles remain, so cleanup is incomplete. See [renderGame](../app/static/app.js#L3241) and [remaining minimap code](../app/static/app.js#L3277). |
| **Demo 5 [Agent A]** | Increase the 15-character edit identifier limit. | **Implemented.** `MAX_ID_LEN` is 24 for newly generated LLM edit identifiers. The manual scenario editor separately accepts identifiers up to 100 characters, and modifying a rule with an existing longer identifier is supported. See the [LLM validator](../app/llm/edit_validator.py#L26), [validator tests](../tests/test_edit_validator.py#L82), and [symbol guide](scenarios.md#L35). |
| **Demo 6 [Agent C]** | Support major official providers and OpenRouter, with GUI selection. | **Substantially implemented.** Workspace > AI access supports Anthropic, OpenAI, Google Gemini, and OpenRouter through BYOK. Selection uses a curated model catalog. At review time, funded access exposed only the approved Balanced profile; Economy and Quality were not public. This is not unrestricted access to every model. See [model selection](../app/static/workspace.js#L445), the [catalog](../app/llm/models.yaml#L135), and [public configuration](https://demo.abda-nl.org/config). |
| **Demo 7 [Agent C]** | Replace the misleading “Supporting arguments” phrase. | **Implemented.** The expandable section says “Premises and subarguments,” and attacks receive separate descriptions. See [support rendering](../app/static/app.js#L3489) and [attack descriptions](../app/static/app.js#L3545). |
| **Demo 8 [Agent C]** | Explain accepted arguments, including those without attackers. | **Implemented.** Accepted conclusions have enabled Explain buttons when a derivation exists. Their explanation exposes premises and subarguments and explicitly states when no challenges remain. See [candidate selection](../app/static/app.js#L2377), [derivation display](../app/static/app.js#L3476), and [no-challenge explanation](../app/static/app.js#L3731). |
| **More radical ideas 1 [Agent D]** | Allow fluent paraphrasing while providing verbatim text as evidence. | **Partially implemented.** The prompt already permits unquoted paraphrases with source citations and requests concise prose. It does not require an inspectable exact excerpt alongside each relevant answer, and the validator does not verify quotation accuracy. See the [chat prompt](../app/prompts/chat_system.md#L15) and [response validator](../app/llm/chat_service.py#L348). |
| **More radical ideas 2 [Agent D]** | Make the connection between natural language and ASPIC- more explicit. | **Substantially improved, but incomplete.** Show ASPIC-, a glossary, proposals displaying natural language alongside formal syntax, Guided/Rule text editing, and consistent symbol renaming are implemented. Direct navigation and highlighting between a selected claim, its formal rules, and its arguments remain missing. See the [scenario guide](scenarios.md), [proposal preview](../app/static/app.js#L2696), and [ASPIC- view](../app/static/app.js#L2982). |
| **More radical ideas 3 [Agent D]** | Expose a fuller structured argumentation graph and integrate it with natural language and ASPIC-. | **Partially implemented.** Explain exposes some internal structure, but the overview groups distinct arguments by conclusion and merges or filters attack edges. Explain also groups some derivation variants. A view of individual derivations with linked premises, rules, and attacks is still missing. The backend retains individual argument data. See [graph grouping](../app/static/app.js#L1852), [variant grouping](../app/static/app.js#L2330), and [serialized argument structure](../app/scenario/serialize.py#L133). |

The following improvements are recommended, in priority order. Scope estimates
are relative judgments about implementation effort, not calendar commitments.

- **Demo 3 [Agent C], the paragraph beginning “When we click the ‘?’ button…”:
  implement context insertion first.** This is the best small usability
  improvement. Replace immediate submission with an explicit “Add to question”
  action. Preserve the existing draft, allow several selected elements, show
  removable context items, and submit only when the user chooses Ask. Keep the
  selected element's identity so the request refers to the intended rule or
  claim even when descriptions are similar. A useful first version should
  support composing a question about two rules without sending either one
  prematurely or losing typed text. The existing composer and delegated item
  handler make this a contained frontend change; representing context
  references explicitly in the API would add some backend work.

- **More radical ideas 2 [Agent D] and 3 [Agent D]: build a linked derivation
  inspector together.** This has the strongest research value. Keep the compact
  conclusion overview and add “Inspect derivation” for a selected argument.
  Display its concrete premises, applied rules, subarguments, label, and attacks.
  Let the user move between each element's natural-language description and
  exact ASPIC- representation. Preserve distinct derivations even when they
  share a conclusion or top rule. Label the compact graph clearly as a
  conclusion overview, and distinguish support links from attack links.

  This is a moderate extension because the API already supplies `premises`,
  `sub_arguments`, `top_rule`, `rules_used`, labels, and attack endpoints. The
  initial version can focus on one selected derivation and its local attack
  neighborhood, which bounds the display size without changing the reasoner.
  The live Popov baseline provided a concrete motivation: 77 underlying
  arguments appeared as 34 nodes under “All conclusions.” That compression is
  useful for orientation but cannot expose every argument's structure. Existing
  grouping also means that changing only the graph title would not complete
  these ideas.

- **Demo 3 [Agent C], the paragraph beginning “Inspired by Cursor…”:
  add basic conversation lifecycle before full branching.** New conversation,
  saved history, and transcript export would deliver most of the immediate
  benefit. Durable history is a moderate addition because it needs storage and
  user controls as well as a chat interface. Associate each saved turn with the
  scenario state or version it describes, including any unsaved scenario edits,
  so an answer can be interpreted after the knowledge base changes. Project
  version alone is insufficient when a question uses pending edits. Exports
  should preserve the question, answer, and relevant scenario context without
  provider credentials.

  Multiple conversation tabs and editing a previous turn to fork a conversation
  are feasible follow-ups. They have lower immediate priority because they add
  navigation and branching semantics. A fork should identify whether it uses
  the historical scenario state or the current one. Conversation branching and
  scenario branching should be explicit user choices.

- **More radical ideas 1 [Agent D]: pair fluent answers with inspectable,
  validated evidence.** Provide concise prose with expandable source excerpts.
  For background claims, bind excerpts to actual source spans and validate
  quotation text against the material supplied to the model. For formal
  explanations, link to the engine's rules, arguments, and computed labels.
  Simplified wording should preserve formal distinctions such as explicit
  negation and the meaning of “undecided.”

  This is feasible but needs more than a prompt change. During the review, a
  deliberately invented quotation paired with a recognized source filename
  produced no validation flags. The current validator checks source names and
  identifier patterns, not quotation text. Exact matching would establish that
  the quotation exists; it would not by itself establish that a paraphrase is
  faithful or that the quoted passage supports the claim. Include examples
  involving negation and unsupported paraphrases in validation before treating
  this as complete. ABDA should continue to determine formal labels.

**Demo 4 [Agent A]** needs only low-priority removal of unused code unless
larger derivation views reveal a real navigation need for a minimap. Existing
Zoom and Fit controls already support graph navigation. **Demo 6 [Agent C]**
also needs the funded/BYOK catalog and provider-routing work described in
supplement items 2 through 4. Haoyang's additional requirements make this a
functional gap to resolve alongside the interaction improvements.

Relevant documentation already describes several foundations for these changes:
the [scenario guide](scenarios.md), [unified editor release record](operations/unified-scenario-editor-20260908.md),
[symbol-renaming release record](operations/symbol-renaming-20260909.md), and
[COMMA demonstration playbook](operations/comma-2026-demo-playbook.md).
The scenario guide also makes clear that reference documents provide context
and citations; importing a document does not automatically turn it into logical
facts or rules.

For completeness, the paper-only checks below refer to the local
`camera-ready.pdf` supplied in this checkout. That file is not a tracked
publication artifact, so these observations do not establish the state of an
external submission or published version.

| Gdoc index | Finding in the local camera-ready PDF |
| --- | --- |
| **Paper 1** | The reported grammar error is absent. |
| **Paper 2** | The Walton and Krabbe reference still lacks publisher and location. |
| **Paper 3** | Multiple scenarios are mentioned, but only Popov is named. The current repo has six bundled scenarios across several domains. |
| **Paper 4** | Local-model portability is not discussed. Ollama support and local-model launch targets remain in the code, but this review did not reproduce the older model-evaluation claim. |
| **Paper 5** | Explicitly addressed: the LLM translates, while ABDA performs the argumentation reasoning. |
| **Paper 6** | Partially addressed: scenario components and storage are explained, but preparation from raw material remains underspecified. The newer scenario guide documents authoring and import. |

If a later paper revision is possible, completing **Paper 2** and clarifying
**Paper 3** and **Paper 6** are small, useful edits. Any added evaluation claim
under **Paper 4** should be supported by the corresponding experiment records.

The September 9 review used source inspection, relevant documents, focused
tests, and anonymous browser checks. The following test selection completed
with **128 passed**:

```bash
.venv/bin/python -m pytest -q \
  tests/test_chat_validator.py \
  tests/test_edit_validator.py \
  tests/test_edit_retry.py \
  tests/test_frontend_contract.py \
  tests/test_serialize.py \
  tests/test_scenario_editor.py \
  tests/test_scenario_symbol_rename.py
```

At review time, public downloads of `index.html`, `app.js`, `style.css`,
`workspace.js`, and `scenarios.js` matched the checkout bytes. Anonymous
Chromium checks confirmed the chat heading, an enabled explanation for an
unattacked accepted conclusion, its premises section and no-challenges message,
the modified-state indicator, a changed-label card after the equity toggle,
Reset, the graph node count, and the ASPIC- glossary view. Those checks reported
no browser page errors or unexpected requests. They used deterministic
computation and made no model calls.

Provider support in this review means implemented routes, catalog entries, and
GUI selection. It is not a fresh quality evaluation of every live model. The
source and live observations above are tied to the recorded review date and
commit and should be refreshed when the implementation changes.

## Supplement: Haoyang's September 9 requirements and manual feedback

All six requests are appropriate to include. The recommendations below preserve
their numbering. They distinguish working foundations from missing behavior;
they do not treat catalog entries, mocked tests, or earlier acceptance records
as proof that a new model is ready for public use.

This supplement uses the same `development` commit recorded above. A fresh
anonymous read of the [hosted configuration](https://demo.abda-nl.org/config)
confirmed one funded choice, Balanced, versus four BYOK provider menus. A
read-only Azure inspection confirmed 100 public trial slots, a $5 grant per
account, a $500 trial allocation limit, enabled OpenRouter fallback, and a
separate $500 OpenRouter emergency limit. No account balances, credentials,
cloud resources, or application settings were changed. Individual users'
current balances and registration status were not queried.

### 1. Allocate $50 to each of the five named administrators

**Finding.** Trial activation gives every eligible account the same configured
grant. Existing grants are returned unchanged, so changing the global amount
would neither selectively upgrade administrators nor update their existing
balances. The scenario administrator allowlist controls example publication;
it does not control funded credit. See [trial activation](../app/services/trials.py#L62),
[grant configuration](../app/core/config.py#L206), and
[administrator recognition](../app/services/scenario_submissions.py#L32).

The live allowlist contains the first three institutional addresses below.
Martin and Timothy's addresses come from Haoyang's new request and are absent
from that allowlist.

| Administrator | Institutional identity | Proposed total grant |
| --- | --- | --- |
| Haoyang | `hl57@illinois.edu` | $50 |
| Bertram | `ludaesch@illinois.edu` | $50 |
| Shawn | `bowers@gonzaga.edu` | $50 |
| Martin Caminada | `CaminadaM@cardiff.ac.uk` | $50 |
| Timothy McPhillips | `tmcphill@illinois.edu` | $50 |

**Recommendation.** Interpret $50 as each account's total allocation, with
previous usage still deducted. For example, an existing $5 grant becomes $50
by adding $45, rather than adding another $50 or erasing spending. Match the
verified institutional email using the existing normalization rules, then bind
the entitlement to the internal account identity. Support both existing users
and a named administrator's first verified registration. Repeated login,
activation, or execution of the allocation procedure must not duplicate credit.

Keep credit eligibility separate from content-publication permissions. Adding
Martin and Timothy as scenario curators is a distinct role change, not a
necessary consequence of giving them credit. Do not grant privileges to an
entire institutional email domain.

I recommend a separate $250 administrator allocation so these five accounts
do not consume the first 100 public $5 grants. This makes the proposed maximum
user-credit allocation $750, consisting of $500 public credit and $250 team
credit. Reconcile any existing administrator trial allocation during migration
without duplicating its credit or losing its usage history. This budget
separation is a proposal, not a live limit increase. The independent $500
OpenRouter emergency ceiling remains a separate control; administrator credit
does not expand personal OpenRouter exposure.

**Acceptance.** Verify all five exact identities, ordinary users retaining $5,
late administrator registration, repeat execution and concurrent activation,
preservation of spent/reserved amounts, and correct browser/MCP balances. A
suspended or unverified account must not become eligible through this policy.

### 2. Use CloudBank first, the same model on OpenRouter after failure, and usable non-LLM behavior

**Finding.** Authenticated funded requests already reserve and settle the
requesting user's credit. BYOK uses a separate path. OpenRouter fallback
requires an outage-classified provider failure or an already-open circuit,
and its spend is recorded against both the user's credit and the emergency
ledger. Local credit exhaustion is not a provider outage. These foundations
are present in [request selection](../app/api/llm_access.py#L122),
[routing](../app/llm/routing.py#L543), and
[combined accounting](../app/services/llm_billing.py#L40).

There are several gaps against the requested behavior:

- Funded routing implements Azure Foundry and OpenRouter. The Google adapter
  is the direct Gemini API BYOK path, not GCP Vertex AI funded access. Managed
  startup also requires the default funded route to be Azure Foundry. Adding
  GCP therefore requires an adapter, CloudBank project authentication, billing
  attribution, deployment configuration, and startup validation changes.
- Balanced currently maps Sonnet 4.6 to Gemini 3.7 Flash on fallback. The
  unpublished Economy and Quality profiles also change models. The catalog
  validates route references but does not require model identity to match.
- The retry default is three total attempts per provider, and the circuit
  cooldown default is 60 seconds. The live app did not override these two
  settings. A later request can go directly to OpenRouter during that cooldown.
  Missing credentials or an invalid deployment can also fail before the
  failover wrapper runs; HTTP 401/403/404 do not currently qualify as outages.
- Exhausting both providers produces a sanitized error. Deterministic
  reasoning and manual editing are independent of the LLM, but the browser
  does not automatically enter a clearly explained degraded state. Chat
  currently clears the draft and appends a generic error message.

See the [current profiles](../app/llm/models.yaml#L135),
[route construction](../app/llm/routing.py#L678),
[managed startup](../app/api/main.py#L99), and
[chat failure handling](../app/static/app.js#L1511).

**Recommendation.** For an eligible registered user with available credit,
resolve the selected canonical model to a verified CloudBank deployment on
Azure **or** GCP. Require an OpenRouter route for that same model and version
before publishing the choice. Provider names, deployment aliases, token usage,
and response formats may differ; model identity, feature behavior, and the
selected question must remain stable. Do not silently substitute another
family or spend a user's BYOK credit as the funded fallback.

Use one CloudBank retry for a transient failure, two total attempts, with
bounded backoff, jitter, and a bounded `Retry-After` delay. Set a total request
deadline so retries and prompt-correction attempts cannot multiply into an
unacceptably long wait. Make at most one initial OpenRouter attempt before
offering non-LLM use. Keep recovery state scoped to the failing deployment.

| Condition | Recommended behavior |
| --- | --- |
| CloudBank succeeds | Return its result; make zero OpenRouter calls. |
| Timeout, connection failure, provider 429, or retryable 5xx | One bounded CloudBank retry, then the selected model's OpenRouter route. |
| A previously validated deployment loses credentials/access or returns deployment-not-found | Do not retry a permanent error blindly. Report the operator fault and allow only its already-qualified, budgeted same-model backup. An unconfigured candidate must never be admitted by relying on this path. |
| A recent failure has opened the circuit | A short cooldown may bypass the failed deployment, followed by a controlled recovery probe. Record the prior failure as the reason for fallback. |
| Missing login, exhausted user credit, invalid request, safety refusal, failed semantic validation, or unavailable accounting | Preserve the appropriate error; do not reinterpret it as permission to spend on OpenRouter. |
| Both providers fail, or emergency capacity is exhausted | Preserve the scenario and draft; explain that AI is temporarily unavailable and keep deterministic/manual features usable. |

The cooldown is a proposed refinement to a literal failure on every request:
it avoids repeatedly waiting for a deployment already known to be unavailable.
It must never become permanent OpenRouter-first routing. Preserve accounting
for every physical attempt, including a timeout that may have incurred a
provider charge; release only reservations known to be unused. Show useful
model/provider and cost information without exposing credentials.

For non-LLM use, retain scenario loading, assumption toggles, computation,
formal explanations, the graph, manual Guided/Rule text editing, project
saving, and export. Do not manufacture a natural-language answer and label it
as an LLM response. A recovery action should restore AI without resetting the
project. Add injected-failure browser tests that verify these operations after
both providers fail, plus routing and ledger tests for every row above.

### 3. Publish one qualified model pool for funded access and BYOK

**Finding.** The public catalog mismatch is real. Funded selection filters
profiles by `public_ready`; BYOK enumerates model families and a separately
maintained OpenRouter map. MCP separately hard-codes Balanced. The common
pool must therefore drive all selectors and server-side validation, not just
the visible dropdown. See [selector construction](../app/api/llm_access.py#L159),
[OpenRouter aliases](../app/llm/routing.py#L55), and
[MCP profile types](../app/mcp/server.py#L572).

Eligibility should mean `(CloudBank Azure OR CloudBank GCP) AND OpenRouter`,
with no AWS-funded route. It does not require every model to exist on both
Azure and GCP. Require access in the actual funded account, a compatible
same-version backup, reliable tool calling, and ABDA-specific prompt and
feature acceptance. An Azure catalog listing or a direct Google AI Studio key alone
does not establish CloudBank billing eligibility.

**Selection method, incorporating Haoyang's clarification.** Trust published
[LiveBench results](https://livebench.ai/) and
[Artificial Analysis results](https://artificialanalysis.ai/leaderboards/models)
for general model quality and comparative performance. Use their published
cost-per-task measurements, Artificial Analysis provider latency/throughput,
and current provider tariffs to select the Pareto frontier within each family.
Preserve family choice. Do not spend the $100 budget recreating general
intelligence benchmarks or conducting our own comparative ranking study.

Treat direct successors in the same model line as the preferred upgrades:
Gemini 3.8 Flash replaces 3.7/3.6 Flash, Sonnet 5 replaces Sonnet 4.6, and
GPT-5.6 Sol replaces GPT-5.5. No new head-to-head experiment is needed to
justify these choices. The remaining release checks establish that the chosen
model is accessible through the funded account and works with ABDA's prompts,
tools, and accounting. Different tiers such as Flash-Lite versus Flash or
Haiku versus Sonnet can remain because they serve different cost preferences.

Record each benchmark's release, retrieval date, model version, reasoning
effort, and measured provider. Do not mix a maximum-effort quality score with
low-effort cost or latency, or combine numbers from different benchmark
versions as though they used one scale. Artificial Analysis currently uses
[Intelligence Index v4.3](https://artificialanalysis.ai/methodology/intelligence-benchmarking);
LiveBench's displayed release is `2026-06-25`. The September 9 snapshot below
records public scores, with each site's setting kept explicit. A missing
entry is not a zero score.

| Model | LiveBench setting and overall score | Artificial Analysis setting and Intelligence Index |
| --- | --- | --- |
| GPT-5.6 Luna | Max, 73.6 | Max, 38 |
| GPT-5.6 Terra | Max, 77.9 | Max, 42 |
| GPT-5.6 Sol | Max, 81.0 | Max, 47 |
| Claude Sonnet 5 | xHigh, 76.0 | Max, 38; xHigh index not reported |
| Claude Opus 5 | Max, 80.1 | Max, 51 |
| Claude Haiku 4.5 | Not in the displayed current table | Reasoning, 18 |
| Gemini 3.5 Flash-Lite | High, 63.9 | Default listed reasoning configuration, 23 |
| Gemini 3.8 Flash | High, 75.8 | High, 41 |
| DeepSeek V4 Flash 0731 | Listed configuration, 74.2 | Max, 35 |

Sources: the rendered [LiveBench leaderboard](https://livebench.ai/) and
[Artificial Analysis leaderboard](https://artificialanalysis.ai/leaderboards/models),
read on September 9. The scores are separate scales, not values to average.
Their published task costs and API speed measurements describe their own
workloads and providers, not a promised ABDA bill or response time.

The sites can disagree: LiveBench currently ranks Flash 3.7 High above 3.8
High, 78.8 versus 75.8, while Artificial Analysis ranks 3.8 High above 3.7
High, 41 versus 39. Keep Haoyang's requested successor preference rather than
commissioning a new benchmark study to settle this. The replacement decision
does not require claiming that every published metric improved.

The following is a **qualification shortlist**, not an assertion that these
models are deployed. General capability is assessed from the public sources
above; qualification here means funded access and application compatibility.
Prices are USD
per million uncached input/output text tokens, standard interactive service,
before applicable regional premiums and OpenRouter credit-purchase overhead.

| Family and candidate | Public price reference, input / output | Candidate funded route and matching OpenRouter ID | Recommendation |
| --- | --- | --- | --- |
| GPT-5.6 Luna | $0.20 / $1.20 | Azure; `openai/gpt-5.6-luna` | Inexpensive OpenAI choice, replacing GPT-5.4 mini once ABDA integration passes. |
| GPT-5.6 Terra | $2 / $12 | Azure; `openai/gpt-5.6-terra` | Middle tier selected using public benchmark, cost, and latency data. |
| GPT-5.6 Sol | $4 / $20 currently on OpenAI and Azure; OpenRouter advertises a separate $2 / $10 promotion | Azure; `openai/gpt-5.6-sol` | Upper OpenAI tier; replace GPT-5.5 after qualification. |
| Claude Haiku 4.5 | $1 / $5 | Azure; `anthropic/claude-haiku-4.5` | Candidate inexpensive Claude choice; test its smaller context limit and tool reliability. |
| Claude Sonnet 5 | $2 / $10 | Azure; `anthropic/claude-sonnet-5` | Replace Sonnet 4.6 once funded access and ABDA integration pass. |
| Claude Opus 5 | $5 / $25 | Azure; `anthropic/claude-opus-5` | Upper Claude tier, with bounded reasoning/output and ABDA integration checks. |
| Gemini 3.5 Flash-Lite | $0.30 / $2.50 | GCP Vertex AI; `google/gemini-3.5-flash-lite` | Lower-cost Gemini tier supported by public benchmark and price data. |
| Gemini 3.8 Flash | $0.75 / $3.75 through December 31, 2026 | GCP Vertex AI; `google/gemini-3.8-flash` | Replace 3.7 and 3.6 Flash once funded access and ABDA integration pass. |
| DeepSeek V4 Flash 0731 | OpenRouter advertises from $0.05 / $0.16; Azure rate needs route-specific confirmation | Azure `DeepSeek-V4-Flash-0731`; `deepseek/deepseek-v4-flash-0731` | Investigate the newer matching revision instead of promoting the catalog's older undated route. Azure still labels its offering Preview. |

OpenAI/Azure evidence: [Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna),
[Terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra),
[Sol](https://developers.openai.com/api/docs/models/gpt-5.6-sol), and
[Azure's model availability and dated pricing promotion](https://azure.microsoft.com/en-us/blog/gpt-5-6-now-available-in-microsoft-foundry/).
The Azure promotion runs through at least November 30, 2026. The different
[OpenRouter Sol promotion](https://openrouter.ai/openai/gpt-5.6-sol) can make
Sol temporarily cheaper than Terra on backup traffic; it does not establish
Terra's dominance status for funded Azure traffic.

Claude evidence: [current pricing](https://platform.claude.com/docs/en/about-claude/pricing),
[cost/quality selection guidance](https://platform.claude.com/docs/en/about-claude/models/optimizing-for-cost-and-intelligence),
and [Foundry availability](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/claude-models).
Google evidence: [GCP standard pricing](https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing),
[Flash-Lite model card](https://deepmind.google/models/model-cards/gemini-3-5-flash-lite/),
and [OpenRouter Flash 3.8](https://openrouter.ai/google/gemini-3.8-flash).
DeepSeek evidence: [Azure's exact revision](https://ai.azure.com/catalog/models/DeepSeek-V4-Flash-0731)
and [OpenRouter's matching revision and provider prices](https://openrouter.ai/deepseek/deepseek-v4-flash-0731).

Google's [3.8 model card](https://deepmind.google/models/model-cards/gemini-3-8-flash/)
provides supplementary capability information. Independent public benchmarks
remain the comparison sources specified above. Gemini's announced rates become
$1.50 / $7.50 on January 1, 2027, so a promotion-dependent choice needs a
scheduled price review. See the
[pricing announcement](https://ai.google.dev/gemini-api/docs/latest-model#pricing).

Other families and tiers were considered rather than silently omitted:

- **DeepSeek V4 Pro / Pro 0813:** public Azure documentation lists V4 Pro,
  while OpenRouter distinguishes the older undated alias from
  [Pro 0813](https://openrouter.ai/deepseek/deepseek-v4-pro-0813). Retain a Pro
  option when public benchmark/cost data justify that tier and a matching
  funded revision is identified. The existing V4 Pro entry is not proof of that
  mapping. See [Azure's DeepSeek catalog](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure#deepseek).
- **Gemini 3.1 Pro Preview:** GCP and OpenRouter list it at $2 / $12 for
  short-context requests. Include it only if public benchmark/cost data justify
  a distinct tier alongside 3.8 Flash; an older Pro name alone does not justify another public
  option. [GCP pricing](https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing)
  and [OpenRouter catalog metadata](https://openrouter.ai/api/v1/models)
  establish listing and pricing, not that benefit.
- **MiniMax M3 and Kimi K3:** both have Foundry listings and OpenRouter entries;
  the latter currently advertise $0.30 / $1.20 and $3 / $15 respectively.
  Foundry supplies them through Fireworks infrastructure. Hold them outside
  the initial pool until this specific CloudBank subscription can fund that
  offering and its data handling fits the existing application contract.
  A Foundry listing must not be treated as an ordinary Azure-hosted deployment.
  See [MiniMax on Foundry](https://ai.azure.com/catalog/models/FW-MiniMax-M3),
  [Kimi on Foundry](https://ai.azure.com/catalog/models/FW-Kimi-K3), and
  [OpenRouter metadata](https://openrouter.ai/api/v1/models).
- **Qwen 3.8:** OpenRouter lists Flash at $0.15 / $0.47. The verified Foundry
  listing is instead [Qwen3.8-27B](https://ai.azure.com/catalog/models/qwen--qwen3.8-27b),
  a distinct model with deployment/serving requirements. This does not verify
  a funded Qwen3.8 Flash API. Hold Qwen outside the initial pool until an exact
  funded API match is established; do not substitute 27B for Flash or equate
  a weights listing with economical managed inference.

Exclude GPT-6 Astra, Claude Fable 5.1, and other tiers above Haoyang's specified
GPT-5.6 Sol / Claude Opus 5 ceiling from both funded and BYOK admission. Enforce
an explicit model allowlist and route price/output bounds, including rejection
of unsupported IDs sent directly to the API. Do not let an OpenRouter model
fallback or a premium processing tier silently bypass the intended ceiling.

**Actual access remains a separate prerequisite.** The September 9 read-only
inventory of the Foundry account used by this app returned the same 15
successful deployments documented in the [September 6 inventory](operations/model-promotion.md#verified-deployment-inventory-on-2026-09-06).
It includes Sonnet 4.6 and Haiku 4.5, but not Sonnet 5, Opus 5, any GPT-5.6
variant, or either shortlisted DeepSeek V4 revision. GCP project entitlement
and callable Gemini routes were not verified in this review. A catalog change
alone cannot finish this request. Confirm account eligibility and exact route
names before provisioning or evaluating candidates in the implementation stage.

Create one canonical qualified set and derive the funded menu, BYOK menus,
OpenRouter mapping, request validation, and MCP schema from it. A direct
Anthropic key naturally shows only the Claude subset, a direct Google key the
Gemini subset, and OpenRouter the complete eligible set. Funded access and the
union of BYOK choices should agree. Keep the working baseline available during
qualification, then retire superseded public choices together when their
replacements pass; preserve historical model IDs in saved usage records.

Require an eligible backup under the existing `zdr`, `data_collection`, tool,
and price filters. Public model-level support does not prove that one endpoint
meets all filters. Prefer a backup upstream outside the failed CloudBank
provider's outage domain, and keep AWS/Bedrock out of the proposed routes.
See [OpenRouter provider selection](https://openrouter.ai/docs/guides/routing/provider-selection)
and the [current request filters](../app/llm/routing.py#L230).

### 4. Verify ABDA prompt and feature behavior within $100 of CloudBank spend

Per Haoyang's clarification, this testing budget is for application correctness,
prompt tuning, provider compatibility, and failure handling. It is not for
re-running LiveBench or Artificial Analysis, ranking general model intelligence,
or proving that a direct successor improves on its predecessor. Continue the
original request to **carefully test every selected LLM on every LLM-backed
ABDA feature, and tune prompts when and only when testing shows a need**.
Prompts that already work well should remain unchanged. Public benchmark
strength, a successful smoke call, or another model passing the same prompt
cannot substitute for this testing coverage.

**Finding.** The three feature prompts are shared across models:
[chat](../app/prompts/chat_system.md), [proposer](../app/prompts/proposer_system.md),
and [reviewer](../app/prompts/reviewer_system.md). The version-4
[evaluation suite](../evals/llm_suite.yaml) contains 16 cases, comprising eight
chat, five proposal, and three review cases. Three repetitions produce 48
case runs, not necessarily 48 physical provider calls. It covers five of the
six bundled scenarios and predates the latest scenario-editing features.
The earlier 48/48 results for two routes in the [promotion record](operations/model-promotion.md)
do not establish correct ABDA integration for the proposed pool.

The existing evaluator's `paid_run_cap_microusd` is applied only when the route
is `openrouter-emergency`. CloudBank routes receive no spend-cap object.
Setting that option to $100 would therefore **not enforce Haoyang's CloudBank
budget**. See [evaluation dispatch](../app/evals/llm_eval.py#L426).

**Recommendation.** Before paid testing, add one persistent evaluation-budget
ledger shared across Azure and GCP, models, processes, retries, tuning rounds,
and resumed runs. Reject a call before dispatch if spent plus outstanding
conservative reservations plus its maximum cost would exceed $100
(100,000,000 microUSD). Include reasoning, cache writes, unsuccessful billable
attempts, reviewer calls, and uncertainty after a timeout. Reconcile provider
usage and applicable route prices; use conservative bounds when exact billing
is unavailable. Do not charge this evaluation to the five administrator grants
or public trial credit.

Use isolated CloudBank routes with automatic fallback disabled. The test
process must not receive Haoyang's OpenRouter key, and an outbound guard should
reject model-generation calls to OpenRouter. Public catalog reads and mocked
transport tests can validate backup wiring without spending there. New live
OpenRouter behavior must remain explicitly unverified under this constraint;
CloudBank success cannot prove another provider's live conformance.

A proposed allocation is $5 for availability/smoke checks, $35 for complete
ABDA feature checks, $30 for targeted prompt tuning, $20 for final regression tests,
and $10 for accounting uncertainty or failed attempts. The total is a ceiling,
not a spending target. Stop and report incomplete models if the budget cannot
cover the remaining work; do not loosen application acceptance or switch billing
sources to finish.

| Feature or behavior | Required evaluation coverage |
| --- | --- |
| Grounded chat and item questions | Accepted, rejected, and undecided labels; unattacked acceptance; multiple derivations; actual rule/premise/attack references; questions composed from multiple selected items. |
| Corpus-grounded explanation | Exact quotations, correct citations, unsupported paraphrases, source contradictions, and missing context. A recognized filename alone must not pass an invented quote. |
| Sensitivity exploration | Changed assumptions, suspended rules, preferences, explicit negation, and conflicting conclusions. Check proposed counterfactual outcomes against the deterministic engine. |
| All four proposal tasks | Add rule, modify rule, add fact, add assumption; correct target and polarity; strict versus defeasible; preservation of unrelated fields; forward references; ID collisions and existing long IDs. |
| Semantic reviewer | Detect changed intent or reversed meaning, accept correct edits, and avoid irrelevant warnings. Explicit user choices must not be rewritten as reviewer preferences. |
| Current authoring workflow | Custom scenarios, imported/reference material, renamed symbols, description changes, pending edits, conversation history after a state change, and all six bundled scenarios. |
| Provider contract and failure behavior | Forced tool selection, JSON/schema validity, missing/empty output, truncation, reasoning budgets, cache and usage normalization, timeout, retry, and route recovery. |

Maintain an explicit model-by-feature coverage matrix, recording the model
version, prompt version, provider adapter, and decoding settings in every
cell. Exercise each cell with routine, ambiguous, adversarial, and edge-case
inputs relevant to that feature. Review the actual model answers and proposed
operations for grounding, semantic fidelity, usefulness, and presentation,
alongside deterministic schema and engine checks. Repeated trials should
establish that observed behavior is reliable, rather than selecting one good
answer. Every selected model must cover chat, corpus questions, sensitivity
questions, all four proposal tasks, refinement, and semantic review in the
supported scenario contexts. MCP's calls to the same chat/proposal services
also need model coverage, with client/protocol acceptance under item 5.

For each model, first record how the existing prompts behave, identify failure
patterns, tune the prompts and supported decoding settings when and only when
needed to address an identified problem, and rerun its complete affected
feature set. A change to a shared prompt requires
regression checks across every selected model that uses it. A model-specific
override requires full coverage of that model's affected features. Keep
passing prompts unchanged when no tuning is needed, with evidence showing
that they passed. Record untuned and tuned outcomes, unresolved failures, and
the final accepted prompt/configuration for every model. A successor's general
quality advantage does not waive these prompt and integration checks.

Begin with a common semantic prompt and add small, versioned model or family
overrides only where repeated failures justify them. Keep adapter/API
compatibility settings separate from semantic instructions. For example,
Claude's Sonnet 5 migration changes thinking and assistant-prefill behavior;
one old Claude request configuration is not automatically valid for every
Claude model. Choose Google's 3.8 thinking level using public performance data,
then verify that the setting works within the application's response limits.
See [Sonnet 5 migration](https://platform.claude.com/docs/en/models/sonnet-5/migration-guide)
and [Gemini 3.8 usage guidance](https://ai.google.dev/gemini-api/docs/latest-model).

Align the proposer's introductory description with the actual advisory reviewer
and explicit Apply workflow, rather than implying automatic application after
review. Preserve the shared semantic contract: ABDA determines formal labels,
the proposer translates the requested edit, the deterministic validator checks
structure, and the reviewer advises the user. Inspect model failures for prompt
ambiguity before creating separate full prompt copies for every model.

Define concrete feature pass criteria before tuning and keep regression cases
that were not used to tune the prompts. Repeat cases where needed to diagnose
unstable behavior, rather than running a model-ranking tournament. Inspect
grounding and semantic correctness, since keyword presence alone is too weak.
Produce a reproducible report with code, prompt, suite and catalog hashes;
model/deployment versions; decoding settings; per-feature outcomes; actual
physical call counts; cost including retries; and observed request duration for
budget and timeout diagnostics. These are operational receipts, not replacement
public benchmark scores. Admit a model only when every exposed feature passes
its application checks. No prompt changes or paid
model evaluations were performed for this document update.

### 5. Test complete MCP workflows through both subscribed clients

**Finding.** MCP has substantial implementation and test coverage. Its nine
tools separate read, project-write, and metered-LLM scopes, reuse ownership and
version checks, and keep proposals separate from application. Token expiry,
revocation, cross-user isolation, safe errors, and metering are tested. The
dated [live acceptance record](operations/staging-mcp-client-acceptance.md)
shows both real clients listing examples and losing access after revocation.
Its later write gate used direct protocol calls, and explicitly never called
`apply_project_ops`. That is narrower than demonstrating a full interactive
editing task in Codex and Claude Code. The current local MCP wire tests also
exercise an invalid edit, but do not demonstrate a successful full agent-led
apply-and-verify workflow.

Distinguish two useful user experiences:

- With `projects:read` and `projects:write`, the client's own subscribed model
  can inspect a scenario, explain it, construct operations, apply an authorized
  edit, and read the recomputed result. These tools do not invoke an ABDA-hosted
  LLM and should not spend ABDA credit.
- `ask_project` and `propose_project_edit` invoke the ABDA server's funded
  model and consume the account's ABDA quota, even when the caller has a Codex
  or Claude Code subscription. They require `llm:use`. A subscription is not
  authentication to ABDA or payment for its separate provider calls.

The first path directly serves the original subscription-based exploration
idea and deserves a clear onboarding example. Keep personal MCP credentials
revocable and distinct from provider keys. Current official
[Codex MCP documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)
and [Claude Code MCP documentation](https://code.claude.com/docs/en/mcp)
support remote HTTP configuration. Recheck generated instructions against the
actual client versions during acceptance.

**Recommendation.** Run the same bounded task in both real clients using a
disposable project with public/synthetic content: discover tools, read the
scenario and formal result, formulate one user-authorized edit, apply it at the
observed version, and verify the changed labels and browser-visible project.
Check an invalid operation, a stale version, attempted cross-user access,
read-only denial of writes, revocation, and a repeat request after revocation.
The successful workflow should also run without `llm:use` and with zero ABDA
credit, proving the subscription-funded path does not call the server's model.

Test the optional server-LLM path separately: both question and proposal tools,
exact quota deduction, proposal not applied implicitly, depleted credit,
provider failures, and cleanup. Any model calls in this acceptance belong
inside item 4's aggregate CloudBank-only $100 cap. Use injected OpenRouter
responses for failure-path tests under the no-OpenRouter-spend constraint.
Refresh MCP's currently hard-coded `Literal["balanced"]` schema from the
qualified pool when item 3 changes model selection. Include every selected
model in the shared chat/proposal prompt coverage; verify MCP-specific
instructions and tool behavior separately in this client acceptance.

Record exact client and server versions, tool outcomes, ledger deltas, and
revocation/cleanup receipts. Keep tokens and private payloads out of reports.
Historical client acceptance and current mocked tests should remain separately
identified from this future complete live workflow.

### 6. Make the question button populate the editable composer

**Finding.** The [delegated question-button handler](../app/static/app.js#L1532)
calls `sendChatMessage` with `Can you explain "${desc}"?`.
[Submission](../app/static/app.js#L1462) immediately clears the composer and
sends the request. This confirms Haoyang's observation and overlaps with
Demo 3 [Agent C] above.

**Recommendation.** First make the small, direct behavior change Haoyang
requested: clicking `?` puts that same question into the bottom-right input,
reveals the panel on narrow layouts, and focuses the editable input. Make no
LLM request until the user selects Ask or uses the existing explicit keyboard
submission action. Do not add a conversation turn or deduct credit on click.

Preserve an existing draft. If the input already contains text, insert the
new question with a separator at the cursor, preserving all existing text;
when empty, use the generated question as the complete draft. Preserve the
item's identity where descriptions are ambiguous. Removable context items and
multi-item composition remain a useful later extension, but should not delay
this direct correction. Update the tooltip and accessible name to describe
draft insertion rather than immediate explanation.

Acceptance should cover keyboard and mouse activation, edits before sending,
nonempty drafts, repeated item clicks, narrow layouts, access-denied states,
an in-flight request, and scenario changes. Assert zero chat/proposal requests
and zero credit changes before submission, then exactly one request containing
the user's edited question. Update the existing browser expectations that
currently assert an immediate answer after a `?` click.

## Suggested implementation order and evidence from this supplement

The question-button correction and selective administrator allocation are
contained early tasks. For the provider work, first establish exact funded
deployment access and the CloudBank evaluation cap, then implement same-model
routing and the shared catalog, test candidates and tune prompts only as needed,
and finally refresh the browser and real-client MCP acceptance. This sequence preserves a usable
baseline while replacements are being evaluated. It does not replace the
linked-derivation and conversation improvements recommended earlier.

This document-only investigation ran two focused local selections with test
databases and mocked provider responses:

| Selection | Result |
| --- | --- |
| `test_llm_routing_billing`, `test_llm_api_access`, `test_llm_eval`, `test_mcp`, the four MCP acceptance/recovery test modules, and `test_accounts_projects_trials` | 131 passed |
| `test_provider_clients`, `test_outage_drill`, `test_outage_drill_gate`, and `test_outage_drill_recovery_gate` | 46 passed |

These **177 passing tests** confirm existing tested behavior, including some
behavior this supplement proposes to change. They do not establish new-model
quality, a current end-to-end subscribed-client workflow, or an implemented
CloudBank evaluation cap. Public provider metadata, hosted `/config`, and
Azure settings/deployment inventory were inspected without model inference.
This review incurred no CloudBank or OpenRouter model charges and did not run
deployment, allocation, paid-evaluation, or live MCP write procedures.
