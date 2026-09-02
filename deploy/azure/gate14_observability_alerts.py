#!/usr/bin/env python3
"""Deploy and verify the bounded ABDA-NL Azure Monitor alert resources."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Sequence


SCRIPT_REVISION = "2"
SOURCE_COMMIT = "b63109adbc09f1265d4eccf9ad934fa6cd46cfa2"
SOURCE_REPOSITORY = "https://github.com/Liu-Hy/ABDA-NL.git"
BICEP_VERSION = "0.46.1"
BICEP_SHA256 = "e073e9dac769beed3c417aa3b29d15647debd4034049301efaeac27e7fb44b4c"
PARAMETERS_SHA256 = "98305fa55beb66c4bec66532167fc93513207f59fe41276382771f991525e734"

SUBSCRIPTION_ID = "00e62f6e-2174-40b2-b428-8ebfd7c2ac54"
TENANT_ID = "040f05eb-33ab-462f-af54-fb4bedb055ae"
AZURE_USER = "hliu2@cloudbank.org"
RESOURCE_GROUP = "abda-nl-staging"
LOCATION = "eastus2"
APP_NAME = "abda-nl-stg-web"
LOG_WORKSPACE_NAME = "abda-nl-stg-logs-bgjhpbgw"
RESOURCE_PREFIX = "abda-nl-stg"
ALERT_EMAIL = "support@abda-nl.org"
PUBLIC_READINESS_URL = "https://demo.abda-nl.org/health/ready"
DEPLOYMENT_NAME = "abda-nl-stg-observability"
ACTION_GROUP_NAME = f"{RESOURCE_PREFIX}-operators"
SERVER_ERROR_ALERT_NAME = f"{RESOURCE_PREFIX}-web-5xx"
UNAVAILABLE_ALERT_NAME = f"{RESOURCE_PREFIX}-web-unavailable"
APPLICATION_INSIGHTS_NAME = f"{RESOURCE_PREFIX}-availability"
READINESS_TEST_NAME = f"{RESOURCE_PREFIX}-public-ready"
READINESS_ALERT_NAME = f"{RESOURCE_PREFIX}-public-ready-failed"


class GateFailure(RuntimeError):
    """A bounded gate assertion failed."""


def _run(
    command: Sequence[str],
    *,
    timeout: int = 120,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    if check and result.returncode:
        detail = (result.stderr or result.stdout).strip().splitlines()
        message = detail[-1] if detail else "command returned no diagnostic"
        raise GateFailure(f"command failed safely: {command[0]} {message}")
    return result


def _az_json(arguments: Sequence[str], *, timeout: int = 120) -> Any:
    result = _run(
        ("az", *arguments, "--only-show-errors", "--output", "json"),
        timeout=timeout,
    )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise GateFailure("Azure returned invalid JSON") from exc


def _normalize_location(value: object) -> str:
    return "".join(str(value or "").lower().split())


def _resource_id(resource_type: str, name: str) -> str:
    return (
        f"/subscriptions/{SUBSCRIPTION_ID}/resourceGroups/{RESOURCE_GROUP}"
        f"/providers/{resource_type}/{name}"
    )


def validate_identity(account: Any) -> None:
    if not isinstance(account, dict):
        raise GateFailure("the Azure account response is malformed")
    user = account.get("user") or {}
    observed = (
        account.get("id"),
        account.get("tenantId"),
        str(user.get("name") or "").lower(),
        account.get("state"),
    )
    expected = (SUBSCRIPTION_ID, TENANT_ID, AZURE_USER.lower(), "Enabled")
    if observed != expected:
        raise GateFailure("the active Azure identity or subscription changed")


def validate_app(app: Any) -> str:
    if not isinstance(app, dict):
        raise GateFailure("the Container App response is malformed")
    expected_id = _resource_id("Microsoft.App/containerApps", APP_NAME)
    properties = app.get("properties") or {}
    ingress = (properties.get("configuration") or {}).get("ingress") or {}
    scale = (properties.get("template") or {}).get("scale") or {}
    if str(app.get("id") or "").lower() != expected_id.lower():
        raise GateFailure("the monitored Container App identity changed")
    if _normalize_location(app.get("location")) != LOCATION:
        raise GateFailure("the monitored Container App region changed")
    if properties.get("provisioningState") != "Succeeded":
        raise GateFailure("the monitored Container App is not provisioned")
    if properties.get("runningStatus") != "Running":
        raise GateFailure("the monitored Container App is not running")
    if ingress.get("external") is not True or ingress.get("targetPort") != 8000:
        raise GateFailure("the monitored Container App ingress changed")
    if int(scale.get("minReplicas") or 0) < 1:
        raise GateFailure("the monitored Container App has no minimum replica")
    return expected_id


def validate_log_workspace(workspace: Any) -> str:
    expected_id = _resource_id(
        "Microsoft.OperationalInsights/workspaces", LOG_WORKSPACE_NAME
    )
    if not isinstance(workspace, dict):
        raise GateFailure("the Log Analytics workspace response is malformed")
    properties = workspace.get("properties") or {}
    provisioning_state = workspace.get(
        "provisioningState", properties.get("provisioningState")
    )
    retention_days = workspace.get("retentionInDays", properties.get("retentionInDays"))
    if str(workspace.get("id") or "").lower() != expected_id.lower():
        raise GateFailure("the Log Analytics workspace identity changed")
    if _normalize_location(workspace.get("location")) != LOCATION:
        raise GateFailure("the Log Analytics workspace region changed")
    if provisioning_state != "Succeeded":
        raise GateFailure("the Log Analytics workspace is not provisioned")
    if retention_days != 30:
        raise GateFailure("the Log Analytics retention period changed")
    return expected_id


def _metric_name(metric: Any) -> str:
    if not isinstance(metric, dict):
        return ""
    name = metric.get("name") or {}
    return str(name.get("value") if isinstance(name, dict) else name or "")


def _dimension_name(dimension: Any) -> str:
    if not isinstance(dimension, dict):
        return ""
    name = dimension.get("name")
    if isinstance(name, dict):
        value = name.get("value")
        if value:
            return str(value)
    for key in ("value", "internalName"):
        if dimension.get(key):
            return str(dimension[key])
    return str(name or "")


def validate_metric_definitions(definitions: Any) -> None:
    if not isinstance(definitions, list):
        raise GateFailure("Azure metric definitions are malformed")
    metrics = {_metric_name(item): item for item in definitions}
    for name in ("Requests", "Replicas"):
        if name not in metrics:
            raise GateFailure(f"the Container Apps {name} metric is unavailable")
        namespace = str(metrics[name].get("namespace") or "").lower()
        if namespace != "microsoft.app/containerapps":
            raise GateFailure(f"the Container Apps {name} namespace changed")
    request_dimensions = {
        _dimension_name(item)
        for item in (metrics["Requests"].get("dimensions") or [])
    }
    if "statusCodeCategory" not in request_dimensions:
        raise GateFailure("Requests no longer exposes statusCodeCategory")
    request_aggregations = set(metrics["Requests"].get("supportedAggregationTypes") or [])
    replica_aggregations = set(metrics["Replicas"].get("supportedAggregationTypes") or [])
    if "Total" not in request_aggregations or "Minimum" not in replica_aggregations:
        raise GateFailure("the required metric aggregation is unavailable")


def validate_what_if(document: Any) -> list[tuple[str, str]]:
    if not isinstance(document, dict):
        raise GateFailure("the Azure what-if response is malformed")
    payload = document.get("properties", document)
    if payload.get("status") not in (None, "Succeeded"):
        raise GateFailure("the Azure what-if did not succeed")
    changes = payload.get("changes")
    if not isinstance(changes, list):
        raise GateFailure("the Azure what-if did not return a changes list")
    allowed = {
        _resource_id("Microsoft.Insights/actionGroups", ACTION_GROUP_NAME).lower(),
        _resource_id("Microsoft.Insights/metricAlerts", SERVER_ERROR_ALERT_NAME).lower(),
        _resource_id("Microsoft.Insights/metricAlerts", UNAVAILABLE_ALERT_NAME).lower(),
        _resource_id("Microsoft.Insights/components", APPLICATION_INSIGHTS_NAME).lower(),
        _resource_id("Microsoft.Insights/webtests", READINESS_TEST_NAME).lower(),
        _resource_id("Microsoft.Insights/metricAlerts", READINESS_ALERT_NAME).lower(),
    }
    known = {"Create", "Delete", "Deploy", "Ignore", "Modify", "NoChange", "Unsupported"}
    mutations: list[tuple[str, str]] = []
    for change in changes:
        if not isinstance(change, dict):
            raise GateFailure("the Azure what-if contains a malformed change")
        change_type = str(change.get("changeType") or "")
        resource_id = str(
            change.get("resourceId")
            or (change.get("after") or {}).get("id")
            or (change.get("before") or {}).get("id")
            or ""
        )
        if change_type not in known:
            raise GateFailure(f"the Azure what-if returned unknown change {change_type!r}")
        if change_type in {"Delete", "Unsupported"}:
            raise GateFailure(f"the Azure what-if returned unsafe change {change_type}")
        if change_type in {"Create", "Deploy", "Modify"}:
            if resource_id.lower() not in allowed:
                raise GateFailure("the Azure what-if would change an unexpected resource")
            mutations.append((change_type, resource_id))
    return mutations


def _empty_receiver_lists(properties: dict[str, Any]) -> bool:
    keys = (
        "armRoleReceivers",
        "automationRunbookReceivers",
        "azureAppPushReceivers",
        "azureFunctionReceivers",
        "eventHubReceivers",
        "itsmReceivers",
        "logicAppReceivers",
        "smsReceivers",
        "voiceReceivers",
        "webhookReceivers",
    )
    return all(not properties.get(key) for key in keys)


def validate_action_group(group: Any) -> str:
    expected_id = _resource_id("Microsoft.Insights/actionGroups", ACTION_GROUP_NAME)
    if not isinstance(group, dict):
        raise GateFailure("the deployed action group response is malformed")
    properties = group.get("properties") or {}
    receivers = properties.get("emailReceivers") or []
    if str(group.get("id") or "").lower() != expected_id.lower():
        raise GateFailure("the deployed action group identity changed")
    if _normalize_location(group.get("location")) != "global":
        raise GateFailure("the deployed action group location changed")
    if properties.get("enabled") is not True or properties.get("groupShortName") != "abda-alert":
        raise GateFailure("the deployed action group settings changed")
    if receivers != [
        {
            "name": "abda-support",
            "emailAddress": ALERT_EMAIL,
            "useCommonAlertSchema": True,
        }
    ]:
        raise GateFailure("the deployed action group email receiver changed")
    if not _empty_receiver_lists(properties):
        raise GateFailure("the deployed action group has an unexpected receiver")
    return expected_id


def validate_metric_alert(
    alert: Any,
    *,
    expected_id: str,
    app_id: str,
    action_group_id: str,
    severity: int,
    metric_name: str,
    operator: str,
    aggregation: str,
    threshold: int,
    dimension: dict[str, Any] | None,
) -> None:
    if not isinstance(alert, dict):
        raise GateFailure("a deployed metric alert response is malformed")
    properties = alert.get("properties") or {}
    criteria = properties.get("criteria") or {}
    rules = criteria.get("allOf") or []
    expected_dimensions = [] if dimension is None else [dimension]
    if str(alert.get("id") or "").lower() != expected_id.lower():
        raise GateFailure("a deployed metric alert identity changed")
    if _normalize_location(alert.get("location")) != "global":
        raise GateFailure("a deployed metric alert location changed")
    if properties.get("enabled") is not True or properties.get("severity") != severity:
        raise GateFailure("a deployed metric alert severity or enabled state changed")
    if properties.get("evaluationFrequency") != "PT1M" or properties.get("windowSize") != "PT5M":
        raise GateFailure("a deployed metric alert evaluation window changed")
    if properties.get("autoMitigate") is not True:
        raise GateFailure("a deployed metric alert no longer auto-mitigates")
    if [str(item).lower() for item in (properties.get("scopes") or [])] != [app_id.lower()]:
        raise GateFailure("a deployed metric alert scope changed")
    if str(properties.get("targetResourceType") or "").lower() != "microsoft.app/containerapps":
        raise GateFailure("a deployed metric alert target type changed")
    if _normalize_location(properties.get("targetResourceRegion")) != LOCATION:
        raise GateFailure("a deployed metric alert target region changed")
    actions = properties.get("actions") or []
    if len(actions) != 1 or str(actions[0].get("actionGroupId") or "").lower() != action_group_id.lower():
        raise GateFailure("a deployed metric alert action group changed")
    if criteria.get("odata.type") != "Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria":
        raise GateFailure("a deployed metric alert criteria type changed")
    if len(rules) != 1:
        raise GateFailure("a deployed metric alert has an unexpected rule count")
    rule = rules[0]
    observed = (
        rule.get("criterionType"),
        rule.get("metricName"),
        str(rule.get("metricNamespace") or "").lower(),
        rule.get("operator"),
        rule.get("timeAggregation"),
        rule.get("threshold"),
        rule.get("dimensions") or [],
        bool(rule.get("skipMetricValidation", False)),
    )
    expected = (
        "StaticThresholdCriterion",
        metric_name,
        "microsoft.app/containerapps",
        operator,
        aggregation,
        threshold,
        expected_dimensions,
        False,
    )
    if observed != expected:
        raise GateFailure("a deployed metric alert threshold or dimension changed")


def validate_application_insights(component: Any, workspace_id: str) -> str:
    expected_id = _resource_id("Microsoft.Insights/components", APPLICATION_INSIGHTS_NAME)
    if not isinstance(component, dict):
        raise GateFailure("the Application Insights response is malformed")
    properties = component.get("properties") or {}
    if str(component.get("id") or "").lower() != expected_id.lower():
        raise GateFailure("the Application Insights identity changed")
    if _normalize_location(component.get("location")) != LOCATION:
        raise GateFailure("the Application Insights region changed")
    if str(component.get("kind") or "").lower() != "web":
        raise GateFailure("the Application Insights kind changed")
    if str(properties.get("Application_Type") or "").lower() != "web":
        raise GateFailure("the Application Insights application type changed")
    if str(properties.get("IngestionMode") or "").lower() != "loganalytics":
        raise GateFailure("the Application Insights ingestion mode changed")
    if str(properties.get("WorkspaceResourceId") or "").lower() != workspace_id.lower():
        raise GateFailure("the Application Insights workspace link changed")
    if properties.get("publicNetworkAccessForIngestion") != "Enabled":
        raise GateFailure("Application Insights public ingestion changed")
    if properties.get("publicNetworkAccessForQuery") != "Enabled":
        raise GateFailure("Application Insights public query access changed")
    return expected_id


def validate_readiness_test(webtest: Any) -> str:
    expected_id = _resource_id("Microsoft.Insights/webtests", READINESS_TEST_NAME)
    if not isinstance(webtest, dict):
        raise GateFailure("the public readiness web test response is malformed")
    properties = webtest.get("properties") or {}
    if str(webtest.get("id") or "").lower() != expected_id.lower():
        raise GateFailure("the public readiness web test identity changed")
    if _normalize_location(webtest.get("location")) != LOCATION:
        raise GateFailure("the public readiness web test region changed")
    observed_locations = {
        str(item.get("Id") or item.get("id") or "")
        for item in (properties.get("Locations") or [])
        if isinstance(item, dict)
    }
    if observed_locations != {"us-il-ch1-azr", "us-va-ash-azr", "emea-nl-ams-azr"}:
        raise GateFailure("the public readiness web test locations changed")
    request = properties.get("Request") or {}
    rules = properties.get("ValidationRules") or {}
    expected = (
        properties.get("SyntheticMonitorId"),
        properties.get("Name"),
        properties.get("Enabled"),
        properties.get("Frequency"),
        properties.get("Timeout"),
        str(properties.get("Kind") or "").lower(),
        properties.get("RetryEnabled"),
        request.get("RequestUrl"),
        request.get("HttpVerb"),
        rules.get("ExpectedHttpStatusCode"),
        rules.get("SSLCheck"),
        rules.get("SSLCertRemainingLifetimeCheck"),
    )
    required = (
        READINESS_TEST_NAME,
        READINESS_TEST_NAME,
        True,
        300,
        30,
        "standard",
        True,
        PUBLIC_READINESS_URL,
        "GET",
        200,
        True,
        14,
    )
    if expected != required:
        raise GateFailure("the public readiness URL, TLS, retry, or schedule changed")
    return expected_id


def validate_readiness_alert(
    alert: Any,
    *,
    webtest_id: str,
    component_id: str,
    action_group_id: str,
) -> None:
    expected_id = _resource_id("Microsoft.Insights/metricAlerts", READINESS_ALERT_NAME)
    if not isinstance(alert, dict):
        raise GateFailure("the public readiness alert response is malformed")
    properties = alert.get("properties") or {}
    criteria = properties.get("criteria") or {}
    scopes = {str(item).lower() for item in (properties.get("scopes") or [])}
    if str(alert.get("id") or "").lower() != expected_id.lower():
        raise GateFailure("the public readiness alert identity changed")
    if _normalize_location(alert.get("location")) != "global":
        raise GateFailure("the public readiness alert location changed")
    if properties.get("enabled") is not True or properties.get("severity") != 1:
        raise GateFailure("the public readiness alert severity or enabled state changed")
    if properties.get("evaluationFrequency") != "PT1M" or properties.get("windowSize") != "PT5M":
        raise GateFailure("the public readiness alert evaluation window changed")
    if properties.get("autoMitigate") is not True:
        raise GateFailure("the public readiness alert no longer auto-mitigates")
    if scopes != {webtest_id.lower(), component_id.lower()}:
        raise GateFailure("the public readiness alert scope changed")
    actions = properties.get("actions") or []
    if len(actions) != 1 or str(actions[0].get("actionGroupId") or "").lower() != action_group_id.lower():
        raise GateFailure("the public readiness alert action group changed")
    observed = (
        criteria.get("odata.type"),
        str(criteria.get("webTestId") or "").lower(),
        str(criteria.get("componentId") or "").lower(),
        criteria.get("failedLocationCount"),
    )
    expected = (
        "Microsoft.Azure.Monitor.WebtestLocationAvailabilityCriteria",
        webtest_id.lower(),
        component_id.lower(),
        2,
    )
    if observed != expected:
        raise GateFailure("the public readiness alert location threshold changed")


def _verify_hash(path: Path, expected: str) -> None:
    import hashlib

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected:
        raise GateFailure(f"immutable source hash mismatch for {path.name}")


def _prepare_source(root: Path) -> tuple[Path, Path]:
    source = root / "source"
    _run(("git", "init", "--quiet", str(source)))
    _run(("git", "-C", str(source), "remote", "add", "origin", SOURCE_REPOSITORY))
    _run(
        (
            "git",
            "-C",
            str(source),
            "fetch",
            "--quiet",
            "--depth",
            "1",
            "origin",
            SOURCE_COMMIT,
        ),
        timeout=180,
    )
    _run(("git", "-C", str(source), "checkout", "--quiet", "--detach", "FETCH_HEAD"))
    observed = _run(("git", "-C", str(source), "rev-parse", "HEAD")).stdout.strip()
    if observed != SOURCE_COMMIT:
        raise GateFailure("the immutable source commit did not match")
    module = source / "deploy" / "azure" / "observability.bicep"
    parameters = source / "deploy" / "azure" / "observability.bicepparam"
    _verify_hash(module, BICEP_SHA256)
    _verify_hash(parameters, PARAMETERS_SHA256)
    return module, parameters


def _ensure_bicep() -> None:
    result = _run(("az", "bicep", "version"), check=False)
    if result.returncode or BICEP_VERSION not in result.stdout:
        _run(("az", "bicep", "install", "--version", f"v{BICEP_VERSION}"), timeout=180)
    version = _run(("az", "bicep", "version")).stdout
    if BICEP_VERSION not in version:
        raise GateFailure("the pinned Bicep compiler is unavailable")


def _deployment_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "ABDA_DEPLOY_LOCATION": LOCATION,
            "ABDA_DEPLOY_ALERT_PREFIX": RESOURCE_PREFIX,
            "ABDA_DEPLOY_APP_NAME": APP_NAME,
            "ABDA_DEPLOY_LOG_WORKSPACE_NAME": LOG_WORKSPACE_NAME,
            "ABDA_DEPLOY_PUBLIC_READINESS_URL": PUBLIC_READINESS_URL,
            "ABDA_DEPLOY_ALERT_EMAIL": ALERT_EMAIL,
        }
    )
    return environment


def _resource_json(resource_id: str, api_version: str) -> Any:
    return _az_json(("resource", "show", "--ids", resource_id, "--api-version", api_version))


def _register_provider_if_needed() -> None:
    provider = _az_json(("provider", "show", "--namespace", "Microsoft.Insights"))
    state = str((provider or {}).get("registrationState") or "")
    print(f"microsoft_insights_provider: {state or 'unknown'}")
    if state == "Registered":
        return
    if state == "Registering":
        _run(
            ("az", "provider", "register", "--namespace", "Microsoft.Insights", "--wait"),
            timeout=900,
        )
        provider = _az_json(("provider", "show", "--namespace", "Microsoft.Insights"))
        if str((provider or {}).get("registrationState") or "") != "Registered":
            raise GateFailure("the in-progress Microsoft.Insights registration did not complete")
        return
    if state not in {"NotRegistered", "Unregistered"}:
        raise GateFailure("Microsoft.Insights is not in a safe registration state")
    print("Registering Microsoft.Insights enables Azure Monitor resources in this subscription.")
    print("It does not create an alert, change the application, or set a budget.")
    confirmation = input("Type REGISTER_ABDA_INSIGHTS to continue: ").strip()
    if confirmation != "REGISTER_ABDA_INSIGHTS":
        raise GateFailure("Microsoft.Insights registration was not authorized")
    print("Confirmation accepted. Waiting for Microsoft.Insights registration...")
    _run(
        ("az", "provider", "register", "--namespace", "Microsoft.Insights", "--wait"),
        timeout=900,
    )
    provider = _az_json(("provider", "show", "--namespace", "Microsoft.Insights"))
    if str((provider or {}).get("registrationState") or "") != "Registered":
        raise GateFailure("Microsoft.Insights registration did not complete")


def main() -> int:
    section = "startup"
    try:
        if not sys.stdin.isatty():
            raise GateFailure("this deployment gate requires an interactive Cloud Shell")
        for executable in ("az", "git"):
            if shutil.which(executable) is None:
                raise GateFailure(f"required executable {executable!r} is unavailable")
        print(f"ABDA-NL observability alert gate revision: {SCRIPT_REVISION}")
        print("This gate creates six bounded monitor resources, then sends one test email.")
        print("It does not deploy application code, restart a replica, call a model, or change a budget.")
        print("The three-region standard web test is billable per scheduled execution.")

        with tempfile.TemporaryDirectory(prefix="abda-nl-alerts-") as temporary:
            root = Path(temporary)
            section = "immutable source verification"
            print("\n[1/8] Verifying immutable source and the Bicep compiler...")
            _, parameters = _prepare_source(root)
            _ensure_bicep()

            section = "Azure identity and provider verification"
            print("\n[2/8] Verifying the exact Azure identity and monitor provider...")
            account = _az_json(("account", "show"))
            validate_identity(account)
            _register_provider_if_needed()

            section = "application and metric verification"
            print("\n[3/8] Verifying the application, workspace, and live metric definitions...")
            app = _az_json(("containerapp", "show", "--name", APP_NAME, "--resource-group", RESOURCE_GROUP))
            app_id = validate_app(app)
            workspace = _az_json(
                (
                    "monitor",
                    "log-analytics",
                    "workspace",
                    "show",
                    "--workspace-name",
                    LOG_WORKSPACE_NAME,
                    "--resource-group",
                    RESOURCE_GROUP,
                )
            )
            workspace_id = validate_log_workspace(workspace)
            definitions = _az_json(("monitor", "metrics", "list-definitions", "--resource", app_id))
            validate_metric_definitions(definitions)
            print("metric_contract: Requests/Total/statusCodeCategory and Replicas/Minimum")
            print("log_analytics_retention_days: 30")

            section = "provider-validated deployment review"
            print("\n[4/8] Validating the module and reviewing the exact Azure changes...")
            deployment_env = _deployment_environment()
            _run(
                (
                    "az",
                    "deployment",
                    "group",
                    "validate",
                    "--name",
                    DEPLOYMENT_NAME,
                    "--resource-group",
                    RESOURCE_GROUP,
                    "--parameters",
                    str(parameters),
                    "--only-show-errors",
                    "--output",
                    "none",
                ),
                timeout=300,
                env=deployment_env,
            )
            result = _run(
                (
                    "az",
                    "deployment",
                    "group",
                    "what-if",
                    "--name",
                    DEPLOYMENT_NAME,
                    "--resource-group",
                    RESOURCE_GROUP,
                    "--parameters",
                    str(parameters),
                    "--result-format",
                    "ResourceIdOnly",
                    "--no-pretty-print",
                    "--only-show-errors",
                    "--output",
                    "json",
                ),
                timeout=600,
                env=deployment_env,
            )
            try:
                mutations = validate_what_if(json.loads(result.stdout))
            except json.JSONDecodeError as exc:
                raise GateFailure("the Azure what-if returned invalid JSON") from exc
            print("Planned Azure changes:")
            if mutations:
                for change_type, resource_id in mutations:
                    print(f"  {change_type:<7} {resource_id}")
            else:
                print("  No resource mutation reported. Exact resources will still be verified.")

            print("\nThis one confirmation authorizes only:")
            print(f"  action group {ACTION_GROUP_NAME} to {ALERT_EMAIL}")
            print(f"  metric alerts {SERVER_ERROR_ALERT_NAME} and {UNAVAILABLE_ALERT_NAME}")
            print(f"  Application Insights component {APPLICATION_INSIGHTS_NAME}")
            print(f"  three-region standard web test {READINESS_TEST_NAME}")
            print(f"  public readiness alert {READINESS_ALERT_NAME}")
            print("  one Azure Monitor test email to the same public support address")
            print("The standard test schedules about 25,920 location executions per 30 days.")
            confirmation = input("Type DEPLOY_AND_TEST_ABDA_ALERTS to continue: ").strip()
            if confirmation != "DEPLOY_AND_TEST_ABDA_ALERTS":
                print("Cancelled without deploying or sending a test notification.")
                return 0

            section = "bounded alert deployment"
            print("\n[5/8] Deploying the reviewed alert resources...")
            _run(
                (
                    "az",
                    "deployment",
                    "group",
                    "create",
                    "--name",
                    DEPLOYMENT_NAME,
                    "--resource-group",
                    RESOURCE_GROUP,
                    "--parameters",
                    str(parameters),
                    "--mode",
                    "Incremental",
                    "--only-show-errors",
                    "--output",
                    "none",
                ),
                timeout=900,
                env=deployment_env,
            )

            section = "deployed resource verification"
            print("\n[6/8] Verifying exact receivers, scopes, thresholds, and actions...")
            action_group_id = _resource_id("Microsoft.Insights/actionGroups", ACTION_GROUP_NAME)
            server_error_id = _resource_id("Microsoft.Insights/metricAlerts", SERVER_ERROR_ALERT_NAME)
            unavailable_id = _resource_id("Microsoft.Insights/metricAlerts", UNAVAILABLE_ALERT_NAME)
            component_id = _resource_id("Microsoft.Insights/components", APPLICATION_INSIGHTS_NAME)
            webtest_id = _resource_id("Microsoft.Insights/webtests", READINESS_TEST_NAME)
            readiness_alert_id = _resource_id(
                "Microsoft.Insights/metricAlerts", READINESS_ALERT_NAME
            )
            group = _resource_json(action_group_id, "2023-01-01")
            server_error = _resource_json(server_error_id, "2018-03-01")
            unavailable = _resource_json(unavailable_id, "2018-03-01")
            component = _resource_json(component_id, "2020-02-02")
            webtest = _resource_json(webtest_id, "2022-06-15")
            readiness_alert = _resource_json(readiness_alert_id, "2018-03-01")
            validated_group_id = validate_action_group(group)
            validate_metric_alert(
                server_error,
                expected_id=server_error_id,
                app_id=app_id,
                action_group_id=validated_group_id,
                severity=2,
                metric_name="Requests",
                operator="GreaterThanOrEqual",
                aggregation="Total",
                threshold=5,
                dimension={
                    "name": "statusCodeCategory",
                    "operator": "Include",
                    "values": ["5xx"],
                },
            )
            validate_metric_alert(
                unavailable,
                expected_id=unavailable_id,
                app_id=app_id,
                action_group_id=validated_group_id,
                severity=1,
                metric_name="Replicas",
                operator="LessThan",
                aggregation="Minimum",
                threshold=1,
                dimension=None,
            )
            validated_component_id = validate_application_insights(
                component, workspace_id
            )
            validated_webtest_id = validate_readiness_test(webtest)
            validate_readiness_alert(
                readiness_alert,
                webtest_id=validated_webtest_id,
                component_id=validated_component_id,
                action_group_id=validated_group_id,
            )

            section = "test notification submission"
            print("\n[7/8] Sending one bounded Azure Monitor test notification...")
            _run(
                (
                    "az",
                    "monitor",
                    "action-group",
                    "test-notifications",
                    "create",
                    "--action-group",
                    ACTION_GROUP_NAME,
                    "--resource-group",
                    RESOURCE_GROUP,
                    "--alert-type",
                    "metricstaticthreshold",
                    "--add-action",
                    "email",
                    "abda-support",
                    ALERT_EMAIL,
                    "usecommonalertschema",
                    "--only-show-errors",
                    "--output",
                    "none",
                ),
                timeout=300,
            )

            section = "final receipt"
            print("\n[8/8] Recording the content-free deployment receipt...")
            print("\nABDA-NL observability alert status:")
            print(f"script_revision: {SCRIPT_REVISION}")
            print(f"source_commit: {SOURCE_COMMIT}")
            print(f"subscription_id: {SUBSCRIPTION_ID}")
            print(f"resource_group: {RESOURCE_GROUP}")
            print(f"application: {APP_NAME}")
            print(f"action_group: {ACTION_GROUP_NAME}")
            print(f"server_error_alert: {SERVER_ERROR_ALERT_NAME}")
            print(f"unavailable_alert: {UNAVAILABLE_ALERT_NAME}")
            print(f"application_insights: {APPLICATION_INSIGHTS_NAME}")
            print(f"public_readiness_test: {READINESS_TEST_NAME}")
            print(f"public_readiness_alert: {READINESS_ALERT_NAME}")
            print(f"public_readiness_url: {PUBLIC_READINESS_URL}")
            print("public_readiness_locations: 3")
            print("public_readiness_frequency_seconds: 300")
            print(f"alert_destination: {ALERT_EMAIL}")
            print("test_notification_submission: accepted")
            print("application_changed: false")
            print("model_provider_called: false")
            print("result: OBSERVABILITY_ALERTS_DEPLOYED_DELIVERY_CONFIRMATION_PENDING")
            return 0
    except KeyboardInterrupt:
        print(f"\nSTOP: alert gate was interrupted in section: {section}", file=sys.stderr)
        return 130
    except (GateFailure, subprocess.TimeoutExpired) as exc:
        print(f"\nSTOP: alert gate failed in section: {section}", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        print("Do not delete Azure resources or rerun a separate deployment command.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
