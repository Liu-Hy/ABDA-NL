"""Static contracts for the operator-owned Azure alert resources."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AZURE = ROOT / "deploy" / "azure"


def test_alert_module_has_one_operator_action_group_and_three_metric_alerts() -> None:
    module = (AZURE / "observability.bicep").read_text(encoding="utf-8")

    assert module.count("Microsoft.Insights/actionGroups@2023-01-01") == 1
    assert module.count("Microsoft.Insights/metricAlerts@2018-03-01") == 3
    assert module.count("Microsoft.Insights/components@2020-02-02") == 1
    assert module.count("Microsoft.Insights/webtests@2022-06-15") == 1
    assert "emailAddress: alertEmail" in module
    assert "useCommonAlertSchema: true" in module
    assert module.count("actionGroupId: operatorActionGroup.id") == 3


def test_alerts_cover_sustained_server_errors_and_no_active_replica() -> None:
    module = (AZURE / "observability.bicep").read_text(encoding="utf-8")

    for expected in (
        "metricName: 'Requests'",
        "name: 'statusCodeCategory'",
        "'5xx'",
        "operator: 'GreaterThanOrEqual'",
        "timeAggregation: 'Total'",
        "threshold: 5",
        "metricName: 'Replicas'",
        "operator: 'LessThan'",
        "timeAggregation: 'Minimum'",
        "threshold: 1",
        "evaluationFrequency: 'PT1M'",
        "windowSize: 'PT5M'",
        "autoMitigate: true",
    ):
        assert expected in module


def test_alert_parameters_are_operator_controlled_and_contain_no_secret() -> None:
    parameters = (AZURE / "observability.bicepparam").read_text(encoding="utf-8")

    assert "ABDA_DEPLOY_ALERT_PREFIX" in parameters
    assert "ABDA_DEPLOY_APP_NAME" in parameters
    assert "ABDA_DEPLOY_LOG_WORKSPACE_NAME" in parameters
    assert "ABDA_DEPLOY_PUBLIC_READINESS_URL" in parameters
    assert "ABDA_DEPLOY_ALERT_EMAIL" in parameters
    assert "support@abda-nl.org" in parameters
    for forbidden in ("password", "secret", "token", "api_key", "API_KEY"):
        assert forbidden not in parameters


def test_standard_public_readiness_test_is_retried_and_tls_checked() -> None:
    module = (AZURE / "observability.bicep").read_text(encoding="utf-8")

    for expected in (
        "Kind: 'standard'",
        "Frequency: 300",
        "Timeout: 30",
        "RetryEnabled: true",
        "us-il-ch1-azr",
        "us-va-ash-azr",
        "emea-nl-ams-azr",
        "ExpectedHttpStatusCode: 200",
        "SSLCheck: true",
        "SSLCertRemainingLifetimeCheck: 14",
        "Microsoft.Azure.Monitor.WebtestLocationAvailabilityCriteria",
        "failedLocationCount: 2",
    ):
        assert expected in module
