# ABDA-NL operations

Start with the
[final public-service operator batch](final-operator-batch.md). It is the only
current ordered sequence for changing the deployed release. Dated staging
checkpoints are evidence records. Do not reconstruct a current command from a
historical checkpoint or edit an immutable commit, image digest, revision, or
checksum in Cloud Shell.

## Current release sequence

- [GPL distribution checkpoint](gpl-distribution-checkpoint-20260905.md)
  records the selected license, preserved notices, verified source and image,
  and repinned operator helper. Azure rollout remains pending.
- [Final public-service operator batch](final-operator-batch.md) contains the
  current download block, exact confirmations, resume behavior, and ordered
  release Gates.
- [Source-security checkpoint](source-security-checkpoint-20260902.md) binds the
  current hardened source, CI, CodeQL, immutable image digest, provenance,
  Azure deployment, and live sanitized-log audit.
- [Development source checkpoint](development-source-checkpoint-20260904.md)
  records the cumulative application source before the container-security
  checkpoint, its unchanged stable main ancestor, and the explicit
  license-gated deployment hold.
- [Container security checkpoint](container-security-checkpoint-20260904.md)
  records the current development container build, exact severe-vulnerability
  baseline, independent secret scan, CycloneDX SBOM, CI evidence, and continued
  license-gated deployment hold.
- [Rate-limit retention checkpoint](rate-limit-retention-checkpoint-20260904.md)
  records the original tested and attested retention image, now preserved as
  historical evidence.
- [Account-suspension integrity checkpoint](suspension-integrity-checkpoint-20260904.md)
  records the final pre-WebKit candidate. It is historical evidence and must
  not be deployed as the current release target.
- [Provider accounting integrity checkpoint](accounting-integrity-checkpoint-20260904.md)
- [Provider lifecycle checkpoint](provider-lifecycle-checkpoint-20260904.md)
  records an intermediate cumulative retention and hard-cap accounting image
  that was superseded before deployment.
- [Requirements traceability](requirements-traceability.md) distinguishes
  completed implementation evidence from external and hardware acceptance.
- [Public and COMMA release checklist](release-checklist.md) is the final
  requirement-by-requirement signoff record.
- [Source license review](source-license-review.md) records the GPL-3.0-only
  distribution decision, preserved MIT and upstream notices, and artifact checks.
- [Deterministic engine validation](deterministic-engine-validation-20260904.md)
  records historical scenario compatibility and exact parity for all six
  deployed baseline payloads.
- [Deterministic computation budget](deterministic-computation-budget-20260904.md)
  records the source-level bound on combinatorial reasoning work and its
  unchanged bundled outputs. It is not yet a live deployment record.
- [MCP read abuse boundary](mcp-read-abuse-boundary-20260904.md) records the
  shared per-account request ceiling for deterministic MCP read tools. It is
  source-level evidence pending the license-gated cumulative deployment.

If a Gate stops, preserve its visible sanitized output and exit code. Do not
issue an improvised Azure update or repeat a paid provider call. Resume only
through the same pinned Gate or through a reviewed recovery instruction.

OCI license fields in historical image records reproduce immutable artifact
metadata. They are not proof that the label covers the imported engine. The
[source license review](source-license-review.md) controls any new public image
or final release declaration.

## Service runbooks

- [Public Azure deployment](public-deployment.md)
- [Operator accounts, domains, and external services](operator-service-bootstrap.md)
- [Auth0 email OTP](auth0-email-otp.md)
- [Cloudflare root-domain redirect](cloudflare-apex-redirect.md)
- [Model evaluation and promotion](model-promotion.md)
- [Privacy access and deletion requests](privacy-requests.md)
- [PostgreSQL recovery and incident handoff](database-recovery.md)
- [Observability alerts](observability-alerts.md)
- [COMMA 2026 demonstration playbook](comma-2026-demo-playbook.md)

The PostgreSQL recovery runbook documents an incident path. Reading it and
completing its tabletop do not authorize or require a billable restore.

## Retained acceptance evidence

Files named with staging stages or dates record what was true for an exact
source commit, image, revision, and observation window. They support an audit
trail but do not replace the current operator batch. In particular:

- [Initial staging deployment](staging-deployment-record-20260828.md)
- [Funded trial pilot](staging-trial-pilot-20260828.md)
- [Early live acceptance](staging-live-acceptance-20260828.md)
- [First release candidate](staging-release-candidate-20260829.md)
- [Authenticated browser acceptance](staging-gate8-authenticated-acceptance-20260829.md)
- [OpenRouter outage drill](staging-openrouter-outage-drill.md)
- [Delta contingency](staging-delta-contingency-20260829.md)
- [Consolidated staging release](consolidated-release-acceptance-20260830.md)
- [Managed-boundary release](managed-boundary-release-acceptance-20260902.md)

Do not delete these records when a later release supersedes them. They explain
why earlier changes were accepted and preserve compatible rollback evidence.
