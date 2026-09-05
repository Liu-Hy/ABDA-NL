# Privacy preflight failure, September 5, 2026

## Current recovery result

Status: recovered deletion and database destination reviewed; the operator
confirmed deletion of the exact disposable Auth0 identity on September 5, 2026.
The privacy-recovery prerequisite is complete. Do not rerun preparation,
preflight, deletion, or account creation. The cumulative image rollout and the
other public-service gates remain separate, unfinished operations.

The final `READ_ONLY_PRIVACY_METADATA_COLLECTED` receipt supplied these
execution times (UTC), with all three executions in `Succeeded`:

| Execution | Operation | Started | Ended |
| --- | --- | --- | --- |
| `abda-nl-stg-migrate-7tlx9gq` | Preparation | 2026-09-04 05:18:35 | 2026-09-04 05:19:04 |
| `abda-nl-stg-migrate-w9hv7gt` | Deletion | 2026-09-04 16:35:18 | 2026-09-04 16:35:48 |
| `abda-nl-stg-migrate-iw6rmwz` | Read-only inspection | 2026-09-05 20:36:11 | 2026-09-05 20:36:45 |

The completed preparation preceded deletion by more than eleven hours,
exceeding the required fifteen-minute hold. The inspection followed deletion.
Every reported environment was an array with the expected PostgreSQL host,
an application-password secret reference, and no `ABDA_DATABASE_URL` override.
The host was
`abda-nl-stg-postgres-bgjhpbgw.postgres.database.azure.com`.

The original revision 8 and revision 10 runner hashes were rechecked against
the recorded execution classifications. Both runners construct the connection
URL using that host, fixed user `abda_app`, port 5432, and database `abda`.
The password is URL-encoded, so its contents cannot alter the destination.
The inspection runner uses the same destination construction. The reviewed
image does not set a competing database URL. Combined with the actual inner
preparation, deletion, and inspection receipts, this establishes the intended
database destination without retrieving a secret value.

The remaining `expected_password_ref: false` fields only establish that the
reference names did not equal the diagnostic's hard-coded
`app-database-password`. They do not show a wrong password or database. The
actual names and the reason for their difference remain unknown. This
destination review does not assert that the references were identical or that
the old diagnostic passed. Its exact-reference-name requirement was stronger
than necessary for establishing which database these reviewed runners used.

Auth0 cleanup is an operator-confirmed dashboard action, not an automated API
verification. No account email, token, or private project content is retained
in this record. The normal funded account was not the cleanup target.

## Earlier recovery evidence and diagnostic limits

The following records preserve the investigation as it unfolded. Statements
about pending work below describe that earlier state, not new instructions.

The operator's revision 3 `--history` receipt has recovered an actual successful
deletion, `abda-nl-stg-migrate-w9hv7gt`. Its recorded command is `privacy_delete`,
its embedded runner matches reviewed revision 10, and its image matches the
hardened service. Log Analytics reports one inner deletion success marker,
zero refusals, and exactly one deleted identity, project, share link, and MCP
credential. These are application database records, not a deletion of the
external Auth0 user. The reviewed runner prints success only after the privacy
CLI returns a committed deletion receipt with these counts.

This is positive evidence of a completed deletion, not merely an inference
from the later zero-match inspection. It provides a plausible explanation for
the later account-match refusal. The report does not include execution times
or a verified historical database binding, so it does not independently prove
the ordering and database continuity of every execution.

All four history records returned `database_input: unrecognized`. Revision 3
therefore reported zero *fully database-verified* deletions and exited 2,
despite the positive deletion receipt. That result does not mean the delete
job failed. Nor does it prove a database change. The sanitized receipt cannot
distinguish absent environment metadata from a different representation or
unexpected input. Do not assert an Azure omission or classifier root cause
without further evidence.

Revision 4 separates verified deletion receipts from full historical database
verification. It retains exit 2 and `database_input_chain_verified: false`
when the latter is unresolved. Missing environment metadata is now distinct
from unrecognized metadata; neither is accepted as a match. Focused local
regressions cover both shapes and the reported success-with-unknown-binding
case. No new cloud run is needed merely to reformat the receipt already supplied.

Do not rerun preparation, preflight, or deletion and do not recreate test
objects. Keep the exact disposable Auth0 identity blocked while its final
cleanup is pending. The remaining historical database-binding evidence can be
collected with the next read-only operator batch, without starting another job
or requesting raw environment values. Do not mark that evidence check, Auth0
cleanup, or the full public-service release complete yet. The source license
publication hold remains independent and unchanged.

Local verification for this reporting-only correction:

```bash
.venv/bin/ruff check deploy/azure/diagnose-privacy-preflight.py tests/test_privacy_failure_diagnostic.py
.venv/bin/pytest -q tests/test_privacy_failure_diagnostic.py tests/test_privacy_match_inspection.py tests/test_privacy_acceptance_gate.py tests/test_post_privacy_operator_gate.py
git diff --check
```

Lint passed, all 44 focused tests passed, and the diff check passed. These are
local regression results, not a new Azure verification. No application image,
cloud configuration, account data, destructive gate, or stable `main` code was
changed during this recovery update.

## Historical investigation

The operator ran helper revision 14 and Gate 11 revision 10 with both correct
confirmations. The read-only `preflight-delete` execution
`abda-nl-stg-migrate-n9lelb6` reached `Failed`. The wrapper stopped before
starting the deletion execution. The failure reason is not established by the
receipt. Keep the disposable Auth0 identity blocked pending diagnosis.

The operator's diagnostic receipt subsequently reported one runner refusal,
specifically `account_match_refused: 1`, with no traceback or database error
markers. The preflight reached the account query but did not find exactly one
matching account. This does not distinguish zero matches from multiple matches.
The revision 8 and revision 10 selectors have the same project, credential,
verified-email, account-state, and non-archived-project conditions.

Revision 2 of the diagnostic adds `--preparation` to inspect the earlier
`abda-nl-stg-migrate-7tlx9gq` execution instead. It classifies the saved command
and hashes the embedded runner source without executing it or printing its
arguments. It queries counts for the actual preparation, export, deletion, and
migration success markers. A successful Azure execution alone does not prove
which operation ran. The original wrapper's preparation result was inferred
from the requested phase and execution status; its inner receipt has not yet
been independently established. Do not claim the preparation failed or change
account selection until that evidence is available.

The operator then verified the original execution with revision 2. Its saved
command was `privacy_prepare`, its runner matched revision 8, its image matched
the reviewed image, and its logs contained one preparation success marker and
one validated-export marker. There were no refusal, deletion, or migration
markers. The original preparation is now independently confirmed. The
account-match discrepancy remains unexplained by logs alone.

The next operation is `deploy/azure/inspect-privacy-matches.py`. This starts one
execution of the existing manual job with the application database role and
the reviewed image. The runner enforces a SQL read-only transaction, counts
each selector condition, and exits without preparing or deleting an account.
It counts revoked shares and credentials within the original preparation's
execution interval to help distinguish the already prepared account from
other accounts with identical test names. These are diagnostic counts only,
not an alternate deletion selector. No account email, identifier, project
content, or credential value is printed. The wrapper retrieves only aggregate
log counts and requires the inner inspection receipt before reporting success.
The saved job configuration and web application are not changed. A second
inspection is unnecessary if the first execution merely awaits log ingestion;
retain its execution name when reporting any error.

The inspection completed in `abda-nl-stg-migrate-iw6rmwz`, with one verified
inner receipt and zero inspection errors. All selector counters were zero,
including named project owners, named credential owners, and all accounts
in `deletion_pending`. This rules out ambiguity or an archived named project
as the explanation at that snapshot. It does not prove account deletion:
an intervening deletion or a change in database inputs must be checked.

The next step at that point was diagnostic revision 3 with `--history`. It reads
seven days of the existing job's receipt counts, then compares recorded
commands, runner hashes, image identities, and database inputs for relevant
executions. It starts no job. A past deletion is accepted as evidence only
with a successful execution, recognized deletion runner, expected image and
database inputs, a deletion success marker, no refusal marker, and positive
deleted identity, project, share, and credential counts. The original
preparation and latest inspection database inputs must also match for the full
binding check. Its result is now recorded above. Do not repeat deletion or
declare the full privacy acceptance complete solely because selector counts are zero.

`deploy/azure/diagnose-privacy-preflight.py` inspects that exact execution and
queries seven days of its Log Analytics evidence. The query returns only
numeric counts for fixed refusal messages, exception classes, platform failure
categories, and the runner traceback line number. It never retrieves raw log
text, starts a job, or changes account data or Azure configuration. Azure CLI
operations have a 70-second process limit; the log HTTP request has a
60-second total limit. The Log Analytics token travels through curl standard
input, never command arguments, files, or terminal output.

For a future explicitly requested diagnostic, run the downloaded,
checksum-verified diagnostic with `python3`, in either the
existing Azure Cloud Shell session or a new authenticated session. Use
`python3 SCRIPT_PATH --preparation` to repeat the already completed historical
execution check only when needed. No input or
confirmation is required. Return its final status and exit code. Zero matching
logs produce `PRIVACY_EXECUTION_LOG_EVIDENCE_NOT_AVAILABLE`, not a successful
diagnosis. A completed diagnostic also does not establish successful deletion.

Do not rerun the failed job or infer the cause from local tests. Resolve the
reported failure category before changing the privacy workflow or requesting
another deletion attempt.

References:

- [Azure jobs log filtering](https://learn.microsoft.com/en-us/azure/container-apps/jobs-get-started-cli)
- [Container Apps log tables](https://learn.microsoft.com/en-us/azure/container-apps/log-monitoring)
- [Log Analytics query API](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/api/request-format)
