# Container security checkpoint, 2026-09-04

State: source and CI verified, not published or deployed

This checkpoint records the container-hardening change in source commit
`887a59cfcd03a4e2211efd9b822d98432de9b36c`. The documentation commit that
contains this record is intentionally newer. No service image tag was created,
and no Azure, Auth0, Cloudflare, Resend, database, model-routing, or budget
setting changed.

The public service at `https://demo.abda-nl.org` continues to run the audited
image from source commit `51702e175bd14d4cb54075808f839d173d561324`.
The source-license gate remains blocked, so this newer image may be built in
ephemeral CI for verification but must not be published or deployed.

## Implemented boundary

The production Dockerfile now removes pip from both the copied application
virtual environment and the runtime interpreter. Runtime dependency packages
remain hash locked. The image still starts as the fixed non-root user and uses
the same digest-pinned Python 3.13 Bookworm base in both stages.

CI and the future image-publication workflow now use Trivy 0.74.0 from its
official release archive with SHA-256 checksum
`2ae6fe3ee734b7fdf11335663e18c75ea12dccc76062f09f164a3b0f8be4371a`.
Each workflow:

1. scans the complete built image for vulnerabilities;
2. scans separately for embedded secrets without retaining a raw secret
   report;
3. scans the Dockerfile and blocks any reported configuration failure;
4. generates a CycloneDX SBOM as a workflow artifact;
5. blocks every high or critical vulnerability with a reported fixed version;
6. blocks every new, unfixed high or critical finding that is absent from the
   exact reviewed base-image baseline; and
7. verifies at runtime that neither the system interpreter nor the application
   virtual environment can import pip.

The explicit exclusion `**/pip/_vendor/bom.cdx.json` removes only pip's own
vendored component manifest from vulnerability discovery. Direct inspection
showed that treating that file as an installed-package inventory introduced
two false findings for `msgpack 1.1.2` and `setuptools 70.3.0`. Without the
exclusion, the policy rejected both findings because fixed versions exist.
With the exclusion, the scanner still examines the complete remaining image
filesystem and package database.

The checked-in unfixed baseline is tied to
`python:3.13-slim-bookworm@sha256:ed86c82274b3c69b52fb5820f358f0bd7df0b603332063cb5c6e32bd220c3e6e`.
That digest was also the current registry digest for the named official tag at
the time of review. A base-image refresh or newly reported severe finding must
change the source and pass the full matrix again.

The SBOM remains a separate workflow artifact rather than an OCI index
attachment. This preserves the single-platform manifest shape already proven
compatible with Azure Container Apps.

## Verification evidence

Local verification for the source commit passed:

- complete Python suite: 813 passed, 29 skipped;
- normal Ruff checks for application, migrations, tests, and the new policy;
- Ruff security rules for the runtime application and new policy;
- `python -m pip check`;
- syntax checks for every `deploy/azure/*.sh` file;
- JSON and CycloneDX generation with the pinned Trivy binary; and
- the policy against both the exact base image and the currently deployed
  image.

The complete GitHub matrix passed in
[CI run 33883113444](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33883113444).
It included Python 3.10 and 3.13, PostgreSQL 16, complete-history secret
scanning, Chromium, Firefox, WebKit, Bicep compilation, wheel checks, the
production container build, the new container scan, and the post-scan runtime
smoke test. [CodeQL run 33883112710](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33883112710)
also passed. The repository then reported zero open CodeQL, Dependabot, and
secret-scanning alerts.

The CI container-security artifact was
`container-security-ci-887a59cfcd03a4e2211efd9b822d98432de9b36c`, artifact
ID `9940778004`, with archive digest
`sha256:06ef3bdc9eb2086fdc6006fc987f781ca4b9b0f3cbd44f4c284608b339acd746`.
Its retained policy summary reported:

```text
total_vulnerabilities: 249
high_critical_vulnerabilities: 60
reviewed_unfixed_high_critical: 60
unreviewed_unfixed_high_critical: 0
stale_baseline_entries: 0
actionable_high_critical: 0
secret_findings: 0
result: CONTAINER_SECURITY_POLICY_VERIFIED
```

The separate CycloneDX 1.7 SBOM contained 162 components. The artifact did not
retain the temporary raw secret report. GitHub is scheduled to expire the
artifact on 2026-09-18, so the durable source record contains the policy,
baseline, scanner identity, counts, run URL, artifact identity, and archive
digest.

## Remaining release gate

This checkpoint strengthens source and artifact verification, but it does not
clear the imported engine's GPL-3.0 redistribution question. Follow the
[source license review](source-license-review.md) before creating another
public image. After that decision, the image-publication workflow must scan the
exact pushed digest and preserve a new SBOM, vulnerability report, policy
summary, smoke-test result, and provenance attestation before deployment.
