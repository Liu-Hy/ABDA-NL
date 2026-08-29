"""Contracts for the one-resource Azure Container App probe repair."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import textwrap

import pytest


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "deploy" / "azure" / "gate3-probe-repair.sh"
SOURCE_COMMIT = "ef91e88226abf9f916f976d9e668ad3536f1fe46"
IMAGE_SHA256 = "c3f6ec80972850d30850ec2e72d28fd673e835187bebdc45a8f9cda4a8ad1a55"
SUBSCRIPTION = "00e62f6e-2174-40b2-b428-8ebfd7c2ac54"
RESOURCE_GROUP = "abda-nl-staging"
APP = "abda-nl-stg-web"
OLD_REVISION = "abda-nl-stg-web--ztv7ycn"
NEW_REVISION = "abda-nl-stg-web--repaired"
FQDN = "abda-nl-stg-web.blueforest-da494f7c.eastus2.azurecontainerapps.io"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    path.chmod(0o700)


def _run_what_if_check(
    tmp_path: Path,
    changes: list[dict[str, object]],
    allowed_resource_id: str,
) -> subprocess.CompletedProcess[str]:
    result_path = tmp_path / "what-if.json"
    result_path.write_text(
        json.dumps({"status": "Succeeded", "changes": changes}),
        encoding="utf-8",
    )
    return subprocess.run(
        [
            "bash",
            "-c",
            f"source {GATE}; abda_validate_repair_what_if {result_path} {allowed_resource_id}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_repair_gate_has_valid_bash_syntax_and_is_executable():
    assert GATE.stat().st_mode & 0o111
    subprocess.run(["bash", "-n", str(GATE)], check=True)


def test_repair_gate_is_bound_to_the_diagnosed_revision_and_one_resource():
    script = GATE.read_text(encoding="utf-8")

    for expected in (
        SOURCE_COMMIT,
        IMAGE_SHA256,
        SUBSCRIPTION,
        RESOURCE_GROUP,
        APP,
        OLD_REVISION,
        "REPAIR_ABDA_STAGING_PROBES",
        "STAGING_PROBE_REPAIR_COMPLETE_CUSTOM_DOMAIN_NOT_CONFIGURED",
    ):
        assert expected in script

    assert script.count("az deployment group create") == 1
    assert "az containerapp job start" not in script
    assert "az containerapp job create" not in script
    assert "ABDA_DEPLOY_POSTGRES_ADMIN_PASSWORD" not in script
    assert "Microsoft.Authorization/roleAssignments" not in script
    assert "az group delete" not in script
    assert "az containerapp delete" not in script
    assert "--mode Incremental" in script
    assert "--result-format ResourceIdOnly" in script
    assert "ABDA_DEPLOY_TRIAL_ENABLED='false'" in script
    assert "ABDA_DEPLOY_OPENROUTER_FAILOVER_ENABLED='false'" in script
    assert "set +x" in script
    assert "unset HISTFILE" in script
    assert "set -x" not in script


@pytest.mark.parametrize("change_type", ["Modify", "Deploy"])
def test_repair_review_accepts_one_exact_app_mutation(tmp_path, change_type):
    expected_id = (
        f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{RESOURCE_GROUP}"
        f"/providers/Microsoft.App/containerApps/{APP}"
    )
    result = _run_what_if_check(
        tmp_path,
        [
            {"changeType": "NoChange", "resourceId": "/read-only/reference"},
            {"changeType": change_type, "resourceId": expected_id},
        ],
        expected_id,
    )

    assert result.returncode == 0, result.stderr
    assert change_type in result.stdout
    assert expected_id in result.stdout


@pytest.mark.parametrize("change_type", ["Create", "Delete", "Unsupported"])
def test_repair_review_rejects_dangerous_change_types(tmp_path, change_type):
    expected_id = (
        f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{RESOURCE_GROUP}"
        f"/providers/Microsoft.App/containerApps/{APP}"
    )
    result = _run_what_if_check(
        tmp_path,
        [{"changeType": change_type, "resourceId": expected_id}],
        expected_id,
    )

    assert result.returncode != 0
    assert f"unexpected {change_type}" in result.stderr


def test_repair_review_rejects_no_mutation(tmp_path):
    expected_id = (
        f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{RESOURCE_GROUP}"
        f"/providers/Microsoft.App/containerApps/{APP}"
    )
    result = _run_what_if_check(
        tmp_path,
        [{"changeType": "NoChange", "resourceId": expected_id}],
        expected_id,
    )

    assert result.returncode != 0
    assert "no Container App mutation" in result.stderr


def test_repair_review_rejects_an_extra_mutation(tmp_path):
    expected_id = (
        f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{RESOURCE_GROUP}"
        f"/providers/Microsoft.App/containerApps/{APP}"
    )
    unexpected_id = (
        f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{RESOURCE_GROUP}"
        "/providers/Microsoft.Network/virtualNetworks/unexpected"
    )
    result = _run_what_if_check(
        tmp_path,
        [
            {"changeType": "Modify", "resourceId": expected_id},
            {"changeType": "Deploy", "resourceId": unexpected_id},
        ],
        expected_id,
    )

    assert result.returncode != 0
    assert "unexpected Deploy target" in result.stderr
    assert "expected one mutation" in result.stderr


def _install_fake_commands(tmp_path: Path) -> tuple[Path, Path, Path]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    az_log = tmp_path / "az.log"
    repair_marker = tmp_path / "repair-complete"

    _write_executable(
        fake_bin / "git",
        f"""
        #!/usr/bin/env python3
        import os
        from pathlib import Path
        import shutil
        import sys

        args = sys.argv[1:]
        if args and args[0] == "clone":
            destination = Path(args[-1])
            source = Path(os.environ["ABDA_TEST_SOURCE_ROOT"])
            target = destination / "deploy" / "azure"
            target.mkdir(parents=True)
            for name in (
                "gate3-staging-application.sh",
                "app.bicep",
                "app.bicepparam",
            ):
                shutil.copy2(source / "deploy" / "azure" / name, target / name)
        elif "rev-parse" in args:
            print("{SOURCE_COMMIT}")
        elif "checkout" in args:
            pass
        else:
            raise SystemExit(f"unexpected fake git command: {{args!r}}")
        """,
    )
    _write_executable(
        fake_bin / "sha256sum",
        """
        #!/usr/bin/env python3
        import sys

        if "--check" not in sys.argv[1:]:
            raise SystemExit(f"unexpected fake sha256sum command: {sys.argv[1:]!r}")
        sys.stdin.read()
        """,
    )
    _write_executable(
        fake_bin / "curl",
        f"""
        #!/usr/bin/env python3
        import json
        from pathlib import Path
        import sys

        args = sys.argv[1:]
        urls = [value for value in args if value.startswith("https://")]
        if not urls:
            raise SystemExit(f"fake curl received no HTTPS URL: {{args!r}}")
        url = urls[-1]

        def option(name):
            if name not in args:
                return None
            return args[args.index(name) + 1]

        def write_output(value):
            output = option("--output")
            if output:
                Path(output).write_text(value, encoding="utf-8")

        if url == "https://ghcr.io/token":
            print(json.dumps({{"token": "anonymous-test-token"}}))
        elif "/manifests/sha256:" in url:
            write_output("{{}}")
            Path(option("--dump-header")).write_text(
                "HTTP/1.1 200 OK\\r\\n"
                "Docker-Content-Digest: sha256:{IMAGE_SHA256}\\r\\n\\r\\n",
                encoding="utf-8",
            )
        elif url.endswith("/.well-known/openid-configuration"):
            write_output(
                json.dumps(
                    {{
                        "issuer": "https://login.abda-nl.org/",
                        "authorization_endpoint": "https://login.abda-nl.org/authorize",
                        "token_endpoint": "https://login.abda-nl.org/oauth/token",
                        "jwks_uri": "https://login.abda-nl.org/.well-known/jwks.json",
                        "end_session_endpoint": "https://login.abda-nl.org/oidc/logout",
                    }}
                )
            )
        elif url.endswith("/health/ready"):
            write_output(json.dumps({{"status": "ready"}}))
        elif url.endswith("/health/live"):
            write_output(json.dumps({{"status": "ok"}}))
        elif url.endswith("/config"):
            write_output(
                json.dumps(
                    {{
                        "llm_enabled": True,
                        "llm_auth_required": True,
                        "byok_enabled": True,
                        "byok_keys_stored": False,
                        "profiles": [{{"id": "balanced"}}],
                        "byok_providers": [
                            {{"id": "anthropic"}},
                            {{"id": "google"}},
                            {{"id": "openai"}},
                            {{"id": "openrouter"}},
                        ],
                    }}
                )
            )
        elif url.endswith("/privacy.html") or url.endswith("/terms.html"):
            write_output("<!doctype html><title>policy</title>")
        elif url.endswith("/internal/metrics") and "--config" in args:
            write_output(
                "abda_trial_enabled 0\\n"
                "abda_trial_max_users 100\\n"
                "abda_trial_grant_microusd 5000000\\n"
                "abda_trial_budget_microusd 500000000\\n"
                "abda_openrouter_enabled 0\\n"
                "abda_openrouter_budget_microusd 500000000\\n"
                "abda_trial_reserved_microusd 0\\n"
                "abda_openrouter_reserved_microusd 0\\n"
                "abda_database_pool_capacity 5\\n"
            )
        elif url.endswith("/internal/metrics"):
            write_output(json.dumps({{"detail": "Not authenticated"}}))
            print("401", end="")
        elif url == "https://{FQDN}/":
            write_output("<!doctype html><title>ABDA-NL</title>")
            Path(option("--dump-header")).write_text(
                "HTTP/1.1 200 OK\\r\\n"
                "X-Content-Type-Options: nosniff\\r\\n"
                "X-Frame-Options: DENY\\r\\n"
                "Referrer-Policy: no-referrer\\r\\n"
                "Cross-Origin-Opener-Policy: same-origin\\r\\n"
                "Cross-Origin-Resource-Policy: same-origin\\r\\n"
                "Strict-Transport-Security: max-age=31536000; includeSubDomains\\r\\n"
                "Content-Security-Policy: default-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; script-src 'self'; connect-src 'self'; upgrade-insecure-requests\\r\\n\\r\\n",
                encoding="utf-8",
            )
        else:
            raise SystemExit(f"unexpected fake curl command: {{args!r}}")
        """,
    )
    _write_executable(
        fake_bin / "az",
        f"""
        #!/usr/bin/env python3
        import json
        import os
        from pathlib import Path
        import sys

        args = sys.argv[1:]
        log = Path(os.environ["ABDA_TEST_AZ_LOG"])
        marker = Path(os.environ["ABDA_TEST_REPAIR_MARKER"])
        with log.open("a", encoding="utf-8") as handle:
            handle.write(" ".join(args) + "\\n")

        def emit(value):
            if "--output" in args and args[args.index("--output") + 1] == "none":
                return
            if isinstance(value, str):
                print(value)
            else:
                print(json.dumps(value))

        def app_document(repaired):
            revision = "{NEW_REVISION}" if repaired else "{OLD_REVISION}"
            headers = [{{"name": "Host", "value": "{FQDN}"}}] if repaired else []
            probes = []
            for probe_type, path in (
                ("Startup", "/health/live"),
                ("Liveness", "/health/live"),
                ("Readiness", "/health/ready"),
            ):
                probes.append(
                    {{
                        "type": probe_type,
                        "httpGet": {{
                            "path": path,
                            "port": 8000,
                            "scheme": "HTTP",
                            "httpHeaders": headers,
                        }},
                    }}
                )
            env = [
                {{"name": "ABDA_ENVIRONMENT", "value": "staging"}},
                {{"name": "ABDA_AUTH_MODE", "value": "oidc"}},
                {{"name": "ABDA_AUTO_CREATE_DB", "value": "0"}},
                {{"name": "ABDA_PUBLIC_BASE_URL", "value": "https://{FQDN}"}},
                {{"name": "ABDA_TRIAL_ENABLED", "value": "false"}},
                {{"name": "ABDA_OPENROUTER_FAILOVER_ENABLED", "value": "false"}},
                {{"name": "ABDA_DATABASE_URL", "secretRef": "database-url"}},
            ]
            return {{
                "name": "{APP}",
                "properties": {{
                    "provisioningState": "Succeeded",
                    "latestRevisionName": revision,
                    "latestReadyRevisionName": revision if repaired else None,
                    "configuration": {{
                        "ingress": {{
                            "fqdn": "{FQDN}",
                            "external": True,
                            "allowInsecure": False,
                            "targetPort": 8000,
                        }},
                    }},
                    "template": {{
                        "containers": [
                            {{
                                "name": "web",
                                "image": "ghcr.io/liu-hy/abda-nl@sha256:{IMAGE_SHA256}",
                                "env": env,
                                "probes": probes,
                            }}
                        ]
                    }},
                }},
            }}

        if args[:2] == ["account", "show"]:
            if "table" in args:
                emit("Name TenantId User State\\naccess test test Enabled")
            else:
                emit({{
                    "id": "{SUBSCRIPTION}",
                    "tenantId": "040f05eb-33ab-462f-af54-fb4bedb055ae",
                    "user": {{"name": "hliu2@cloudbank.org"}},
                    "state": "Enabled",
                }})
        elif args[:2] == ["bicep", "version"]:
            emit("Bicep CLI version 0.46.1 (test)")
        elif args[:3] == ["deployment", "group", "show"]:
            query = args[args.index("--query") + 1]
            if query == "properties.provisioningState":
                emit("Succeeded")
            elif query == "properties.outputs":
                emit({{
                    "containerAppsEnvironmentName": {{"value": "abda-nl-stg-environment"}},
                    "migrationJobName": {{"value": "abda-nl-stg-migrate"}},
                    "expectedAppName": {{"value": "{APP}"}},
                    "postgresHost": {{"value": "abda-nl-stg-postgres-bgjhpbgw.postgres.database.azure.com"}},
                    "expectedPublicOrigin": {{"value": "https://{FQDN}"}},
                    "postgresDatabase": {{"value": "abda"}},
                    "postgresAdminLogin": {{"value": "abdaadmin"}},
                }})
            else:
                raise SystemExit(f"unexpected deployment query: {{query}}")
        elif args[:3] == ["containerapp", "env", "show"]:
            emit({{
                "name": "abda-nl-stg-environment",
                "properties": {{"provisioningState": "Succeeded"}},
            }})
        elif args[:3] == ["postgres", "flexible-server", "show"]:
            emit({{
                "name": "abda-nl-stg-postgres-bgjhpbgw",
                "state": "Ready",
                "fullyQualifiedDomainName": "abda-nl-stg-postgres-bgjhpbgw.postgres.database.azure.com",
                "publicNetworkAccess": "Disabled",
            }})
        elif args[:3] == ["containerapp", "job", "list"]:
            emit([{{"name": "abda-nl-stg-migrate"}}])
        elif args[:2] == ["containerapp", "list"]:
            emit([{{"name": "{APP}"}}])
        elif args[:4] == ["containerapp", "job", "execution", "list"]:
            emit([{{"name": "migration-ok", "properties": {{"status": "Succeeded"}}}}])
        elif args[:2] == ["containerapp", "show"]:
            emit(app_document(marker.exists()))
        elif args[:3] == ["containerapp", "revision", "show"]:
            repaired = marker.exists()
            emit({{
                "name": "{NEW_REVISION}" if repaired else "{OLD_REVISION}",
                "properties": {{
                    "provisioningState": "Provisioned",
                    "healthState": "Healthy" if repaired else "Unhealthy",
                    "replicas": 1,
                }},
            }})
        elif args[:3] == ["containerapp", "replica", "list"]:
            repaired = marker.exists()
            emit([
                {{
                    "name": "replica-1",
                    "properties": {{
                        "runningState": "Running" if repaired else "NotRunning",
                        "containers": [{{"name": "web", "ready": repaired}}],
                    }},
                }}
            ])
        elif args[:3] == ["deployment", "group", "validate"]:
            emit({{}})
        elif args[:3] == ["deployment", "group", "what-if"]:
            resource = (
                "/subscriptions/{SUBSCRIPTION}/resourceGroups/{RESOURCE_GROUP}"
                "/providers/Microsoft.App/containerApps/{APP}"
            )
            emit({{"status": "Succeeded", "changes": [
                {{"changeType": "Modify", "resourceId": resource}}
            ]}})
        elif args[:3] == ["deployment", "group", "create"]:
            marker.touch()
            emit({{}})
        else:
            raise SystemExit(f"unexpected fake az command: {{args!r}}")
        """,
    )

    return fake_bin, az_log, repair_marker


def _run_mocked_gate(
    tmp_path: Path,
    confirmation: str,
) -> tuple[subprocess.CompletedProcess[str], str]:
    fake_bin, az_log, repair_marker = _install_fake_commands(tmp_path)
    secrets = {
        "app": "app-password-123456789012345678901234",
        "auth0": "auth0-secret-1234567890",
        "session": "session-secret-12345678901234567890",
        "mcp": "mcp-pepper-1234567890123456789012",
        "metrics": "metrics-token-12345678901234567890",
        "foundry": "foundry-key-1234567890",
        "openrouter": "openrouter-key-1234567890",
    }
    input_lines = [
        secrets["app"],
        secrets["app"],
        "clientid123",
        secrets["auth0"],
        secrets["session"],
        secrets["session"],
        secrets["mcp"],
        secrets["mcp"],
        secrets["metrics"],
        secrets["metrics"],
        "https://example.services.ai.azure.com/anthropic",
        "claude-sonnet-4-6",
        secrets["foundry"],
        secrets["openrouter"],
        confirmation,
    ]
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "ABDA_TEST_SOURCE_ROOT": str(ROOT),
            "ABDA_TEST_AZ_LOG": str(az_log),
            "ABDA_TEST_REPAIR_MARKER": str(repair_marker),
        }
    )
    result = subprocess.run(
        [str(GATE)],
        input="\n".join(input_lines) + "\n",
        check=False,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=environment,
        timeout=60,
    )
    combined = result.stdout + result.stderr
    for secret in secrets.values():
        assert secret not in combined
    return result, az_log.read_text(encoding="utf-8")


def test_repair_gate_reaches_confirmation_without_mutating_azure(tmp_path):
    result, commands = _run_mocked_gate(tmp_path, "")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Probe repair planned Azure changes:" in result.stdout
    assert "Cancelled without changing Azure" in result.stdout
    assert "deployment group what-if" in commands
    assert "deployment group create" not in commands
    assert "containerapp job start" not in commands


def test_repair_gate_completes_healthy_revision_and_origin_acceptance(tmp_path):
    result, commands = _run_mocked_gate(tmp_path, "REPAIR_ABDA_STAGING_PROBES")

    assert result.returncode == 0, result.stdout + result.stderr
    assert f"previous_revision: {OLD_REVISION}" in result.stdout
    assert f"repaired_revision: {NEW_REVISION}" in result.stdout
    assert "generated_origin_acceptance: passed" in result.stdout
    assert "result: STAGING_PROBE_REPAIR_COMPLETE_CUSTOM_DOMAIN_NOT_CONFIGURED" in result.stdout
    assert commands.count("deployment group create") == 1
    assert "containerapp job start" not in commands
