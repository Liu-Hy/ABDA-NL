# COMMA 2026 requirements traceability

This record maps the accepted paper, the project requirements, and the later
service requirements to evidence in the repository. It distinguishes code
completion from release checks that require operator-owned accounts, public
infrastructure, or presentation hardware.

## Authoritative inputs

- `Requirements.docx`, SHA-256
  `fb934fec9ab180586774a80f01f5d57d23693f3814eb61fa0db6f0e54b240606`
- `camera-ready.pdf`, SHA-256
  `2fa5737de77fa2ac799a1d5a34a49d4f27b894421cffa22ca57e7cffecc16c07`
- Model gate suite version 4, SHA-256
  `83345e9a6a6a13d0c3c25bac7810bd7042b48ecf6bd1ee6989a42f0773dce867`

The two source documents are deliberately untracked. They must not enter a
release image or public source commit unless the authors make that separate
publication decision.

## September 5 recovery checkpoint

Current September 6 status supersedes the pilot and remaining-cloud-operation
statements in this historical checkpoint and its evidence tables. The
[public release record](public-release-20260906.md) proves completed rollback
and restoration, 100 cumulative $5 trial grants with a $500 total cap, enabled
outage-only OpenRouter fallback under its separate $500 cap, and passed final
audit, external release, public browser, and bounded capacity checks. The
operator-authorized Delta CLI now owns routine cloud operations. There is no
remaining manual deployment batch.

The actual Foundry inventory is also verified. The four newer candidates
previously probed by name are absent; the evaluated primary and fallback stay
unchanged. Earlier verified-email, project, sharing, BYOK, and MCP live evidence
is retained without redundant user testing. Presentation hardware, direct BYOK
accounts with sufficient provider credit, and organizational reviews remain
separate acceptance boundaries.

### Historical pilot evidence

The original document hashes above were rechecked unchanged. Development
commit `26c0908bcbd1fb2bab87f7892f3ae4c6c3b113e8` passed all eight jobs in
[CI run 33991132718](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33991132718),
including Python 3.10 and 3.13, PostgreSQL, deployment artifacts, secret
scanning, and Chromium, Firefox, and WebKit acceptance.
[CodeQL run 33991132713](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33991132713)
also passed. Fresh repository API queries returned zero open development
code-scanning alerts, zero open Dependabot alerts, and zero open secret-scanning
alerts. These are source checks, not approval to deploy a new image.

The privacy history receipt recovered a successful reviewed deletion with one
identity, project, share link, and MCP credential removed. The subsequent
read-only metadata and exact-runner review established the intended database
destination and execution ordering. The operator confirmed deletion of the
exact disposable Auth0 identity. The privacy-recovery prerequisite is now
complete, without rerunning deletion or relabeling the old diagnostic as
passed. See
[the recovery evidence](privacy-preflight-failure-20260905.md). Do not repeat
the privacy workflow or infer failure from the diagnostic's exit 2.

After the operator saved the corrected Cloudflare hostname rule, the unchanged
public hostname gate passed through ordinary DNS resolution. Root and `www`
redirects, path and query preservation, demo readiness, Auth0 discovery, and
the existing Resend DNS records were verified. See the
[hostname receipt](cloudflare-apex-redirect.md). These public checks do not
refresh protected budget metrics or establish a new deployed image identity.

Live remote checks confirmed both repositories' `main` branches still at
`e4be41c72f34dd555147a2de221d84b3fd735c9f`. No Azure, Auth0, Cloudflare,
trial, provider, or license setting was changed by those initial checks.
The subsequent GPL decision and artifact publication are recorded in the
[GPL checkpoint](gpl-distribution-checkpoint-20260905.md). Its subsequent
[live pilot audit and browser smoke](gpl-live-checkpoint-20260905.md) passed.
Public Chromium, Firefox, and bounded capacity checks passed afterward.
The remaining operator-owned cloud checks and presentation hardware remain
external gates;
the original 100-user trial and bounded public fallback objectives are not
replaced by the current ten-user pilot.

## Design evolution from the original requirements

The original requirements posed five product questions rather than prescribing
one architecture. The following refinements preserve those goals while adapting
them to the provider, security, and ownership evidence gathered during
implementation.

| Original intent | Adopted refinement | Reason and release boundary |
| --- | --- | --- |
| Keep the implementation faithful to the accepted paper and improve it for the live demonstration. | The iDAKS `main` branch remains the reviewed, paper-faithful demo. Hosted-service work stays on the personal repository's `development` branch until separately accepted. | ArXiv readers get a stable artifact while service debugging cannot silently change the paper target. |
| Make the demo available at a fixed URL and keep convenient local and Delta operation. | Azure Container Apps serves `demo.abda-nl.org`. The same Python entrypoint also supports an ordinary local browser launch and the private Delta `demo` launcher. On 2026-08-29, the tracked placeholder contract, pinned-node doctor and status, liveness, readiness, public configuration, and managed logs passed without restarting the running fallback. | Delta login nodes are not public hosting. Retest the `ssh delta-demo` tunnel and automatic local browser opening on the actual presentation laptop. |
| Give the first 100 users $5, possibly after phone registration. | Auth0 verifies email OTP identities. Trial credit is claimed explicitly and capped transactionally at 100 users, $5 each, and $500 total. The live service currently uses a ten-user, $50 pilot. | Verified email is easier to operate professionally than phone verification. The smaller pilot validates real billing before the final cap is promoted, but it does not replace the 100-user requirement. |
| Use CloudBank-funded models, investigate stronger low-cost choices, and keep OpenRouter as a safety net. | A versioned catalog separates provider deployments from logical profiles. Only routes that pass ABDA-specific quality, latency, cost, and privacy gates can become public. CloudBank Claude Sonnet 4.6 is the balanced primary, and OpenRouter Gemini 3.7 Flash is the qualifying-outage fallback. | Catalog availability is not deployment availability, and general rankings do not prove reliable grounded chat or structured editing. The controlled outage drill reconciled both ledgers. Public fallback remains disabled until its final spending boundary and release settings are accepted. |
| Let Codex or Claude Code interact with the demo. | Verified users create revocable, scoped personal MCP tokens for the HTTPS Streamable HTTP endpoint. OAuth is deferred until a complete authorization server can replace the token flow. | This delivers real client access without advertising incomplete OAuth or weakening project ownership, version checks, or trial accounting. |
| Preserve unlimited use for researchers who bring their own keys. | BYOK supports fixed Anthropic, OpenAI, Google, and OpenRouter endpoints and allowlisted models. A key exists only in tab memory and one request client, the client is closed after that request, and MCP deliberately does not accept provider keys. | This preserves unlimited self-funded use without creating a credential vault, arbitrary proxy, or agent-transcript secret path. |
| Organize collaboration cleanly while keeping current and improved demos runnable. | The paper repository and personal service repository have separate responsibilities. One application entrypoint serves local, Delta, and managed modes, while immutable image digests identify public releases. | Administrative control is available now, Shawn's history and the stable paper demo remain intact, and later organization promotion remains possible. |

Private projects, read-only sharing, abuse controls, accessibility gates,
observability, privacy operations, and rollback procedures are deliberate
service requirements added during planning. They support a durable public
research service and do not alter the paper's deterministic ABDA authority.

## Camera-ready feature claims

| Published claim | Implementation and evidence | State |
| --- | --- | --- |
| Web explorer with conclusions, facts and assumptions, rules, and chat | The primary page retains the four-panel explorer. The real-browser test requires populated conclusions, facts, rules, and at least six scenarios. | Implemented and browser-tested |
| Natural-language glossary over an ASPIC- knowledge base | Scenario YAML contains proposition descriptions. Serialization renders them while the ABDA bridge remains the source of arguments, attacks, and grounded labels. Engine, loader, serialization, and integration tests cover this boundary. A [fixed-source audit](deterministic-engine-validation-20260904.md) also passed 20 historical engine checks and exactly matched all six deployed baseline payloads to local recomputation. | Implemented and deterministic |
| Corpus-grounded general and item-focused chat | Chat prompts receive only the selected immutable corpus and current deterministic state. Citation validation rejects invented files and retries once. The question-mark controls issue focused questions and remain keyboard operable. | Implemented, live model routes evaluated |
| Interactive Explain discussion game | Explain exposes argument selection, support expansion, attacks, preferences, moves, and resolution. The Chromium and Firefox journeys enter it by keyboard, run WCAG A and AA scans on the picker and tree, and exercise multi-challenge resolution plus an undecided cycle. | Implemented and browser-tested |
| Suspend rules or assumptions and modify preferences | State changes are represented as validated diff operations. The browser previews suspension impact before applying it. Conflict and grounded-engine tests cover preference changes and recomputation. | Implemented and deterministic |
| Author rules, facts, and assumptions in natural language | The model proposes schema-constrained operations. Deterministic validation can block them, semantic review is advisory, and the user must apply an accepted proposal. The browser test opens and closes the edit dialog by keyboard. | Implemented, model quality-gated |
| ABDA remains authoritative after every change | `/state` and project working-state routes rebuild the framework and grounded labels from the validated scenario. No model response can set a conclusion label. | Implemented and tested |
| Graph view, raw ASPIC- view, saving, and multiple examples | The browser journey opens both views. Private projects provide durable public saving, while local filesystem saving remains a development feature. Six bundled examples are included in the source tree, container, and installed wheel. | Implemented and browser-tested |

## Expanded research-service requirements

| Requirement | Implementation and evidence | Remaining release gate |
| --- | --- | --- |
| Ordinary local launch and Delta `demo` compatibility | One `abda-nl` entrypoint defaults to loopback, waits for readiness, and opens the local browser. `--no-browser` supports managed runs. `.demo.json` retains `{host}` and `{port}`, uses the foreground command, and the shared launcher relays to the pinned Delta node. The installed-wheel smoke test starts outside the checkout, waits for readiness, invokes a harmless operating-system browser handler with the exact local URL, and serves six scenarios. The production-container smoke test separately covers `--no-browser --basic`. On 2026-09-02, a Delta lifecycle check passed doctor, deliberately restarted the managed launcher process, then passed status and readiness on the pinned node. A read-only 2026-09-04 check again passed doctor, status, both health endpoints, and public configuration without restarting the process. | Confirm the real default browser on the presentation laptop and the exact laptop `ssh delta-demo` tunnel in the consolidated hardware acceptance. |
| Durable public URL associated with ABDA-NL | The paper-facing iDAKS repository remains unchanged. A standalone operator-controlled repository now owns hosted-service development, CI, and the public image. `abda-nl.org` is active under operator control with authoritative Cloudflare DNS and DNSSEC. The application is live at `demo.abda-nl.org` with a valid Azure-managed certificate and successful external HTTPS checks. No CS hostname or institutional DNS dependency is used. The narrowly scoped Cloudflare redirect for the shorter apex and `www` addresses passed the public hostname gate, preserving paths and query strings without capturing `demo`, `login`, or `auth`. The GPL cumulative image passed its live pilot release and sanitized-log audit. | Complete. Do not repeat the verified DNS or redirect setup. |
| Professional verified-email accounts | Production accepts exact-issuer OIDC identities only when `email_verified` is Boolean true. Duplicate concurrent first-login callbacks converge on one account in real PostgreSQL testing, while different identities with one email remain blocked. Resend delivery from `auth.abda-nl.org`, the Auth0 custom domain `login.abda-nl.org`, SPF, DKIM, DMARC, support and privacy forwarding, attack protection, and administrator MFA are verified. Exact generated and custom origins are configured. Correct-OTP sign-in and complete browser sign-out passed at the custom origin, then passed again in a fresh private window against release-candidate revision `abda-nl-stg-web--rc-4485109`. Auth0 also rejected an intentionally incorrect OTP without creating an ABDA-NL session during Gate 8. Auth0's current Free plan includes Passwordless and one custom domain, so the login design does not depend on the temporary feature trial. Development login is visibly limited to non-production use. | On September 6 the operator confirmed Resend Free, accepted quota-related availability risk, and will monitor email volume and upgrade when necessary. This does not block 100-account promotion. Repeat browser identity checks only after an Auth0 or application identity change. |
| First 100 verified users receive $5 | Trial activation is explicit, idempotent per account, and transactionally capped at 100 grants, $5 each, and $500 total. Concurrent final-grant tests cover the race boundary. Reservations settle exact known usage, release only confirmed uncharged or pre-dispatch failures, charge an indeterminate in-process outcome immediately, and conservatively charge an expired unknown outcome after worker loss. These rules prevent either failure path from reopening the hard budget. A live ten-user, $50 pilot activated one account and reconciled one real request with no pending reservation. Gate 12 is a resume-safe three-setting promotion covered by focused state, accounting, mutation-boundary, and full-flow tests. | Complete the preceding release gates, then run Gate 12 to promote the live cap from 10 users and $50 to 100 users and $500. |
| CloudBank primary with temporary OpenRouter outage fallback | Balanced uses the validated CloudBank Sonnet route. Only transport, throttling, timeout, and provider 5xx outage classes can open the fallback circuit after bounded retries. Authentication, request, deployment, and validation failures cannot spend OpenRouter funds. Every physical call reserves and settles independently. Metered Anthropic routes disable hidden SDK retries, and validation failures retain any returned usage or provider cost. OpenRouter requests require both no data collection and Zero Data Retention. Gate 7 injected a qualifying CloudBank 503 and reached the live OpenRouter Gemini 3.7 Flash route. Its original 32-token marker assertion was incompatible with mandatory reasoning, so it stopped before printing its receipt and refused a blind retry. The read-only recovery gate then proved the same 149 microUSD settled cost in the trial and emergency ledgers, zero reservations, a restored disabled switch, no repeated provider call, and no Azure change. The corrected command now preserves accounting evidence before checking marker text. | Complete the preceding release gates, then enable public fallback only through Gate 12. |
| Owner exposure capped at $500 or explicitly $1,000 | The chosen production limit is $500. Values above $500 need an exact acknowledgement, and values above $1,000 are rejected. Metrics expose spent and reserved totals without user identifiers. Gate 9 reconciled the live trial and OpenRouter ledgers with zero unsafe log indicators. Gate 12 preserves the independent $500 hard limit and refuses non-idle or unreconciled accounting. | Preserve the verified boundary during Gate 12. |
| Registered-user BYOK with no usage quota | Anthropic, OpenAI, Google, and OpenRouter use fixed endpoints and model allowlists. Provider request IDs are separate from stable catalog IDs. Keys remain in tab memory and one request client, bypass trial charging, and are absent from storage, cookies, URLs, logs, projects, shares, MCP, and database records. Reload and sign-out clear the browser value. Managed Delta acceptance on 2026-08-17 produced successful direct Google and OpenRouter calls with unchanged trial state and no key in the response, database event, or managed log. A later OpenRouter Gemini 3.7 Flash request also succeeded after per-request ZDR enforcement, with no key in the response or managed log. OpenAI account quota returned a sanitized HTTP 429 and retry hint. The configured Anthropic account returned a sanitized billing rejection for the documented Sonnet 5 API ID. On 2026-09-02, the resume-safe public-origin Gate completed one real browser OpenRouter Gemini 3.7 Flash action, reload and sign-out clearing, zero BYOK trial charge, an unchanged emergency ledger, and zero key, email, or bearer log indicators. It independently reconciled 18,437 microUSD of concurrent trial usage to one separate CloudBank result instead of misattributing public traffic to BYOK. | Public OpenRouter BYOK is accepted for the managed-boundary image. Restore Anthropic account credit and OpenAI account quota before claiming successful direct calls for all four providers. |
| Private projects and research sharing | Projects are owner-scoped, versioned working baselines. Share tokens remain in URL fragments, resolve to read-only views, support validated private copies, and can be revoked. OIDC return paths discard fragments and shared-view login uses a separate tab, so a share bearer cannot enter a server-visible login URL. Cross-user and stale-version tests cover isolation. Gate 8 exercised a real Azure-backed project through creation, reload, a rejected stale-tab update, preserved version 2 state, an anonymous fragment-only read-only share, and revocation. The follow-up shared-view image removed an unnecessary signed-out Workspace dialog, and the operator confirmed the corrected behavior in a fresh private window. | Repeat after a project, sharing, session, or database migration change. |
| Codex and Claude Code access | Authenticated MCP uses one-time bearer credentials stored as keyed digests. Read, write, and model scopes are independent. Writes require the observed version, and proposals never apply themselves. Revocation, expiry, malformed tokens, and cross-user access are tested. On 2026-08-29, Codex CLI 0.150.1 and Claude Code 2.1.247 each completed a real `list_examples` call through the public HTTPS endpoint with one `projects:read` token. Both clients then lost access after browser revocation, with no private project tool, ABDA-NL model call, retained token, or retained transcript. The live scoped-write Gate independently rejected a read-only mutation, created and versioned one disposable project with the correct scope, rejected a stale update, recorded a funded CloudBank proposal without applying it, removed the project, and proved both temporary credentials were revoked. Credential creation remains throttled, while verified same-origin revocation is intentionally unthrottled so abuse protection cannot prevent emergency cleanup. The immutable unthrottled-revocation image passed public deployment acceptance, and a fresh browser credential disappeared immediately after revocation and Refresh without a rate-limit error. Source `1f576e71909114c1d94aabfcb167dfafc1a432e5` additionally gives all four deterministic MCP read tools one shared database-backed per-account limit across replicas, without limiting credential revocation. | Repeat the live gates only after an MCP authentication, scope, project, or routing change. |
| Security and abuse resistance | Production startup validates all trust boundaries. The app applies trusted hosts, same-origin mutation checks, secure session cookies, body limits, database-backed rate limits, safe errors, CSP and other headers, private database networking, and protected metrics. Deterministic reasoning budgets now bound premise matching, candidate products, argument count and representation size, attack inspection, and attack count, so one compact valid scenario cannot monopolize a worker through combinatorial expansion. Inputs over a boundary receive HTTP 422 `scenario_too_complex`; all six bundled canonical state payloads remain identical. Expired rate-limit rows are removed at startup and by a nonblocking hourly cleanup triggered by later limiter traffic. A cleanup failure is safely logged without exception text and cannot fail an already-accounted request. Managed staging and production deployments reject the local-only filesystem save API, and that endpoint has an independent same-origin browser boundary. Credential creation is throttled, while authenticated same-origin revocation remains available without a rate limit. The administrator database credential is confined to the migration job. Web replicas use a distinct role with no memberships. Its explicit table and sequence grants exclude role, database, schema, temporary-object, ownership, replication, and row-security bypass powers, and startup rejects an overprivileged login. Isolated PostgreSQL 16 acceptance exercises account, trial, project, share, rate-limit, usage-accounting, and MCP writes, then proves object and role creation are denied. The B1ms deployment caps three replicas at five connections each, and protected metrics expose pool occupancy. Provider connection pools are closed after owned API, MCP, evaluation, and outage-drill calls, including handled failures. Logs omit query strings, normalize route names, and no longer record user or model-generated object identifiers. Unexpected-error diagnostics omit exception messages and tracebacks, retaining only the exception class and internal code location. Assistant Markdown uses a restricted DOMPurify fragment sink without reparsing, and browser tests exercise active-content and context-switch payloads. Vendored asset provenance, hashes, and licenses are tracked. CI audits both native dependency lock sets with `pip-audit`. The production container now removes pip from both runtime interpreters. Checksum-pinned Trivy jobs scan the complete image, scan the Dockerfile, check embedded secrets without retaining the raw secret report, enforce an exact reviewed base-image vulnerability baseline, and retain a CycloneDX SBOM. The final source run reported 27 successful Dockerfile checks, zero configuration failures, zero secrets, zero actionable high or critical vulnerabilities, and zero unreviewed unfixed high or critical findings. A pinned Python CodeQL `security-extended` workflow also fails on any SARIF result. Its first development-branch scan exposed 15 findings, every finding was corrected without dismissal, and the enforced follow-up scan reported zero results across 50 rules. The service repository additionally enables GitHub secret scanning, push protection, vulnerability alerts, automated security updates, protected branches, required CI for `main`, and Private Vulnerability Reporting for the form documented in `SECURITY.md`. The real migration and restricted-role application deployment succeeded, the public custom origin passed external TLS, HTTPS redirect, policy-page, security-header, configuration-exposure, and metrics-authentication checks, and both live MCP acceptance gates passed. Gate 18 deployed the managed-boundary image and proved that a same-origin filesystem-save request is rejected without mutation while all settings, secrets, migrations, and other application contracts remain unchanged. The exact superseding source-hardening image then deployed as `abda-nl-stg-web--harden-51702e1` without changing the application contract. Its live Gate 9 audit passed the release checker and found zero query, email, bearer, share-fragment, OIDC-code, provider-key, or private-identifier indicators across 28,898 count-only log records. | Privacy recovery, exact Auth0 cleanup, and the GPL pilot rollout audit are complete. Obtain institutional privacy and terms review before describing the service as durable production. |
| Accessibility and user experience | Automated Chromium, Firefox, and Playwright WebKit journeys cover desktop, a 200 percent zoom-equivalent viewport, mobile reflow, keyboard dialogs, focus trapping, focus return, reduced motion, and WCAG A and AA scans. A production-only keyboard defect was reproduced: opening Research workspace while signed out could leave focus behind the dialog because the preferred development-login control was hidden. The modal now selects only visible enabled controls and falls back to the first visible dialog control. On 2026-09-02, the public Chromium and Firefox Gate passed against `abda-nl-stg-web--secure-b873112`. On 2026-09-04 CDT, it passed again immediately after the privacy wrapper verified the exact hardened revision and unchanged configuration. Each public engine completed six WCAG scans, three viewport checks, and three keyboard checks with no console or page errors. The first WebKit CI run then detected that the scrollable argument graph lacked a Safari keyboard focus target. Source `17ef6593de0bcb9fdc213915bda83e3cf38a03bd` adds a labeled focusable region and visible focus outline; its complete CI run passed Chromium, Firefox, and WebKit. Source `24abcf9576dc9033a902d27a8f9b6381fee85f4e` further gives filter groups programmatic pressed state, labels every explorer search and scrolling region, announces project context and unsaved changes, and makes all four layout dividers keyboard adjustable as named ARIA separators. Source `5819e8ffb291704e6ce299bda9136fff363aaddf` adds programmatic scope state, named zoom controls with live zoom status, and a concise text summary for the argument graph. Source `87ab9f42a15b2888837594c2b274622da4a27d40` keeps compact and ASPIC controls reachable on phones, widens the mobile ASPIC dialog, and reveals the stacked chat panel when an item question starts while respecting reduced motion. Its complete CI run passed Chromium, Firefox, and WebKit, and its matching CodeQL run passed with no open alerts. Playwright WebKit reduces Safari-engine risk but does not replace Safari on macOS. | Complete Safari, manual screen-reader, and actual 200 percent browser zoom checks on presentation hardware. |
| Observability, bounded capacity, and rollback | Liveness and readiness are distinct. Operator-managed startup refuses a database whose Alembic revision differs from the application image and warms each immutable example before the replica becomes ready. Metrics report low-cardinality HTTP, exact trial caps, both reservation ledgers, fallback-budget, and model-event state. The external release check rejects cap mismatches, inconsistent balances, and non-idle reservations. Azure retains logs for 30 days. Gate 9 verified the earlier release checker, reconciled both ledgers, and found zero sensitive indicators in 12,653 count-only log records. Gate 10 accepted the compatible rollback image and automatically restored the current image without rerunning migration or changing secrets or settings. The deployed alert layer combines Container Apps 5xx and replica alerts with a three-region standard readiness and TLS test of the real custom domain, all routed through one support action group. On 2026-09-02, Gate 14 verified all six resource contracts, Azure accepted a test notification, and that message reached the monitored support inbox. Gate 17 then exercised the managed-boundary revision with 123 public requests at concurrency 20. It recorded zero HTTP failures, zero response mismatches, post-burst readiness, scenario p95 of 306 ms, and state p95 of 763 ms, both well below the 6,000 ms threshold. On 2026-09-04 CDT, the same bounded smoke passed against the unchanged hardened service with scenario p95 of 276 ms and state p95 of 614 ms. This is a deterministic burst regression, not a claim that 100 users can call an LLM simultaneously. On 2026-09-04 UTC, Gate 9 revision 7 bound a new read-only audit to the exact hardened source, digest, and healthy revision. It passed the release checker, confirmed 30-day retention, checked the five-connection pool, reconciled live trial and emergency spend, and found zero sensitive indicators across 28,898 count-only records. The [PostgreSQL recovery runbook](database-recovery.md) now separates image rollback from seven-day point-in-time recovery, restores into a new private server, requires validation before a separate cutover, and forbids deletion as part of recovery. | Run compatible rollback and restoration for the hardened image, retain the final promoted release receipt, and complete the content-free recovery tabletop with a second team member. |
| Privacy access and deletion requests | The public policy routes requests through `privacy@abda-nl.org` and promises completion within 30 days. The operator CLI reads the verified email through a hidden prompt or secret-backed environment value, produces content-free inspection output, and writes access exports only to a new mode-600 file in a private directory. Permanent deletion is two-phase: preparation suspends the account and revokes share and MCP access, while deletion requires an exact second confirmation and refuses unsettled model reservations. Private records are removed, provider accounting is anonymized, and aggregate funded liability is retained. The tool is present in the deployed image. Gate 11 adds a two-run, 15-minute, disposable-account acceptance with exact confirmations and no Azure configuration change. Its embedded runner passed an end-to-end database test. On 2026-09-04 CDT, the live preparation execution succeeded, verified and removed its export, revoked share and MCP access, and proved the saved job and application configurations unchanged without terminal email input or a model call. The latest tested source additionally makes project, share, MCP credential, trial activation, and funded-credit reservation mutations lock and refresh the durable account row. Deterministic SQLite tests and the PostgreSQL 16 CI contract prove that suspension rejects every stale-session mutation, disables an existing share, and releases rejection locks. | The recovered deletion, historical database-destination review, and exact Auth0 cleanup are complete. The GPL cumulative image has passed its pilot audit and model smoke. Do not repeat the completed privacy workflow. |

## Model selection evidence

General popularity is only a discovery signal. Public routes must pass the
ABDA-specific suite for grounded answers, schema-valid proposals, semantic
review behavior, latency, cost, and complete provider-call accounting.

| Route | Current evidence | Decision |
| --- | --- | --- |
| CloudBank Claude Sonnet 4.6 | Current suite version 4 passed 48 of 48 cases, with 7,982 ms p95 wall time, zero provider or parser errors, and no OpenRouter spend. The raw artifact has SHA-256 `544f8017350244fe1d7d1d83de8840ac86c8303d4d47b441f6a6967bf99fcd7b`. | Balanced primary |
| OpenRouter Gemini 3.7 Flash | Current suite version 4 passed 48 of 48 cases under per-request ZDR and no-data-collection enforcement, with 10,621 ms p95 wall time, zero provider or parser errors, and 3,627 microUSD average owner-accounted cost per case. The raw artifact has SHA-256 `cb2f4f37a2897ad1fc65732897cf549090ed9ab893685ee82a0104b8fbc1a215`. | Balanced outage fallback |
| CloudBank GPT-5.4 mini | Complete evaluation passed 45 of 48. Repeated clean-review runs produced unnecessary warnings. | Economy remains hidden |
| OpenRouter Claude Sonnet 5 | Complete evaluation passed 45 of 48 because of repeated false-positive review warnings. Anthropic made its $2/$10 launch price the standard direct price. The route keeps a conservative $3/$15 ceiling. | Not promoted |
| New CloudBank Claude, GPT, DeepSeek, and Qwen candidates | Live project probes returned 404 for the configured candidate deployment names on 2026-08-17. A bounded 2026-09-04 refresh sent one isolated case to each of the same four names. All four again returned HTTP 404, recorded one failed call and zero cost, and had no OpenRouter fallback. Catalog visibility does not prove project deployment, and data-plane probes cannot discover a differently named deployment. The model-promotion runbook now includes a read-only Cloud Shell inventory that derives the account from the deployed endpoint and lists actual deployment names without reading a key or calling a model. | Run the read-only inventory. If a suitable deployment exists, configure its exact name and rerun the unchanged evaluation gate. |

The detailed routing decision and primary-source links are in
[ADR 0003](../decisions/0003-model-routing-and-cost-controls.md). Promotion
steps are in [the model runbook](model-promotion.md).

## Completed external checkpoint evidence

The initial personal-hosting checkpoint proves a successful tag-gated image
build, exact-digest registry smoke test, anonymous GHCR access, and GitHub
provenance for source commit `1217b3a`. It also records the clean separation
between the unchanged paper `main` and the standalone service repository. See
[the checkpoint record](personal-hosting-checkpoint.md) for exact CI, workflow,
digest, attestation, registry, and branch-protection evidence.

The 2026-08-29
[staging release-candidate checkpoint](staging-release-candidate-20260829.md)
records complete CI, image workflow, anonymous registry access, exact digest,
provenance, Azure deployment, fresh-browser sign-in and sign-out, and the
reconciled OpenRouter outage drill for source commit `4485109`. Remaining
authenticated workspace and operator checks stay separate. An earlier image
cannot establish a later release identity.

The dated
[external prerequisites checkpoint](external-prerequisites-20260828.md)
records the completed Azure provider, domain, incoming-mail, authentication
mail, Auth0, GitHub security, and public-package foundations without including
private destination addresses or credentials.

The dated
[staging deployment record](staging-deployment-record-20260828.md) binds the
verified application commit, complete CI, immutable public image, exact digest,
provenance, recovered Azure infrastructure, generated origin, Auth0 URLs, and
rollback candidate before the first application deployment.

The dated
[staging live acceptance record](staging-live-acceptance-20260828.md) records
the deployed custom origin, real verified-email session, funded pilot request,
reconciled accounting, public HTTPS checks, and Delta cross-login-node
contingency evidence.

The 2026-08-30
[consolidated release checkpoint](consolidated-release-acceptance-20260830.md)
binds the final focus and portable-launch fixes to one complete CI run, one
immutable image digest, and one GitHub provenance attestation. Its Azure image
deployment, public browser accessibility, release and log audit, six-resource
monitor deployment, and test-email delivery are now verified. Authenticated
Privacy, hardware, redirect, rollback, and budget-promotion evidence remain
explicitly separate.

The 2026-09-02 historical
[managed-boundary release record](managed-boundary-release-acceptance-20260902.md)
binds the capacity replacement to its exact source, immutable image, CI,
provenance, Azure revision, capacity receipt, public Chromium and Firefox
receipt, and BYOK receipt. Current operator work uses the later source-security
checkpoint below.

The later
[development source security checkpoint](source-security-checkpoint-20260902.md)
records the pinned CodeQL baseline, correction of all 15 findings without
dismissal, enforced zero-result SARIF check, clean dependency audits, immutable
image provenance, the exact image-only Azure deployment, and the subsequent
release and sanitized-log audit.

The 2026-09-04
[container security checkpoint](container-security-checkpoint-20260904.md)
records runtime pip removal, the exact base-image vulnerability baseline,
complete image and Dockerfile scanning, secret-scan isolation, a CycloneDX
SBOM, clean CodeQL and repository alert state, and the full CI matrix for the
latest code-changing source. This evidence is source and ephemeral-build
evidence only. The GPL distribution correction on September 5 resolves the
license-choice hold. Its subsequently published and verified image is recorded
in the [GPL checkpoint](gpl-distribution-checkpoint-20260905.md). Deployment
and pilot audit have since passed; see the
[live acceptance record](gpl-live-checkpoint-20260905.md).

The historical
[account-suspension integrity checkpoint](suspension-integrity-checkpoint-20260904.md)
binds periodic cleanup, provider-boundary hard-cap safeguards, billed-response
validation, deterministic client cleanup, and stale-session suspension safety
to complete CI, real restricted-role PostgreSQL coverage, browser checks,
CodeQL, an immutable image digest, and GitHub provenance. It superseded the
earlier provider-lifecycle, accounting, and retention images, but was itself
superseded before deployment when WebKit exposed a keyboard focus defect. A
replacement image must include source `17ef659` or later and use the license
disposition chosen through the source license review.

## Release evidence and remaining external acceptance

The following list distinguishes completed live evidence from the final human
batch in [the operator runbook](final-operator-batch.md):

1. The source license choice is resolved as GPL-3.0-only, with original MIT
   notices retained. See [the source license review](source-license-review.md).
   This does not retroactively change old artifacts or the paper branch.
2. Privacy recovery is complete: the historical destination and timing review
   supports the successful deletion, and the operator confirmed removal of the
   exact disposable Auth0 identity. Do not repeat the workflow.
3. The correctly licensed cumulative image and post-privacy Gate pins are
   [verified](gpl-distribution-checkpoint-20260905.md). Its live pilot audit,
   funded smoke, and public browser and capacity checks passed. Do not repeat
   this completed batch; continue with the remaining external gates below.
4. Root-domain redirect setup and the full public hostname gate are complete.
   No further operator DNS action or manual browser test is required.
5. Sender-plan decision closed on September 6: the operator confirmed Resend
   Free and accepted quota-related availability risk, monitoring volume and
   upgrading when needed. Pro is not a prerequisite for 100 trial accounts.
   See [the email operations decision](auth0-email-otp.md#capacity-before-general-registration).
6. The exact Azure Foundry deployment inventory was recorded on September 6.
   The four newer candidates are not deployed. Existing models remain subject
   to the quality gate; no guessed-name probe needs repeating.
7. Final-image rollback and restoration, public budget promotion, and the
   promoted-state release audit all passed on September 6. Independent external
   release, Chromium, Firefox, and capacity checks also passed. See
   [the exact release receipt](public-release-20260906.md).
8. The exact laptop `ssh delta-demo` browser path.
9. Safari, screen-reader, presentation display, conference network, and two
   complete rehearsal runs.
10. A two-person, content-free PostgreSQL recovery tabletop. It does not create
   a restored server or change Azure.
11. Institutional review of the public privacy and terms text before the
    service is described as a durable production research service.

These are explicit items in [the release checklist](release-checklist.md), not
implicit claims of completion. A release record must identify one Git commit
and one immutable image, then attach evidence from that same release.
