"""Contracts for the bounded Azure funded-trial pilot gate."""

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
GATE = ROOT / "deploy" / "azure" / "gate5-trial-pilot.sh"
APP = "abda-nl-stg-web"
GENERATED_HOST = "abda-nl-stg-web.blueforest-da494f7c.eastus2.azurecontainerapps.io"
CUSTOM_HOST = "demo.abda-nl.org"
OLD_REVISION = "abda-nl-stg-web--0000002"
TARGET_REVISION = "abda-nl-stg-web--trial-pilot-v1"
IMAGE = (
    "ghcr.io/liu-hy/abda-nl@sha256:71f759c7bbfe25cc2ae974f006b8fed853ef87e5db260fc875fa3f50257739f9"
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
            f"source {shlex.quote(str(GATE))}; abda_trial_set_constants; {function} {quoted}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def _environment(*, enabled: bool, max_users: int, budget: int) -> list[dict]:
    values = {
        "ABDA_ENVIRONMENT": "staging",
        "ABDA_ENABLE_LLM": "1",
        "ABDA_AUTH_MODE": "oidc",
        "ABDA_AUTO_CREATE_DB": "0",
        "ABDA_PUBLIC_BASE_URL": f"https://{CUSTOM_HOST}",
        "ABDA_TRUSTED_HOSTS": f"{GENERATED_HOST},{CUSTOM_HOST}",
        "ABDA_SESSION_COOKIE": "__Host-abda_session",
        "ABDA_COOKIE_SECURE": "1",
        "ABDA_TRIAL_ENABLED": str(enabled).lower(),
        "ABDA_TRIAL_MAX_USERS": str(max_users),
        "ABDA_TRIAL_GRANT_MICROUSD": "5000000",
        "ABDA_TRIAL_BUDGET_MICROUSD": str(budget),
        "ABDA_LLM_BACKEND": "claude",
        "ABDA_CLAUDE_PROVIDER": "foundry",
        "ABDA_LLM_DEFAULT_PROFILE": "balanced",
        "ABDA_LLM_ALLOW_BYOK": "1",
        "ABDA_LLM_REQUIRE_AUTH": "1",
        "ABDA_OPENROUTER_FAILOVER_ENABLED": "False",
        "ABDA_OPENROUTER_BUDGET_MICROUSD": "500000000",
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
    if phase == "disabled":
        enabled, max_users, budget = False, 100, 500_000_000
        latest = ready = OLD_REVISION
        suffix = "0000002"
    elif phase == "pilot":
        enabled, max_users, budget = True, 10, 50_000_000
        latest = ready = TARGET_REVISION
        suffix = "trial-pilot-v1"
    elif phase == "pilot_pending":
        enabled, max_users, budget = True, 10, 50_000_000
        latest, ready = TARGET_REVISION, OLD_REVISION
        suffix = "trial-pilot-v1"
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
                        "env": _environment(enabled=enabled, max_users=max_users, budget=budget),
                        "probes": probes,
                    }
                ],
            },
        },
    }


def _metrics(*, enabled: bool, activations: int = 0, spent: int = 0) -> str:
    max_users = 10 if enabled else 100
    budget = 50_000_000 if enabled else 500_000_000
    allocated = activations * 5_000_000
    return "\n".join(
        (
            f"abda_trial_enabled {int(enabled)}",
            f"abda_trial_max_users {max_users}",
            "abda_trial_grant_microusd 5000000",
            f"abda_trial_budget_microusd {budget}",
            f"abda_trial_activations {activations}",
            f"abda_trial_allocated_microusd {allocated}",
            f"abda_trial_spent_microusd {spent}",
            "abda_trial_reserved_microusd 0",
            "abda_trial_uncertain_charged_reservations 0",
            "abda_trial_uncertain_charged_microusd 0",
            "abda_openrouter_enabled 0",
            "abda_openrouter_budget_microusd 500000000",
            "abda_openrouter_spent_microusd 0",
            "abda_openrouter_reserved_microusd 0",
            "abda_openrouter_uncertain_charged_reservations 0",
            "abda_openrouter_uncertain_charged_microusd 0",
        )
    )


def _write_executable(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    path.chmod(0o700)


def _install_main_fakes(tmp_path: Path) -> tuple[dict[str, str], Path, Path]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    state_path = tmp_path / "state"
    state_path.write_text("disabled", encoding="utf-8")
    az_log = tmp_path / "az.log"
    disabled_app = tmp_path / "disabled-app.json"
    pilot_app = tmp_path / "pilot-app.json"
    disabled_app.write_text(json.dumps(_app(phase="disabled")), encoding="utf-8")
    pilot_app.write_text(json.dumps(_app(phase="pilot")), encoding="utf-8")

    _write_executable(
        fake_bin / "az",
        """
        #!/usr/bin/env python3
        import json
        import os
        from pathlib import Path
        import sys

        args = sys.argv[1:]
        state_path = Path(os.environ["ABDA_TEST_STATE"])
        log_path = Path(os.environ["ABDA_TEST_AZ_LOG"])
        with log_path.open("a", encoding="utf-8") as handle:
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
                    "ABDA_TEST_PILOT_APP"
                    if state_path.read_text(encoding="utf-8") == "pilot"
                    else "ABDA_TEST_DISABLED_APP"
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
                "ABDA_TRIAL_ENABLED=true",
                "ABDA_TRIAL_MAX_USERS=10",
                "ABDA_TRIAL_BUDGET_MICROUSD=50000000",
            }
            if not required.issubset(args):
                raise SystemExit(f"trial update values changed: {args!r}")
            if args[args.index("--revision-suffix") + 1] != "trial-pilot-v1":
                raise SystemExit("trial revision suffix changed")
            state_path.write_text("pilot", encoding="utf-8")
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
            enabled = Path(os.environ["ABDA_TEST_STATE"]).read_text(encoding="utf-8") == "pilot"
            output(
                os.environ[
                    "ABDA_TEST_PILOT_METRICS"
                    if enabled
                    else "ABDA_TEST_DISABLED_METRICS"
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
            "ABDA_TEST_STATE": str(state_path),
            "ABDA_TEST_AZ_LOG": str(az_log),
            "ABDA_TEST_DISABLED_APP": str(disabled_app),
            "ABDA_TEST_PILOT_APP": str(pilot_app),
            "ABDA_TEST_DISABLED_METRICS": _metrics(enabled=False),
            "ABDA_TEST_PILOT_METRICS": _metrics(enabled=True),
        }
    )
    return environment, state_path, az_log


def test_trial_pilot_gate_has_valid_syntax_and_one_narrow_mutation():
    assert GATE.stat().st_mode & 0o111
    subprocess.run(["bash", "-n", str(GATE)], check=True)
    source = GATE.read_text(encoding="utf-8")

    for expected in (
        "ABDA_TRIAL_ENABLED=true",
        "ABDA_PILOT_MAX_USERS='10'",
        "ABDA_PILOT_BUDGET_MICROUSD='50000000'",
        "ENABLE_ABDA_TRIAL_PILOT",
        "TRIAL_PILOT_ENABLED_BROWSER_MODEL_TEST_REQUIRED",
        "TRIAL_PILOT_ACCOUNTING_VERIFIED",
    ):
        assert expected in source
    assert source.count("az containerapp update") == 2
    assert source.count("--set-env-vars") == 2
    assert "az deployment group create" not in source
    assert "az containerapp secret set" not in source
    assert "az containerapp job start" not in source
    assert "az containerapp delete" not in source
    assert "az group delete" not in source
    assert "read -r -s" not in source
    assert '--header "Authorization: Bearer' not in source
    assert '--config "$ABDA_TRIAL_ROOT/metrics-curl-config"' in source
    assert "set +x" in source
    assert "set -x" not in source


@pytest.mark.parametrize("phase", ["disabled", "pilot", "pilot_pending"])
def test_trial_phase_accepts_only_reviewed_states(tmp_path: Path, phase: str):
    app_path = tmp_path / "app.json"
    app_path.write_text(json.dumps(_app(phase=phase)), encoding="utf-8")
    result = _run_function("abda_trial_phase", app_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == phase


def test_trial_phase_rejects_an_unreviewed_budget(tmp_path: Path):
    app = _app(phase="pilot")
    environment = app["properties"]["template"]["containers"][0]["env"]
    next(item for item in environment if item["name"] == "ABDA_TRIAL_BUDGET_MICROUSD")["value"] = (
        "500000000"
    )
    app_path = tmp_path / "app.json"
    app_path.write_text(json.dumps(app), encoding="utf-8")
    result = _run_function("abda_trial_phase", app_path)
    assert result.returncode != 0
    assert "outside the reviewed disabled or pilot state" in result.stderr


def test_trial_phase_rejects_enabled_openrouter(tmp_path: Path):
    app = _app(phase="disabled")
    environment = app["properties"]["template"]["containers"][0]["env"]
    next(item for item in environment if item["name"] == "ABDA_OPENROUTER_FAILOVER_ENABLED")[
        "value"
    ] = "True"
    app_path = tmp_path / "app.json"
    app_path.write_text(json.dumps(app), encoding="utf-8")
    result = _run_function("abda_trial_phase", app_path)
    assert result.returncode != 0
    assert "ABDA_OPENROUTER_FAILOVER_ENABLED changed" in result.stderr


@pytest.mark.parametrize(
    ("enabled", "activations", "spent", "expected_state"),
    [
        (False, 0, 0, "disabled_empty"),
        (True, 0, 0, "unused"),
        (True, 1, 0, "activated"),
        (True, 1, 125, "used"),
    ],
)
def test_trial_metrics_reconcile_caps_and_usage(
    tmp_path: Path,
    enabled: bool,
    activations: int,
    spent: int,
    expected_state: str,
):
    metrics_path = tmp_path / "metrics.txt"
    state_path = tmp_path / "state.txt"
    metrics_path.write_text(
        _metrics(enabled=enabled, activations=activations, spent=spent),
        encoding="utf-8",
    )
    result = _run_function(
        "abda_trial_validate_metrics",
        metrics_path,
        "pilot" if enabled else "disabled",
        state_path,
    )
    assert result.returncode == 0, result.stderr
    assert state_path.read_text(encoding="utf-8").strip() == expected_state


def test_trial_metrics_enforce_the_ten_user_boundary(tmp_path: Path):
    metrics_path = tmp_path / "metrics.txt"
    state_path = tmp_path / "state.txt"
    metrics_path.write_text(_metrics(enabled=True, activations=10, spent=1), encoding="utf-8")
    accepted = _run_function("abda_trial_validate_metrics", metrics_path, "pilot", state_path)
    assert accepted.returncode == 0, accepted.stderr

    metrics_path.write_text(_metrics(enabled=True, activations=11, spent=1), encoding="utf-8")
    rejected = _run_function("abda_trial_validate_metrics", metrics_path, "pilot", state_path)
    assert rejected.returncode != 0
    assert "allocations do not reconcile" in rejected.stderr


def test_trial_update_comparison_allows_only_three_trial_values(tmp_path: Path):
    before = _app(phase="disabled")
    after = _app(phase="pilot")
    before_path = tmp_path / "before.json"
    after_path = tmp_path / "after.json"
    before_path.write_text(json.dumps(before), encoding="utf-8")
    after_path.write_text(json.dumps(after), encoding="utf-8")

    accepted = _run_function("abda_trial_compare_update", before_path, after_path)
    assert accepted.returncode == 0, accepted.stderr

    changed = copy.deepcopy(after)
    changed["properties"]["template"]["containers"][0]["image"] = "example.invalid/drift"
    after_path.write_text(json.dumps(changed), encoding="utf-8")
    rejected = _run_function("abda_trial_compare_update", before_path, after_path)
    assert rejected.returncode != 0
    assert "outside the three reviewed trial values changed" in rejected.stderr


def test_trial_gate_cancellation_runs_complete_read_only_preflight(tmp_path: Path):
    environment, state_path, az_log = _install_main_fakes(tmp_path)
    result = subprocess.run(
        [str(GATE)],
        input="\n",
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert "deployment_phase: disabled" in result.stdout
    assert "Cancelled without changing Azure." in result.stdout
    assert state_path.read_text(encoding="utf-8") == "disabled"
    update_commands = [
        line
        for line in az_log.read_text(encoding="utf-8").splitlines()
        if line.startswith("containerapp update")
    ]
    assert update_commands == ["containerapp update --help"]


def test_trial_gate_full_mocked_rollout_changes_only_the_three_caps(tmp_path: Path):
    environment, state_path, az_log = _install_main_fakes(tmp_path)
    result = subprocess.run(
        [str(GATE)],
        input="ENABLE_ABDA_TRIAL_PILOT\n",
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert "m" * 48 not in result.stdout + result.stderr
    assert state_path.read_text(encoding="utf-8") == "pilot"
    assert "trial_max_users: 10" in result.stdout
    assert "trial_budget_microusd: 50000000" in result.stdout
    assert "openrouter_failover_enabled: false" in result.stdout
    assert "TRIAL_PILOT_ENABLED_BROWSER_MODEL_TEST_REQUIRED" in result.stdout
    update_commands = [
        line
        for line in az_log.read_text(encoding="utf-8").splitlines()
        if line.startswith("containerapp update") and "--help" not in line
    ]
    assert len(update_commands) == 1
    assert "ABDA_TRIAL_ENABLED=true" in update_commands[0]
    assert "ABDA_TRIAL_MAX_USERS=10" in update_commands[0]
    assert "ABDA_TRIAL_BUDGET_MICROUSD=50000000" in update_commands[0]
