# Account-suspension integrity checkpoint, 2026-09-04

State: historical candidate, built, tested, and attested, then superseded
before deployment

Source commit `084817fcefdcbee36e223ff6932d6c344618e1c3` retains the complete
provider lifecycle, conservative accounting, and rate-limit retention work,
then closes a race at the account-suspension boundary.

A request can authenticate immediately before a privacy operator suspends its
account. SQLAlchemy sessions deliberately retain loaded values after a commit,
so a long-lived request could otherwise hold an outdated active `User` object.
Project creation and updates, project archival, share creation, MCP credential
creation, and trial activation now lock and refresh the durable user row before
changing state. They reject an account that is no longer active and release the
transaction lock before returning the rejection. Public share resolution also
requires an active project owner. Consequently, suspension wins before any new
durable mutation that has not already obtained the user lock. The existing
15-minute deletion hold remains the boundary for a provider call that was
already in flight.

## Verification evidence

Four deterministic stale-session regressions cover project updates, share
creation and resolution, MCP credential creation, and trial activation. The
PostgreSQL 16 acceptance performs the same sequence through independently
cached sessions and the restricted application role. It also proves that each
rejection releases its row lock, so a later rejected session does not wait
behind it.

The complete local suite passed with 758 tests and five intentional skips.
Ruff and focused security lint passed. The complete seven-job
[CI run 33854320982](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33854320982)
passed on Python 3.10 and 3.13, Chromium, Firefox, PostgreSQL 16, deployment
artifacts, dependency audits, and the complete-history secret scan. The
[CodeQL run 33854321016](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33854321016)
also passed.

The annotated tag
`service-image-staging-suspension-integrity-20260904-083939` identifies the exact
source commit. [Image workflow run 33854509626](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33854509626)
reran release checks, built the production image, pulled and smoke-tested its
exact digest, and published GitHub build provenance.

- image: `ghcr.io/liu-hy/abda-nl@sha256:ef13b298df3eea1f1a52cd6f546d1c3f81cbc67cf73486b916bb2938f48b56b3`
- attestation: [45200764](https://github.com/Liu-Hy/ABDA-NL/attestations/45200764)
- OCI source: `https://github.com/Liu-Hy/ABDA-NL`
- OCI revision: `084817fcefdcbee36e223ff6932d6c344618e1c3`
- OCI license: `MIT`

The OCI license line records the immutable label already present on this image.
It is not evidence that the label covers the imported engine. Do not declare
this artifact's source release complete until the separate
[source license review](source-license-review.md) is resolved.

An independent anonymous registry request accepted the exact manifest and
configuration. The configuration contains the expected source, revision, and
license labels. An independent GitHub attestation verification accepted the
SLSA provenance subject `ghcr.io/liu-hy/abda-nl` at the exact image digest.

## Deployment boundary

This image was never deployed. The prepared disposable-account privacy Gate is
bound to the current hardened image and may finish there. A later WebKit Gate
found that the argument graph lacked a Safari keyboard focus target. Source
`17ef6593de0bcb9fdc213915bda83e3cf38a03bd` corrects that defect and passed the
complete Chromium, Firefox, and WebKit CI matrix. Consequently, Gate 20 must
not deploy this older image.

A replacement image and Gate chain must include the WebKit correction. They
remain unpublished while the separate source license review determines which
license label and notices can accurately cover the imported engine. The old
digest and attestation above remain immutable historical evidence.

Later source commit `333f730af91df6e61ff49781f1931b75e10251cb` closes one
additional stale-session path before any replacement image is published. A
funded-credit reservation now locks the existing trial grant and then refreshes
and locks its durable user row before creating new liability. This matches the
privacy-deletion order of trial grant before user, so it does not invert the
row-lock order. An inactive or unverified account is rejected before provider
dispatch. Focused SQLite tests first reproduced the missing check, then passed
after the fix. The restricted-role PostgreSQL 16 acceptance now exercises the
same stale reservation path in CI. This paragraph is source evidence only, not
a deployment or image record.

For a replacement image, the post-deployment funded smoke and read-only audit
cover the managed provider and complete public release contract. The exact
historical image already passed the
stale-session boundary against PostgreSQL 16, so this internal serialization
change does not require an additional disposable browser account. Gate 22
rehearses a compatible rollback to the current hardened image and restores this
image automatically. Gate 23 may promote the restored image from the ten-user
pilot to the reviewed 100-user limits and enable the independently capped
outage fallback only after the remaining external prerequisites are complete.
