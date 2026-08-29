"""Contracts for the image-only Azure logout repair gate."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import textwrap


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "deploy" / "azure" / "gate3-logout-image.sh"
SOURCE_COMMIT = "9abd0264c715596401d87b83d08ed2e82ab5e34b"
OLD_IMAGE = "c3f6ec80972850d30850ec2e72d28fd673e835187bebdc45a8f9cda4a8ad1a55"
NEW_IMAGE = "71f759c7bbfe25cc2ae974f006b8fed853ef87e5db260fc875fa3f50257739f9"
OLD_REVISION = "abda-nl-stg-web--0000001"
TARGET_REVISION = "abda-nl-stg-web--logout-9abd026"
FQDN = "abda-nl-stg-web.blueforest-da494f7c.eastus2.azurecontainerapps.io"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    path.chmod(0o700)


def test_logout_image_gate_is_executable_and_has_valid_bash_syntax():
    assert GATE.stat().st_mode & 0o111
    subprocess.run(["bash", "-n", str(GATE)], check=True)


def test_logout_image_gate_has_one_narrow_mutation_and_no_secret_prompts():
    source = GATE.read_text(encoding="utf-8")

    for expected in (
        SOURCE_COMMIT,
        OLD_IMAGE,
        NEW_IMAGE,
        OLD_REVISION,
        TARGET_REVISION,
        "DEPLOY_ABDA_LOGOUT_FIX",
        "LOGOUT_FIX_DEPLOYED_BROWSER_RETEST_REQUIRED",
    ):
        assert expected in source

    assert source.count("az containerapp update") == 2
    assert source.count("--image \"$ABDA_IMAGE_REPOSITORY@sha256:") == 1
    assert source.count("--revision-suffix \"$ABDA_LOGOUT_TARGET_SUFFIX\"") == 1
    assert "az deployment group create" not in source
    assert "az containerapp job start" not in source
    assert "az containerapp job create" not in source
    assert "az containerapp secret set" not in source
    assert "az containerapp hostname" not in source
    assert "ABDA_DEPLOY_POSTGRES_ADMIN_PASSWORD" not in source
    assert "read -r -s" not in source
    assert "set +x" in source
    assert "unset HISTFILE" in source
    assert "set -x" not in source
    assert "az containerapp update --help |" not in source
    assert "az containerapp secret list --help |" not in source


def _install_fake_commands(tmp_path: Path) -> tuple[Path, Path, Path]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    az_log = tmp_path / "az.log"
    deployed_marker = tmp_path / "deployed"

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
            (destination / "deploy" / "azure").mkdir(parents=True)
            (destination / "app" / "static").mkdir(parents=True)
            shutil.copy2(
                source / "deploy" / "azure" / "gate3-staging-application.sh",
                destination / "deploy" / "azure" / "gate3-staging-application.sh",
            )
            shutil.copy2(
                source / "app" / "static" / "workspace.js",
                destination / "app" / "static" / "workspace.js",
            )
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

        args = sys.argv[1:]
        if "--check" in args:
            sys.stdin.read()
        elif len(args) == 1 and args[0].endswith("workspace.js"):
            print(
                "3382ba705376229eb63fc7bd1e74fa999beffdc2fef6510e6af67dbccd046804  "
                + args[0]
            )
        else:
            raise SystemExit(f"unexpected fake sha256sum command: {args!r}")
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
            else:
                print(value, end="")

        def write_headers(value):
            output = option("--dump-header")
            if output:
                Path(output).write_text(value, encoding="utf-8")

        if url == "https://ghcr.io/token":
            print(json.dumps({{"token": "anonymous-test-token"}}))
        elif "/manifests/sha256:{NEW_IMAGE}" in url:
            write_headers(
                "HTTP/1.1 200 OK\\r\\n"
                "Docker-Content-Digest: sha256:{NEW_IMAGE}\\r\\n\\r\\n"
            )
            write_output(
                json.dumps(
                    {{
                        "schemaVersion": 2,
                        "mediaType": "application/vnd.oci.image.manifest.v1+json",
                        "config": {{"digest": "sha256:test-config"}},
                    }}
                )
            )
        elif "/blobs/sha256:test-config" in url:
            write_output(
                json.dumps(
                    {{
                        "config": {{
                            "Labels": {{
                                "org.opencontainers.image.source": "https://github.com/Liu-Hy/ABDA-NL",
                                "org.opencontainers.image.revision": "{SOURCE_COMMIT}",
                                "org.opencontainers.image.licenses": "MIT",
                            }}
                        }}
                    }}
                )
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
        elif url == "https://{FQDN}/":
            write_headers(
                "HTTP/1.1 200 OK\\r\\n"
                "X-Content-Type-Options: nosniff\\r\\n"
                "X-Frame-Options: DENY\\r\\n"
                "Referrer-Policy: no-referrer\\r\\n"
                "Cross-Origin-Opener-Policy: same-origin\\r\\n"
                "Cross-Origin-Resource-Policy: same-origin\\r\\n"
                "Strict-Transport-Security: max-age=31536000; includeSubDomains\\r\\n"
                "Content-Security-Policy: default-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; script-src 'self'; connect-src 'self'; upgrade-insecure-requests\\r\\n\\r\\n"
            )
            write_output("<!doctype html><title>ABDA-NL</title>")
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
        elif url.endswith("/workspace.js"):
            write_output("tested workspace script")
        elif url.endswith("/auth/login"):
            location = (
                "https://login.abda-nl.org/authorize?"
                "redirect_uri=https%3A%2F%2F{FQDN}%2Fauth%2Fcallback&"
                "response_type=code&code_challenge_method=S256&"
                "state=test-state&nonce=test-nonce&code_challenge=test-challenge"
            )
            write_headers(f"HTTP/1.1 303 See Other\\r\\nLocation: {{location}}\\r\\n\\r\\n")
            write_output("")
            if "--write-out" in args:
                print("303", end="")
        elif url.endswith("/api/auth/logout"):
            write_headers("HTTP/1.1 200 OK\\r\\nContent-Type: application/json\\r\\n\\r\\n")
            write_output(
                json.dumps(
                    {{
                        "logout_url": (
                            "https://login.abda-nl.org/oidc/logout?client_id=test-client&"
                            "post_logout_redirect_uri=https%3A%2F%2F{FQDN}%2F"
                        )
                    }}
                )
            )
            if "--write-out" in args:
                print("200", end="")
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
        marker = Path(os.environ["ABDA_TEST_DEPLOYED_MARKER"])
        with log.open("a", encoding="utf-8") as handle:
            handle.write(" ".join(args) + "\\n")

        def emit(value):
            if "--output" in args and args[args.index("--output") + 1] == "none":
                return
            if isinstance(value, str):
                print(value)
            else:
                print(json.dumps(value))

        def app_document(deployed):
            image = "{NEW_IMAGE}" if deployed else "{OLD_IMAGE}"
            revision = "{TARGET_REVISION}" if deployed else "{OLD_REVISION}"
            suffix = "logout-9abd026" if deployed else "0000001"
            secret_names = [
                "database-url",
                "session-secret",
                "mcp-token-pepper",
                "metrics-token",
                "oidc-client-secret",
                "foundry-api-key",
                "openrouter-api-key",
            ]
            env = [
                {{"name": "ABDA_ENVIRONMENT", "value": "staging"}},
                {{"name": "ABDA_ENABLE_LLM", "value": "1"}},
                {{"name": "ABDA_AUTH_MODE", "value": "oidc"}},
                {{"name": "ABDA_AUTO_CREATE_DB", "value": "0"}},
                {{"name": "ABDA_PUBLIC_BASE_URL", "value": "https://{FQDN}"}},
                {{"name": "ABDA_TRUSTED_HOSTS", "value": "{FQDN}"}},
                {{"name": "ABDA_COOKIE_SECURE", "value": "1"}},
                {{"name": "ABDA_LLM_ALLOW_BYOK", "value": "1"}},
                {{"name": "ABDA_LLM_REQUIRE_AUTH", "value": "1"}},
                {{"name": "ABDA_TRIAL_ENABLED", "value": "false"}},
                {{"name": "ABDA_TRIAL_BUDGET_MICROUSD", "value": "500000000"}},
                {{"name": "ABDA_OPENROUTER_FAILOVER_ENABLED", "value": "false"}},
                {{"name": "ABDA_OPENROUTER_BUDGET_MICROUSD", "value": "500000000"}},
                {{"name": "ABDA_DATABASE_URL", "secretRef": "database-url"}},
                {{"name": "ABDA_SESSION_SECRET", "secretRef": "session-secret"}},
                {{"name": "ABDA_MCP_TOKEN_PEPPER", "secretRef": "mcp-token-pepper"}},
                {{"name": "ABDA_METRICS_TOKEN", "secretRef": "metrics-token"}},
                {{"name": "ABDA_OIDC_CLIENT_SECRET", "secretRef": "oidc-client-secret"}},
                {{"name": "AZURE_OPENAI_API_KEY", "secretRef": "foundry-api-key"}},
                {{"name": "OPENROUTER_API_KEY", "secretRef": "openrouter-api-key"}},
            ]
            probes = [
                {{
                    "type": probe_type,
                    "httpGet": {{
                        "path": path,
                        "port": 8000,
                        "scheme": "HTTP",
                        "httpHeaders": [{{"name": "Host", "value": "{FQDN}"}}],
                    }},
                }}
                for probe_type, path in (
                    ("Startup", "/health/live"),
                    ("Liveness", "/health/live"),
                    ("Readiness", "/health/ready"),
                )
            ]
            return {{
                "name": "abda-nl-stg-web",
                "location": "eastus2",
                "properties": {{
                    "environmentId": "/subscriptions/test/environments/abda-nl-stg-environment",
                    "workloadProfileName": "Consumption",
                    "provisioningState": "Succeeded",
                    "runningStatus": "Running",
                    "latestRevisionName": revision,
                    "latestReadyRevisionName": revision,
                    "configuration": {{
                        "activeRevisionsMode": "Single",
                        "ingress": {{
                            "fqdn": "{FQDN}",
                            "external": True,
                            "allowInsecure": False,
                            "targetPort": 8000,
                            "transport": "Auto",
                            "customDomains": [],
                            "traffic": [{{"latestRevision": True, "weight": 100}}],
                        }},
                        "secrets": [{{"name": name}} for name in secret_names],
                    }},
                    "template": {{
                        "revisionSuffix": suffix,
                        "terminationGracePeriodSeconds": 30,
                        "containers": [
                            {{
                                "name": "web",
                                "image": "ghcr.io/liu-hy/abda-nl@sha256:" + image,
                                "resources": {{"cpu": 0.5, "memory": "1Gi"}},
                                "env": env,
                                "probes": probes,
                            }}
                        ],
                        "scale": {{"minReplicas": 1, "maxReplicas": 3}},
                    }},
                }},
            }}

        if args[:3] == ["containerapp", "update", "--help"]:
            emit("--revision-suffix\\n" + "long Azure help output\\n" * 20000)
        elif args[:4] == ["containerapp", "secret", "list", "--help"]:
            emit("--show-values\\n" + "long Azure help output\\n" * 20000)
        elif args[:2] == ["account", "show"]:
            if "table" in args:
                emit("Name TenantId User State\\naccess test test Enabled")
            else:
                emit(
                    {{
                        "id": "00e62f6e-2174-40b2-b428-8ebfd7c2ac54",
                        "tenantId": "040f05eb-33ab-462f-af54-fb4bedb055ae",
                        "user": {{"name": "hliu2@cloudbank.org"}},
                        "state": "Enabled",
                    }}
                )
        elif args[:3] == ["deployment", "group", "show"]:
            query = args[args.index("--query") + 1]
            if query == "properties.provisioningState":
                emit("Succeeded")
            elif query == "properties.outputs":
                emit(
                    {{
                        "containerAppsEnvironmentName": {{"value": "abda-nl-stg-environment"}},
                        "migrationJobName": {{"value": "abda-nl-stg-migrate"}},
                        "expectedAppName": {{"value": "abda-nl-stg-web"}},
                        "postgresHost": {{"value": "abda-nl-stg-postgres-bgjhpbgw.postgres.database.azure.com"}},
                        "expectedPublicOrigin": {{"value": "https://{FQDN}"}},
                        "postgresDatabase": {{"value": "abda"}},
                        "postgresAdminLogin": {{"value": "abdaadmin"}},
                    }}
                )
            else:
                raise SystemExit(f"unexpected deployment query: {{query}}")
        elif args[:3] == ["containerapp", "env", "show"]:
            emit(
                {{
                    "name": "abda-nl-stg-environment",
                    "properties": {{"provisioningState": "Succeeded"}},
                }}
            )
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
            emit([{{"name": "abda-nl-stg-web"}}])
        elif args[:4] == ["containerapp", "job", "execution", "list"]:
            emit([{{"name": "migration-ok", "properties": {{"status": "Succeeded"}}}}])
        elif args[:2] == ["containerapp", "show"]:
            emit(app_document(marker.exists()))
        elif args[:3] == ["containerapp", "revision", "list"]:
            revisions = [
                {{
                    "name": "{OLD_REVISION}",
                    "properties": {{
                        "active": not marker.exists(),
                        "healthState": "Healthy",
                        "provisioningState": "Provisioned",
                    }},
                }}
            ]
            if marker.exists():
                revisions.append(
                    {{
                        "name": "{TARGET_REVISION}",
                        "properties": {{
                            "active": True,
                            "healthState": "Healthy",
                            "provisioningState": "Provisioned",
                        }},
                    }}
                )
            emit(revisions)
        elif args[:3] == ["containerapp", "revision", "show"]:
            if not marker.exists():
                raise SystemExit("target revision is not deployed")
            emit(
                {{
                    "name": "{TARGET_REVISION}",
                    "properties": {{
                        "active": True,
                        "healthState": "Healthy",
                        "provisioningState": "Provisioned",
                        "replicas": 1,
                    }},
                }}
            )
        elif args[:3] == ["containerapp", "replica", "list"]:
            if not marker.exists():
                raise SystemExit("target replica is not deployed")
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
        elif args[:2] == ["containerapp", "update"]:
            expected_image = "ghcr.io/liu-hy/abda-nl@sha256:{NEW_IMAGE}"
            if args[args.index("--image") + 1] != expected_image:
                raise SystemExit("unexpected target image")
            if args[args.index("--revision-suffix") + 1] != "logout-9abd026":
                raise SystemExit("unexpected revision suffix")
            marker.touch()
            emit({{}})
        elif args[:3] == ["containerapp", "secret", "list"]:
            secrets = {{
                "database-url": "postgresql-secret-value",
                "session-secret": "session-secret-12345678901234567890",
                "mcp-token-pepper": "mcp-token-pepper-1234567890123456",
                "metrics-token": "metrics-token-12345678901234567890",
                "oidc-client-secret": "oidc-client-secret-value",
                "foundry-api-key": "foundry-api-key-value",
                "openrouter-api-key": "openrouter-api-key-value",
            }}
            emit([{{"name": name, "value": value}} for name, value in secrets.items()])
        else:
            raise SystemExit(f"unexpected fake az command: {{args!r}}")
        """,
    )

    return fake_bin, az_log, deployed_marker


def _run_mocked_gate(
    tmp_path: Path,
    confirmation: str,
    *,
    already_deployed: bool = False,
) -> tuple[subprocess.CompletedProcess[str], str]:
    fake_bin, az_log, marker = _install_fake_commands(tmp_path)
    if already_deployed:
        marker.touch()
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "ABDA_TEST_SOURCE_ROOT": str(ROOT),
            "ABDA_TEST_AZ_LOG": str(az_log),
            "ABDA_TEST_DEPLOYED_MARKER": str(marker),
        }
    )
    result = subprocess.run(
        [str(GATE)],
        input=f"{confirmation}\n",
        check=False,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=environment,
        timeout=60,
    )
    combined = result.stdout + result.stderr
    for secret in (
        "session-secret-12345678901234567890",
        "mcp-token-pepper-1234567890123456",
        "metrics-token-12345678901234567890",
        "oidc-client-secret-value",
        "foundry-api-key-value",
        "openrouter-api-key-value",
    ):
        assert secret not in combined
    return result, az_log.read_text(encoding="utf-8")


def test_logout_image_gate_cancels_before_the_only_mutation(tmp_path):
    result, commands = _run_mocked_gate(tmp_path, "")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "deployment_phase: old" in result.stdout
    assert "Cancelled without changing Azure" in result.stdout
    assert "containerapp update --name" not in commands
    assert "containerapp job start" not in commands


def test_logout_image_gate_deploys_and_accepts_the_exact_target(tmp_path):
    result, commands = _run_mocked_gate(tmp_path, "DEPLOY_ABDA_LOGOUT_FIX")

    assert result.returncode == 0, result.stdout + result.stderr
    assert f"source_commit: {SOURCE_COMMIT}" in result.stdout
    assert f"image_digest: sha256:{NEW_IMAGE}" in result.stdout
    assert f"previous_revision: {OLD_REVISION}" in result.stdout
    assert f"application_revision: {TARGET_REVISION}" in result.stdout
    assert "generated_origin_acceptance: passed" in result.stdout
    assert "logout_contract_acceptance: passed" in result.stdout
    assert "result: LOGOUT_FIX_DEPLOYED_BROWSER_RETEST_REQUIRED" in result.stdout
    assert commands.count("containerapp update --name") == 1
    assert "containerapp job start" not in commands


def test_logout_image_gate_resumes_without_redeploying(tmp_path):
    result, commands = _run_mocked_gate(tmp_path, "", already_deployed=True)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "deployment_phase: target" in result.stdout
    assert "already submitted. Resuming verification" in result.stdout
    assert "containerapp update --name" not in commands
    assert "result: LOGOUT_FIX_DEPLOYED_BROWSER_RETEST_REQUIRED" in result.stdout
