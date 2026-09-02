"""Contracts for the live disposable-account privacy acceptance gate."""

from __future__ import annotations

from datetime import timedelta
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    Base,
    Identity,
    MCPAccessToken,
    Project,
    ShareLink,
    User,
    utc_now,
)


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "deploy" / "azure" / "gate11-privacy-acceptance.sh"
EMAIL = "privacy-gate@example.edu"
EXPECTED_REVISION = "abda-nl-stg-web--harden-c173dd5"
EXPECTED_IMAGE = (
    "ghcr.io/liu-hy/abda-nl@sha256:"
    "ecf7531064fe6f86d3d647e9f0239bfbe5e082d71c5fcdd5e7e7fb91e9b32a64"
)


def _runner_source() -> str:
    result = subprocess.run(
        [
            "bash",
            "-c",
            f"source {shlex.quote(str(GATE))}; abda_privacy_runner_source",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    compile(result.stdout, "<privacy-acceptance>", "exec")
    return result.stdout


def _run_function(function: str, *arguments: Path | str) -> subprocess.CompletedProcess[str]:
    quoted = " ".join(shlex.quote(str(argument)) for argument in arguments)
    return subprocess.run(
        [
            "bash",
            "-c",
            (
                f"source {shlex.quote(str(GATE))}; "
                f"abda_privacy_set_constants; {function} {quoted}"
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
        "ABDA_TRIAL_ENABLED": "True",
        "ABDA_TRIAL_MAX_USERS": "10",
        "ABDA_TRIAL_GRANT_MICROUSD": "5000000",
        "ABDA_TRIAL_BUDGET_MICROUSD": "50000000",
        "ABDA_OPENROUTER_FAILOVER_ENABLED": "False",
        "ABDA_OPENROUTER_BUDGET_MICROUSD": "500000000",
    }
    values = [{"name": name, "value": value} for name, value in environment.items()]
    values.append({"name": "ABDA_DATABASE_URL", "secretRef": "database-url"})
    return {
        "name": "abda-nl-stg-web",
        "properties": {
            "provisioningState": "Succeeded",
            "runningStatus": "Running",
            "latestRevisionName": revision,
            "latestReadyRevisionName": revision,
            "configuration": {"activeRevisionsMode": "Single"},
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


def _seed_database(path: Path) -> str:
    engine = create_engine(f"sqlite+pysqlite:///{path}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = utc_now()
    with factory() as session:
        user = User(
            email=EMAIL,
            email_verified=True,
            display_name="Disposable Privacy Gate",
            created_at=now,
            updated_at=now,
            last_login_at=now,
        )
        session.add(user)
        session.flush()
        session.add(
            Identity(
                user_id=user.id,
                issuer="https://identity.example.test",
                subject="privacy-gate-subject",
                provider_email=EMAIL,
                created_at=now,
                last_login_at=now,
            )
        )
        project = Project(
            owner_user_id=user.id,
            name="Disposable privacy acceptance",
            description="Content that must be exported and deleted",
            source_scenario_id="fire_prevention",
            scenario_json={"title": "Disposable", "language": {"p": "Test"}},
            version=1,
            created_at=now,
            updated_at=now,
        )
        session.add(project)
        session.flush()
        session.add(
            ShareLink(
                project_id=project.id,
                token_hash="a" * 64,
                permission="view",
                created_at=now,
            )
        )
        session.add(
            MCPAccessToken(
                user_id=user.id,
                name="Disposable privacy token",
                token_prefix="abda_mcp_privacy",
                token_hash="b" * 64,
                scopes="projects:read projects:write",
                created_at=now,
                expires_at=now + timedelta(days=30),
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


def test_gate_has_valid_syntax_and_a_narrow_destructive_boundary():
    assert GATE.stat().st_mode & 0o111
    subprocess.run(["bash", "-n", str(GATE)], check=True)
    source = GATE.read_text(encoding="utf-8")
    runner = _runner_source()

    for expected in (
        "RUN_ABDA_PRIVACY_ACCEPTANCE",
        "PREPARE_PRIVACY_ACCEPTANCE",
        "DELETE_PRIVACY_ACCEPTANCE",
        "PRIVACY_ACCEPTANCE_PREPARED_WAIT_15_MINUTES",
        "LIVE_PRIVACY_EXPORT_AND_DELETION_VERIFIED",
        "abda-nl-stg-web--harden-c173dd5",
        "Handshake status 404 Not Found",
        "Retrying safely",
    ):
        assert expected in source
    assert source.count("\n    az containerapp exec ") == 1
    assert "az containerapp update" not in source
    assert "az containerapp delete" not in source
    assert "az group delete" not in source
    assert "az containerapp secret" not in source
    assert "OPENROUTER_API_KEY" not in source
    assert "AZURE_OPENAI_API_KEY" not in source
    assert "getpass.getpass" in runner
    assert "shutil.rmtree(export_root" in runner
    assert "updated_at" in runner
    assert "age < 900" in runner
    assert "token_hash" not in runner.split("forbidden =", 1)[0]
    assert "\N{EN DASH}" not in source and "\N{EM DASH}" not in source


def test_app_preflight_accepts_only_the_approved_revision(tmp_path: Path):
    valid = tmp_path / "valid.json"
    valid.write_text(json.dumps(_application()), encoding="utf-8")
    result = _run_function("abda_privacy_validate_app", valid)
    assert result.returncode == 0, result.stderr

    wrong = tmp_path / "wrong.json"
    wrong.write_text(json.dumps(_application(revision="abda-nl-stg-web--ux-6d0fb44")), encoding="utf-8")
    result = _run_function("abda_privacy_validate_app", wrong)
    assert result.returncode != 0
    assert "application revision changed" in result.stderr


def test_exec_retry_is_limited_to_preconnection_404(tmp_path: Path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    counter = tmp_path / "exec-count"
    fake_az = fake_bin / "az"
    fake_az.write_text(
        """#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

arguments = sys.argv[1:]
if arguments[:3] == ["containerapp", "replica", "list"]:
    print(json.dumps([{
        "name": "ready-replica",
        "properties": {
            "runningState": "Running",
            "containers": [{"name": "web", "ready": True}],
        },
    }]))
    raise SystemExit(0)
if arguments[:2] == ["containerapp", "exec"]:
    path = Path(os.environ["ABDA_PRIVACY_TEST_COUNTER"])
    count = int(path.read_text() if path.exists() else "0") + 1
    path.write_text(str(count))
    if count == 1:
        print("Handshake status 404 Not Found")
        raise SystemExit(1)
    print("phase: prepared")
    print("result: PRIVACY_ACCEPTANCE_PREPARED_WAIT_15_MINUTES")
    raise SystemExit(0)
raise SystemExit("unexpected az command")
""",
        encoding="utf-8",
    )
    fake_az.chmod(0o755)
    gate_root = tmp_path / "gate-root"
    gate_root.mkdir()
    command = (
        f"source {shlex.quote(str(GATE))}; "
        "abda_privacy_set_constants; "
        f"ABDA_PRIVACY_ROOT={shlex.quote(str(gate_root))}; "
        "sleep() { :; }; "
        "abda_privacy_run_runner harmless-payload"
    )
    environment = os.environ.copy()
    environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
    environment["ABDA_PRIVACY_TEST_COUNTER"] = str(counter)
    result = subprocess.run(
        ["bash", "-c", command],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert result.returncode == 0, result.stderr
    assert counter.read_text(encoding="utf-8") == "2"
    assert "Retrying safely" in result.stdout
    assert "PRIVACY_ACCEPTANCE_PREPARED_WAIT_15_MINUTES" in (
        gate_root / "container-exec.log"
    ).read_text(encoding="utf-8")


def test_embedded_runner_prepares_waits_and_deletes_disposable_data(tmp_path: Path):
    database = tmp_path / "privacy.sqlite3"
    user_id = _seed_database(database)
    runner = _runner_source()
    environment = _runner_environment(database)

    prepared = subprocess.run(
        [sys.executable, "-c", runner],
        input=f"{EMAIL}\nPREPARE_PRIVACY_ACCEPTANCE\n",
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert prepared.returncode == 0, prepared.stderr
    assert "PRIVACY_ACCEPTANCE_PREPARED_WAIT_15_MINUTES" in prepared.stdout
    assert EMAIL not in prepared.stdout
    assert "a" * 64 not in prepared.stdout
    assert "b" * 64 not in prepared.stdout

    engine = create_engine(f"sqlite+pysqlite:///{database}")
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        user = session.get(User, user_id)
        assert user is not None and user.status == "deletion_pending"
        assert session.scalar(select(ShareLink.revoked_at)) is not None
        assert session.scalar(
            select(MCPAccessToken.revoked_at).where(MCPAccessToken.user_id == user_id)
        ) is not None
        user.updated_at = utc_now() - timedelta(minutes=16)
        session.commit()
    engine.dispose()

    deleted = subprocess.run(
        [sys.executable, "-c", runner],
        input=f"{EMAIL}\nDELETE_PRIVACY_ACCEPTANCE\n",
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert deleted.returncode == 0, deleted.stderr
    assert "LIVE_PRIVACY_EXPORT_AND_DELETION_VERIFIED" in deleted.stdout
    assert EMAIL not in deleted.stdout

    engine = create_engine(f"sqlite+pysqlite:///{database}")
    with sessionmaker(bind=engine)() as session:
        assert session.get(User, user_id) is None
    engine.dispose()
