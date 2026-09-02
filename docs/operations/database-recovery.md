# PostgreSQL recovery and incident handoff

State: recovery procedure documented, two-person tabletop review pending

This runbook covers the Azure Database for PostgreSQL Flexible Server used by
the public ABDA-NL service. It is not part of the normal release sequence. Do
not create a restored server merely to complete a checklist. A restore creates
a second billable server and requires an explicit incident or rehearsal
decision.

## Current recovery boundary

- Subscription: `access-CIS260773-547078`
- Resource group: `abda-nl-staging`
- Source server: `abda-nl-stg-postgres-bgjhpbgw`
- Database: `abda`
- Region: East US 2
- Network access: private only
- Delegated subnet: `abda-nl-stg-network/postgres`
- Private DNS zone:
  `abda-nl-stg-bgjhpbgw.postgres.database.azure.com`
- Native backup retention: 7 days

The current burstable database has no high-availability standby. Native Azure
backups support point-in-time recovery within the retained window. Azure states
that transaction-log timing can make the recovery point objective as much as
five minutes. Restore time depends on the database and log volume and can range
from minutes to hours.

Every point-in-time restore creates a new server. It never overwrites the
source server. A privately networked source must restore into private network
access, either in the same virtual network or another suitable virtual network.

## Roles and communication

Haoyang is the primary service operator. Shawn is the intended technical
reviewer for a recovery decision. Bertram is the conference presenter and
should receive a simple service-status update, but should not make an Azure
change during a presentation.

The release checklist remains incomplete until two people have reviewed this
runbook and can identify:

1. the source server and seven-day window;
2. the difference between image rollback and database recovery;
3. the rule that a restore creates a new server;
4. the private validation and controlled cutover steps;
5. the deterministic local and Delta fallback.

Review does not grant a person Azure access and does not authorize a restore.

## First response

1. Record the first known bad time and the last known good time in UTC.
2. Do not run a migration, privacy deletion, budget promotion, or manual SQL
   repair while the incident state is uncertain.
3. Do not delete, rename, stop, or change the source PostgreSQL server.
4. Keep model and project mutations out of the presentation workflow. Use the
   deterministic local or Delta demo if the public service is unavailable.
5. Preserve only content-free evidence. Do not copy database connection
   strings, passwords, emails, project contents, prompts, or bearer tokens into
   an incident note.

If readiness is failing, Container Apps should remove the unhealthy replica
from traffic. Do not weaken readiness or expose PostgreSQL publicly to make the
site appear healthy.

## Read-only source inspection

In Azure Cloud Shell, confirm the expected subscription and inspect only the
source server. These commands do not change Azure:

```bash
az account show \
  --query '{name:name,id:id,tenantId:tenantId,user:user.name}' \
  --output table

az postgres flexible-server show \
  --resource-group abda-nl-staging \
  --name abda-nl-stg-postgres-bgjhpbgw \
  --query '{name:name,state:state,location:location,version:version,backupRetentionDays:backup.backupRetentionDays,publicNetworkAccess:network.publicNetworkAccess,delegatedSubnetResourceId:network.delegatedSubnetResourceId,privateDnsZoneArmResourceId:network.privateDnsZoneArmResourceId}' \
  --output json
```

Stop if the subscription ID is not
`00e62f6e-2174-40b2-b428-8ebfd7c2ac54`, the server name differs, the backup
window is not 7 days, or public network access is not disabled. Investigate the
drift before considering a restore.

In the Azure portal, open the source server and use **Monitoring**, then
**Metrics**, plus the Activity log, to locate the incident boundary. Avoid
opening or exporting user records merely to diagnose platform health.

## Point-in-time restore decision

Use point-in-time recovery for confirmed logical corruption, accidental
deletion, or a server failure that cannot be resolved safely in place. An image
regression alone uses the tested image rollback and does not justify a database
restore.

Choose a restore time in UTC that is:

- after the earliest restore point shown by Azure;
- before the first known bad write;
- no older than the retained seven-day window;
- recorded in the private incident note with the reason for choosing it.

When the exact bad time is uncertain, restore to a conservative earlier point
and validate the result. Do not guess a future timestamp. Azure may normalize a
future timestamp to the current time, which would defeat the recovery intent.

## Create a separate restored server

This section is mutating and billable. It requires an explicit operator
decision after the read-only inspection.

1. In the Azure portal, open
   `abda-nl-stg-postgres-bgjhpbgw` and select **Overview**, then **Restore**.
2. Select **Custom restore point** and enter the reviewed UTC timestamp.
3. Keep subscription `access-CIS260773-547078`, resource group
   `abda-nl-staging`, and region East US 2.
4. Give the new server a unique incident name such as
   `abda-nl-stg-restore-YYYYMMDDHHMM`. Never reuse the source name.
5. Preserve private network access. Select virtual network
   `abda-nl-stg-network`, the delegated PostgreSQL subnet, and the existing
   private DNS integration offered by the restore wizard. Do not select public
   access.
6. Keep the inherited PostgreSQL major version, backup retention, compute, and
   storage unless a separately reviewed capacity issue requires a change.
7. Review the summary carefully. Confirm that Azure will create one new server
   and will not modify or delete the source. Then select **Create**.
8. Record only the new server name, requested restore time, submission time,
   and final provisioning state.

The Azure CLI also supports `az postgres flexible-server restore`, but the
portal is preferred here because it exposes the earliest restore point and the
private networking selections before the billable mutation.

## Validate without public cutover

Keep the Container App pointed at the original database while validating the
restored server.

1. Confirm that the restored server is `Ready`, private-only, and in the
   expected network and private DNS boundary.
2. Use an operator-controlled temporary migration or validation job inside the
   same Container Apps environment. Never open a public PostgreSQL firewall
   rule for convenience.
3. Confirm that database `abda` exists and that its Alembic revision is one
   supported by the selected application image.
4. Inspect content-free counts and accounting totals. Confirm that trial and
   OpenRouter reservations reconcile and that the chosen restore point contains
   the expected project and credential metadata.
5. Confirm that the restricted web role still lacks database, role, schema,
   object-creation, ownership, replication, and row-security bypass powers.
6. If a forward migration is required for the selected release, run the normal
   migration job against only the restored server and repeat validation.

Do not use a recovered copy for privacy-request evidence unless the privacy
operator has reviewed how restored data affects an already completed deletion.

## Controlled cutover

Cutover is a separate maintenance event. It must not be combined with the
restore submission.

1. Record the current `database-url` secret version without displaying its
   value.
2. Prepare a replacement secret that targets the validated restored server and
   uses the restricted application login.
3. Deploy one new web revision using the normal guarded application process.
   Do not change the image, trial limits, provider routing, or unrelated
   secrets in the same operation.
4. Require readiness, public HTTPS, authenticated project access, protected
   metrics, idle accounting reservations, and sanitized logs before declaring
   recovery.
5. Keep the original server unchanged until the observation period and the
   incident review are complete. A rollback should restore the prior secret and
   application revision, not destroy either database server.

Do not delete either server from this runbook. Decommissioning a recovered or
source server is a later, separately reviewed cost and retention decision.

## Deleted-server exception

If the source Azure resource itself was deleted, stop normal recovery. Azure's
deleted-server recovery path is different, requires the original subscription
and Activity log evidence, and is available for only five days according to
the current Microsoft documentation. Escalate immediately and follow that
official procedure. Do not improvise a replacement resource ID.

## Tabletop receipt

After two people review the procedure, record a content-free receipt in the
private conference checklist:

```text
ABDA-NL PostgreSQL recovery tabletop
source server identified: yes
seven-day PITR window understood: yes
new-server restore boundary understood: yes
private validation before cutover understood: yes
image rollback distinguished from database restore: yes
deterministic fallback understood: yes
primary operator: reviewed
technical reviewer: reviewed
```

Do not record credentials, user data, or a hypothetical restored-server name.

## References

- [Azure PostgreSQL backup and restore](https://learn.microsoft.com/en-us/azure/postgresql/backup-restore/concepts-backup-restore)
- [Restore to a custom restore point](https://learn.microsoft.com/en-us/azure/postgresql/backup-restore/how-to-restore-custom-restore-point)
- [Restore a deleted Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/backup-restore/how-to-restore-deleted-server)
- [ABDA-NL public deployment](public-deployment.md)
- [COMMA 2026 demonstration playbook](comma-2026-demo-playbook.md)
