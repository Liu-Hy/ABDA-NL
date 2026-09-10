# Consolidated review findings and correction plan

September 10, 2026. This document merges the independent review of the demo
revision with the implementer's [comments](demo-revision-review-response-20260910.md)
into one work list for the next revision. It is written against the
[requirements](demo-revision-contract.md) and the
[review guide](demo-revision-review-guide.md).

Both inputs remain dated records. Where the two reviews disagreed, this
document states the resolution and the evidence that settled it. Nothing here
authorizes deployment, new paid experiments, or prompt tuning beyond the
corrections listed.

## Provenance of this document

| Input | Snapshot | Method |
| --- | --- | --- |
| Independent review | working tree at `026fde9`, deployed source `234ffc9` | source review of every area named in the guide, the deterministic suite (1454 passed, 53 skipped), 20 probes against fake providers and temporary databases, Chromium and Firefox browser workflows, read-only checks of the public site and the private qualification artifacts |
| Implementer response | `94febed`, which differs from `026fde9` in three documentation files | traced each finding, isolated probes with fake inputs, in-memory SQLite, JavaScript in a Node VM, and a check of current OpenRouter documentation |
| Consolidation | working tree at `026fde9` | re-verified every disputed claim in code and in the private receipts before accepting or rejecting it |

Neither review made paid model calls, cloud mutations, or changes to the
budget ledger. Neither repeated the other's full suite or browser matrix.

## Status after consolidation

2 High, 12 Medium, and the Low groups below. One review finding was promoted
(Anthropic BYOK endpoint, from Low to Medium), one was restated after its
measurement was shown to be unrepresentative (storage capacity), one was
withdrawn (OpenRouter reported cost), and several were narrowed. Both reviews
agree that the two High findings and most Medium findings justify corrective
work despite the earlier passing acceptance checks.

### Disputed claims and how they were resolved

| Claim in the first review | Resolution | Evidence |
| --- | --- | --- |
| A paused named-credit program locks out administrators | Narrowed. A pause blocks a new beneficiary, not an administrator already holding the full $50 | `trials.py:178-179`: the raise is guarded by `if added and not program.enabled`, and `added` is 0 at the full grant |
| The misconfigured route records no failed usage event | Confined to the construction placeholder. A Vertex token failure is raised inside the metered request, so it is recorded | `providers.py:1216-1222` is reached from `_post`, inside the metered call |
| Roughly twenty questions on the default scenario exhaust storage | Restated. Submission deduplicates identical snapshots, so an unchanged scenario reuses one snapshot; the exposure is distinct scenario states, forks, and separate conversations | `app.js:1535-1538` compares snapshots with `captured_at` nulled and reuses the existing id; the implementer completed 39 questions with one snapshot and a 254 KB store |
| `use_provider_reported_cost` is inert because no payload requests cost | Withdrawn | The adapter parses `usage.cost` at nine call sites (`providers.py:195-215, 275, 492-651`), metering tests exercise provider-cost settlement, and current OpenRouter documentation describes usage accounting as returned in the response without additional calls |
| The `llm:use` scope inconsistently grants project read | Reframed as a token-issuance clarity point, not an inconsistency | [ADR 0004](decisions/0004-authenticated-mcp-access.md) explicitly assigns `ask_project` and `propose_project_edit` to `llm:use`; ownership is still checked |
| The hosted browser readback verified restored copies | Corrected | `hosted-native-verification-restoration-20260910.json` records `new_projects: 0`, the same two archived project ids, and a restore that sets `archived_at=NULL` while preserving every other field including scenario and version 3. These were the original rows after unarchiving. The fair limitation is that this was a later verification phase after archival, not an uninterrupted native-edit-to-browser journey |
| DeepSeek prompt branches are dead code | Corrected. The internal evaluation route still supports withheld candidates | Withheld candidates remain selectable for internal evaluation only |
| Hashing the five institutional emails would protect privacy | Softened. Five guessable institutional addresses are not meaningfully protected by hashing; publishing less unnecessary data is the useful step | |

The first review's proposed fixes for findings 3, 7, 8, 9, 11, and 12 were
each improved by the response and are superseded below.

## Verdict

The revision implements the contract's substance. The engine still owns every
label, no model output writes state, funded routing and accounting are
conservative, the MCP subscription path makes zero server inference, the
eight-model pool is consistent across quota, BYOK, and MCP, and the guide's
provenance claims all check out.

Two High defects and twelve Medium defects should be corrected before this
release is treated as accepted. None requires new paid experiments to fix, and
most can be established with deterministic or mocked-provider regressions. The
two High items: a named administrator whose account is deleted can never sign
in again; and a missing local configuration on a verified funded route can
sustain OpenRouter-first operation, which the guide says must never happen,
while the production preflight now only warns.

## Provenance checks that hold

| Claim in the guide | Checked | Result |
| --- | --- | --- |
| Changes after the deployed source `234ffc9` are docs, one CI line, one gitleaks fingerprint | `git diff --stat 234ffc9..026fde9` | holds |
| `Requirements.docx` SHA-256 `fb934fec...`; both private files untracked and ignored | sha256sum, `git ls-files`, `git check-ignore` | holds |
| Catalog SHA-256 `2a0090bb...` | sha256sum of `app/llm/models.yaml` | holds |
| 1,080 observations = 1,057 + 21 + 2; 45 cases x 8 models x 3 repetitions; $65.361387 spent, zero pending, zero paid OpenRouter | composite assessment and ledger, read-only; both artifact hashes match | holds |
| Eight CI jobs, 1,454 tests / 53 skips, 52 browser tests per engine | workflow file, local full suite, browser collection | holds |
| Public site serves the eight-model pool with CSP and HSTS; served JS equals HEAD | read-only GET of `/`, `/config`, static assets | holds |
| "All 1,080 observations passed manual material-correctness review" | reviewer fields in the 36 review and decision files | wording needs correction; see evidence limits |

## High

### 1. A deleted named administrator can never sign in again

R03, E03. Implementation defect. Both reviews agree, with the description
narrowed.

Sign-in calls the named-credit allocator with no error handling, and the
identity is already committed when the allocation fails. When the caller's
email is one of the five named identities and its entitlement is retired (user
id cleared but bound) or bound to another account, the allocator raises on
every subsequent sign-in. The OIDC callback turns any non-identity exception
into a `login_failed` redirect; the development login returns HTTP 500.

A paused program is a narrower case: it blocks a new beneficiary's first
allocation, and resuming the program restores that login. An administrator who
already holds the full $50 signs in normally while the program is paused.

Locations: `app/services/accounts.py:216-218`,
`app/services/trials.py:126-130, 178-186`, `app/api/account_routes.py:370-373`.

Evidence: sign in as the fifth named identity, run privacy deletion, sign in
again twice; both attempts return 500 `internal_error`. The explicit claim
route also raises before reaching the public branch, so the person gets no
trial at all. Tests encode the raise at service level
(`tests/test_named_credit.py:229-231, 293-295`) but never exercise the sign-in
boundary. The hosted deployment runs with automatic activation on, so the path
is live.

Agreed correction: separate successful authentication from unavailable
automatic credit. Catch the expected allocation-unavailable condition, roll
back that allocation transaction, and record a sanitized operational reason. Do
not swallow identity or security failures, or accounting corruption. Preserve
the explicit claim errors and retired-entitlement protection. Add a regression
at the sign-in boundary, not only at the service level.

Open question: whether a retired named identity may still receive the ordinary
$5 is the policy decision in finding 13.

### 2. Missing configuration on a verified route can sustain OpenRouter-first operation, and startup no longer fails closed

R04, E05, E07. Implementation defect and questionable design. Both reviews
agree; the remedy is refined.

When a verified primary route cannot be constructed (missing Azure key or
endpoint, missing GCP project), the router substitutes a placeholder that
raises a synthetic 401 `provider_configuration` error. A 401 on a verified
route is classified as a qualified operator fault, so the circuit opens and the
request goes to OpenRouter. Every 15 seconds the probe fails instantly without
touching CloudBank and re-opens the circuit. Users are charged the OpenRouter
multiplier meanwhile, and the only bound is the $500 emergency cap.

The circuit does log an error, so this is not literally silent, but a log line
and a spend cap are not adequate operator notification. No alert covers
OpenRouter spend or circuit opening. The construction placeholder records no
usage event; a Vertex token failure at request time is inside the metered call
and is recorded.

In the same revision the staging and production preflight was changed from
raising to logging a warning when Azure credentials, the GCP project, or the
OpenRouter key are missing, while `docs/operations/revision-rollout-20260909.md`
still calls a no-LLM configuration invalid. The preflight also checks only the
default profile and can return before checking its backup.

Locations: `app/llm/routing.py:68-85, 795-804, 950-955`,
`app/llm/providers.py:1216-1222`, `app/api/main.py:95-140` (diff since
`85bd4ae`), `deploy/azure/gate14_observability_alerts.py:35-39`.

Evidence: two independent reproductions with fake transports and no funded
environment. Four public profiles served every request from OpenRouter with
emergency billing across 40 seconds and three zero-cost probes. The hosted
readiness receipt shows all eight configurations verified on September 10, so
this is a latent path today, not a current outage.

Agreed correction: validate required local configuration for every public
primary and every enabled backup before accepting a new deployment. Missing
local configuration should produce a route-unavailable condition, not a
synthetic provider 401 that authorizes spending. Keep actual provider and
authentication-service outages distinct from absent settings. Emit a
configuration-health event rather than inventing a paid-attempt event for an
undispatched call. Add route-health and fallback-spend alerting.

Constraint on the fix: this is about configuration presence at deployment
acceptance, not provider reachability at runtime. A running demo must keep its
manual features when providers fail, so transient provider reachability must
not become a condition for the site to run.

## Medium

### 3. A fallback source passage is shown under the quotation caption

R12. Implementation defect. Both reviews agree on the problem; the verification
claim and the fix are qualified.

For every cited source with no verified quotation, the evidence builder
attaches the lexically best-overlapping supplied chunk (up to 1,200
characters) marked `verified: true`. The UI renders every verified source item
as "Exact excerpt verified against the supplied source". The bytes and offsets
do identify supplied text, so the caption is literally true of the span; what
fails is the distinction between a matched quotation and suggested reading
context. The passage can be attached to a paraphrase it does not support.

Locations: `app/llm/evidence.py:238-248`, `app/static/exploration.js:303-315`.

Agreed correction: represent these as different evidence roles and explain the
distinction in the UI. Keep source-span integrity separate from quotation
matching and from claim support. Do not simply set `verified: false`: the UI
filter at `exploration.js:303` renders only `verified === true` items, so that
would hide useful inspectable evidence instead of relabelling it.

### 4. Metadata preservation reverses requested edits

R07, R01. Implementation defect. Both reviews reproduced all three classes.

The preservation helper restores every optional field (source, category, block,
active, negated description) unless the instruction contains one of a fixed
keyword list. Natural phrasings fall outside the list: "Turn off r_stack for
now" restores `active=true`; "Make r_stack much more important than the tanking
rule" restores block 1; "Say that this rule comes from the 2025 roster memo"
restores the old source. The application undoes a correct model proposal, which
is the wrong-edit class the contract says must be addressed.

Location: `app/llm/edit_service.py:585-667`.

Agreed correction: preserve omitted fields, retain explicit proposed values,
and expose the complete change for review. Any exclusive-field protection must
have an unambiguous scope rather than guessing natural language; more keyword
synonyms would perpetuate the problem. Add deterministic regressions for
ordinary alternative phrasings and for unrelated-field preservation. This is a
postprocessing fix and is not evidence that prompts need further tuning.

### 5. A reviewer failure discards an already validated and charged proposal

R04, R01. Implementation defect. Both reviews agree.

The advisory reviewer is called without error handling after the proposer loop
has consumed budget. A reviewer provider error, or the shared 180-second
deadline expiring during review, raises out of `run_propose`; the endpoint
returns a provider error and the validated operation is lost. No test injects a
reviewer failure.

Location: `app/llm/edit_service.py:795-804`.

Agreed correction: degrade to an explicit "review unavailable" result that
retains the validated operation for user inspection. Handle expected provider,
deadline, and response-validation failures narrowly; do not turn unknown
programming errors or unresolved accounting failures into success. Preserve all
settled proposer and reviewer costs, including failed attempts, using the
metered client's totals rather than only successful response objects. Never
apply the proposal automatically.

### 6. The derivation inspector opens the wrong argument for a conclusion

R13. Implementation defect. Reproduced on all six bundled examples.

Opening the inspector from a conclusion card selects the first argument
concluding either the claim or its negation, in serializer order. Inspect on
the Accepted card "crispy" opens a Rejected derivation of "not crispy";
"legal_today" opens "not legal_today"; the same for "be_indication",
"order_to_go", "continue_ppi", and the Popov claims.

Locations: `app/static/exploration.js:357-372`; the browser test at
`tests/test_exploration_browser.py:232-249` sidesteps it by choosing an option
explicitly.

Agreed correction: prefer the exact selected literal and an appropriate
argument label, with an explicit fallback when no such derivation exists.
Apply the same rule to formal-reference navigation. Test the initial inspector
state before interacting with its selector. The user's ability to choose the
correct argument afterwards does not excuse the misleading initial view.

### 7. Concurrent tabs lose conversation history

R11. Implementation defect. Both reviews agree; the first review's proposed fix
is insufficient.

Persistence writes the whole in-memory record array from one tab's stale
memory, storage is read only when the owner changes, and there is no `storage`
listener or merge. Sign-in deliberately opens a new tab, so multi-tab is a
designed path. Probe: tab B's new conversation disappears after one keystroke
in tab A and is gone after reload.

Location: `app/static/exploration.js:18-62, 89-100`.

Agreed correction: use transactional per-conversation storage, or another
design with explicit conflict and deletion handling. A `storage` listener or
last-write-timestamp merge helps but does not make simultaneous
read-modify-write atomic, and merging only surviving records can resurrect
deleted conversations. Cover concurrent creation, edits to the same
conversation, deletion, reload, and account isolation. Browser-local storage
was an intentional scope choice; cross-tab data loss was not.

### 8. Switching scenario or pressing Reset while an answer is pending discards the paid answer

R11, R04. Implementation defect. Both reviews agree.

Loading a scenario, project, or share, and Reset, all start a new conversation
record; when the response arrives, the sender sees a different active
conversation and returns without storing or notifying. The original record
keeps only the user turn. A changed scenario can also replace the answer with a
notice.

Location: `app/static/app.js:1326-1345, 1549-1556`.

Agreed correction: store the answer on its original conversation and snapshot
with a clear earlier-state label, leaving the current view alone. Keep the
account-change and deleted-record checks: a late response must not restore
deleted content or persist another account's conversation after sign-out. Do
not block scenario switching, which would unnecessarily constrain non-LLM
exploration.

### 9. Snapshot duplication and write amplification can exhaust browser storage

R11. Questionable design. Both reviews agree on the problem; the first review's
threshold was unrepresentative and is withdrawn.

Each turn snapshots the full portable scenario with all source text plus the
framework (243 KB for Popov). Submission deduplicates identical snapshots
within a conversation, so repeated questions against an unchanged scenario
reuse one snapshot: the implementer completed 39 questions with one snapshot
and a 254 KB serialized store in a Node VM probe. The original measurement of
21 turns before `QuotaExceededError` in headless Chromium used a distinct
scenario state per turn, which is the exploration workflow but not the only
one. The exposure is therefore different scenario states, forks, large answers,
and separate conversations, each of which can duplicate substantial data.
Independently of that, every keystroke re-serializes the whole store, and once
the blob exceeds quota all later turns are lost on reload while the notice's
advice to delete older conversations does not help.

Locations: `app/static/app.js:1535-1538` (dedup),
`app/static/exploration.js:186-198, 452`.

Agreed correction: deduplicate shared immutable source content, debounce
writes, and provide useful capacity and recovery controls. Transactional
storage can address this together with finding 7. Any compact internal
representation must still reconstruct complete portable exports without the
original catalog; a bare external base-scenario reference would violate R15.

### 10. BYOK requests have no overall deadline and skip the provider slot bound

E03, E04. Implementation defect. Both reviews agree.

The BYOK client is built with the configured retry attempts and no deadline, so
OpenAI, Google, and OpenRouter BYOK clients use the 120-second default timeout.
The concurrency bound is also skipped: `invoke_before_deadline` returns the
call directly when no deadline is supplied, before acquiring the provider slot
semaphore. A proposal can occupy a synchronous worker for four calls times the
attempt count times 120 seconds, versus 180 seconds for funded calls, so enough
slow BYOK requests can starve the worker pool for every user.

Locations: `app/llm/routing.py:1091`, `app/llm/client.py:94-97`,
`app/llm/providers.py:409, 913`.

Agreed correction: give BYOK the same overall wall-time and concurrency
protections as funded requests, including retries and advisory review. A
shorter HTTP inactivity timeout alone is insufficient. Keep BYOK charging and
credentials separate. Fake slow transports can verify this without paid calls.

### 11. One `verified` flag conflates different kinds of evidence

R05. Missing evidence. Both reviews agree on the gap; the admission rule is
qualified.

All eight OpenRouter routes carry `verified: true`, and public admission
requires that flag, but the hosted readiness receipt records
`openrouter_live_inference_verified: false`. Configuration and published
availability do not prove successful live inference under this application's
tools, decoding, and privacy filters. Unverified request contracts include the
GPT `max_completion_tokens` field, the reasoning-effort mapping, Kimi's
required tool choice, and the AWS-exclusion slugs.

Locations: `app/llm/models.yaml:341-575`, `app/llm/catalog.py:349-353`,
`docs/operations/hosted-model-configuration-readiness-20260910.json:22`.

Agreed correction: separate metadata and configuration confirmation, funded
feature qualification, and live backup testing, so the flag stops standing for
all three. Public metadata and mock request-contract checks can reduce
uncertainty without spending. This does not establish that the backups are
broken, and the pool must not be silently disabled or unperformed tests
declared successful.

Open question: requiring fresh paid OpenRouter inference before admission
conflicts with the CloudBank-only testing authorization in R08. That is
Haoyang's decision: either extend the spending authorization, or accept and
record the release boundary as it stands.

### 12. Gemini's OpenRouter backup does not decode like its qualified primary

R05. Implementation defect. Both reviews agree; the first review's alternative
fix is withdrawn.

The Vertex adapter sends temperature 0, one candidate, and an explicit thinking
level; the OpenRouter payload for the same model omits temperature. The other
families send no temperature on either path, so only Gemini diverges.

Locations: `app/llm/providers.py:1025-1032` versus
`app/llm/providers.py:449-463`.

Agreed correction: preserve the already qualified setting in the backup,
subject to the provider's supported parameter contract, and test both payloads.
Do not remove the primary's setting to obtain superficial symmetry, which would
invalidate its qualification. Different thinking-field names across adapters
are expected; equivalent intent needs checking, not identical JSON or identical
answers. This is a code correction, not a documentation item.

### 13. Public credit can be granted again after deletion

R03. Behavior agreed; the remedy is a policy choice.

Deletion removes the grant but leaves the program counters, and activation
checks only the current account and the cumulative counters. After deletion and
re-registration the public program shows two activations for one person. This
weakens a one-lifetime-grant-per-person reading of R03. It does not bypass the
100-grant and $500 public ceiling, and deletion is operator-mediated.

Locations: `app/services/privacy_requests.py:498-503`,
`app/services/trials.py:315-341`.

Recommended policy, subject to Haoyang: no automatic repeat introductory grant,
while allowing sign-in and self-funded use. Make the rule and any retained
eligibility marker explicit. The existing unsalted, truncated email fingerprint
is not automatically an adequate anti-abuse identifier because the addresses
are guessable; decide the identifier, its retention, and the eligibility
semantics together. Named-entitlement retirement must remain intact regardless
of this decision.

### 14. BYOK Anthropic requests inherit the ambient endpoint

E04. Implementation defect. Promoted from Low at the implementer's request, and
confirmed here.

The native Anthropic branch constructs the SDK client without a base URL, so it
honours `ANTHROPIC_BASE_URL` from the process environment, which the repository
`.env` defines and `serve.py` loads. With a dummy key and an `.invalid`
environment URL, the constructed client inherited that URL; no request was
sent. `README.md:97-98` promises fixed official endpoints, so this is a
concrete violation of the fixed-endpoint contract and a credential-routing
risk, not a demonstrated real-key leak.

Location: `app/llm/client.py:399-403`. Note that the constructor accepts
`base_url` but applies it only in the Foundry branch (`client.py:393-398`), so
passing a router argument alone would be ignored.

Agreed correction: pin the native Anthropic endpoint inside the SDK branch
itself.

## Low, grouped by area

### Exploration interaction (R10, R11, R14)

- The stale-context notice says to reselect the item, but reselecting adds a
  second chip, keeps the stale one, inserts the question text again, and Ask
  stays blocked (`exploration.js:272-275`, `app.js:1518-1521`). Fix the
  recovery action and the wording. Whole-scenario invalidation is defensible,
  because remote changes can alter an item's grounded status, so outdated
  context must not be kept silently.
- Enforce the 24-reference limit before submission; today the 25th chip
  produces a 422 with a raw validation message (`app/api/models.py:214`).
- Forking drops the edited turn's references (`exploration.js:243`). Preserve
  the reference identities but revalidate them against the explicitly current
  scenario, with visible treatment for missing or changed references. Carrying
  old references forward blindly is unsafe.
- Repeated New clicks persist empty records (`exploration.js:128-138`). Reuse
  an unused draft or defer persistence until the record has content.
- Changed-label highlighting is a 0.75-second animation that reduced-motion
  neutralizes and that no test asserts (`style.css:247-259, 1098-1105`,
  `app.js:826-831`). Add a non-motion changed-state cue and regression
  coverage, keeping reduced-motion support.
- The chat container is `aria-live` and fully rebuilt on every render, so
  screen readers may re-announce the conversation on unrelated changes. This is
  a plausible announcement problem that neither review demonstrated with
  assistive technology. Prefer incremental announcements and verify with a real
  screen reader.

### Explain game, pre-existing (R13, R14)

- The game groups derivations by top rule and conclusion, unions attackers
  across variants, and silently drops the "Attacks" line when the edge belongs
  to a sibling derivation; the canonical label is the strongest variant's
  (`app.js:2404-2440, 3540-3548, 3871-3876`). Not reproducible on bundled data.
  Build a custom-case reproduction before choosing the change. If it
  demonstrates a wrong causal explanation or label, treat it as Medium despite
  being pre-existing; the separate inspector does not repair the game.
- Under a non-accepted root, "Premises and subarguments" lists only contested
  premises with no qualifier (`app.js:3471-3482`). Qualify the list or offer
  the complete derivation.
- The 24-character generated-ID limit predates the review boundary (introduced
  in `e83d3d2`). R14 is satisfied by existing behavior, not by a change in this
  diff, and no further increase follows from that observation.

### MCP (R09, E03)

- A token with only `llm:use` can read project content through `ask_project`
  (`app/mcp/server.py:312-325`). This is the documented design in ADR 0004, and
  ownership is still checked, so it is not an authorization bypass and implies
  no cross-owner disclosure. Clarify the read implication when issuing tokens,
  or deliberately change the scope dependency.
- Unauthenticated requests to `/mcp/` are never rate limited; each bad bearer
  costs an HMAC and an indexed lookup (`app/api/main.py:252`,
  `server.py:81-108, 759`). Throttle unauthenticated transport requests early,
  keeping authentication, revocation, and trusted client-address handling
  correct.
- MCP model tools meter in a separate bucket from the HTTP path
  (`server.py:318`, `main.py:842, 885`). This does not violate the financial
  caps but can exceed the intended aggregate request rate; share an
  account-wide limit across HTTP and MCP, with per-tool limits if useful.
- `ValueError` text is forwarded verbatim (`server.py:228-229`). No sensitive
  disclosure was demonstrated, but returning every exception string is not a
  sound boundary: use typed safe user errors and a generic message for
  unexpected cases. The browser conflict message should say "another editor or
  connected tool" rather than "another tab" (`workspace.js:895`).

### Evidence and qualification (R12, R07, R08)

- A fabricated quotation with no citation in its paragraph is neither checked
  nor flagged (`app/llm/evidence.py:217-219`), and no runtime check binds prose
  label claims to computed labels (`chat_service.py:475-519`). Both remain
  semantic assurance limits rather than defects to close by brute force: an
  uncited quotation may be a legitimate rule description or heading, and the
  engine still owns actual labels. Keep provenance distinctions clear and
  target demonstrated material errors instead of adding a general
  natural-language truth checker or another model judge.
- Commit the two additional sensitivity case definitions with any required
  sanitized fixtures, and explain how the 45-case release assessment relates to
  the committed 43-case suite (`evals/llm_suite.yaml`, `evals/README.md`).
  Preserve the original reports and hashes. Reproducibility does not require
  publishing raw transcripts or private operational receipts.
- The guide should state that the extra accepted-defeater context is supplied
  selectively rather than uniformly (`app/llm/prompts.py:68-69`,
  `chat_service.py:581`). Require a concrete case reference for GLM's
  provenance override. Do not broaden passing prompts for uniformity alone.
  DeepSeek guidance is not dead code, because the internal evaluation route
  still supports withheld candidates; the empty `app/prompts/guidance/`
  directory is optional cleanup.
- Use an explicit funded-variable allowlist and remove personal API-key
  variables from the inherited environment as well as from `.env` copying
  (`app/evals/funded.py:16-21`), preserving the ADC and Vertex variables
  actually required. The current transport restriction limits the risk and no
  personal-project spending was shown.

### Accounting and routing details (E06, E04)

- Stale reservations are reconciled only at process start
  (`app/db/session.py:391-400`). Add a periodic or operator-triggered sweep
  that preserves uncertain liabilities rather than releasing them blindly.
- Refusing a mismatched fixed allocation at boot (`trials.py:85-91`) protects
  the ledger and should be kept. Provide a controlled policy-migration path and
  a clear diagnostic instead of silently changing allocations.
- The full conservative charge for a billing-uncertain failure
  (`routing.py:483-486`) is an existing E06 budget-protection choice, not
  incorrect arithmetic. Show users when an amount is provisional or
  conservatively assessed, and reconcile or credit verified differences later.
  Any policy that shifts uncertain costs away from the user needs explicit
  accounting for who bears them.
- Release half-open probe state even when a `BaseException` escapes, without
  swallowing it (`routing.py:721, 811`); use consistent provider identifiers
  (`client.py:367, 478`); return the existing sanitized
  accounting-unavailable response instead of a bare 500 (`routing.py:522,
  576`); and keep metrics visibility into known routes with outstanding or
  historical liabilities (`main.py:428-441`). None of these may weaken
  reservations or permit fallback after an accounting failure.
- The legacy direct-key chat path is a development-only exception, not a public
  admission bypass (`llm_access.py:109-114`, `client.py:247`). Make that
  boundary explicit and prevent it from silently governing the shared demo.
- Record or pin resolved GCP model versions where supported
  (`models.yaml:501, 565`); an alias alone does not prove a wrong model was
  served. The hidden duplicate Sonnet 5 profile should report that the profile
  is unavailable rather than imply its qualified model failed evaluation
  (`models.yaml:220-225, 246-252`).
- Unhandled `ValueError` text is returned in chat 400s (`main.py:661-662`).

### Operations and repository hygiene (E01, E07)

- Centralize the eligibility data and parameterize deployment-specific
  identifiers while preserving exact-target checks
  (`deploy/azure/prepare-revision-rollout.py:22-28`,
  `deploy/azure/inspect-named-credit.py:18-22, 32-35`,
  `app/services/credit_policy.py:5-11`). These identifiers are not credentials,
  so this justifies no secret rotation or rewriting of historical receipts, and
  hashing five guessable institutional addresses is not itself meaningful
  protection; publishing less unnecessary data is the useful step.
- Base64 job payloads transport a reviewed script through job arguments and are
  not a correctness defect or a secrecy mechanism
  (`prepare-revision-rollout.py:172-186`, `inspect-named-credit.py:144-147`).
  Keep readable source and payload hashes available for audit.
- "Drain incompatible writers" is a runbook step evidenced by receipts, not a
  machine-checked gate. Make it a deployment gate covering old replicas and
  jobs before activating transfers.

## Verified as satisfied

| Area | What was checked |
| --- | --- |
| R01 engine ownership | Proposal endpoints return operations only; state changes go through client-supplied ops and deterministic validation; labels come only from the engine; the reviewer is advisory; MCP writes require scope, validation, and an expected version. All six bundled examples match their expected labels; the explorer, Explain game, ASPIC export, library, and import round-trips pass in the browser. |
| R03 credit | 100 x $5 public program with database constraints, exact under 8-thread contention; the $50 lifetime named total moves prior spending and pending reservations correctly; email normalization binds all five contract identities including mixed case; a second identity with a held address is refused; retired entitlements never re-grant; no curator privilege derives from eligibility. |
| R04 routing | With the real adapter and 18 failure shapes: 429, 408, 5xx, and transport errors retry once then fall back; 400, content filter, invalid request, malformed JSON, empty output, and validation failures never fall back; deadline errors are terminal; one CloudBank retry, no OpenRouter retry, one 180-second deadline shared by corrections and review; reservation before every physical attempt; BYOK never uses the app's OpenRouter key; provider text never reaches responses. |
| R05, R06 pool | Public ids are the eight models on the API, BYOK subsets, and the MCP profile schema; Haiku, Luna, Flash-Lite, Sonnet 4.6, Gemini 3.7, DeepSeek, and cross-provider models are rejected; Astra, Fable, and Grok are absent; the default is Sonnet 5 everywhere; the price gate matches the Sol/Opus class; OpenRouter payloads carry ZDR, denied data collection, required parameters, price caps, and AWS exclusions; Vertex requires an explicit project and the personal project id appears nowhere. |
| R08 budget | Ledger read-only: $65.361387 settled, zero pending, 4,073 settled and 37 released reservations, no charge above its reservation, no OpenRouter rows; the evaluator refuses OpenRouter credentials and enforces a transport allowlist; interrupts leave reservations pending, which is conservative. |
| R09 MCP | With every model entry point patched to raise: list, create, read, apply, and readback succeed and no billing rows appear; stale version, invalid op, bad second op in a batch, unknown kind, and 101 ops are rejected with byte-identical readback; cross-owner and share-only access return "not found"; revocation, expiry, suspension, and un-verification give 401 on the next call; a foreign Origin gives 403. |
| R10 composer | The question is inserted at the cursor without deleting a selection; chips carry identity and are removable by keyboard; the click makes no request (tests assert no chat and no export request); no-access keeps the composer editable with Ask disabled; the 390 px layout keeps the composer in view; axe passes. |
| R13, R15 structure and export | One argument per premise combination with unique flattened subtrees; the inspector shows premises, subarguments, rules, labels, and typed attacks with text labels; v3 export embeds every corpus file's text and re-imports with identical labels and no source catalog; uploaded sources never become facts. |
| R14, E01, E02, E07 | Heading, modified count, Reset, "Premises and subarguments", accepted-without-challenge explanation, and minimap removal present; the launcher keeps placeholders and a foreground child on loopback; private files ignored; image publishing gated by license, audit, digest smoke test, and attestation; the restricted database role enforced at startup; migration 0006 refuses downgrade while bound; fixture cleanup recorded with counts and the FAILED Slurm verdict retained. |

## Evidence limits

- The guide's phrase "manual material-correctness review" is ambiguous. The
  accurate description is answer-by-answer assessment by AI agents, with
  explicit adjudications and preserved failures. Every reviewer field in the 36
  review and decision files names an agent. Haoyang did request agent-driven
  evaluation, so this is a wording correction for the guide and not a newly
  discovered unmet requirement; it implies no new human-review gate.
- Raw model outputs, the 45-case suite, hosted ledger reports, and rollout
  payloads are in gitignored or private storage; both reviews verified hashes,
  counts, and internal consistency, not content from a fresh clone.
- No live provider outage was induced; live OpenRouter inference for the six
  new routes is unverified by design; the real administrator's OIDC sign-in was
  never exercised.
- PostgreSQL row locking was not exercised in this review, which used SQLite
  and a process lock. The earlier PostgreSQL CI evidence remains separate and
  valid within its documented scope.
- The two real subscribed clients were not re-run, and the FAILED combined
  verifier's cause remains unconfirmed. The hosted browser readback used the
  original project rows after unarchiving, not reconstructed copies; its
  limitation is that it was a later verification phase after archival rather
  than an uninterrupted native-edit-to-browser journey.
- WebKit could not launch on the review host; Safari, screen readers, the
  laptop tunnel, and projector hardware were not exercised.

## Decisions for Haoyang

1. Whether a retired named identity may still receive the ordinary $5, and
   whether public credit may be granted again after account deletion, together
   with the identifier and retention that would enforce either rule
   (findings 1 and 13).
2. Whether to extend the testing authorization to cover live OpenRouter
   inference for the six new backup routes, or to accept and record the release
   boundary as it stands (finding 11).
3. Whether to correct the guide's "manual review" wording to agent assessment,
   which both reviews recommend.

## Correction order

1. Sign-in and credit separation (finding 1) and missing-configuration routing
   (finding 2), followed closely by the BYOK endpoint and deadline protections
   (findings 14 and 10).
2. Wrong edit preservation (4), advisory review degradation (5), inspector
   selection (6), and retaining paid answers on their original snapshots (8).
3. Conversation concurrency and capacity (7 and 9), evidence-role labeling (3),
   Gemini payload parity (12), and the scope, throttling, and error-boundary
   items in the Low groups.
4. Verification terminology (11), committed sensitivity fixtures, precise AI
   review attribution, and the public-credit deletion policy (13).

Most corrections can be established with deterministic or mocked-provider
regressions. Any prompt or model-input change would still need the affected
feature qualification under the original CloudBank budget, and must not trigger
indiscriminate tuning or paid OpenRouter testing. Once these are settled, the
accepted clarifications belong in the two-document brief; this consolidated
list and the two dated review records remain the history.
