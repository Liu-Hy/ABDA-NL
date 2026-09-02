"""Contracts for the bounded Azure Monitor alert deployment gate."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "deploy" / "azure" / "gate14_observability_alerts.py"
APP_ID = (
    "/subscriptions/00e62f6e-2174-40b2-b428-8ebfd7c2ac54/"
    "resourceGroups/abda-nl-staging/providers/Microsoft.App/"
    "containerApps/abda-nl-stg-web"
)


def _module():
    spec = importlib.util.spec_from_file_location("observability_alert_gate", GATE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _account() -> dict:
    return {
        "id": "00e62f6e-2174-40b2-b428-8ebfd7c2ac54",
        "tenantId": "040f05eb-33ab-462f-af54-fb4bedb055ae",
        "state": "Enabled",
        "user": {"name": "hliu2@cloudbank.org"},
    }


def _app() -> dict:
    return {
        "id": APP_ID,
        "location": "East US 2",
        "properties": {
            "provisioningState": "Succeeded",
            "runningStatus": "Running",
            "configuration": {"ingress": {"external": True, "targetPort": 8000}},
            "template": {"scale": {"minReplicas": 1, "maxReplicas": 3}},
        },
    }


def _metric_definitions() -> list[dict]:
    return [
        {
            "name": {"value": "Requests"},
            "namespace": "Microsoft.App/containerapps",
            "dimensions": [{"name": {"value": "statusCodeCategory"}}],
            "supportedAggregationTypes": ["Average", "Total", "Minimum"],
        },
        {
            "name": {"value": "Replicas"},
            "namespace": "Microsoft.App/containerapps",
            "dimensions": [{"internalName": "revisionName"}],
            "supportedAggregationTypes": ["Average", "Minimum", "Maximum"],
        },
    ]


def _workspace(module) -> dict:
    return {
        "id": module._resource_id(
            "Microsoft.OperationalInsights/workspaces", "abda-nl-stg-logs-bgjhpbgw"
        ),
        "location": "eastus2",
        "provisioningState": "Succeeded",
        "retentionInDays": 30,
    }


def _action_group(module) -> dict:
    return {
        "id": module._resource_id(
            "Microsoft.Insights/actionGroups", "abda-nl-stg-operators"
        ),
        "location": "global",
        "properties": {
            "enabled": True,
            "groupShortName": "abda-alert",
            "emailReceivers": [
                {
                    "name": "abda-support",
                    "emailAddress": "support@abda-nl.org",
                    "useCommonAlertSchema": True,
                }
            ],
            "smsReceivers": [],
            "webhookReceivers": [],
        },
    }


def _metric_alert(
    module,
    *,
    name: str,
    severity: int,
    metric_name: str,
    operator: str,
    aggregation: str,
    threshold: int,
    dimensions: list[dict],
) -> dict:
    return {
        "id": module._resource_id("Microsoft.Insights/metricAlerts", name),
        "location": "global",
        "properties": {
            "enabled": True,
            "severity": severity,
            "evaluationFrequency": "PT1M",
            "windowSize": "PT5M",
            "autoMitigate": True,
            "scopes": [APP_ID],
            "targetResourceType": "Microsoft.App/containerApps",
            "targetResourceRegion": "eastus2",
            "actions": [
                {
                    "actionGroupId": module._resource_id(
                        "Microsoft.Insights/actionGroups", "abda-nl-stg-operators"
                    )
                }
            ],
            "criteria": {
                "odata.type": (
                    "Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria"
                ),
                "allOf": [
                    {
                        "criterionType": "StaticThresholdCriterion",
                        "metricName": metric_name,
                        "metricNamespace": "Microsoft.App/containerapps",
                        "operator": operator,
                        "timeAggregation": aggregation,
                        "threshold": threshold,
                        "dimensions": dimensions,
                    }
                ],
            },
        },
    }


def _application_insights(module, workspace_id: str) -> dict:
    return {
        "id": module._resource_id(
            "Microsoft.Insights/components", "abda-nl-stg-availability"
        ),
        "location": "East US 2",
        "kind": "web",
        "properties": {
            "Application_Type": "web",
            "IngestionMode": "LogAnalytics",
            "WorkspaceResourceId": workspace_id,
            "publicNetworkAccessForIngestion": "Enabled",
            "publicNetworkAccessForQuery": "Enabled",
        },
    }


def _webtest(module) -> dict:
    return {
        "id": module._resource_id(
            "Microsoft.Insights/webtests", "abda-nl-stg-public-ready"
        ),
        "location": "eastus2",
        "properties": {
            "SyntheticMonitorId": "abda-nl-stg-public-ready",
            "Name": "abda-nl-stg-public-ready",
            "Enabled": True,
            "Frequency": 300,
            "Timeout": 30,
            "Kind": "standard",
            "RetryEnabled": True,
            "Locations": [
                {"Id": "us-il-ch1-azr"},
                {"Id": "us-va-ash-azr"},
                {"Id": "emea-nl-ams-azr"},
            ],
            "Request": {
                "RequestUrl": "https://demo.abda-nl.org/health/ready",
                "HttpVerb": "GET",
            },
            "ValidationRules": {
                "ExpectedHttpStatusCode": 200,
                "SSLCheck": True,
                "SSLCertRemainingLifetimeCheck": 14,
            },
        },
    }


def _readiness_alert(module, webtest_id: str, component_id: str) -> dict:
    return {
        "id": module._resource_id(
            "Microsoft.Insights/metricAlerts", "abda-nl-stg-public-ready-failed"
        ),
        "location": "global",
        "properties": {
            "enabled": True,
            "severity": 1,
            "evaluationFrequency": "PT1M",
            "windowSize": "PT5M",
            "autoMitigate": True,
            "scopes": [webtest_id, component_id],
            "actions": [
                {
                    "actionGroupId": module._resource_id(
                        "Microsoft.Insights/actionGroups", "abda-nl-stg-operators"
                    )
                }
            ],
            "criteria": {
                "odata.type": (
                    "Microsoft.Azure.Monitor.WebtestLocationAvailabilityCriteria"
                ),
                "webTestId": webtest_id,
                "componentId": component_id,
                "failedLocationCount": 2,
            },
        },
    }


def test_gate_is_executable_syntax_valid_and_bounded() -> None:
    assert GATE.stat().st_mode & 0o111
    subprocess.run(["python", "-m", "py_compile", str(GATE)], check=True)
    source = GATE.read_text(encoding="utf-8")
    for expected in (
        "DEPLOY_AND_TEST_ABDA_ALERTS",
        "REGISTER_ABDA_INSIGHTS",
        "ResourceIdOnly",
        "statusCodeCategory",
        "metricstaticthreshold",
        "three-region standard web test",
        "OBSERVABILITY_ALERTS_DEPLOYED_DELIVERY_CONFIRMATION_PENDING",
    ):
        assert expected in source
    for forbidden in (
        "az group delete",
        "az resource delete",
        "containerapp update",
        "containerapp revision restart",
        "api_key",
        "client_secret",
    ):
        assert forbidden not in source.lower()
    assert "\N{EN DASH}" not in source and "\N{EM DASH}" not in source


def test_identity_application_and_live_metric_contracts() -> None:
    module = _module()
    module.validate_identity(_account())
    assert module.validate_app(_app()) == APP_ID
    workspace = _workspace(module)
    assert module.validate_log_workspace(workspace) == workspace["id"]
    module.validate_metric_definitions(_metric_definitions())


def test_log_workspace_accepts_raw_arm_resource_shape() -> None:
    module = _module()
    workspace = _workspace(module)
    workspace["properties"] = {
        "provisioningState": workspace.pop("provisioningState"),
        "retentionInDays": workspace.pop("retentionInDays"),
    }
    assert module.validate_log_workspace(workspace) == workspace["id"]


@pytest.mark.parametrize(
    ("mutation", "resource_type", "name"),
    (
        ("Create", "Microsoft.Insights/actionGroups", "abda-nl-stg-operators"),
        ("Deploy", "Microsoft.Insights/metricAlerts", "abda-nl-stg-web-5xx"),
        ("Modify", "Microsoft.Insights/metricAlerts", "abda-nl-stg-web-unavailable"),
        ("Create", "Microsoft.Insights/components", "abda-nl-stg-availability"),
        ("Deploy", "Microsoft.Insights/webtests", "abda-nl-stg-public-ready"),
        (
            "Create",
            "Microsoft.Insights/metricAlerts",
            "abda-nl-stg-public-ready-failed",
        ),
    ),
)
def test_what_if_allows_only_the_three_exact_resources(
    mutation: str, resource_type: str, name: str
) -> None:
    module = _module()
    resource_id = module._resource_id(resource_type, name)
    assert module.validate_what_if(
        {"status": "Succeeded", "changes": [{"changeType": mutation, "resourceId": resource_id}]}
    ) == [(mutation, resource_id)]


@pytest.mark.parametrize("change_type", ("Delete", "Unsupported"))
def test_what_if_rejects_destructive_or_unsupported_changes(change_type: str) -> None:
    module = _module()
    with pytest.raises(module.GateFailure):
        module.validate_what_if(
            {
                "status": "Succeeded",
                "changes": [
                    {
                        "changeType": change_type,
                        "resourceId": module._resource_id(
                            "Microsoft.Insights/actionGroups", "abda-nl-stg-operators"
                        ),
                    }
                ],
            }
        )


def test_what_if_rejects_an_unexpected_resource() -> None:
    module = _module()
    with pytest.raises(module.GateFailure):
        module.validate_what_if(
            {
                "status": "Succeeded",
                "changes": [
                    {
                        "changeType": "Modify",
                        "resourceId": APP_ID,
                    }
                ],
            }
        )


def test_metric_contract_rejects_missing_status_category() -> None:
    module = _module()
    definitions = _metric_definitions()
    definitions[0]["dimensions"] = []
    with pytest.raises(module.GateFailure, match="statusCodeCategory"):
        module.validate_metric_definitions(definitions)


def test_exact_action_group_and_both_metric_alerts_are_accepted() -> None:
    module = _module()
    action_group_id = module.validate_action_group(_action_group(module))
    status_dimension = {
        "name": "statusCodeCategory",
        "operator": "Include",
        "values": ["5xx"],
    }
    module.validate_metric_alert(
        _metric_alert(
            module,
            name="abda-nl-stg-web-5xx",
            severity=2,
            metric_name="Requests",
            operator="GreaterThanOrEqual",
            aggregation="Total",
            threshold=5,
            dimensions=[status_dimension],
        ),
        expected_id=module._resource_id(
            "Microsoft.Insights/metricAlerts", "abda-nl-stg-web-5xx"
        ),
        app_id=APP_ID,
        action_group_id=action_group_id,
        severity=2,
        metric_name="Requests",
        operator="GreaterThanOrEqual",
        aggregation="Total",
        threshold=5,
        dimension=status_dimension,
    )
    module.validate_metric_alert(
        _metric_alert(
            module,
            name="abda-nl-stg-web-unavailable",
            severity=1,
            metric_name="Replicas",
            operator="LessThan",
            aggregation="Minimum",
            threshold=1,
            dimensions=[],
        ),
        expected_id=module._resource_id(
            "Microsoft.Insights/metricAlerts", "abda-nl-stg-web-unavailable"
        ),
        app_id=APP_ID,
        action_group_id=action_group_id,
        severity=1,
        metric_name="Replicas",
        operator="LessThan",
        aggregation="Minimum",
        threshold=1,
        dimension=None,
    )


def test_unexpected_action_group_receiver_is_rejected() -> None:
    module = _module()
    group = _action_group(module)
    group["properties"]["webhookReceivers"] = [{"name": "unexpected"}]
    with pytest.raises(module.GateFailure, match="unexpected receiver"):
        module.validate_action_group(group)


def test_exact_workspace_link_webtest_and_availability_alert_are_accepted() -> None:
    module = _module()
    workspace_id = module.validate_log_workspace(_workspace(module))
    component_id = module.validate_application_insights(
        _application_insights(module, workspace_id), workspace_id
    )
    webtest_id = module.validate_readiness_test(_webtest(module))
    action_group_id = module.validate_action_group(_action_group(module))
    module.validate_readiness_alert(
        _readiness_alert(module, webtest_id, component_id),
        webtest_id=webtest_id,
        component_id=component_id,
        action_group_id=action_group_id,
    )


def test_readiness_test_rejects_a_weakened_tls_lifetime_check() -> None:
    module = _module()
    webtest = _webtest(module)
    webtest["properties"]["ValidationRules"]["SSLCertRemainingLifetimeCheck"] = 1
    with pytest.raises(module.GateFailure, match="TLS"):
        module.validate_readiness_test(webtest)
