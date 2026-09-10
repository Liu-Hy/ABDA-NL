# Azure Monitor alerts and public readiness checks

State: six baseline resources and email delivery verified on 2026-09-02.
Three additional routing alerts are implemented and checked locally, but have
not been deployed or verified against Azure.

ABDA-NL uses two complementary monitoring layers. Platform metrics report what
Azure Container Apps observes inside the application resource. A standard
Application Insights web test independently calls the public custom domain, so
DNS, TLS, ingress, and readiness failures remain visible even when Container
Apps emits no useful metric during an outage.

## Bounded resources

The full `deploy/azure/observability.bicep` template defines nine resources in
the existing `abda-nl-staging` resource group. These six form the baseline:

1. One action group that sends common-schema email to
   `support@abda-nl.org`.
2. One severity 2 alert after at least five HTTP 5xx responses in five minutes.
3. One severity 1 alert when the minimum active replica count falls below one
   during five minutes.
4. One workspace-linked Application Insights component.
5. One standard web test that requests
   `https://demo.abda-nl.org/health/ready` every five minutes from Illinois,
   Virginia, and the Netherlands. It retries failures, expects HTTP 200, checks
   TLS, and warns when fewer than 14 certificate days remain.
6. One severity 1 alert when at least two test regions report failure.

The web test sends no authentication, cookie, private project content, API key,
or model prompt. The readiness response is already public and content-free.

The three additional rules query the existing workspace's Container Apps
console logs, filtered to `abda-nl-stg-web`, and use the existing support action
group. Their query results contain only timestamps, route identifiers, and
numeric aggregates. Azure documents this log table and the scheduled-query
rule contract in its [Container Apps logging reference](https://learn.microsoft.com/en-us/azure/container-apps/log-monitoring)
and [scheduled-query resource schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.insights/2023-12-01/scheduledqueryrules).

| Rule suffix | Default trigger | Severity |
| --- | --- | --- |
| `llm-configuration` | At least one `llm_configuration_unavailable` event in five minutes. Startup failures without a route use `public-routes`. | 1 |
| `llm-circuit` | The same funded route reports circuit-open events in at least two of three five-minute periods. | 2 |
| `llm-fallback-spend` | Aggregate settled fallback charges reach $1 within 15 minutes. | 2 |

All three evaluate every five minutes and resolve automatically. The circuit
rule uses Azure's [failing-period settings](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-create-log-alert-rule)
to avoid notifying for a single brief interruption. Settled fallback charges
include conservative liability for uncertain attempts. They are local
accounting estimates, not provider invoices. The spend threshold can be set
between $0.10 and $10; changing it does not change any spending limit. Log
ingestion can lag or fail, so the durable usage ledger remains the accounting
authority.

## Cost boundary

Platform metrics are standard Azure resource metrics. Standard web tests are
billable per scheduled execution, and alert rules or notifications may have
separate charges. Three locations at a five-minute frequency schedule about
25,920 location executions in a 30-day month. The exact CloudBank subscription
rate must be reviewed in Azure Cost Management because public list prices do
not determine an allocation-specific charge.

This recurring check is intentionally limited to one URL, three locations, and
one five-minute schedule. Expanding the location count, adding URLs, or reducing
the interval requires a new review.

## Routing alert preview and verification

Use the current local template mode of
`deploy/azure/gate14_observability_alerts.py` for the three new rules. First
review both files and record their hashes:

```sh
sha256sum deploy/azure/observability.bicep deploy/azure/observability.bicepparam
```

Replace the two hash placeholders with those reviewed values:

```sh
python deploy/azure/gate14_observability_alerts.py \
  --local-template deploy/azure/observability.bicep \
  --template-sha256 REVIEWED_TEMPLATE_SHA256 \
  --local-parameters deploy/azure/observability.bicepparam \
  --parameters-sha256 REVIEWED_PARAMETERS_SHA256
```

The default mode freezes and checks the source bytes, compiles with pinned
Bicep, verifies the exact existing subscription, app, workspace, and receiver,
then performs Azure validation and what-if. The compiled deployment payload
contains only the three new scheduled-query rules. The gate rejects deletion,
unsupported changes, and mutation of any other resource, including the six
baseline resources. It requires Microsoft.Insights to be registered already.

Add `--verify-only` to check the three deployed rules against their exact query,
scope, receiver, window, and threshold contracts without creating a deployment.
Add `--deploy-reviewed-routing-alerts` only when deployment is authorized; this
runs validation and what-if before an incremental deployment and exact
readback. Both modes require the same source hashes. The optional
`--fallback-alert-microusd` sets the bounded spend threshold (default 1000000).
This local mode never submits a synthetic test email or calls a model provider.

Local verification on 2026-09-10 compiled both templates with Bicep 0.46.1 and
tested the source, mutation, query, receiver, and CLI mode boundaries with
mocked Azure responses. Actual query execution and deployed alert state remain
unverified until the Azure gate runs.

## Historical baseline deployment gate

Running the gate without arguments retains its historical, commit-pinned
six-resource workflow. It does not include the new routing alerts and performs
these steps:

1. verifies the exact subscription, tenant, user, source hashes, and Bicep
   compiler;
2. verifies the existing Container App and the live Azure metric definitions;
3. runs provider validation and a resource-ID-only what-if;
4. rejects deletion, unsupported changes, or mutation outside the six exact
   resources;
5. deploys only after the exact confirmation shown by the gate;
6. verifies every receiver, scope, threshold, region, URL, TLS rule, and action;
7. submits one Azure Monitor test email to the public support address.

The content-free receipt proves that Azure accepted the deployment and test
submission. Inbox delivery remains a separate human observation and should be
recorded during the consolidated release acceptance. Do not trigger a real 5xx
burst or stop the public replica merely to test notifications.

Azure's Action Group test message is a synthetic delivery check. Its body can
name placeholder resources such as `test-storageAccount`, `test-RG`, and a
sample subscription or alert identifier. Those values do not describe a
resource created in the ABDA-NL subscription. The deployment receipt and Gate
verification identify the real six monitoring resources separately.

## Live staging evidence

On 2026-09-02, Gate 14 revision 3 completed against subscription-scoped resource
group `abda-nl-staging`. It verified the action group, both Container Apps metric
alerts, workspace-linked Application Insights component, three-region standard
web test, and public-readiness alert. Azure accepted the bounded static-threshold
test notification, and the message reached the monitored inbox through
`support@abda-nl.org`.

The final receipt was
`OBSERVABILITY_ALERTS_DEPLOYED_DELIVERY_CONFIRMATION_PENDING`, followed by the
separate inbox delivery confirmation. It also recorded
`application_changed: false` and `model_provider_called: false`.

The live Azure response exposed two computed representation details absent from
the original fixtures. Azure CLI returns Log Analytics workspace properties at
the top level, while the action-group API adds a read-only receiver status.
Gate revision 3 accepts both documented workspace representations, verifies the
configured receiver fields, and requires its computed status to be `Enabled`.

## Primary references

- [Container Apps metrics](https://learn.microsoft.com/azure/container-apps/metrics)
- [Application Insights availability tests](https://learn.microsoft.com/azure/azure-monitor/app/availability)
- [Workspace-based Application Insights resources](https://learn.microsoft.com/azure/azure-monitor/app/create-workspace-resource)
- [Azure Monitor metric-alert templates](https://learn.microsoft.com/azure/azure-monitor/alerts/resource-manager-alerts-metric)
- [Azure Monitor pricing](https://azure.microsoft.com/pricing/details/monitor/)
