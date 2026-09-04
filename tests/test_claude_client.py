"""Anthropic client response and retry-accounting boundaries."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.llm.client import ClaudeClient, LLMResponseValidationError


class _CompletedStream:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def get_final_message(self):
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="not a tool call")],
            stop_reason="end_turn",
            usage=SimpleNamespace(
                input_tokens=120,
                output_tokens=8,
                cache_read_input_tokens=20,
                cache_creation_input_tokens=5,
            ),
        )


class _CompletedMessages:
    def stream(self, **_kwargs):
        return _CompletedStream()


def test_claude_tool_validation_failure_preserves_billable_usage():
    client = object.__new__(ClaudeClient)
    client._client = SimpleNamespace(messages=_CompletedMessages())
    client.model = "claude-test"
    client.provider = "foundry"
    client.billing_source = "cloudbank"
    client.route = "test-route"

    with pytest.raises(LLMResponseValidationError) as caught:
        client.tool_call(
            system="system",
            messages=[{"role": "user", "content": "question"}],
            tool={"name": "answer", "input_schema": {"type": "object"}},
            max_tokens=32,
        )

    assert caught.value.usage == {
        "input_tokens": 120,
        "output_tokens": 8,
        "cache_read_input_tokens": 20,
        "cache_creation_input_tokens": 5,
    }
    assert caught.value.provider_cost_microusd is None
    assert caught.value.billing_uncertain is False
    assert caught.value.error_type == "invalid_response"


def test_managed_claude_disables_sdk_internal_retries(monkeypatch):
    captured = {}

    class _Anthropic:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("anthropic.Anthropic", _Anthropic)
    client = ClaudeClient(
        model="claude-test",
        provider="foundry",
        api_key="test-key",
        base_url="https://example.invalid/anthropic",
        sdk_max_retries=0,
    )

    assert client.model == "claude-test"
    assert captured["max_retries"] == 0
