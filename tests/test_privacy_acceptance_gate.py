"""Contracts for the live disposable-account privacy acceptance gate."""

from __future__ import annotations

import base64
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
PROJECT_NAME = "Privacy acceptance disposable"
TOKEN_NAME = "Privacy acceptance disposable"
EXPECTED_REVISION = "abda-nl-stg-web--harden-51702e1"
EXPECTED_IMAGE = (
    "ghcr.io/liu-hy/abda-nl@sha256:"
    "a0b3ba24aff06ecf461f86547131d86451c541e306a7ecfc278f280fcef5c0bc"
)


def _runner_source() -> str:
    result = subprocess.run(
        ["bash", "-c", f"source {shlex.quote(str(GATE))}; abda_privacy_runner_source"],
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
                    {"name": "web", "image": EXPECTED_IMAGE, "env": values}
                ]
            },
        },
    }


def _job() -> dict:
    return {
        "name": "abda-nl-stg-migrate",
        "location": "East US 2",
        "properties": {
            "provisioningState": "Succeeded",
            "environmentId": (
                "/subscriptions/test/resourceGroups/abda-nl-staging/providers/"
                "Microsoft.App/managedEnvironments/abda-nl-stg-environment"
            ),
            "configuration": {
                "triggerType": "Manual",
                "replicaTimeout": 900,
                "replicaRetryLimit": 0,
                "manualTriggerConfig": {
                    "parallelism": 1,
                    "replicaCompletionCount": 1,
                },
                "secrets": [
                    {"name": "admin-database-url"},
                    {"name": "app-database-password"},
                ],
            },
            "template": {
                "containers": [
                    {
                        "name": "migrate",
                        "image": "ghcr.io/liu-hy/abda-nl@sha256:" + "c" * 64,
                        "command": ["/opt/venv/bin/python"],
                        "args": ["-m", "app.cli.migrate"],
                        "env": [
                            {
                                "name": "ABDA_DATABASE_URL",
                                "secretRef": "admin-database-url",
                            },
                            {
                                "name": "ABDA_DATABASE_APP_PASSWORD",
                                "secretRef": "app-database-password",
                            },
                        ],
                    }
                ]
            },
        },
    }


def _seed_database(path: Path, *, email: str = EMAIL, marker: str = "a") -> str:
    engine = create_engine(f"sqlite+pysqlite:///{path}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = utc_now()
    with factory() as session:
        user = User(
            email=email,
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
                subject=f"privacy-gate-subject-{marker}",
                provider_email=email,
                created_at=now,
                last_login_at=now,
            )
        )
        project = Project(
            owner_user_id=user.id,
            name=PROJECT_NAME,
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
                token_hash=marker * 64,
                permission="view",
                created_at=now,
            )
        )
        session.add(
            MCPAccessToken(
                user_id=user.id,
                name=TOKEN_NAME,
                token_prefix=f"abda_mcp_privacy_{marker}",
                token_hash=marker.upper() * 64,
                scopes="projects:read",
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


def _write_template(path: Path, action: str = "prepare") -> dict:
    payload = base64.b64encode(_runner_source().encode()).decode()
    result = _run_function("abda_privacy_write_job_template", path, payload, action)
    assert result.returncode == 0, result.stderr
    return json.loads(path.read_text(encoding="utf-8"))


def _execution(name: str, status: str, template: dict) -> dict:
    return {
        "name": name,
        "properties": {
            "status": status,
            "startTime": "2026-09-04T01:00:00Z",
            "template": template,
        },
    }


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
        "az containerapp job start",
        "--yaml",
    ):
        assert expected in source
    assert source.count("\n      az containerapp job start ") == 1
    for forbidden in (
        "az containerapp exec",
        "az containerapp job update",
        "az containerapp update",
        "az containerapp delete",
        "az group delete",
        "az containerapp secret",
        "az deployment group",
        "OPENROUTER_API_KEY",
        "AZURE_OPENAI_API_KEY",
    ):
        assert forbidden not in source
    assert "getpass.getpass" not in runner
    assert PROJECT_NAME in runner and TOKEN_NAME in runner
    assert "postgresql+psycopg://abda_app:" in runner
    assert 'os.environ.pop("ABDA_DATABASE_APP_PASSWORD"' in runner
    assert "shutil.rmtree(export_root" in runner
    assert "age < 900" in runner
    assert "account_fingerprint:" not in runner
    assert "\N{EN DASH}" not in source and "\N{EM DASH}" not in source


def test_app_and_job_preflights_are_narrow(tmp_path: Path):
    app = tmp_path / "app.json"
    app.write_text(json.dumps(_application()), encoding="utf-8")
    assert _run_function("abda_privacy_validate_app", app).returncode == 0
    app.write_text(
        json.dumps(_application(revision="abda-nl-stg-web--ux-6d0fb44")),
        encoding="utf-8",
    )
    result = _run_function("abda_privacy_validate_app", app)
    assert result.returncode != 0 and "application revision changed" in result.stderr

    before = tmp_path / "job-before.json"
    after = tmp_path / "job-after.json"
    before.write_text(json.dumps(_job()), encoding="utf-8")
    assert _run_function("abda_privacy_validate_job", before).returncode == 0
    changed = _job()
    changed["systemData"] = {"lastModifiedAt": "later"}
    after.write_text(json.dumps(changed), encoding="utf-8")
    assert _run_function("abda_privacy_compare_job_configuration", before, after).returncode == 0
    changed["properties"]["template"]["containers"][0]["args"] = ["changed"]
    after.write_text(json.dumps(changed), encoding="utf-8")
    result = _run_function("abda_privacy_compare_job_configuration", before, after)
    assert result.returncode != 0 and "job configuration changed" in result.stderr


def test_execution_template_and_resume_classifier(tmp_path: Path):
    template_path = tmp_path / "privacy-execution.yaml"
    template = _write_template(template_path)
    assert template_path.stat().st_mode & 0o777 == 0o600
    container = template["containers"][0]
    assert container["name"] == "migrate"
    assert container["image"] == EXPECTED_IMAGE
    assert container["args"][-2:] == ["prepare", "PRIV-ACCEPT-20260830-01"]
    environment = {item["name"]: item for item in container["env"]}
    assert environment["ABDA_DATABASE_APP_PASSWORD"]["secretRef"] == "app-database-password"
    serialized = json.dumps(template)
    assert EMAIL not in serialized
    assert "admin-database-url" not in serialized
    assert "ABDA_DATABASE_URL" not in serialized

    executions = tmp_path / "executions.json"
    for value, expected in (
        ([], "new|"),
        (
            [_execution("abda-nl-stg-migrate-running", "Running", template)],
            "active|abda-nl-stg-migrate-running",
        ),
        (
            [_execution("abda-nl-stg-migrate-success", "Succeeded", template)],
            "succeeded|abda-nl-stg-migrate-success",
        ),
        (
            [_execution("abda-nl-stg-migrate-failed", "Failed", template)],
            "failed|abda-nl-stg-migrate-failed",
        ),
    ):
        executions.write_text(json.dumps(value), encoding="utf-8")
        result = _run_function(
            "abda_privacy_classify_executions", executions, template_path
        )
        assert result.returncode == 0 and result.stdout.strip() == expected

    foreign = json.loads(json.dumps(template))
    foreign["containers"][0]["args"][-2] = "delete"
    executions.write_text(
        json.dumps([_execution("abda-nl-stg-migrate-foreign", "Processing", foreign)]),
        encoding="utf-8",
    )
    result = _run_function("abda_privacy_classify_executions", executions, template_path)
    assert result.returncode != 0
    assert "another migration job execution is active" in result.stderr


def test_embedded_runner_prepares_resumes_and_deletes(tmp_path: Path):
    database = tmp_path / "privacy.sqlite3"
    user_id = _seed_database(database)
    runner = _runner_source()
    environment = _runner_environment(database)
    prepare = [sys.executable, "-c", runner, "prepare", "PRIV-ACCEPT-20260830-01"]

    prepared = subprocess.run(
        prepare,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert prepared.returncode == 0, prepared.stderr
    assert "PRIVACY_ACCEPTANCE_PREPARED_WAIT_15_MINUTES" in prepared.stdout
    assert EMAIL not in prepared.stdout

    resumed = subprocess.run(
        prepare,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert resumed.returncode == 0 and "preparation_resumed: true" in resumed.stdout

    engine = create_engine(f"sqlite+pysqlite:///{database}")
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        user = session.get(User, user_id)
        assert user is not None and user.status == "deletion_pending"
        assert session.scalar(select(ShareLink.revoked_at)) is not None
        assert session.scalar(select(MCPAccessToken.revoked_at)) is not None
        user.updated_at = utc_now() - timedelta(minutes=16)
        session.commit()
    engine.dispose()

    deleted = subprocess.run(
        [sys.executable, "-c", runner, "delete", "PRIV-ACCEPT-20260830-01"],
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


def test_embedded_runner_refuses_ambiguous_accounts(tmp_path: Path):
    database = tmp_path / "ambiguous.sqlite3"
    first_id = _seed_database(database, marker="a")
    second_id = _seed_database(
        database,
        email="privacy-gate-second@example.edu",
        marker="b",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            _runner_source(),
            "prepare",
            "PRIV-ACCEPT-20260830-01",
        ],
        env=_runner_environment(database),
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode != 0 and "exactly one disposable account" in result.stderr
    assert EMAIL not in result.stderr
    engine = create_engine(f"sqlite+pysqlite:///{database}")
    with sessionmaker(bind=engine)() as session:
        assert session.get(User, first_id).status == "active"
        assert session.get(User, second_id).status == "active"
    engine.dispose()
