#!/usr/bin/env python3
"""Read the authorized Azure app and render protected rollout requests without applying them."""
from __future__ import annotations

import argparse
import base64
from copy import deepcopy
from datetime import datetime, timezone
from dataclasses import asdict
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlsplit

from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from deploy.azure.rollout_target import RolloutTarget, TargetError, load_target

API_VERSION = "2025-01-01"
AUTO_ACTIVATE = "ABDA_NAMED_CREDIT_AUTO_ACTIVATE"
ELIGIBILITY_ENV = "ABDA_CREDIT_ELIGIBILITY_PEPPER"
ELIGIBILITY_SECRET = "credit-eligibility-pepper"
ADC_PATH = "/var/run/abda-gcp/adc.json"
VOLUME = {"name": "gcp-adc", "storageType": "Secret", "secrets": [
    {"secretRef": "gcp-adc-json", "path": "adc.json"},
]}
MOUNT = {"volumeName": "gcp-adc", "mountPath": "/var/run/abda-gcp"}


class PreparationError(RuntimeError):
    """Only fixed, credential-free messages reach the terminal."""


def immutable_image(value: str) -> str:
    if not re.fullmatch(r"ghcr\.io/liu-hy/abda-nl@sha256:[0-9a-f]{64}", value):
        raise PreparationError("every image must be the approved immutable GHCR digest")
    return value


def azure_endpoint(value: str) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.port not in (None, 443)
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or not parsed.hostname.endswith((".openai.azure.com", ".services.ai.azure.com", ".cognitiveservices.azure.com"))):
        raise PreparationError("a source endpoint is outside the validated Azure boundary")
    return value.rstrip("/")


def default_anthropic_endpoint(source: dict[str, str]) -> str:
    endpoint = urlsplit(azure_endpoint(source["AZURE_OPENAI_ENDPOINT"]))
    # The live audit established the default account's OpenAI and Anthropic
    # aliases. Pin both protocols to that same account, including legacy envs.
    resource = endpoint.hostname.split(".", 1)[0]
    return f"https://{resource}.services.ai.azure.com/anthropic"


def unique_named(entries: list[dict], *, key: str = "name") -> dict[str, dict]:
    result = {entry[key]: entry for entry in entries}
    if len(result) != len(entries):
        raise PreparationError("duplicate named configuration entries require inspection")
    return result


def merge_environment(existing: list[dict], changes: dict[str, dict]) -> list[dict]:
    result = deepcopy(unique_named(existing))
    result.update(deepcopy(changes))
    return list(result.values())


def app_template(application: dict, *, image: str, suffix: str, source: dict[str, str],
                 project: str, auto_activate: bool) -> dict:
    """Preserve the full running template while changing explicit release fields."""
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,45}", suffix) or suffix.endswith("-") or "--" in suffix:
        raise PreparationError("the new revision suffix is invalid")
    template = deepcopy(application["properties"]["template"])
    containers = template.get("containers", [])
    if len(containers) != 1 or containers[0].get("name") != "web":
        raise PreparationError("the existing single web container boundary changed")
    web = containers[0]
    web["image"] = immutable_image(image)
    template["revisionSuffix"] = suffix
    values = {
        "AZURE_OPENAI_ENDPOINT": azure_endpoint(source["AZURE_OPENAI_ENDPOINT"]),
        "AZURE_ANTHROPIC_ENDPOINT": default_anthropic_endpoint(source),
        "ANTHROPIC_FOUNDRY_BASE_URL": default_anthropic_endpoint(source),
        "AZURE_OPUS5_ENDPOINT": azure_endpoint(source["AZURE_OPUS5_ENDPOINT"]),
        "ABDA_CLAUDE_PROVIDER": "foundry",
        "GOOGLE_APPLICATION_CREDENTIALS": ADC_PATH,
        "GOOGLE_CLOUD_PROJECT": project,
        "GOOGLE_CLOUD_QUOTA_PROJECT": project,
        "GOOGLE_CLOUD_LOCATION": "global",
        AUTO_ACTIVATE: str(auto_activate).lower(),
    }
    changes = {name: {"name": name, "value": value} for name, value in values.items()}
    for name in ("AZURE_OPENAI_API_KEY", "AZURE_ANTHROPIC_API_KEY"):
        changes[name] = {"name": name, "secretRef": "foundry-api-key"}
    changes["AZURE_OPUS5_API_KEY"] = {"name": "AZURE_OPUS5_API_KEY", "secretRef": "foundry-opus5-api-key"}
    changes[ELIGIBILITY_ENV] = {"name": ELIGIBILITY_ENV, "secretRef": ELIGIBILITY_SECRET}
    web["env"] = merge_environment(web.get("env", []), changes)
    volumes = unique_named(template.get("volumes") or [])
    if "gcp-adc" in volumes and volumes["gcp-adc"] != VOLUME:
        raise PreparationError("the ADC volume name is already used by a different configuration")
    volumes["gcp-adc"] = deepcopy(VOLUME)
    template["volumes"] = list(volumes.values())
    mounts = deepcopy(web.get("volumeMounts") or [])
    for mount in mounts:
        if (mount.get("volumeName") == "gcp-adc" or mount.get("mountPath") == MOUNT["mountPath"]) and mount != MOUNT:
            raise PreparationError("the ADC mount conflicts with an existing mount")
    if MOUNT not in mounts:
        mounts.append(deepcopy(MOUNT))
    web["volumeMounts"] = mounts
    return template


def secret_configuration(
    application: dict, listed: list[dict], source: dict[str, str], adc: str, *, eligibility: dict,
) -> dict:
    """Preserve existing settings while adding validated provider and eligibility secrets."""
    configuration = deepcopy(application["properties"]["configuration"])
    expected = unique_named(configuration.get("secrets", []))
    secrets = unique_named(listed)
    if set(expected) != set(secrets):
        raise PreparationError("the application secrets changed during preparation")
    for item in secrets.values():
        if not item.get("value") and not item.get("keyVaultUrl"):
            raise PreparationError("an existing application secret could not be preserved")
    default_key = source.get("AZURE_OPENAI_API_KEY")
    if not default_key or secrets.get("foundry-api-key", {}).get("value") != default_key:
        raise PreparationError("the existing default key differs from the validated source; recheck resource lineage")
    if not source.get("AZURE_OPUS5_API_KEY"):
        raise PreparationError("the validated scoped Opus credential is missing")
    secrets = deepcopy(secrets)
    secrets["foundry-opus5-api-key"] = {"name": "foundry-opus5-api-key", "value": source["AZURE_OPUS5_API_KEY"]}
    secrets["gcp-adc-json"] = {"name": "gcp-adc-json", "value": adc}
    secrets[ELIGIBILITY_SECRET] = deepcopy(eligibility)
    configuration["secrets"] = list(secrets.values())
    return configuration


def stable_eligibility_secret(
    app_secrets: list[dict], job_secrets: list[dict], *, supplied: str | None = None,
) -> dict:
    """Reuse the existing key; initial provisioning requires an owner-only source."""
    app = unique_named(app_secrets)
    job = unique_named(job_secrets)
    existing = [secrets[ELIGIBILITY_SECRET] for secrets in (app, job) if ELIGIBILITY_SECRET in secrets]
    if existing and any(item != existing[0] for item in existing[1:]):
        raise PreparationError("application and job eligibility keys differ; do not rotate retained markers")
    if existing:
        selected = deepcopy(existing[0])
        if supplied is not None and supplied != selected.get("value"):
            raise PreparationError("the supplied eligibility key would rotate existing eligibility history")
    elif supplied is not None:
        selected = {"name": ELIGIBILITY_SECRET, "value": supplied}
    else:
        raise PreparationError("initial eligibility setup requires --eligibility-key-file; reuse this key thereafter")
    if selected.get("keyVaultUrl") and supplied is None:
        return selected
    value = selected.get("value", "")
    if not isinstance(value, str) or len(value) < 32 or value != value.strip():
        raise PreparationError("the stable eligibility key must contain at least 32 characters")
    other_values = {
        item.get("value") for items in (app.values(), job.values()) for item in items
        if item.get("name") != ELIGIBILITY_SECRET and item.get("value")
    }
    if value in other_values:
        raise PreparationError("eligibility requires a distinct stable key")
    return selected


def job_secret_configuration(job: dict, listed: list[dict], *, eligibility: dict) -> dict:
    configuration = deepcopy(job["properties"]["configuration"])
    expected = unique_named(configuration.get("secrets", []))
    secrets = unique_named(listed)
    if set(expected) != set(secrets) or any(
        not item.get("value") and not item.get("keyVaultUrl") for item in secrets.values()
    ):
        raise PreparationError("existing job secrets could not be preserved")
    secrets[ELIGIBILITY_SECRET] = deepcopy(eligibility)
    configuration["secrets"] = list(secrets.values())
    return configuration


def migration_template(job: dict, image: str) -> dict:
    template = deepcopy(job["properties"]["template"])
    containers = template.get("containers", [])
    if len(containers) != 1 or containers[0].get("name") != "migrate":
        raise PreparationError("the existing migration container boundary changed")
    container = containers[0]
    if container.get("command") != ["/opt/venv/bin/python"] or container.get("args") != ["-m", "app.cli.migrate"]:
        raise PreparationError("the migration job entrypoint changed")
    container["image"] = immutable_image(image)
    return template


def inspection_module():
    path = Path(__file__).with_name("inspect-named-credit.py")
    spec = importlib.util.spec_from_file_location("abda_named_credit_inspection", path)
    if spec is None or spec.loader is None:
        raise PreparationError("the read-only inspection helper is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def reconciliation_runner(*, apply: bool) -> str:
    return """import os, runpy, sys
from sqlalchemy.engine import URL
try:
    url = URL.create('postgresql+psycopg', username=os.environ['ABDA_DATABASE_APP_LOGIN'],
        password=os.environ['ABDA_DATABASE_APP_PASSWORD'], host=os.environ['ABDA_POSTGRES_HOST'],
        port=5432, database=os.environ['ABDA_DATABASE_NAME'], query={'sslmode': 'require'})
    os.environ['ABDA_DATABASE_URL'] = url.render_as_string(hide_password=False)
    sys.argv = ['app.cli.reconcile_named_credit'] + APPLY_ARGUMENTS
    runpy.run_module('app.cli.reconcile_named_credit', run_name='__main__')
except Exception:
    print('NAMED_CREDIT_JOB_FAILED_WITHOUT_CREDENTIAL_OUTPUT', file=sys.stderr)
    raise SystemExit(1)
""".replace("APPLY_ARGUMENTS", repr(["--apply"] if apply else []))


def reconcile_template(
    application: dict, job: dict, postgres: dict, *, image: str, apply: bool,
    target: RolloutTarget,
) -> dict:
    template = inspection_module().read_only_job_template(application, job, postgres, target=target)
    container = template["containers"][0]
    # Only the restricted login and the stable eligibility key enter this job.
    container["env"].append({"name": ELIGIBILITY_ENV, "secretRef": ELIGIBILITY_SECRET})
    runner = reconciliation_runner(apply=apply)
    encoded = base64.b64encode(runner.encode()).decode()
    container.update(image=immutable_image(image), args=["-c", f"exec(__import__('base64').b64decode('{encoded}'))"])
    return template


def azure(arguments: list[str], environment: dict[str, str]) -> dict:
    executable = Path.home() / ".local/share/abda-azure/cli/bin/az"
    result = subprocess.run(  # noqa: S603, fixed CLI argv with no shell; only reads below are allowed.
        [str(executable), *arguments, "--only-show-errors", "--output", "json"],
        env=environment, capture_output=True, text=True, timeout=60, check=False,
    )
    if result.returncode:
        raise PreparationError("an authorized Azure configuration read failed")
    return json.loads(result.stdout)


def azure_collection(url: str, environment: dict[str, str], *, target: RolloutTarget) -> list[dict]:
    """Read every ARM page, rejecting repeated or out-of-target continuations."""
    values = []
    seen = set()
    while url:
        if (url in seen or len(seen) >= 100
                or not url.lower().startswith(target.arm_root.lower() + "/providers/microsoft.app/")):
            raise PreparationError("the Azure inventory pagination boundary changed")
        seen.add(url)
        page = azure(["rest", "--method", "get", "--url", url], environment)
        if not isinstance(page.get("value"), list) or not all(isinstance(item, dict) for item in page["value"]):
            raise PreparationError("Azure returned an incomplete writer inventory")
        values.extend(page["value"])
        url = page.get("nextLink") or ""
        if not isinstance(url, str):
            raise PreparationError("Azure returned an invalid inventory continuation")
    return values


def writer_drain_inventory(target: RolloutTarget, environment: dict[str, str]) -> dict:
    app_url = f"{target.arm_root}/providers/Microsoft.App/containerApps/{target.app}"
    revisions = azure_collection(f"{app_url}/revisions?api-version={API_VERSION}", environment, target=target)
    replicas = {}
    for revision in revisions:
        name = revision.get("name", "")
        if not re.fullmatch(re.escape(target.app) + r"--[a-z0-9-]+", name):
            raise PreparationError("the revision inventory contains an unexpected target")
        replicas[name] = azure_collection(
            f"{app_url}/revisions/{name}/replicas?api-version={API_VERSION}", environment, target=target,
        )
    jobs = azure_collection(
        f"{target.arm_root}/providers/Microsoft.App/jobs?api-version={API_VERSION}", environment, target=target,
    )
    executions = {}
    for job in jobs:
        name = job.get("name", "")
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,89}", name):
            raise PreparationError("the job inventory contains an invalid target")
        target.require_resource(job, "Microsoft.App/jobs", name)
        executions[name] = azure_collection(
            f"{target.arm_root}/providers/Microsoft.App/jobs/{name}/executions?api-version={API_VERSION}",
            environment, target=target,
        )
    return {"revisions": revisions, "replicas": replicas, "jobs": jobs, "executions": executions}


def require_writer_drain(
    inventory: dict, *, target: RolloutTarget, expected_revision: str, expected_image: str,
    compatible_images: set[str],
) -> dict:
    """Fail closed before preparing any ready revision or transfer execution."""
    revisions = inventory.get("revisions")
    replicas = inventory.get("replicas", {})
    jobs = inventory.get("jobs")
    executions = inventory.get("executions", {})
    if not isinstance(revisions, list) or not revisions or not isinstance(jobs, list):
        raise PreparationError("a complete revision and job inventory is required for activation")
    names = [item.get("name") for item in revisions]
    job_names = [item.get("name") for item in jobs]
    if (expected_revision not in names or len(set(names)) != len(names) or set(replicas) != set(names)
            or target.job not in job_names or len(set(job_names)) != len(job_names)
            or set(executions) != set(job_names)):
        raise PreparationError("writer inventory is missing or duplicating revisions, replicas, or jobs")
    active = 0
    for revision in revisions:
        properties = revision.get("properties", {})
        observed = replicas[revision["name"]]
        if not isinstance(properties.get("active"), bool) or not isinstance(observed, list):
            raise PreparationError("a revision's writer state is unknown")
        count = properties.get("replicas")
        if type(count) is not int or count != len(observed):
            raise PreparationError("revision and replica inventories disagree; refresh before activation")
        template = properties.get("template", {})
        containers = [*template.get("containers", []), *template.get("initContainers", [])]
        if revision["name"] == expected_revision and (
            not properties["active"] or len(containers) != 1 or containers[0].get("image") != expected_image
        ):
            raise PreparationError("the current application and revision inventories disagree")
        compatible = bool(containers) and all(item.get("image") in compatible_images for item in containers)
        if compatible and (properties["active"] or observed) and (
            template.get("initContainers") or len(containers) != 1
            or containers[0].get("command") or containers[0].get("args")
        ):
            raise PreparationError("an active web command override requires separate writer-compatibility review")
        if (properties["active"] or observed) and not compatible:
            raise PreparationError("an incompatible web revision or replica can still write")
        active += int(properties["active"])
    if active != 1:
        raise PreparationError("activation requires one compatible active revision")
    for job in jobs:
        properties = job.get("properties", {})
        template = properties.get("template", {})
        containers = [*template.get("containers", []), *template.get("initContainers", [])]
        if (properties.get("provisioningState") != "Succeeded"
                or properties.get("configuration", {}).get("triggerType") != "Manual" or not containers
                or any(item.get("image") not in compatible_images for item in containers)):
            raise PreparationError("an automatic or incompatible job template can still start a writer")
        if (template.get("initContainers") or len(containers) != 1
                or containers[0].get("command") != ["/opt/venv/bin/python"]
                or containers[0].get("args") != ["-m", "app.cli.migrate"]):
            raise PreparationError("a job command override requires separate writer-compatibility review")
        history = executions[job["name"]]
        if not isinstance(history, list) or any(
            item.get("properties", {}).get("status") not in {"Succeeded", "Failed", "Stopped"}
            for item in history
        ):
            raise PreparationError("a job execution is active or has an unknown terminal state")
    return {"passed": True, "checked_utc": datetime.now(timezone.utc).isoformat(),
            "revisions": len(revisions), "replicas": sum(len(value) for value in replicas.values()),
            "jobs": len(jobs), "job_executions": sum(len(value) for value in executions.values()),
            "compatible_images": sorted(compatible_images),
            "scope": "configured_app_all_revisions_and_all_jobs_in_target_resource_group"}


def write_private(path: Path, value: dict | str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        if isinstance(value, str):
            stream.write(value)
        else:
            json.dump(value, stream, indent=2)
            stream.write("\n")


def private_text(path: Path) -> str:
    if not path.is_file() or path.stat().st_mode & 0o077 or path.stat().st_uid != os.getuid():
        raise PreparationError("a credential source must be an owner-only file")
    return path.read_text()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-file", required=True, type=Path)
    parser.add_argument("--expected-revision", required=True)
    parser.add_argument("--recovery-image", required=True)
    parser.add_argument("--candidate-image", required=True)
    parser.add_argument("--revision-prefix", required=True)
    parser.add_argument("--adc-file", required=True, type=Path)
    parser.add_argument("--source-env", type=Path, default=ROOT / ".env")
    parser.add_argument("--eligibility-key-file", type=Path,
                        help="owner-only stable initial key; never rotate per rollout")
    parser.add_argument("--include-activation", action="store_true",
                        help="prepare ready/apply files only after a fresh compatible-writer drain check")
    parser.add_argument("--output-directory", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        target = load_target(args.target_file)
        recovery = immutable_image(args.recovery_image)
        candidate = immutable_image(args.candidate_image)
        if args.output_directory.resolve().is_relative_to(ROOT):
            raise PreparationError("protected rollout requests must be stored outside the checkout")
        private_text(args.source_env)
        source = dict(dotenv_values(args.source_env))
        adc_text = private_text(args.adc_file)
        adc = json.loads(adc_text)
        if adc.get("type") != "authorized_user" or not all(adc.get(name) for name in ("refresh_token", "client_id", "client_secret")):
            raise PreparationError("the source must be the previously verified standard ADC credential")
        project = source.get("GOOGLE_CLOUD_PROJECT") or source.get("GOOGLE_PROJECT_ID") or adc.get("quota_project_id", "")
        if not project.startswith("access-") or adc.get("quota_project_id") != project:
            raise PreparationError("the ADC and configured CloudBank quota project do not match")
        environment = dict(os.environ, AZURE_CONFIG_DIR=str(Path.home() / ".local/share/abda-azure/config"),
                           AZURE_CORE_COLLECT_TELEMETRY="false", AZURE_LOGGING_ENABLE_LOG_FILE="false",
                           AZURE_EXTENSION_USE_DYNAMIC_INSTALL="no")
        identity = azure(["account", "show"], environment)
        target.require_identity(identity)
        app_url = f"{target.arm_root}/providers/Microsoft.App/containerApps/{target.app}?api-version={API_VERSION}"
        job_url = f"{target.arm_root}/providers/Microsoft.App/jobs/{target.job}?api-version={API_VERSION}"
        application = azure(["rest", "--method", "get", "--url", app_url], environment)
        job = azure(["rest", "--method", "get", "--url", job_url], environment)
        postgres = azure(["postgres", "flexible-server", "show", "--name", target.postgres,
                          "--resource-group", target.resource_group, "--subscription", target.subscription], environment)
        target.require_resource(application, "Microsoft.App/containerApps", target.app)
        target.require_resource(job, "Microsoft.App/jobs", target.job)
        target.require_resource(postgres, "Microsoft.DBforPostgreSQL/flexibleServers", target.postgres)
        properties = application["properties"]
        if (properties.get("latestReadyRevisionName") != args.expected_revision
                or properties.get("latestRevisionName") != args.expected_revision
                or properties.get("provisioningState") != "Succeeded"
                or properties["configuration"].get("activeRevisionsMode") != "Single"):
            raise PreparationError("the live revision or single-revision deployment boundary changed")
        drain = {"passed": False, "reason": "activation_not_requested"}
        if args.include_activation:
            inventory = writer_drain_inventory(target, environment)
            inspected_job = next((item for item in inventory["jobs"] if item.get("name") == target.job), None)
            if inspected_job is None or inspected_job.get("properties", {}).get("template") != job["properties"]["template"]:
                raise PreparationError("the configured migration job changed during the drain check")
            drain = require_writer_drain(
                inventory, target=target, expected_revision=args.expected_revision,
                expected_image=properties["template"]["containers"][0]["image"],
                compatible_images={candidate, recovery},
            )
        listed = azure(["rest", "--method", "post", "--url", app_url.replace("?", "/listSecrets?")], environment)
        job_listed = azure(["rest", "--method", "post", "--url", job_url.replace("?", "/listSecrets?")], environment)
        key = private_text(args.eligibility_key_file).strip() if args.eligibility_key_file else None
        eligibility = stable_eligibility_secret(listed["value"], job_listed["value"], supplied=key)
        secrets = secret_configuration(application, listed["value"], source, adc_text, eligibility=eligibility)
        job_secrets = job_secret_configuration(job, job_listed["value"], eligibility=eligibility)
        artifacts = {"secrets.patch.json": {"properties": {"configuration": secrets}},
                     "job-secrets.patch.json": {"properties": {"configuration": job_secrets}},
                     "before.application.json": application,
                     "before.migration-job.json": job,
                     "inspection.runner.py": inspection_module().RUNNER,
                     "reconcile-preview.runner.py": reconciliation_runner(apply=False)}
        if args.include_activation:
            artifacts["reconcile-apply.runner.py"] = reconciliation_runner(apply=True)
        phases = [("stage", False)] + ([("ready", True)] if args.include_activation else [])
        for label, image in (("recovery", recovery), ("candidate", candidate)):
            for stage, activate in phases:
                template = app_template(application, image=image, suffix=f"{args.revision_prefix}-{label}-{stage}",
                                        source=source, project=project, auto_activate=activate)
                artifacts[f"{label}-{stage}.patch.json"] = {"properties": {"template": template}}
            artifacts[f"{label}-migration.patch.json"] = {"properties": {"template": migration_template(job, image)}}
            inspection = inspection_module().read_only_job_template(application, job, postgres, target=target)
            inspection["containers"][0]["image"] = image
            artifacts[f"{label}-inspect.execution.json"] = inspection
            for apply in ((False, True) if args.include_activation else (False,)):
                artifacts[f"{label}-reconcile-{'apply' if apply else 'preview'}.execution.json"] = reconcile_template(
                    application, job, postgres, image=image, apply=apply, target=target,
                )
        artifacts["inspect-before.execution.json"] = inspection_module().read_only_job_template(application, job, postgres, target=target)
        runner_hashes = {name: hashlib.sha256(value.encode()).hexdigest()
                         for name, value in artifacts.items() if name.endswith(".runner.py")}
        artifacts["manifest.json"] = {"prepared_utc": datetime.now(timezone.utc).isoformat(), "expected_revision": args.expected_revision,
            "old_image": properties["template"]["containers"][0]["image"], "recovery_image": recovery,
            "candidate_image": candidate, "cloud_mutations": False, "database_mutations": False,
            "app_patch_url": app_url, "job_patch_url": job_url, "target": asdict(target),
            "application": target.app, "job": target.job,
            "automatic_named_credit_stage": False, "automatic_named_credit_ready": args.include_activation,
            "writer_drain": drain,
            "new_secret_names": sorted(set(unique_named(secrets["secrets"])) - set(unique_named(listed["value"]))),
            "new_job_secret_names": sorted(set(unique_named(job_secrets["secrets"])) - set(unique_named(job_listed["value"]))),
            "eligibility_key_reused": any(item.get("name") == ELIGIBILITY_SECRET
                                          for item in [*listed["value"], *job_listed["value"]]),
            "runner_sha256": runner_hashes,
            "default_key_secret_verified": "foundry-api-key",
            "default_key_environment": ["AZURE_OPENAI_API_KEY", "AZURE_ANTHROPIC_API_KEY"],
            "adc_mount": deepcopy(MOUNT), "adc_path": ADC_PATH, "credential_values_in_manifest": False,
            "required_release_evidence": ["both immutable images verified", "0007-aware recovery tested",
                "existing grants and retired eligibility preserved through stage", "all old writers gone before reconcile",
                "candidate feature qualification", "post-reconcile accounting invariants",
                "re-run the drain check immediately before activating prepared files"],
            "files": sorted(artifacts)}
        args.output_directory.mkdir(mode=0o700)
        for name, artifact in artifacts.items():
            write_private(args.output_directory / name, artifact)
        print("REVISION_ROLLOUT_REQUESTS_PREPARED cloud_mutations=false database_mutations=false secrets_printed=false")
        return 0
    except (PreparationError, TargetError) as error:
        print(f"Rollout preparation stopped: {error}", file=sys.stderr)
    except Exception:
        print("Rollout preparation failed; raw cloud and credential output was suppressed.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
