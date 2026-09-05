# Licensing and third-party notices

Effective for this development distribution from September 5, 2026.

ABDA-NL, including the imported ABDA engine and its modifications, is
distributed as a combined program under GNU GPL version 3 only
(`GPL-3.0-only`). The complete license is in [LICENSE](LICENSE).
This does not revoke or replace the original grants for separately
identifiable MIT, BSD, Apache, or other third-party components.

## Original ABDA-NL code

The original notice, `Copyright (c) 2026 idaks`, and its complete MIT grant are
preserved verbatim in [LICENSES/ABDA-NL-MIT.txt](LICENSES/ABDA-NL-MIT.txt).
That grant remains applicable to the original MIT-covered portions. It is not
an MIT grant for the imported GPL engine or for the combined distribution.

## ABDA engine

Upstream: [Schirmi136/ABDA](https://github.com/Schirmi136/ABDA), revision
[`6e7a45c40150fbf6bb5377271bf238d8fcd32463`](https://github.com/Schirmi136/ABDA/tree/6e7a45c40150fbf6bb5377271bf238d8fcd32463).
Its [LICENSE.md](https://github.com/Schirmi136/ABDA/blob/6e7a45c40150fbf6bb5377271bf238d8fcd32463/LICENSE.md)
contains GNU GPL version 3. This distribution preserves those license bytes in
its top-level LICENSE. It does not assume an additional grant for later GPL
versions.

Martin Caminada led ABDA and proposed ABDA-NL. The upstream public Git history
credits Sören Uebis. These acknowledgements describe project and development
contributions, not an assertion of exclusive copyright ownership.

The engine was imported into ABDA-NL on June 29, 2026, in commit
`90b7338da35d8a33b36ad4c877f9a61c99c61d7c`. The following 21 paths beneath
`app/abda/` derive from that upstream revision:

```text
ABDA.py
ABDAShell.py
ArgumentationSystem/Argument.py
ArgumentationSystem/ArgumentBuilder.py
ArgumentationSystem/ArgumentationGraph.py
ArgumentationSystem/Attack.py
Configuration.py
GraphVisualization/GraphConvert.py
GroundedDiscussionGame/Game.py
GroundedDiscussionGame/GameShell.py
GroundedDiscussionGame/Moves/CB.py
GroundedDiscussionGame/Moves/CONCEDE.py
GroundedDiscussionGame/Moves/HTB.py
GroundedDiscussionGame/Moves/Move.py
GroundedDiscussionGame/Moves/RETRACT.py
KnowledgeBase/AspicRulesLoader.py
KnowledgeBase/BaseRule.py
KnowledgeBase/DefeasibleRule.py
KnowledgeBase/DefeasibleRuleSet.py
KnowledgeBase/RuleCollection.py
KnowledgeBase/StrictRule.py
```

ABDA-NL is a modified distribution, not an unchanged upstream release. On
September 4, 2026, 14 of these files still matched upstream byte for byte.
The seven modified paths were `ABDAShell.py`, `ArgumentationSystem/Argument.py`,
`ArgumentationSystem/ArgumentBuilder.py`, `ArgumentationSystem/ArgumentationGraph.py`,
`GraphVisualization/GraphConvert.py`, `KnowledgeBase/DefeasibleRule.py`, and
`KnowledgeBase/StrictRule.py`. Their modification notices were added on
September 5, 2026. Git history records the individual code changes and authors.
The browser application, bridge, service, and deployment tooling are ABDA-NL
additions, not upstream ABDA features.

## Browser dependencies

The vendored browser libraries retain their original grants and notices:

- dagre 0.8.5: [MIT](app/static/vendor/DAGRE-MIT.txt).
- marked 18.0.7: [MIT](app/static/vendor/MARKED-MIT.txt).
- DOMPurify 3.4.13: the Apache-2.0 option of its dual license is used for this
  distribution. Both [Apache-2.0](app/static/vendor/DOMPURIFY-APACHE-2.0.txt) and
  [MPL-2.0](app/static/vendor/DOMPURIFY-MPL-2.0.txt) texts remain included.

[The vendor manifest](app/static/vendor/manifest.json) records exact versions,
download locations, integrity values, and file hashes. Editable upstream
sources are available from [dagre v0.8.5](https://github.com/dagrejs/dagre/tree/v0.8.5),
[marked v18.0.7](https://github.com/markedjs/marked/tree/v18.0.7), and
[DOMPurify 3.4.13](https://github.com/cure53/DOMPurify/tree/3.4.13).

Python packages and the container's operating-system packages retain their own
licenses. Their installed metadata and license files must be preserved when
redistributing an image. Python versions and hashes are recorded in the
requirements locks; published container builds also generate an SBOM. In
particular, psycopg is LGPL-3.0-only, not MIT.

## Corresponding source

Application source, unminified application JavaScript, migrations, dependency
locks, tests, and the Dockerfile/build scripts are public in
[Liu-Hy/ABDA-NL](https://github.com/Liu-Hy/ABDA-NL).
For each published container, use its OCI `org.opencontainers.image.source`
and `org.opencontainers.image.revision` labels to select the matching commit,
not the moving development branch. The workflow publishes a commit-specific
source archive link beside the image digest and attestation. GitHub permits
anonymous download of that commit's source ZIP or tarball.

To inspect or rebuild a published version, replace COMMIT with the complete
40-character revision from the image labels:

```bash
git clone https://github.com/Liu-Hy/ABDA-NL.git
cd ABDA-NL
git checkout --detach COMMIT
docker build --build-arg ABDA_IMAGE_SOURCE=https://github.com/Liu-Hy/ABDA-NL \
  --build-arg ABDA_IMAGE_REVISION=COMMIT -t abda-nl:local .
```

No deployment credential or private user data is needed to build the software.
The documented [local launch](README.md#run-the-demo) works without funded API
access. Build recipes identify upstream dependencies and exact versions; keep
their source locations and notices available along with redistributed binaries.
For source-access problems contact support@abda-nl.org.

This notice covers software. It does not grant new rights in the paper,
third-party publications, uploaded content, service names, or trademarks.

## Historical artifacts

This correction applies to the development source and artifacts built from it.
It does not alter immutable old image labels, Git commits, or stable `main`.
Old images labeled MIT do not establish an MIT grant for the imported engine.
Use corrected GPL-labeled artifacts for new distributions. Historical
provenance and release records remain intact.
