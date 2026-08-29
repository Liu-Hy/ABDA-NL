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
| Preserve unlimited use for researchers who bring their own keys. | BYOK supports fixed Anthropic, OpenAI, Google, and OpenRouter endpoints and allowlisted models. A key exists only in tab memory and one request client, and MCP deliberately does not accept provider keys. | This preserves unlimited self-funded use without creating a credential vault, arbitrary proxy, or agent-transcript secret path. |
| Organize collaboration cleanly while keeping current and improved demos runnable. | The paper repository and personal service repository have separate responsibilities. One application entrypoint serves local, Delta, and managed modes, while immutable image digests identify public releases. | Administrative control is available now, Shawn's history and the stable paper demo remain intact, and later organization promotion remains possible. |

Private projects, read-only sharing, abuse controls, accessibility gates,
observability, privacy operations, and rollback procedures are deliberate
service requirements added during planning. They support a durable public
research service and do not alter the paper's deterministic ABDA authority.

## Camera-ready feature claims

| Published claim | Implementation and evidence | State |
| --- | --- | --- |
| Web explorer with conclusions, facts and assumptions, rules, and chat | The primary page retains the four-panel explorer. The real-browser test requires populated conclusions, facts, rules, and at least six scenarios. | Implemented and browser-tested |
| Natural-language glossary over an ASPIC- knowledge base | Scenario YAML contains proposition descriptions. Serialization renders them while the ABDA bridge remains the source of arguments, attacks, and grounded labels. Engine, loader, serialization, and integration tests cover this boundary. | Implemented and deterministic |
| Corpus-grounded general and item-focused chat | Chat prompts receive only the selected immutable corpus and current deterministic state. Citation validation rejects invented files and retries once. The question-mark controls issue focused questions and remain keyboard operable. | Implemented, live model routes evaluated |
| Interactive Explain discussion game | Explain exposes argument selection, support expansion, attacks, preferences, moves, and resolution. The Chromium and Firefox journeys enter it by keyboard and run WCAG A and AA scans on the picker and tree. | Implemented and browser-tested |
| Suspend rules or assumptions and modify preferences | State changes are represented as validated diff operations. The browser previews suspension impact before applying it. Conflict and grounded-engine tests cover preference changes and recomputation. | Implemented and deterministic |
| Author rules, facts, and assumptions in natural language | The model proposes schema-constrained operations. Deterministic validation can block them, semantic review is advisory, and the user must apply an accepted proposal. The browser test opens and closes the edit dialog by keyboard. | Implemented, model quality-gated |
| ABDA remains authoritative after every change | `/state` and project working-state routes rebuild the framework and grounded labels from the validated scenario. No model response can set a conclusion label. | Implemented and tested |
| Graph view, raw ASPIC- view, saving, and multiple examples | The browser journey opens both views. Private projects provide durable public saving, while local filesystem saving remains a development feature. Six bundled examples are included in the source tree, container, and installed wheel. | Implemented and browser-tested |

## Expanded research-service requirements

| Requirement | Implementation and evidence | Remaining release gate |
| --- | --- | --- |
| Ordinary local launch and Delta `demo` compatibility | One `abda-nl` entrypoint defaults to loopback, waits for readiness, and opens the local browser. `--no-browser` supports managed runs. `.demo.json` retains `{host}` and `{port}`, uses the foreground command, and the shared launcher relays to the pinned Delta node. The installed-wheel smoke test starts outside the checkout and serves six scenarios. | Confirm the default browser opens on the presentation laptop. Confirm the exact laptop `ssh delta-demo` tunnel reaches the running Delta app. |
| Durable public URL associated with ABDA-NL | The paper-facing iDAKS repository remains unchanged. A standalone operator-controlled repository now owns hosted-service development, CI, and the public image. `abda-nl.org` is active under operator control with authoritative Cloudflare DNS and DNSSEC. The application is live at `demo.abda-nl.org` with a valid Azure-managed certificate and successful external HTTPS checks. No CS hostname or institutional DNS dependency is used. | Repeat the external checks for the final immutable release candidate. |
| Professional verified-email accounts | Production accepts exact-issuer OIDC identities only when `email_verified` is Boolean true. Duplicate concurrent first-login callbacks converge on one account in real PostgreSQL testing, while different identities with one email remain blocked. Resend delivery from `auth.abda-nl.org`, the Auth0 custom domain `login.abda-nl.org`, SPF, DKIM, DMARC, support and privacy forwarding, attack protection, and administrator MFA are verified. Exact generated and custom origins are configured. Correct-OTP sign-in and complete browser sign-out passed at the custom origin, then passed again in a fresh private window against release-candidate revision `abda-nl-stg-web--rc-4485109`. Auth0 also rejected an intentionally incorrect OTP without creating an ABDA-NL session during Gate 8. Development login is visibly limited to non-production use. | Repeat the browser identity checks only after an Auth0 or application identity change. |
| First 100 verified users receive $5 | Trial activation is explicit, idempotent per account, and transactionally capped at 100 grants, $5 each, and $500 total. Concurrent final-grant tests cover the race boundary. Reservations settle exact known usage, release confirmed uncharged failures, and conservatively charge an expired unknown outcome so a worker loss cannot reopen either hard budget. A live ten-user, $50 pilot activated one account and reconciled one real request with no pending reservation. Gate 12 is a resume-safe three-setting promotion covered by focused state, accounting, mutation-boundary, and full-flow tests. | Complete the preceding release gates, then run Gate 12 to promote the live cap from 10 users and $50 to 100 users and $500. |
| CloudBank primary with temporary OpenRouter outage fallback | Balanced uses the validated CloudBank Sonnet route. Only transport, throttling, timeout, and provider 5xx outage classes can open the fallback circuit after bounded retries. Authentication, request, deployment, and validation failures cannot spend OpenRouter funds. Every physical call reserves and settles independently. OpenRouter requests require both no data collection and Zero Data Retention. Gate 7 injected a qualifying CloudBank 503 and reached the live OpenRouter Gemini 3.7 Flash route. Its original 32-token marker assertion was incompatible with mandatory reasoning, so it stopped before printing its receipt and refused a blind retry. The read-only recovery gate then proved the same 149 microUSD settled cost in the trial and emergency ledgers, zero reservations, a restored disabled switch, no repeated provider call, and no Azure change. The corrected command now preserves accounting evidence before checking marker text. | Complete the preceding release gates, then enable public fallback only through Gate 12. |
| Owner exposure capped at $500 or explicitly $1,000 | The chosen production limit is $500. Values above $500 need an exact acknowledgement, and values above $1,000 are rejected. Metrics expose spent and reserved totals without user identifiers. Gate 12 preserves the independent $500 hard limit and refuses non-idle or unreconciled accounting. | Reconcile the live account in Gate 9, then preserve this boundary during Gate 12. |
| Registered-user BYOK with no usage quota | Anthropic, OpenAI, Google, and OpenRouter use fixed endpoints and model allowlists. Provider request IDs are separate from stable catalog IDs. Keys remain in tab memory and one request client, bypass trial charging, and are absent from storage, cookies, URLs, logs, projects, shares, MCP, and database records. Reload and sign-out clear the browser value. Managed Delta acceptance on 2026-08-17 produced successful direct Google and OpenRouter calls with unchanged trial state and no key in the response, database event, or managed log. A later OpenRouter Gemini 3.7 Flash request also succeeded after per-request ZDR enforcement, with no key in the response or managed log. OpenAI account quota returned a sanitized HTTP 429 and retry hint. The configured Anthropic account returned a sanitized billing rejection for the documented Sonnet 5 API ID. | Repeat with disposable keys at the staged public origin. Restore Anthropic account credit and OpenAI account quota before claiming successful direct calls for all four providers. |
| Private projects and research sharing | Projects are owner-scoped, versioned working baselines. Share tokens remain in URL fragments, resolve to read-only views, support validated private copies, and can be revoked. OIDC return paths discard fragments and shared-view login uses a separate tab, so a share bearer cannot enter a server-visible login URL. Cross-user and stale-version tests cover isolation. Gate 8 exercised a real Azure-backed project through creation, reload, a rejected stale-tab update, preserved version 2 state, an anonymous fragment-only read-only share, and revocation. The follow-up shared-view image removed an unnecessary signed-out Workspace dialog, and the operator confirmed the corrected behavior in a fresh private window. | Repeat after a project, sharing, session, or database migration change. |
| Codex and Claude Code access | Authenticated MCP uses one-time bearer credentials stored as keyed digests. Read, write, and model scopes are independent. Writes require the observed version, and proposals never apply themselves. Revocation, expiry, malformed tokens, and cross-user access are tested. | Exercise one Codex and one Claude Code client against the final HTTPS MCP endpoint. |
| Security and abuse resistance | Production startup validates all trust boundaries. The app applies trusted hosts, same-origin mutation checks, secure session cookies, body limits, database-backed rate limits, safe errors, CSP and other headers, private database networking, and protected metrics. The administrator database credential is confined to the migration job. Web replicas use a distinct role with no memberships. Its explicit table and sequence grants exclude role, database, schema, temporary-object, ownership, replication, and row-security bypass powers, and startup rejects an overprivileged login. Isolated PostgreSQL 16 acceptance exercises account, trial, project, share, rate-limit, usage-accounting, and MCP writes, then proves object and role creation are denied. The B1ms deployment caps three replicas at five connections each, and protected metrics expose pool occupancy. Logs omit query strings and normalize route names. Assistant Markdown uses a restricted DOMPurify fragment sink without reparsing, and browser tests exercise active-content and context-switch payloads. Vendored asset provenance, hashes, and licenses are tracked. CI audits both native dependency lock sets with `pip-audit`. The service repository additionally enables GitHub secret scanning, push protection, vulnerability alerts, automated security updates, protected branches, and required CI for `main`. The real migration and restricted-role application deployment succeeded, and the public custom origin passed external TLS, HTTPS redirect, policy-page, security-header, configuration-exposure, and metrics-authentication checks. | Exercise the remaining authenticated write paths on Azure, inspect Log Analytics, and complete institutional privacy and terms review. |
| Accessibility and user experience | Automated Chromium and Firefox journeys cover desktop, a 200 percent zoom-equivalent viewport, mobile reflow, keyboard dialogs, focus return, reduced motion, and WCAG A and AA scans. Both engines also scanned the real custom origin at desktop, zoom-equivalent, and mobile dimensions with zero anonymous-view violations, zero horizontal overflow, and no console or page errors. | Complete Safari, manual screen-reader, and actual 200 percent browser zoom checks on presentation hardware. |
| Observability and rollback | Liveness and readiness are distinct. Operator-managed startup refuses a database whose Alembic revision differs from the application image. Metrics report low-cardinality HTTP, exact trial caps, both reservation ledgers, fallback-budget, and model-event state. The external release check rejects cap mismatches, inconsistent balances, and non-idle reservations. Azure retains logs for 30 days. The runbook deploys only smoke-tested and attested GHCR digest URIs and documents digest rollback. The live migration succeeded, both health endpoints pass, metrics authentication is enforced, and the Gate 5 accounting audit reconciled the active trial ledger. Read-only Gate 9 and reversible image-only Gate 10 are pinned to the current deployment and covered by focused contract tests. | Run Gate 9 to inspect Log Analytics and the authorized release check, then run Gate 10 to rehearse the compatible rollback and automatic restoration. |
| Privacy access and deletion requests | The public policy routes requests through `privacy@abda-nl.org` and promises completion within 30 days. The operator CLI reads the verified email through a hidden prompt or secret-backed environment value, produces content-free inspection output, and writes access exports only to a new mode-600 file in a private directory. Permanent deletion is two-phase: preparation suspends the account and revokes share and MCP access, while deletion requires an exact second confirmation and refuses unsettled model reservations. Private records are removed, provider accounting is anonymized, and aggregate funded liability is retained. The tool is present in the deployed image. Gate 11 adds a two-run, 15-minute, disposable-account acceptance with exact confirmations and no Azure configuration change. Its embedded runner passed an end-to-end database test. | Run Gate 11 after Gate 10, retain only its content-free receipt, then delete the blocked disposable Auth0 identity. |

## Model selection evidence

General popularity is only a discovery signal. Public routes must pass the
ABDA-specific suite for grounded answers, schema-valid proposals, semantic
review behavior, latency, cost, and complete provider-call accounting.

| Route | Current evidence | Decision |
| --- | --- | --- |
| CloudBank Claude Sonnet 4.6 | Current suite version 4 passed 48 of 48 cases, with 7,982 ms p95 wall time, zero provider or parser errors, and no OpenRouter spend. The raw artifact has SHA-256 `544f8017350244fe1d7d1d83de8840ac86c8303d4d47b441f6a6967bf99fcd7b`. | Balanced primary |
| OpenRouter Gemini 3.7 Flash | Current suite version 4 passed 48 of 48 cases under per-request ZDR and no-data-collection enforcement, with 10,621 ms p95 wall time, zero provider or parser errors, and 3,627 microUSD average owner-accounted cost per case. The raw artifact has SHA-256 `cb2f4f37a2897ad1fc65732897cf549090ed9ab893685ee82a0104b8fbc1a215`. | Balanced outage fallback |
| CloudBank GPT-5.4 mini | Complete evaluation passed 45 of 48. Repeated clean-review runs produced unnecessary warnings. | Economy remains hidden |
| OpenRouter Claude Sonnet 5 | Complete evaluation passed 45 of 48 because of repeated false-positive review warnings. Its current $2/$10 direct price is introductory through 2026-08-31, while the route ceiling uses standard $3/$15 pricing. | Not promoted |
| New CloudBank Claude, GPT, DeepSeek, and Qwen candidates | Live project probes returned 404 for the configured candidate deployment names. Catalog visibility does not prove project deployment. | Await a real CloudBank deployment, then rerun the unchanged gate |

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

## Release-only evidence still required

The repository is not sufficient evidence for these remaining items:

1. Live Codex and Claude Code MCP clients, plus disposable BYOK calls at the
   public origin.
2. Privacy-command operation against an isolated staging account.
3. Authorized release-check output, sanitized Log Analytics evidence, alert
   ownership, and one rollback rehearsal.
4. The exact laptop `ssh delta-demo` browser path.
5. Safari, screen-reader, presentation display, conference network, and two
   complete rehearsal runs.

These are explicit items in [the release checklist](release-checklist.md), not
implicit claims of completion. A release record must identify one Git commit
and one immutable image, then attach evidence from that same release.
