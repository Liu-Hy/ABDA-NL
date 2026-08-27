# Decision 0007: Service repository ownership and promotion

Date: 2026-08-27

## Status

Accepted.

## Context

The accepted paper links to `idaks/ABDA-NL`. Its `main` branch must remain a
stable, paper-faithful demo for readers. The hosted research service needs
frequent development plus administrative control of Actions, branch rules,
packages, security settings, and deployment credentials. The current developer
can write to the iDAKS repository but cannot administer its package or
repository settings. Waiting for organization-level changes would block the
service without improving the paper artifact.

A GitHub fork was considered. A fork keeps useful provenance but remains in the
upstream fork network, adds workflow activation constraints, and cannot later
be transferred into the organization while the upstream repository occupies
the target network and name.

## Decision

The repositories have separate responsibilities:

1. `idaks/ABDA-NL` remains the paper-facing upstream. Its `main` branch stays at
   the reviewed paper demo until a separately reviewed release is ready.
2. `Liu-Hy/ABDA-NL` is a standalone public repository for hosted-service
   development and operation. It preserves the complete Git ancestry from the
   paper repository without belonging to its fork network.
3. The personal repository's `main` begins at the exact paper-demo commit.
   Hosted work continues on `development` until its public release gates pass.
4. In the shared Delta checkout, `origin` names the iDAKS upstream and
   `personal` names the operator-controlled repository. Service branches and
   image tags are pushed explicitly to `personal`.
5. Image publication derives `ghcr.io/OWNER/abda-nl` from the repository that
   runs the workflow. Azure receives the public image repository and immutable
   digest as separate deployment parameters. No application code assumes a
   personal or organization package owner.
6. Personal `main` requires a pull request, all seven CI checks, current-base
   status, linear history, and resolved conversations. Force pushes and branch
   deletion are disabled for both `main` and `development`.
7. GitHub secret scanning, push protection, vulnerability alerts, and automated
   Dependabot security updates remain enabled on the service repository.

## Promotion paths

Once the hosted service passes its release checklist, either of these paths is
valid:

- Merge or fast-forward the reviewed commits into a designated iDAKS branch,
  then promote them under the organization's normal review process.
- Transfer the standalone repository to iDAKS after an organization
  administrator makes the target name available and reviews the repository
  settings.

GitHub container packages and attestations are owner-scoped. Promotion never
assumes that they move with source ownership. A promoted release publishes a
new organization-owned image, verifies anonymous access, records its new
digest and attestation, and updates the Azure image-repository parameter.

## Consequences

- The archival paper URL remains stable throughout service development.
- Hosted development no longer depends on iDAKS repository or package
  administration.
- The personal GitHub account is currently an operational recovery boundary.
  Before public registration opens, it needs strong multifactor authentication,
  stored recovery codes, and a second trusted maintainer or documented transfer
  procedure.
- GitHub settings, secrets, package visibility, and deployment history are not
  source-controlled artifacts. The release record must capture their relevant
  state, and organization promotion must recreate and verify them.
- A green personal service branch does not authorize changing the paper-facing
  iDAKS `main` branch.
