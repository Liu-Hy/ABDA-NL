# Privacy request operations

Status: implemented and present in the current staging image. Live operation
against an isolated disposable account remains an acceptance gate.

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

The inspect output contains only a 16-character account fingerprint, status,
timestamps, counts, and monetary totals. It contains no email, identity
subject, project content, token hash, or request content.

## Staging acceptance gate

`deploy/azure/gate11-privacy-acceptance.sh` turns the manual sequence below into
a bounded two-run staging acceptance. Run it only after the Gate 10 rollback
rehearsal has restored revision `abda-nl-stg-web--restore-6d0fb44`.

Prepare one disposable verified-email account as follows:

1. Do not activate trial credit and do not call a model from this account.
2. Create one project from a bundled public example.
3. Create one read-only share and one scoped MCP credential. Do not copy their
   bearer values into the operator record.
4. Sign out, then block this exact user in Auth0. Keep it blocked throughout
   both gate runs.

The first run asks for the account address through a hidden prompt. It checks
that the account has never received funded credit, exercises `inspect`, writes
an access export to a new mode-600 file inside the container, validates the
export without printing it, and removes the file. After the exact preparation
confirmation, it changes the account to `deletion_pending` and proves that all
active share and MCP access was revoked. A successful first run ends with:

```text
result: PRIVACY_ACCEPTANCE_PREPARED_WAIT_15_MINUTES
```

Keep the Auth0 user blocked and wait at least 15 minutes. Rerun the same pinned
gate. It recognizes the prepared state, refuses unsettled reservations, runs a
deletion dry run, and requires a separate exact deletion confirmation. It then
proves that the local user and private records are gone. Success ends with:

```text
result: LIVE_PRIVACY_EXPORT_AND_DELETION_VERIFIED
```

Delete the still-blocked disposable user from Auth0 only after the second
receipt succeeds. The gate never changes Azure configuration, secrets, DNS,
Auth0, trial limits, or provider routing.

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
