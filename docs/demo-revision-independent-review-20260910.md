# Independent review of the September 2026 demo revision

Date: September 10, 2026. Brief: [requirements](demo-revision-contract.md)
and [review guide](demo-revision-review-guide.md). Reviewed snapshot: working
tree at `026fde9` (deployed source `234ffc9`); the revision starts after
`85bd4ae`.

Method: source review of every area named in the guide, the deterministic test
suite, 20 probe scripts against fake providers and temporary databases,
Chromium and Firefox browser workflows, and read-only checks of the public site
and the private qualification artifacts. Not done: no paid model calls, no live
provider outage, no cloud reads or writes, no WebKit (it cannot launch on the
review host), no re-run of the real subscribed clients. No repository files
were changed by the review; the budget ledger was only read.

## Verdict

The revision implements the contract's substance. The engine still owns every
label, no model output writes state, funded routing and accounting are
conservative, the MCP subscription path makes zero server inference, the
eight-model pool is consistent across quota, BYOK, and MCP, and the guide's
provenance claims all check out.

Two High defects and eleven Medium defects were confirmed by reproduction or
explicit code trace and should be corrected before this release is treated as
accepted. None requires new paid experiments to fix. The two High items: a named
administrator whose account is deleted (or whose entitlement is paused) can
never sign in again; and a configuration fault on a verified funded route
silently turns into indefinite OpenRouter-first routing, which the guide says
must never happen, while the production preflight now only warns.

Counts: 2 High, 11 Medium, 13 Low groups. Local suite: 1454 passed, 53 skipped.

## Provenance checks that hold

| Claim in the guide | Checked | Result |
| --- | --- | --- |
| Changes after the deployed source `234ffc9` are docs, one CI line, one gitleaks fingerprint | `git diff --stat 234ffc9..026fde9` | holds |
| `Requirements.docx` SHA-256 `fb934fec...`; both private files untracked and ignored | sha256sum, `git ls-files`, `git check-ignore` | holds |
| Catalog SHA-256 `2a0090bb...` | sha256sum of `app/llm/models.yaml` | holds |
| 1,080 observations = 1,057 + 21 + 2; 45 cases x 8 models x 3 repetitions; $65.361387 spent, zero pending, zero paid OpenRouter | composite assessment and ledger, read-only; both artifact hashes match | holds |
| Eight CI jobs, 1,454 tests / 53 skips, 52 browser tests per engine | workflow file, local full suite, browser collection | holds |
| Public site serves the eight-model pool with CSP and HSTS; served JS equals HEAD | read-only GET of `/`, `/config`, static assets | holds |
| "All 1,080 observations passed manual material-correctness review" | reviewer fields in the 36 review and decision files | see evidence limits: every reviewer is an AI evaluation agent |

## High

### 1. A deleted named administrator can never sign in again

R03, E03. Implementation defect. CONFIRMED by reproduction.

Sign-in calls the named-credit allocator with no error handling. When the
caller's email is one of the five named identities and its entitlement is
retired (user id cleared but bound), bound to another account, or the
administrator program is paused, the allocator raises. The user row is already
committed, so every later sign-in raises again. The OIDC callback turns any
non-identity exception into a `login_failed` redirect; the development login
returns HTTP 500.

Locations: `app/services/accounts.py:216-218`,
`app/services/trials.py:126-130, 185-186`, `app/api/account_routes.py:370-373`.

Reproduced: sign in as the fifth named identity, run privacy deletion, sign in
again twice; both attempts return 500 `internal_error`. The explicit claim route
also raises before reaching the public branch, so the person gets no trial at
all. Tests encode the raise at service level (`tests/test_named_credit.py:229-231,
293-295`) but never exercise the sign-in boundary. The hosted deployment runs
with automatic activation on, so the path is live.

Suggested correction: catch `TrialUnavailableError` in
`upsert_verified_identity` (log and continue) or make the allocator treat
bound, retired, and paused as "no automatic allocation". Keep the 409 on the
explicit claim route. Decide explicitly whether a retired named identity may
still claim the ordinary $5.

### 2. A configuration fault on a verified route becomes indefinite OpenRouter-first routing, and startup no longer fails closed

R04, E05, E07. Implementation defect and questionable design. CONFIRMED by two
independent reproductions.

When a verified primary route cannot be constructed (missing Azure key or
endpoint, missing GCP project, Vertex token failure), the router substitutes a
placeholder that raises a synthetic 401 `provider_configuration` error. A 401 on
a verified route is classified as a qualified operator fault, so the circuit
opens and the request goes to OpenRouter. Every 15 seconds the probe fails
instantly without touching CloudBank and re-opens the circuit. The failed
primary records no usage event, no alert covers OpenRouter spend or circuit
opening, and users are charged the OpenRouter multiplier meanwhile. The only
bound is the $500 emergency cap.

In the same revision the staging and production preflight was changed from
raising to logging a warning when Azure credentials, the GCP project, or the
OpenRouter key are missing, while `docs/operations/revision-rollout-20260909.md`
still calls a no-LLM configuration invalid. A mis-rendered secret reference
would therefore pass readiness and route silently.

Locations: `app/llm/routing.py:68-85, 795-804, 950-955`,
`app/llm/providers.py:1218-1222`, `app/api/main.py:120-140` (diff since
`85bd4ae`), `deploy/azure/gate14_observability_alerts.py:35-39`.

Reproduced with fake transports and no funded environment: four public profiles
served every request from OpenRouter with emergency billing across 40 seconds
and three zero-cost probes. The hosted readiness receipt shows all eight
configurations verified on September 10, so this is a latent path today, not a
current outage.

Suggested correction: substitute the placeholder only for runtime credential
responses from the provider, not for missing configuration; make the preflight
raise in staging and production for every public profile's primary route, or
require an explicit degraded-mode flag; record a failed usage event for the
placeholder; add an alert on `provider_configuration` failures or OpenRouter
spend rate.

## Medium

### 3. A paraphrase's fallback passage is shown as "Exact excerpt verified against the supplied source"

R12. Implementation defect. CONFIRMED by reproduction.

For every cited source with no verified quotation, the evidence builder appends
the lexically best-overlapping supplied chunk (up to 1,200 characters) marked
`verified: true`. The UI renders every verified source item with the caption
above. A user cannot distinguish a matched quotation from a context passage,
which is exactly the confusion R12 names.

Locations: `app/llm/evidence.py:238-248`, `app/static/exploration.js:303-315`.

Suggested correction: mark fallback entries `verified: false` or
`kind: "context"` and caption them as a supplied passage for the cited source,
not a verified quotation.

### 4. Modify-rule proposals silently revert explicitly requested changes

R07, R01. Implementation defect. CONFIRMED by reproduction.

The metadata-preservation heuristic restores every optional field (source,
category, block, active, negated description) unless the instruction contains
one of a fixed keyword list. Natural phrasings fall outside the list: "Turn off
r_stack for now" keeps the rule active; "Make r_stack much more important than
the tanking rule" keeps block 1; "Say that this rule comes from the 2025 roster
memo" keeps the old source. The preview then omits the requested change. This is
the wrong-edit class the contract says must be addressed.

Location: `app/llm/edit_service.py:585-667`.

Suggested correction: restore a field only when the proposal omits it or when
an explicit exclusive scope ("change only ...") is present; otherwise keep the
model's value and let the reviewer flag unrequested changes.

### 5. A reviewer-side provider failure discards an already validated and charged proposal

R04, R01. Implementation defect. CONFIRMED by code trace.

The advisory reviewer is called without error handling after the proposer loop
has consumed budget. A reviewer provider error, or the shared 180-second
deadline expiring during review, raises out of `run_propose`; the endpoint
returns a provider error and the validated operation is lost. No test injects a
reviewer failure.

Location: `app/llm/edit_service.py:795-804`.

Suggested correction: catch provider and validation errors around `run_review`,
return the operation with a "review unavailable" warning issue, and keep any
settled review cost in the totals.

### 6. The derivation inspector opens the wrong argument for a conclusion

R13. Implementation defect. Reproduced on all six bundled examples.

Opening the inspector from a conclusion card selects the first argument
concluding either the claim or its negation, in serializer order. Inspect on the
Accepted card "crispy" opens a Rejected derivation of "not crispy";
"legal_today" opens "not legal_today"; the same for "be_indication",
"order_to_go", "continue_ppi", and the Popov claims. The argument selector lets
the user recover, but the first view contradicts the card.

Locations: `app/static/exploration.js:357-372`; the browser test at
`tests/test_exploration_browser.py:232-249` sidesteps it by choosing an option
explicitly.

Suggested correction: prefer arguments whose conclusion equals the id and whose
label matches the card's aggregated label; fall back to the negation only when
no positive derivation exists, mirroring `getCandidateRootArguments` in
`app.js`.

### 7. Two tabs of the same account overwrite each other's saved history

R11. Implementation defect. CONFIRMED by reproduction.

Persistence writes the whole in-memory record array, storage is read only when
the owner changes, and there is no `storage` listener or merge. Sign-in
deliberately opens a new tab, so multi-tab is a designed path. Probe: tab B's
new conversation disappears after one keystroke in tab A and is gone after
reload.

Location: `app/static/exploration.js:18-62, 89-100`.

Suggested correction: re-read and merge by record id (newest `updated_at` wins)
before each write, or refresh the store on `storage` events.

### 8. Switching scenario or pressing Reset while an answer is pending discards the paid answer

R11, R04. Implementation defect. CONFIRMED by reproduction.

Loading a scenario, project, or share, and Reset, all start a new conversation
record; when the response arrives, the sender sees a different active
conversation and returns without storing or notifying. The original record
keeps only the user turn. The scenario selector is not disabled while a request
is in flight.

Location: `app/static/app.js:1326-1345, 1555`.

Suggested correction: append the assistant turn to the captured conversation
array and persist it, skipping only the render; or block switching while a
request is pending.

### 9. Roughly twenty questions on the default scenario exhaust browser storage

R11. Questionable design. CONFIRMED by measurement.

Each turn snapshots the full portable scenario with all source text plus the
framework (243 KB for Popov), and every keystroke re-serializes the whole store.
Headless Chromium stored 21 such turns before `QuotaExceededError`; after that
the entire blob fails to save, so all later turns are lost on reload, and the
notice's advice to delete older conversations does not help when the active one
is over quota.

Location: `app/static/exploration.js:186-198, 452`.

Suggested correction: deduplicate source text across snapshots by content hash,
or store pending operations plus a base-scenario reference; debounce
per-keystroke persistence.

### 10. BYOK requests have no overall deadline and skip the provider slot limit

E03, E04. Implementation defect. CONFIRMED by code trace.

The BYOK client is built with the configured retry attempts and no deadline,
and OpenAI, Google, and OpenRouter BYOK clients use the 120-second default
timeout. A proposal can occupy a synchronous worker for four calls times the
attempt count times 120 seconds, versus 180 seconds for funded calls. Enough
slow BYOK requests can starve the worker pool for every user.

Locations: `app/llm/routing.py:1091`, `app/llm/providers.py:409, 913`.

Suggested correction: give `byok()` the same 180-second deadline and 45-second
physical timeout as `funded()`.

### 11. The catalog marks OpenRouter backups verified although their live inference is unverified

R05. Missing evidence. CONFIRMED.

All eight OpenRouter routes carry `verified: true`, and public admission
requires that flag, but the hosted readiness receipt records
`openrouter_live_inference_verified: false` and the guide says the new routes'
conformance is unverified. The flag therefore does not establish the "AND
OpenRouter" half of R05 for the six new models. Unverified request contracts
include the GPT `max_completion_tokens` field, the reasoning-effort mapping,
Kimi's required tool choice, and the AWS-exclusion slugs.

Locations: `app/llm/models.yaml:341-575`, `app/llm/catalog.py:352-353`,
`docs/operations/hosted-model-configuration-readiness-20260910.json:22`.

Suggested correction: split the flag into metadata-verified and
inference-verified and require the latter for public admission, or record the
accepted risk explicitly in the guide.

### 12. Gemini's OpenRouter backup does not decode like its qualified primary

R05. Implementation defect. CONFIRMED by code trace.

The Vertex adapter sends temperature 0, one candidate, and an explicit thinking
level; the OpenRouter payload for the same model sends no temperature and a
reasoning-effort object. The other families send no temperature on either path,
so only Gemini diverges. The guide asks that decoding behaviour, not just
display labels, be preserved across routes.

Locations: `app/llm/providers.py:1025-1032` versus
`app/llm/providers.py:449-463`.

Suggested correction: set temperature 0 for the Google family in the
OpenAI-compatible payload, or drop it from the native adapter and re-qualify.

### 13. Operator deletion followed by re-registration grants a second public $5

R03. Questionable design, possible unmet intent. CONFIRMED by reproduction.

Deletion removes the grant but leaves the program counters, and activation
mints a new grant when none exists. After deletion and re-registration the
public program shows two activations for one person. Only named entitlements
keep a tombstone. Exposure is operator-mediated because deletion is CLI-only.

Locations: `app/services/privacy_requests.py:498-503`,
`app/services/trials.py:315-341`.

Suggested correction: persist a hashed-email tombstone (the account fingerprint
already exists at `privacy_requests.py:93-95`) and refuse a second public
activation, or document that deletion resets public eligibility.

## Low, grouped by area

### Exploration interaction (R10, R11, R14)

- The stale-context notice says to reselect the item, but reselecting adds a
  second chip, keeps the stale one, inserts the question text again, and Ask
  stays blocked (`exploration.js:272-275`, `app.js:1518-1521`). The staleness
  signature is the whole scenario JSON, so toggling an unrelated assumption
  invalidates every reference (`exploration.js:251-254`).
- No client cap on references; the 25th chip produces a 422 with a raw
  validation message at submission (`app/api/models.py:214`).
- Forking drops the edited turn's references, so the re-asked prompt differs
  from the original (`exploration.js:243`).
- Repeated New clicks persist empty "New conversation" records
  (`exploration.js:128-138`).
- Changed-label highlighting is a 0.75-second animation that reduced-motion
  neutralizes and that no test asserts; there is no persistent marker
  (`style.css:247-259, 1098-1105`, `app.js:826-831`).
- The chat container is `aria-live` and fully rebuilt on every render, so screen
  readers may re-announce the conversation on unrelated changes (pre-existing).

### Explain game, pre-existing (R13, R14)

- The game groups derivations by top rule and conclusion, unions attackers
  across variants, and silently drops the "Attacks" line when the edge belongs
  to a sibling derivation; the canonical label is the strongest variant's
  (`app.js:2404-2440, 3540-3548, 3871-3876`). Not reproducible on bundled data,
  but reachable on custom scenarios.
- Under a non-accepted root, "Premises and subarguments" lists only contested
  premises with no qualifier (`app.js:3471-3482`).
- The 24-character generated-ID limit predates the review boundary (introduced
  in `e83d3d2`); the diff under review contains no ID-limit change, though the
  current state satisfies R14.

### MCP (R09, E03)

- A token with only `llm:use` can read a project's facts and labels through
  `ask_project` although `get_project` refuses it (`app/mcp/server.py:312-325`).
- Unauthenticated requests to `/mcp/` are never rate limited; each bad bearer
  costs an HMAC and an indexed lookup (`app/api/main.py:252`,
  `server.py:81-108, 759`).
- MCP model tools meter in a separate bucket from the HTTP path, so one account
  can exceed the per-minute limit by splitting channels (`server.py:318`,
  `main.py:842, 885`).
- `ValueError` text is forwarded verbatim to the client (`server.py:228-229`);
  the browser's conflict message says "another tab" for MCP edits
  (`workspace.js:895`).

### Evidence and qualification (R12, R07, R08)

- A fabricated quotation with no citation in its paragraph is neither checked
  nor flagged (`app/llm/evidence.py:217-219`); no runtime check binds prose
  label claims to computed labels (`chat_service.py:475-519`), so offline
  qualification is the only protection.
- The committed suite has 43 cases; the two sensitivity cases behind the
  45-case evidence exist only in gitignored artifacts, while `evals/README.md`
  implies the committed suite is complete.
- Model identity gates computed context, not only guidance: accepted defeaters
  are included only for Sonnet 5 and DeepSeek (`app/llm/prompts.py:68-69`,
  `chat_service.py:581`). The GLM provenance override lacks an itemized failure;
  dead DeepSeek branches and an empty `app/prompts/guidance/` directory remain.
- The evaluator launcher copies every `GOOGLE_*` variable into the child, which
  would include a personal API key if one were set (`app/evals/funded.py:16-21`);
  harmless today because the transport allowlist blocks that host.

### Accounting and routing details (E06, E04)

- Stale reservations are reconciled only at process start, so an orphaned hold
  persists until a restart (`app/db/session.py:391-400`); a named-credit
  configuration mismatch refuses boot with no migration or CLI path
  (`trials.py:85-91`).
- Users pay the full conservative ceiling for a billing-uncertain CloudBank
  failure even when the fallback then succeeds, $0.09 to $0.36 per event on a
  40 KB prompt (`routing.py:483-486`).
- `use_provider_reported_cost` is inert because no OpenRouter payload asks for
  usage cost (`providers.py:442-467`); a `BaseException` in the half-open probe
  leaves the circuit stuck (`routing.py:721, 811`); Foundry Claude failures are
  recorded under provider `foundry` and successes under `azure-foundry`
  (`client.py:367, 478`); an accounting outage after dispatch surfaces as a bare
  500 instead of the existing accounting-unavailable message
  (`routing.py:522, 576`); internal metrics now cover only the public pool
  (`main.py:428-441`).
- BYOK Anthropic honours `ANTHROPIC_BASE_URL` from the process environment,
  which the repo's `.env` defines (`client.py:400-403`); the legacy non-router
  chat path survives in development with a direct key and the excluded Sonnet
  4.6 default (`llm_access.py:109-114`, `client.py:247`); GCP routes use undated
  aliases with no per-route version field (`models.yaml:501, 565`); a non-public
  duplicate Sonnet 5 profile answers "has not passed the public quality gate"
  (`models.yaml:220-225, 246-252`); unhandled `ValueError` text is returned in
  chat 400s (`main.py:661-662`).

### Operations and repository hygiene (E01, E07)

- Tracked deploy scripts and one receipt hard-code the Azure subscription,
  tenant, operator email, and full ARM resource ids
  (`deploy/azure/prepare-revision-rollout.py:22-28`,
  `deploy/azure/inspect-named-credit.py:18-22`,
  `docs/operations/hosted-recovery-rollout-plan-20260910.json`). Identifiers,
  not credentials, but the repository is public.
- The five colleagues' institutional emails are plaintext in public source and
  duplicated in a second literal list (`app/services/credit_policy.py:5-11`,
  `inspect-named-credit.py:32-35`); consider matching on digests and importing
  one list.
- Hosted job overrides execute base64-encoded Python, which is unreadable in
  execution history (`prepare-revision-rollout.py:172-186`,
  `inspect-named-credit.py:144-147`).
- "Drain incompatible writers" is a runbook step verified by receipts, not a
  code gate; the receipts are internally consistent but their ledger reports
  are private.

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

- The "manual" review was agentic. All reviewer fields in the 36 review and
  decision files name AI evaluation agents ("Codex evaluation agent", "root,
  explicit inspection ...", workspace paths). The adjudications sampled are
  justified in their own terms (the failed "label" checks are phrase matchers,
  and the quoted answers do state the label), but no person reviewed the 1,080
  answers. The guide should say so.
- Raw model outputs, the 45-case suite, hosted ledger reports, and rollout
  payloads are in gitignored or private storage; this review verified their
  hashes, counts, and internal consistency, not their content from a fresh
  clone.
- No live provider outage was induced; live OpenRouter inference for the six
  new routes is unverified by design; the real administrator's OIDC sign-in was
  never exercised; PostgreSQL row locking was not exercised locally (SQLite plus
  a process lock).
- The two real subscribed clients were not re-run; the FAILED combined
  verifier's cause remains unconfirmed; the hosted browser readback verified
  restored copies of the fixture projects, not the live post-edit rows.
- WebKit could not launch on the review host; Safari, screen readers, the
  laptop tunnel, and projector hardware were not exercised.

## Suggested order of corrections

1. Finding 1 (sign-in lockout) and finding 2 (fail-closed preflight,
   placeholder scope, alert). Both are small, deterministic changes with
   existing test scaffolding.
2. Findings 3 to 6: evidence caption, preservation heuristic, guarded reviewer,
   inspector candidate order. Each is a local change with an obvious regression
   test.
3. Findings 7 to 10: conversation merge, pending-answer retention, snapshot
   size, BYOK deadline.
4. Findings 11 to 13 and the guide wording on agentic review are documentation
   and policy decisions for Haoyang rather than code.

Nothing in this review authorizes deployment, new paid experiments, or prompt
tuning beyond the corrections above.
