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
