# Revision rollout and administrator credit

Prepared September 9, 2026. Hosted reads completed September 10 at 02:47 UTC.
The image rollout, schema migration, hosted secret changes, and credit
reconciliation described here have not been applied. The separate approved
Foundry capacity change is recorded in the
[model deployment addendum](model-deployment-plan-20260909.md).

## Verified starting point

The only Container App in `abda-nl-staging` is `abda-nl-stg-web`. It uses
Single revision mode, with healthy revision
`abda-nl-stg-web--symbols-c6123d1` and image
`ghcr.io/liu-hy/abda-nl@sha256:a5edbbae91c9eb0ed2afcba2e4e179b9388ea858d75c71f14206d04425c50d59`.
Its scale range is one to three replicas. The only Container Apps job in
the resource group is the manual `abda-nl-stg-migrate`, currently using
`ghcr.io/liu-hy/abda-nl@sha256:c3f6ec80972850d30850ec2e72d28fd673e835187bebdc45a8f9cda4a8ad1a55`.
No scheduled or event jobs, or additional Container Apps workers, were found
in this resource group. Repeat this inventory immediately before release.

The existing migration job ran one execution-only read probe between
02:37:07 and 02:37:37 UTC. It succeeded under the restricted application
database role, with PostgreSQL confirming an explicit read-only transaction.
The job's persistent image, entrypoint, credentials, resources, and trigger
configuration were preserved. This was a `SELECT` inspection, not a migration
or reconciliation. Container console access returned the known handshake 404,
so the existing job supplied the private database path without opening any
network access. Azure documents that an
[execution template override](https://learn.microsoft.com/en-us/azure/container-apps/jobs)
applies to that execution, replacing its whole template.

The live schema is `20260908_0005`; `named_credit_entitlements` is absent.
Of the [five approved institutional identities](named-credit-20260909.md),
one is registered, active, and verified, with an existing $5 public grant.
Four have not registered. The registered account has prior settled usage and
no pending reservation. The public grant and program totals reconcile, and
there are no pending reservations in the database. The individual balances
and transaction counts are retained in the protected operational receipt,
outside the checkout.

Reconciliation must raise the existing account's total grant to $50 while
preserving spending. The four other slots remain available for future verified
registration; do not create placeholder users. Transfer the existing grant
and all its reservation attribution into `administrators` atomically. Keep
public trial capacity and configured budget unchanged. Do not alter the
independent OpenRouter emergency budget. Repeat the read immediately before
applying credit, because normal public usage can change these numbers.

## Images and accounting transition

Build and verify a recovery image from the completed implementation with
schema 0006, named entitlements, program-aware reservation settlement and
release, and only the historically qualified Sonnet 4.6 public selection.
Record its exact source commit and immutable GHCR digest. Build the final
catalog promotion as a separate commit and image after its CloudBank feature
qualification completes. Both images must pass the relevant migration,
accounting, recovery, and managed-startup checks. The recovery digest is an
actual tested artifact, not the historical 0005 image.

The two-phase setting is `ABDA_NAMED_CREDIT_AUTO_ACTIVATE`. Its default is
`true`. Set it explicitly to `false` in the first 0006 web revision. That
suppresses automatic named binding on verified sign-in and trial activation,
while ordinary public grants and their settlement continue to work. Explicit
reconciliation preview/apply bypasses the setting. A false 0006 replica also
preserves an existing named grant, so the later false/true overlap is safe.
The [accounting runbook](named-credit-20260909.md) describes this contract.

Verify that no named allocation is bound or transferred before beginning the
mixed-version stage. After migration, an already running 0005 process can
continue handling the unchanged public accounting state. Its startup check
does not accept schema 0006, however, so it cannot be restarted as recovery.
Keep the verified 0006 recovery image ready before migrating. A restart during
this brief transition requires forward deployment of that compatible image.

Once the first 0006 revision is healthy, confirm that every old web replica is
gone and no old job execution is running. Single revision mode normally
[keeps the previous revision until the new one is ready](https://learn.microsoft.com/en-us/azure/container-apps/revisions),
but that traffic behavior alone is not proof that every old database writer
has stopped. Do not apply credit before confirming process termination.
Container Apps sends termination signals during
[revision deactivation](https://learn.microsoft.com/en-us/azure/container-apps/application-lifecycle-management);
wait for the old replicas to disappear, then inspect pending reservations.

Run explicit reconciliation only after all remaining writers use 0006-aware
code. Then promote the `true` revision. At this point both sides of the rollout
understand the administrator program. The final qualified catalog image can
be promoted afterward without another accounting transition.

## Provider credentials and protected request preparation

The Azure sanity check followed the Azure sections of
[cloudbank-llm-setup](https://github.com/Liu-Hy/cloudbank-llm-setup). It privately
matched the root `.env` default GPT and Claude endpoint/key pairs to one
Succeeded AIServices resource in the pinned funded subscription. The scoped
Opus 5 endpoint/key maps to a separate Succeeded AIServices resource in that
same subscription, with the exact `claude-opus-5` deployment present. Actual
resource keys matched the configured keys. This verifies endpoint/auth/funding
lineage; model behavior is established by the separate paid acceptance.
The hosted `foundry-api-key` secret was also checked privately and exactly
matches that validated root default key. Its current `AZURE_OPENAI_API_KEY`
reference and Anthropic endpoint are valid. The renderer nevertheless pins
both adapters' endpoint/key mappings explicitly and refuses a mismatched
default secret, so it does not depend on inherited environment configuration.

The GCP audit separately verified the current CloudBank identity, matching
project and quota project, billing, enabled API, prediction permissions, and
standard ADC refresh through the Vertex adapter. Use that existing protected
ADC file for hosted Vertex authentication. It does not require a new external
account or a new GCP identity setup.

The [request renderer](../../deploy/azure/prepare-revision-rollout.py) performs
read-only Azure inspection and writes mode-600 JSON into a new mode-700
directory outside the checkout. It verifies the pinned operator/subscription,
expected ready revision, immutable images, existing app/job contracts, private
credential file permissions, and matching CloudBank ADC quota project. It reads
existing secret values privately so the complete secret collection is preserved.
It does not deploy, migrate, register a feature, accept terms, change billing,
or make an inference call. Run it after the actual image digests are available:

```bash
set +x
umask 077
bash deploy/azure/agent-azure-session.sh status
.venv/bin/python deploy/azure/prepare-revision-rollout.py \
  --expected-revision abda-nl-stg-web--symbols-c6123d1 \
  --recovery-image "$ABDA_REVISION_RECOVERY_IMAGE" \
  --candidate-image "$ABDA_REVISION_CANDIDATE_IMAGE" \
  --revision-prefix "$ABDA_REVISION_PREFIX" \
  --adc-file "$ABDA_REVISION_VERIFIED_ADC_FILE" \
  --output-directory "$ABDA_REVISION_PLAN_DIRECTORY"
```

The digest and file variables are filled by the release agent from verified
artifacts and protected local configuration. No credential value is put in a
shell argument. The renderer preserves auth settings, ingress, domains,
certificates, probes, scale, existing environment variables, mounts, and
unrelated secrets. For the first recovery-only release, pass its verified
digest for both image arguments and regenerate the plan in a new private
directory once the final candidate exists. Its new configuration is:

| Field | Source or reference |
| --- | --- |
| `AZURE_OPENAI_ENDPOINT` | Existing validated root `.env` endpoint |
| `AZURE_OPENAI_API_KEY` | Existing verified secret reference `foundry-api-key` |
| `AZURE_ANTHROPIC_ENDPOINT` | `/anthropic` endpoint of the same default resource |
| `ANTHROPIC_FOUNDRY_BASE_URL` | The same default Anthropic endpoint |
| `AZURE_ANTHROPIC_API_KEY` | Existing verified secret reference `foundry-api-key` |
| `AZURE_OPUS5_ENDPOINT` | Existing validated scoped root `.env` endpoint |
| `AZURE_OPUS5_API_KEY` | Secret reference `foundry-opus5-api-key` |
| `ABDA_CLAUDE_PROVIDER` | `foundry` |
| `GOOGLE_APPLICATION_CREDENTIALS` | `/var/run/abda-gcp/adc.json` |
| `GOOGLE_CLOUD_PROJECT` | Validated CloudBank project |
| `GOOGLE_CLOUD_QUOTA_PROJECT` | The same validated project |
| `GOOGLE_CLOUD_LOCATION` | `global` |
| `ABDA_NAMED_CREDIT_AUTO_ACTIVATE` | `false` for stage, `true` after reconciliation |

The new application secrets are `foundry-opus5-api-key`, from the existing
scoped key, and `gcp-adc-json`, containing the existing ADC JSON. The volume
contains an explicit list with only the ADC secret:

```json
{
  "name": "gcp-adc",
  "storageType": "Secret",
  "secrets": [{"secretRef": "gcp-adc-json", "path": "adc.json"}]
}
```

The web container mounts it with
`{"volumeName":"gcp-adc","mountPath":"/var/run/abda-gcp"}`. This follows the
[REST volume schema](https://learn.microsoft.com/en-us/rest/api/resource-manager/containerapps/container-apps/update?view=rest-resource-manager-containerapps-2025-01-01)
and [explicit secret-volume selection](https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets).
Do not omit the `secrets` list, which would mount all application secrets.
Secret updates are application-scoped; attach the new references and volume
to the new image revision. Existing revisions do not acquire changed secret
values automatically.

## Bounded execution order

1. Verify the recovery image receipt and its source hash. Require the final
   candidate's image and CloudBank feature qualification before its later
   catalog promotion. Keep the aggregate paid-test ceiling of
   $100 and require zero OpenRouter inference in those tests. Preview the
   protected JSON diff against the fresh live app/job state. Recheck writer
   inventory, no bound named slots, current schema, and balanced accounting.
   Rebuild the plan if an unrelated setting changed during preparation.
2. Apply `secrets.patch.json` to the existing app. This adds the two approved
   credentials while preserving all prior secrets and configuration. Use the
   protected body file with the existing private Azure CLI; capture raw cloud
   output privately and report only sanitized status.
3. Update the existing migration job using `recovery-migration.patch.json`.
   Keep its manual trigger, retry limit zero, one replica, administrator
   database secret, and `python -m app.cli.migrate` entrypoint. Run that job
   once and require `Succeeded`. It upgrades to `20260909_0006` and then grants
   the application role the required table privileges and default privileges.
   A bare Alembic invocation does not replace this role-provisioning step.
4. Apply `recovery-stage.patch.json` to the app. It sets the explicit false
   automatic-credit gate. Require a healthy ready revision on the exact
   recovery digest. Check public read-only/scenario/auth flows, then confirm
   the old revision is inactive, has no replicas, and has no running auxiliary
   executions. Preserve any pending reservations for new-code settlement or
   conservative recovery. Do not erase them to make the check pass.
5. Run `recovery-reconcile-preview.execution.json` as an execution override of
   the existing migration job. The template removes the administrator URL and
   all provider credentials and uses only the existing restricted application
   login. Its runner calls `app.cli.reconcile_named_credit` without `--apply`,
   which rolls back all work. Read the protected report and compare it to the
   fresh read-only account snapshot.
6. Run `recovery-reconcile-apply.execution.json` once. It calls the same CLI
   with `--apply`. Run the preview again and confirm it proposes no additional
   grant. Use `recovery-inspect.execution.json` for the read-only after-state.
   Verify the invariants below and retain the reports privately.
7. Apply `recovery-ready.patch.json` to enable future automatic named
   activation. Both sides now use program-aware 0006 code. After the final
   catalog's feature receipts pass, apply `candidate-ready.patch.json` and
   `candidate-migration.patch.json` so the app and any future manual job use
   the same final image. Verify the exact digest, ready revision, catalog,
   provider configuration, quota response, and existing deterministic/MCP
   flows. Routine health checks must not trigger live inference.

The renderer also provides candidate stage, preview, apply, and inspection
templates if the final qualified image is used for the first 0006 rollout.
The same false-gate and old-writer checks still apply. It stores the original
app/job metadata for comparison, not as an executable rollback to 0005.

## After-state and recovery

For the registered administrator, the new total grant must equal $50 and
available credit must equal $50 minus preserved spent and reserved amounts.
Every old reservation keeps its identifier, cost, timestamp, and status, with
only its program attribution transferred. `administrators` has capacity five,
$50 per grant, and a $250 allocation ceiling. Its activation, allocation, and
spending totals must match its grants. The public program releases the moved
place, allocation, and spend, and otherwise keeps its configured 100 places,
$5 grants, and $500 budget. Unregistered slots remain unbound. The emergency
budget, usage-event identities, and total recorded cost remain unchanged.
If normal usage occurred between snapshots, account for those additional
ledger entries explicitly instead of requiring an outdated absolute total.

Before migration, the original image remains a possible image rollback. Once
schema 0006 is installed, recover with the verified 0006 recovery digest or a
forward repair. After any named binding, the old image's global-only settlement
is also incorrect, and the schema downgrade intentionally refuses to remove
bound entitlements. Reverting credit or dropping the table is not an image
recovery strategy.

For a problem in the promoted model catalog, update the app and manual job to
the qualified recovery digest, retaining the true automatic-credit setting,
all current provider secret references, and all database state. Verify that
the remaining public Sonnet route is configured. For an application defect,
use that same compatible image or repair the source and publish a new tested
digest. `ABDA_ENABLE_LLM=0` and disabling BYOK are invalid managed-startup
configurations. Disabling trial activation does not stop existing grants from
being spent, so none of these settings supplies an accounting drain.

The private PostgreSQL server remains on native seven-day backups. Point-in-time
restore creates a separate server and changes the recovery point for user
data; it is reserved for a database incident under the existing
[database recovery runbook](database-recovery.md), not an ordinary image rollback.

Local validation: the two-phase accounting change passed 46 focused tests.
The new request/inspection renderer and actual-client acceptance helper passed
40 focused tests together. Renderer checks cover restricted job credentials,
secret preservation, isolated ADC mounting, false/true template differences,
immutable images, endpoint validation, and exclusive owner-only output. These
are preparation receipts; the hosted release is complete only after its
actual migration, reconciliation, image, and health receipts are recorded.
