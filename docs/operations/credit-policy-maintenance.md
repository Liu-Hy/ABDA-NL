# Credit policy maintenance

The public program has at most 100 introductory grants of $5, with a $500
cumulative allocation ceiling. The five exact named identities have one $50
lifetime allocation each, from a separate $250 pool. An unavailable or retired
allocation must not prevent verified sign-in, private project access, or BYOK.
Explicit claims still report ineligibility. Neither eligibility program grants
curator privileges. OpenRouter has its own independent emergency budget.

## Retention and migration 0007

The owner selected no repeat introductory grant after account deletion,
including a retired named beneficiary claiming ordinary public credit.
Migration `20260910_0007` adds keyed eligibility markers for normalized verified
email and stable `(issuer, subject)` identity. Their HMAC key is
`ABDA_CREDIT_ELIGIBILITY_PEPPER`, a dedicated, stable secret of at least 32
characters in hosted environments. Do not print it or store it in Git.

Startup seeds existing grants and known named retirements without resetting
counters. New claims record markers in the same transaction as allocation.
Deleted accounts lose their user binding; the pseudonymous marker, its type,
and claim time remain for the lifetime of these introductory-credit programs.
They serve only repeat-grant prevention. They are not anonymous data or proof
that wholly different verified identities belong to different people. Access
exports disclose marker purpose, types and retention without exporting digests.
When the programs are permanently retired, an operator can remove their markers
and key together after disabling all future grants and reviewing retention.

The original key must remain available while markers enforce eligibility.
Startup and grant operations compare a stored key fingerprint and fail closed
on mismatch. Rotating the session or MCP token secret does not rotate this key.
Changing it cannot be a routine secret replacement: retired identifiers are no
longer recoverable, so deleting markers or re-keying only active users would
allow repeat claims. A future key rotation requires a reviewed versioned key
scheme that continues to check every retained marker generation.

Earlier public deletions removed their verified identities. Anonymous program
totals and old truncated display fingerprints cannot reconstruct valid keyed
markers. Do not claim complete historical coverage or guess deleted addresses.
Known retired named slots remain protected by their original entitlement rows.

Before hosted activation, apply the migration using the migration role, grant
the restricted web role its existing CRUD permissions on the two new tables,
provide the dedicated key, and verify initialization with the updated release.
Stop older replicas and jobs that can grant or delete accounts before accepting
new writes. Mixed-version writers would bypass retention. Keep schema and key
in compatible rollback plans. Downgrade refuses to remove populated markers.

## Fixed allocation mismatch

Boot must refuse a named program whose fixed dimensions differ from the code.
Do not update amounts to make startup pass or reset an activation counter.
Inspect the three policy dimensions and current grants, pending reservations,
spent totals, retired entitlements and program attribution with the migration
role. Use a backup and a rehearsal database for any repair.

If the policy is unchanged, restore the compatible configuration and release.
If the owner changes the policy, prepare an explicit transactional migration
with expected old values and post-migration conservation assertions. Drain all
incompatible replicas and jobs before applying it. Preserve every prior charge,
pending liability and retired entitlement; maintain the separate public, named,
evaluation and emergency limits. Stage that migration and compatible recovery
before deployment. There is intentionally no generic command to overwrite fixed
allocations. Existing named transfers use
`python -m app.cli.reconcile_named_credit` for preview, then `--apply` only after
the writer gate and ledger review succeed.

## Preparing exact-target rollout artifacts

Both `deploy/azure/inspect-named-credit.py` and `prepare-revision-rollout.py`
require `--target-file` containing exactly these JSON fields: `subscription`,
`tenant`, `operator`, `resource_group`, `app`, `job`, `postgres`, `database`, and
`app_login`. Use the deployment's verified values. Both tools compare the Azure
identity and full resource identifiers, including subscription and group, with
this explicit configuration. The restricted login and PostgreSQL hostname must
also match. Institutional eligibility comes from `app/services/credit_policy.py`.

Preparation defaults to stage and preview artifacts. Add `--include-activation`
only after incompatible writers are drained. It reads every page of the selected
app's revisions and replicas, plus every job and job execution in the target
resource group. It rejects active or remaining incompatible web replicas,
unknown or inconsistent inventory, automatic or incompatible job templates, and
nonterminal job executions. Accepted writer images must match the explicitly
supplied, independently reviewed candidate or recovery digests. Inactive old
revisions with zero replicas may remain for historical inspection. The source
APIs expose the [revision inventory](https://learn.microsoft.com/en-us/rest/api/resource-manager/containerapps/container-apps-revisions/list-revisions?view=rest-resource-manager-containerapps-2025-01-01),
[replica inventory](https://learn.microsoft.com/en-us/rest/api/resource-manager/containerapps/container-apps-revision-replicas/list-replicas?view=rest-resource-manager-containerapps-2025-01-01),
and [job execution pages](https://learn.microsoft.com/en-us/rest/api/resource-manager/containerapps/jobs-executions/list?view=rest-resource-manager-containerapps-2025-01-01).

Ready revisions and reconciliation-apply files are emitted only after this
check passes. The manifest records its scope, time and counts. This is a
preparation-time check, not a lock on Azure: rerun it immediately before applying
artifacts, prevent parallel deployments or manual job starts, and verify the
live schema separately. A shared resource group containing unrelated jobs may
require a narrower reviewed deployment boundary before activation can proceed.

The existing `credit-eligibility-pepper` secret is reused across web and job
configuration. Initial provisioning requires `--eligibility-key-file`, an
owner-only file; the preparer never generates a new key. A supplied replacement
or divergent existing keys stops preparation. Protected output includes separate
application and job secret patches, restricted reconciliation environments,
readable runner files, and their SHA-256 hashes. Apply the secret configurations
before templates referring to them. Base64 encodes the reviewed runners for
transport only. Keep the output directory outside the checkout.

## Sweep expired reservations without restarting

Run `python -m app.cli.reconcile_stale_credit` with the restricted application
database configuration to preview, then add `--apply` to commit. This operator
command makes no provider calls and prints only counts and assessment policy.
It conservatively charges each expired reservation in full, including the
independent emergency liability, with locked rows and one transaction. Repeating
it is idempotent; unexpired reservations remain pending. Missing or inconsistent
accounting aborts the transaction. Preview does not change counters.

An `expired_charged` amount is a conservative assessment, not a confirmed provider
invoice. Review provider evidence before crediting a verified difference; the
credit must preserve all program, user and emergency accounting relationships.
Elapsed time alone does not justify releasing uncertain liabilities.
