# ABDA engine source license review

Status: external authorization or a repository license decision is required
before a public service release is declared complete.

## Why this is a release gate

ABDA-NL currently identifies the repository as MIT licensed. A source review on
2026-09-04 found that the engine added in commit
`90b7338da35d8a33b36ad4c877f9a61c99c61d7c` closely matches the public
[`Schirmi136/ABDA`](https://github.com/Schirmi136/ABDA) implementation at commit
[`6e7a45c40150fbf6bb5377271bf238d8fcd32463`](https://github.com/Schirmi136/ABDA/commit/6e7a45c40150fbf6bb5377271bf238d8fcd32463).
That upstream repository identifies its license as GPL-3.0.

The comparison matched 21 relative engine paths. Fourteen current ABDA-NL
blobs are byte-identical to the upstream blobs, and seven contain later
changes. Git history shows that the engine directory did not exist in ABDA-NL
before the cited import commit. These facts establish a provenance question.
They do not establish whether the project already received a separate license
or other permission outside Git history.

The same upstream repository contains the 15 `Tests/RuleFiles` fixtures that
the historical `tests/ConclusionWarrantedTests.py` references. Those fixtures
were never committed to ABDA-NL. They must not be copied into this MIT-labeled
repository while the license path remains unresolved.

## Evidence that can be reproduced

The upstream license and tree can be inspected without credentials:

```bash
gh api repos/Schirmi136/ABDA/license \
  --jq '{name: .license.name, spdx_id: .license.spdx_id, html_url: .html_url}'

gh api \
  'repos/Schirmi136/ABDA/git/trees/6e7a45c40150fbf6bb5377271bf238d8fcd32463?recursive=1' \
  --jq '.tree[] | select(.type == "blob") | [.path, .sha] | @tsv'
```

Git blob identifiers use the file contents, so equal identifiers are direct
evidence of equal bytes. The current comparison found these byte-identical
paths beneath `app/abda`:

```text
ABDA.py
ArgumentationSystem/Attack.py
Configuration.py
GroundedDiscussionGame/Game.py
GroundedDiscussionGame/GameShell.py
GroundedDiscussionGame/Moves/CB.py
GroundedDiscussionGame/Moves/CONCEDE.py
GroundedDiscussionGame/Moves/HTB.py
GroundedDiscussionGame/Moves/Move.py
GroundedDiscussionGame/Moves/RETRACT.py
KnowledgeBase/AspicRulesLoader.py
KnowledgeBase/BaseRule.py
KnowledgeBase/DefeasibleRuleSet.py
KnowledgeBase/RuleCollection.py
```

The remaining matched paths have different current blobs and should still be
treated as potentially modified upstream work until authorization is clear.

## Acceptable resolution paths

The project owners should choose one path after checking any prior agreements:

1. Obtain written permission from the relevant upstream copyright holder to
   distribute the imported engine and its modifications under MIT. Preserve
   that permission, add accurate attribution, and state which files it covers.
2. Distribute the combined repository under GPL-3.0 or another confirmed
   compatible arrangement, with the required notices and corresponding source.
3. Replace the imported engine with an independently authorized implementation,
   then rerun the complete semantic, browser, packaging, and deployment gates.

Coauthor approval of ABDA-NL's MIT label does not by itself grant rights in
third-party code. This document is an engineering provenance record, not legal
advice. When uncertainty remains, consult the university's research software
or legal support before release.

## Recommended resolution workflow

The least disruptive path is to establish whether separate permission already
exists, then request it from the upstream rights holder only if needed:

1. Ask the author of ABDA-NL's engine import whether the project already has a
   written license or permission that covers the imported source and later
   modifications. Preserve the original record and verify its exact scope.
2. If no such record exists, contact the upstream maintainer through the public
   repository. Include links to both repositories, the fixed upstream commit,
   the current path list, and the intended MIT distribution.
3. Ask the responder to confirm that they own the relevant rights or are
   authorized to grant the permission. A useful unambiguous response would
   grant ABDA-NL permission to use, reproduce, modify, distribute, and
   sublicense the identified upstream source and ABDA-NL derivatives under the
   MIT License, subject to accurate attribution. The rights holder may use
   equivalent preferred wording.
4. Preserve the complete response privately. Add the agreed attribution and
   permission scope to the repository before checking this release gate.
5. If permission is refused, incomplete, or ambiguous, do not infer consent.
   Choose the GPL-compatible or replacement path with the project owners.

For a release with material external visibility, have the final permission and
repository notices reviewed by the university's research software or legal
support rather than relying on this engineering checklist alone.

## Test hygiene

The four historical CamelCase test modules were not collected by the default
pytest rule. Three contained five self-contained tests. The fourth referenced
the 15 absent upstream fixtures and failed before reaching an assertion when
run directly. The development branch retired those modules without rewriting
their history.

Maintained, newly authored tests now cover grounded-label fixed points,
cycles, min-max numbering, and a complete Python discussion-game defense. The
real-browser suite additionally covers a multi-challenge defense and an
undecided cycle through the public interactive game. These tests use generated
in-memory graphs and do not copy the absent upstream fixtures.

The removed historical modules remain available in Git history for provenance
review. Do not restore the upstream fixtures until their redistribution terms
are resolved.

## Transient semantic compatibility check

On 2026-09-04, a disposable directory under `/tmp` combined the unmodified
historical ABDA-NL test modules from commit `e6a3062` with only the missing
`Tests/RuleFiles` directory from the fixed upstream commit `6e7a45c`. The test
process exercised the current engine and reported 20 passing tests in 1.15
seconds. No upstream fixture was added to the ABDA-NL worktree or commit. The
exact identities and result are preserved in the
[deterministic engine validation record](deterministic-engine-validation-20260904.md).

This result provides useful compatibility evidence for the deterministic
engine. It does not resolve the redistribution question or authorize copying
the upstream fixtures into ABDA-NL.
