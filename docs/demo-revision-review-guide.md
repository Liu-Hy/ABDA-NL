# Independent review guide

Read the [requirements](demo-revision-contract.md) first. Together these two
documents contain the review brief; other documents below are optional evidence
for a claim being checked. Historical plans and implementation self-assessments
are not independent approval or current requirements.

## Review boundary and provenance

The recent revision work starts after `85bd4ae75d09a55fb65d1cd254d2ab1d833e8e18`.
Tim reviewed code snapshot `026fde9f0c5024c48a4d1c935b05d459d9e29349`.
The subsequent correction work starts from `94febed`; inspect the current
commit and the correction status below for its validation boundary.
The last verified hosted source is
`234ffc97522b5d82e0a4a4d05082d88a4ab0c173`, on schema 0006. The correction
candidate uses schema 0007 and has not been deployed. Hosted receipts below
describe the earlier release. Review existing foundations as well as this diff
wherever R01-R15 or E01-E07 depend on them.

`Requirements.docx` was read directly and has SHA-256
`fb934fec9ab180586774a80f01f5d57d23693f3814eb61fa0db6f0e54b240606`.
The contract also incorporates every indexed colleague Demo/More radical idea,
the six numbered user requests, and the later model, funding, and prompt-tuning
clarifications. The original investigation and conversation remain provenance if
an interpretation is disputed. This consolidation is an engineering summary,
not a claim that Haoyang separately approved every choice below.

## Decisions and intentional departures

“Explicit” means stated by the user in the available conversation. “Engineering
choice” means the implementation's interpretation or an inherited design; the
reviewer should judge whether it adequately fulfills the contract.

| Area | Choice, reason, and decision status |
| --- | --- |
| Accounts | Verified email OTP replaced the tentative phone-registration idea; it does not prove one unique human. Public trials require an explicit claim and cap grant recipients, not all registrations. Existing Auth0 accounts, private projects, and revocable sharing remain. MCP uses personal scoped tokens; OAuth is deferred. These are inherited engineering choices. |
| Repeat introductory credit | Haoyang accepted the recommended no-repeat policy after account deletion. Re-registration and BYOK remain available. Keyed markers cover a known verified email and issuer/subject pair for the program lifetime. Different credentials are not proof of a distinct person. Public identities deleted before this migration cannot be reconstructed. |
| Administrator credit | $50 means a lifetime total, retaining prior spending/reservations, rather than $50 additional or a fresh $50 balance. Five entitlements use a separate $250 administrator pool, preserving 100 public $5 places/$500 and the separate $500 OpenRouter emergency cap. Engineering interpretation proposed in the review. No curator role or whole-domain grant is implied. |
| Literal “if and only if CloudBank fails” | Transient provider failures get at most one retry; verified deployment/access failures may go directly to the qualified backup. A deployment-scoped circuit may reuse a recent failure without another CloudBank call on every request; default cooldown is 15 seconds, followed by a controlled probe. This cooldown is an engineering refinement of the literal per-request wording. It must never become permanent OpenRouter-first routing. |
| Failure and time limits | Missing local provider configuration, login/credit, invalid input, safety refusal, malformed successful output, semantic rejection, accounting failure, and an exhausted overall deadline do not authorize fallback spending. Provider 429 and transport/retryable server failures do. OpenRouter has no provider-level retry; feature correction calls are still counted and share the 180-second overall deadline. These bounds are engineering choices, not a guarantee of identical answers or latency across providers. |
| Model selection | Excluding the three weakest requested options, preferring successors, adding Gemini 3.1 Pro, using public benchmarks, and avoiding more expensive tiers are explicit. Sonnet 5 as default and the precise eight-model pool below are engineering selections. GLM was retained for family choice after Haoyang questioned its cost; Gemini Pro was added. Do not portray GLM retention as explicitly endorsed or claim the pool is a proven global Pareto frontier. |
| Other candidates | Kimi and GLM provide two additional families. DeepSeek V4 Flash 0731 was withheld after material application/provider failures; Grok lacked a verified exact Azure tariff. Unpublished deployments were retained, including Luna deployed before its exclusion. These are documented selection decisions, not permission for public API/BYOK/MCP access to excluded models. |
| Conversations | History is saved in per-conversation IndexedDB records in the same browser per account, with a compact selector rather than visual tabs. Transactions retain concurrent edits as explicit copies; deletion tombstones prevent stale tabs from restoring removed conversations. Source text and scenario snapshots are deduplicated and portable exports remain complete. Signed-out history is tab-local; signing out hides but retains that account's saved history for its next sign-in. No cross-device chat synchronization was built. These are intentional scope choices, and potential shortfalls if “automatic saving” or “tabs” implied more. |
| Forks and graph | Forks retain previous turns/snapshots but explicitly use the current scenario for the new question. There is no automatic historical-scenario restoration. The derivation inspector shows individual arguments and their local neighborhood alongside the grouped overview; it is not a full ungrouped global graph. Both choices implement the review's bounded proposals and remain reviewable for adequacy. |
| Edit identifiers | New LLM-generated identifiers allow 24 characters; manual editing allows 100, and modifying existing longer rule IDs remains supported. The larger generated-ID limit is an engineering choice intended to keep proposals readable. |
| Proposal scope | Omitted rule fields preserve existing values; explicit proposed values survive, and null or blank optional text clears that field. The complete before/after preview is the user's decision point. No keyword list guesses which natural-language phrasings authorize a change. An unavailable advisory review retains a validated proposal with a warning and all settled charges. |
| Evidence and precision | Source cards distinguish a matched answer quotation from a contextual source excerpt. Both verify source-span integrity; neither proves every paraphrase's entailment. Minor terminology/count/grouping errors were tolerated under the user's explicit guidance; wrong labels, operative causes, polarity, or counterfactual outcomes were material. Do not infer semantic correctness solely from a validator pass. |
| Evaluation method | Broad model-by-feature tests and targeted regressions were used, with short overrides only for observed failures. This is iterative qualification, not a locked blind holdout. Live OpenRouter generation was deliberately excluded to obey the spending constraint; its new routes' live conformance remains unverified. |

## Corrections to Tim's consolidated review

Finding numbers refer to the [dated review](demo-revision-independent-review-20260910.md).
Both High findings and all twelve Medium findings have corresponding code
corrections. This is an implementation status, not independent acceptance or
hosted deployment evidence.

| Findings | Corrected behavior and focused evidence |
| --- | --- |
| 1, 13 | Expected automatic-credit refusal no longer breaks sign-in. Dedicated HMAC eligibility markers survive deletion; mismatched keys fail closed. `test_credit_eligibility.py`, `test_account_error_boundaries.py`, migration 0007. |
| 2, 10, 14 | Every public route's local settings are checked at managed startup. Missing settings cannot authorize OpenRouter spending. BYOK shares the overall deadline and provider concurrency bound; native Anthropic uses its fixed official endpoint. `test_review_provider_guards.py`, routing and provider tests. |
| 3, 4, 5 | Quotation/context captions differ; explicit edits survive postprocessing; expected review failures preserve the paid proposal. Conservative assessments are identified in successful and failed request displays. `test_review_degradation.py`, `test_edit_retry.py`, browser proposal/evidence tests. |
| 6, 7, 8, 9 | Inspector selection matches the selected claim; transactional history retains concurrent copies and deletion markers; late answers stay with their original snapshot; shared source data is deduplicated. `test_exploration_browser.py`. |
| 11, 12 | Catalog evidence has four separate fields. OpenRouter remains live-unverified, as the owner accepted. Gemini's backup retains temperature 0 with compatible reasoning intent. Provider payload and admission tests. |
| Explain and interaction Low items | A custom two-derivation case reproduced a wrong causal explanation. Explain now follows actual argument identities and edges. Reference refresh/limits/forks, empty drafts, persistent changed-label cues and incremental announcements have browser regressions. Real screen-reader behavior is still unverified. |
| MCP and operations Low items | Shared account limits, pre-authentication throttling, safe typed errors, named-pool metrics, explicit funded environment filtering, stale-credit reconciliation, and exact-target rollout checks are implemented. The [credit maintenance procedure](operations/credit-policy-maintenance.md) describes key retention and the preparation-time writer gate; the [alert guide](operations/observability-alerts.md) describes the three new, undeployed routing alerts. |

The 45 qualification case definitions are now committed as suite v8. Historical
reports and failed outcomes remain intact. Assessments were performed answer by
answer by AI agents, not by a human reviewer. Accepted-defeater context remains
selective for Sonnet 5 and the internal DeepSeek route. The [baseline erratum](operations/evaluation-baseline-20260909.md)
identifies the two recorded GLM provenance failures that justify its existing
guidance. Passing prompts were not broadened for uniformity.

Current correction checks: 1,651 deterministic tests passed, with 77 browser or
PostgreSQL tests skipped on Delta. Chromium and Firefox passed the focused
interaction checks; WebKit needs CI's supported host libraries. Both application
and observability templates and parameter files compiled with pinned Bicep
0.46.1 using synthetic configuration. The [development CI workflow](https://github.com/Liu-Hy/ABDA-NL/actions/workflows/ci.yml?query=branch%3Adevelopment)
covers both Python versions, restricted-role PostgreSQL, all three browser
engines, packaging, container checks and secret scanning; match its result to
the reviewed commit.

Offline replay after the postprocessing fix preserved 1,061 of the earlier
1,080 complete request/result observations exactly. The other 19 belong to
Flash and GLM modifications. Fresh checks of all five affected cases, three
times per model, preserved the intended formal edits but found 13 optional
metadata failures, including seven incorrect undercut descriptions. Those
failures remain recorded. A 33-word reminder now tells only these two models'
rule-modification prompts to preserve unrequested fields, including absence.
The affected 30-observation regression is pending. Spending before it was
$66.387462 of the original $100, zero pending, with no paid OpenRouter calls.

## Selected model pool at the release snapshot

| Funded provider | Models |
| --- | --- |
| Azure Foundry | Claude Sonnet 5, Claude Opus 5, GPT-5.6 Terra, GPT-5.6 Sol, GLM 5.3, Kimi K3 |
| GCP Vertex | Gemini 3.8 Flash, Gemini 3.1 Pro Preview |

Every admitted model has an OpenRouter mapping. Native BYOK providers expose
their applicable subset; OpenRouter BYOK exposes the shared pool. Preserve model
identity and supported decoding/tool behavior when comparing routes, not just
display labels. Availability and prices are dated evidence. The catalog uses
gross Flash rates instead of anticipated rebates and caps Gemini Pro's estimated
input at 200,000 tokens to avoid the higher context tier. Catalog fields now
separate metadata/configuration confirmation, funded feature qualification,
and live inference verification. All OpenRouter live-inference flags remain false.

## Where to inspect the implementation

Paths below are starting points, not a restriction on review scope. Read caller,
adapter, error, and persistence paths together; tests may encode an incorrect
interpretation and should themselves be challenged.

| Requirements | Principal code and tests |
| --- | --- |
| R01, R13-R15: engine and scenario integrity | [scenario code](../app/scenario/), [portable exchange](../app/scenario/portable.py), [app.js](../app/static/app.js), [scenarios.js](../app/static/scenarios.js); `tests/test_scenario_*`, `test_rule_argument_context.py`, `test_accepted_defeater_context.py`. |
| R03, E03/E06/E07: identity and accounting | [credit policy](../app/services/credit_policy.py), [trials](../app/services/trials.py), [billing](../app/services/llm_billing.py), [accounts](../app/services/accounts.py), [projects](../app/services/projects.py), [migrations](../migrations/); `test_named_credit*`, `test_accounts_projects_trials.py`, `test_llm_routing_billing.py`, privacy tests. |
| R04-R06, E04/E05: routing and admission | [catalog](../app/llm/models.yaml), [catalog validation](../app/llm/catalog.py), [routing](../app/llm/routing.py), [providers](../app/llm/providers.py), [API access](../app/api/llm_access.py); `test_revision_llm_contracts.py`, `test_llm_api_access.py`, `test_provider_resilience.py`, `test_provider_clients.py`. |
| R07/R08/R12: prompts and qualification | [prompts](../app/prompts/), [model guidance](../app/llm/prompts.py), [chat](../app/llm/chat_service.py), [evidence](../app/llm/evidence.py), [evaluation code](../app/evals/), [budget](../app/evals/budget.py), [suite](../evals/llm_suite.yaml); `test_model_prompt_guidance.py`, `test_chat_validator.py`, `test_llm_eval.py`, proposer/reviewer/context tests. |
| R09: MCP | [server](../app/mcp/server.py), [client acceptance helper](../app/cli/mcp_client_acceptance.py), [token service](../app/services/mcp_tokens.py); `test_mcp*`. Verify subscription-only calls do not reach server inference and server-model calls require `llm:use`. |
| R10-R14: interaction | [exploration.js](../app/static/exploration.js), [app.js](../app/static/app.js), [workspace.js](../app/static/workspace.js), [index.html](../app/static/index.html); [exploration browser tests](../tests/test_exploration_browser.py), [workspace browser tests](../tests/test_browser_e2e.py). |
| R02, E01/E02/E07: operation | [launcher configuration](../.demo.json), [repository rules](../AGENTS.md), [Azure deployment](../deploy/azure/), [CI](../.github/workflows/ci.yml). Preserve managed lifecycle, image/schema compatibility, restricted roles, and budget/configuration invariants. |

## Earlier release evidence and remaining limits

1. **Model behavior:** the accepted composite contains 1,080 observations
   (45 cases, three repetitions, eight models), covering eleven feature groups:
   grounded chat, item/corpus questions, sensitivity, four proposal tasks,
   refinement, semantic review, and authoring-context fidelity. All six bundled
   scenarios plus custom/imported/renamed and adverse cases are represented.
   There are 1,057 original automatic passes, 21 phrase-matching adjudications,
   and two nonblocking assessments. The latter retain an optional GLM category
   omission with unchanged computed framework and a valid Sonnet state-heading
   quotation rejected by a corpus-only scorer. Inspect actual outputs and the
   justification, not just the accepted total. The final GLM-only chat reminder
   has a 63-observation regression; 1,017 retained observations have identical
   full-request/result replay. See the [qualification evidence](operations/model-qualification-20260910.md).
2. **Budget and funding:** before these corrections, lifetime CloudBank evaluation spending was
   $65.361387, zero pending, leaving $34.638613 of the original $100. This is
   conservative application accounting, not an invoice. Paid OpenRouter tests
   were zero. The authoritative evaluation ledger is
   `artifacts/evals/cloudbank-budget.sqlite3`; never restart it or create a fresh
   $100 allowance for review. Check that timeout/correction/cached/reasoning paths
   cannot escape accounting or switch to personal funding.
3. **Hosted credit and release:** schema 0006, one registered administrator's
   $50 total with prior usage retained, and four future entitlements were
   verified. The hosted native fixtures were synthetic; the real administrator's
   own OIDC/browser sign-in was not exercised in this release. See the
   [release receipt](operations/hosted-final-rollout-result-20260910.md).
4. **MCP:** both actual subscribed clients completed six tool calls and a
   versioned edit/readback. Separate HTTPS/browser checks covered owner data,
   denied access/scopes, and cleanup with unchanged ledgers. An earlier combined
   harness job remains FAILED even though its native phases passed; subsequent
   independent verification completes the evidence. A separate $0.048024 funded
   in-process MCP probe, included in the total above, tested question/proposal
   charging. It was not hosted server-model acceptance. See the
   [native result](operations/hosted-native-mcp-acceptance-result-20260910.md).
5. **Browser/failure coverage:** intercepted feature tests, actual anonymous
   hosted checks, and authenticated native-project readback are different scopes.
   The injected outage test checks retained drafts, derivation inspection, and
   recovery; other manual editing/saving/export operations were tested separately,
   not all in one outage session. No live provider outage was induced for this
   release. Review this coverage gap against R04. See the
   [UI evidence map](operations/ui-requirements-acceptance-20260910.md).
6. **Automation and human limits:** snapshot `026fde9` passed all eight
   [CI jobs](https://github.com/Liu-Hy/ABDA-NL/actions/runs/34462931025), including
   1,454 tests/53 skips per Python version and 52 tests per browser engine.
   [CodeQL](https://github.com/Liu-Hy/ABDA-NL/actions/runs/34462931020) found zero
   issues. `.gitleaksignore` exempts one exact, independently verified payload
   checksum occurrence, not a rule or file. Image policy accepted reviewed,
   unfixed dependency findings; do not claim zero image vulnerabilities.
   Actual Safari, screen-reader/hardware rehearsal, organizational reviews, and
   every direct BYOK provider's paid account remain distinct from these results.

Start with source review and deterministic tests. Browser tests require
`ABDA_BROWSER_TESTS=1` and an installed supported engine; the workflow documents
the matrix. Do not print `.env`, tokens, private receipts, or raw payloads.
Detailed model outputs and some cloud evidence live in gitignored/private
workspace storage and are not available from a fresh public clone; report that
evidence limitation instead of assuming the linked summaries prove everything.

Report findings by R/E identifier, severity, exact code location, reproducible
behavior, and missing evidence. Separate implementation defects, unmet user
intent, questionable design choices, and unverified external behavior. Suggest
small corrections; do not use this brief to authorize deployment, new paid
experiments, or unsolicited prompt tuning beyond the user's current task.
