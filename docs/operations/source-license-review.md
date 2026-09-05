# ABDA engine source license review

Status: GPL-3.0 chosen by the project maintainer on September 5, 2026.
The development distribution uses the SPDX identifier `GPL-3.0-only`.

Public image publication gate: cleared

## Decision and scope

The combined ABDA-NL distribution, including the imported ABDA engine, is
distributed under GNU GPL version 3. A special MIT exception for upstream ABDA
is no longer the selected path. No separate relicensing permission request or
institutional review is a prerequisite introduced by this engineering gate.
Existing third-party obligations still apply.

The original ABDA-NL MIT grant is retained verbatim in
[LICENSES/ABDA-NL-MIT.txt](../../LICENSES/ABDA-NL-MIT.txt). It remains a grant
for the original MIT-covered portions, not for the imported engine. The
[third-party notice](../../THIRD_PARTY_NOTICES.md) identifies upstream authorship,
the imported file scope, modification dates, and dependency notices.
Research leadership and authorship are acknowledged without inventing
exclusive copyright ownership.

The top-level GPL text is byte-identical to upstream's pinned `LICENSE.md`.
The package, citation, Dockerfile, and image workflow use `GPL-3.0-only`.
Choosing version 3 specifically does not assert a new grant for later versions.
The paper and third-party research material are outside this software change.

## Preserved provenance

The review on September 4, 2026 identified upstream
[Schirmi136/ABDA](https://github.com/Schirmi136/ABDA) at revision
[`6e7a45c40150fbf6bb5377271bf238d8fcd32463`](https://github.com/Schirmi136/ABDA/tree/6e7a45c40150fbf6bb5377271bf238d8fcd32463).
Its [GPL license](https://github.com/Schirmi136/ABDA/blob/6e7a45c40150fbf6bb5377271bf238d8fcd32463/LICENSE.md)
predates the ABDA-NL import `90b7338da35d8a33b36ad4c877f9a61c99c61d7c`.

Twenty-one engine paths matched upstream. At the time of the review, fourteen
were byte-identical and seven differed. The exact list is preserved in
[THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md#abda-engine).
The upstream public history credits Sören Uebis. The project maintainer
identifies Martin Caminada as ABDA's research lead and the originator of
ABDA-NL. These facts are complementary, not proof that either person alone
owns every contribution.

The earlier top-level MIT notice omitted the imported GPL license. This
change corrects the development distribution; it does not rewrite the
original import, authors, or historical source records.

## Distribution checks

The publication gate is cleared only for source containing this correction.
CI checks the actual wheel's license metadata and the bytes of all three
application notice files. CI and image publication compare the corresponding
container files against the source tree. Existing vendored browser license
files remain part of both wheels and containers. The seven modified imported
modules carry a dated modification notice.

Published images identify their repository and complete source revision in
OCI labels. The publication receipt links directly to that public commit and
its downloadable source archive, containing application source and build
scripts. Dependency locks, retained dependency notices, the vendor manifest,
and image SBOM identify separately licensed components.
See [corresponding-source instructions](../../THIRD_PARTY_NOTICES.md#corresponding-source).

Changing this document alone cannot establish artifact compliance. Tests and
publication checks must pass before a corrected image is handed to an operator.

## Historical images and the next rollout

Stable `main` and existing immutable images have not changed. Their old MIT
labels are historical metadata, not permission to redistribute the imported
engine under MIT. Do not replace those records with invented GPL labels or
overwrite their immutable tags. Use newly built GPL-labeled artifacts for new
distributions. This development-only correction does not retroactively resolve
the older paper branch's missing engine notice.

The previously queued `084817f` image remains superseded. The next image must
include both the cumulative application fixes and this licensing correction.
The operator helper must be repinned to the new source and digest, with exact
GPL label verification for the new image. Historical checks for old images
must continue to expect their actual labels. Do not execute the superseded
deployment chain in the meantime.

Clearing this source gate does not verify Azure rollout, historical privacy
database binding, Auth0 cleanup, root-domain redirection, email capacity, or
public trial/fallback promotion. Those remain separate acceptance evidence.

## Test provenance

The four retired historical CamelCase test modules remain available in Git
history. Three contained five self-contained tests; the fourth depended on
15 absent upstream fixtures. Maintained tests cover grounded-label fixed
points, cycles, min-max numbering, and discussion games without those fixtures.

On September 4, a temporary compatibility check combined the historical
modules from `e6a3062` with the fixed upstream fixture directory and exercised
the current engine: 20 tests passed in 1.15 seconds. No fixture was committed.
Retiring tests was test hygiene, not a licensing remedy. The GPL choice
removes the earlier MIT-only obstacle to considering upstream fixtures, but
no fixture import is needed for this change.
