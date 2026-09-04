# Provider lifecycle checkpoint, 2026-09-04

State: built, tested, and attested, then superseded before deployment

This checkpoint supersedes the queued provider-accounting image before either
image was deployed. Source commit
`e09fb727da2c34f78f97f28f8591f2b5cc33eeb1` retains the rate-limit retention
and conservative accounting work, then closes two additional long-running
service gaps.

Managed and BYOK routes create provider clients for individual application
requests. Those clients and their connection pools are now closed after API,
MCP, evaluation, and outage-drill calls, including handled failures. The one
cached local-demo client is preserved during requests and closed at application
shutdown. Cleanup failures cannot replace a completed model result, and their
diagnostics contain only class names.

Provider adapters now reject empty billed output and malformed forced-tool
responses while retaining available usage or provider cost for settlement.
OpenAI structured refusals remain visible as valid provider answers. A Gemini
content-policy block is treated as a nonretryable request rejection instead of
an outage, so it neither repeats the request nor opens the public fallback
circuit. The accounting-unavailable message no longer promises that a request
was free when its final settlement cannot be confirmed.

## Verification evidence

The complete local suite passed with 754 tests and five intentional skips.
Ruff, focused security lint, and both hash-locked dependency audits passed. One
isolated CloudBank Claude Sonnet 4.6 evaluation case then passed through the
real provider with one successful physical call. It used a temporary SQLite
database and did not use the public trial or OpenRouter emergency budget.

The complete seven-job
[CI run 33850630821](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33850630821)
passed on Python 3.10 and 3.13, Chromium, Firefox, PostgreSQL 16, deployment
artifacts, dependency audits, and the complete-history secret scan. The
[CodeQL run 33850630892](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33850630892)
also passed.

The annotated tag
`service-image-staging-provider-lifecycle-20260904-075321` identifies the exact
source commit. [Image workflow run 33850802706](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33850802706)
reran release checks, built the production image, pulled and smoke-tested its
exact digest, and published GitHub build provenance.

- image: `ghcr.io/liu-hy/abda-nl@sha256:0a33ffa9dac2e5bf6a69855140698c086bced30c12c780318759c5a375307d49`
- attestation: [45192912](https://github.com/Liu-Hy/ABDA-NL/attestations/45192912)
- OCI source: `https://github.com/Liu-Hy/ABDA-NL`
- OCI revision: `e09fb727da2c34f78f97f28f8591f2b5cc33eeb1`
- OCI license: `MIT`

An independent GitHub attestation verification accepted the SLSA provenance
subject `ghcr.io/liu-hy/abda-nl` at the exact digest above.

## Deployment boundary

This image is not yet deployed. The prepared disposable-account privacy Gate is
bound to the current hardened image and must finish first. After permanent
deletion succeeds and the disposable Auth0 identity is removed, Gate 20 may
replace only the web image and revision suffix. It does not rerun migrations or
change secrets, Auth0, DNS, certificates, trial limits, provider routing,
scaling, probes, or database resources.

Because this checkpoint changes provider response handling and resource
lifetime, the operator will make one short funded request after the image-only
deployment. The existing account balance and the following read-only audit
provide live accounting evidence. No repeat BYOK, MCP, privacy, accessibility,
or capacity journey is required because those contracts and user interactions
are unchanged.

Gate 21 binds the resulting Azure revision to this source and digest. Gate 22
rehearses a compatible rollback to the prior hardened image and restores this
image automatically. Gate 23 may then promote the restored image from the
ten-user pilot to the reviewed 100-user limits and enable the independently
capped outage fallback, but only after its external email-capacity prerequisite
is met.

This image was subsequently superseded before deployment by the
[account-suspension integrity checkpoint](suspension-integrity-checkpoint-20260904.md),
which retains all provider lifecycle, accounting, and retention work from this
checkpoint.
