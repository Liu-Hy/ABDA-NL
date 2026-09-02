# Azure Monitor alerts and public readiness checks

State: live deployment, exact resource verification, and email delivery verified

ABDA-NL uses two complementary monitoring layers. Platform metrics report what
Azure Container Apps observes inside the application resource. A standard
Application Insights web test independently calls the public custom domain, so
DNS, TLS, ingress, and readiness failures remain visible even when Container
Apps emits no useful metric during an outage.

## Bounded resources

`deploy/azure/observability.bicep` creates exactly these six resources in the
existing `abda-nl-staging` resource group:

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

## Safe deployment gate

`deploy/azure/gate14_observability_alerts.py` performs these steps:

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
