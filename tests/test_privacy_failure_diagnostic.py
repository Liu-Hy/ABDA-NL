"""The Cloud Shell diagnostic exposes only fixed counters and never starts jobs."""

from __future__ import annotations

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


def test_diagnostic_reads_only_and_keeps_authentication_out_of_argv(monkeypatch, capsys):
    calls = []
    secret = "private.test.token"

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
            assert arguments[arguments.index("--job-execution-name") + 1] == diagnostic.EXECUTION
            data = {"name": diagnostic.EXECUTION, "status": "Failed"}
        elif arguments[:4] == ["az", "monitor", "log-analytics", "workspace"]:
            assert arguments[4] == "show"
            data = "12345678-1234-1234-1234-123456789abc"
        elif arguments[:3] == ["az", "account", "get-access-token"]:
            data = secret
        else:
            assert arguments[0] == "curl"
            assert secret in kwargs["input"]
            query = json.loads(arguments[arguments.index("--data-binary") + 1])["query"]
            assert diagnostic.EXECUTION in query
            assert "| summarize" in query
            assert "| project" not in query
            assert "--location" not in arguments
            data = _response()
        return subprocess.CompletedProcess(arguments, 0, json.dumps(data), "")

    monkeypatch.setattr(diagnostic.subprocess, "run", run)
    assert diagnostic.main() == 0
    output = capsys.readouterr().out
    assert "account_phase_refused: 1" in output
    assert "runner_error_line: 0" in output
    assert "READ_ONLY_PRIVACY_FAILURE_DIAGNOSTIC_COMPLETE" in output
    assert secret not in output
    assert len(calls) == 5


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
