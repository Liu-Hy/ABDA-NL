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
Review existing foundations as well as this diff wherever R01-R21 or E01-E07
depend on them. The later refinement adds R17-R21 and supersedes the earlier
question-frame, starter, Snapshot-control, typography, About and default-model choices.

The latest hosted source is `9a06436e76055997524e1e29cf438078461831e7`, deployed
to [demo.abda-nl.org](https://demo.abda-nl.org/) on September 11 UTC as revision
`abda-nl-stg-web--scenarios-9a06436-0911`. The
[verified release image](https://github.com/Liu-Hy/ABDA-NL/actions/runs/34571442559)
is `sha256:3c6e35cc01acdc9ade553a5eca76189cb4209d07d176e5932e4af9f916e6abb0`.
All eight [CI jobs](https://github.com/Liu-Hy/ABDA-NL/actions/runs/34571039640) and
[CodeQL](https://github.com/Liu-Hy/ABDA-NL/actions/runs/34571039703) passed:
1,925 tests/141 skips per Python version, 140 tests per browser engine, and
restricted-role PostgreSQL. The opt-in browser and PostgreSQL checks ran separately.

The [release receipt](operations/scenario-refinement-release-20260911.json)
binds source, image provenance, qualification and live checks. Both hosted and
managed checks matched 20 assets, six complete scenarios and the six-model pool,
with Flash as default. Anonymous Chromium/WebKit checks verified About defaults,
editable references, source highlighting and desktop/phone layouts. They add no
paid inference, authenticated account workflow or presentation-device acceptance.

This rollout changed the web image, revision suffix and default-model setting.
It preserved other runtime settings, identity and secret references, and kept
the manual migration job unchanged. No migration, secret-value request or database
row comparison was performed. Recovery must retain the stable eligibility key
and use a schema `20260910_0008` compatible image; the
[preceding rollout](operations/hosted-ui-rollout-result-20260911.json) records
that migration's data/accounting comparisons and backup limits.

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
| Accounts | Verified email OTP replaced the tentative phone-registration idea; it does not prove one unique human. Public trials require an explicit claim and cap grant recipients, not all registrations. Existing Auth0 accounts, private projects, and revocable sharing remain. These are inherited engineering choices. |
| MCP scopes | Personal scoped tokens protect account-owned projects; OAuth is deferred. `llm:use` permits reading project context through `ask_project` and `propose_project_edit`; direct `get_project` still requires `projects:read`. Token issuance states this read implication. This is an inherited engineering choice. |
| Repeat introductory credit | Haoyang accepted the recommended no-repeat policy after account deletion. Re-registration and BYOK remain available. Keyed markers cover a known verified email and issuer/subject pair for the program lifetime. Different credentials are not proof of a distinct person. Public identities deleted before this migration cannot be reconstructed. |
| Administrator credit and roles | $50 means a lifetime total, retaining prior spending/reservations. Five entitlements use a separate $250 pool, preserving 100 public $5 places/$500 and the separate $500 OpenRouter emergency cap. These budget interpretations were accepted. The owner subsequently explicitly made all five named identities scenario administrators too. Active, verified identity controls that role, not balance or email domain; configured additional curators remain supported. This supersedes the earlier proposal to keep the five identities' privileges separate. |
| Normal user view | Both groups retain a fixed header switch in both modes; Account also exposes the same setting. The browser session retains identity, projects, conversations and actual credit; it temporarily loses scenario administration in the interface and server requests. Refresh retains the mode, tabs synchronize, and sign-out resets it. This is not impersonation, a separate $5 allowance, or revocation of another browser's session or MCP token. Late administrator responses must not repopulate the demoted interface. |
| Literal “if and only if CloudBank fails” | Transient provider failures get at most one retry; verified deployment/access failures may go directly to the qualified backup. A deployment-scoped circuit may reuse a recent failure without another CloudBank call on every request; default cooldown is 15 seconds, followed by a controlled probe. This cooldown is an engineering refinement of the literal per-request wording. It must never become permanent OpenRouter-first routing. |
| Failure and time limits | Missing local provider configuration, login/credit, invalid input, safety refusal, malformed successful output, semantic rejection, accounting failure, and an exhausted overall deadline do not authorize fallback spending. Provider 429 and transport/retryable server failures do. OpenRouter has no provider-level retry; feature correction calls are still counted and share the 180-second overall deadline. These bounds are engineering choices, not a guarantee of identical answers or latency across providers. |
| Model selection | Excluding the three weakest requested options, preferring successors, adding Gemini 3.1 Pro, using public benchmarks, and avoiding more expensive tiers are explicit. Gemini 3.8 Flash replaces the earlier Sonnet default at the owner's request. The six-model pool is an engineering selection, based on application qualification rather than a new general ranking or a claim of a global Pareto frontier. |
| Other candidates | Gemini 3.1 Pro remains the additional choice. Kimi was initially admitted, then withheld after the expanded scenario tests exposed repeated causal and formal-acceptance errors despite short general prompt revisions. GLM and DeepSeek V4 Flash 0731 also remain internal candidates after application failures; Grok lacked a verified exact Azure tariff. These findings limit the requested optional expansion. Deployments and historical evidence remain, including Luna deployed before its exclusion; quota, BYOK and MCP consistently exclude unqualified choices. |
| Conversations | History is saved in per-conversation IndexedDB records in the same browser per account, with a compact selector rather than visual tabs. Transactions retain concurrent edits as explicit copies; deletion tombstones prevent stale tabs from restoring removed conversations. Source text and scenario snapshots are deduplicated and portable exports remain complete. Signed-out history is tab-local; signing out hides but retains that account's saved history for its next sign-in. No cross-device chat synchronization was built. These are intentional scope choices, and potential shortfalls if “automatic saving” or “tabs” implied more. |
| Forks and graph | Forks retain previous turns/snapshots but explicitly use the current scenario for the new question. There is no automatic historical-scenario restoration. The derivation inspector shows individual arguments and their local neighborhood alongside the grouped overview; it is not a full ungrouped global graph. Both choices implement the review's bounded proposals and remain reviewable for adequacy. |
| Edit identifiers | New LLM-generated identifiers allow 24 characters; manual editing allows 100, and modifying existing longer rule IDs remains supported. The larger generated-ID limit is an engineering choice intended to keep proposals readable. |
| Proposal scope | Omitted rule fields preserve existing values; explicit proposed values survive, and null or blank optional text clears that field. The complete before/after preview is the user's decision point. No keyword list guesses which natural-language phrasings authorize a change. An unavailable advisory review retains a validated proposal with a warning and all settled charges. |
| Evidence and precision | Source cards distinguish a matched answer quotation from a contextual source excerpt. Both verify source-span integrity; neither proves every paraphrase's entailment. A short general instruction requests directly relevant evidence or requested citations and omits irrelevant citations. The application constructs the cards from verified citations, without a separate model tool call. Repetitive formal-reference footers are removed. Minor terminology/count/grouping errors remain tolerable; wrong labels, operative causes, polarity, or counterfactual outcomes are material. |
| Cancellation | Stop aborts the originating HTTP request. The proposal editor's Cancel and close actions also abort pending generation. The serving replica watches its disconnect, signals the provider worker, closes its transport and prevents further retry/fallback/correction calls. Accounting completes on the request thread; dispatched work with unknown usage retains its conservative charge. A proxy or provider can delay termination of already-dispatched work. Explicit development-only legacy/Ollama clients retain their ordinary timeout; public funded and BYOK routes use the cancellation guard. |
| Archived deletion | Checkbox selection, Delete selected, Delete all and confirmation are explicit requirements. Deletion targets the confirmed archived project IDs and versions atomically, so a concurrent restore or newly archived project cannot silently join the operation. Separately submitted and published snapshots remain; deletion does not unpublish them. These scope and concurrency rules are engineering choices. |
| Scenario history | The three reconstructed bundled knowledge bases follow the consolidated proposal; no stored project or published snapshot is migrated. Complete exports preserve embedded source text. Older server objects can contain corpus filenames, so they may resolve the three corrected documents to current text. This existing limitation is documented, rather than adding a source-storage migration to a content-only task. |
| Evaluation method | Broad model-by-feature tests and targeted regressions were used, with short overrides only for observed failures. This is iterative qualification, not a locked blind holdout. Live OpenRouter generation was deliberately excluded to obey the spending constraint; its new routes' live conformance remains unverified. |

## Corrections to Tim's consolidated review

Finding numbers refer to the [dated review](demo-revision-independent-review-20260910.md).
Both High findings and all twelve Medium findings have corresponding code
corrections. This is an implementation status, not independent acceptance or
hosted deployment evidence.

| Findings | Corrected behavior and focused evidence |
| --- | --- |
| 1, 13 | Expected automatic-credit refusal no longer breaks sign-in. Dedicated HMAC eligibility markers survive deletion; mismatched keys fail closed. Account locks precede billing and marker locks, including during live reconciliation. `test_credit_eligibility.py`, `test_account_error_boundaries.py`, `test_postgres_acceptance.py`, migration 0007. |
| 2, 10, 14 | Every public route's local settings are checked at managed startup. Missing settings cannot authorize OpenRouter spending. BYOK shares the overall deadline and provider concurrency bound; native Anthropic uses its fixed official endpoint. `test_review_provider_guards.py`, routing and provider tests. |
| 3, 4, 5 | Quotation/context captions differ; explicit edits survive postprocessing; expected review failures preserve the paid proposal. Conservative assessments are identified in successful and failed request displays. `test_review_degradation.py`, `test_edit_retry.py`, browser proposal/evidence tests. |
| 6, 7, 8, 9 | Inspector selection matches the selected claim; transactional history retains concurrent copies and deletion markers; late answers stay with their original snapshot; shared source data is deduplicated. `test_exploration_browser.py`. |
| 11, 12 | Catalog evidence has four separate fields. OpenRouter remains live-unverified, as the owner accepted. Gemini's backup retains temperature 0 with compatible reasoning intent. Provider payload and admission tests. |
| Explain and interaction Low items | A custom two-derivation case reproduced a wrong causal explanation. Explain now follows actual argument identities and edges. Reference refresh/limits/forks, empty drafts, persistent changed-label cues and incremental announcements have browser regressions. Real screen-reader behavior is still unverified. |
| MCP and operations Low items | Shared account limits, pre-authentication throttling, safe typed errors, named-pool metrics, explicit funded environment filtering, stale-credit reconciliation, and exact-target rollout checks are implemented. The [credit maintenance procedure](operations/credit-policy-maintenance.md) describes key retention and the preparation-time writer gate; the [alert guide](operations/observability-alerts.md) describes the three new, undeployed routing alerts. |

Earlier qualification and failed candidate reports remain in the
[qualification evidence](operations/model-qualification-20260910.md) and
`artifacts/evals/review-corrections-composite-assessment-20260910-v2.json`.
Those results are historical; the scenario-refinement qualification below
supersedes them for the current source and pool.

Earlier correction CI, administrator-view checks and managed-demo receipts are
retained under `artifacts/evals/final-admin-ci-469f688-20260910/` and
`review-local-demo-final-readiness-20260910.json`. The earlier UI baseline
below is historical; the current release boundary is recorded above.

## Consolidated UI revision

The UI revision starts at `02c77dc955661eac3f9773aaeaaa2a29b9dbb3c1`. Its
acceptance criteria are condensed in the contract; Tim's consolidated review
and the earlier response are supporting provenance, not additional entry
points a reviewer must reconcile.

| Area | Implementation and focused checks |
| --- | --- |
| Shell and explorer, P01-P07/P10-P14 | `ui-shell.js`, `ui-shell.css`, `argument-navigation.js`, `app.js`; `test_ui_shell_browser.py` checks selection without loading, Reset/Undo scope, exact graph navigation, saved-bundle games, terminal leaves, and seven screen sizes. Existing game tests retain full-defense and cycle cases. |
| Chat and sources, P08-P10/P15/P29 | `composer.js`, `source-reader.js`, `exploration.js`, `conversation-storage.js`, `chat-exploration.css`; `test_composer_source_reader.py` and `test_exploration_browser.py` cover ordered references, IME, clipboard/caret/Undo, legacy history, late answers and account isolation, quotation offsets, ambiguity, and saved source text. |
| Authoring, P16-P22 | `scenarios.js`, `materials.js`, `authoring.css`; `test_authoring_browser.py` and the migrated existing browser workflows cover empty drafts, stable symbols, literal selection, validation/save, import, documents and portable export. |
| Projects and publication, P23-P28 | `workspace.js`, `curation.js`, `workspace.css`, project/submission services and API, migration 0008; `test_workspace_projects_publication.py`, `test_submission_metadata_migration.py`, `test_workspace_revision_browser.py`, and restricted-role PostgreSQL contention checks. |

Intentional refinements:

- The owner's later feedback replaces the generic question frame with an item
  reference, removes starter questions and per-turn Snapshot controls, and uses
  the shorter Chat & Explore heading. Stored snapshots and exports remain.
- Keep the system font stack, with compact 13 px explorer text, 12 px controls,
  14 px chat text and 14 px reading text on narrow screens. A restrained
  blue-gray heading band is a design choice. Actual original, current and 85%
  zoom screenshots informed the proportions; the older 15 px requirement is
  superseded by the owner's density preference.
- Use a shared navigation bar that replaces the active argument dialog rather
  than nesting the game over the inspector. Preserve the exact bundle and
  derivation, with a return to the prior game or graph. Describe projected
  rebuts as one-way or bidirectional, since an absent projected edge alone
  does not prove a preference decided the outcome. Node descriptions wrap to
  three short lines; complete text remains in the accessible name and tooltip.
  Fit shows the whole topology; larger graphs require zoom or inspection to
  read every description comfortably.
- The selected item's identifier is the direct inspector link; a second
  conclusion-row overflow duplicates that action without adding a user goal.
  Rule overflow remains useful for its three distinct actions. Desktop split
  proportions adapt below laptop width rather than imposing a 420 px minimum
  on a narrow viewport.
- Document page counts are shown only when the upload result actually contains
  them. Retained text size is explicit; original PDFs are not stored. Source
  location mismatches remain unconfirmed instead of changing qualified PDF
  extraction or suggesting that context alone is a verified quotation.
- Current user guides and the conference playbook use the new labels. The
  extended abstract's labels still need alignment in its publication workflow;
  this repository has no tracked manuscript source. Actual presentation-device
  rehearsals remain separate from browser automation.

The earlier UI baseline `2037b60` passed its
[CI](https://github.com/Liu-Hy/ABDA-NL/actions/runs/34546624149) and
[CodeQL](https://github.com/Liu-Hy/ABDA-NL/actions/runs/34546624291). Its hosted
receipt is linked above; local and offline-pack evidence remains under
`artifacts/evals/final-ui-ci-2037b60-20260910/`,
`ui-local-final-readiness-2037b60-20260910.json` and
`ui-conference-20260911T003006Z.json`. These are historical checks, since the
following refinement changes model input and served assets.

## Scenario and chat refinement

This revision reconstructs three knowledge bases, rewrites all six About
introductions and starts About closed. An explicit opening lasts within the
current view; changing scenario, project or account closes it again. Old stored
open preferences do not override the new default. Introductory paragraphs give
background and the decision context without duplicating formal labels.

The [scenario implementation note](operations/scenario-reconstruction-implementation-20260910.md)
records the proposal correspondence, corpus corrections, 93 deterministic
behavioral checks and saved-source limitation. Engine code, scenario format and
stored knowledge bases are unchanged. New local tests cover cancellation through
ASGI middleware, metered settlement, no retry/fallback after Stop, request/account
isolation, the default model, the fixed administrator toggle and About behavior.

The admitted six-model pool has 584 reviewed observations covering all 52 cases
per model. Changed request groups were tested three times; unchanged groups retain
every original repetition only after exact request, result and provider-setting
replay. Repetition counts therefore vary across retained groups. The final
`artifacts/evals/scenario-refinement-20260910/admitted-six-model-assessment.json`
binds these results to fingerprint `5fbca7cd`, preserves automatic flags and
records no material findings in the admitted pool. Reviews are by AI agents,
not independent human acceptance or a blind holdout.

Kimi's last 84 responses included four material findings: two quotation-check
delivery failures, an incorrect premise/cause explanation and an incorrect
acceptance criterion. Its earlier three targeted errors were resolved, but the
new findings justified withholding the entire model. All 112 Kimi observations
in the final candidate set and earlier failed runs remain diagnostic evidence;
none were selected to make its admission pass. See
`kimi-withholding-decision-20260911.json` and
`seven-model-final-diagnostic-assessment.json` in the same artifact directory.
The cumulative ledger is **$104.122660 of $150**, with no pending reservations
and no paid OpenRouter tests. This is conservative recorded usage, not an invoice.

Archived deletion has owner, version, account-change and confirmation tests,
including real disposable API workflows in all three browser engines. Existing
foreign keys remove old links and preserve submitted/published snapshots and
accounting. The final focused browser checks passed in Chromium, Firefox and
WebKit, including graph target spacing and comment contrast. The archive/restore
test now waits for the completed archive layout before clicking its filter.
The final source CI and hosted release passed; their evidence is linked above.

A same-question cost audit found prompt growth from 15,067 to 41,579 characters
across the earlier revisions, mainly complete engine state and exact corpus
passages. The new evidence instruction added 150 characters. Nine corrections in
441 sampled historical chat turns cost $0.052551, about 0.83% of their total.
Output limits and reasoning settings did not increase for this visual revision.
Useful grounding remains; evaluation repetitions now run adjacent to reduce
avoidable cache expiry. The detailed offline audit is retained at
`artifacts/evals/scenario-refinement-20260910/offline-cost-audit.md`.

## Current qualified model pool

| Funded provider | Models |
| --- | --- |
| Azure Foundry | Claude Sonnet 5, Claude Opus 5, GPT-5.6 Terra, GPT-5.6 Sol |
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
| R03/R16: administrator roles and normal user view | [settings](../app/core/config.py), [view-mode policy](../app/services/admin_view.py), [account routes](../app/api/account_routes.py), [effective permissions](../app/api/dependencies.py), [scenario routes](../app/api/scenario_routes.py), [curation UI](../app/static/curation.js), [workspace](../app/static/workspace.js); `test_admin_view.py`, `test_named_credit.py`, browser view-mode tests. |
| R17/R20: bundled scenarios and About | [examples](../examples/), [scenario acceptance](../tests/test_reconstructed_scenarios.py), [shell](../app/static/ui-shell.js), `test_ui_shell_browser.py`. |
| R18/R19: cancellation and cost | [disconnect handling](../app/api/llm_cancellation.py), [provider worker](../app/llm/client.py), [billing](../app/services/llm_billing.py), `test_llm_cancellation.py`, `test_llm_routing_billing.py`; offline cost audit above. |
| R21: archived private project deletion | [project service](../app/services/projects.py), [account routes](../app/api/account_routes.py), [workspace](../app/static/workspace.js); `test_archived_project_deletion.py`, `test_exploration_browser.py`, `test_postgres_acceptance.py`. Check confirmed ID/version sets, atomic ownership and restore conflicts, snapshot preservation, and unchanged accounting. |
| R02, E01/E02/E07: operation | [launcher configuration](../.demo.json), [repository rules](../AGENTS.md), [Azure deployment](../deploy/azure/), [CI](../.github/workflows/ci.yml). Preserve managed lifecycle, image/schema compatibility, restricted roles, and budget/configuration invariants. |

## Earlier release evidence and remaining limits

1. **Earlier model qualification:** the original eight-model reports, failed
   outputs and adjudications are retained in the
   [qualification evidence](operations/model-qualification-20260910.md).
   They and the later 945-observation baseline are historical evidence;
   neither a validator pass nor exact replay proves semantic correctness.
2. **Budget and funding:** the authoritative lifetime ledger is
   `artifacts/evals/cloudbank-budget.sqlite3`. Record the final total with each qualification phase;
   never restart it or create a fresh allowance for review. The owner raised
   the cumulative ceiling from $100 to $150 on September 11, with all earlier
   spending retained and additional testing limited to what is useful. Verify that
   timeout, correction, cached-token and reasoning-token paths remain accounted
   for and cannot switch evaluation to personal funding.
3. **Earlier hosted credit and release:** schema 0006, one registered administrator's
   $50 total with prior usage retained, and four future entitlements were
   verified. The hosted native fixtures were synthetic; the real administrator's
   own OIDC/browser sign-in was not exercised in that release. See the
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
   issues. `.gitleaksignore` exempts two exact checksum occurrences, each
   recomputed against its original private receipt. Image policy accepted reviewed,
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
