"""Contracts for the reversible Azure image rollback rehearsal."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import shlex
import subprocess


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "deploy" / "azure" / "gate10-rollback-rehearsal.sh"
APP = "abda-nl-stg-web"
GENERATED_HOST = "abda-nl-stg-web.blueforest-da494f7c.eastus2.azurecontainerapps.io"
CUSTOM_HOST = "demo.abda-nl.org"
CURRENT_REVISION = "abda-nl-stg-web--secure-b873112"
ROLLBACK_REVISION = "abda-nl-stg-web--rollback-3faf6eb"
RESTORE_REVISION = "abda-nl-stg-web--restore-b873112"
CURRENT_IMAGE = (
    "ghcr.io/liu-hy/abda-nl@sha256:"
    "567ec34602e1b5ab1e1a9b01864f2a67219910dc3080300bc108eb33d569856c"
)
ROLLBACK_IMAGE = (
    "ghcr.io/liu-hy/abda-nl@sha256:"
    "78481da1f49f9b049509eafc61da1c95d55ac42e425c4ab1dbb04d700971b55d"
)
CERTIFICATE_ID = (
    "/subscriptions/00e62f6e-2174-40b2-b428-8ebfd7c2ac54/"
    "resourceGroups/abda-nl-staging/providers/Microsoft.App/managedEnvironments/"
    "abda-nl-stg-environment/managedCertificates/"
    "mc-abda-nl-stg-en-demo-abda-nl-org-1928"
)


def _run_function(function: str, *arguments: Path | str) -> subprocess.CompletedProcess[str]:
    quoted = " ".join(shlex.quote(str(argument)) for argument in arguments)
    return subprocess.run(
        [
            "bash",
            "-c",
            (
                f"source {shlex.quote(str(GATE))}; "
                f"abda_rollback_set_constants; {function} {quoted}"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def _environment() -> list[dict[str, str]]:
    values = {
        "ABDA_ENVIRONMENT": "staging",
        "ABDA_ENABLE_LLM": "1",
        "ABDA_AUTH_MODE": "oidc",
        "ABDA_AUTO_CREATE_DB": "0",
        "ABDA_DATABASE_POOL_SIZE": "4",
        "ABDA_DATABASE_MAX_OVERFLOW": "1",
        "ABDA_DATABASE_POOL_TIMEOUT_SECONDS": "10",
        "ABDA_PUBLIC_BASE_URL": f"https://{CUSTOM_HOST}",
        "ABDA_TRUSTED_HOSTS": f"{GENERATED_HOST},{CUSTOM_HOST}",
        "ABDA_SESSION_COOKIE": "__Host-abda_session",
        "ABDA_COOKIE_SECURE": "1",
        "ABDA_OIDC_METADATA_URL": (
            "https://login.abda-nl.org/.well-known/openid-configuration"
        ),
        "ABDA_OIDC_ISSUER": "https://login.abda-nl.org/",
        "ABDA_OIDC_CLIENT_ID": "test-client-identifier-123456789",
        "ABDA_TRIAL_ENABLED": "True",
        "ABDA_TRIAL_MAX_USERS": "10",
        "ABDA_TRIAL_GRANT_MICROUSD": "5000000",
        "ABDA_TRIAL_BUDGET_MICROUSD": "50000000",
        "ABDA_LLM_BACKEND": "claude",
        "ABDA_CLAUDE_PROVIDER": "foundry",
        "ABDA_LLM_DEFAULT_PROFILE": "balanced",
        "ABDA_LLM_ALLOW_BYOK": "1",
        "ABDA_LLM_REQUIRE_AUTH": "1",
        "ABDA_OPENROUTER_FAILOVER_ENABLED": "False",
        "ABDA_OPENROUTER_BUDGET_MICROUSD": "500000000",
        "ABDA_OPENROUTER_BUDGET_ACK": "",
        "ABDA_PROXY_MODE": "azure-container-apps",
        "ABDA_ABUSE_PROTECTION_ENABLED": "1",
        "ABDA_MAX_REQUEST_BODY_BYTES": "2000000",
        "ABDA_ANONYMOUS_REQUESTS_PER_MINUTE": "120",
        "ABDA_MUTATION_REQUESTS_PER_MINUTE": "60",
        "ABDA_LLM_REQUESTS_PER_MINUTE": "20",
        "AZURE_ANTHROPIC_ENDPOINT": (
            "https://test-resource.services.ai.azure.com/anthropic"
        ),
        "ANTHROPIC_FOUNDRY_CLAUDE_SONNET_4_6_MODEL": "claude-sonnet-4-6",
    }
    environment = [{"name": name, "value": value} for name, value in values.items()]
    for name, secret_ref in {
        "ABDA_DATABASE_URL": "database-url",
        "ABDA_SESSION_SECRET": "session-secret",
        "ABDA_MCP_TOKEN_PEPPER": "mcp-token-pepper",
        "ABDA_METRICS_TOKEN": "metrics-token",
        "ABDA_OIDC_CLIENT_SECRET": "oidc-client-secret",
        "AZURE_OPENAI_API_KEY": "foundry-api-key",
        "OPENROUTER_API_KEY": "openrouter-api-key",
    }.items():
        environment.append({"name": name, "secretRef": secret_ref})
    return environment


def _app(phase: str) -> dict:
    if phase == "current":
        image = CURRENT_IMAGE
        latest = ready = CURRENT_REVISION
        suffix = "secure-b873112"
    elif phase == "rollback_pending":
        image = ROLLBACK_IMAGE
        latest, ready = ROLLBACK_REVISION, CURRENT_REVISION
        suffix = "rollback-3faf6eb"
    elif phase == "rollback":
        image = ROLLBACK_IMAGE
        latest = ready = ROLLBACK_REVISION
        suffix = "rollback-3faf6eb"
    elif phase == "restore_pending":
        image = CURRENT_IMAGE
        latest, ready = RESTORE_REVISION, ROLLBACK_REVISION
        suffix = "restore-b873112"
    elif phase == "restored":
        image = CURRENT_IMAGE
        latest = ready = RESTORE_REVISION
        suffix = "restore-b873112"
    else:
        raise ValueError(phase)
    probes = [
        {
            "type": probe_type,
            "httpGet": {
                "path": path,
                "port": 8000,
                "scheme": "HTTP",
                "httpHeaders": [{"name": "Host", "value": GENERATED_HOST}],
            },
        }
        for probe_type, path in (
            ("Startup", "/health/live"),
            ("Liveness", "/health/live"),
            ("Readiness", "/health/ready"),
        )
    ]
    secret_names = (
        "database-url",
        "session-secret",
        "mcp-token-pepper",
        "metrics-token",
        "oidc-client-secret",
        "foundry-api-key",
        "openrouter-api-key",
    )
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
                "secrets": [{"name": name} for name in secret_names],
                "ingress": {
                    "fqdn": GENERATED_HOST,
                    "external": True,
                    "allowInsecure": False,
                    "targetPort": 8000,
                    "transport": "Auto",
                    "traffic": [{"latestRevision": True, "weight": 100}],
                    "customDomains": [
                        {
                            "name": CUSTOM_HOST,
                            "bindingType": "SniEnabled",
                            "certificateId": CERTIFICATE_ID,
                        }
                    ],
                },
            },
            "template": {
                "revisionSuffix": suffix,
                "terminationGracePeriodSeconds": 30,
                "scale": {"minReplicas": 1, "maxReplicas": 3},
                "containers": [
                    {
                        "name": "web",
                        "image": image,
                        "resources": {"cpu": 0.5, "memory": "1Gi"},
                        "env": _environment(),
                        "probes": probes,
                    }
                ],
            },
        },
    }


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_rollback_gate_is_executable_valid_and_narrow():
    assert GATE.stat().st_mode & 0o111
    subprocess.run(["bash", "-n", str(GATE)], check=True)
    source = GATE.read_text(encoding="utf-8")
    for expected in (
        "b873112040dbfe645683d1b5e7d9adb122173ed2",
        "3faf6ebd94c4dcb69fa36cb1aba481db15a9f973",
        CURRENT_IMAGE.split("sha256:", 1)[1],
        ROLLBACK_IMAGE.split("sha256:", 1)[1],
        CURRENT_REVISION,
        ROLLBACK_REVISION,
        RESTORE_REVISION,
        "RUN_ABDA_ROLLBACK_REHEARSAL",
        "COMPATIBLE_IMAGE_ROLLBACK_AND_RESTORE_VERIFIED",
    ):
        assert expected in source
    assert source.count("az containerapp update") == 2
    assert source.count("abda_rollback_update_image \\") == 2
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
    assert "\u2013" not in source
    assert "\u2014" not in source


def test_rollback_gate_accepts_only_reviewed_resume_phases(tmp_path: Path):
    for phase in (
        "current",
        "rollback_pending",
        "rollback",
        "restore_pending",
        "restored",
    ):
        path = tmp_path / f"{phase}.json"
        _write_json(path, _app(phase))
        result = _run_function("abda_rollback_validate_app_phase", path)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == phase

    changed = _app("current")
    environment = changed["properties"]["template"]["containers"][0]["env"]
    next(
        item
        for item in environment
        if item["name"] == "ABDA_OPENROUTER_FAILOVER_ENABLED"
    )["value"] = "true"
    path = tmp_path / "changed.json"
    _write_json(path, changed)
    result = _run_function("abda_rollback_validate_app_phase", path)
    assert result.returncode != 0
    assert "ABDA_OPENROUTER_FAILOVER_ENABLED" in result.stderr


def test_rollback_gate_preserves_complete_application_contract(tmp_path: Path):
    current = _app("current")
    rollback = _app("rollback")
    restored = _app("restored")
    current_path = tmp_path / "current.json"
    rollback_path = tmp_path / "rollback.json"
    restored_path = tmp_path / "restored.json"
    _write_json(current_path, current)
    _write_json(rollback_path, rollback)
    _write_json(restored_path, restored)
    for left, right in (
        (current_path, rollback_path),
        (rollback_path, restored_path),
    ):
        result = _run_function(
            "abda_rollback_compare_application_contract", left, right
        )
        assert result.returncode == 0, result.stderr

    changed = copy.deepcopy(restored)
    changed["properties"]["template"]["scale"]["maxReplicas"] = 4
    _write_json(restored_path, changed)
    result = _run_function(
        "abda_rollback_compare_application_contract", rollback_path, restored_path
    )
    assert result.returncode != 0
    assert "settings outside the image and revision changed" in result.stderr


def test_rollback_gate_validates_both_registry_images(tmp_path: Path):
    for label, digest, commit in (
        (
            "current",
            CURRENT_IMAGE.split("sha256:", 1)[1],
            "b873112040dbfe645683d1b5e7d9adb122173ed2",
        ),
        (
            "rollback",
            ROLLBACK_IMAGE.split("sha256:", 1)[1],
            "3faf6ebd94c4dcb69fa36cb1aba481db15a9f973",
        ),
    ):
        headers = tmp_path / f"{label}.headers"
        manifest = tmp_path / f"{label}.manifest.json"
        config = tmp_path / f"{label}.config.json"
        headers.write_text(
            f"Docker-Content-Digest: sha256:{digest}\n", encoding="utf-8"
        )
        _write_json(manifest, {"schemaVersion": 2, "config": {"digest": "sha256:cfg"}})
        _write_json(
            config,
            {
                "config": {
                    "Labels": {
                        "org.opencontainers.image.source": (
                            "https://github.com/Liu-Hy/ABDA-NL"
                        ),
                        "org.opencontainers.image.revision": commit,
                        "org.opencontainers.image.licenses": "MIT",
                    }
                }
            },
        )
        result = _run_function(
            "abda_rollback_validate_registry_image",
            headers,
            manifest,
            config,
            digest,
            commit,
        )
        assert result.returncode == 0, result.stderr


def test_rollback_gate_validates_public_contract(tmp_path: Path):
    prefix = tmp_path / "public"
    _write_json(tmp_path / "public-ready.json", {"status": "ready"})
    _write_json(
        tmp_path / "public-config.json",
        {
            "llm_enabled": True,
            "llm_auth_required": True,
            "byok_enabled": True,
            "byok_keys_stored": False,
            "default_profile": "balanced",
        },
    )
    result = _run_function("abda_rollback_validate_public_contract", prefix)
    assert result.returncode == 0, result.stderr

    value = json.loads((tmp_path / "public-config.json").read_text(encoding="utf-8"))
    value["byok_keys_stored"] = True
    _write_json(tmp_path / "public-config.json", value)
    result = _run_function("abda_rollback_validate_public_contract", prefix)
    assert result.returncode != 0
    assert "byok_keys_stored" in result.stderr
