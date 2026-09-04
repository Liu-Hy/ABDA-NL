# Rate-limit retention maintenance checkpoint, 2026-09-04

State: built, tested, attested, and queued after privacy acceptance

This checkpoint closes one durable-service retention gap. Expired rate-limit
rows already stopped affecting a request when their fixed window ended, but a
long-lived replica physically removed them only during startup. Source commit
`db216b83d8df6b2ea487cd8358f05e81e65f8be9` adds a nonblocking cleanup that
later rate-limited traffic may trigger at most once per process each hour.
Cleanup failure cannot fail an already-accounted request, and its diagnostic
omits exception messages and tracebacks.

## Verification evidence

The complete local suite passed with 710 tests and five intentional skips.
The focused security lint passed. The complete seven-job
[CI run 33842325418](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33842325418)
then passed on Python 3.10 and 3.13, Chromium, Firefox, PostgreSQL 16,
deployment artifacts, dependency audits, and complete-history secret scans.
Its real PostgreSQL test exercises the restricted application role, removes an
expired bucket, and preserves the current bucket. The enforced
[CodeQL run 33842325417](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33842325417)
also passed.

The annotated tag
`service-image-staging-rate-limit-retention-20260904-005804` identifies the
exact source commit. [Image workflow run 33842462133](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33842462133)
reran tests and dependency audits, built the production image, pulled and
smoke-tested its exact digest, and published GitHub build provenance.

- image: `ghcr.io/liu-hy/abda-nl@sha256:614cd03d6f87b46e056d6dd736c060b8b652ae024334f9f0bb4eb50d750deac2`
- attestation: [45173216](https://github.com/Liu-Hy/ABDA-NL/attestations/45173216)
- OCI source: `https://github.com/Liu-Hy/ABDA-NL`
- OCI revision: `db216b83d8df6b2ea487cd8358f05e81e65f8be9`
- OCI license: `MIT`

An independent GitHub attestation check accepted the SLSA provenance subject
`ghcr.io/liu-hy/abda-nl` at the exact digest above.

## Deployment boundary

This image is not yet deployed. The existing disposable-account privacy Gate
is bound to the current hardened image and must finish first. After permanent
deletion succeeds and the disposable Auth0 identity is removed, Gate 20 may
replace only the web image and revision suffix. It does not rerun migrations
or change secrets, Auth0, DNS, certificates, trial limits, provider routing,
scaling, probes, or database resources.

The Gate uses one confirmation phrase that explicitly records the completed
privacy-deletion prerequisite. It cancels without changing Azure if the exact
phrase is absent.

The Gate requires the exact new privacy disclosure, rechecks the prior shared
view fix, and proves that the managed filesystem save endpoint remains rejected
without mutation. A separate read-only audit must bind the resulting Azure
revision to this source and digest before the image becomes the release
candidate. Gate 21 supplies that exact audit for both the ten-user pilot and
the later 100-user public configuration without changing Azure or calling a
model provider. Gate 22 rehearses a compatible rollback to the prior hardened
image and restores this image automatically. Gate 23 then reuses the reviewed
promotion logic with the restored retention revision and preserves the
independent $50 trial pilot, $500 public trial cap, and $500 emergency
OpenRouter cap boundaries.
