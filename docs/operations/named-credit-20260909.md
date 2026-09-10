# Named administrator credit

The five institutional accounts below receive a $50 total lifetime grant.
Previous spending and pending reservations remain deducted. An existing $5
grant therefore receives $45 more credit. This does not grant scenario curator
permissions.

| Account | Verified email |
| --- | --- |
| Haoyang | `hl57@illinois.edu` |
| Bertram | `ludaesch@illinois.edu` |
| Shawn | `bowers@gonzaga.edu` |
| Martin Caminada | `caminadam@cardiff.ac.uk` |
| Timothy McPhillips | `tmcphill@illinois.edu` |

Email matching uses the same normalized, lowercase identity as sign-in. Each
allocation binds once to the internal account. A later verified email change
preserves that allocation, and another account cannot reuse the original
address to claim it again. Suspended and unverified accounts cannot receive
credit. The policy is in
[credit_policy.py](../../app/services/credit_policy.py).

Permanent account deletion removes the account link while retaining that the
named allocation was consumed. Re-registering does not mint another grant.
The account access export includes its named entitlement while the account
exists.

The `administrators` program has five places and a $250 allocation limit.
The public `global` program keeps its configured 100 places and $5 grant,
totalling $500. Moving a prior public grant releases its place and allocation
from that public pool. The independent OpenRouter emergency budget is not
changed by this policy or its reconciliation command.

## Rollout and existing accounts

Use an immutable implementation image that includes migration
`20260909_0006` and the matching account, privacy, and reservation code. The
old catalog-only migration bridge is no longer valid. Managed startup requires
the database revision to match the image's migration head exactly.

The temporary rollout switch `ABDA_NAMED_CREDIT_AUTO_ACTIVATE` defaults to
`true`. Set it to `false` only for the first `0006` rollout. Verified sign-in
and explicit credit activation then preserve existing public grants and use
the ordinary public policy for new grants. They do not bind or transfer named
credit. The switch does not reverse an existing named allocation, alter its
balance, or disable ordinary reservation settlement. Explicit reconciliation
preview and application bypass this switch while retaining the eligibility
and accounting checks.

Use this two-phase rollout:

1. Inventory every web revision, auxiliary Container App, Container Apps job,
   active job execution, and operator command that can write to this database.
   Record image digests, commands, trigger types, and active executions without
   recording credentials. Verify that no named grant or bound entitlement
   already exists. Prepare the new image with
   `ABDA_NAMED_CREDIT_AUTO_ACTIVATE=false` before any of its replicas start.
   Without this setting, a sign-in or explicit credit activation can transfer
   a grant immediately, before the reconciliation command below runs.
2. Update the manual migration job to that same implementation image. Run
   `/opt/venv/bin/python -m app.cli.migrate` in its existing protected admin
   environment. This upgrades the schema and then provisions the restricted
   application role. It grants table DML on `named_credit_entitlements`, keeps
   `alembic_version` read-only to the app, and establishes default privileges
   for tables created by that migration role. Bare `alembic upgrade head`
   alone does not perform this role provisioning.
3. Verify revision `20260909_0006` and the restricted role's SELECT, INSERT,
   UPDATE, and DELETE privileges on the new table. The application role must
   still lack object creation, ownership, and administrative privileges. A
   migration job reporting success from an older image is not this check.
4. Start the new web revision with the switch still `false` and zero public
   traffic. Verify readiness and the unchanged public allocation before
   shifting traffic to it. Running old replicas can finish their public-pool
   requests while no named transfer has occurred. The schema upgrade does
   make an old `0005` replica unsafe to restart, so complete the forward
   cutover promptly using the prepared `0006` recovery image if needed.
   Database initialization seeds the five identity slots and fixed program,
   but does not allocate existing users by itself. It also settles expired
   reservations, so even a zero-traffic web revision is a database writer.
5. Deactivate the old web revisions and confirm that their replicas and
   requests have stopped. Upgrade auxiliary writers or keep them stopped,
   including scheduled triggers and active job executions. Preview and apply
   named credit using the new image and the protected restricted application
   environment. Do not give this command the migration administrator
   credentials. Run `--apply` only after every remaining writer is compatible.
6. Deploy the same compatible code with
   `ABDA_NAMED_CREDIT_AUTO_ACTIVATE=true`, verify affected account balances,
   and retain a compatible recovery image. Replicas from the first phase may
   overlap this revision safely: the false setting preserves any named grant
   that has already been transferred.

Do not put database credentials in shell arguments. In the protected
application environment, run:

```sh
/opt/venv/bin/python -m app.cli.reconcile_named_credit
/opt/venv/bin/python -m app.cli.reconcile_named_credit --apply
```

The first reconciliation command is a preview. It rolls back all work,
including program seeding if needed. Review its account identities, previous
and new program, grant amounts, and preserved spent/reserved values. `--apply`
commits all eligible allocations in one transaction. A missing registration,
unverified email, or inactive account appears separately in the report.
Repeating the command does not add another grant. With automatic activation
enabled, new verified sign-ins and explicit credit activation also apply the
policy idempotently. If named allocations already exist, do not use the
temporary switch to justify running an incompatible old image.

During a transfer, settled and pending reservation identifiers, costs,
timestamps, and statuses remain unchanged. Their program attribution moves
with the grant so subsequent settlement, release, or conservative crash
recovery charges the correct pool. Public and administrator allocation and
spending totals move atomically. Row locks and the SQLite billing lock protect
concurrent activation, reconciliation, and usage. A grant already above $50 or
an inconsistent ledger requires operator review rather than reducing credit.

The relevant writer paths are:

| Entry point | Accounting or identity behavior |
| --- | --- |
| Browser chat/edit and MCP `ask_project`/`propose_project_edit` | Reserve before dispatch and settle or release through `llm_billing.py` and `trials.py`. |
| Web startup or a job calling `initialize_database()` | Seed policy rows and charge expired reservations through `reconcile_stale_llm_reservations()`. |
| Verified sign-in and `/api/trial/activate` | Bind a named entitlement and transfer any existing grant when automatic activation is enabled. |
| `reconcile_named_credit --apply` | Transfer all currently eligible accounts atomically. |
| Privacy deletion and outage-drill operator commands | Mutate account or reservation state and must use the compatible image. |

The repository defines one manual migration job and no dedicated scheduled
reservation worker. Live auxiliary jobs must still be inventoried because
they may have been created outside these templates. The migration command
itself does not settle reservations or allocate named credit.

After a transfer, any recovery image must retain settlement by
`reservation.program_key`, permanent entitlement binding, and the matching
privacy behavior. Earlier images that always settle into `global` cannot
safely serve administrator grants. After the schema upgrade, an old image
that requires head `0005` cannot be restarted as a recovery image either.
Removing the entitlement table is refused once any allocation has been bound,
including a retired one. Recovery uses compatible code without downgrading
the schema or reversing grants.

The current implementation can serve as a `0006` recovery image with
`balanced` as its sole public profile and `ABDA_LLM_DEFAULT_PROFILE=balanced`.
Model admission is independent of credit accounting. Preserve the same
verified CloudBank and OpenRouter routes and existing budget settings in that
image. Validate the actual image digest, role grants, readiness, and ledger
totals before recording it as a live recovery target. An offline source test
does not establish that a particular deployed image is ready.

Record the preview and application report in protected operational storage.
After application, verify `/api/trial` for an affected account and the program
totals. `tests/test_named_credit.py` covers each named identity, unchanged
public capacity, preserved usage, pending and expired reservations, duplicate
claims, concurrent activation, identity binding, and ineligible accounts.
`tests/test_named_credit_cli.py` checks that preview writes nothing and repeated
application stays idempotent. `tests/test_named_credit_recovery.py` exercises an
actual `0005` to `0006` upgrade, initialization before transfer, settlement
after transfer, and a later recovery restart. The named-credit tests also
cover mixed-version public grants, preview/apply with the temporary switch,
and overlapping compatible replicas after transfer. These are local receipts,
not evidence that a particular live account has already been reconciled.
