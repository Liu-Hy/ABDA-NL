# Staging live acceptance record

Date: 2026-08-28

State: `GATE5_TRIAL_ACCOUNTING_VERIFIED`

This record summarizes live evidence collected after the initial Azure
infrastructure and application deployment records. It contains no credentials,
share tokens, MCP tokens, session values, or private email addresses.

## Live release identity

- Public origin: `https://demo.abda-nl.org`
- Application source commit:
  `9abd0264c715596401d87b83d08ed2e82ab5e34b`
- Image digest:
  `sha256:71f759c7bbfe25cc2ae974f006b8fed853ef87e5db260fc875fa3f50257739f9`
- Healthy Container Apps revision: `abda-nl-stg-web--trial-pilot-v1`
- Resource group: `abda-nl-staging`
- Trial gate evidence commit:
  `d0a1ec016e271ae93ca376458c01dfeb7575a6a6`
- Trial gate CI:
  `https://github.com/Liu-Hy/ABDA-NL/actions/runs/33234355947`

The CI run completed all seven jobs, including both supported Python versions,
Chromium and Firefox accessibility journeys, PostgreSQL acceptance, production
container smoke testing, deployment artifact validation, and full-history
secret scanning.

## Public HTTPS and policy boundary

A read-only external check against the custom origin established:

- `/health/live` returned HTTP 200 and `{"status":"ok"}`
- `/health/ready` returned HTTP 200 and `{"status":"ready"}`
- `/`, `/privacy.html`, `/terms.html`, and `/config` returned HTTP 200
- plaintext HTTP returned 301 to the same HTTPS origin
- TLS 1.3 certificate validation succeeded for `demo.abda-nl.org`
- the certificate reported an expiry date of 2027-02-28
- CSP, HSTS, content-type protection, referrer policy, permissions policy, and
  frame protection headers were present
- unauthenticated `/internal/metrics` returned HTTP 401 with a Bearer challenge
- public configuration exposed the `balanced` funded profile and the four
  supported BYOK providers without exposing credentials or a private provider
  endpoint
- public configuration reported that BYOK is enabled and keys are not stored

The complete authorized metrics and accounting boundary was checked separately
by the guarded Gate 5 script.

## Live anonymous browser and MCP boundary

Headless Chromium and Firefox exercised the real custom origin at desktop,
720 by 450 as the repository's 200 percent zoom equivalent, and 390 by 844
mobile dimensions. WCAG 2 A, AA, 2.1 A, AA, and 2.2 AA scans reported zero
violations for the explorer and signed-out Workspace dialog in both engines.
Both narrow layouts had zero horizontal overflow, and neither engine reported a
console or page error.

Unauthenticated GET and POST requests to `/mcp/` returned HTTP 401 with a
Bearer challenge and `Cache-Control: no-store`. Malformed bearer and Basic
credentials received the same rejection. The service returned HTTP 404 for
OAuth protected-resource and authorization-server metadata, which is correct
because this release uses scoped personal MCP tokens and does not claim to
operate an OAuth authorization server.

## Identity and funded trial

The operator completed a real verified-email sign-in and complete sign-out at
the custom origin. A verified account then activated the funded pilot and made
one successful CloudBank-funded model request. The browser displayed $4.98
remaining. The protected ledger reported:

```text
trial_activations: 1
trial_allocated_microusd: 5000000
trial_spent_microusd: 22387
trial_reserved_microusd: 0
openrouter_enabled: 0
ledger_state: used
result: TRIAL_PILOT_ACCOUNTING_VERIFIED
```

The exact settled cost was $0.022387. The pilot remains limited to ten users,
$5 per user, and $50 total. OpenRouter outage fallback remains disabled.

## Delta contingency path

The tracked `.demo.json` retains the foreground command with `{host}` and
`{port}`, uses `/health/ready`, and has a 30-second startup timeout. On the
pinned `dt-login03` node:

- `demo doctor` reported the expected repository, fixed port 8765, and pinned
  node
- `demo status` reported the managed process running
- the process listened only on `127.0.0.1:8765`
- the local liveness and readiness endpoints returned their expected success
  bodies
- `/config` reported LLM support enabled with the `balanced` route

A separate read-only command executed from `dt-login02` and automatically
relayed `demo status` to `dt-login03`, proving the cross-login-node launcher
path. The remaining hardware-dependent check is an ordinary laptop
`ssh delta-demo` session reaching the bookmarked loopback URL.

## Remaining live acceptance

The next evidence must cover:

1. private project persistence, read-only sharing, and share revocation in a
   real authenticated and private-browser journey
2. scoped MCP use and revocation from real Codex and Claude Code clients
3. disposable BYOK calls and secret absence checks at the public origin
4. a controlled qualifying CloudBank outage that reaches OpenRouter and
   reconciles both ledgers
5. full authorized release-check output, Log Analytics review, and one rollback
   rehearsal
6. laptop tunnel, Safari, manual keyboard, screen-reader, actual browser
   200 percent zoom, and conference rehearsal evidence

Production expansion from the ten-user pilot to the planned first 100 users is
a separate promotion after the pilot evidence and budget controls are reviewed.
