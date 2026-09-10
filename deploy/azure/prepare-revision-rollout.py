#!/usr/bin/env python3
"""Read the authorized Azure app and render protected rollout requests without applying them."""
from __future__ import annotations

import argparse
import base64
from copy import deepcopy
from datetime import datetime, timezone
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
SUBSCRIPTION = "00e62f6e-2174-40b2-b428-8ebfd7c2ac54"
TENANT = "040f05eb-33ab-462f-af54-fb4bedb055ae"
OPERATOR = "hliu2@cloudbank.org"
GROUP = "abda-nl-staging"
APP = "abda-nl-stg-web"
JOB = "abda-nl-stg-migrate"
POSTGRES = "abda-nl-stg-postgres-bgjhpbgw"
ARM_ROOT = f"https://management.azure.com/subscriptions/{SUBSCRIPTION}/resourceGroups/{GROUP}"
API_VERSION = "2025-01-01"
AUTO_ACTIVATE = "ABDA_NAMED_CREDIT_AUTO_ACTIVATE"
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


def secret_configuration(application: dict, listed: list[dict], source: dict[str, str], adc: str) -> dict:
    """Preserve every existing secret and app setting; add two scoped credentials."""
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


def reconcile_template(application: dict, job: dict, postgres: dict, *, image: str, apply: bool) -> dict:
    template = inspection_module().read_only_job_template(application, job, postgres)
    container = template["containers"][0]
    # This execution uses only the restricted app login. The existing job's
    # administrative URL is removed by read_only_job_template before this step.
    runner = """import os, runpy, sys
from sqlalchemy.engine import URL
try:
    url = URL.create('postgresql+psycopg', username=os.environ['ABDA_DATABASE_APP_LOGIN'],
        password=os.environ['ABDA_DATABASE_APP_PASSWORD'], host=os.environ['ABDA_POSTGRES_HOST'],
        port=5432, database='abda', query={'sslmode': 'require'})
    os.environ['ABDA_DATABASE_URL'] = url.render_as_string(hide_password=False)
    sys.argv = ['app.cli.reconcile_named_credit'] + APPLY_ARGUMENTS
    runpy.run_module('app.cli.reconcile_named_credit', run_name='__main__')
except Exception:
    print('NAMED_CREDIT_JOB_FAILED_WITHOUT_CREDENTIAL_OUTPUT', file=sys.stderr)
    raise SystemExit(1)
""".replace("APPLY_ARGUMENTS", repr(["--apply"] if apply else []))
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


def write_private(path: Path, value: dict) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def private_text(path: Path) -> str:
    if not path.is_file() or path.stat().st_mode & 0o077 or path.stat().st_uid != os.getuid():
        raise PreparationError("a credential source must be an owner-only file")
    return path.read_text()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-revision", required=True)
    parser.add_argument("--recovery-image", required=True)
    parser.add_argument("--candidate-image", required=True)
    parser.add_argument("--revision-prefix", required=True)
    parser.add_argument("--adc-file", required=True, type=Path)
    parser.add_argument("--source-env", type=Path, default=ROOT / ".env")
    parser.add_argument("--output-directory", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
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
        if (identity.get("id"), identity.get("tenantId"), identity.get("user", {}).get("name", "").lower(), identity.get("state")) != (SUBSCRIPTION, TENANT, OPERATOR, "Enabled"):
            raise PreparationError("the Azure identity is outside the authorized boundary")
        app_url = f"{ARM_ROOT}/providers/Microsoft.App/containerApps/{APP}?api-version={API_VERSION}"
        job_url = f"{ARM_ROOT}/providers/Microsoft.App/jobs/{JOB}?api-version={API_VERSION}"
        application = azure(["rest", "--method", "get", "--url", app_url], environment)
        job = azure(["rest", "--method", "get", "--url", job_url], environment)
        postgres = azure(["postgres", "flexible-server", "show", "--name", POSTGRES, "--resource-group", GROUP], environment)
        properties = application["properties"]
        if application.get("name") != APP or properties.get("latestReadyRevisionName") != args.expected_revision or properties["configuration"].get("activeRevisionsMode") != "Single":
            raise PreparationError("the live revision or single-revision deployment boundary changed")
        listed = azure(["rest", "--method", "post", "--url", app_url.replace("?", "/listSecrets?")], environment)
        secrets = secret_configuration(application, listed["value"], source, adc_text)
        artifacts = {"secrets.patch.json": {"properties": {"configuration": secrets}},
                     "before.application.json": application,
                     "before.migration-job.json": job}
        for label, image in (("recovery", recovery), ("candidate", candidate)):
            for stage, activate in (("stage", False), ("ready", True)):
                template = app_template(application, image=image, suffix=f"{args.revision_prefix}-{label}-{stage}",
                                        source=source, project=project, auto_activate=activate)
                artifacts[f"{label}-{stage}.patch.json"] = {"properties": {"template": template}}
            artifacts[f"{label}-migration.patch.json"] = {"properties": {"template": migration_template(job, image)}}
            inspection = inspection_module().read_only_job_template(application, job, postgres)
            inspection["containers"][0]["image"] = image
            artifacts[f"{label}-inspect.execution.json"] = inspection
            for apply in (False, True):
                artifacts[f"{label}-reconcile-{'apply' if apply else 'preview'}.execution.json"] = reconcile_template(
                    application, job, postgres, image=image, apply=apply,
                )
        artifacts["inspect-before.execution.json"] = inspection_module().read_only_job_template(application, job, postgres)
        artifacts["manifest.json"] = {"prepared_utc": datetime.now(timezone.utc).isoformat(), "expected_revision": args.expected_revision,
            "old_image": properties["template"]["containers"][0]["image"], "recovery_image": recovery,
            "candidate_image": candidate, "cloud_mutations": False, "database_mutations": False,
            "app_patch_url": app_url, "job_patch_url": job_url, "application": APP, "job": JOB,
            "automatic_named_credit_stage": False, "automatic_named_credit_ready": True,
            "new_secret_names": ["foundry-opus5-api-key", "gcp-adc-json"],
            "default_key_secret_verified": "foundry-api-key",
            "default_key_environment": ["AZURE_OPENAI_API_KEY", "AZURE_ANTHROPIC_API_KEY"],
            "adc_mount": deepcopy(MOUNT), "adc_path": ADC_PATH, "credential_values_in_manifest": False,
            "required_release_evidence": ["both immutable images verified", "0006-aware recovery tested",
                "no bound named allocations before mixed-version stage", "all old writers gone before reconcile",
                "candidate feature qualification", "post-reconcile accounting invariants"],
            "files": sorted(artifacts)}
        args.output_directory.mkdir(mode=0o700)
        for name, artifact in artifacts.items():
            write_private(args.output_directory / name, artifact)
        print("REVISION_ROLLOUT_REQUESTS_PREPARED cloud_mutations=false database_mutations=false secrets_printed=false")
        return 0
    except PreparationError as error:
        print(f"Rollout preparation stopped: {error}", file=sys.stderr)
    except Exception:
        print("Rollout preparation failed; raw cloud and credential output was suppressed.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
