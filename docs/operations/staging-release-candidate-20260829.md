# Staging release-candidate image checkpoint, 2026-08-29

State: historical release-candidate evidence, superseded by the
[source-security checkpoint](source-security-checkpoint-20260902.md) and
[current operator sequence](final-operator-batch.md)

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

## Live Azure deployment record

Gate 6 completed with shell exit code 0 on 2026-08-29. Azure replaced
`abda-nl-stg-web--trial-pilot-v1` with
`abda-nl-stg-web--rc-4485109`, using the exact source commit and image digest
listed above. The gate reported all of the following:

- public acceptance passed at `https://demo.abda-nl.org`
- the funded pilot remained limited to 10 users and $50 total allocation
- public OpenRouter failover remained disabled
- no migration was rerun
- no application secret changed

This record establishes the deployed machine identity and public HTTP contract.
A fresh private-browser sign-in and complete sign-out both passed against this
exact revision on 2026-08-29. The operator-only outage drill then reached the
reviewed OpenRouter route after an injected CloudBank 503. Its recovery audit
proved the same 149 microUSD settled cost in both ledgers, zero reservations,
and restoration of the disabled public fallback state without a repeated
provider call or Azure change.

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

The immediate compatible rollback image for the current shared-view image is:

`ghcr.io/liu-hy/abda-nl@sha256:11861402c8fa3fd677848f94155e29065ebafd9a4a76b03e41b1cf48312e5c58`

It comes from source commit
`448510936c69d485cf9b4e834adea69becf6b114`, uses the same database schema and
application settings, and differs from the current image only by the later
shared-view correction and release evidence. Gate 10 pins both digests,
temporarily deploys this image, accepts it, and automatically restores the
current image. Do not substitute another digest in Cloud Shell.

## Gate 8 authenticated and shared-view checkpoint

The operator completed the invalid-OTP, private-project, stale-tab conflict,
reload, read-only sharing, and share-revocation journeys against the live Azure
service. One usability defect remained: a disabled shared-view chat action also
opened the signed-out Research workspace dialog.

The correction in source commit
`6d0fb4403c01b37d101f0d03bd9c3070b8f1e343` was published and deployed as:

`ghcr.io/liu-hy/abda-nl@sha256:282a2cb13cbdabe7f60a7efaa41c5fded7b1a4efeb467cc758064c7cadf30f13`

The healthy current revision is `abda-nl-stg-web--ux-6d0fb44`. The operator
retested the affected action in a fresh private browser window and confirmed
that it now shows the read-only notice without opening the Workspace dialog.

The first Gate 8 postdeployment check returned HTTP 404 only because it used
the nonexistent `/static/workspace.js` path. The application serves that asset
at `/workspace.js`. Commit `0120874e08cb72ee8cc24f14f2203fdec93c80fd`
corrected the verifier, its seven CI jobs passed, and the corrected live checks
passed without another Azure mutation. The complete content-free evidence is in
`docs/operations/staging-gate8-authenticated-acceptance-20260829.md`.

## Gates after Azure deployment

The image is not a public release until the following release-candidate checks
are complete:

1. Gate 6 reported a healthy target revision and passed its public HTTPS and
   accounting checks.
2. Correct-OTP sign-in and complete sign-out passed in a fresh browser session.
3. The controlled OpenRouter outage drill called the real reviewed fallback,
   settled 149 microUSD in both ledgers, left no reservation, and restored its
   temporary database switch.
4. Gate 8 authenticated project, conflict, share, revocation, and corrected
   shared-view behavior passed in real browser sessions.
5. The privacy command must be exercised against an isolated staging account
   without retaining private content in the acceptance record.
6. MCP client and disposable-BYOK journeys must pass against the same image.
7. The authorized release check, Log Analytics inspection, and rollback
   rehearsal passed before any promotion from the ten-user pilot.

Gate 9 revision 2 completed against the shared-view image. Its direct Azure
Logs API query counted 12,653 records over 48 hours, including 1,310 from the
current revision and 11,830 normalized request records. Every email, bearer,
share-fragment, OIDC-code, provider-key, and request-query indicator was zero.
The authorized release checker passed with one funded activation, reconciled
trial spend of 60,775 microUSD, reconciled OpenRouter spend of 149 microUSD,
and one checked-out database connection. The audit printed no raw log message
or secret, called no model, and changed no Azure configuration.

Gate 10 then deployed the recorded compatible image at source commit
`448510936c69d485cf9b4e834adea69becf6b114`, passed public acceptance, and
automatically restored the current shared-view image. The healthy restored
revision is `abda-nl-stg-web--restore-6d0fb44`. Both acceptance passes
succeeded without rerunning a migration or changing a secret, setting, trial
limit, or OpenRouter state.

Gate 11 is a two-run disposable-account privacy acceptance. It validates a
mode-600 export without printing or retaining it, suspends the account, proves
share and MCP revocation, enforces a 15-minute wait, and then permanently
deletes local private data after a second confirmation. It is pinned to the
current source-security image and uses an execution-only override of the
manual migration job instead of the unavailable interactive WebSocket. The
saved job configuration remains unchanged. Gate 12 is the final
three-setting promotion from the ten-user pilot to 100 users and from disabled
to outage-only OpenRouter fallback while retaining independent $500 hard caps.
Both gates are prepared and covered by focused tests. The read-only Gate 13
checks the final public origin in Chromium and Firefox at desktop,
zoom-equivalent, and mobile widths. It combines WCAG A and AA scans with
keyboard focus, focus trapping, focus return, reduced-motion, reflow, policy
link, console, and page-error checks. Gate 12 must remain the final configuration
mutation and must not run merely because its source tests pass.
