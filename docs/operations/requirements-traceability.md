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
| Durable public URL associated with ABDA-NL and iDAKS | The Azure runbook and templates use a generated Container Apps origin first, then an operator-owned ABDA-NL domain managed through Cloudflare DNS. No CS hostname or institutional DNS dependency is proposed. | Acquire the domain, create direct DNS-only validation records, issue the managed certificate, and run external HTTPS checks. |
| Professional verified-email accounts | Production accepts exact-issuer OIDC identities only when `email_verified` is Boolean true. Duplicate concurrent first-login callbacks converge on one account in real PostgreSQL testing, while different identities with one email remain blocked. The Auth0 runbook uses hosted email OTP and an external email provider. Development login is visibly limited to non-production use. | Create the Auth0 application and email connection, test real delivery, and verify valid and invalid OTP behavior at the public origin. |
| First 100 verified users receive $5 | Trial activation is explicit, idempotent per account, and transactionally capped at 100 grants, $5 each, and $500 total. Concurrent final-grant tests cover the race boundary. Reservations settle exact known usage, release confirmed uncharged failures, and conservatively charge an expired unknown outcome so a worker loss cannot reopen either hard budget. | Validate the migrated PostgreSQL deployment and activate one real staging account. |
| CloudBank primary with temporary OpenRouter outage fallback | Balanced uses the validated CloudBank Sonnet route. Only transport, throttling, timeout, and provider 5xx outage classes can open the fallback circuit after bounded retries. Authentication, request, deployment, and validation failures cannot spend OpenRouter funds. Every physical call reserves and settles independently. OpenRouter requests require both no data collection and Zero Data Retention. | Force one qualifying outage in staging and inspect both ledgers. Confirm the live OpenRouter account limit agrees with the configured cap. |
| Owner exposure capped at $500 or explicitly $1,000 | The emergency ledger defaults to $500. A higher value needs an exact acknowledgement and values above $1,000 are rejected. Metrics expose spent and reserved totals without user identifiers. | Record the chosen production cap and reconcile the live account before opening registration. |
| Registered-user BYOK with no usage quota | Anthropic, OpenAI, Google, and OpenRouter use fixed endpoints and model allowlists. Provider request IDs are separate from stable catalog IDs. Keys remain in tab memory and one request client, bypass trial charging, and are absent from storage, cookies, URLs, logs, projects, shares, MCP, and database records. Reload and sign-out clear the browser value. Managed Delta acceptance on 2026-08-17 produced successful direct Google and OpenRouter calls with unchanged trial state and no key in the response, database event, or managed log. A later OpenRouter Gemini 3.7 Flash request also succeeded after per-request ZDR enforcement, with no key in the response or managed log. OpenAI account quota returned a sanitized HTTP 429 and retry hint. The configured Anthropic account returned a sanitized billing rejection for the documented Sonnet 5 API ID. | Repeat with disposable keys at the staged public origin. Restore Anthropic account credit and OpenAI account quota before claiming successful direct calls for all four providers. |
| Private projects and research sharing | Projects are owner-scoped, versioned working baselines. Share tokens remain in URL fragments, resolve to read-only views, support validated private copies, and can be revoked. OIDC return paths discard fragments and shared-view login uses a separate tab, so a share bearer cannot enter a server-visible login URL. Cross-user and stale-version tests cover isolation. | Complete the same journey against production PostgreSQL and a private browser window. |
| Codex and Claude Code access | Authenticated MCP uses one-time bearer credentials stored as keyed digests. Read, write, and model scopes are independent. Writes require the observed version, and proposals never apply themselves. Revocation, expiry, malformed tokens, and cross-user access are tested. | Exercise one Codex and one Claude Code client against the final HTTPS MCP endpoint. |
| Security and abuse resistance | Production startup validates all trust boundaries. The app applies trusted hosts, same-origin mutation checks, secure session cookies, body limits, database-backed rate limits, safe errors, CSP and other headers, private database networking, and protected metrics. The administrator database credential is confined to the migration job. Web replicas use a distinct role with no memberships. Its explicit table and sequence grants exclude role, database, schema, temporary-object, ownership, replication, and row-security bypass powers, and startup rejects an overprivileged login. Isolated PostgreSQL 16 acceptance exercises account, trial, project, share, rate-limit, usage-accounting, and MCP writes, then proves object and role creation are denied. The B1ms deployment caps three replicas at five connections each, and protected metrics expose pool occupancy. Logs omit query strings and normalize route names. Assistant Markdown uses a restricted DOMPurify fragment sink without reparsing, and browser tests exercise active-content and context-switch payloads. Vendored asset provenance, hashes, and licenses are tracked. CI audits both native dependency lock sets with `pip-audit`. | Repeat the PostgreSQL journey on Azure, run the external header checks, inspect Log Analytics, and complete institutional privacy and terms review. |
| Accessibility and user experience | Automated Chromium and Firefox journeys cover desktop, a 200 percent zoom-equivalent viewport, mobile reflow, keyboard dialogs, focus return, reduced motion, and WCAG A and AA scans. | Complete Safari, manual screen-reader, and actual 200 percent browser zoom checks on presentation hardware. |
| Observability and rollback | Liveness and readiness are distinct. Operator-managed startup refuses a database whose Alembic revision differs from the application image. Metrics report low-cardinality HTTP, exact trial caps, both reservation ledgers, fallback-budget, and model-event state. The external release check rejects cap mismatches, inconsistent balances, and non-idle reservations. Azure retains logs for 30 days. The runbook deploys only smoke-tested and attested GHCR digest URIs and documents digest rollback. | Prove public telemetry ingestion, alert ownership, a migration execution, and one rollback rehearsal. |

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

## Release-only evidence still required

The repository is not sufficient evidence for these items:

1. A successful tag-gated GHCR build, exact-digest smoke test, public anonymous
   pull, and GitHub provenance attestation.
2. A successful migration job and public Container Apps revision using private
   PostgreSQL.
3. Auth0 email delivery, exact callbacks, and verified-email acceptance at the
   final origin.
4. Cloudflare DNS and Azure certificate validation for the operator-owned
   ABDA-NL hostname.
5. External health, policy, security-header, metrics, and sanitized-log checks.
6. The exact laptop `ssh delta-demo` browser path.
7. Safari, screen-reader, presentation display, conference network, and two
   complete rehearsal runs.

These are explicit items in [the release checklist](release-checklist.md), not
implicit claims of completion. A release record must identify one Git commit
and one immutable image, then attach evidence from that same release.
