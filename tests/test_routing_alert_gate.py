"""Exact resource, query, and source boundaries for routing alerts."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "deploy/azure/observability.bicep"
PARAMETERS = ROOT / "deploy/azure/observability.bicepparam"


@pytest.fixture
def gate():
    path = ROOT / "deploy/azure/gate14_observability_alerts.py"
    spec = importlib.util.spec_from_file_location("routing_alert_gate", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _bundle(gate):
    return {
        "templateJson": json.dumps({"resources": [
            {"type": "Microsoft.Insights/actionGroups", "condition": "[not(parameters('routingAlertsOnly'))]"},
            *[{"type": "Microsoft.Insights/scheduledQueryRules", "apiVersion": "2023-12-01",
               "name": f"[format('{{0}}-{suffix}', parameters('resourcePrefix'))]",
               "dependsOn": ["legacy-receiver"]} for suffix in gate.ROUTING_ALERT_SUFFIXES],
        ], "outputs": {"legacyOutput": {"value": "legacy-resource"}}}),
        "parametersJson": json.dumps({"parameters": {
            name: {"value": value} for name, value in gate._routing_parameters(1_000_000).items()
        }}),
        "templateSpecId": None,
    }


def _alert(gate, suffix):
    contract = gate.routing_alert_contracts()[suffix]
    criterion = {key: contract[key] for key in (
        "query", "timeAggregation", "threshold", "metricMeasureColumn", "dimensions", "failingPeriods")}
    criterion["operator"] = "GreaterThanOrEqual"
    return {
        "id": gate._resource_id("Microsoft.Insights/scheduledQueryRules", gate.RESOURCE_PREFIX + "-" + suffix),
        "location": gate.LOCATION, "kind": "LogAlert",
        "properties": {"enabled": True, "severity": contract["severity"],
            "evaluationFrequency": "PT5M", "windowSize": contract["windowSize"],
            "autoMitigate": True, "skipQueryValidation": False,
            "scopes": [gate._resource_id("Microsoft.OperationalInsights/workspaces", gate.LOG_WORKSPACE_NAME)],
            "criteria": {"allOf": [criterion]},
            "actions": {"actionGroups": [gate._resource_id("Microsoft.Insights/actionGroups", gate.ACTION_GROUP_NAME)]}},
    }


@pytest.mark.parametrize("suffix", ["llm-configuration", "llm-circuit", "llm-fallback-spend"])
def test_current_mode_accepts_only_the_exact_three_new_resource_ids(gate, suffix):
    resource_id = gate._resource_id("Microsoft.Insights/scheduledQueryRules", gate.RESOURCE_PREFIX + "-" + suffix)
    change = {"status": "Succeeded", "changes": [{"changeType": "Create", "resourceId": resource_id}]}
    assert gate.validate_what_if(change, routing_alerts_only=True) == [("Create", resource_id)]
    with pytest.raises(gate.GateFailure):
        gate.validate_what_if(change)


@pytest.mark.parametrize("resource_type,name", [
    ("Microsoft.Insights/scheduledQueryRules", "unreviewed-extra-rule"),
    ("Microsoft.Insights/actionGroups", "abda-nl-stg-operators"),
    ("Microsoft.App/containerApps", "abda-nl-stg-web"),
    ("Microsoft.Insights/metricAlerts", "abda-nl-stg-web-5xx"),
])
def test_current_mode_refuses_legacy_or_unrelated_resource_mutations(gate, resource_type, name):
    with pytest.raises(gate.GateFailure):
        gate.validate_what_if({"changes": [{"changeType": "Modify", "resourceId": gate._resource_id(resource_type, name)}]},
                             routing_alerts_only=True)


@pytest.mark.parametrize("mutation", ["Delete", "Unsupported"])
def test_current_mode_refuses_unsafe_changes_even_to_new_rules(gate, mutation):
    with pytest.raises(gate.GateFailure):
        gate.validate_what_if({"changes": [{"changeType": mutation, "resourceId": gate._resource_id(
            "Microsoft.Insights/scheduledQueryRules", "abda-nl-stg-llm-circuit")}]}, routing_alerts_only=True)


def test_local_source_freezes_reviewed_bytes_and_rejects_wrong_hashes(gate, tmp_path):
    source = tmp_path / "input"
    source.mkdir()
    module, parameters = source / "module.bicep", source / "parameters.bicepparam"
    module.write_text("reviewed module")
    parameters.write_text("reviewed parameters")
    staging = tmp_path / "staging"
    staging.mkdir()
    copied_module, copied_parameters = gate.prepare_local_source(staging, module=module, parameters=parameters,
        module_sha256=hashlib.sha256(module.read_bytes()).hexdigest(),
        parameters_sha256=hashlib.sha256(parameters.read_bytes()).hexdigest())
    module.write_text("later change")
    assert copied_module.read_text() == "reviewed module"
    assert copied_parameters.read_text() == "reviewed parameters"
    rejected = tmp_path / "rejected"
    rejected.mkdir()
    with pytest.raises(gate.GateFailure, match="hash mismatch"):
        gate.prepare_local_source(rejected, module=module, parameters=parameters,
            module_sha256="0" * 64, parameters_sha256=hashlib.sha256(parameters.read_bytes()).hexdigest())


def test_compiled_payload_contains_only_new_rules_and_exact_reviewed_parameters(gate):
    template_text, parameter_text = gate.validate_compiled_routing_bundle(_bundle(gate), 1_000_000)
    template = json.loads(template_text)
    assert len(template["resources"]) == 3
    assert all(resource["type"] == "Microsoft.Insights/scheduledQueryRules" and "dependsOn" not in resource
               for resource in template["resources"])
    assert "outputs" not in template
    assert json.loads(parameter_text)["parameters"]["routingAlertsOnly"]["value"] is True


@pytest.mark.parametrize("fault", ["target", "threshold", "routing_mode", "active_resource", "extra_rule", "disabled_rule"])
def test_compilation_cannot_expand_reviewed_target_or_resource_set(gate, fault):
    bundle = _bundle(gate)
    parameters, template = json.loads(bundle["parametersJson"]), json.loads(bundle["templateJson"])
    if fault == "target":
        parameters["parameters"]["appName"]["value"] = "another-app"
    elif fault == "threshold":
        parameters["parameters"]["fallbackSpendThresholdMicrousd"]["value"] = 50_000_000
    elif fault == "routing_mode":
        parameters["parameters"]["routingAlertsOnly"]["value"] = False
    elif fault == "active_resource":
        template["resources"][0].pop("condition")
    elif fault == "extra_rule":
        template["resources"].append(copy.deepcopy(template["resources"][1]))
    else:
        template["resources"][1]["condition"] = False
    bundle.update(templateJson=json.dumps(template), parametersJson=json.dumps(parameters))
    with pytest.raises(gate.GateFailure):
        gate.validate_compiled_routing_bundle(bundle, 1_000_000)


@pytest.mark.parametrize("fault", ["bundle", "template", "parameters", "parameter_map"])
def test_malformed_compilation_output_stops_with_a_typed_failure(gate, fault):
    bundle = _bundle(gate)
    if fault == "bundle":
        bundle = []
    elif fault == "template":
        bundle["templateJson"] = "null"
    elif fault == "parameters":
        bundle["parametersJson"] = "[]"
    else:
        bundle["parametersJson"] = json.dumps({"parameters": []})
    with pytest.raises(gate.GateFailure):
        gate.validate_compiled_routing_bundle(bundle, 1_000_000)


@pytest.mark.parametrize("suffix", ["llm-configuration", "llm-circuit", "llm-fallback-spend"])
def test_deployed_rule_contract_and_template_queries_agree(gate, suffix):
    gate.validate_routing_alert(_alert(gate, suffix), suffix=suffix)
    queries = re.findall(r"var (\w+Query) = format\('''\n(.*?)''', appName\)", TEMPLATE.read_text(), re.DOTALL)
    actual = {name: query.replace("{0}", gate.APP_NAME).strip() for name, query in queries}
    name = {"llm-configuration": "routeConfigurationQuery", "llm-circuit": "routeCircuitQuery",
            "llm-fallback-spend": "fallbackSpendQuery"}[suffix]
    assert actual[name] == gate.routing_alert_contracts()[suffix]["query"]
    assert "| project TimeGenerated" in actual[name] or "| summarize Opens" in actual[name]


@pytest.mark.parametrize("fault", ["query", "scope", "action", "payload", "threshold", "periods", "disabled", "mute", "skip_validation"])
def test_live_verifier_rejects_wrong_filters_receivers_or_alert_behavior(gate, fault):
    alert = _alert(gate, "llm-fallback-spend")
    properties, criterion = alert["properties"], alert["properties"]["criteria"]["allOf"][0]
    if fault == "query":
        criterion["query"] = "ContainerAppConsoleLogs_CL | project Log_s"
    elif fault == "scope":
        properties["scopes"] = ["/subscriptions/wrong/workspaces/another"]
    elif fault == "action":
        properties["actions"]["actionGroups"] = ["/unreviewed/receiver"]
    elif fault == "payload":
        properties["actions"]["customProperties"] = {"private": "unreviewed"}
    elif fault == "threshold":
        criterion["threshold"] = 500_000_000
    elif fault == "periods":
        criterion["failingPeriods"]["numberOfEvaluationPeriods"] = 99
    elif fault == "disabled":
        properties["enabled"] = False
    elif fault == "mute":
        properties["muteActionsDuration"] = "P1D"
    else:
        properties["skipQueryValidation"] = True
    with pytest.raises(gate.GateFailure):
        gate.validate_routing_alert(alert, suffix="llm-fallback-spend")


@pytest.mark.parametrize("field", ["properties", "scopes", "actions", "criteria"])
def test_malformed_readback_stops_with_a_typed_failure(gate, field):
    alert = _alert(gate, "llm-fallback-spend")
    if field == "properties":
        alert[field] = []
    else:
        alert["properties"][field] = "malformed"
    with pytest.raises(gate.GateFailure):
        gate.validate_routing_alert(alert, suffix="llm-fallback-spend")


@pytest.mark.parametrize("mode,fault", [
    ("preview", None), ("verify", None), ("apply", None),
    ("apply", "unexpected_mutation"), ("apply", "unregistered"),
    ("verify", "wrong_rule"), ("apply", "wrong_rule"),
])
def test_routing_mode_enforces_mutation_and_notification_boundaries(gate, monkeypatch, capsys, mode, fault):
    calls = []
    monkeypatch.setattr(gate, "_ensure_bicep", lambda: None)
    monkeypatch.setattr(gate, "_run", lambda *_args, **_kwargs: type("Result", (), {"stdout": json.dumps(_bundle(gate))})())
    for name in ("validate_identity", "validate_app", "validate_log_workspace", "validate_action_group"):
        monkeypatch.setattr(gate, name, lambda *_args: None)

    def azure(arguments, **_kwargs):
        calls.append(arguments)
        if arguments[:2] == ("provider", "show"):
            return {"registrationState": "NotRegistered" if fault == "unregistered" else "Registered"}
        if arguments[:3] == ("deployment", "group", "what-if"):
            if fault == "unexpected_mutation":
                return {"changes": [{"changeType": "Modify", "resourceId": gate._resource_id(
                    "Microsoft.Insights/actionGroups", gate.ACTION_GROUP_NAME)}]}
            return {"changes": []}
        if arguments[:2] == ("resource", "show"):
            for suffix in gate.ROUTING_ALERT_SUFFIXES:
                if arguments[3].endswith("-" + suffix):
                    alert = _alert(gate, suffix)
                    if fault == "wrong_rule":
                        alert["properties"]["enabled"] = False
                    return alert
        return {}

    monkeypatch.setattr(gate, "_az_json", azure)
    args = ["--local-template", str(TEMPLATE), "--template-sha256", hashlib.sha256(TEMPLATE.read_bytes()).hexdigest(),
            "--local-parameters", str(PARAMETERS), "--parameters-sha256", hashlib.sha256(PARAMETERS.read_bytes()).hexdigest()]
    if mode != "preview":
        args.append("--verify-only" if mode == "verify" else "--deploy-reviewed-routing-alerts")
    assert gate.routing_main(args) == (1 if fault else 0)
    output = capsys.readouterr()
    if fault:
        assert not output.out
        assert "GateFailure" in output.err
    else:
        receipt = json.loads(output.out)
        assert receipt["result"] == ("ROUTING_ALERTS_PREVIEWED" if mode == "preview" else "ROUTING_ALERTS_VERIFIED")
        assert receipt["deployed"] is (mode == "apply")
        assert not receipt["test_email_sent"]
    deployments = [command for command in calls if command[:2] == ("deployment", "group")]
    applied = any(command[2] == "create" for command in deployments)
    assert applied is (mode == "apply" and fault in (None, "wrong_rule"))
    if mode == "verify":
        assert not deployments
    if applied:
        assert [command[2] for command in deployments] == ["validate", "what-if", "create"]
    assert not any("test-notifications" in command or "register" in command for command in calls)
