# Privacy preflight failure, September 5, 2026

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

`deploy/azure/diagnose-privacy-preflight.py` inspects that exact execution and
queries seven days of its Log Analytics evidence. The query returns only
numeric counts for fixed refusal messages, exception classes, platform failure
categories, and the runner traceback line number. It never retrieves raw log
text, starts a job, or changes account data or Azure configuration. Azure CLI
operations have a 70-second process limit; the log HTTP request has a
60-second total limit. The Log Analytics token travels through curl standard
input, never command arguments, files, or terminal output.

Run the downloaded, checksum-verified diagnostic with `python3`, in either the
existing Azure Cloud Shell session or a new authenticated session. Use
`python3 SCRIPT_PATH --preparation` for the current recovery step. No input or
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
