# Development source security checkpoint, 2026-09-02

State: source scan clean, immutable image deployed, and live audit verified

This checkpoint records both source-level security evidence and the later live
acceptance of that exact image. The public service now runs
`abda-nl-stg-web--harden-51702e1`, built from source commit `51702e1`.

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

## Initial immutable image evidence

The annotated tag
`service-image-staging-source-security-20260902-182221` identifies source
commit `c173dd5983ba209b17c585c0c82aeb33c2e49028`. The tag-triggered
[image workflow run 33666791617](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33666791617)
reran the complete tests and dependency audits, built the production image,
pulled and smoke-tested its exact digest, and published GitHub build
provenance.

- image: `ghcr.io/liu-hy/abda-nl@sha256:ecf7531064fe6f86d3d647e9f0239bfbe5e082d71c5fcdd5e7e7fb91e9b32a64`
- attestation: [44790406](https://github.com/Liu-Hy/ABDA-NL/attestations/44790406)
- OCI source: `https://github.com/Liu-Hy/ABDA-NL`
- OCI revision: `c173dd5983ba209b17c585c0c82aeb33c2e49028`
- OCI license: `MIT`

An independent anonymous registry fetch returned that exact manifest digest
and all three labels. The GitHub attestation verifier accepted the digest
against `Liu-Hy/ABDA-NL`.

## Superseding exception-diagnostic hardening

A final review found that four unexpected-error handlers still used automatic
exception logging. Although ordinary request and model-result fields were
already sanitized, an arbitrary parser or database exception message could
contain user-supplied text. Commit
`51702e175bd14d4cb54075808f839d173d561324` replaced those paths with a
shared safe diagnostic that records only the exception class and the final
internal filename, function, and line number. It never records the exception
message or a traceback.

The new regression suite injects a deliberately private email and bearer-like
string into an exception, then proves that neither the MCP response nor the
captured log contains it. A source invariant also forbids `log.exception` in
application code. The complete local suite passed with 705 tests and five
intentional skips. The complete seven-job
[CI run 33672007813](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33672007813)
and [CodeQL run 33672007757](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33672007757)
passed, and the repository reported zero open code-scanning alerts.

The annotated tag
`service-image-staging-safe-exceptions-20260902-191532` identifies that exact
commit. [Image workflow run 33672235004](https://github.com/Liu-Hy/ABDA-NL/actions/runs/33672235004)
reran the complete test and dependency-audit boundary, built the production
image, pulled and smoke-tested its exact digest, and published GitHub build
provenance.

- image: `ghcr.io/liu-hy/abda-nl@sha256:a0b3ba24aff06ecf461f86547131d86451c541e306a7ecfc278f280fcef5c0bc`
- attestation: [44802693](https://github.com/Liu-Hy/ABDA-NL/attestations/44802693)
- OCI source: `https://github.com/Liu-Hy/ABDA-NL`
- OCI revision: `51702e175bd14d4cb54075808f839d173d561324`
- OCI license: `MIT`

The GitHub attestation verifier accepted this newer digest against
`Liu-Hy/ABDA-NL`. This image superseded the earlier candidate for Azure. The
earlier record remains above as historical evidence and is not relabeled as
evidence for the newer source.

## Azure deployment and live audit

On 2026-09-04 UTC, source-security Gate revision 2 deployed the exact attested
digest above. Azure single revision mode kept the prior healthy revision
serving until `abda-nl-stg-web--harden-51702e1` was provisioned with one ready
replica and reported healthy. The Gate proved that the transition changed only
the web image and revision suffix. It did not rerun a migration or change a
secret, trial limit, provider-routing setting, scaling rule, probe, database,
DNS record, certificate, or Auth0 setting. Public HTTPS acceptance passed and
the managed filesystem save boundary remained rejected without mutation.

The immediately following read-only Gate 9 revision 7 bound its checks to the
same source commit, image digest, and Azure revision. It verified HTTPS,
security headers, policy pages, protected metrics, the five-connection
database pool, trial and OpenRouter accounting, and 30-day Log Analytics
retention. Its 48-hour count-only query observed 28,898 records, including 36
from the new revision and 24 current-revision request records. It found zero
query-string markers, email-like values, bearer-like values, share fragments,
OIDC codes, provider-key-like values, or private identifier field names.

At the audit instant, one trial account had been allocated 5,000,000 microUSD,
with 307,716 microUSD settled against the funded ledger. The isolated outage
drill remained recorded at 149 microUSD on the OpenRouter emergency ledger.
The release checker passed without calling a model, displaying a protected
secret, printing raw log messages, or changing Azure configuration. The final
receipt was `RELEASE_AND_OBSERVABILITY_AUDIT_VERIFIED`.

## Remaining release boundary

The hardened image deployment and its first live audit are complete. The
remaining release sequence is the disposable-account privacy acceptance,
friendly apex and `www` redirects, compatible rollback and restoration,
production-cap promotion after email-capacity confirmation, and the final
promoted-state audit. These phases are pinned in
[the final operator batch](final-operator-batch.md). Earlier live BYOK and
browser evidence remains applicable because the deployment Gate proved the
application contract unchanged, but it is not relabeled as a new browser run.
