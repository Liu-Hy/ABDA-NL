"""Contracts for the live Codex and Claude MCP read acceptance gate."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import subprocess


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "deploy" / "azure" / "gate10-mcp-read-client-acceptance.sh"


def _run_function(
    function: str,
    *arguments: Path | str,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    quoted = " ".join(shlex.quote(str(argument)) for argument in arguments)
    token_setup = ""
    if environment and "ABDA_NL_MCP_TOKEN" in environment:
        token_setup = (
            'ABDA_NL_MCP_TOKEN="$ABDA_MCP_READ_TEST_TOKEN"; '
            "export ABDA_NL_MCP_TOKEN; "
        )
    command = (
        f"source {shlex.quote(str(GATE))}; "
        f"{token_setup}"
        f"abda_mcp_read_set_constants; {function} {quoted}"
    )
    process_environment = os.environ.copy()
    if environment:
        process_environment.update(environment)
        if "ABDA_NL_MCP_TOKEN" in environment:
            process_environment["ABDA_MCP_READ_TEST_TOKEN"] = environment[
                "ABDA_NL_MCP_TOKEN"
            ]
    return subprocess.run(
        ["bash", "-c", command],
        check=False,
        capture_output=True,
        text=True,
        env=process_environment,
    )


def _write_jsonl(path: Path, events: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )


def _codex_positive_events() -> list[dict]:
    return [
        {"type": "thread.started"},
        {
            "type": "item.started",
            "item": {
                "type": "mcp_tool_call",
                "server": "abda_nl",
                "tool": "list_examples",
                "status": "in_progress",
            },
        },
        {
            "type": "item.completed",
            "item": {
                "type": "mcp_tool_call",
                "server": "abda_nl",
                "tool": "list_examples",
                "status": "completed",
                "error": None,
                "result": {
                    "structured_content": {
                        "examples": [{"id": "public-one"}, {"id": "public-two"}]
                    }
                },
            },
        },
        {
            "type": "item.completed",
            "item": {"type": "agent_message", "text": "content-free"},
        },
        {"type": "turn.completed"},
    ]


def _claude_positive_events() -> list[dict]:
    return [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tool-one",
                        "name": "mcp__abda_nl__list_examples",
                        "input": {},
                    }
                ]
            },
        },
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tool-one",
                        "is_error": False,
                        "content": json.dumps(
                            {
                                "examples": [
                                    {"id": "public-one"},
                                    {"id": "public-two"},
                                ]
                            }
                        ),
                    }
                ]
            },
        },
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "structured-one",
                        "name": "StructuredOutput",
                    }
                ]
            },
        },
        {
            "type": "result",
            "is_error": False,
            "structured_output": {"success": True, "example_count": 2},
        },
    ]


def test_mcp_read_gate_is_executable_valid_and_content_safe():
    assert GATE.stat().st_mode & 0o111
    subprocess.run(["bash", "-n", str(GATE)], check=True)
    source = GATE.read_text(encoding="utf-8")
    for expected in (
        "LIVE_CODEX_AND_CLAUDE_MCP_READ_ACCEPTANCE_VERIFIED",
        "https://demo.abda-nl.org/mcp/",
        'shell_environment_policy.inherit="none"',
        'mcp_servers.abda_nl.enabled_tools=["list_examples"]',
        "--strict-mcp-config",
        "--setting-sources ''",
        "--tools ''",
        "--allowedTools \"$ABDA_MCP_CLAUDE_TOOL\"",
        "Type CLAUDE_COMMAND_BOUNDARY_CONFIRMED to continue",
        "timeout --kill-after=10s 180s codex exec",
        "timeout --kill-after=10s 180s claude -p",
        "IFS= read -r -s -p 'ABDA-NL read-only MCP token: '",
        "Type TOKEN_REVOKED to continue",
        "private_project_tools_enabled: false",
        "raw_client_logs_retained: false",
    ):
        assert expected in source
    for forbidden in (
        "list_projects",
        "get_project",
        "create_project",
        "update_project",
        "delete_project",
        "propose_project_edit",
        "apply_project_ops",
        "az containerapp",
        "az deployment",
        "set -x",
        "printenv",
        "env |",
        "cat $ABDA_MCP_READ_ROOT",
        "tail $ABDA_MCP_READ_ROOT",
    ):
        assert forbidden not in source
    assert "\N{EM DASH}" not in source
    assert "\N{EN DASH}" not in source


def test_mcp_read_gate_accepts_real_codex_jsonl_shape(tmp_path: Path):
    output = tmp_path / "codex.jsonl"
    _write_jsonl(output, _codex_positive_events())
    result = _run_function("abda_mcp_read_validate_codex_positive", output, "0")
    assert result.returncode == 0, result.stderr

    changed = _codex_positive_events()
    changed[2]["item"]["tool"] = "list_projects"
    _write_jsonl(output, changed)
    result = _run_function("abda_mcp_read_validate_codex_positive", output, "0")
    assert result.returncode != 0
    assert "unexpected MCP" in result.stderr

    changed = _codex_positive_events()
    changed.insert(
        -1,
        {
            "type": "item.completed",
            "item": {"type": "command_execution", "status": "completed"},
        },
    )
    _write_jsonl(output, changed)
    result = _run_function("abda_mcp_read_validate_codex_positive", output, "0")
    assert result.returncode != 0
    assert "non-MCP" in result.stderr


def test_mcp_read_gate_accepts_codex_revocation_and_rejects_access(
    tmp_path: Path,
):
    output = tmp_path / "codex-revoked.jsonl"
    _write_jsonl(
        output,
        [
            {"type": "thread.started"},
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": "unavailable"},
            },
            {"type": "turn.completed"},
        ],
    )
    result = _run_function("abda_mcp_read_validate_codex_revoked", output, "0")
    assert result.returncode == 0, result.stderr

    _write_jsonl(output, _codex_positive_events())
    result = _run_function("abda_mcp_read_validate_codex_revoked", output, "0")
    assert result.returncode != 0
    assert "after token revocation" in result.stderr


def test_mcp_read_gate_accepts_real_claude_stream_shape(tmp_path: Path):
    output = tmp_path / "claude.jsonl"
    _write_jsonl(output, _claude_positive_events())
    result = _run_function("abda_mcp_read_validate_claude_positive", output, "0")
    assert result.returncode == 0, result.stderr

    changed = _claude_positive_events()
    changed[-1]["structured_output"]["example_count"] = 3
    _write_jsonl(output, changed)
    result = _run_function("abda_mcp_read_validate_claude_positive", output, "0")
    assert result.returncode != 0
    assert "inconsistent" in result.stderr


def test_mcp_read_gate_accepts_claude_revocation_and_rejects_access(
    tmp_path: Path,
):
    output = tmp_path / "claude-revoked.jsonl"
    _write_jsonl(
        output,
        [
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "structured-false",
                            "name": "StructuredOutput",
                        }
                    ]
                },
            },
            {
                "type": "result",
                "is_error": False,
                "structured_output": {"success": False, "example_count": 0},
            },
        ],
    )
    result = _run_function("abda_mcp_read_validate_claude_revoked", output, "0")
    assert result.returncode == 0, result.stderr

    _write_jsonl(output, _claude_positive_events())
    result = _run_function("abda_mcp_read_validate_claude_revoked", output, "0")
    assert result.returncode != 0
    assert "after token revocation" in result.stderr


def test_mcp_read_gate_validates_token_without_printing_it():
    token = "abda_mcp_" + "b" * 43
    result = _run_function(
        "abda_mcp_read_validate_token_format",
        environment={"ABDA_NL_MCP_TOKEN": token},
    )
    assert result.returncode == 0, result.stderr
    assert token not in result.stdout
    assert token not in result.stderr

    result = _run_function(
        "abda_mcp_read_validate_token_format",
        environment={"ABDA_NL_MCP_TOKEN": "not-a-token"},
    )
    assert result.returncode != 0
    assert "not-a-token" not in result.stdout
    assert "not-a-token" not in result.stderr
