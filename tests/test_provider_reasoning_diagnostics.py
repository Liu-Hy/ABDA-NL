"""Provider reasoning parity and bounded synthetic parser-failure evidence."""
from __future__ import annotations

import json
from dataclasses import replace

import httpx
import pytest

from app.llm.catalog import load_model_catalog
from app.llm.providers import (
    GeminiClient,
    LLMProviderError,
    OpenAICompatibleClient,
    OpenAIResponsesClient,
)


_TOOL = {"name": "add_fact", "input_schema": {"type": "object"}}
_CALL = {"function": {"name": "add_fact", "arguments": '{"fact":"p"}'}}
_INPUT = {"system": "Synthetic fixture", "messages": [{"role": "user", "content": "Add p"}]}


def _compatible(model_id, provider, handler, *, effort="low"):
    return OpenAICompatibleClient(
        model=f"deployed-{model_id}",
        model_spec=replace(load_model_catalog().models[model_id], reasoning_effort=effort),
        provider=provider, billing_source="cloudbank" if provider == "azure-foundry" else "byok",
        route="synthetic", base_url="https://provider.invalid/v1", api_key="synthetic-test-key",
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.parametrize("method", ["complete", "tool_call"])
@pytest.mark.parametrize("model_id,provider", [
    ("glm-5.3", "azure-foundry"), ("kimi-k3", "azure-foundry"),
    ("gpt-5.6-terra", "openrouter"), ("gpt-5.6-sol", "openrouter"),
    ("gemini-3.8-flash", "openrouter"), ("gemini-3.1-pro-preview", "openrouter"),
    ("glm-5.3", "openrouter"), ("kimi-k3", "openrouter"),
])
def test_provider_wire_preserves_configured_low_effort_and_output_cap(model_id, provider, method):
    captured = {}

    def handler(request):
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "Visible", "tool_calls": [_CALL]}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
        })

    client = _compatible(model_id, provider, handler)
    try:
        kwargs = {**_INPUT, "max_tokens": 2048}
        if method == "tool_call":
            kwargs["tool"] = _TOOL
        getattr(client, method)(**kwargs)
    finally:
        client.close()

    if provider == "openrouter":
        assert captured["reasoning"] == {"effort": "low"}
        assert "reasoning_effort" not in captured
    else:
        assert captured["reasoning_effort"] == "low"
        assert "reasoning" not in captured
    assert "thinking" not in captured
    assert captured[load_model_catalog().models[model_id].max_token_field] == 2048
    if method == "tool_call":
        assert len(captured["tools"]) == 1
        assert captured["tool_choice"] == (
            "required" if model_id == "kimi-k3"
            else {"type": "function", "function": {"name": "add_fact"}}
        )


@pytest.mark.parametrize("provider", ["azure-foundry", "openrouter"])
@pytest.mark.parametrize("model_id", ["claude-sonnet-5", "deepseek-v4-flash-0731"])
def test_unaffected_family_does_not_gain_reasoning_controls(provider, model_id):
    client = _compatible(model_id, provider, lambda _request: httpx.Response(500))
    try:
        payload = client._base_payload(**_INPUT, max_tokens=1024)
    finally:
        client.close()
    assert not {"reasoning", "reasoning_effort", "thinking"} & payload.keys()


@pytest.mark.parametrize("effort", [None, "high"])
def test_explicit_catalog_effort_is_preserved(effort):
    client = _compatible("glm-5.3", "openrouter", lambda _request: httpx.Response(500), effort=effort)
    try:
        payload = client._base_payload(**_INPUT, max_tokens=1024)
    finally:
        client.close()
    assert payload.get("reasoning") == ({"effort": "high"} if effort else None)


@pytest.mark.parametrize("failure", [
    "no_candidate", "malformed_candidates", "empty_text", "missing_tool", "wrong_tool", "invalid_json",
    "non_object", "multiple_tools",
])
def test_compatible_parse_failure_captures_only_visible_evidence(failure):
    function = dict(_CALL["function"], provider_headers="nested-transport-secret")
    message = {
        "content": "Visible partial output", "reasoning_content": "hidden-reasoning-secret",
        "tool_calls": [{"function": function, "provider_metadata": "call-transport-secret"}],
    }
    if failure in {"empty_text", "missing_tool"}:
        message.update(content="", tool_calls=[])
    elif failure == "wrong_tool":
        function["name"] = "unadvertised_tool"
    elif failure == "invalid_json":
        function["arguments"] = '{"fact":'
    elif failure == "non_object":
        function["arguments"] = "[]"
    elif failure == "multiple_tools":
        message["tool_calls"].append(_CALL)
    data = {
        "model": "actual-deployed-model",
        "choices": [] if failure == "no_candidate" else [{"finish_reason": "length", "message": message}],
        "usage": {"prompt_tokens": 40, "completion_tokens": 2048,
                  "prompt_tokens_details": {"cached_tokens": 10},
                  "completion_tokens_details": {"reasoning_tokens": 2000}},
        "headers": "response-transport-secret", "endpoint": "private-endpoint-secret",
    }
    if failure == "malformed_candidates":
        data["choices"] = {"unexpected": "not a candidate list"}
    client = _compatible("kimi-k3", "azure-foundry", lambda _request: httpx.Response(200, json=data))
    try:
        with pytest.raises(LLMProviderError) as caught:
            if failure in {"empty_text", "no_candidate", "malformed_candidates"}:
                client.complete(**_INPUT, max_tokens=2048)
            else:
                client.tool_call(**_INPUT, tool=_TOOL, max_tokens=2048)
    finally:
        client.close()

    error = caught.value
    assert error.error_type == "invalid_response"
    assert not error.retryable and not error.outage_candidate
    diagnostic = error.diagnostics
    assert set(diagnostic) == {"finish_reason", "requested_max_tokens", "actual_model",
                               "visible_content", "tool_calls", "usage", "reasoning_tokens"}
    assert diagnostic["finish_reason"] == (
        None if failure in {"no_candidate", "malformed_candidates"} else "length"
    )
    assert diagnostic["requested_max_tokens"] == 2048
    assert diagnostic["actual_model"] == "actual-deployed-model"
    assert diagnostic["reasoning_tokens"] == 2000
    assert diagnostic["usage"] == error.usage
    assert error.usage["output_tokens"] == 2048
    assert error.usage["input_tokens"] == 30
    if failure == "invalid_json":
        assert diagnostic["tool_calls"][0]["function"]["arguments"] == '{"fact":'
    elif failure == "multiple_tools":
        assert len(diagnostic["tool_calls"]) == 2
    serialized = json.dumps(diagnostic)
    assert "secret" not in serialized
    assert "Visible partial output" not in str(error)
    assert "actual-deployed-model" not in str(error)


def test_responses_failure_excludes_reasoning_items_and_preserves_visible_tool_arguments():
    data = {
        "model": "actual-sol", "status": "incomplete",
        "incomplete_details": {"reason": "max_output_tokens"},
        "output": [
            {"type": "reasoning", "summary": "hidden-reasoning-secret", "encrypted_content": "secret"},
            {"type": "message", "content": [{"type": "output_text", "text": "Visible partial"}]},
            {"type": "function_call", "name": "add_fact", "arguments": '{"fact":'},
        ],
        "usage": {"input_tokens": 20, "output_tokens": 1024,
                  "output_tokens_details": {"reasoning_tokens": 1000}},
    }
    client = OpenAIResponsesClient(
        model="gpt-5.6-sol", model_spec=load_model_catalog().models["gpt-5.6-sol"],
        provider="azure-foundry", billing_source="cloudbank", route="synthetic",
        base_url="https://provider.invalid/v1", api_key="synthetic-test-key",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=data)),
    )
    try:
        with pytest.raises(LLMProviderError) as caught:
            client.tool_call(**_INPUT, tool=_TOOL, max_tokens=1024)
    finally:
        client.close()
    diagnostic = caught.value.diagnostics
    assert diagnostic["visible_content"] == "Visible partial"
    assert diagnostic["finish_reason"] == "max_output_tokens"
    assert diagnostic["reasoning_tokens"] == 1000
    assert diagnostic["tool_calls"][0]["function"]["arguments"] == '{"fact":'
    assert "secret" not in json.dumps(diagnostic)


@pytest.mark.parametrize("method", ["complete", "tool_call"])
def test_gemini_failure_excludes_thought_parts_but_counts_their_usage(method):
    data = {
        "modelVersion": "actual-gemini",
        "candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [
            {"thought": True, "text": "hidden-reasoning-secret"},
        ]}}],
        "usageMetadata": {"promptTokenCount": 20, "candidatesTokenCount": 5,
                          "thoughtsTokenCount": 1019},
    }
    client = GeminiClient(
        model="gemini-3.8-flash", model_spec=load_model_catalog().models["gemini-3.8-flash"],
        api_key="synthetic-test-key",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=data)),
    )
    try:
        with pytest.raises(LLMProviderError) as caught:
            kwargs = {**_INPUT, "max_tokens": 1024}
            if method == "tool_call":
                kwargs["tool"] = _TOOL
            getattr(client, method)(**kwargs)
    finally:
        client.close()
    diagnostic = caught.value.diagnostics
    assert caught.value.error_type == "invalid_response"
    assert diagnostic["visible_content"] == ""
    assert diagnostic["finish_reason"] == "MAX_TOKENS"
    assert diagnostic["reasoning_tokens"] == 1019
    assert diagnostic["usage"]["output_tokens"] == 1024
    assert "secret" not in json.dumps(diagnostic)


@pytest.mark.parametrize("byok", [False, True])
def test_synthetic_diagnostics_are_not_exposed_in_http_errors(byok):
    from app.api.llm_access import llm_http_exception

    error = LLMProviderError(
        "Provider returned invalid tool arguments", provider="azure-foundry",
        error_type="invalid_response",
        diagnostics={"visible_content": "private synthetic output"},
    )
    response = llm_http_exception(error, byok=byok)
    assert "private synthetic output" not in json.dumps(response.detail)
    assert "diagnostics" not in json.dumps(response.detail)
