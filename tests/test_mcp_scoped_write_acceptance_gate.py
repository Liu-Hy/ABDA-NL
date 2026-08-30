"""Contracts for the live MCP scoped-write acceptance gate."""

from __future__ import annotations

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shlex
import subprocess
from threading import Thread
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "deploy" / "azure" / "gate10-mcp-scoped-write-acceptance.sh"
READ_TOKEN = "abda_mcp_" + "R" * 40
WRITE_TOKEN = "abda_mcp_" + "W" * 40
PROJECT_NAME = "MCP scoped acceptance, delete me"


class MCPFixture:
    def __init__(self) -> None:
        self.projects: dict[str, dict[str, Any]] = {}
        self.revoked: set[str] = set()
        self.enforce_scopes = True
        self.proposal_applies = False
        self.proposal_calls = 0

    @staticmethod
    def success(request_id: int, value: dict[str, Any]) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "isError": False,
                "content": [{"type": "text", "text": json.dumps(value)}],
                "structuredContent": value,
            },
        }

    @staticmethod
    def error(request_id: int, message: str) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "isError": True,
                "content": [{"type": "text", "text": message}],
            },
        }

    @staticmethod
    def project_payload(project: dict[str, Any]) -> dict[str, Any]:
        return {
            **project,
            "source_scenario_id": "fire_prevention",
            "created_at": "2026-08-29T12:00:00+00:00",
            "updated_at": project["updated_at"],
            "scenario": {"title": "Prescribed Burn", "facts": {}},
            "af_summary": {
                "argument_count": 1,
                "attack_count": 0,
                "labels_by_proposition": {},
            },
        }

    def handle(self, token: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        request_id = payload["id"]
        if token not in {READ_TOKEN, WRITE_TOKEN} or token in self.revoked:
            return 401, {"detail": "unauthorized"}
        if payload["method"] == "initialize":
            return 200, {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": "2025-11-25",
                    "serverInfo": {"name": "abda-nl", "version": "test"},
                },
            }
        assert payload["method"] == "tools/call"
        params = payload["params"]
        name = params["name"]
        arguments = params.get("arguments") or {}
        if name == "list_projects":
            projects = [
                {
                    "id": project["id"],
                    "name": project["name"],
                    "description": project["description"],
                    "version": project["version"],
                }
                for project in self.projects.values()
            ]
            return 200, self.success(request_id, {"projects": projects})
        if name == "create_project":
            if token == READ_TOKEN and self.enforce_scopes:
                return 200, self.error(
                    request_id,
                    "This token requires the projects:write scope.",
                )
            if arguments["source_scenario_id"] != "fire_prevention":
                return 200, self.error(request_id, "Scenario not found.")
            project = {
                "id": "fixture-project-id",
                "name": arguments["name"],
                "description": arguments.get("description", ""),
                "version": 1,
                "updated_at": "2026-08-29T12:00:00+00:00",
            }
            self.projects[project["id"]] = project
            return 200, self.success(request_id, self.project_payload(project))
        project_id = arguments["project_id"]
        project = self.projects.get(project_id)
        if project is None:
            return 200, self.error(request_id, "Project not found.")
        if name == "get_project":
            return 200, self.success(request_id, self.project_payload(project))
        if name == "update_project_metadata":
            if arguments["expected_version"] != project["version"]:
                return 200, self.error(
                    request_id,
                    "The project changed since it was loaded.",
                )
            if "name" in arguments:
                project["name"] = arguments["name"]
            if "description" in arguments:
                project["description"] = arguments["description"]
            project["version"] += 1
            project["updated_at"] = "2026-08-29T12:01:00+00:00"
            return 200, self.success(request_id, self.project_payload(project))
        if name == "propose_project_edit":
            self.proposal_calls += 1
            expected_version = project["version"]
            if self.proposal_applies:
                project["version"] += 1
                project["updated_at"] = "2026-08-29T12:02:00+00:00"
            return 200, self.success(
                request_id,
                {
                    "project_id": project_id,
                    "expected_version": expected_version,
                    "op": {
                        "op": "add-fact",
                        "id": "temporary_monitor",
                        "fact": {"description": "A monitor is operating."},
                    },
                    "reviewed": False,
                    "review_issues": [],
                    "billing_source": "trial",
                    "cost_microusd": 321,
                },
            )
        raise AssertionError(f"unexpected tool: {name}")


@contextmanager
def _server(fixture: MCPFixture) -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            return

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            auth = self.headers.get("Authorization", "")
            token = auth.removeprefix("Bearer ") if auth.startswith("Bearer ") else ""
            status, response = fixture.handle(token, payload)
            wire = json.dumps(response).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(wire)))
            self.end_headers()
            self.wfile.write(wire)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/mcp/"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _run_phase(
    phase: str,
    state_path: Path,
    url: str,
) -> subprocess.CompletedProcess[str]:
    command = (
        f"source {shlex.quote(str(GATE))}; "
        'ABDA_MCP_READ_TOKEN="$ABDA_MCP_SCOPED_TEST_READ_TOKEN"; '
        'ABDA_MCP_WRITE_TOKEN="$ABDA_MCP_SCOPED_TEST_WRITE_TOKEN"; '
        "export ABDA_MCP_READ_TOKEN ABDA_MCP_WRITE_TOKEN; "
        f"abda_mcp_scoped_runner {shlex.quote(phase)} "
        f"{shlex.quote(str(state_path))}"
    )
    environment = os.environ.copy()
    environment.update(
        {
            "ABDA_MCP_SCOPED_URL": url,
            "ABDA_MCP_SCOPED_PROJECT_NAME": PROJECT_NAME,
            "ABDA_MCP_SCOPED_TEST_READ_TOKEN": READ_TOKEN,
            "ABDA_MCP_SCOPED_TEST_WRITE_TOKEN": WRITE_TOKEN,
        }
    )
    return subprocess.run(
        ["bash", "-c", command],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def test_scoped_write_gate_is_executable_valid_and_secret_safe() -> None:
    assert GATE.stat().st_mode & 0o111
    subprocess.run(["bash", "-n", str(GATE)], check=True)
    source = GATE.read_text(encoding="utf-8")
    for expected in (
        "LIVE_MCP_SCOPED_WRITE_ACCEPTANCE_VERIFIED",
        "__abda_missing_scope_probe__",
        "after_proposal != before_proposal",
        "Type PROJECT_DELETED after deletion",
        "Type TOKENS_REVOKED after both are revoked",
        "IFS= read -r -s -p 'Read-only MCP token: '",
        "Keep this shell open. In the browser, create a separate 30-day token named",
        "IFS= read -r -s -p 'Full-scope MCP token: '",
        "proposal_did_not_apply: passed",
        "azure_configuration_changed: false",
    ):
        assert expected in source
    for forbidden in (
        "apply_project_ops",
        "az containerapp",
        "az deployment",
        "set -x",
        "printenv",
        "env |",
    ):
        assert forbidden not in source
    assert source.index("Read-only MCP token: ") < source.index(
        "create a separate 30-day token named"
    ) < source.index("Full-scope MCP token: ")
    assert "\N{EM DASH}" not in source
    assert "\N{EN DASH}" not in source


def test_scoped_write_runner_accepts_the_complete_bounded_lifecycle(
    tmp_path: Path,
) -> None:
    fixture = MCPFixture()
    state_path = tmp_path / "private-state.json"
    with _server(fixture) as url:
        preflight = _run_phase("preflight", state_path, url)
        assert preflight.returncode == 0, preflight.stderr
        assert "rejected_without_mutation" in preflight.stdout
        assert fixture.projects == {}

        mutation = _run_phase("mutation", state_path, url)
        assert mutation.returncode == 0, mutation.stderr
        assert "proposal_did_not_apply: passed" in mutation.stdout
        assert fixture.proposal_calls == 1
        assert fixture.projects["fixture-project-id"]["version"] == 2
        assert (tmp_path / "project-created").is_file()
        assert state_path.stat().st_mode & 0o077 == 0

        fixture.projects.clear()
        deleted = _run_phase("deleted", state_path, url)
        assert deleted.returncode == 0, deleted.stderr
        assert "disposable_project_removed: passed" in deleted.stdout

        fixture.revoked.update({READ_TOKEN, WRITE_TOKEN})
        revoked = _run_phase("revoked", state_path, url)
        assert revoked.returncode == 0, revoked.stderr
        assert "full_scope_token_revocation: passed" in revoked.stdout


def test_scoped_write_runner_stops_if_read_scope_does_not_block_writes(
    tmp_path: Path,
) -> None:
    fixture = MCPFixture()
    fixture.enforce_scopes = False
    with _server(fixture) as url:
        result = _run_phase("preflight", tmp_path / "state.json", url)
    assert result.returncode != 0
    assert "read-only token was not rejected" in result.stderr
    assert fixture.projects == {}


def test_scoped_write_runner_stops_if_a_proposal_mutates_the_project(
    tmp_path: Path,
) -> None:
    fixture = MCPFixture()
    fixture.proposal_applies = True
    state_path = tmp_path / "state.json"
    with _server(fixture) as url:
        assert _run_phase("preflight", state_path, url).returncode == 0
        result = _run_phase("mutation", state_path, url)
    assert result.returncode != 0
    assert "proposal changed the project" in result.stderr
    assert fixture.proposal_calls == 1
