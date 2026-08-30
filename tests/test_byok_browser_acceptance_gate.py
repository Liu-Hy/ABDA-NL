"""Contracts for the live public-browser BYOK acceptance gate."""

from __future__ import annotations

import json
import os
from pathlib import Path
import select as select_io
import shlex
import subprocess
import sys
import time

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    Base,
    EmergencyBudget,
    LLMUsageEvent,
    TrialGrant,
    User,
    utc_now,
)


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "deploy" / "azure" / "gate10-byok-browser-acceptance.sh"
EMAIL = "byok-gate@example.edu"
EXPECTED_REVISION = "abda-nl-stg-web--mcp-c55aa0d"
EXPECTED_IMAGE = (
    "ghcr.io/liu-hy/abda-nl@sha256:"
    "2df0bf98401adb6f72d1b930d83ab68bd2466de756b0bead3864f3d41d30b9d0"
)


def _runner_source() -> str:
    result = subprocess.run(
        [
            "bash",
            "-c",
            f"source {shlex.quote(str(GATE))}; abda_byok_runner_source",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    compile(result.stdout, "<byok-browser-acceptance>", "exec")
    return result.stdout


def _run_function(function: str, *arguments: Path | str) -> subprocess.CompletedProcess[str]:
    quoted = " ".join(shlex.quote(str(argument)) for argument in arguments)
    return subprocess.run(
        [
            "bash",
            "-c",
            (
                f"source {shlex.quote(str(GATE))}; "
                f"abda_byok_set_constants; {function} {quoted}"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def _application(*, revision: str = EXPECTED_REVISION) -> dict:
    environment = {
        "ABDA_ENVIRONMENT": "staging",
        "ABDA_AUTH_MODE": "oidc",
        "ABDA_PUBLIC_BASE_URL": "https://demo.abda-nl.org",
        "ABDA_LLM_ALLOW_BYOK": "1",
        "ABDA_LLM_REQUIRE_AUTH": "1",
        "ABDA_TRIAL_ENABLED": "True",
        "ABDA_TRIAL_MAX_USERS": "10",
        "ABDA_TRIAL_GRANT_MICROUSD": "5000000",
        "ABDA_TRIAL_BUDGET_MICROUSD": "50000000",
        "ABDA_OPENROUTER_FAILOVER_ENABLED": "False",
        "ABDA_OPENROUTER_BUDGET_MICROUSD": "500000000",
    }
    values = [{"name": name, "value": value} for name, value in environment.items()]
    values.extend(
        {"name": name, "secretRef": secret}
        for name, secret in {
            "ABDA_DATABASE_URL": "database-url",
            "ABDA_SESSION_SECRET": "session-secret",
            "ABDA_METRICS_TOKEN": "metrics-token",
            "ABDA_OIDC_CLIENT_SECRET": "oidc-client-secret",
            "AZURE_OPENAI_API_KEY": "foundry-api-key",
            "OPENROUTER_API_KEY": "openrouter-api-key",
        }.items()
    )
    return {
        "name": "abda-nl-stg-web",
        "properties": {
            "provisioningState": "Succeeded",
            "runningStatus": "Running",
            "latestRevisionName": revision,
            "latestReadyRevisionName": revision,
            "configuration": {
                "activeRevisionsMode": "Single",
                "ingress": {
                    "external": True,
                    "allowInsecure": False,
                    "targetPort": 8000,
                    "customDomains": [{"name": "demo.abda-nl.org"}],
                },
            },
            "template": {
                "containers": [
                    {
                        "name": "web",
                        "image": EXPECTED_IMAGE,
                        "env": values,
                    }
                ]
            },
        },
    }


def _public_config() -> dict:
    return {
        "llm_enabled": True,
        "llm_auth_required": True,
        "byok_enabled": True,
        "byok_keys_stored": False,
        "byok_providers": [
            {"id": "anthropic", "models": []},
            {"id": "openai", "models": []},
            {"id": "google", "models": []},
            {
                "id": "openrouter",
                "models": [{"id": "gemini-3.7-flash"}],
            },
        ],
    }


def _seed_database(path: Path) -> str:
    engine = create_engine(f"sqlite+pysqlite:///{path}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = utc_now()
    with factory() as session:
        user = User(
            email=EMAIL,
            email_verified=True,
            display_name="BYOK Gate",
            created_at=now,
            updated_at=now,
            last_login_at=now,
        )
        session.add(user)
        session.flush()
        session.add(
            TrialGrant(
                user_id=user.id,
                program_key="global",
                granted_microusd=5_000_000,
                spent_microusd=60_775,
                reserved_microusd=0,
                activated_at=now,
            )
        )
        session.add(
            EmergencyBudget(
                key="openrouter",
                enabled=False,
                hard_limit_microusd=500_000_000,
                spent_microusd=149,
                reserved_microusd=0,
                updated_at=now,
            )
        )
        session.commit()
        user_id = user.id
    engine.dispose()
    return user_id


def _runner_environment(database: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "ABDA_DATABASE_URL": f"sqlite+pysqlite:///{database}",
            "ABDA_ENVIRONMENT": "test",
            "ABDA_AUTH_MODE": "dev",
            "ABDA_AUTO_CREATE_DB": "0",
            "ABDA_SESSION_SECRET": "s" * 48,
            "ABDA_MCP_TOKEN_PEPPER": "p" * 48,
        }
    )
    return environment


def _wait_for_ready(process: subprocess.Popen[str]) -> str:
    assert process.stdout is not None
    lines: list[str] = []
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        ready, _, _ = select_io.select([process.stdout], [], [], 0.25)
        if not ready:
            continue
        line = process.stdout.readline()
        if not line:
            break
        lines.append(line)
        if "browser_test_ready: true" in line:
            return "".join(lines)
    process.kill()
    raise AssertionError("embedded BYOK runner did not reach browser readiness")


def test_gate_is_read_only_secret_safe_and_syntactically_valid():
    assert GATE.stat().st_mode & 0o111
    subprocess.run(["bash", "-n", str(GATE)], check=True)
    source = GATE.read_text(encoding="utf-8")
    runner = _runner_source()

    for expected in (
        "BYOK_OPENROUTER_CALL_CONFIRMED",
        "BYOK_RELOAD_CLEAR_CONFIRMED",
        "BYOK_SIGNOUT_CLEAR_CONFIRMED",
        "LIVE_BYOK_PRIVACY_AND_ACCOUNTING_ACCEPTANCE_VERIFIED",
        EXPECTED_REVISION,
        "provider_key_entered_in_shell: false",
        "raw_log_messages_printed: false",
    ):
        assert expected in source
    assert source.count("\n  az containerapp exec ") == 2
    for forbidden in (
        "az containerapp update",
        "az containerapp delete",
        "az containerapp secret",
        "az group delete",
        "read -r -s -p 'OpenRouter",
    ):
        assert forbidden not in source
    assert "getpass.getpass" in runner
    assert "provider key" not in runner.lower()
    assert "openrouter_api_key" not in runner.lower()
    assert "\N{EM DASH}" not in source and "\N{EN DASH}" not in source


def test_preflights_accept_only_the_approved_app_and_public_config(tmp_path: Path):
    valid_app = tmp_path / "app.json"
    valid_app.write_text(json.dumps(_application()), encoding="utf-8")
    result = _run_function("abda_byok_validate_app", valid_app)
    assert result.returncode == 0, result.stderr

    wrong_app = tmp_path / "wrong-app.json"
    wrong_app.write_text(
        json.dumps(_application(revision="abda-nl-stg-web--other")),
        encoding="utf-8",
    )
    result = _run_function("abda_byok_validate_app", wrong_app)
    assert result.returncode != 0
    assert "application revision changed" in result.stderr

    valid_config = tmp_path / "config.json"
    valid_config.write_text(json.dumps(_public_config()), encoding="utf-8")
    result = _run_function("abda_byok_validate_config", valid_config)
    assert result.returncode == 0, result.stderr

    invalid = _public_config()
    invalid["byok_keys_stored"] = True
    invalid_config = tmp_path / "invalid-config.json"
    invalid_config.write_text(json.dumps(invalid), encoding="utf-8")
    result = _run_function("abda_byok_validate_config", invalid_config)
    assert result.returncode != 0
    assert "storage boundary changed" in result.stderr


def test_embedded_runner_proves_byok_accounting_and_private_state_boundaries(
    tmp_path: Path,
):
    database = tmp_path / "byok.sqlite3"
    user_id = _seed_database(database)
    runner = _runner_source()
    process = subprocess.Popen(
        [sys.executable, "-u", "-c", runner],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=ROOT,
        env=_runner_environment(database),
    )
    assert process.stdin is not None
    process.stdin.write(f"{EMAIL}\n")
    process.stdin.flush()
    prefix = _wait_for_ready(process)

    engine = create_engine(f"sqlite+pysqlite:///{database}")
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        session.add(
            LLMUsageEvent(
                request_id="byok-browser-request",
                user_id=user_id,
                provider="openrouter",
                route="byok:openrouter:gemini-3.7-flash",
                model="gemini-3.7-flash",
                billing_source="byok",
                request_kind="chat",
                status="succeeded",
                input_tokens=120,
                output_tokens=24,
                cost_microusd=321,
                latency_ms=20,
            )
        )
        session.commit()
    engine.dispose()

    process.stdin.write(
        "BYOK_OPENROUTER_CALL_CONFIRMED\n"
        "BYOK_RELOAD_CLEAR_CONFIRMED\n"
        "BYOK_SIGNOUT_CLEAR_CONFIRMED\n"
    )
    process.stdin.flush()
    process.stdin.close()
    process.stdin = None
    stdout, stderr = process.communicate(timeout=10)
    output = prefix + stdout
    assert process.returncode == 0, stderr
    assert "BYOK_BROWSER_AND_DATABASE_ACCEPTANCE_VERIFIED_LOG_AUDIT_REQUIRED" in output
    assert "trial_ledger_unchanged: true" in output
    assert "openrouter_emergency_ledger_unchanged: true" in output
    assert "private_project_state_unchanged: true" in output
    assert "settled_byok_cost_microusd: 321" in output
    assert EMAIL not in output
