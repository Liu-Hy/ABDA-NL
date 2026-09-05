"""The Cloud Shell diagnostic exposes only fixed counters and never starts jobs."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest


PATH = Path(__file__).resolve().parents[1] / "deploy/azure/diagnose-privacy-preflight.py"
SPEC = importlib.util.spec_from_file_location("privacy_failure_diagnostic", PATH)
assert SPEC and SPEC.loader
diagnostic = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagnostic)


def _response():
    counts = dict.fromkeys(diagnostic.FIELDS, 0)
    counts.update(total_logs=7, console_logs=7, runner_refusals=1, account_phase_refused=1)
    counts["runner_error_line"] = None
    return {"tables": [{
        "name": "PrimaryResult",
        "columns": [{"name": name, "type": "long"} for name in counts],
        "rows": [list(counts.values())],
    }]}


@pytest.mark.parametrize("preparation", [False, True])
def test_diagnostic_reads_only_and_keeps_authentication_out_of_argv(monkeypatch, capsys, preparation):
    calls = []
    secret = "private.test.token"
    execution = diagnostic.PREPARATION_EXECUTION if preparation else diagnostic.EXECUTION

    def run(arguments, **kwargs):
        calls.append(arguments)
        assert secret not in " ".join(arguments)
        assert kwargs["capture_output"] and kwargs["timeout"] == 70
        if arguments[:3] == ["az", "account", "show"]:
            data = {
                "id": diagnostic.SUBSCRIPTION, "tenantId": diagnostic.TENANT,
                "user": {"name": diagnostic.AZURE_USER}, "state": "Enabled",
            }
        elif arguments[:4] == ["az", "containerapp", "job", "execution"]:
            assert arguments[4] == "show"
            assert arguments[arguments.index("--job-execution-name") + 1] == execution
            assert "env" not in arguments[arguments.index("--query") + 1]
            data = {"name": execution, "status": "Succeeded" if preparation else "Failed"}
        elif arguments[:4] == ["az", "monitor", "log-analytics", "workspace"]:
            assert arguments[4] == "show"
            data = "12345678-1234-1234-1234-123456789abc"
        elif arguments[:3] == ["az", "account", "get-access-token"]:
            data = secret
        else:
            assert arguments[0] == "curl"
            assert secret in kwargs["input"]
            query = json.loads(arguments[arguments.index("--data-binary") + 1])["query"]
            assert execution in query
            assert "| summarize" in query
            assert "| project" not in query
            assert "--location" not in arguments
            data = _response()
        return subprocess.CompletedProcess(arguments, 0, json.dumps(data), "")

    monkeypatch.setattr(diagnostic.subprocess, "run", run)
    assert diagnostic.main(["--preparation"] if preparation else []) == 0
    output = capsys.readouterr().out
    assert "account_phase_refused: 1" in output
    assert "runner_error_line: 0" in output
    assert "READ_ONLY_PRIVACY_FAILURE_DIAGNOSTIC_COMPLETE" in output
    assert secret not in output
    assert len(calls) == 5


def test_migration_is_distinguished_from_privacy_preparation():
    containers = [{
        "command": ["/opt/venv/bin/python"], "args": ["-m", "app.cli.migrate"],
        "image": "private-image-value",
    }]
    summary = diagnostic.describe_command(containers)
    assert summary["execution_command"] == "database_migration"
    assert summary["reviewed_privacy_image"] == "false"
    assert "private-image-value" not in str(summary)


def test_runner_payload_is_checked_but_never_executed(monkeypatch):
    source = b"raise RuntimeError('must never execute the recorded program')\n"
    payload = base64.b64encode(source).decode()
    monkeypatch.setattr(diagnostic, "REVIEWED_RUNNERS", {
        hashlib.sha256(source).hexdigest(): "privacy_revision_8",
    })
    code = "import base64;exec(compile(base64.b64decode(" + repr(payload) + "),'<privacy-acceptance>','exec'))"
    containers = [{
        "command": ["/opt/venv/bin/python"], "image": diagnostic.EXPECTED_IMAGE,
        "args": ["-c", code, "prepare", "PRIV-ACCEPT-20260830-01"],
    }]
    assert diagnostic.describe_command(containers) == {
        "execution_command": "privacy_prepare", "runner_source": "privacy_revision_8",
        "reviewed_privacy_image": "true",
    }
    containers[0]["args"][1] += ";print('private@example.edu')"
    summary = diagnostic.describe_command(containers)
    assert summary["runner_source"] == "unrecognized"
    assert "private@example.edu" not in str(summary)


def test_log_queries_do_not_accept_unreviewed_execution_names():
    with pytest.raises(diagnostic.DiagnosticError, match="outside this diagnostic"):
        diagnostic.logs_query("unexpected' | take 100 //")


def test_unknown_or_private_response_fields_are_never_reported():
    response = _response()
    response["tables"][0]["columns"].append({"name": "Log_s", "type": "string"})
    response["tables"][0]["rows"][0].append("private@example.edu")
    with pytest.raises(diagnostic.DiagnosticError, match="summary shape"):
        diagnostic.parse_counts(response)
    with pytest.raises(diagnostic.DiagnosticError, match="query error"):
        diagnostic.parse_counts({"error": {"message": "private@example.edu"}})


def test_failed_external_command_does_not_echo_private_errors(monkeypatch):
    def run(arguments, **kwargs):
        return subprocess.CompletedProcess(arguments, 1, "private@example.edu", "secret-value")

    monkeypatch.setattr(diagnostic.subprocess, "run", run)
    with pytest.raises(diagnostic.DiagnosticError) as error:
        diagnostic.run_json(["az", "account", "get-access-token"], label="Authentication")
    assert str(error.value) == "Authentication exited with code 1"


def test_history_counts_cannot_substitute_for_a_verified_deletion_command():
    row = dict.fromkeys(diagnostic.HISTORY_FIELDS, 1)
    row.update(execution="abda-nl-stg-migrate-delete01", runner_refusals=0)
    description = {"execution_command": "privacy_delete", "runner_source": "privacy_revision_8", "reviewed_privacy_image": "true"}
    assert diagnostic.verified_deletion(row, "Succeeded", description, "expected_postgres_runner_inputs")
    assert diagnostic.verified_deletion_receipt(row, "Succeeded", description)
    assert not diagnostic.verified_deletion(row, "Failed", description, "expected_postgres_runner_inputs")
    assert not diagnostic.verified_deletion(row, "Succeeded", description, "secret_reference_not_resolved")
    assert not diagnostic.verified_deletion(row, "Succeeded", description, "unrecognized")
    assert not diagnostic.verified_deletion(row, "Succeeded", description, "not_recorded")
    assert not diagnostic.verified_deletion(row, "Succeeded", {**description, "execution_command": "database_migration"}, "expected_postgres_runner_inputs")
    row["deleted_identity_count"] = None
    assert not diagnostic.verified_deletion(row, "Succeeded", description, "expected_postgres_runner_inputs")


@pytest.mark.parametrize("changes", [
    {"runner_source": "unrecognized"},
    {"reviewed_privacy_image": "false"},
    {"execution_command": "privacy_prepare"},
])
def test_receipt_recovery_does_not_relax_runner_or_image_verification(changes):
    row = dict.fromkeys(diagnostic.HISTORY_FIELDS, 1)
    row["runner_refusals"] = 0
    description = {
        "execution_command": "privacy_delete", "runner_source": "privacy_revision_10",
        "reviewed_privacy_image": "true", **changes,
    }
    assert not diagnostic.verified_deletion_receipt(row, "Succeeded", description)


def test_history_validates_every_field_before_reporting_rows():
    values = ["abda-nl-stg-migrate-delete01", 0, 0, 1, 0, 1, 1, 1, 1]
    response = {"tables": [{"columns": [{"name": name} for name in diagnostic.HISTORY_FIELDS], "rows": [values]}]}
    assert diagnostic.history_rows(response)[0]["deletion_success"] == 1
    values[0] = "private@example.edu"
    with pytest.raises(diagnostic.DiagnosticError, match="invalid history entry"):
        diagnostic.history_rows(response)
    values[0] = "abda-nl-stg-migrate-delete01"
    values[5] = "private@example.edu"
    with pytest.raises(diagnostic.DiagnosticError, match="nonnumeric history count"):
        diagnostic.history_rows(response)


def test_database_description_does_not_expose_values():
    env = [
        {"name": "ABDA_POSTGRES_HOST", "value": "abda-nl-stg-postgres-bgjhpbgw.postgres.database.azure.com"},
        {"name": "ABDA_DATABASE_APP_PASSWORD", "secretRef": "app-database-password"},
    ]
    assert diagnostic.database_input([{"env": env}]) == "expected_postgres_runner_inputs"
    env.append({"name": "ABDA_DATABASE_URL", "value": "postgresql+psycopg://private:secret@unexpected.example/db"})
    assert diagnostic.database_input([{"env": env}]) == "different_database_url"
    env[-1] = {"name": "ABDA_DATABASE_URL", "secretRef": "secret-value"}
    assert diagnostic.database_input([{"env": env}]) == "secret_reference_not_resolved"


@pytest.mark.parametrize("containers, expected", [
    ([{}], "not_recorded"),
    ([{"env": None}], "not_recorded"),
    ([{"env": []}], "not_recorded"),
    ([None], "unavailable"),
    ([{"env": "private-value"}], "unrecognized"),
    ([{"env": [None]}], "unrecognized"),
    ([{"env": [{"name": []}]}], "unrecognized"),
    ([{"env": [{"name": "same"}, {"name": "same"}]}], "unrecognized"),
])
def test_missing_or_invalid_database_metadata_is_not_a_match(containers, expected):
    assert diagnostic.database_input(containers) == expected


@pytest.mark.parametrize("database_state", ["verified", "unrecognized", "not_recorded"])
def test_history_audit_uses_only_queries_and_never_prints_arguments(monkeypatch, capsys, database_state):
    secret = "private.test.token"
    delete_name = "abda-nl-stg-migrate-delete01"
    calls = []
    def az(*args, label):
        calls.append(args)
        if args[:2] == ("account", "show"):
            return {"id": diagnostic.SUBSCRIPTION, "tenantId": diagnostic.TENANT,
                    "user": {"name": diagnostic.AZURE_USER}, "state": "Enabled"}
        if args[:4] == ("monitor", "log-analytics", "workspace", "show"):
            return "12345678-1234-1234-1234-123456789abc"
        if args[:2] == ("account", "get-access-token"):
            return secret
        assert args[:4] == ("containerapp", "job", "execution", "show")
        name = args[args.index("--job-execution-name") + 1]
        containers = [{
            "phase": "privacy_delete" if name == delete_name else "privacy_prepare",
            "args": ["private-argument"],
            "env": [
                {"name": "ABDA_POSTGRES_HOST", "value": "abda-nl-stg-postgres-bgjhpbgw.postgres.database.azure.com"},
                {"name": "ABDA_DATABASE_APP_PASSWORD", "secretRef": "app-database-password"},
            ],
        }]
        if database_state == "not_recorded":
            containers[0].pop("env")
        elif database_state == "unrecognized":
            containers[0]["env"] = [{"name": "unrecognized", "value": "private-db-value"}]
        return {"name": name, "status": "Succeeded", "containers": containers}

    def run(args, *, label, stdin):
        assert secret in stdin and secret not in " ".join(args)
        query = json.loads(args[args.index("--data-binary") + 1])["query"]
        assert "| summarize" in query
        assert query.strip().endswith(", ".join(diagnostic.HISTORY_FIELDS))
        return {"tables": [{
            "columns": [{"name": field} for field in diagnostic.HISTORY_FIELDS],
            "rows": [[delete_name, 0, 0, 1, 0, 1, 1, 1, 1]],
        }]}

    monkeypatch.setattr(diagnostic, "az_json", az)
    monkeypatch.setattr(diagnostic, "run_json", run)
    monkeypatch.setattr(diagnostic, "describe_command", lambda cs: {
        "execution_command": cs[0]["phase"], "runner_source": "privacy_revision_8", "reviewed_privacy_image": "true",
    })
    assert diagnostic.main(["--history"]) == (0 if database_state == "verified" else 2)
    output = capsys.readouterr().out
    assert "verified_deletion_receipt_count: 1" in output
    assert f"verified_deletion_receipt_execution: {delete_name}" in output
    assert "deletion_retry_authorized: false" in output
    if database_state == "verified":
        assert "VERIFIED_PRIOR_PRIVACY_DELETION_FOUND" in output
        assert "database_input_chain_verified: true" in output
    else:
        assert "PRIVACY_DELETION_RECEIPT_FOUND_DATABASE_REVIEW_PENDING" in output
        assert "database_input_chain_verified: false" in output
        assert "verified_deletion_execution_count: 0" in output
        assert "Do not repeat deletion" in output
    assert secret not in output and "private-argument" not in output
    assert "private-db-value" not in output
    assert all("start" not in args and "delete" not in args for args in calls)
