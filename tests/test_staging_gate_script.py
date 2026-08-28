"""Contracts for the guarded first Azure application deployment."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import textwrap

import pytest


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "deploy" / "azure" / "gate3-staging-application.sh"
SOURCE_COMMIT = "3cace0bdef793e6ee966675d1e97b69d77fe2112"
IMAGE_SHA256 = "c3f6ec80972850d30850ec2e72d28fd673e835187bebdc45a8f9cda4a8ad1a55"
SUBSCRIPTION = "00e62f6e-2174-40b2-b428-8ebfd7c2ac54"
RESOURCE_GROUP = "abda-nl-staging"
JOB = "abda-nl-stg-migrate"
APP = "abda-nl-stg-web"


def _run_what_if_check(
    tmp_path: Path,
    changes: list[dict[str, str]],
    allowed_resource_id: str,
) -> subprocess.CompletedProcess[str]:
    result_path = tmp_path / "what-if.json"
    result_path.write_text(
        json.dumps({"status": "Succeeded", "changes": changes}),
        encoding="utf-8",
    )
    command = (
        f"source {GATE}; "
        f"abda_validate_what_if {result_path} {allowed_resource_id} Test"
    )
    return subprocess.run(
        ["bash", "-c", command],
        check=False,
        capture_output=True,
        text=True,
    )


def _write_executable(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    path.chmod(0o700)


def test_gate_has_valid_bash_syntax_and_is_executable():
    assert GATE.stat().st_mode & 0o111
    subprocess.run(["bash", "-n", str(GATE)], check=True)


def test_gate_is_bound_to_the_verified_staging_candidate():
    script = GATE.read_text(encoding="utf-8")

    for expected in (
        SOURCE_COMMIT,
        IMAGE_SHA256,
        SUBSCRIPTION,
        RESOURCE_GROUP,
        JOB,
        APP,
        "https://login.abda-nl.org/.well-known/openid-configuration",
        "https://abda-nl-stg-web.blueforest-da494f7c.eastus2.azurecontainerapps.io",
    ):
        assert expected in script

    assert "ABDA_DEPLOY_TRIAL_ENABLED='false'" in script
    assert "ABDA_DEPLOY_OPENROUTER_FAILOVER_ENABLED='false'" in script
    assert "DEPLOY_ABDA_STAGING_APPLICATION" in script
    assert "--mode Incremental" in script
    assert "--result-format ResourceIdOnly" in script
    assert "set +x" in script
    assert "unset HISTFILE" in script
    assert "set -x" not in script
    assert ":latest" not in script
    assert "Microsoft.Authorization/roleAssignments" not in script
    assert "az group delete" not in script
    assert "az containerapp delete" not in script


def test_review_accepts_only_the_expected_job_mutation(tmp_path):
    expected_id = (
        f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{RESOURCE_GROUP}"
        f"/providers/Microsoft.App/jobs/{JOB}"
    )
    result = _run_what_if_check(
        tmp_path,
        [
            {"changeType": "NoChange", "resourceId": "/unrelated/read-only"},
            {"changeType": "Create", "resourceId": expected_id},
        ],
        expected_id,
    )

    assert result.returncode == 0, result.stderr
    assert "Create" in result.stdout
    assert expected_id in result.stdout


@pytest.mark.parametrize("change_type", ["Delete", "Unsupported"])
def test_review_rejects_dangerous_change_types(tmp_path, change_type):
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
    assert f"STOP: {change_type}" in result.stderr


def test_review_rejects_a_mutation_outside_the_expected_resource(tmp_path):
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
        [{"changeType": "Deploy", "resourceId": unexpected_id}],
        expected_id,
    )

    assert result.returncode != 0
    assert "STOP: unexpected Deploy target" in result.stderr


def test_review_accepts_the_wrapped_azure_result_shape(tmp_path):
    expected_id = (
        f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{RESOURCE_GROUP}"
        f"/providers/Microsoft.App/containerApps/{APP}"
    )
    result_path = tmp_path / "what-if.json"
    result_path.write_text(
        json.dumps(
            {
                "properties": {
                    "status": "Succeeded",
                    "changes": [
                        {"changeType": "Modify", "resourceId": expected_id}
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            "bash",
            "-c",
            f"source {GATE}; "
            f"abda_validate_what_if {result_path} {expected_id} Test",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Modify" in result.stdout


def test_gate_reaches_confirmation_without_mutating_azure(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    az_log = tmp_path / "az.log"

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
                "migration-job.bicep",
                "migration-job.bicepparam",
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
        fake_bin / "curl",
        f"""
        #!/usr/bin/env python3
        import json
        from pathlib import Path
        import sys

        args = sys.argv[1:]
        url = args[-1]

        def option(name):
            if name not in args:
                return None
            return args[args.index(name) + 1]

        output = option("--output")
        headers = option("--dump-header")
        if url == "https://ghcr.io/token":
            print(json.dumps({{"token": "anonymous-test-token"}}))
        elif "/manifests/sha256:" in url:
            Path(output).write_text("{{}}", encoding="utf-8")
            Path(headers).write_text(
                "HTTP/1.1 200 OK\\r\\n"
                "Docker-Content-Digest: sha256:{IMAGE_SHA256}\\r\\n\\r\\n",
                encoding="utf-8",
            )
        elif url.endswith("/.well-known/openid-configuration"):
            Path(output).write_text(
                json.dumps(
                    {{
                        "issuer": "https://login.abda-nl.org/",
                        "authorization_endpoint": "https://login.abda-nl.org/authorize",
                        "token_endpoint": "https://login.abda-nl.org/oauth/token",
                        "jwks_uri": "https://login.abda-nl.org/.well-known/jwks.json",
                        "end_session_endpoint": "https://login.abda-nl.org/oidc/logout",
                    }}
                ),
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
        with Path(os.environ["ABDA_TEST_AZ_LOG"]).open("a", encoding="utf-8") as handle:
            handle.write(" ".join(args) + "\\n")

        def emit(value):
            if "--output" in args and args[args.index("--output") + 1] == "none":
                return
            if isinstance(value, str):
                print(value)
            else:
                print(json.dumps(value))

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
                    "migrationJobName": {{"value": "{JOB}"}},
                    "expectedAppName": {{"value": "{APP}"}},
                    "postgresHost": {{"value": "abda-nl-stg-postgres-bgjhpbgw.postgres.database.azure.com"}},
                    "expectedPublicOrigin": {{"value": "https://abda-nl-stg-web.blueforest-da494f7c.eastus2.azurecontainerapps.io"}},
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
                "properties": {{
                    "state": "Ready",
                    "network": {{"publicNetworkAccess": "Disabled"}},
                }},
            }})
        elif args[:3] in (
            ["containerapp", "job", "list"],
            ["containerapp", "list", "--resource-group"],
        ):
            emit([])
        elif args[:3] == ["deployment", "group", "validate"]:
            emit({{}})
        elif args[:3] == ["deployment", "group", "what-if"]:
            name = args[args.index("--name") + 1]
            if name == "abda-nl-stg-migration":
                resource = (
                    "/subscriptions/{SUBSCRIPTION}/resourceGroups/{RESOURCE_GROUP}"
                    "/providers/Microsoft.App/jobs/{JOB}"
                )
            elif name == "abda-nl-stg-app":
                resource = (
                    "/subscriptions/{SUBSCRIPTION}/resourceGroups/{RESOURCE_GROUP}"
                    "/providers/Microsoft.App/containerApps/{APP}"
                )
            else:
                raise SystemExit(f"unexpected what-if deployment: {{name}}")
            emit({{"status": "Succeeded", "changes": [{{"changeType": "Create", "resourceId": resource}}]}})
        else:
            raise SystemExit(f"unexpected fake az command: {{args!r}}")
        """,
    )

    secret_lines = [
        "admin-password-1234567890",
        "admin-password-1234567890",
        "app-password-123456789012345678901234",
        "app-password-123456789012345678901234",
        "clientid123",
        "auth0-secret-1234567890",
        "session-secret-12345678901234567890",
        "session-secret-12345678901234567890",
        "mcp-pepper-1234567890123456789012",
        "mcp-pepper-1234567890123456789012",
        "metrics-token-12345678901234567890",
        "metrics-token-12345678901234567890",
        "https://example.services.ai.azure.com/anthropic",
        "claude-sonnet-4-6",
        "foundry-key-1234567890",
        "openrouter-key-1234567890",
        "",
    ]
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "ABDA_TEST_SOURCE_ROOT": str(ROOT),
            "ABDA_TEST_AZ_LOG": str(az_log),
        }
    )
    result = subprocess.run(
        [str(GATE)],
        input="\n".join(secret_lines) + "\n",
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        timeout=60,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Migration job planned Azure changes:" in result.stdout
    assert "Web application planned Azure changes:" in result.stdout
    assert "Cancelled without deploying" in result.stdout
    commands = az_log.read_text(encoding="utf-8")
    assert "deployment group what-if" in commands
    assert "deployment group create" not in commands
    assert "containerapp job start" not in commands
