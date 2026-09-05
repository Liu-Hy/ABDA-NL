# Privacy request operations

Status: implemented in the source-security candidate. Live preparation against
an isolated disposable account passed on 2026-09-04 CDT. The minimum 15-minute
hold has elapsed, and the permanent-deletion phase remains. On September 5,
the revision 10 read-only deletion preflight failed before deletion began.
See [the failure diagnostic](privacy-preflight-failure-20260905.md) before retrying.

This runbook supports verified access exports and permanent deletion requests.
The operator tool is `abda-nl-privacy`. It never accepts an account email on the
command line, never prints that email, and does not write private content to
application logs. The service must be deployed from an image that contains the
tool before this runbook is used against staging or production.

## Intake and verification

1. Receive the request through `privacy@abda-nl.org`.
2. Ask the requester to confirm from the same verified address used by the
   ABDA-NL account. Never ask for an OTP, password, API key, share link, MCP
   token, or session cookie.
3. Assign a content-free reference such as `PRIV-20260828-001`. Store the
   request and verification evidence in the operator's private case record,
   not in the source repository or application logs.
4. In Auth0, open **User Management**, then **Users**, locate the exact verified
   address, and block the account before beginning a deletion. Do not delete
   the Auth0 user until the ABDA-NL database operation succeeds.

## Load the verified address without shell history

Run the tool in a private operator shell connected to the deployed application
database. Entering the address through the hidden prompt is preferred:

```bash
abda-nl-privacy inspect
```

For a noninteractive one-off job, provide the address through a secret-backed
environment variable named `ABDA_PRIVACY_USER_EMAIL`. Do not place the address
in a command argument, deployment name, source file, or ordinary environment
template.

The inspect output contains a pseudonymous 16-character account fingerprint,
status, timestamps, counts, and monetary totals. Treat that fingerprint as
private operator data because it is derived from the verified address. Do not
copy it into a shared release receipt. The output contains no email, identity
subject, project content, token hash, or request content.

## Staging acceptance gate

`deploy/azure/gate11-privacy-acceptance.sh` turns the manual sequence below into
a bounded two-run staging acceptance. The pinned gate currently accepts only
the source-security candidate revision `abda-nl-stg-web--harden-51702e1` and
exact image digest
`sha256:a0b3ba24aff06ecf461f86547131d86451c541e306a7ecfc278f280fcef5c0bc`.
It stops if the deployed application changes.

That pin is intentional. It keeps the already prepared account bound to the
same live code through permanent deletion. The newer account-suspension image
was never deployed, so it cannot invalidate or silently repeat the prepared
operation. It was superseded after WebKit exposed a keyboard focus defect. A
correctly licensed replacement image must include that correction before the
post-deletion deployment proceeds.

Prepare one disposable verified-email account as follows:

1. Do not activate trial credit and do not call a model from this account.
2. Create one project from a bundled public example.
3. Create one read-only share and one scoped MCP credential. Do not copy their
   bearer values into the operator record.
4. Sign out, then block this exact user in Auth0. Keep it blocked throughout
   both gate runs.

The staging gate locates exactly one account by the exact project and MCP
credential name `Privacy acceptance disposable`. It refuses zero or multiple
matches. It therefore does not ask for the email address or place it in the
shell, execution template, or shared receipt. The first run checks that the
account has never received funded credit, exercises `inspect`, writes an access
export to a new mode-600 file inside the isolated execution, validates the
export without printing it, and removes the file. After the exact preparation
confirmation, it changes the account to `deletion_pending` and proves that all
active share and MCP access was revoked. A successful first run ends with:

```text
result: PRIVACY_ACCEPTANCE_PREPARED_WAIT_15_MINUTES
```

The live first phase succeeded in execution
`abda-nl-stg-migrate-7tlx9gq`. Its wrapper verified a `Succeeded` execution,
unchanged job configuration, unchanged application configuration, no terminal
email input, and no model-provider call.

Keep the Auth0 user blocked and wait at least 15 minutes. Rerun the same pinned
gate. It recognizes the prepared state, refuses unsettled reservations, runs a
deletion dry run, and requires a separate exact deletion confirmation. It then
proves that the local user and private records are gone. Success ends with:

```text
result: LIVE_PRIVACY_EXPORT_AND_DELETION_VERIFIED
```

An initial revision 9 deletion attempt stopped before creating a deletion
execution because Azure's historical list response did not yield an exactly
matching full preparation template. Revision 10 no longer treats that response
shape as the hold authority. It first runs a read-only execution that checks
the durable account status, preparation timestamp, revoked bearer access,
settled reservations, and absence of trial usage. The permanent deletion
execution starts only after that preflight succeeds, and it repeats the same
checks before mutation. A failed read-only preflight can be retried safely.

Delete the still-blocked disposable user from Auth0 only after the second
receipt succeeds. The gate never changes Azure configuration, secrets, DNS,
Auth0, trial limits, or provider routing. Its shareable receipts omit both the
email address and its derived account fingerprint.

The Gate avoids the Azure Container Apps interactive WebSocket. It starts an
execution-only template override on the existing manual migration job, using
the approved application image and the job's restricted application-password
secret. Deletion uses one read-only preflight execution followed by the
mutating execution. These overrides run privacy code instead of the migration
command for those executions only. They do not change the saved job
configuration, and the Gate compares the before and after configuration to
prove that boundary. It hydrates list results through the execution detail API
before matching exact templates, resumes an exact active or successful
execution after a shell interruption, refuses an unrelated active execution,
and never automatically repeats a failed mutating execution. The database
status remains the authority between the preparation and deletion runs.

## Produce an access export

Create a private directory and write a new file. The tool refuses an existing
file or a parent directory that grants group or other permissions.

```bash
ABDA_PRIVACY_EXPORT_DIR="$(mktemp -d)"
chmod 700 "$ABDA_PRIVACY_EXPORT_DIR"
abda-nl-privacy export \
  --output "$ABDA_PRIVACY_EXPORT_DIR/access.json"
```

The JSON file is created with mode 600. It includes the account profile,
identity claims, private projects, share metadata, MCP credential metadata,
trial accounting, and model usage metadata. It deliberately excludes share
token hashes, MCP token hashes, provider API keys, cookies, and server secrets.
Transfer it only through the approved private response channel, then remove the
operator copy under the project's case-retention procedure.

## Prepare permanent deletion

Preparation is a separate mutation. It changes the local status to
`deletion_pending`, which invalidates browser and OIDC sessions, and revokes all
MCP credentials and share links. The command is a dry run unless `--execute`
and the exact confirmation are both present.

The cumulative release candidate also serializes project writes, new share
links, MCP credential creation, trial activation, and the final funded-credit
reservation before a provider call with this status change. It refreshes the
locked account row rather than trusting a status cached at the start of a
request. Share resolution independently requires an active owner. This closes
the stale-session window in which a request that authenticated just before
preparation could otherwise create durable state or new funded liability after
preparation committed.

```bash
ABDA_PRIVACY_REFERENCE='PRIV-20260828-001'
abda-nl-privacy prepare-delete \
  --request-reference "$ABDA_PRIVACY_REFERENCE"

export ABDA_PRIVACY_CONFIRMATION="PREPARE:$ABDA_PRIVACY_REFERENCE"
abda-nl-privacy prepare-delete \
  --request-reference "$ABDA_PRIVACY_REFERENCE" \
  --execute
unset ABDA_PRIVACY_CONFIRMATION
```

Run `abda-nl-privacy inspect` again. Permanent deletion is refused while any
trial or OpenRouter reservation is pending or while trial credit remains
reserved. Wait at least 15 minutes after preparation so requests that were
already in flight can finish, even when the first inspection is clear. A normal
in-flight call should settle promptly. Do not bypass this check. Investigate a
reservation that remains after its 15-minute expiry and reconcile it
conservatively before continuing.

## Permanently delete local data

Review the dry run, then use a new exact confirmation:

```bash
abda-nl-privacy delete \
  --request-reference "$ABDA_PRIVACY_REFERENCE"

export ABDA_PRIVACY_CONFIRMATION="DELETE:$ABDA_PRIVACY_REFERENCE"
abda-nl-privacy delete \
  --request-reference "$ABDA_PRIVACY_REFERENCE" \
  --execute
unset ABDA_PRIVACY_CONFIRMATION
unset ABDA_PRIVACY_USER_EMAIL
unset ABDA_PRIVACY_REFERENCE
```

Deletion removes the local user, identity bindings, project contents, share
records, MCP records, trial grant, and trial reservation details. Provider
usage and emergency reservation rows retain only anonymous operational and cost
fields. The global trial program keeps its historical activation, allocation,
and spend totals, so deletion cannot reopen funded capacity or reduce recorded
liability.

After the local receipt succeeds, delete the blocked user in Auth0. Confirm to
the requester that active application data is deleted. Explain that managed
database backups expire within 7 days and application logs within 30 days, as
stated in the privacy notice. Record only the content-free deletion receipt and
case reference in the operator case record.

## Failure and recovery rules

- A missing account, invalid reference, unsafe export directory, wrong
  confirmation, active account, or unsettled reservation produces no deletion.
- `prepare-delete` is idempotent for an already prepared account.
- A database error rolls back the current operation and emits a generic error
  without database credentials or private content.
- Do not manually edit rows, lower budget totals, delete provider usage events,
  or bypass the two-phase process.
- If local deletion fails, keep the Auth0 user blocked, retain the private case
  record, and retry only after diagnosing the database state.
