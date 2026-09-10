"""Acceptance receipts require actual, bounded client tool evidence."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.cli.mcp_client_acceptance import (
    AcceptanceError, EDIT, _client_environment, _endpoint, client_command,
    client_failure_message, require_subscription_auth, transcript_calls, verify_client_workflow,
)


def _workflow():
    return [
        {"name": "list_examples", "arguments": {}},
        {"name": "get_example", "arguments": {"scenario_id": "fire_prevention"}},
        {"name": "create_project", "arguments": {"name": "Disposable", "source_scenario_id": "fire_prevention"}},
        {"name": "get_project", "arguments": {"project_id": "created-id"}},
        {"name": "apply_project_ops", "arguments": {"project_id": "created-id", "expected_version": 1, "diff_ops": [EDIT]}},
        {"name": "get_project", "arguments": {"project_id": "created-id"}},
    ]


def _transcript(client, calls):
    events = []
    for index, call in enumerate(calls):
        if client == "codex":
            events.append({"type": "item.completed", "item": {
                "type": "mcp_tool_call", "server": "abda_nl", "tool": call["name"],
                "arguments": call["arguments"], "status": "completed", "error": None,
                "result": {"content": [{"type": "text", "text": "successful tool result"}]},
            }})
        else:
            events.extend([
                {"type": "assistant", "message": {"content": [{
                    "type": "tool_use", "name": f"mcp__abda_nl__{call['name']}",
                    "id": str(index), "input": call["arguments"],
                }]}},
                {"type": "user", "message": {"content": [{
                    "type": "tool_result", "tool_use_id": str(index), "content": "successful tool result",
                }]}},
            ])
    events.append({"type": "turn.completed"} if client == "codex" else {"type": "result", "is_error": False})
    return "\n".join(json.dumps(event) for event in events)


@pytest.mark.parametrize("client", ["codex", "claude-code"])
def test_actual_tool_sequence_is_required_for_success(client):
    calls = transcript_calls(client, _transcript(client, _workflow()))
    verify_client_workflow(calls, {"id": "created-id"}, "Disposable")
    with pytest.raises(AcceptanceError, match="create one project"):
        verify_client_workflow([], {"id": "created-id"}, "Disposable")


@pytest.mark.parametrize("change", ["wrong_project", "extra_edit", "no_readback", "no_explicit_reads", "wrong_operation"])
def test_receipt_rejects_incomplete_or_out_of_scope_workflow(change):
    calls = _workflow()
    if change == "wrong_project":
        calls[3]["arguments"]["project_id"] = "another-private-project"
    elif change == "extra_edit":
        calls.append(calls[4])
    elif change == "no_readback":
        calls.pop()
    elif change == "no_explicit_reads":
        calls = [call for call in calls if call["name"] != "get_project"]
    else:
        calls[4]["arguments"]["diff_ops"] = [{"op": "remove-fact", "id": "heavy_fuels"}]
    with pytest.raises(AcceptanceError):
        verify_client_workflow(calls, {"id": "created-id"}, "Disposable")


@pytest.mark.parametrize("client", ["codex", "claude-code"])
def test_hosted_llm_tool_is_rejected_even_if_client_reports_success(client):
    calls = _workflow() + [{"name": "ask_project", "arguments": {"question": "Oops"}}]
    with pytest.raises(AcceptanceError, match="outside this acceptance"):
        transcript_calls(client, _transcript(client, calls))


def test_tool_errors_cannot_be_hidden_in_codex_success_envelopes():
    transcript = _transcript("codex", _workflow()).splitlines()
    first = json.loads(transcript[0])
    first["item"]["result"] = {"content": [{"type": "text", "text": '{"isError": true}'}]}
    transcript[0] = json.dumps(first)
    with pytest.raises(AcceptanceError, match="successful result"):
        transcript_calls("codex", "\n".join(transcript))


def test_claude_requires_every_tool_result():
    transcript = _transcript("claude-code", _workflow()).splitlines()
    transcript.pop(1)
    with pytest.raises(AcceptanceError, match="tool returned an error"):
        transcript_calls("claude-code", "\n".join(transcript))


def test_claude_refresh_failure_is_actionable_without_echoing_client_output():
    transcript = json.dumps({"type": "result", "is_error": True, "result": (
        "Failed to refresh OAuth token: another Claude Code process is refreshing it. "
        "Potentially sensitive additional output: private-test-value"
    )})
    message = client_failure_message("claude-code", transcript)
    assert "could not refresh its subscription login" in message
    assert "private-test-value" not in message
    for value in ["not JSON private-test-value", json.dumps({"type": "result", "is_error": True, "result": "private-test-value"})]:
        assert "private-test-value" not in client_failure_message("claude-code", value)


def test_subscription_environment_drops_api_keys_and_gateway_settings(monkeypatch):
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL",
                "AZURE_OPENAI_API_KEY", "OPENROUTER_API_KEY", "GOOGLE_API_KEY",
                "CLAUDE_CODE_USE_VERTEX", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(key, "secret-test-value")
    environment = _client_environment()
    assert "secret-test-value" not in environment.values()
    assert environment["HOME"]


@pytest.mark.parametrize("client", ["codex", "claude-code"])
def test_client_command_never_places_credentials_in_arguments(client):
    command = client_command(client, "https://demo.example/mcp/", "ABDA_NL_MCP_TOKEN", Path("/tmp/test"))
    joined = " ".join(command)
    assert "ABDA_NL_MCP_TOKEN" in joined
    assert "ask_project" not in joined and "propose_project_edit" not in joined
    assert "dangerously" not in joined


@pytest.mark.parametrize("url", ["http://public.example/mcp/", "https://secret@example.com/mcp/", "https://example.com/mcp/?token=secret"])
def test_credentials_only_travel_to_validated_endpoints(url):
    with pytest.raises(AcceptanceError):
        _endpoint(url)


def test_loopback_acceptance_is_allowed():
    assert _endpoint("http://127.0.0.1:8765/mcp/") == "http://127.0.0.1:8765/mcp/"


@pytest.mark.parametrize("client", ["codex", "claude-code"])
def test_stored_api_key_auth_cannot_spend_outside_subscription(client, monkeypatch):
    response = "Logged in using an API key" if client == "codex" else json.dumps({
        "loggedIn": True, "authMethod": "api_key", "subscriptionType": None,
    })
    monkeypatch.setattr("app.cli.mcp_client_acceptance.subprocess.run", lambda *args, **kwargs: SimpleNamespace(
        returncode=0, stdout=response, stderr="",
    ))
    with pytest.raises(AcceptanceError, match="requires subscription authentication"):
        require_subscription_auth(client, {})
