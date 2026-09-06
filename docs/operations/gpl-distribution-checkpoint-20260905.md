# GPL distribution checkpoint, September 5, 2026

Status: development source and container verified and published. Not an Azure
deployment receipt or a declaration that all public-service gates are complete.

Subsequent live status: the operator's `gpl-6` audit and funded smoke passed
for this exact image. Public browser and bounded capacity checks then passed.
See the separate [live acceptance record](gpl-live-checkpoint-20260905.md).

## Decision and source

The project maintainer selected GPL-3.0 for the combined ABDA-NL distribution.
The implementation uses `GPL-3.0-only`, retains the original MIT grant verbatim,
and preserves upstream and third-party attribution. No special MIT exception
is required for this chosen distribution path.

- Application source: `ed241c1509739f16b2433ced686da76fe1ed1d94`.
- Source license: `GPL-3.0-only`.
- GPL text SHA-256:
  `3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986`.
- Preserved original MIT notice SHA-256:
  `56582fa54ed6605931f1adbc6ae1bf450aa3067a51c04263d990c8003fc7daba`.
- The seven modified imported engine files received dated comments only.
  Their parsed Python ASTs matched the prior source exactly.
- The wheel was built locally and its GPL metadata, GPL text, original MIT
  notice, and third-party notice were checked against the source bytes.

The package, citation, Dockerfile, and publication workflow agree on the SPDX
identifier. The minimum setuptools version is 77, matching its support for
the standardized license expression and license-file metadata.

## Verification

- Local suite: 852 passed, 29 skipped; lint and Python security rules passed.
- [Source CI](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33992470908): all
  eight jobs passed, including Python 3.10 and 3.13, restricted-role PostgreSQL,
  Chromium, Firefox, WebKit, container/wheel checks, and secret scanning.
- [CodeQL](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33992470938): passed.
- [Tag CI](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33992513393): passed.
- [Image publication](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33992513397):
  source and dependency checks, container smoke, retained notice checks,
  security scans under the existing vulnerability policy, SBOM, and attestation
  all passed.
- Twelve new label-matching cases cover the pending rollout and rollback.
  Together with the affected wrapper and chain tests, 30 focused tests passed.

## Published artifact

```text
ghcr.io/liu-hy/abda-nl@sha256:b7025d4322e05a698e79eb120a233c68cf638d5cdd44c8f58223681ff15ae1c5
```

The source tag is `service-image-staging-gpl3-20260905-ed241c1`. No GitHub
Release was created. Anonymous registry access verified the complete manifest
and config hashes and the exact GPL, source-repository, and source-commit labels.
Independent `gh attestation verify` succeeded with the exact source digest,
expected signing workflow, and GitHub-hosted-runner restriction.

[Matching source archive](https://github.com/Liu-Hy/ABDA-NL/archive/ed241c1509739f16b2433ced686da76fe1ed1d94.tar.gz).
The archive includes source and build recipes; component notices and dependency
source locations are recorded in [THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md).

## Operator handoff and preserved boundaries

- Image, audit, rollback, and promotion wrappers are pinned in
  `9ccbab542a93898c02223b94dfc9e0e1d4eacb7e`.
- Post-privacy helper revision 7 is pinned in
  `b14357722d8a2f6686d1fb14beb2c0806cb568be`.
- Helper SHA-256:
  `2e8fa216c34c4ff96c674e1d6f00ebd8d7169e84c951a38a8209dfb887328dcb`.
- The helper's read-only `verify` command downloaded and verified all six
  phase entries successfully. It made no Azure request or change.
- Use the exact download block and ordering in
  [the final operator batch](final-operator-batch.md#3-deploy-and-audit-the-cumulative-service-image).
  The later September 5 [privacy recovery review](privacy-preflight-failure-20260905.md)
  and operator confirmation of exact Auth0 cleanup have satisfied that
  prerequisite. The subsequent rollout audit and funded smoke have also
  passed, as recorded in the live checkpoint above. Do not repeat deployment
  or the already successful privacy deletion merely to obtain a new receipt.

Neither repository's stable `main` changed; both were verified live at
`e4be41c72f34dd555147a2de221d84b3fd735c9f`. The old main license label is not
retroactively corrected by this development-only change. Historical commits,
authors, tags, images, and their real labels were preserved. The paper was
not relicensed.

No Azure configuration, application revision, secret, database row, Auth0
identity, DNS record, or quota changed in this checkpoint. The ten-user pilot
and disabled public OpenRouter failover remain at their last operator-verified
settings. Further live acceptance requires the operator's authenticated cloud
session, not another software-license choice.
