# Managed-boundary release acceptance, 2026-09-02

State: historical managed-boundary checkpoint, superseded by the source-security
release candidate

For current operator steps, use
[the source-security checkpoint](source-security-checkpoint-20260902.md) and
[the final operator batch](final-operator-batch.md). This record is retained as
evidence for the image that completed capacity, accessibility, and BYOK
acceptance.

This record binds every remaining public-service acceptance result to one
application artifact. Historical evidence remains useful for unchanged
infrastructure and external integrations, but it does not prove the behavior
of this replacement image.

## Immutable application identity

- source commit: `b873112040dbfe645683d1b5e7d9adb122173ed2`
- source tag: `service-image-staging-managed-boundary-20260902-170432`
- complete source CI run: [33656551816](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33656551816)
- image workflow run: [33658830308](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33658830308)
- image: `ghcr.io/liu-hy/abda-nl@sha256:567ec34602e1b5ab1e1a9b01864f2a67219910dc3080300bc108eb33d569856c`
- provenance attestation: [44771024](https://github.com/Liu-Hy/ABDA-NL/attestations/44771024)
- deployed Azure revision: `abda-nl-stg-web--secure-b873112`
- public origin: `https://demo.abda-nl.org`

The image workflow reran the complete test suite and dependency audits, built
the production image, pulled and smoke-tested the exact pushed digest, and
published GitHub build provenance. The seven-job source CI matrix covered
Python 3.10 and 3.13, Chromium and Firefox, PostgreSQL 16, deployment artifacts,
and complete-history secret scanning.

The operator Gate bundle checkpoint is commit `fc7e768`. Its changes do not
alter the immutable application image. Complete CI run
[33660132569](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33660132569)
covered that bundle and runbook, with all seven jobs successful.

The later evidence-only checkpoint is commit `1fb674c`, with complete CI run
[33661284038](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33661284038).
All seven jobs passed again. A read-only GitHub API check on 2026-09-02 also
confirmed that the personal service repository remained public, used `main`
as its default branch, enforced the seven required CI checks on an up-to-date
branch even for administrators, and kept secret scanning, push protection,
Dependabot security updates, and vulnerability alerts enabled. The open
Dependabot-alert and secret-scanning-alert sets were both empty. The GitHub
attestation verifier accepted the exact deployed digest against
`Liu-Hy/ABDA-NL`.

A separate read-only remote check confirmed that both `idaks/ABDA-NL:main`
and `Liu-Hy/ABDA-NL:main` still point to paper-demo commit `e4be41c`, whose
[iDAKS CI run 32413305836](https://github.com/idaks/ABDA-NL/actions/runs/32413305836)
passed. Hosted-service work remains confined to the personal repository's
`development` branch. This preserves the reviewed paper artifact while the
service release proceeds independently.

## Replacement purpose

The prior candidate allowed the local filesystem scenario-save route whenever
the environment name was not exactly `production`. Azure intentionally uses
`staging`, so a same-origin anonymous request could reach an ephemeral
filesystem write path. The replacement makes managed-service status explicit
for both staging and production, rejects that route before a write, and retains
local scenario saving for ordinary development use.

The replacement also precompiles and caches deep-copyable state for all
immutable bundled examples during managed startup. This addresses the prior
public capacity observation in which deterministic scenario computation
exceeded the release latency threshold under a 20-connection burst. The ABDA
engine remains authoritative, and every request receives an isolated copy.

## Evidence already accepted

The following evidence remains applicable because the replacement does not
change its corresponding infrastructure or application contract:

- Auth0 verified-email OTP, custom-domain login, complete logout, invalid-OTP
  rejection, attack protection, and administrator MFA
- Resend SPF, DKIM, and DMARC delivery from the dedicated authentication
  subdomain
- the ten-user, $50 funded pilot and reconciled CloudBank usage
- the controlled OpenRouter outage drill and reconciled emergency ledger
- Azure private PostgreSQL, restricted application role, seven-day backup, and
  migration ordering
- private-project isolation, optimistic versions, fragment-only sharing, and
  anonymous read-only views
- live Codex and Claude Code MCP reads, scoped writes, non-applying proposals,
  and immediate credential revocation
- six Azure Monitor resources, three-region readiness monitoring, and delivery
  of the test alert through `support@abda-nl.org`
- 30-day Log Analytics retention and the prior count-only sensitive-pattern
  audit

These results are historical supporting evidence. The replacement must also
pass the remaining image-sensitive checks below before public promotion.

## Replacement image evidence

Gate 18 revision 1 completed the exact image-only transition from
`abda-nl-stg-web--release-3faf6eb` to
`abda-nl-stg-web--secure-b873112`. It verified the source label and digest,
healthy revision, public HTTPS contract, protected metrics boundary, retained
shared-view fix, and managed filesystem-save rejection. Its receipt recorded
that migrations did not rerun, secrets did not change, trial users remained at
10, public OpenRouter fallback remained disabled, and only the image and
revision suffix changed:

```text
result: MANAGED_BOUNDARY_IMAGE_DEPLOYED_CAPACITY_SMOKE_REQUIRED
```

Gate 17 revision 1 then completed its bounded public burst:

| Phase | Requests | p50 | p95 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| Readiness | 40 | 677 ms | 1,032 ms | 1,073 ms |
| Bundled scenario | 40 | 211 ms | 306 ms | 317 ms |
| Deterministic state | 40 | 500 ms | 763 ms | 773 ms |

All 123 requests, including the three baselines, completed with zero HTTP
failures and zero response mismatches at concurrency 20. Readiness remained
healthy after the burst. The requests were anonymous, made no model call, and
changed no Azure configuration:

```text
result: LIVE_PUBLIC_BOUNDED_CAPACITY_SMOKE_VERIFIED
```

Gate 13 revision 2 then passed against the same public origin. Chromium and
Firefox each completed six WCAG A and AA scans, three viewport checks, and
three keyboard checks. Both reported zero console and page errors. Reduced
motion and privacy and terms links before registration also passed:

```text
result: LIVE_PUBLIC_CHROMIUM_FIREFOX_ACCESSIBILITY_VERIFIED
```

Gate 10 revision 5 then resumed the already completed browser checks without
making another model request. It confirmed one OpenRouter Gemini 3.7 Flash
BYOK action, key clearing after reload, and key clearing after sign-out and
sign-in. The audit found three model events in the bounded window: two BYOK
result logs and one separate CloudBank-funded result. The funded result cost
was 18,437 microUSD, exactly matching the trial-spend increase. BYOK therefore
charged zero trial credit, while the independently capped emergency OpenRouter
ledger remained unchanged at 149 microUSD. Count-only logs found zero provider
key, API-key field, email, bearer, or other secret indicators. No Azure
configuration changed:

```text
result: LIVE_BYOK_PRIVACY_AND_ACCOUNTING_ACCEPTANCE_VERIFIED
```

The original revision 4 Gate rejected any global trial-spend change. That
assumption was unsuitable for a public multi-user service because an unrelated
funded request can settle during the same observation window. Revision 5
retains the strict BYOK and emergency-ledger boundaries, but accepts concurrent
trial usage only when separate CloudBank result logs explain the exact cost.

## Ordered remaining acceptance

1. Gate 9 repeats external HTTPS, protected-metrics, accounting, 30-day log
   retention, and count-only sensitive-pattern checks against the replacement.
2. Gate 11 exports and deletes one blocked disposable account after the bounded
   waiting period.
3. Gate 16 verifies the separately configured apex and `www` redirect without
   capturing the `demo`, `login`, or `auth` hostnames.
4. The compatible rollback rehearsal changes only the image, accepts the prior
   candidate, and restores this candidate automatically.
5. After outbound email capacity is confirmed, Gate 12 promotes the trial to
   100 users and $500 total while enabling the separately capped $500
   OpenRouter outage route.
6. The final Gate 9 audit verifies the exact promoted revision, caps, idle
   reservations, public endpoints, protected metrics, and sanitized logs.

The current commands and confirmation boundaries are in
[the final operator batch](final-operator-batch.md). A result is complete only
when its explicit content-free receipt is recorded here.

## Conference-only acceptance

The actual presentation laptop remains necessary for Safari, a screen reader,
actual 200 percent browser zoom, automatic local browser opening, and the
`ssh delta-demo` tunnel. Two complete presentation rehearsals, a funded
presenter account, and the presenter/operator role split remain conference
readiness gates rather than application deployment gates.

## Historical stop boundary

At this checkpoint, the next step was the read-only pilot Gate 9 audit. That
sequence has since been replaced by the source-security image deployment and
audit in the final operator batch. BYOK remains complete and must not be
repeated solely because of the logging-only source-security change.
