# Staging deployment record

Date: 2026-08-28

State: `GATE3_APPLICATION_DEPLOYED_PROBE_REPAIR_PENDING`

This record binds the first application deployment candidate to one source
commit, one immutable image digest, and the already recovered Azure staging
infrastructure. It contains no credentials. This documentation record is newer
than the application source commit and is not part of the image.

## Application identity

- Source repository: `https://github.com/Liu-Hy/ABDA-NL`
- Source commit: `3cace0bdef793e6ee966675d1e97b69d77fe2112`
- Source CI:
  [`33194426064`](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33194426064)
- Publishing tag: `service-image-staging-20260828-172505`
- Image workflow:
  [`33194589496`](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33194589496)
- Deployable image:
  `ghcr.io/liu-hy/abda-nl@sha256:c3f6ec80972850d30850ec2e72d28fd673e835187bebdc45a8f9cda4a8ad1a55`
- Provenance attestation:
  [`43717397`](https://github.com/Liu-Hy/ABDA-NL/attestations/43717397)
- Platform: Linux AMD64

The source CI completed all seven jobs. Local verification at the same commit
reported 492 passing tests and four environment-gated skips. Separate local
browser runs passed all three browser journeys in both Chromium and Firefox.
Both Ruff profiles, both hash-locked dependency audits, native Python 3.13 lock
regeneration, migration parity, the wheel build, and Bicep 0.46.1 compilation
passed.

The publishing workflow repeated the locked installation, Ruff checks,
dependency audits, and non-browser test suite. It refused replacement of an
existing commit image, built and pushed the Linux AMD64 image, pulled and
smoke-tested the exact digest, and created SLSA provenance.

An anonymous registry token retrieved the manifest by digest with HTTP 200 and
the exact `Docker-Content-Digest` header. The anonymous image configuration
reported:

```text
org.opencontainers.image.source=https://github.com/Liu-Hy/ABDA-NL
org.opencontainers.image.revision=3cace0bdef793e6ee966675d1e97b69d77fe2112
org.opencontainers.image.licenses=MIT
```

`gh attestation verify` accepted the image while enforcing the exact source
repository, source commit, publishing tag, and
`.github/workflows/publish-service-image.yml` signer. The verified predicate is
`https://slsa.dev/provenance/v1` and names the exact image digest above.

## Azure infrastructure target

- Subscription: `00e62f6e-2174-40b2-b428-8ebfd7c2ac54`
- Resource group: `abda-nl-staging`
- Infrastructure deployment: `abda-nl-stg-infra`, `Succeeded`
- Container Apps environment: `abda-nl-stg-environment`, `Succeeded`
- PostgreSQL host:
  `abda-nl-stg-postgres-bgjhpbgw.postgres.database.azure.com`
- PostgreSQL state: `Ready`
- PostgreSQL public network access: `Disabled`
- Database: `abda`
- Backup retention: seven days
- Log Analytics retention: 30 days
- Expected migration job: `abda-nl-stg-migrate`
- Expected Container App: `abda-nl-stg-web`
- Generated origin:
  `https://abda-nl-stg-web.blueforest-da494f7c.eastus2.azurecontainerapps.io`

No migration job or Container App existed when this image record was created.

## Guarded application gate

The deployment orchestration is pinned separately from the application image:

- Gate source commit:
  `075beeee5aab1d08dafd4bc05fabed3ef04f2c9b`
- Gate CI:
  [`33225052231`](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33225052231)
- Gate script: `deploy/azure/gate3-staging-application.sh`
- Gate script SHA-256:
  `05536276ebfe23731677611792a26b2fac90e9a57d935b673e339022f3a6a64e`

All seven CI jobs passed at the gate source commit. Local verification reported
500 passing tests and four environment-gated skips. Revision 2 passed Bash
syntax validation, both Ruff checks, a complete mocked run from an unrelated
temporary working directory, a fresh public-clone checksum test, and an
immutable-download checksum test. The mocked operator cancelled at the final
confirmation, and the command log proved that no deployment creation or job
execution occurred.

The first operator run, using revision 1, stopped during source verification before
credential input or deployment confirmation. The checksum producer changed to
the cloned checkout, but the piped `sha256sum` consumer retained the Cloud Shell
working directory. Revision 2 runs both operations inside the cloned checkout
and makes the mocked test start from an unrelated temporary directory so this
failure cannot recur unnoticed. The stopped revision 1 run did not change
Azure state.

The second operator run, using revision 2, passed the immutable source and image
checks, then stopped during recovered-infrastructure verification before
credential input or deployment confirmation. Azure CLI exposes PostgreSQL
`state` and `network` at the top level, while the validator expected the raw ARM
`properties` wrapper used by the original mock. Revision 3 makes the CLI emit a
small normalized object, verifies the server name, hostname, ready state, and
disabled public access, and changes the mock to enforce that live CLI shape.
The stopped revision 2 run did not change Azure state.

The gate clones and verifies the application source commit above, checks the
four deployment-template hashes, confirms anonymous access to the exact image
digest, verifies the Azure identity and recovered infrastructure, reads the
public Auth0 discovery document, validates both deployments, and accepts
mutations only for the expected migration job and web application. It rejects
deletes, unsupported changes, and mutations to any other resource. One exact
confirmation authorizes the migration and application sequence. Trial
activation and OpenRouter failover remain disabled.

This gate commit changes only deployment orchestration and tests. It does not
replace or republish the application image.

## Auth0 generated-origin boundary

The `ABDA-NL Public Service` Regular Web Application has exact, wildcard-free
generated-origin values:

```text
Callback:
https://abda-nl-stg-web.blueforest-da494f7c.eastus2.azurecontainerapps.io/auth/callback

Logout return:
https://abda-nl-stg-web.blueforest-da494f7c.eastus2.azurecontainerapps.io/

Web origin:
https://abda-nl-stg-web.blueforest-da494f7c.eastus2.azurecontainerapps.io
```

The public OIDC discovery values are:

```text
Metadata: https://login.abda-nl.org/.well-known/openid-configuration
Issuer: https://login.abda-nl.org/
End session: https://login.abda-nl.org/oidc/logout
```

The application client ID and secret remain only in the operator's private
credential manager and are not recorded here.

## Live Gate 3 outcome and probe diagnosis

The guarded Gate 3 deployment ran the migration execution
`abda-nl-stg-migrate-ird46jy` successfully and deployed Container App revision
`abda-nl-stg-web--ztv7ycn`. Azure accepted the resource deployment, and the
application logs then confirmed all of the following:

- the process started with LLM support enabled
- database-backed application startup completed
- the MCP session manager started
- Uvicorn listened on `0.0.0.0:8000`

The generated HTTPS origin nevertheless timed out. A read-only control-plane,
replica, and log inspection found the revision `Unhealthy`, its only replica
`NotRunning`, and the web container restarted four times. The Container Apps
environment log recorded repeated startup-probe HTTP 400 responses and
`ProbeFailure` terminations. At the same five-second interval, the application
logged an unmatched HTTP 400 request.

The failure is a strict-host and health-probe integration defect, not an image,
port, database, or process-start failure. Container Apps probes connect to the
pod IP by default, which also supplies a pod-IP `Host` value unless the probe
sets one explicitly. The application intentionally permits only its generated
and custom public hostnames through `TrustedHostMiddleware`, so that probe host
was rejected before `/health/live` could be routed.

The repair keeps strict host validation and adds an explicit `Host` header with
the generated Container Apps hostname to the startup, liveness, and readiness
probes. It does not add a wildcard trusted host. The existing immutable image
digest remains the deployment candidate because the failure is entirely in the
Azure revision template. Trial activation and OpenRouter failover remain
disabled.

## Rollback candidate

The previous schema-compatible, smoke-tested image is:

```text
ghcr.io/liu-hy/abda-nl@sha256:0a1b22112687a6a409cc55de0061ac0d7259160582a14bba88929d1a3234ad14
```

It corresponds to source commit
`7240a21882774a90216ac621bdd091c1b2c34a15`, workflow
[`33185202463`](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33185202463),
and attestation
[`43691170`](https://github.com/Liu-Hy/ABDA-NL/attestations/43691170).
It remains only a rollback candidate until an actual staging rollback rehearsal
passes. No automatic database downgrade is permitted.

## Next guarded gate

Run a narrowly scoped probe-repair gate from Azure Cloud Shell. It must verify
the existing successful migration, the unhealthy revision, the exact image
digest, and the three corrected probe headers. Its resource-only what-if may
modify only `abda-nl-stg-web`. It must not rerun the migration, update any other
resource, enable trial activation or OpenRouter failover, or change Auth0 and
DNS. Acceptance requires a healthy running replica plus the complete
generated-origin HTTPS, configuration, security-header, and protected-metrics
checks.

The implemented gate is `deploy/azure/gate3-probe-repair.sh`. It requires a
separate confirmation immediately before the one permitted Container App
deployment. Both the cancellation path and the complete success path are
covered by command-level tests. The success simulation requires a replacement
revision that is provisioned and healthy, at least one running and ready
replica, all three exact probe headers, and every generated-origin acceptance
check before it reports completion.
