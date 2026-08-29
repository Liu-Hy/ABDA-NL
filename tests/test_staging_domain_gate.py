"""Contracts for the resume-safe Azure staging custom-domain gate."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import textwrap

import pytest


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "deploy" / "azure" / "gate4-staging-domain.sh"
SOURCE_COMMIT = "9abd0264c715596401d87b83d08ed2e82ab5e34b"
IMAGE_SHA256 = "71f759c7bbfe25cc2ae974f006b8fed853ef87e5db260fc875fa3f50257739f9"
SUBSCRIPTION = "00e62f6e-2174-40b2-b428-8ebfd7c2ac54"
RESOURCE_GROUP = "abda-nl-staging"
ENVIRONMENT = "abda-nl-stg-environment"
APP = "abda-nl-stg-web"
GENERATED_HOST = "abda-nl-stg-web.blueforest-da494f7c.eastus2.azurecontainerapps.io"
CUSTOM_HOST = "demo.abda-nl.org"
CERTIFICATE_ID = (
    f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{RESOURCE_GROUP}"
    f"/providers/Microsoft.App/managedEnvironments/{ENVIRONMENT}"
    "/managedCertificates/demo-abda-nl-org"
)
VERIFICATION_ID = "verification-id-1234567890"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    path.chmod(0o700)


def test_domain_gate_has_valid_bash_syntax_and_is_executable():
    assert GATE.stat().st_mode & 0o111
    subprocess.run(["bash", "-n", str(GATE)], check=True)


def test_domain_gate_is_pinned_and_has_narrow_mutations():
    script = GATE.read_text(encoding="utf-8")

    for expected in (
        SOURCE_COMMIT,
        IMAGE_SHA256,
        SUBSCRIPTION,
        RESOURCE_GROUP,
        CUSTOM_HOST,
        "BIND_ABDA_STAGING_DOMAIN",
        "AUTH0_CUSTOM_URLS_SAVED",
        "PROMOTE_ABDA_STAGING_DOMAIN",
        "WAITING_FOR_CLOUDFLARE_DNS",
        "DOMAIN_BOUND_AUTH0_UPDATE_REQUIRED",
        "CUSTOM_DOMAIN_DEPLOYED_BROWSER_AUTH_REQUIRED",
    ):
        assert expected in script

    assert script.count("az containerapp hostname add") == 1
    assert script.count("az containerapp hostname bind") == 2  # help plus mutation
    assert script.count("az deployment group create") == 1
    assert "az containerapp job start" not in script
    assert "az containerapp delete" not in script
    assert "az group delete" not in script
    assert "az containerapp hostname delete" not in script
    assert "az containerapp env certificate delete" not in script
    assert "ABDA_DEPLOY_POSTGRES_ADMIN_PASSWORD" not in script
    assert "--mode Incremental" in script
    assert "--result-format ResourceIdOnly" in script
    assert "ABDA_DEPLOY_TRIAL_ENABLED='false'" in script
    assert "ABDA_DEPLOY_OPENROUTER_FAILOVER_ENABLED='false'" in script
    assert "set +x" in script
    assert "unset HISTFILE" in script
    assert "set -x" not in script
    assert "az containerapp secret list --help |" not in script


def _run_what_if_check(
    tmp_path: Path,
    changes: list[dict[str, object]],
) -> subprocess.CompletedProcess[str]:
    expected_id = (
        f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{RESOURCE_GROUP}"
        f"/providers/Microsoft.App/containerApps/{APP}"
    )
    result_path = tmp_path / "what-if.json"
    result_path.write_text(
        json.dumps({"status": "Succeeded", "changes": changes}),
        encoding="utf-8",
    )
    return subprocess.run(
        [
            "bash",
            "-c",
            (
                f"source {GATE}; "
                f"abda_domain_validate_promotion_what_if {result_path} {expected_id}"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("change_type", ["Deploy", "Modify"])
def test_domain_promotion_review_accepts_one_exact_app_mutation(
    tmp_path: Path, change_type: str
):
    expected_id = (
        f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{RESOURCE_GROUP}"
        f"/providers/Microsoft.App/containerApps/{APP}"
    )
    result = _run_what_if_check(
        tmp_path,
        [{"changeType": change_type, "resourceId": expected_id}],
    )

    assert result.returncode == 0, result.stderr
    assert change_type in result.stdout


@pytest.mark.parametrize("change_type", ["Create", "Delete", "Unsupported"])
def test_domain_promotion_review_rejects_dangerous_changes(
    tmp_path: Path, change_type: str
):
    expected_id = (
        f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{RESOURCE_GROUP}"
        f"/providers/Microsoft.App/containerApps/{APP}"
    )
    result = _run_what_if_check(
        tmp_path,
        [{"changeType": change_type, "resourceId": expected_id}],
    )

    assert result.returncode != 0
    assert f"unexpected {change_type}" in result.stderr


def _install_fake_commands(tmp_path: Path) -> tuple[Path, Path, Path]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    state_path = tmp_path / "azure-state"
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
        fake_bin / "dig",
        f"""
        #!/usr/bin/env python3
        import os
        import sys

        args = sys.argv[1:]
        ready = os.environ.get("ABDA_TEST_DNS_READY") == "1"
        if args[-2:] == ["abda-nl.org", "NS"]:
            print("alexis.ns.cloudflare.com.")
            print("dana.ns.cloudflare.com.")
        elif args[-2:] == ["abda-nl.org", "CAA"]:
            pass
        elif args[-2:] == ["{CUSTOM_HOST}", "CNAME"] and ready:
            print("{GENERATED_HOST}.")
        elif args[-2:] == ["asuid.{CUSTOM_HOST}", "TXT"] and ready:
            print('"{VERIFICATION_ID}"')
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

        if url.endswith("/.well-known/openid-configuration"):
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
                        "default_profile": "balanced",
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
        elif url in {{
            "https://{GENERATED_HOST}/",
            "https://{CUSTOM_HOST}/",
        }}:
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
        from urllib.parse import quote

        args = sys.argv[1:]
        state_path = Path(os.environ["ABDA_TEST_STATE"])
        log_path = Path(os.environ["ABDA_TEST_AZ_LOG"])
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(" ".join(args) + "\\n")

        if "--help" in args:
            if args[:3] == ["containerapp", "secret", "list"]:
                print("--show-values")
            print("long Azure help output\\n" * 20000, end="")
            raise SystemExit(0)

        def state():
            return state_path.read_text(encoding="utf-8").strip() if state_path.exists() else "unbound"

        def set_state(value):
            state_path.write_text(value, encoding="utf-8")

        def emit(value):
            if "--output" in args and args[args.index("--output") + 1] == "none":
                return
            if isinstance(value, str):
                print(value)
            else:
                print(json.dumps(value))

        def revision_name():
            return "{APP}--custom" if state() == "promoted" else "{APP}--repaired"

        def app_document():
            current = state()
            if current == "unbound":
                custom_domains = []
            elif current == "added":
                custom_domains = [{{"name": "{CUSTOM_HOST}", "bindingType": "Disabled"}}]
            else:
                custom_domains = [
                    {{
                        "name": "{CUSTOM_HOST}",
                        "bindingType": "SniEnabled",
                        "certificateId": "{CERTIFICATE_ID}",
                    }}
                ]
            promoted = current == "promoted"
            public_origin = "https://{CUSTOM_HOST}" if promoted else "https://{GENERATED_HOST}"
            trusted_hosts = "{GENERATED_HOST},{CUSTOM_HOST}" if promoted else "{GENERATED_HOST}"
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
                            "httpHeaders": [{{"name": "Host", "value": "{GENERATED_HOST}"}}],
                        }},
                    }}
                )
            env = [
                {{"name": "ABDA_ENVIRONMENT", "value": "staging"}},
                {{"name": "ABDA_AUTH_MODE", "value": "oidc"}},
                {{"name": "ABDA_AUTO_CREATE_DB", "value": "0"}},
                {{"name": "ABDA_PUBLIC_BASE_URL", "value": public_origin}},
                {{"name": "ABDA_TRUSTED_HOSTS", "value": trusted_hosts}},
                {{"name": "ABDA_TRIAL_ENABLED", "value": "false"}},
                {{"name": "ABDA_OPENROUTER_FAILOVER_ENABLED", "value": "false"}},
                {{"name": "ABDA_DATABASE_URL", "secretRef": "database-url"}},
                {{"name": "ABDA_SESSION_SECRET", "secretRef": "session-secret"}},
                {{"name": "ABDA_MCP_TOKEN_PEPPER", "secretRef": "mcp-token-pepper"}},
                {{"name": "ABDA_METRICS_TOKEN", "secretRef": "metrics-token"}},
                {{"name": "ABDA_OIDC_CLIENT_SECRET", "secretRef": "oidc-client-secret"}},
                {{"name": "AZURE_OPENAI_API_KEY", "secretRef": "foundry-api-key"}},
                {{"name": "OPENROUTER_API_KEY", "secretRef": "openrouter-api-key"}},
                {{"name": "ABDA_OIDC_CLIENT_ID", "value": "clientid123456"}},
                {{"name": "AZURE_ANTHROPIC_ENDPOINT", "value": "https://example.services.ai.azure.com/anthropic"}},
                {{"name": "ANTHROPIC_FOUNDRY_CLAUDE_SONNET_4_6_MODEL", "value": "claude-sonnet-4-6"}},
            ]
            return {{
                "name": "{APP}",
                "properties": {{
                    "provisioningState": "Succeeded",
                    "runningStatus": "Running",
                    "latestRevisionName": revision_name(),
                    "latestReadyRevisionName": revision_name(),
                    "customDomainVerificationId": "{VERIFICATION_ID}",
                    "configuration": {{
                        "ingress": {{
                            "fqdn": "{GENERATED_HOST}",
                            "external": True,
                            "allowInsecure": False,
                            "targetPort": 8000,
                            "customDomains": custom_domains,
                        }}
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
                emit(
                    {{
                        "id": "{SUBSCRIPTION}",
                        "tenantId": "040f05eb-33ab-462f-af54-fb4bedb055ae",
                        "user": {{"name": "hliu2@cloudbank.org"}},
                        "state": "Enabled",
                    }}
                )
        elif args[:2] == ["bicep", "version"]:
            emit("Bicep CLI version 0.46.1 (test)")
        elif args[:3] == ["deployment", "group", "show"]:
            query = args[args.index("--query") + 1]
            if query == "properties.provisioningState":
                emit("Succeeded")
            elif query == "properties.outputs":
                emit(
                    {{
                        "containerAppsEnvironmentName": {{"value": "{ENVIRONMENT}"}},
                        "migrationJobName": {{"value": "abda-nl-stg-migrate"}},
                        "expectedAppName": {{"value": "{APP}"}},
                        "postgresHost": {{"value": "abda-nl-stg-postgres-bgjhpbgw.postgres.database.azure.com"}},
                        "expectedPublicOrigin": {{"value": "https://{GENERATED_HOST}"}},
                        "postgresDatabase": {{"value": "abda"}},
                        "postgresAdminLogin": {{"value": "abdaadmin"}},
                    }}
                )
            else:
                raise SystemExit(f"unexpected deployment query: {{query}}")
        elif args[:3] == ["containerapp", "env", "show"]:
            emit({{"name": "{ENVIRONMENT}", "properties": {{"provisioningState": "Succeeded"}}}})
        elif args[:4] == ["containerapp", "env", "certificate", "list"]:
            if state() in {{"bound", "promoted"}}:
                emit(
                    [
                        {{
                            "id": "{CERTIFICATE_ID}",
                            "properties": {{
                                "subjectName": "CN={CUSTOM_HOST}",
                                "provisioningState": "Succeeded",
                                "domainControlValidation": "CNAME",
                            }},
                        }}
                    ]
                )
            else:
                emit([])
        elif args[:3] == ["postgres", "flexible-server", "show"]:
            emit(
                {{
                    "name": "abda-nl-stg-postgres-bgjhpbgw",
                    "state": "Ready",
                    "fullyQualifiedDomainName": "abda-nl-stg-postgres-bgjhpbgw.postgres.database.azure.com",
                    "publicNetworkAccess": "Disabled",
                }}
            )
        elif args[:3] == ["containerapp", "job", "list"]:
            emit([{{"name": "abda-nl-stg-migrate"}}])
        elif args[:2] == ["containerapp", "list"]:
            emit([{{"name": "{APP}"}}])
        elif args[:2] == ["containerapp", "show"]:
            emit(app_document())
        elif args[:3] == ["containerapp", "revision", "show"]:
            emit(
                {{
                    "name": revision_name(),
                    "properties": {{
                        "active": True,
                        "healthState": "Healthy",
                        "provisioningState": "Provisioned",
                    }},
                }}
            )
        elif args[:3] == ["containerapp", "replica", "list"]:
            emit(
                [
                    {{
                        "name": "replica-1",
                        "properties": {{
                            "runningState": "Running",
                            "containers": [{{"name": "web", "ready": True}}],
                        }},
                    }}
                ]
            )
        elif args[:3] == ["containerapp", "hostname", "add"]:
            set_state("added")
        elif args[:3] == ["containerapp", "hostname", "bind"]:
            set_state("bound")
        elif args[:3] == ["containerapp", "secret", "list"]:
            app_password = "app-password-123456789012345678901234"
            database_url = (
                "postgresql+psycopg://abda_app:"
                + quote(app_password, safe="")
                + "@abda-nl-stg-postgres-bgjhpbgw.postgres.database.azure.com:5432/abda?sslmode=require"
            )
            emit(
                [
                    {{"name": "database-url", "value": database_url}},
                    {{"name": "session-secret", "value": "session-secret-12345678901234567890"}},
                    {{"name": "mcp-token-pepper", "value": "mcp-pepper-1234567890123456789012"}},
                    {{"name": "metrics-token", "value": "metrics-token-12345678901234567890"}},
                    {{"name": "oidc-client-secret", "value": "auth0-secret-1234567890"}},
                    {{"name": "foundry-api-key", "value": "foundry-key-1234567890"}},
                    {{"name": "openrouter-api-key", "value": "openrouter-key-1234567890"}},
                ]
            )
        elif args[:3] == ["deployment", "group", "validate"]:
            emit({{}})
        elif args[:3] == ["deployment", "group", "what-if"]:
            resource_id = (
                "/subscriptions/{SUBSCRIPTION}/resourceGroups/{RESOURCE_GROUP}"
                "/providers/Microsoft.App/containerApps/{APP}"
            )
            emit({{"status": "Succeeded", "changes": [{{"changeType": "Modify", "resourceId": resource_id}}]}})
        elif args[:3] == ["deployment", "group", "create"]:
            set_state("promoted")
        else:
            raise SystemExit(f"unexpected fake az command: {{args!r}}")
        """,
    )
    return fake_bin, state_path, az_log


def _run_gate(
    run_dir: Path,
    fake_bin: Path,
    state_path: Path,
    az_log: Path,
    *,
    dns_ready: bool,
    input_text: str = "",
) -> subprocess.CompletedProcess[str]:
    run_dir.mkdir()
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "ABDA_TEST_SOURCE_ROOT": str(ROOT),
            "ABDA_TEST_STATE": str(state_path),
            "ABDA_TEST_AZ_LOG": str(az_log),
            "ABDA_TEST_DNS_READY": "1" if dns_ready else "0",
        }
    )
    return subprocess.run(
        [str(GATE)],
        input=input_text,
        check=False,
        capture_output=True,
        text=True,
        cwd=run_dir,
        env=environment,
        timeout=60,
    )


def test_domain_gate_reports_dns_without_mutating_azure(tmp_path: Path):
    fake_bin, state_path, az_log = _install_fake_commands(tmp_path)
    result = _run_gate(
        tmp_path / "run-dns",
        fake_bin,
        state_path,
        az_log,
        dns_ready=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "result: WAITING_FOR_CLOUDFLARE_DNS" in result.stdout
    assert f"cname_target: {GENERATED_HOST}" in result.stdout
    assert f"txt_value: {VERIFICATION_ID}" in result.stdout
    commands = az_log.read_text(encoding="utf-8")
    assert "containerapp hostname add" not in commands
    assert "containerapp hostname bind --name" not in commands
    assert "deployment group create" not in commands
    assert not state_path.exists()


def test_domain_gate_can_cancel_binding_without_mutation(tmp_path: Path):
    fake_bin, state_path, az_log = _install_fake_commands(tmp_path)
    result = _run_gate(
        tmp_path / "run-cancel",
        fake_bin,
        state_path,
        az_log,
        dns_ready=True,
        input_text="\n",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Cancelled without changing Azure" in result.stdout
    commands = az_log.read_text(encoding="utf-8")
    assert "containerapp hostname add" not in commands
    assert "containerapp hostname bind --name" not in commands
    assert "deployment group create" not in commands
    assert not state_path.exists()


def test_domain_gate_resumes_through_binding_and_promotion(tmp_path: Path):
    fake_bin, state_path, az_log = _install_fake_commands(tmp_path)

    bind = _run_gate(
        tmp_path / "run-bind",
        fake_bin,
        state_path,
        az_log,
        dns_ready=True,
        input_text="BIND_ABDA_STAGING_DOMAIN\n",
    )
    assert bind.returncode == 0, bind.stdout + bind.stderr
    assert "result: DOMAIN_BOUND_AUTH0_UPDATE_REQUIRED" in bind.stdout
    assert state_path.read_text(encoding="utf-8") == "bound"

    promote = _run_gate(
        tmp_path / "run-promote",
        fake_bin,
        state_path,
        az_log,
        dns_ready=True,
        input_text=(
            "AUTH0_CUSTOM_URLS_SAVED\n"
            "PROMOTE_ABDA_STAGING_DOMAIN\n"
        ),
    )
    combined = promote.stdout + promote.stderr
    assert promote.returncode == 0, combined
    assert "Custom-domain promotion planned Azure changes:" in promote.stdout
    assert "custom_origin_acceptance: passed" in promote.stdout
    assert "generated_origin_readiness: passed" in promote.stdout
    assert "result: CUSTOM_DOMAIN_DEPLOYED_BROWSER_AUTH_REQUIRED" in promote.stdout
    assert state_path.read_text(encoding="utf-8") == "promoted"

    commands = az_log.read_text(encoding="utf-8")
    assert commands.count("containerapp hostname add --name") == 1
    assert commands.count("containerapp hostname bind --name") == 1
    assert commands.count("deployment group create") == 1
    assert "containerapp job start" not in commands
    for secret in (
        "app-password-123456789012345678901234",
        "session-secret-12345678901234567890",
        "mcp-pepper-1234567890123456789012",
        "metrics-token-12345678901234567890",
        "auth0-secret-1234567890",
        "foundry-key-1234567890",
        "openrouter-key-1234567890",
    ):
        assert secret not in combined
