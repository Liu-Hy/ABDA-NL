"""Explain zero and ambiguous account matches without changing account data."""

from datetime import timedelta
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.models import MCPAccessToken, Project, ShareLink, User, utc_now
from test_privacy_acceptance_gate import _job, _runner_environment, _seed_database


PATH = Path(__file__).resolve().parents[1] / "deploy/azure/inspect-privacy-matches.py"
SPEC = importlib.util.spec_from_file_location("privacy_match_inspection", PATH)
assert SPEC and SPEC.loader
inspection = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inspection)


@pytest.mark.parametrize("change", ["none", "duplicate", "archived", "renamed_token", "unverified", "other_status"])
def test_each_selector_failure_is_explained_without_mutation(tmp_path, change):
    database = tmp_path / "inspection.sqlite3"
    user_id = _seed_database(database)
    if change == "duplicate":
        _seed_database(database, email="another-test@example.edu", marker="b")
    engine = create_engine(f"sqlite+pysqlite:///{database}")
    prepared_at = utc_now() - timedelta(minutes=20)
    with sessionmaker(bind=engine)() as session:
        user = session.get(User, user_id)
        user.status = "deletion_pending"
        user.updated_at = prepared_at
        token = session.scalar(select(MCPAccessToken).where(MCPAccessToken.user_id == user_id))
        token.revoked_at = prepared_at
        project = session.scalar(select(Project).where(Project.owner_user_id == user_id))
        session.scalar(select(ShareLink).where(ShareLink.project_id == project.id)).revoked_at = prepared_at
        if change == "archived":
            project.archived_at = prepared_at
        elif change == "renamed_token":
            token.name = "Different name"
        elif change == "unverified":
            user.email_verified = False
        elif change == "other_status":
            user.status = "suspended"
        session.commit()
    engine.dispose()
    before = database.read_bytes()
    environment = _runner_environment(database)
    environment.update({
        "ABDA_PRIVACY_PREPARED_START": (prepared_at - timedelta(seconds=10)).isoformat(),
        "ABDA_PRIVACY_PREPARED_END": (prepared_at + timedelta(seconds=10)).isoformat(),
    })
    result = subprocess.run([sys.executable, "-c", inspection.RUNNER], env=environment, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert "PRIVACY_ACCOUNT_MATCH_INSPECTION_COMPLETE" in result.stdout
    assert "@" not in result.stdout and user_id not in result.stdout
    counts = {}
    for line in result.stdout.splitlines():
        if line.startswith("privacy_match_count "):
            name, value = line.removeprefix("privacy_match_count ").split("=")
            counts[name] = int(value)
    assert tuple(counts) == inspection.COUNT_FIELDS
    expected_original = {"none": 1, "duplicate": 2}.get(change, 0)
    assert counts["original_selector_matches"] == expected_original
    if change == "duplicate":
        assert counts["both_names_active"] == 1 and counts["both_names_prepared"] == 1
    if change == "archived":
        assert counts["archived_bearer_window_matches"] == 1
    if change == "renamed_token":
        assert counts["prepared_with_named_credential"] == 0
        assert counts["prepared_with_named_project"] == 1
    if change == "unverified":
        assert counts["unverified_bearer_window_matches"] == 1
    if change == "other_status":
        assert counts["both_names_other_status"] == 1
    assert database.read_bytes() == before

    # Verify the connection itself rejects writes, not just that this query
    # happens to avoid them.
    bad_runner = inspection.RUNNER.replace(
        "        counts = {", "        session.execute(text(\"UPDATE users SET status='active'\"))\n        counts = {",
    )
    forbidden = subprocess.run([sys.executable, "-c", bad_runner], env=environment, capture_output=True, text=True, check=False)
    assert forbidden.returncode == 1
    assert "privacy_match_error: inspection_failed" in forbidden.stdout
    assert database.read_bytes() == before


def test_template_uses_application_password_and_read_only_program():
    document = inspection.template("reviewed-image", "2026-09-04T05:00:00Z", "2026-09-04T05:00:30Z")
    container = document["containers"][0]
    assert container["command"] == ["/opt/venv/bin/python"]
    environment = {item["name"]: item for item in container["env"]}
    assert environment["ABDA_DATABASE_APP_PASSWORD"]["secretRef"] == "app-database-password"
    assert "ABDA_DATABASE_URL" not in environment
    assert "admin-database-url" not in json.dumps(document)
    assert "SET TRANSACTION READ ONLY" in inspection.RUNNER


def test_active_job_refuses_inspection_start(tmp_path, monkeypatch):
    import types

    calls = []
    def az(*args, label):
        calls.append(args)
        if args[:2] == ("account", "show"):
            return {"id": "sub", "tenantId": "tenant", "user": {"name": "operator"}, "state": "Enabled"}
        if args[:4] == ("containerapp", "job", "execution", "show"):
            return {}
        if args[:3] == ("containerapp", "job", "show"):
            return _job()
        if args[:4] == ("containerapp", "job", "execution", "list"):
            return [{"properties": {"status": "Running"}}]
        pytest.fail(f"Unexpected command: {args}")

    diagnostic = types.SimpleNamespace(
        az_json=az, SUBSCRIPTION="sub", TENANT="tenant", AZURE_USER="operator",
        JOB="abda-nl-stg-migrate", RESOURCE_GROUP="abda-nl-staging", PREPARATION_EXECUTION="old",
    )
    monkeypatch.setattr(inspection, "preparation_interval", lambda *_: ("start", "end"))
    with pytest.raises(inspection.InspectionError, match="active or unknown"):
        inspection.run(tmp_path, diagnostic)
    assert all("start" not in call for call in calls)


def test_full_inspection_collects_inner_receipt_without_leaking_credentials(tmp_path, monkeypatch, capsys):
    diagnostic_path = PATH.with_name("diagnose-privacy-preflight.py")
    spec = importlib.util.spec_from_file_location("match_receipt_parser", diagnostic_path)
    diagnostic = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(diagnostic)
    secret = "private.test.token"
    calls = []
    execution = "abda-nl-stg-migrate-inspect01"

    def az(*args, label):
        calls.append(args)
        if args[:2] == ("account", "show"):
            return {"id": diagnostic.SUBSCRIPTION, "tenantId": diagnostic.TENANT,
                    "user": {"name": diagnostic.AZURE_USER}, "state": "Enabled"}
        if args[:4] == ("containerapp", "job", "execution", "show"):
            return "Succeeded" if "--query" in args else {}
        if args[:3] == ("containerapp", "job", "show"):
            return _job()
        if args[:4] == ("containerapp", "job", "execution", "list"):
            return [{"properties": {"status": "Succeeded"}}]
        if args[:3] == ("containerapp", "job", "start"):
            document = json.loads(Path(args[args.index("--yaml") + 1]).read_text())
            assert document == inspection.template(diagnostic.EXPECTED_IMAGE, "start", "end")
            return {"name": execution}
        if args[:4] == ("monitor", "log-analytics", "workspace", "show"):
            return "12345678-1234-1234-1234-123456789abc"
        if args[:2] == ("account", "get-access-token"):
            return secret
        pytest.fail(f"Unexpected command: {args}")

    def run_json(args, *, label, stdin):
        assert secret not in " ".join(args)
        assert secret in stdin
        body = json.loads(args[args.index("--data-binary") + 1])
        assert execution in body["query"] and "| summarize" in body["query"]
        return {"tables": [{
            "columns": [{"name": name} for name in inspection.RESULT_FIELDS],
            "rows": [[1, 0, *([0] * len(inspection.COUNT_FIELDS))]],
        }]}

    monkeypatch.setattr(diagnostic, "az_json", az)
    monkeypatch.setattr(diagnostic, "run_json", run_json)
    monkeypatch.setattr(inspection, "preparation_interval", lambda *_: ("start", "end"))
    assert inspection.run(tmp_path, diagnostic) == 0
    assert sum(call[:3] == ("containerapp", "job", "start") for call in calls) == 1
    output = capsys.readouterr().out
    assert "PRIVACY_ACCOUNT_MATCH_COUNTS_VERIFIED" in output
    assert secret not in output
