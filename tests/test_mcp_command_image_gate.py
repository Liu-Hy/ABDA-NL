"""Contracts for the image-only Azure MCP command gate."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import shlex
import subprocess


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "deploy" / "azure" / "gate10-mcp-command-image.sh"
APP = "abda-nl-stg-web"
GENERATED_HOST = "abda-nl-stg-web.blueforest-da494f7c.eastus2.azurecontainerapps.io"
CUSTOM_HOST = "demo.abda-nl.org"
OLD_REVISION = "abda-nl-stg-web--mcp-82f97fb"
TARGET_REVISION = "abda-nl-stg-web--mcp-c55aa0d"
OLD_IMAGE = (
    "ghcr.io/liu-hy/abda-nl@sha256:"
    "a1488eaf90d21f68c3e2a1e4398ee4ecadea24677fa8a08e882894d7b41cece7"
)
TARGET_IMAGE = (
    "ghcr.io/liu-hy/abda-nl@sha256:"
    "2df0bf98401adb6f72d1b930d83ab68bd2466de756b0bead3864f3d41d30b9d0"
)


def _run_function(function: str, *arguments: Path | str) -> subprocess.CompletedProcess[str]:
    quoted = " ".join(shlex.quote(str(argument)) for argument in arguments)
    return subprocess.run(
        [
            "bash",
            "-c",
            (
                f"source {shlex.quote(str(GATE))}; "
                f"abda_mcp_image_set_constants; {function} {quoted}"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def _environment() -> list[dict[str, str]]:
    values = {
        "ABDA_ENVIRONMENT": "staging",
        "ABDA_AUTH_MODE": "oidc",
        "ABDA_PUBLIC_BASE_URL": f"https://{CUSTOM_HOST}",
        "ABDA_TRIAL_ENABLED": "True",
        "ABDA_TRIAL_MAX_USERS": "10",
        "ABDA_TRIAL_GRANT_MICROUSD": "5000000",
        "ABDA_TRIAL_BUDGET_MICROUSD": "50000000",
        "ABDA_LLM_ALLOW_BYOK": "1",
        "ABDA_LLM_REQUIRE_AUTH": "1",
        "ABDA_OPENROUTER_FAILOVER_ENABLED": "False",
        "ABDA_OPENROUTER_BUDGET_MICROUSD": "500000000",
    }
    return [{"name": name, "value": value} for name, value in values.items()]


def _app(phase: str) -> dict:
    if phase == "old":
        image = OLD_IMAGE
        latest = ready = OLD_REVISION
        suffix = "mcp-82f97fb"
    elif phase == "target_pending":
        image = TARGET_IMAGE
        latest, ready = TARGET_REVISION, OLD_REVISION
        suffix = "mcp-c55aa0d"
    elif phase == "target":
        image = TARGET_IMAGE
        latest = ready = TARGET_REVISION
        suffix = "mcp-c55aa0d"
    else:
        raise ValueError(phase)
    return {
        "name": APP,
        "identity": {"type": "None"},
        "properties": {
            "provisioningState": "Succeeded",
            "runningStatus": "Running",
            "latestRevisionName": latest,
            "latestReadyRevisionName": ready,
            "environmentId": "/environments/staging",
            "managedEnvironmentId": "/environments/staging",
            "workloadProfileName": "Consumption",
            "configuration": {
                "activeRevisionsMode": "Single",
                "secrets": [{"name": "protected-secret"}],
                "ingress": {
                    "fqdn": GENERATED_HOST,
                    "external": True,
                    "allowInsecure": False,
                    "targetPort": 8000,
                    "traffic": [{"latestRevision": True, "weight": 100}],
                    "customDomains": [{"name": CUSTOM_HOST}],
                },
            },
            "template": {
                "revisionSuffix": suffix,
                "scale": {"minReplicas": 1, "maxReplicas": 3},
                "containers": [
                    {
                        "name": "web",
                        "image": image,
                        "env": _environment(),
                        "resources": {"cpu": 0.5, "memory": "1Gi"},
                        "probes": [{"type": "Readiness"}],
                    }
                ],
            },
        },
    }


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_mcp_command_image_gate_is_executable_and_has_valid_bash_syntax():
    assert GATE.stat().st_mode & 0o111
    subprocess.run(["bash", "-n", str(GATE)], check=True)


def test_mcp_command_image_gate_has_exactly_one_narrow_mutation():
    source = GATE.read_text(encoding="utf-8")
    for expected in (
        "c55aa0d67562d2a08ea4fa158aab262e432ddb88",
        OLD_IMAGE.split("sha256:", 1)[1],
        TARGET_IMAGE.split("sha256:", 1)[1],
        OLD_REVISION,
        TARGET_REVISION,
        "DEPLOY_ABDA_MCP_COMMAND_FINAL_FIX",
        "MCP_COMMAND_FINAL_FIX_DEPLOYED_CLIENT_TEST_REQUIRED",
    ):
        assert expected in source
    assert source.count("az containerapp update") == 2
    assert source.count('--image "$ABDA_IMAGE_REPOSITORY@sha256:') == 1
    assert source.count('--revision-suffix "$ABDA_MCP_IMAGE_TARGET_SUFFIX"') == 1
    assert '$ABDA_CUSTOM_ORIGIN/workspace.js?source=' in source
    assert '$ABDA_CUSTOM_ORIGIN/app.js?source=' in source
    assert '$ABDA_CUSTOM_ORIGIN/static/' not in source
    for forbidden in (
        "az deployment group create",
        "az containerapp job start",
        "az containerapp job create",
        "az containerapp secret set",
        "az containerapp secret list",
        "az containerapp hostname",
        "--set-env-vars",
        "read -r -s",
    ):
        assert forbidden not in source
    assert "set +x" in source
    assert "unset HISTFILE" in source
    assert "set -x" not in source


def test_mcp_command_image_gate_accepts_only_reviewed_app_phases(tmp_path: Path):
    for phase in ("old", "target_pending", "target"):
        path = tmp_path / f"{phase}.json"
        _write_json(path, _app(phase))
        result = _run_function("abda_mcp_image_validate_app_phase", path)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == phase

    changed = _app("old")
    environment = changed["properties"]["template"]["containers"][0]["env"]
    next(
        item
        for item in environment
        if item["name"] == "ABDA_OPENROUTER_FAILOVER_ENABLED"
    )["value"] = "true"
    path = tmp_path / "changed.json"
    _write_json(path, changed)
    result = _run_function("abda_mcp_image_validate_app_phase", path)
    assert result.returncode != 0
    assert "ABDA_OPENROUTER_FAILOVER_ENABLED" in result.stderr


def test_mcp_command_image_gate_preserves_complete_application_contract(tmp_path: Path):
    before = _app("old")
    after = _app("target")
    before_path = tmp_path / "before.json"
    after_path = tmp_path / "after.json"
    _write_json(before_path, before)
    _write_json(after_path, after)
    result = _run_function(
        "abda_mcp_image_compare_application_contract", before_path, after_path
    )
    assert result.returncode == 0, result.stderr

    changed = copy.deepcopy(after)
    environment = changed["properties"]["template"]["containers"][0]["env"]
    next(item for item in environment if item["name"] == "ABDA_TRIAL_MAX_USERS")[
        "value"
    ] = "100"
    _write_json(after_path, changed)
    result = _run_function(
        "abda_mcp_image_compare_application_contract", before_path, after_path
    )
    assert result.returncode != 0
    assert "settings outside the image and revision changed" in result.stderr
    assert "ABDA_TRIAL_MAX_USERS" not in result.stderr


def test_mcp_command_image_gate_validates_registry_digest_and_labels(tmp_path: Path):
    headers = tmp_path / "headers"
    manifest = tmp_path / "manifest.json"
    config = tmp_path / "config.json"
    digest = TARGET_IMAGE.split("sha256:", 1)[1]
    headers.write_text(f"Docker-Content-Digest: sha256:{digest}\n", encoding="utf-8")
    _write_json(manifest, {"schemaVersion": 2, "config": {"digest": "sha256:cfg"}})
    _write_json(
        config,
        {
            "config": {
                "Labels": {
                    "org.opencontainers.image.source": (
                        "https://github.com/Liu-Hy/ABDA-NL"
                    ),
                    "org.opencontainers.image.revision": (
                        "c55aa0d67562d2a08ea4fa158aab262e432ddb88"
                    ),
                    "org.opencontainers.image.licenses": "MIT",
                }
            }
        },
    )
    result = _run_function(
        "abda_mcp_image_validate_registry_image", headers, manifest, config
    )
    assert result.returncode == 0, result.stderr

    changed = json.loads(config.read_text(encoding="utf-8"))
    changed["config"]["Labels"]["org.opencontainers.image.revision"] = "wrong"
    _write_json(config, changed)
    result = _run_function(
        "abda_mcp_image_validate_registry_image", headers, manifest, config
    )
    assert result.returncode != 0
    assert "provenance labels changed" in result.stderr


def test_mcp_command_image_gate_validates_public_contract(tmp_path: Path):
    ready = tmp_path / "public-ready.json"
    config = tmp_path / "public-config.json"
    _write_json(ready, {"status": "ready"})
    _write_json(
        config,
        {
            "llm_enabled": True,
            "llm_auth_required": True,
            "byok_enabled": True,
            "byok_keys_stored": False,
            "default_profile": "balanced",
        },
    )
    prefix = tmp_path / "public"
    result = _run_function("abda_mcp_image_validate_public_contract", prefix)
    assert result.returncode == 0, result.stderr

    value = json.loads(config.read_text(encoding="utf-8"))
    value["byok_keys_stored"] = True
    _write_json(config, value)
    result = _run_function("abda_mcp_image_validate_public_contract", prefix)
    assert result.returncode != 0
    assert "byok_keys_stored" in result.stderr
