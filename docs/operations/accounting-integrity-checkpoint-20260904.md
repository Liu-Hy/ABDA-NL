# Provider accounting integrity checkpoint, 2026-09-04

State: historical candidate, built, tested, and attested, then superseded
before deployment

This checkpoint supersedes the earlier queued retention-only image. Source
commit `050ce2cda65838b4c875079239e91f5161a4bbbe` includes that retention work and
closes additional hard-cap accounting gaps at the provider boundary.

Metered Anthropic routes now disable SDK-managed retries so every physical
provider attempt remains visible to ABDA-NL's reservation ledger. A provider
failure that proves the request was not dispatched or charged releases its
reservation. A response with reliable usage or cost settles that evidence. If
a request may have started but returns no reliable billing result, the service
settles the full conservative reservation rather than reopening spend capacity.
Tool-response validation failures retain any returned usage evidence. The public
terms describe this conservative case.

## Verification evidence

The complete local suite passed with 742 tests and five intentional skips.
Chromium and Firefox each passed the four browser journeys. Ruff, focused
security lint, both locked dependency audits, and the SQLite migration parity
check passed.

The complete seven-job
[CI run 33848402688](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33848402688)
passed on Python 3.10 and 3.13, Chromium, Firefox, PostgreSQL 16, deployment
artifacts, dependency audits, and the complete-history secret scan. The
[CodeQL run 33848402677](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33848402677)
also passed.

The annotated tag
`service-image-staging-accounting-integrity-20260904-072417` identifies the
exact source commit. [Image workflow run 33848576342](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33848576342)
reran its release checks, built the production image, pulled and smoke-tested
the exact digest, and published GitHub build provenance.

- image: `ghcr.io/liu-hy/abda-nl@sha256:2ff479555d21a5ea44506e6d74a080551ddfc0fa4f5122cf7cc96f1e26afb50d`
- attestation: [45187780](https://github.com/Liu-Hy/ABDA-NL/attestations/45187780)
- OCI source: `https://github.com/Liu-Hy/ABDA-NL`
- OCI revision: `050ce2cda65838b4c875079239e91f5161a4bbbe`
- OCI license: `MIT`

An independent GitHub attestation check accepted the SLSA provenance subject
`ghcr.io/liu-hy/abda-nl` at the exact digest above.

This image was subsequently superseded before deployment by the
[provider lifecycle checkpoint](provider-lifecycle-checkpoint-20260904.md),
which retains all accounting and retention work from this checkpoint.

## Deployment boundary

This image was never deployed and must not be used as the current Gate 20
target. It was superseded by the later provider lifecycle and
account-suspension candidates recorded in this directory.

Gate 20 requires the retention and conservative billing disclosures, rechecks
the shared-view fix, and proves that the managed filesystem save endpoint
remains rejected without mutation. Gate 21 binds the resulting Azure revision
to this source and digest through a read-only release and sanitized-log audit.
Gate 22 rehearses a compatible rollback to the prior hardened image and restores
this image automatically. Gate 23 then promotes the restored image from the
ten-user pilot to the reviewed 100-user limits and enables the independently
capped outage fallback.
