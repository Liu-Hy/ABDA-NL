# GPL pilot live acceptance, September 5, 2026

Status: GPL cumulative image live; operator model smoke and pilot audit
accepted. Automated public Chromium, Firefox, and bounded capacity checks
passed afterward. This is not the 100-user promotion or final public release.

## Deployed identity and operator evidence

- Application source: `ed241c1509739f16b2433ced686da76fe1ed1d94`.
- Image: `ghcr.io/liu-hy/abda-nl@sha256:b7025d4322e05a698e79eb120a233c68cf638d5cdd44c8f58223681ff15ae1c5`.
- Azure revision: `abda-nl-stg-web--gpl-ed241c1`.
- Public origin: `https://demo.abda-nl.org`.
- Audit revision: `gpl-6`, stage `suspension-pilot`, exit code 0.
- Audit result: `SERVICE_INTEGRITY_RELEASE_AND_OBSERVABILITY_AUDIT_VERIFIED`.
- Browser funded request: the operator confirmed that the answer was normal.

The operator supplied the completed audit, which validates the deployed
identity and pilot configuration. The image-update receipt was not included
in this handoff. Do not describe the audit's `azure_configuration_changed:
false` as an independent before-and-after proof of the preceding deployment.
The audit itself changed no Azure configuration and called no model provider.

The audited pilot remains ten users, with a $5 grant per user and $50 total.
Public OpenRouter failover remains disabled. The protected counters were:

| Counter | Value |
| --- | --- |
| Trial activations | 1 |
| Allocated trial credit, microUSD | 5,000,000 |
| Cumulative trial spend, microUSD | 447,085 |
| Cumulative emergency OpenRouter spend, microUSD | 149 |
| Database connections checked out | 1 |

These are cumulative counters, not the cost of the latest browser request.
The release checker passed. The workspace retains logs for 30 days. The audit
counted 28,745 log records, including 28,616 console records, 129 system
records, 101 current-revision records, and 77 current-revision request records.
All seven reported sensitive-pattern counters were zero. This is a bounded
pattern scan, not a proof that every possible secret format can be detected.
No raw log message or secret value was printed.

## Independent automated public checks

After the operator receipt, the existing public-browser gate ran against the
live origin. Each of Chromium and Firefox completed six WCAG A and AA scans,
three viewport checks, and three keyboard checks. Both had zero console and
page errors. Reduced motion and policy links before registration passed.
The result was `LIVE_PUBLIC_CHROMIUM_FIREFOX_ACCESSIBILITY_VERIFIED`.

The bounded capacity gate completed 123 requests, with at most 20 concurrent
connections, zero HTTP failures, and zero response mismatches:

| Endpoint phase | Measured requests | p50, ms | p95, ms | Maximum, ms |
| --- | --- | --- | --- | --- |
| Readiness | 40 | 598 | 913 | 919 |
| Bundled scenario | 40 | 210 | 290 | 331 |
| Deterministic state | 40 | 464 | 727 | 734 |

The result was `LIVE_PUBLIC_BOUNDED_CAPACITY_SMOKE_VERIFIED`. Neither gate
signed in, called a model, created a project, or changed Azure configuration.
The state requests can create an automatically expiring rate-limit counter.

An additional live WebKit attempt could not launch because Delta lacks its
required system libraries. It did not reach the application. No system
package was installed and no host configuration was changed. The successful
source-image WebKit CI evidence in the [distribution checkpoint](gpl-distribution-checkpoint-20260905.md)
remains separate from a live WebKit pass. Safari and screen-reader acceptance
on the presentation hardware are still pending.

## Remaining operator boundaries

At the initial pilot checkpoint, the hostname gate reported no apex A record.
The operator subsequently saved the Cloudflare records and corrected redirect
condition. The unchanged gate then returned
`PUBLIC_HOSTNAME_AND_EMAIL_DNS_BOUNDARY_VERIFIED`, exit code 0, through normal
DNS resolution. The full receipt is in the [hostname record](cloudflare-apex-redirect.md).
Do not repeat this completed setup.

Establish sufficient transactional-email capacity before the 100-user
promotion. The existing revision 7 post-privacy
helper remains current; its scripts and hashes have not changed. Follow
Sections 4 and 5 of the [operator batch](final-operator-batch.md). The final
image rollback, restoration, promotion, and promoted-state audit remain
unperformed. Preserve the ten-user pilot until their prerequisites are met.

Privacy recovery and exact disposable Auth0 cleanup are complete. Do not
repeat them, re-create their objects, or repeat BYOK and MCP acceptance merely
to obtain a new receipt. No stable `main` branch or runtime source was changed
while recording this checkpoint.
