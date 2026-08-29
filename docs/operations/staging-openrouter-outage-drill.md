# Staging OpenRouter outage drill

State: fallback transition observed in live staging, read-only ledger recovery
audit pending

The reviewed implementation is in source commit
`448510936c69d485cf9b4e834adea69becf6b114` and image
`ghcr.io/liu-hy/abda-nl@sha256:11861402c8fa3fd677848f94155e29065ebafd9a4a76b03e41b1cf48312e5c58`.
The image workflow and provenance evidence are recorded in the
[release-candidate checkpoint](staging-release-candidate-20260829.md).
Gate 6 deployed that image as revision `abda-nl-stg-web--rc-4485109` and passed
its public acceptance checks on 2026-08-29.

This gate proves that a qualifying primary-provider outage reaches the selected
OpenRouter fallback and charges the same settled cost to the user's trial grant
and the owner-funded emergency budget. It does not damage or reconfigure the
CloudBank endpoint.

## Safety boundary

The command has the following fixed constraints:

- It runs only when `ABDA_ENVIRONMENT=staging`.
- Its required `--expected-origin` must exactly match
  `ABDA_PUBLIC_BASE_URL`.
- The deployed web revision must still have public OpenRouter failover
  disabled.
- It selects only the public `balanced` profile, the reviewed CloudBank Claude
  Sonnet 4.6 primary, and the reviewed OpenRouter Gemini 3.7 Flash fallback.
- It reads an active trial user's verified email from a hidden prompt or a
  selected environment variable. The email is absent from its JSON output.
- It is a dry run unless `--execute` and the exact confirmation are both
  present.
- The first deployed version used a fixed, content-free marker prompt with at
  most 32 output tokens.
- It temporarily enables the emergency budget database row only for this
  process. The public application revision remains unable to select fallback.
- It restores the row in a `finally` block after provider success or failure.

The dry run is:

```bash
python -m app.cli.outage_drill \
  --expected-origin https://demo.abda-nl.org
```

The operator must first deploy and accept that exact image through Gate 6. The
operator should then run the command inside the deployed container so it reuses
the exact image, restricted PostgreSQL role, catalog, and secret references. Do not
place the account email, OpenRouter key, database password, or any bearer token
in the command line. The guarded Azure gate supplies the container selection
and confirmation procedure.

## First live execution

The first Gate 7 execution reached the exact healthy revision and selected a
ready replica. Its preflight recorded 60,626 microUSD of trial spend, zero
OpenRouter spend, zero reservations, and a disabled emergency switch. The
synthetic CloudBank HTTP 503 then opened the expected circuit from
`cloudbank-claude-sonnet-4-6` to `openrouter-gemini-3.7-flash`.

OpenRouter returned a successful completion object, so the route and provider
checks passed and the metered client settled the call. The visible response did
not contain the marker, however, and the deployed command stopped before
printing its JSON receipt. The outer gate then completed its post-call metrics
snapshot, which proves that the temporary switch was disabled and that no
trial or emergency reservation or uncertain charge remained. It stopped at
receipt extraction and correctly refused a blind paid rerun.

The public OpenRouter model metadata identifies `google/gemini-3.7-flash` as a
mandatory-reasoning model with reasoning enabled at medium effort by default.
A total completion allowance of 32 tokens is therefore not a sound marker
test. The corrected implementation uses 2,048 tokens and audits the settled
call before evaluating visible marker text. If marker text is still missing,
it emits a content-free accounting receipt and exits distinctly instead of
discarding the successful accounting evidence.

`deploy/azure/gate7-marker-failure-recovery.sh` is specific to this first call.
It makes no provider call and no Azure configuration change. It verifies the
same positive delta in the aggregate trial and OpenRouter ledgers against the
recorded preflight, plus the final disabled and idle states. Its public model
metadata check is diagnostic only, so later catalog drift cannot invalidate
the accounting evidence. A successful recovery completes the accounting
portion of this live gate without paying for another request.

## Acceptance record

A successful JSON result must report all of the following:

- `result` is `OPENROUTER_OUTAGE_DRILL_PASSED`.
- `marker_verified` is true.
- The primary and fallback routes match the reviewed balanced profile.
- The per-call trial, emergency, and usage-event costs are equal and positive.
- The successful provider is OpenRouter.
- No emergency reservation remains.
- `openrouter_enabled_restored` is true.

Provider retries may create more than one finalized reservation. The audit uses
a unique request kind for this execution and compares the sum of every
provider-attempt record, rather than relying on a whole-account balance delta
that could be confused by a concurrent normal request.

After the drill passes, commit a sanitized record containing the source commit,
image digest, Container Apps revision, request identifier, route names, cost
totals, and final enabled and reservation states. Do not record the account
email, prompt response, provider key, database URL, or Azure secret values.

## Interruption behavior

If the command returns normally, including a provider rejection, it restores
the emergency budget row. If the container process is forcibly terminated
during the call, the public web revision still has failover disabled and cannot
spend through the temporarily enabled database row. Do not rerun the paid drill
blindly. First inspect the emergency budget and reservation state. An expired
pending reservation is conservatively charged by the existing startup
reconciliation policy before any retry.
