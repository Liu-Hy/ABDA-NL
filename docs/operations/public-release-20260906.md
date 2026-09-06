# Public research service release, September 6, 2026

Status: public trial limits and outage fallback are live. Compatible image
rollback and restoration, the promoted release audit, an independent external
release check, public browser accessibility, and bounded capacity checks passed.
Presentation-hardware acceptance remains separate.

## Release identity

- Public origin: `https://demo.abda-nl.org`.
- Application source: `ed241c1509739f16b2433ced686da76fe1ed1d94`.
- Image: `ghcr.io/liu-hy/abda-nl@sha256:b7025d4322e05a698e79eb120a233c68cf638d5cdd44c8f58223681ff15ae1c5`.
- Active revision: `abda-nl-stg-web--public-100-ed241c1`.
- Resource group: `abda-nl-staging`.
- Application and revision health: Succeeded, Running, Provisioned, Healthy.
- Source, complete CI, image publication, GPL notices, and provenance:
  [distribution checkpoint](gpl-distribution-checkpoint-20260905.md).

The operator completed the private Delta Azure login. The agent verified that
the account matched the approved subscription, tenant, and user, then read
live Azure state before changing it. The initial revision was the expected GPL
pilot, with no active resource-group deployment or migration job execution.
No new role, service principal, or identity grant was created.

## Completed live transitions

The locally checked-in Gates matched their previously reviewed SHA-256 pins.
The agent supplied the existing confirmation phrases for the already approved
operations; the operator did not need to relay commands or receipts.

1. Gate 22 (`gpl-6`) deployed the compatible prior image from source
   `51702e175bd14d4cb54075808f839d173d561324` as
   `abda-nl-stg-web--rollback-51702e1`, accepted its health and public contract,
   and restored the exact GPL image as `abda-nl-stg-web--restore-ed241c1`.
   Only the image and revision suffix changed. Exit code 0 and
   `COMPATIBLE_SERVICE_IMAGE_ROLLBACK_AND_RESTORE_VERIFIED` were observed.
2. Gate 23 (`gpl-6`, using the shared Gate 12 implementation) changed only the
   three approved public settings and revision suffix. Exit code 0 and
   `PUBLIC_BUDGETS_AND_OUTAGE_FALLBACK_PROMOTED` were observed. Image, secrets,
   database resources, migrations, Auth0, DNS, and certificates were unchanged.
3. Gate 21 (`gpl-6`, `--public`, using the shared Gate 9 implementation) ran the
   read-only promoted-state audit. The deployed image's release checker passed
   at `2026-09-06T18:28:41.324316+00:00`. Exit code 0 and
   `FINAL_PUBLIC_RELEASE_AND_OBSERVABILITY_AUDIT_VERIFIED` were observed.

The rollback was completed and restored in this run, not inferred only from
a revision name. Do not rerun the pilot-bound rollback or promotion scripts
against the public revision merely to obtain another success receipt.

## Budget and account preservation

| Setting or counter | Verified value |
| --- | --- |
| Trial activation | Enabled |
| Maximum cumulative trial activations | 100 |
| Grant per account | $5 |
| Total trial cap | $500 |
| OpenRouter outage fallback | Enabled |
| Independent OpenRouter emergency cap | $500 |
| Existing activations | 1 |
| Allocated trial credit, microUSD | 5,000,000 |
| Cumulative trial spend, microUSD | 447,085 |
| Cumulative emergency OpenRouter spend, microUSD | 149 |
| Trial and emergency reservations | 0 each |
| Uncertain charged reservations and costs | 0 each |

Before-and-after accounting totals matched exactly. The existing account was
not given another grant. No model provider was called during this batch.
OpenRouter remains an outage route, not a replacement for CloudBank or an
alternative triggered by a deployment-name, authentication, or validation error.
User-provided keys remain separate from these owner-funded ledgers.
The caps cover requests admitted by ABDA-NL, not unrelated use of the same
provider account or key by another application.

## Release, logs, and infrastructure checks

Both the deployed checker and the same unchanged checker run externally from
Delta passed HTTPS certificate, insecure-HTTP redirect, liveness, readiness,
public configuration, security headers, policy pages, metrics authentication,
budgets, and database-pool checks. The external result was
`EXTERNAL_PUBLIC_RELEASE_CHECK_VERIFIED` at
`2026-09-06T18:29:20.649606+00:00`. Its metrics credential was loaded directly
into private process memory, never printed or placed in command arguments.

The 48-hour Log Analytics query returned only aggregate counts:

| Log counter | Value |
| --- | --- |
| Total records | 29,134 |
| Console records | 28,955 |
| System records | 179 |
| Current-revision records | 134 |
| Current-revision request records | 123 |
| Request records across revisions | 28,873 |
| Query, email, bearer, share-fragment, OIDC-code, provider-key indicators | 0 each |
| Current-revision private-identifier field indicators | 0 |

This is a bounded pattern scan, not proof that every possible secret format
can be detected. Raw application logs and secret values were not printed.
Log retention is 30 days. The application pool reported one connection checked
out of a capacity of five.

Independent Azure reads confirmed PostgreSQL 16 is Ready, public network access
is Disabled, and backup retention is seven days. High availability is Disabled,
as designed for this deployment. All three configured metric alerts are enabled,
evaluate every minute, and point to `abda-nl-stg-operators`. Their previously
verified inbox delivery was not redundantly retested. No restored database,
monitor resource, or additional cloud infrastructure was created.

A separate count-only query of the
[Application Insights availability-results table](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/appavailabilityresults)
confirmed the scheduled tests are actually running, not merely configured.
Over the preceding 24 hours, East US, North Central US, and West Europe each
recorded 288 samples with zero failures, 864 successful samples in total.
Their respective p95 durations were 284, 359, and 556 ms. Latest samples were
between `2026-09-06T18:28:18Z` and `2026-09-06T18:29:50Z`.
Result: `THREE_REGION_AVAILABILITY_ACTIVITY_VERIFIED`. No raw message,
instrumentation key, client IP address, or user identity was retrieved.

## Browser and bounded capacity acceptance

The public-origin gate passed in Chromium and Firefox. Each completed six
WCAG A and AA scans, three viewport checks, and three keyboard checks, with
zero console or page errors. Reduced motion and pre-registration policy links
passed. Result: `LIVE_PUBLIC_CHROMIUM_FIREFOX_ACCESSIBILITY_VERIFIED`.

The public capacity smoke completed 123 requests, including 120 measured
requests at a maximum concurrency of 20, with zero failures or mismatches:

| Phase | Requests | p50, ms | p95, ms | Maximum, ms |
| --- | --- | --- | --- | --- |
| Readiness | 40 | 594 | 911 | 915 |
| Bundled scenario | 40 | 200 | 276 | 277 |
| Deterministic state | 40 | 417 | 671 | 681 |

Result: `LIVE_PUBLIC_BOUNDED_CAPACITY_SMOKE_VERIFIED`. These checks did not
sign in, create a project, or call a model. State requests may create an
automatically expiring rate-limit counter. This is a bounded deterministic
burst test, not a claim of 100 simultaneous LLM users.

## Requirements and remaining acceptance

`Requirements.docx` and `camera-ready.pdf` retain their recorded hashes and
remain untracked. Live remote checks found both repositories' `main` branches
unchanged at `e4be41c72f34dd555147a2de221d84b3fd735c9f`.

The [actual Foundry deployment inventory](model-promotion.md#verified-deployment-inventory-on-2026-09-06)
is now recorded. The four previously probed newer candidates are absent from
that account. Existing catalog entries and other deployed models are not
automatically promoted without passing the ABDA quality evaluation.

Earlier accepted verified-email, private-project, sharing, BYOK, and real-client
MCP tests remain relevant because this batch changed none of their application
code or identity configuration. They were not repeated with new disposable
accounts or tokens. Successful direct Anthropic and OpenAI BYOK calls still
depend on usable credit or quota in the corresponding test accounts; their
failure handling and public OpenRouter BYOK are separately tested.

The final human batch is actual presentation-laptop Safari, real zoom and
screen-reader checks, local browser launch and the laptop Delta tunnel, and
the narrated rehearsal. The two-person recovery tabletop and any required
institutional policy review remain external operational work. None requires
another routine Cloud Shell deployment batch or a new paid email subscription.
Do not claim these human or organizational checks have passed automatically.

## Repository checkpoint verification

The eight-job [CI run for the Azure login handoff](https://github.com/Liu-Hy/ABDA-NL/actions/runs/34045729231)
and its [CodeQL run](https://github.com/Liu-Hy/ABDA-NL/actions/runs/34045729254)
passed for source `21e36608f75c4aaa6c54040d18859a1bc9c13aaf` before this live
batch. After documenting the results, 39 focused login-helper, release-chain,
rollback, promotion, and audit tests passed. Full CI then caught one outdated
documentation assertion requiring the old manual-only entrypoint wording.
The test now requires the current release, authorized handoff, historical
runbook, and valid links while retaining the warning against replaying old
commands. The expanded focused suite passed 55 tests; Ruff and whitespace
checks passed. Application source and gate pins were not edited during this
release batch.
