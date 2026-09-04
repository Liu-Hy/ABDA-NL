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

## Test hygiene after the license decision

The default pytest suite currently collects the maintained `test_*.py` tests.
The four historical CamelCase test modules are not collected by that rule.
Three of them contain five self-contained passing tests. The fourth references
the 15 absent upstream fixtures and fails before reaching an assertion when run
directly.

After the license path is settled, either:

- restore the fixtures under authorized terms and modernize all four modules,
  or
- retire the historical modules and retain equivalent independently authored
  coverage in the maintained engine test suite.

Do not describe the missing-fixture module as a passing test suite until one of
these paths is complete.
