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


class _StaticStream:
    def __init__(self, final):
        self.final = final

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def get_final_message(self):
        return self.final


class _StaticMessages:
    def __init__(self, final):
        self.final = final

    def stream(self, **_kwargs):
        return _StaticStream(self.final)


def _usage():
    return SimpleNamespace(
        input_tokens=120,
        output_tokens=8,
        cache_read_input_tokens=20,
        cache_creation_input_tokens=5,
    )


def _client_for_final(final):
    client = object.__new__(ClaudeClient)
    client._client = SimpleNamespace(messages=_StaticMessages(final))
    client.model = "claude-test"
    client.provider = "foundry"
    client.billing_source = "cloudbank"
    client.route = "test-route"
    return client


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


def test_claude_empty_text_preserves_billable_usage():
    client = _client_for_final(
        SimpleNamespace(
            content=[SimpleNamespace(type="text", text="   ")],
            stop_reason="end_turn",
            usage=_usage(),
        )
    )

    with pytest.raises(LLMResponseValidationError) as caught:
        client.complete(
            system="system",
            messages=[{"role": "user", "content": "question"}],
            max_tokens=32,
        )

    assert caught.value.usage["input_tokens"] == 120
    assert caught.value.billing_uncertain is False


@pytest.mark.parametrize(
    "tool_block",
    [
        SimpleNamespace(type="tool_use", name="wrong_tool", input={}),
        SimpleNamespace(type="tool_use", name="answer", input=[]),
    ],
)
def test_claude_malformed_tool_response_preserves_billable_usage(tool_block):
    client = _client_for_final(
        SimpleNamespace(
            content=[tool_block],
            stop_reason="tool_use",
            usage=_usage(),
        )
    )

    with pytest.raises(LLMResponseValidationError) as caught:
        client.tool_call(
            system="system",
            messages=[{"role": "user", "content": "question"}],
            tool={"name": "answer", "input_schema": {"type": "object"}},
            max_tokens=32,
        )

    assert caught.value.usage["output_tokens"] == 8
    assert caught.value.billing_uncertain is False


def test_claude_close_delegates_to_sdk_client():
    closed = []
    client = object.__new__(ClaudeClient)
    client._client = SimpleNamespace(close=lambda: closed.append(True))

    client.close()

    assert closed == [True]
