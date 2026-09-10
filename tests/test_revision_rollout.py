"""Reviewable rollout rendering preserves credentials, privileges, and accounting phases."""
from __future__ import annotations

import base64
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import re

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load(name):
    path = ROOT / "deploy" / "azure" / name
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PREPARE = load("prepare-revision-rollout.py")
INSPECT = load("inspect-named-credit.py")
OLD_IMAGE = "ghcr.io/liu-hy/abda-nl@sha256:" + "1" * 64
NEW_IMAGE = "ghcr.io/liu-hy/abda-nl@sha256:" + "2" * 64
SOURCE = {"AZURE_OPENAI_ENDPOINT": "https://default-example.openai.azure.com/",
          "AZURE_OPENAI_API_KEY": "test-primary-key",
          "AZURE_OPUS5_ENDPOINT": "https://opus-example.services.ai.azure.com/",
          "AZURE_OPUS5_API_KEY": "test-scoped-key"}


@pytest.fixture
def state():
    application = {"name": "abda-nl-stg-web", "properties": {
        "latestReadyRevisionName": "abda-nl-stg-web--old",
        "configuration": {"activeRevisionsMode": "Single", "ingress": {
            "external": True, "targetPort": 8000, "customDomains": [{"name": "example.test"}],
            "traffic": [{"latestRevision": True, "weight": 100}]},
            "secrets": [{"name": "database-url"}, {"name": "foundry-api-key"}, {"name": "vault-secret"}]},
        "template": {"revisionSuffix": "old", "scale": {"minReplicas": 1, "maxReplicas": 3},
            "volumes": [{"name": "scratch", "storageType": "EmptyDir"}],
            "containers": [{"name": "web", "image": OLD_IMAGE,
                "resources": {"cpu": 0.25, "memory": "0.5Gi"},
                "probes": [{"type": "Readiness", "httpGet": {"path": "/healthz", "port": 8000}}],
                "volumeMounts": [{"volumeName": "scratch", "mountPath": "/tmp/scratch"}],
                "env": [{"name": "ABDA_DATABASE_URL", "secretRef": "database-url"},
                        {"name": "OPENROUTER_API_KEY", "secretRef": "openrouter-api-key"},
                        {"name": "ABDA_TRIAL_MAX_USERS", "value": "100"},
                        {"name": "AZURE_OPENAI_ENDPOINT", "value": "https://old-example.openai.azure.com"}]}]}}}
    job = {"name": "abda-nl-stg-migrate", "properties": {
        "configuration": {"triggerType": "Manual", "replicaRetryLimit": 0,
            "manualTriggerConfig": {"parallelism": 1, "replicaCompletionCount": 1},
            "secrets": [{"name": "admin-database-url"}, {"name": "app-database-password"}]},
        "template": {"containers": [{"name": "migrate", "image": OLD_IMAGE,
            "command": ["/opt/venv/bin/python"], "args": ["-m", "app.cli.migrate"],
            "resources": {"cpu": 0.25, "memory": "0.5Gi"}, "env": [
                {"name": "ABDA_DATABASE_URL", "secretRef": "admin-database-url"},
                {"name": "ABDA_DATABASE_APP_LOGIN", "value": "abda_app"},
                {"name": "ABDA_DATABASE_APP_PASSWORD", "secretRef": "app-database-password"},
                {"name": "OPENROUTER_API_KEY", "secretRef": "openrouter-api-key"}]}]}}}
    postgres = {"name": "abda-nl-stg-postgres-bgjhpbgw",
                "fullyQualifiedDomainName": "abda-nl-stg-postgres-bgjhpbgw.postgres.database.azure.com"}
    return application, job, postgres


def test_application_rollout_keeps_auth_network_scale_probes_and_existing_secrets(state):
    app, _, _ = state
    before = deepcopy(app)
    template = PREPARE.app_template(app, image=NEW_IMAGE, suffix="rev-recovery-stage",
                                    source=SOURCE, project="access-example", auto_activate=False)
    assert app == before
    assert template["scale"] == app["properties"]["template"]["scale"]
    web = template["containers"][0]
    old_web = app["properties"]["template"]["containers"][0]
    assert web["resources"] == old_web["resources"]
    assert web["probes"] == old_web["probes"]
    assert web["image"] == NEW_IMAGE
    env = {entry["name"]: entry for entry in web["env"]}
    for name in ("ABDA_DATABASE_URL", "OPENROUTER_API_KEY", "ABDA_TRIAL_MAX_USERS"):
        assert env[name] == next(item for item in old_web["env"] if item["name"] == name)
    assert env[PREPARE.AUTO_ACTIVATE]["value"] == "false"
    assert env["AZURE_OPUS5_API_KEY"]["secretRef"] == "foundry-opus5-api-key"
    assert env["AZURE_OPENAI_API_KEY"]["secretRef"] == "foundry-api-key"
    assert env["AZURE_ANTHROPIC_API_KEY"]["secretRef"] == "foundry-api-key"
    assert env["AZURE_ANTHROPIC_ENDPOINT"]["value"] == "https://default-example.services.ai.azure.com/anthropic"
    assert env["ANTHROPIC_FOUNDRY_BASE_URL"] == {"name": "ANTHROPIC_FOUNDRY_BASE_URL", "value": env["AZURE_ANTHROPIC_ENDPOINT"]["value"]}
    assert env["GOOGLE_CLOUD_PROJECT"]["value"] == env["GOOGLE_CLOUD_QUOTA_PROJECT"]["value"]
    assert "test-scoped-key" not in json.dumps(template)
    assert template["volumes"][-1]["secrets"] == [{"secretRef": "gcp-adc-json", "path": "adc.json"}]
    assert web["volumeMounts"] == [*old_web["volumeMounts"], PREPARE.MOUNT]


def test_only_activation_gate_and_revision_suffix_change_between_accounting_phases(state):
    app, _, _ = state
    kwargs = dict(image=NEW_IMAGE, source=SOURCE, project="access-example")
    stage = PREPARE.app_template(app, suffix="rev-stage", auto_activate=False, **kwargs)
    ready = PREPARE.app_template(app, suffix="rev-ready", auto_activate=True, **kwargs)
    ready["revisionSuffix"] = stage["revisionSuffix"]
    next(entry for entry in ready["containers"][0]["env"] if entry["name"] == PREPARE.AUTO_ACTIVATE)["value"] = "false"
    assert ready == stage


def test_secret_configuration_preserves_existing_values_and_key_vault_references(state):
    app, _, _ = state
    listed = [{"name": "database-url", "value": "test-database-credential"},
              {"name": "foundry-api-key", "value": "test-primary-key"},
              {"name": "vault-secret", "keyVaultUrl": "https://example.vault.azure.net/secrets/test", "identity": "system"}]
    before = deepcopy(listed)
    cfg = PREPARE.secret_configuration(app, listed, SOURCE, '{"type":"authorized_user"}')
    assert listed == before
    assert cfg["ingress"] == app["properties"]["configuration"]["ingress"]
    assert cfg["activeRevisionsMode"] == "Single"
    assert cfg["secrets"][:3] == listed
    assert {item["name"] for item in cfg["secrets"]} == {"database-url", "foundry-api-key", "vault-secret", "foundry-opus5-api-key", "gcp-adc-json"}
    with pytest.raises(PREPARE.PreparationError):
        PREPARE.secret_configuration(app, listed[:2], SOURCE, "test-adc")
    stale = deepcopy(listed)
    stale[1]["value"] = "test-key-from-different-resource"
    with pytest.raises(PREPARE.PreparationError, match="resource lineage"):
        PREPARE.secret_configuration(app, stale, SOURCE, "test-adc")


@pytest.mark.parametrize("change", ["extra-container", "mutable-image", "wrong-role", "scheduled-job", "retry-job", "wrong-database"])
def test_read_only_probe_rejects_changed_execution_boundaries(state, change):
    app, job, postgres = state
    if change == "extra-container":
        app["properties"]["template"]["containers"].append({"name": "other"})
    elif change == "mutable-image":
        app["properties"]["template"]["containers"][0]["image"] = "ghcr.io/liu-hy/abda-nl:latest"
    elif change == "wrong-role":
        job["properties"]["template"]["containers"][0]["env"][1]["value"] = "admin"
    elif change == "scheduled-job":
        job["properties"]["configuration"]["triggerType"] = "Schedule"
    elif change == "retry-job":
        job["properties"]["configuration"]["replicaRetryLimit"] = 1
    else:
        postgres["name"] = "other-database"
    with pytest.raises(INSPECT.InspectionError):
        INSPECT.read_only_job_template(app, job, postgres)


def test_read_only_job_has_no_administrator_or_provider_credentials(state):
    app, job, postgres = state
    before = deepcopy(state)
    template = INSPECT.read_only_job_template(app, job, postgres)
    assert state == before
    container = template["containers"][0]
    assert container["image"] == OLD_IMAGE
    assert container["resources"] == job["properties"]["template"]["containers"][0]["resources"]
    assert {entry["name"] for entry in container["env"]} == {"ABDA_DATABASE_APP_LOGIN", "ABDA_DATABASE_APP_PASSWORD", "ABDA_POSTGRES_HOST"}
    assert {entry["secretRef"] for entry in container["env"] if "secretRef" in entry} == {"app-database-password"}
    assert "admin-database-url" not in json.dumps(template)
    assert "OPENROUTER" not in json.dumps(template)


@pytest.mark.parametrize("apply", [False, True])
def test_reconciliation_uses_new_image_and_explicit_application_under_restricted_role(state, apply):
    app, job, postgres = state
    result = PREPARE.reconcile_template(app, job, postgres, image=NEW_IMAGE, apply=apply)
    container = result["containers"][0]
    assert container["image"] == NEW_IMAGE
    assert not any(entry.get("secretRef") == "admin-database-url" for entry in container["env"])
    encoded = re.search(r"b64decode\('([^']+)'\)", container["args"][1]).group(1)
    runner = base64.b64decode(encoded).decode()
    assert "runpy.run_module('app.cli.reconcile_named_credit'" in runner
    assert ("['--apply']" in runner) == apply
    assert "ABDA_NAMED_CREDIT_AUTO_ACTIVATE" not in runner


def test_migration_keeps_administrator_entrypoint_and_default_privilege_provisioning(state):
    _, job, _ = state
    before = deepcopy(job)
    template = PREPARE.migration_template(job, NEW_IMAGE)
    assert job == before
    expected = deepcopy(job["properties"]["template"])
    expected["containers"][0]["image"] = NEW_IMAGE
    assert template == expected


@pytest.mark.parametrize("endpoint", ["http://example.openai.azure.com", "https://example.org", "https://example.openai.azure.com@evil.test", "https://example.openai.azure.com?key=unsafe"])
def test_endpoint_validation_does_not_copy_unverified_or_credential_bearing_urls(endpoint):
    with pytest.raises(PREPARE.PreparationError):
        PREPARE.azure_endpoint(endpoint)


def test_mount_collision_stops_preparation(state):
    app, _, _ = state
    app["properties"]["template"]["containers"][0]["volumeMounts"].append({"volumeName": "different", "mountPath": "/var/run/abda-gcp"})
    with pytest.raises(PREPARE.PreparationError):
        PREPARE.app_template(app, image=NEW_IMAGE, suffix="test-stage", source=SOURCE, project="access-example", auto_activate=False)


def test_protected_output_is_exclusive_and_owner_only(tmp_path):
    path = tmp_path / "secrets.patch.json"
    PREPARE.write_private(path, {"secret": "test-only"})
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        PREPARE.write_private(path, {"secret": "replacement"})
    assert json.loads(path.read_text()) == {"secret": "test-only"}
