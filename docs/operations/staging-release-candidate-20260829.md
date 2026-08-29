# Staging release-candidate image checkpoint, 2026-08-29

State: immutable image published and verified, Azure deployment pending

This checkpoint identifies the first staging image that contains the privacy
operations command, the controlled OpenRouter outage drill, and the corrected
Codex and Claude Code MCP setup instructions. It does not claim that those
operator and authenticated-user paths have passed live Azure acceptance.

## Immutable identity

- Source commit:
  `448510936c69d485cf9b4e834adea69becf6b114`
- Annotated trigger tag:
  `service-image-staging-20260829-103102`
- Image:
  `ghcr.io/liu-hy/abda-nl@sha256:11861402c8fa3fd677848f94155e29065ebafd9a4a76b03e41b1cf48312e5c58`
- Complete CI run:
  `https://github.com/Liu-Hy/ABDA-NL/actions/runs/33260377139`
- Image workflow run:
  `https://github.com/Liu-Hy/ABDA-NL/actions/runs/33260469176`
- GitHub provenance attestation:
  `https://github.com/Liu-Hy/ABDA-NL/attestations/43861955`

The complete CI run passed all seven jobs, including Python 3.10 and 3.13,
native dependency audits, PostgreSQL restricted-role acceptance, deployment
artifact checks, container smoke tests, Chromium, and Firefox. The tag-triggered
image workflow repeated the non-browser suite and audits, pulled the exact
published digest, ran its container smoke test, and created GitHub provenance.

Local verification on 2026-08-29 established all of the following:

- GitHub attestation verification bound the image digest to the source commit,
  repository, workflow, and annotated tag.
- An anonymous GHCR manifest request returned HTTP 200 and the exact
  `Docker-Content-Digest` value.
- OCI labels identify the public repository, exact source commit, and MIT code
  license.
- The diff from the currently deployed application source
  `9abd0264c715596401d87b83d08ed2e82ab5e34b` contains no migration or database
  schema file change.

## Deployment boundary

`deploy/azure/gate6-release-candidate-image.sh` is the guarded transition from
the current `abda-nl-stg-web--trial-pilot-v1` revision to
`abda-nl-stg-web--rc-4485109`.

The gate accepts only the exact known pilot image or the exact target image. It
checks the Azure identity, anonymous image access, OCI provenance labels,
custom-domain certificate, ingress, health probes, scaling, full environment
variable inventory, secret references, public security headers, funded model
profile, BYOK catalog, database pool boundary, and both accounting ledgers.

Its only Azure write command changes:

- the `web` container image to the immutable digest above
- the revision suffix to `rc-4485109`

It does not rerun migrations or change secrets, Auth0, DNS, certificates,
trial limits, OpenRouter failover, scaling, probes, or database resources. It
supports safe resumption when Azure has already accepted the target image.

The previous compatible rollback image remains:

`ghcr.io/liu-hy/abda-nl@sha256:71f759c7bbfe25cc2ae974f006b8fed853ef87e5db260fc875fa3f50257739f9`

Do not perform a rollback merely because a postdeployment browser check fails.
First preserve the Gate 6 output and inspect the target revision and application
logs. The old revision remains the recorded recovery target.

## Gates after Azure deployment

The image is not a public release until the following release-candidate checks
are complete:

1. Gate 6 reports a healthy target revision and passes its public HTTPS and
   accounting checks.
2. Correct-OTP sign-in and complete sign-out pass in a fresh browser session.
3. The controlled OpenRouter outage drill calls the real reviewed fallback,
   settles the same positive cost in both ledgers, leaves no reservation, and
   restores its temporary database switch.
4. The privacy command is exercised against an isolated staging account without
   retaining private content in the acceptance record.
5. Private project, read-only share, MCP client, and disposable-BYOK journeys
   pass against the same image.
6. The authorized release check, Log Analytics inspection, and rollback
   rehearsal pass before any promotion from the ten-user pilot.
