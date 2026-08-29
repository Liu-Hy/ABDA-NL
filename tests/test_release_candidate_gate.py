"""Contracts for the image-only Azure release-candidate gate."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import shlex
import subprocess


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "deploy" / "azure" / "gate6-release-candidate-image.sh"
APP = "abda-nl-stg-web"
GENERATED_HOST = "abda-nl-stg-web.blueforest-da494f7c.eastus2.azurecontainerapps.io"
CUSTOM_HOST = "demo.abda-nl.org"
OLD_REVISION = "abda-nl-stg-web--trial-pilot-v1"
TARGET_REVISION = "abda-nl-stg-web--rc-4485109"
OLD_IMAGE = (
    "ghcr.io/liu-hy/abda-nl@sha256:"
    "71f759c7bbfe25cc2ae974f006b8fed853ef87e5db260fc875fa3f50257739f9"
)
TARGET_IMAGE = (
    "ghcr.io/liu-hy/abda-nl@sha256:"
    "11861402c8fa3fd677848f94155e29065ebafd9a4a76b03e41b1cf48312e5c58"
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
                f"abda_rc_set_constants; {function} {quoted}"
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
    if phase == "old":
        image = OLD_IMAGE
        latest = ready = OLD_REVISION
        suffix = "trial-pilot-v1"
    elif phase == "target_pending":
        image = TARGET_IMAGE
        latest, ready = TARGET_REVISION, OLD_REVISION
        suffix = "rc-4485109"
    elif phase == "target":
        image = TARGET_IMAGE
        latest = ready = TARGET_REVISION
        suffix = "rc-4485109"
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
        "properties": {
            "provisioningState": "Succeeded",
            "runningStatus": "Running",
            "latestRevisionName": latest,
            "latestReadyRevisionName": ready,
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


def _metrics(*, openrouter_spent: int = 0) -> str:
    return "\n".join(
        (
            "abda_trial_enabled 1",
            "abda_trial_max_users 10",
            "abda_trial_grant_microusd 5000000",
            "abda_trial_budget_microusd 50000000",
            "abda_trial_activations 1",
            "abda_trial_allocated_microusd 5000000",
            "abda_trial_spent_microusd 22387",
            "abda_trial_reserved_microusd 0",
            "abda_trial_uncertain_charged_reservations 0",
            "abda_trial_uncertain_charged_microusd 0",
            "abda_openrouter_enabled 0",
            "abda_openrouter_budget_microusd 500000000",
            f"abda_openrouter_spent_microusd {openrouter_spent}",
            "abda_openrouter_reserved_microusd 0",
            "abda_openrouter_uncertain_charged_reservations 0",
            "abda_openrouter_uncertain_charged_microusd 0",
            "abda_database_pool_capacity 5",
        )
    )


def _acceptance_files(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    headers = tmp_path / "root.headers"
    ready = tmp_path / "ready.json"
    config = tmp_path / "config.json"
    metrics = tmp_path / "metrics.txt"
    headers.write_text(
        "\n".join(
            (
                "HTTP/2 200",
                "x-content-type-options: nosniff",
                "x-frame-options: DENY",
                "referrer-policy: no-referrer",
                "cross-origin-opener-policy: same-origin",
                "cross-origin-resource-policy: same-origin",
                (
                    "permissions-policy: camera=(), microphone=(), geolocation=(), "
                    "payment=(), usb=()"
                ),
                "strict-transport-security: max-age=31536000",
                (
                    "content-security-policy: default-src 'self'; base-uri 'none'; "
                    "object-src 'none'; frame-ancestors 'none'; script-src 'self'; "
                    "connect-src 'self'; upgrade-insecure-requests"
                ),
            )
        ),
        encoding="utf-8",
    )
    _write_json(ready, {"status": "ready"})
    _write_json(
        config,
        {
            "llm_enabled": True,
            "llm_auth_required": True,
            "byok_enabled": True,
            "byok_keys_stored": False,
            "default_profile": "balanced",
            "profiles": [{"id": "balanced"}],
            "byok_providers": [
                {
                    "id": provider,
                    "models": [{"id": f"{provider}-model"}],
                    "default_model": f"{provider}-model",
                }
                for provider in ("anthropic", "google", "openai", "openrouter")
            ],
        },
    )
    metrics.write_text(_metrics(), encoding="utf-8")
    return headers, ready, config, metrics


def test_release_candidate_gate_is_executable_and_has_valid_bash_syntax():
    assert GATE.stat().st_mode & 0o111
    subprocess.run(["bash", "-n", str(GATE)], check=True)


def test_release_candidate_gate_has_exactly_one_narrow_mutation():
    source = GATE.read_text(encoding="utf-8")
    for expected in (
        "448510936c69d485cf9b4e834adea69becf6b114",
        OLD_IMAGE.split("sha256:", 1)[1],
        TARGET_IMAGE.split("sha256:", 1)[1],
        OLD_REVISION,
        TARGET_REVISION,
        "DEPLOY_ABDA_RELEASE_CANDIDATE",
        "RELEASE_CANDIDATE_IMAGE_DEPLOYED_BROWSER_AND_OUTAGE_DRILL_REQUIRED",
    ):
        assert expected in source
    assert source.count("az containerapp update") == 2
    assert source.count('--image "$ABDA_IMAGE_REPOSITORY@sha256:') == 1
    assert source.count('--revision-suffix "$ABDA_RC_TARGET_SUFFIX"') == 1
    for forbidden in (
        "az deployment group create",
        "az containerapp job start",
        "az containerapp job create",
        "az containerapp secret set",
        "az containerapp hostname",
        "--set-env-vars",
        "read -r -s",
    ):
        assert forbidden not in source
    assert "set +x" in source
    assert "unset HISTFILE" in source
    assert "set -x" not in source


def test_release_candidate_gate_accepts_only_reviewed_app_phases(tmp_path: Path):
    for phase in ("old", "target_pending", "target"):
        path = tmp_path / f"{phase}.json"
        _write_json(path, _app(phase))
        result = _run_function("abda_rc_validate_app_phase", path)
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
    result = _run_function("abda_rc_validate_app_phase", path)
    assert result.returncode != 0
    assert "ABDA_OPENROUTER_FAILOVER_ENABLED" in result.stderr


def test_release_candidate_gate_rejects_added_environment_or_domain_drift(
    tmp_path: Path,
):
    changed = _app("old")
    changed["properties"]["template"]["containers"][0]["env"].append(
        {"name": "UNREVIEWED_SETTING", "value": "1"}
    )
    path = tmp_path / "added-env.json"
    _write_json(path, changed)
    result = _run_function("abda_rc_validate_app_phase", path)
    assert result.returncode != 0
    assert "inventory changed" in result.stderr

    changed = _app("old")
    changed["properties"]["configuration"]["ingress"]["customDomains"][0][
        "certificateId"
    ] = "/wrong-certificate"
    path = tmp_path / "changed-domain.json"
    _write_json(path, changed)
    result = _run_function("abda_rc_validate_app_phase", path)
    assert result.returncode != 0
    assert "certificate binding changed" in result.stderr


def test_release_candidate_gate_preserves_opaque_provider_and_identity_values(
    tmp_path: Path,
):
    before = _app("old")
    after = _app("target")
    before_path = tmp_path / "before.json"
    after_path = tmp_path / "after.json"
    _write_json(before_path, before)
    _write_json(after_path, after)
    result = _run_function(
        "abda_rc_compare_opaque_settings", before_path, after_path
    )
    assert result.returncode == 0, result.stderr

    environment = after["properties"]["template"]["containers"][0]["env"]
    next(
        item for item in environment if item["name"] == "AZURE_ANTHROPIC_ENDPOINT"
    )["value"] = "https://other-resource.services.ai.azure.com/anthropic"
    _write_json(after_path, after)
    result = _run_function(
        "abda_rc_compare_opaque_settings", before_path, after_path
    )
    assert result.returncode != 0
    assert "opaque identity or provider setting changed" in result.stderr


def test_release_candidate_gate_validates_registry_digest_and_labels(tmp_path: Path):
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
                        "448510936c69d485cf9b4e834adea69becf6b114"
                    ),
                    "org.opencontainers.image.licenses": "MIT",
                }
            }
        },
    )
    result = _run_function(
        "abda_rc_validate_registry_image", headers, manifest, config
    )
    assert result.returncode == 0, result.stderr

    changed = json.loads(config.read_text(encoding="utf-8"))
    changed["config"]["Labels"]["org.opencontainers.image.revision"] = "wrong"
    _write_json(config, changed)
    result = _run_function(
        "abda_rc_validate_registry_image", headers, manifest, config
    )
    assert result.returncode != 0
    assert "provenance labels changed" in result.stderr


def test_release_candidate_gate_validates_public_contract_and_ledgers(
    tmp_path: Path,
):
    paths = _acceptance_files(tmp_path)
    result = _run_function("abda_rc_validate_acceptance", *paths)
    assert result.returncode == 0, result.stderr
    assert "trial_spent_microusd: 22387" in result.stdout
    assert "openrouter_spent_microusd: 0" in result.stdout

    metrics = paths[-1]
    metrics.write_text(_metrics(openrouter_spent=1), encoding="utf-8")
    result = _run_function("abda_rc_validate_acceptance", *paths)
    assert result.returncode != 0
    assert "disabled and unused" in result.stderr


def test_release_candidate_gate_rejects_security_or_profile_drift(tmp_path: Path):
    headers, ready, config, metrics = _acceptance_files(tmp_path)
    headers.write_text(
        headers.read_text(encoding="utf-8").replace("x-frame-options: DENY\n", ""),
        encoding="utf-8",
    )
    result = _run_function(
        "abda_rc_validate_acceptance", headers, ready, config, metrics
    )
    assert result.returncode != 0
    assert "x-frame-options" in result.stderr

    headers, ready, config, metrics = _acceptance_files(tmp_path)
    value = json.loads(config.read_text(encoding="utf-8"))
    value["profiles"] = copy.deepcopy(value["profiles"]) + [{"id": "unreviewed"}]
    _write_json(config, value)
    result = _run_function(
        "abda_rc_validate_acceptance", headers, ready, config, metrics
    )
    assert result.returncode != 0
    assert "funded profile allowlist changed" in result.stderr
