"""Contracts for the final public trial and outage-fallback promotion gate."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shlex
import subprocess
import textwrap

import pytest


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "deploy" / "azure" / "gate12-public-budget-promotion.sh"
APP = "abda-nl-stg-web"
GENERATED_HOST = "abda-nl-stg-web.blueforest-da494f7c.eastus2.azurecontainerapps.io"
CUSTOM_HOST = "demo.abda-nl.org"
PILOT_REVISION = "abda-nl-stg-web--restore-51702e1"
PUBLIC_REVISION = "abda-nl-stg-web--public-100-51702e1"
IMAGE = (
    "ghcr.io/liu-hy/abda-nl@sha256:"
    "a0b3ba24aff06ecf461f86547131d86451c541e306a7ecfc278f280fcef5c0bc"
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
                f"abda_promotion_set_constants; {function} {quoted}"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def _environment(*, public: bool) -> list[dict]:
    values = {
        "ABDA_ENVIRONMENT": "staging",
        "ABDA_ENABLE_LLM": "1",
        "ABDA_AUTH_MODE": "oidc",
        "ABDA_AUTO_CREATE_DB": "0",
        "ABDA_PUBLIC_BASE_URL": f"https://{CUSTOM_HOST}",
        "ABDA_TRUSTED_HOSTS": f"{GENERATED_HOST},{CUSTOM_HOST}",
        "ABDA_SESSION_COOKIE": "__Host-abda_session",
        "ABDA_COOKIE_SECURE": "1",
        "ABDA_TRIAL_ENABLED": "true",
        "ABDA_TRIAL_MAX_USERS": "100" if public else "10",
        "ABDA_TRIAL_GRANT_MICROUSD": "5000000",
        "ABDA_TRIAL_BUDGET_MICROUSD": "500000000" if public else "50000000",
        "ABDA_LLM_BACKEND": "claude",
        "ABDA_CLAUDE_PROVIDER": "foundry",
        "ABDA_LLM_DEFAULT_PROFILE": "balanced",
        "ABDA_LLM_ALLOW_BYOK": "1",
        "ABDA_LLM_REQUIRE_AUTH": "1",
        "ABDA_OPENROUTER_FAILOVER_ENABLED": "true" if public else "false",
        "ABDA_OPENROUTER_BUDGET_MICROUSD": "500000000",
        "ABDA_OPENROUTER_BUDGET_ACK": "",
        "ABDA_PROXY_MODE": "azure-container-apps",
        "ABDA_ABUSE_PROTECTION_ENABLED": "1",
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


def _app(*, phase: str) -> dict:
    if phase == "pilot":
        public = False
        latest = ready = PILOT_REVISION
        suffix = "restore-51702e1"
    elif phase == "public":
        public = True
        latest = ready = PUBLIC_REVISION
        suffix = "public-100-51702e1"
    elif phase == "public_pending":
        public = True
        latest, ready = PUBLIC_REVISION, PILOT_REVISION
        suffix = "public-100-51702e1"
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
            "workloadProfileName": "Consumption",
            "configuration": {
                "activeRevisionsMode": "Single",
                "secrets": [{"name": name} for name in secret_names],
                "ingress": {
                    "fqdn": GENERATED_HOST,
                    "external": True,
                    "allowInsecure": False,
                    "targetPort": 8000,
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
                "scale": {"minReplicas": 1, "maxReplicas": 3},
                "containers": [
                    {
                        "name": "web",
                        "image": IMAGE,
                        "resources": {"cpu": 0.5, "memory": "1Gi"},
                        "env": _environment(public=public),
                        "probes": probes,
                    }
                ],
            },
        },
    }


def _metrics(*, public: bool) -> str:
    return "\n".join(
        (
            "abda_trial_enabled 1",
            f"abda_trial_max_users {100 if public else 10}",
            "abda_trial_grant_microusd 5000000",
            f"abda_trial_budget_microusd {500000000 if public else 50000000}",
            "abda_trial_activations 1",
            "abda_trial_allocated_microusd 5000000",
            "abda_trial_spent_microusd 60775",
            "abda_trial_reserved_microusd 0",
            "abda_trial_uncertain_charged_reservations 0",
            "abda_trial_uncertain_charged_microusd 0",
            f"abda_openrouter_enabled {1 if public else 0}",
            "abda_openrouter_budget_microusd 500000000",
            "abda_openrouter_spent_microusd 149",
            "abda_openrouter_reserved_microusd 0",
            "abda_openrouter_uncertain_charged_reservations 0",
            "abda_openrouter_uncertain_charged_microusd 0",
        )
    )


def _write_executable(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    path.chmod(0o700)


def _install_fakes(tmp_path: Path) -> tuple[dict[str, str], Path]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    state = tmp_path / "state"
    state.write_text("pilot", encoding="utf-8")
    az_log = tmp_path / "az.log"
    pilot_app = tmp_path / "pilot.json"
    public_app = tmp_path / "public.json"
    pilot_app.write_text(json.dumps(_app(phase="pilot")), encoding="utf-8")
    public_app.write_text(json.dumps(_app(phase="public")), encoding="utf-8")

    _write_executable(
        fake_bin / "az",
        """
        #!/usr/bin/env python3
        import json
        import os
        from pathlib import Path
        import sys

        args = sys.argv[1:]
        state = Path(os.environ["ABDA_TEST_STATE"])
        with Path(os.environ["ABDA_TEST_AZ_LOG"]).open("a", encoding="utf-8") as handle:
            handle.write(" ".join(args) + "\\n")

        def emit(value):
            if "--output" in args and args[args.index("--output") + 1] == "none":
                return
            print(value if isinstance(value, str) else json.dumps(value))

        if "--help" in args:
            if args[:2] == ["containerapp", "update"]:
                print("--set-env-vars\\n--revision-suffix")
            elif args[:3] == ["containerapp", "secret", "list"]:
                print("--show-values")
            else:
                raise SystemExit(f"unexpected help command: {args!r}")
        elif args[:2] == ["account", "show"]:
            if "table" in args:
                emit("Name TenantId User State\\naccess test test Enabled")
            else:
                emit(
                    {
                        "id": "00e62f6e-2174-40b2-b428-8ebfd7c2ac54",
                        "tenantId": "040f05eb-33ab-462f-af54-fb4bedb055ae",
                        "user": {"name": "hliu2@cloudbank.org"},
                        "state": "Enabled",
                    }
                )
        elif args[:2] == ["containerapp", "show"]:
            source = Path(
                os.environ[
                    "ABDA_TEST_PUBLIC_APP"
                    if state.read_text(encoding="utf-8") == "public"
                    else "ABDA_TEST_PILOT_APP"
                ]
            )
            emit(json.loads(source.read_text(encoding="utf-8")))
        elif args[:3] == ["containerapp", "revision", "show"]:
            revision = args[args.index("--revision") + 1]
            emit(
                {
                    "name": revision,
                    "properties": {
                        "active": True,
                        "healthState": "Healthy",
                        "provisioningState": "Provisioned",
                    },
                }
            )
        elif args[:3] == ["containerapp", "replica", "list"]:
            emit(
                [
                    {
                        "name": "replica-1",
                        "properties": {
                            "runningState": "Running",
                            "containers": [{"name": "web", "ready": True}],
                        },
                    }
                ]
            )
        elif args[:3] == ["containerapp", "secret", "list"]:
            names = [
                "database-url",
                "session-secret",
                "mcp-token-pepper",
                "metrics-token",
                "oidc-client-secret",
                "foundry-api-key",
                "openrouter-api-key",
            ]
            emit(
                [
                    {
                        "name": name,
                        "value": "m" * 48 if name == "metrics-token" else "secret",
                    }
                    for name in names
                ]
            )
        elif args[:2] == ["containerapp", "update"]:
            required = {
                "ABDA_TRIAL_MAX_USERS=100",
                "ABDA_TRIAL_BUDGET_MICROUSD=500000000",
                "ABDA_OPENROUTER_FAILOVER_ENABLED=true",
            }
            if not required.issubset(args):
                raise SystemExit(f"public update values changed: {args!r}")
            if args[args.index("--revision-suffix") + 1] != "public-100-51702e1":
                raise SystemExit("public revision suffix changed")
            state.write_text("public", encoding="utf-8")
        else:
            raise SystemExit(f"unexpected fake az command: {args!r}")
        """,
    )
    _write_executable(
        fake_bin / "curl",
        """
        #!/usr/bin/env python3
        import json
        import os
        from pathlib import Path
        import sys

        args = sys.argv[1:]
        urls = [value for value in args if value.startswith("https://")]
        if not urls:
            raise SystemExit(f"fake curl received no HTTPS URL: {args!r}")
        url = urls[-1]

        def option(name):
            return args[args.index(name) + 1] if name in args else None

        def output(value):
            target = option("--output")
            if target:
                Path(target).write_text(value, encoding="utf-8")

        if url.endswith("/health/ready"):
            output(json.dumps({"status": "ready"}))
        elif url.endswith("/config"):
            output(
                json.dumps(
                    {
                        "llm_enabled": True,
                        "llm_auth_required": True,
                        "byok_enabled": True,
                        "byok_keys_stored": False,
                        "default_profile": "balanced",
                        "profiles": [{"id": "balanced"}],
                    }
                )
            )
        elif url.endswith("/internal/metrics") and "--config" not in args:
            output(json.dumps({"detail": "Not authenticated"}))
            print("401", end="")
        elif url.endswith("/internal/metrics"):
            public = Path(os.environ["ABDA_TEST_STATE"]).read_text(encoding="utf-8") == "public"
            output(
                os.environ[
                    "ABDA_TEST_PUBLIC_METRICS" if public else "ABDA_TEST_PILOT_METRICS"
                ]
            )
        else:
            raise SystemExit(f"unexpected fake curl command: {args!r}")
        """,
    )

    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "ABDA_TEST_STATE": str(state),
            "ABDA_TEST_AZ_LOG": str(az_log),
            "ABDA_TEST_PILOT_APP": str(pilot_app),
            "ABDA_TEST_PUBLIC_APP": str(public_app),
            "ABDA_TEST_PILOT_METRICS": _metrics(public=False),
            "ABDA_TEST_PUBLIC_METRICS": _metrics(public=True),
        }
    )
    return environment, az_log


def test_gate_has_valid_syntax_and_one_three_setting_mutation():
    assert GATE.stat().st_mode & 0o111
    subprocess.run(["bash", "-n", str(GATE)], check=True)
    source = GATE.read_text(encoding="utf-8")
    for expected in (
        "ABDA_PUBLIC_MAX_USERS='100'",
        "ABDA_PUBLIC_TRIAL_BUDGET_MICROUSD='500000000'",
        "ABDA_OPENROUTER_BUDGET_MICROUSD='500000000'",
        "ABDA_OPENROUTER_FAILOVER_ENABLED=true",
        "PROMOTE_ABDA_PUBLIC_BUDGETS",
        "PUBLIC_BUDGETS_AND_OUTAGE_FALLBACK_PROMOTED",
    ):
        assert expected in source
    assert source.count("\n    az containerapp update ") == 1
    assert source.count("--set-env-vars") == 2
    assert "az containerapp secret set" not in source
    assert "az deployment group create" not in source
    assert "az containerapp delete" not in source
    assert "az group delete" not in source
    assert "–" not in source and "—" not in source


@pytest.mark.parametrize("phase", ["pilot", "public", "public_pending"])
def test_phase_accepts_only_reviewed_states(tmp_path: Path, phase: str):
    path = tmp_path / f"{phase}.json"
    path.write_text(json.dumps(_app(phase=phase)), encoding="utf-8")
    result = _run_function("abda_promotion_phase", path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == phase


def test_phase_rejects_unreviewed_budget_or_fallback(tmp_path: Path):
    app = _app(phase="pilot")
    environment = app["properties"]["template"]["containers"][0]["env"]
    for item in environment:
        if item.get("name") == "ABDA_OPENROUTER_FAILOVER_ENABLED":
            item["value"] = "true"
    path = tmp_path / "mixed.json"
    path.write_text(json.dumps(app), encoding="utf-8")
    result = _run_function("abda_promotion_phase", path)
    assert result.returncode != 0
    assert "outside the reviewed" in result.stderr


def test_metrics_accept_idle_pilot_and_public_without_changing_totals(tmp_path: Path):
    pilot = tmp_path / "pilot.metrics"
    public = tmp_path / "public.metrics"
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    pilot.write_text(_metrics(public=False), encoding="utf-8")
    public.write_text(_metrics(public=True), encoding="utf-8")
    result = _run_function("abda_promotion_validate_metrics", pilot, "pilot", before)
    assert result.returncode == 0, result.stderr
    result = _run_function("abda_promotion_validate_metrics", public, "public", after)
    assert result.returncode == 0, result.stderr
    result = _run_function("abda_promotion_compare_metrics", before, after)
    assert result.returncode == 0, result.stderr

    changed = json.loads(after.read_text(encoding="utf-8"))
    changed["openrouter_spent_microusd"] += 1
    after.write_text(json.dumps(changed), encoding="utf-8")
    result = _run_function("abda_promotion_compare_metrics", before, after)
    assert result.returncode != 0


def test_full_gate_changes_only_reviewed_values_and_is_resume_safe(tmp_path: Path):
    environment, az_log = _install_fakes(tmp_path)
    first = subprocess.run(
        ["bash", str(GATE)],
        input="PROMOTE_ABDA_PUBLIC_BUDGETS\n",
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert first.returncode == 0, first.stderr
    assert "PUBLIC_BUDGETS_AND_OUTAGE_FALLBACK_PROMOTED" in first.stdout
    log_after_first = az_log.read_text(encoding="utf-8")
    assert log_after_first.count("containerapp update") == 2
    assert "ABDA_TRIAL_MAX_USERS=100" in log_after_first
    assert "ABDA_TRIAL_BUDGET_MICROUSD=500000000" in log_after_first
    assert "ABDA_OPENROUTER_FAILOVER_ENABLED=true" in log_after_first

    second = subprocess.run(
        ["bash", str(GATE)],
        input="",
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert second.returncode == 0, second.stderr
    assert "already active" in second.stdout
    assert "PUBLIC_BUDGETS_AND_OUTAGE_FALLBACK_PROMOTED" in second.stdout
    assert az_log.read_text(encoding="utf-8").count("containerapp update") == 3


def test_compare_update_rejects_an_unrelated_change(tmp_path: Path):
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    before.write_text(json.dumps(_app(phase="pilot")), encoding="utf-8")
    accepted = _app(phase="public")
    after.write_text(json.dumps(accepted), encoding="utf-8")
    result = _run_function("abda_promotion_compare_update", before, after)
    assert result.returncode == 0, result.stderr

    changed = copy.deepcopy(accepted)
    changed["properties"]["template"]["scale"]["maxReplicas"] = 4
    after.write_text(json.dumps(changed), encoding="utf-8")
    result = _run_function("abda_promotion_compare_update", before, after)
    assert result.returncode != 0
