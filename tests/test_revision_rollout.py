"""Reviewable rollout rendering preserves credentials, privileges, and accounting phases."""
from __future__ import annotations

import base64
from copy import deepcopy
from dataclasses import asdict, replace
import hashlib
import importlib.util
import json
from pathlib import Path
import re

import pytest

from app.services.credit_policy import NAMED_CREDIT_EMAILS
from deploy.azure.rollout_target import RolloutTarget, TargetError, load_target


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
TARGET = RolloutTarget(
    subscription="11111111-1111-4111-8111-111111111111",
    tenant="22222222-2222-4222-8222-222222222222", operator="operator@example.test",
    resource_group="abda-nl-staging", app="abda-nl-stg-web", job="abda-nl-stg-migrate",
    postgres="abda-nl-stg-postgres-bgjhpbgw", database="abda", app_login="abda_app",
)
ELIGIBILITY = {"name": "credit-eligibility-pepper", "value": "test-only-stable-eligibility-key-" + "a" * 32}
SOURCE = {"AZURE_OPENAI_ENDPOINT": "https://default-example.openai.azure.com/",
          "AZURE_OPENAI_API_KEY": "test-primary-key",
          "AZURE_OPUS5_ENDPOINT": "https://opus-example.services.ai.azure.com/",
          "AZURE_OPUS5_API_KEY": "test-scoped-key"}


@pytest.fixture
def state():
    application = {"name": "abda-nl-stg-web", "properties": {
        "latestReadyRevisionName": "abda-nl-stg-web--old",
        "latestRevisionName": "abda-nl-stg-web--old", "provisioningState": "Succeeded",
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
        "provisioningState": "Succeeded",
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
    for resource, kind in ((application, "Microsoft.App/containerApps"), (job, "Microsoft.App/jobs"),
                           (postgres, "Microsoft.DBforPostgreSQL/flexibleServers")):
        resource["id"] = (TARGET.arm_root.removeprefix("https://management.azure.com")
                          + f"/providers/{kind}/{resource['name']}")
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
    assert env[PREPARE.ELIGIBILITY_ENV]["secretRef"] == "credit-eligibility-pepper"
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
    cfg = PREPARE.secret_configuration(app, listed, SOURCE, '{"type":"authorized_user"}', eligibility=ELIGIBILITY)
    assert listed == before
    assert cfg["ingress"] == app["properties"]["configuration"]["ingress"]
    assert cfg["activeRevisionsMode"] == "Single"
    assert cfg["secrets"][:3] == listed
    assert {item["name"] for item in cfg["secrets"]} == {"database-url", "foundry-api-key", "vault-secret", "foundry-opus5-api-key", "gcp-adc-json", "credit-eligibility-pepper"}
    with pytest.raises(PREPARE.PreparationError):
        PREPARE.secret_configuration(app, listed[:2], SOURCE, "test-adc", eligibility=ELIGIBILITY)
    stale = deepcopy(listed)
    stale[1]["value"] = "test-key-from-different-resource"
    with pytest.raises(PREPARE.PreparationError, match="resource lineage"):
        PREPARE.secret_configuration(app, stale, SOURCE, "test-adc", eligibility=ELIGIBILITY)


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
    with pytest.raises((INSPECT.InspectionError, TargetError)):
        INSPECT.read_only_job_template(app, job, postgres, target=TARGET)


def test_read_only_job_has_no_administrator_or_provider_credentials(state):
    app, job, postgres = state
    before = deepcopy(state)
    template = INSPECT.read_only_job_template(app, job, postgres, target=TARGET)
    assert state == before
    container = template["containers"][0]
    assert container["image"] == OLD_IMAGE
    assert container["resources"] == job["properties"]["template"]["containers"][0]["resources"]
    assert {entry["name"] for entry in container["env"]} == {"ABDA_DATABASE_APP_LOGIN", "ABDA_DATABASE_APP_PASSWORD", "ABDA_POSTGRES_HOST", "ABDA_DATABASE_NAME"}
    assert {entry["secretRef"] for entry in container["env"] if "secretRef" in entry} == {"app-database-password"}
    assert "admin-database-url" not in json.dumps(template)
    assert "OPENROUTER" not in json.dumps(template)


@pytest.mark.parametrize("apply", [False, True])
def test_reconciliation_uses_new_image_and_explicit_application_under_restricted_role(state, apply):
    app, job, postgres = state
    result = PREPARE.reconcile_template(app, job, postgres, image=NEW_IMAGE, apply=apply, target=TARGET)
    container = result["containers"][0]
    assert container["image"] == NEW_IMAGE
    assert not any(entry.get("secretRef") == "admin-database-url" for entry in container["env"])
    encoded = re.search(r"b64decode\('([^']+)'\)", container["args"][1]).group(1)
    runner = base64.b64decode(encoded).decode()
    assert "runpy.run_module('app.cli.reconcile_named_credit'" in runner
    assert ("['--apply']" in runner) == apply
    assert "ABDA_NAMED_CREDIT_AUTO_ACTIVATE" not in runner
    assert next(entry for entry in container["env"] if entry["name"] == PREPARE.ELIGIBILITY_ENV) == {
        "name": PREPARE.ELIGIBILITY_ENV, "secretRef": "credit-eligibility-pepper",
    }


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


def test_target_is_explicit_and_checked_at_full_resource_and_identity_boundaries(tmp_path, state):
    path = tmp_path / "target.json"
    path.write_text(json.dumps(asdict(TARGET)))
    selected = load_target(path)
    assert selected == TARGET
    identity = {"id": TARGET.subscription, "tenantId": TARGET.tenant,
                "user": {"name": TARGET.operator.upper()}, "state": "Enabled"}
    selected.require_identity(identity)
    identity["tenantId"] = TARGET.subscription
    with pytest.raises(TargetError, match="identity"):
        selected.require_identity(identity)
    app, job, postgres = state
    # Matching names in another subscription are still the wrong resources.
    app["id"] = app["id"].replace(TARGET.subscription, TARGET.tenant)
    with pytest.raises(TargetError, match="resource"):
        INSPECT.read_only_job_template(app, job, postgres, target=selected)
    bad = asdict(TARGET)
    bad["app_login"] = "postgres"
    path.write_text(json.dumps(bad))
    with pytest.raises(TargetError, match="complete, valid"):
        load_target(path)


def test_named_inspection_uses_the_central_policy_and_exported_readable_runner():
    assert repr(NAMED_CREDIT_EMAILS) in INSPECT.RUNNER
    assert "APPROVED_EMAILS" not in INSPECT.RUNNER
    compile(INSPECT.RUNNER, "inspection.runner.py", "exec")
    for apply in (False, True):
        compile(PREPARE.reconciliation_runner(apply=apply), "reconciliation.runner.py", "exec")


def test_explicit_different_deployment_keeps_exact_checks_without_source_edits(state):
    app, job, postgres = state
    target = replace(TARGET, app="another-web", job="another-migrate", postgres="another-postgres",
                     database="research", app_login="research_app")
    for resource, kind, name in ((app, "Microsoft.App/containerApps", target.app),
                                 (job, "Microsoft.App/jobs", target.job),
                                 (postgres, "Microsoft.DBforPostgreSQL/flexibleServers", target.postgres)):
        resource["name"] = name
        resource["id"] = target.arm_root.removeprefix("https://management.azure.com") + f"/providers/{kind}/{name}"
    postgres["fullyQualifiedDomainName"] = target.postgres + ".postgres.database.azure.com"
    next(item for item in job["properties"]["template"]["containers"][0]["env"]
         if item["name"] == "ABDA_DATABASE_APP_LOGIN")["value"] = target.app_login
    template = INSPECT.read_only_job_template(app, job, postgres, target=target)
    environment = {item["name"]: item for item in template["containers"][0]["env"]}
    assert environment["ABDA_DATABASE_APP_LOGIN"]["value"] == "research_app"
    assert environment["ABDA_DATABASE_NAME"]["value"] == "research"


def test_stable_eligibility_key_is_reused_and_never_silently_rotated(state):
    assert PREPARE.stable_eligibility_secret([ELIGIBILITY], [ELIGIBILITY]) == ELIGIBILITY
    assert PREPARE.stable_eligibility_secret([], [], supplied=ELIGIBILITY["value"]) == ELIGIBILITY
    with pytest.raises(PREPARE.PreparationError, match="initial eligibility setup"):
        PREPARE.stable_eligibility_secret([], [])
    with pytest.raises(PREPARE.PreparationError, match="rotate"):
        PREPARE.stable_eligibility_secret([ELIGIBILITY], [], supplied="another-stable-key" * 3)
    with pytest.raises(PREPARE.PreparationError, match="differ"):
        PREPARE.stable_eligibility_secret([ELIGIBILITY], [{**ELIGIBILITY, "value": "another-key" * 4}])
    with pytest.raises(PREPARE.PreparationError, match="distinct"):
        PREPARE.stable_eligibility_secret(
            [{"name": "session-secret", "value": ELIGIBILITY["value"]}], [], supplied=ELIGIBILITY["value"],
        )
    _, job, _ = state
    listed = [{"name": "admin-database-url", "value": "test-admin-db"},
              {"name": "app-database-password", "value": "test-app-db"}]
    changed = PREPARE.job_secret_configuration(job, listed, eligibility=ELIGIBILITY)
    assert changed["secrets"] == [*listed, ELIGIBILITY]
    assert changed["triggerType"] == "Manual"


def _drained_inventory(state):
    _, job, _ = deepcopy(state)
    job["properties"]["template"]["containers"][0]["image"] = NEW_IMAGE
    return {"revisions": [
        {"name": TARGET.app + "--old", "properties": {"active": False, "replicas": 0,
            "template": {"containers": [{"image": OLD_IMAGE}]}}},
        {"name": TARGET.app + "--stage", "properties": {"active": True, "replicas": 1,
            "template": {"containers": [{"image": NEW_IMAGE}]}}},
    ], "replicas": {TARGET.app + "--old": [], TARGET.app + "--stage": [{"name": "new-replica"}]},
        "jobs": [job], "executions": {TARGET.job: [{"properties": {"status": "Succeeded"}}]}}


@pytest.mark.parametrize("problem", ["active-old", "leftover-replica", "missing-replica-page",
                                    "old-job-template", "automatic-job", "active-execution",
                                    "unknown-execution", "missing-job", "mismatched-replica-count",
                                    "web-command", "job-command", "job-init", "current-image-mismatch"])
def test_drain_gate_rejects_every_incompatible_or_unproven_writer(state, problem):
    inventory = _drained_inventory(state)
    if problem == "active-old":
        inventory["revisions"][0]["properties"]["active"] = True
    elif problem == "leftover-replica":
        inventory["replicas"][TARGET.app + "--old"] = [{"name": "old-pod"}]
        inventory["revisions"][0]["properties"]["replicas"] = 1
    elif problem == "missing-replica-page":
        del inventory["replicas"][TARGET.app + "--old"]
    elif problem == "old-job-template":
        inventory["jobs"][0]["properties"]["template"]["containers"][0]["image"] = OLD_IMAGE
    elif problem == "automatic-job":
        inventory["jobs"][0]["properties"]["configuration"]["triggerType"] = "Schedule"
    elif problem in {"active-execution", "unknown-execution"}:
        inventory["executions"][TARGET.job][0]["properties"]["status"] = (
            "Running" if problem == "active-execution" else "Unknown"
        )
    elif problem == "missing-job":
        inventory["executions"] = {}
    elif problem == "mismatched-replica-count":
        inventory["revisions"][1]["properties"]["replicas"] = 2
    elif problem == "web-command":
        inventory["revisions"][1]["properties"]["template"]["containers"][0]["command"] = ["/bin/sh"]
    elif problem == "job-command":
        inventory["jobs"][0]["properties"]["template"]["containers"][0]["args"] = ["-c", "old SQL writer"]
    elif problem == "job-init":
        inventory["jobs"][0]["properties"]["template"]["initContainers"] = [{"image": OLD_IMAGE}]
    else:
        inventory["revisions"][1]["properties"]["template"]["containers"][0]["image"] = OLD_IMAGE
    with pytest.raises(PREPARE.PreparationError):
        PREPARE.require_writer_drain(inventory, target=TARGET,
            expected_revision=TARGET.app + "--stage", expected_image=NEW_IMAGE, compatible_images={NEW_IMAGE})


def test_drain_gate_includes_other_jobs_and_accepts_only_complete_compatible_state(state):
    inventory = _drained_inventory(state)
    receipt = PREPARE.require_writer_drain(inventory, target=TARGET,
        expected_revision=TARGET.app + "--stage", expected_image=NEW_IMAGE, compatible_images={NEW_IMAGE})
    assert receipt["passed"] is True
    assert (receipt["revisions"], receipt["replicas"], receipt["jobs"]) == (2, 1, 1)
    another = deepcopy(inventory["jobs"][0])
    another["name"] = "another-database-writer"
    inventory["jobs"].append(another)
    inventory["executions"][another["name"]] = [{"properties": {"status": "Processing"}}]
    with pytest.raises(PREPARE.PreparationError, match="execution"):
        PREPARE.require_writer_drain(inventory, target=TARGET,
            expected_revision=TARGET.app + "--stage", expected_image=NEW_IMAGE, compatible_images={NEW_IMAGE})


def test_inventory_follows_all_pages_and_rejects_outside_target_continuations(monkeypatch):
    url = TARGET.arm_root + "/providers/Microsoft.App/jobs?api-version=2025-01-01"
    seen = []

    def fake_azure(arguments, _environment):
        seen.append(arguments[-1])
        return {"value": [{"name": "one"}], "nextLink": url + "&page=2"} if len(seen) == 1 else {
            "value": [{"name": "two"}], "nextLink": None,
        }

    monkeypatch.setattr(PREPARE, "azure", fake_azure)
    assert [row["name"] for row in PREPARE.azure_collection(url, {}, target=TARGET)] == ["one", "two"]
    assert len(seen) == 2
    monkeypatch.setattr(PREPARE, "azure", lambda *_args: {"value": [], "nextLink": "https://outside.invalid/"})
    with pytest.raises(PREPARE.PreparationError, match="pagination"):
        PREPARE.azure_collection(url, {}, target=TARGET)


@pytest.mark.parametrize("include_activation", [False, True])
def test_preparation_emits_activation_files_only_after_drain_and_keeps_runner_hashes(
    state, tmp_path, monkeypatch, include_activation,
):
    application, job, postgres = state
    if include_activation:
        application["properties"]["template"]["containers"][0]["image"] = NEW_IMAGE
        job["properties"]["template"]["containers"][0]["image"] = NEW_IMAGE
    target_file = tmp_path / "target.json"
    target_file.write_text(json.dumps(asdict(TARGET)))
    source = tmp_path / "source.env"
    source.write_text("\n".join(f"{name}={value}" for name, value in SOURCE.items()))
    source.chmod(0o600)
    adc = tmp_path / "adc.json"
    adc.write_text(json.dumps({"type": "authorized_user", "refresh_token": "test-token",
                               "client_id": "test-client", "client_secret": "test-secret",
                               "quota_project_id": "access-example"}))
    adc.chmod(0o600)
    key = tmp_path / "eligibility-key"
    key.write_text(ELIGIBILITY["value"])
    key.chmod(0o600)
    directory = tmp_path / "protected"

    def fake_azure(arguments, _environment):
        if arguments[:2] == ["account", "show"]:
            return {"id": TARGET.subscription, "tenantId": TARGET.tenant,
                    "user": {"name": TARGET.operator}, "state": "Enabled"}
        if arguments[0] == "postgres":
            return postgres
        url = arguments[-1]
        if "/listSecrets?" in url:
            if "/containerApps/" in url:
                return {"value": [
                    {"name": "database-url", "value": "test-database-url"},
                    {"name": "foundry-api-key", "value": SOURCE["AZURE_OPENAI_API_KEY"]},
                    {"name": "vault-secret", "value": "test-other-secret"},
                ]}
            return {"value": [{"name": "admin-database-url", "value": "test-admin-url"},
                               {"name": "app-database-password", "value": "test-app-password"}]}
        return application if "/containerApps/" in url else job

    monkeypatch.setattr(PREPARE, "azure", fake_azure)
    inventory_calls = []

    def inventory(*_args):
        inventory_calls.append(True)
        result = _drained_inventory(state)
        result["revisions"][0]["name"] = TARGET.app + "--historic"
        result["revisions"][1]["name"] = TARGET.app + "--old"
        result["replicas"] = {TARGET.app + "--historic": [], TARGET.app + "--old": [{"name": "pod"}]}
        return result

    monkeypatch.setattr(PREPARE, "writer_drain_inventory", inventory)
    arguments = ["--target-file", str(target_file), "--expected-revision", TARGET.app + "--old",
                 "--recovery-image", NEW_IMAGE, "--candidate-image", NEW_IMAGE,
                 "--revision-prefix", "review", "--adc-file", str(adc), "--source-env", str(source),
                 "--eligibility-key-file", str(key), "--output-directory", str(directory)]
    if include_activation:
        arguments.append("--include-activation")
    assert PREPARE.main(arguments) == 0
    assert bool(inventory_calls) is include_activation
    manifest = json.loads((directory / "manifest.json").read_text())
    assert manifest["writer_drain"]["passed"] is include_activation
    assert (directory / "candidate-ready.patch.json").exists() is include_activation
    assert (directory / "candidate-reconcile-apply.execution.json").exists() is include_activation
    for name, checksum in manifest["runner_sha256"].items():
        assert hashlib.sha256((directory / name).read_bytes()).hexdigest() == checksum
    assert ELIGIBILITY["value"] not in (directory / "manifest.json").read_text()
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in directory.iterdir())
