# Personal hosting checkpoint

Date: 2026-08-27, anonymous visibility reconfirmed 2026-08-28

This record captures the first externally verified source and image checkpoint
under the operator-controlled repository. It is not a production release
record. Identity, email, Azure, DNS, final browser, and conference gates remain
open.

## Repository boundary

- Paper upstream: `https://github.com/idaks/ABDA-NL`
- Paper `main`: `e4be41c72f34dd555147a2de221d84b3fd735c9f`
- Service repository: `https://github.com/Liu-Hy/ABDA-NL`
- Personal `main`: `e4be41c72f34dd555147a2de221d84b3fd735c9f`
- Image source commit:
  `1217b3a5aa7d3e1f5ada80e701a4234996c705f7`
- Documentation checkpoint after the image:
  `d0576d242a1e50583c68573ac15f328364a667db`

The personal repository is standalone, not a GitHub fork. Both source branches
retain the paper repository's complete commit ancestry. The paper documents
remain untracked and were absent from both commits and the image context.

Personal `main` requires a pull request and the seven GitHub Actions checks
listed below. Required checks must be current with the base branch. Linear
history and conversation resolution are required. Force pushes and deletion
are disabled on `main` and `development`.

The personal repository also has GitHub secret scanning, secret push
protection, vulnerability alerts, and automated Dependabot security updates
enabled. Merge commits are disabled, while squash and rebase merges remain
available.

## Source verification

Local verification of image source commit `1217b3a` produced:

- Ruff default and security profiles: passed
- locked runtime dependency audit: no known vulnerabilities
- locked development dependency audit: no known vulnerabilities
- pytest: 480 passed, 4 environment-specific skips
- deployment-contract tests: 6 passed
- all Bicep modules and parameter files compiled with Bicep 0.46.1
- workflow YAML parsed successfully
- staged-content secret pattern scan: passed

GitHub CI run
[`33125108496`](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33125108496)
passed at the same commit. Its seven jobs were:

- `Python 3.10`
- `Python 3.13`
- `browser-acceptance (chromium)`
- `browser-acceptance (firefox)`
- `deployment-artifacts`
- `postgres-acceptance`
- `secret-scan`

The later documentation-only checkpoint passed the same seven jobs in CI run
[`33125598741`](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33125598741).

## Immutable image verification

- Trigger tag: `service-image-personal-20260827-230851`
- Workflow run:
  [`33125216358`](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33125216358)
- Deployable image:
  `ghcr.io/liu-hy/abda-nl@sha256:3a697972b5192c07d815e22821b5495fc8ce7b73890ab95ef0ac33a0f1629cda`
- Provenance attestation:
  [`43533971`](https://github.com/Liu-Hy/ABDA-NL/attestations/43533971)

The tag-gated workflow reran the locked installation, Ruff profiles,
dependency audits, and complete non-browser suite. It built and pushed one
Linux AMD64 image, pulled the exact digest, started it as the service, checked
liveness, readiness, configuration, privacy, and terms endpoints, and then
created GitHub build provenance.

After the package owner changed its one-time visibility setting to Public, an
unauthenticated OCI registry request on 2026-08-28 returned HTTP 200 and the
exact header:

```text
docker-content-digest: sha256:3a697972b5192c07d815e22821b5495fc8ce7b73890ab95ef0ac33a0f1629cda
```

`gh attestation verify` accepted the digest for `Liu-Hy/ABDA-NL`. The
anonymous image configuration reported:

```text
org.opencontainers.image.source=https://github.com/Liu-Hy/ABDA-NL
org.opencontainers.image.revision=1217b3a5aa7d3e1f5ada80e701a4234996c705f7
org.opencontainers.image.licenses=MIT
```

## Remaining release boundary

This checkpoint proves the portable source, CI, public image, digest, and
provenance path. It does not prove a public application deployment. The final
release must repeat image publication for its exact release commit and attach
the remaining evidence from the release checklist, including Azure migration,
private PostgreSQL, live identity and email, funded routes, DNS and TLS,
external security checks, accessibility review, rollback, and conference
rehearsal.
