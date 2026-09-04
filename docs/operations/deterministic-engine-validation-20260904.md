# Deterministic engine validation, 2026-09-04

This record supplements the maintained unit, integration, and browser suites
with two bounded checks of the paper's deterministic reasoning core. Neither
check used a credential, called a model provider, changed Azure, or modified
the public service.

## Release identities

- Public service application source: `51702e175bd14d4cb54075808f839d173d561324`
- Local validation source: `1f088efc5b6450c35b588898279aef5dd9402d0a`
- `app/abda` Git tree for both sources:
  `34d703184eb9de6fa0c3c164fc8f0e9b3f733169`
- Public origin: `https://demo.abda-nl.org`
- Check time: `2026-09-04T09:09:02Z`

The local source contains later service tests and documentation. A Git diff
confirmed that `app/abda`, `app/scenario`, and `examples` were unchanged from
the public service source.

## Historical scenario compatibility

A disposable directory under `/tmp` combined the unmodified historical test
modules from ABDA-NL commit `e6a3062` with only the missing `Tests/RuleFiles`
directory from fixed upstream ABDA commit
`6e7a45c40150fbf6bb5377271bf238d8fcd32463`. It then ran these modules against
the unchanged current engine:

- `ConclusionWarrantedTests.py`
- `GroundedDiscussionGameTests.py`
- `GroundedExtensionTests.py`
- `MinMaxNumberingTests.py`

Result: 20 tests passed in 1.15 seconds. No upstream fixture was added to the
ABDA-NL worktree or Git history. This is compatibility evidence only. It does
not resolve the separate redistribution gate in the
[source license review](source-license-review.md).

## Public baseline parity

A read-only process fetched the public scenario list and every
`GET /scenarios/{id}` response. It independently compiled each same-version
bundled scenario with the local deterministic engine, compared the complete
`scenario` and `af` objects, and hashed canonical sorted JSON after equality
was established.

| Scenario | Canonical payload SHA-256 prefix | Result |
| --- | --- | --- |
| `popov_v_hayashi` | `f49208ac074c` | Exact match |
| `fire_prevention` | `c83794d99d26` | Exact match |
| `medical_ppi` | `1bfea6e2c8b2` | Exact match |
| `nba_rebuild` | `62390e88ec96` | Exact match |
| `fried_chicken_v1` | `52eb7939dc84` | Exact match |
| `fried_chicken_v2` | `6abb47a2c7c9` | Exact match |

Result: all six public baseline states exactly matched the local deterministic
engine. This proves parity for the bundled baseline payloads at the identities
above. Mutation behavior, authentication, model behavior, and future source
revisions remain covered by their separate gates.
