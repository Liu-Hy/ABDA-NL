# Development source security checkpoint, 2026-09-02

State: source scan clean; publication and Azure deployment of the replacement image pending

This checkpoint records source-level security evidence without treating it as
evidence for the older image that Azure currently serves. The public service
continues to run `abda-nl-stg-web--secure-b873112` until a later, explicit
image-only deployment.

## Static analysis

Commit `6d9341fff8c0bcfb4b52de3cfa5e64c2aba1774a` added a pinned Python
CodeQL workflow using the `security-extended` query suite. The first analysis,
[run 33664994392](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33664994392),
reported 15 findings across 50 rules:

- 12 possible log-injection paths involving request or model-derived fields
- two test assertions that used URL substring membership
- one evaluator route-list field that CodeQL classified as sensitive billing
  metadata

No finding was dismissed. Commits `51fed774671568f894aa9622d0066c68b409ca99`
and `a114c0315faec1447e1d70cb56c76605c4b1d06b` removed private,
high-cardinality identifiers and untrusted stop details from service logs,
kept only the fixed event and aggregate accounting fields needed by operators,
made both URL assertions exact, and limited the route-list command to its
public selector fields. The detailed evaluation report and validated catalog
still retain billing information for authorized operator review.

[CodeQL run 33666138020](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33666138020)
then reported zero findings across the same 50 rules. The GitHub code-scanning
API independently returned zero open alerts for `refs/heads/development`.

Commit `c173dd5983ba209b17c585c0c82aeb33c2e49028` made that clean state a
CI requirement. The workflow saves the generated SARIF result, refuses a
missing report, and fails when the report contains any result. It runs on each
push to `development` and on pull requests targeting `development`. Scheduled
events are intentionally omitted because
[GitHub runs scheduled workflows only from the default branch](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule),
while the stable paper artifact remains the default `main` branch.

[CodeQL run 33666397796](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33666397796)
passed the explicit zero-result check. Its uploaded analysis ID `1713525311`
records zero results across 50 rules for commit `c173dd5`.

The complete seven-job
[CI run 33666397729](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33666397729)
also passed for that commit. It covered both supported Python versions, the
complete test suite, both browser engines, PostgreSQL 16, deployment artifacts,
dependency audits, lock regeneration, and the complete-history secret scan.

## Complementary verification

The focused regression suites passed after each logging change. The complete
local suite then passed with 692 tests and five intentional skips. Both the
Python 3.10 and Python 3.13 hash-locked CI paths passed for commit `a114c03`,
along with PostgreSQL 16, Chromium, Firefox, deployment-artifact, and complete
history secret-scanning jobs in
[CI run 33666137858](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33666137858).

Local `pip-audit` checks independently reported no known vulnerability in any
of the four runtime and development lock files:

- `requirements.runtime.lock`
- `requirements.lock`
- `requirements.runtime.py310.lock`
- `requirements.py310.lock`

The repository already published a private-reporting policy in `SECURITY.md`,
but its GitHub Private Vulnerability Reporting setting was disabled. The
setting was enabled and read back through the GitHub API on 2026-09-02. Public
researchers can now use the documented private advisory form instead of
[disclosing an unpatched issue publicly](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configure-for-a-repository).

## Artifact boundary

This checkpoint does not change Azure, DNS, Auth0, Resend, trial limits,
OpenRouter settings, the database, or the currently deployed image. Before
calling the hardening live, publish one immutable image from the final source
commit, verify its digest and provenance, deploy only that image, then rerun
public release checks and the count-only sanitized-log audit. Earlier live
BYOK and browser evidence remains useful for unchanged behavior, but it must
not be relabeled as execution evidence from the new image.
