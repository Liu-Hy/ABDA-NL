"""Tests for the tracked model catalog and portable provider adapters."""
from __future__ import annotations

import json

import httpx
import pytest

from app.llm.catalog import load_model_catalog
from app.llm.providers import (
    GeminiClient,
    LLMProviderError,
    OpenAICompatibleClient,
    OpenAIResponsesClient,
)


def test_catalog_profiles_reference_valid_routes_and_models():
    catalog = load_model_catalog()
    assert catalog.version == 3
    assert set(catalog.profiles) == {"economy", "balanced", "quality"}
    assert "claude-sonnet-5" in catalog.models
    assert "gpt-5.6-sol" in catalog.models
    assert "gemini-3.6-flash" in catalog.models
    assert "gemini-3.7-flash" in catalog.models
    for profile in catalog.profiles.values():
        primary = catalog.routes[profile.primary_route]
        assert catalog.model_for_route(primary).structured_tools is True
        if profile.fallback_route:
            fallback = catalog.routes[profile.fallback_route]
            assert fallback.billing_source == "openrouter-emergency"

    sonnet = catalog.models["claude-sonnet-5"]
    assert sonnet.input_usd_per_million == 2
    fallback = catalog.routes["openrouter-claude-sonnet-5"]
    assert fallback.use_provider_reported_cost is True
    assert str(fallback.billing_multiplier) == "1.055"
    assert catalog.cost_ceiling_for_route(fallback).output_usd_per_million == 15
    assert (
        catalog.profiles["balanced"].fallback_route
        == "openrouter-gemini-3.7-flash"
    )
    assert catalog.byok_defaults["google"].model == "gemini-3.7-flash"
    for candidate in (
        "cloudbank-claude-sonnet-5",
        "cloudbank-gpt-5.6-terra",
        "cloudbank-deepseek-v4-flash",
        "cloudbank-qwen3.6-plus",
    ):
        route = catalog.routes[candidate]
        assert route.provider == "azure-foundry"
        assert route.billing_source == "cloudbank"
        assert route.model_env is not None


def test_catalog_costs_round_up_to_whole_microusd():
    catalog = load_model_catalog()
    model = catalog.models["deepseek-v4-flash"]
    assert model.cost_microusd({"input_tokens": 1}) == 1
    assert model.cost_microusd(
        {"input_tokens": 1_000_000, "output_tokens": 1_000_000}
    ) == 247_800


def test_catalog_costs_mutually_exclusive_cache_categories():
    model = load_model_catalog().models["gpt-5.4-mini"]
    usage = {
        "input_tokens": 70,
        "output_tokens": 35,
        "cache_read_input_tokens": 50,
        "cache_creation_input_tokens": 20,
    }
    assert model.cost_microusd(usage) == 214


def test_catalog_conservative_reservation_uses_full_output_allowance():
    model = load_model_catalog().models["claude-sonnet-4-6"]
    reserved = model.conservative_cost_microusd(
        estimated_input_tokens=10_000,
        max_output_tokens=4_096,
    )
    actual = model.cost_microusd(
        {"input_tokens": 8_000, "output_tokens": 2_000}
    )
    assert reserved == 98_940
    assert reserved > actual


def test_openai_compatible_complete_maps_payload_usage_and_metadata():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "gpt-test-2026",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "Grounded answer"},
                    }
                ],
                "usage": {
                    "prompt_tokens": 120,
                    "completion_tokens": 25,
                    "prompt_tokens_details": {"cached_tokens": 40},
                },
            },
        )

    spec = load_model_catalog().models["gpt-5.4-mini"]
    client = OpenAICompatibleClient(
        model="deployment-name",
        model_spec=spec,
        provider="azure-foundry",
        billing_source="cloudbank",
        route="test-route",
        base_url="https://example.test/openai/v1",
        api_key="secret-test-key",
        auth_style="api-key",
        transport=httpx.MockTransport(handler),
    )
    response = client.complete(
        system=[{"type": "text", "text": "Stable context"}],
        messages=[{"role": "user", "content": "Question"}],
        max_tokens=300,
    )

    assert captured["url"] == "https://example.test/openai/v1/chat/completions"
    assert captured["headers"]["api-key"] == "secret-test-key"
    assert captured["payload"]["model"] == "deployment-name"
    assert captured["payload"]["max_completion_tokens"] == 300
    assert captured["payload"]["messages"][0] == {
        "role": "system",
        "content": "Stable context",
    }
    assert response.text == "Grounded answer"
    assert response.usage["input_tokens"] == 80
    assert response.usage["cache_read_input_tokens"] == 40
    assert response.provider == "azure-foundry"
    assert response.billing_source == "cloudbank"
    assert response.route == "test-route"


def test_openai_compatible_rejects_empty_billed_text():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "   "},
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 2,
                    "cost": 0.0002,
                },
            },
        )

    client = OpenAICompatibleClient(
        model="google/gemini-3.7-flash",
        model_spec=load_model_catalog().models["gemini-3.7-flash"],
        provider="openrouter",
        billing_source="openrouter-emergency",
        route="fallback",
        base_url="https://openrouter.test/api/v1",
        api_key="secret",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(LLMProviderError) as caught:
        client.complete(
            system="system",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=10,
        )

    assert caught.value.error_type == "invalid_response"
    assert caught.value.retryable is False
    assert caught.value.outage_candidate is False
    assert caught.value.usage["input_tokens"] == 100
    assert caught.value.provider_cost_microusd == 200


def test_openai_compatible_returns_structured_refusal_text():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "refusal": "I cannot help with that request.",
                        },
                    }
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 8},
            },
        )

    client = OpenAICompatibleClient(
        model="gpt-5.4-mini",
        model_spec=load_model_catalog().models["gpt-5.4-mini"],
        provider="openai",
        billing_source="byok",
        route="byok:openai:gpt-5.4-mini",
        base_url="https://openai.test/v1",
        api_key="secret",
        transport=httpx.MockTransport(handler),
    )

    response = client.complete(
        system="system",
        messages=[{"role": "user", "content": "question"}],
        max_tokens=20,
    )

    assert response.text == "I cannot help with that request."


def test_openai_compatible_tool_call_forces_named_function():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "claude-sonnet-5",
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "tool_calls": [
                                {
                                    "type": "function",
                                    "function": {
                                        "name": "add_fact",
                                        "arguments": '{"id":"new_fact","description":"New fact"}',
                                    },
                                }
                            ]
                        },
                    }
                ],
                "usage": {"prompt_tokens": 90, "completion_tokens": 15},
            },
        )

    spec = load_model_catalog().models["claude-sonnet-5"]
    client = OpenAICompatibleClient(
        model="anthropic/claude-sonnet-5",
        model_spec=spec,
        provider="openrouter",
        billing_source="byok",
        route="byok:openrouter",
        base_url="https://openrouter.test/api/v1",
        api_key="or-test-key",
        transport=httpx.MockTransport(handler),
    )
    result = client.tool_call(
        system="system",
        messages=[{"role": "user", "content": "Add a fact"}],
        tool={
            "name": "add_fact",
            "description": "Create one fact",
            "input_schema": {
                "type": "object",
                "properties": {"id": {"type": "string"}},
                "required": ["id"],
            },
        },
        max_tokens=200,
    )

    payload = captured["payload"]
    assert payload["tool_choice"]["function"]["name"] == "add_fact"
    assert "parallel_tool_calls" not in payload
    assert payload["tools"][0]["function"]["parameters"]["required"] == ["id"]
    assert result.tool_name == "add_fact"
    assert result.tool_input["id"] == "new_fact"


def test_openrouter_reports_exact_cost_and_receives_safe_provider_preferences():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "openai/gpt-5.6-luna",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "Answer"},
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "cost": 0.000321,
                },
            },
        )

    preferences = {
        "sort": "price",
        "require_parameters": True,
        "data_collection": "deny",
        "max_price": {"prompt": 0.2, "completion": 1.2},
    }
    client = OpenAICompatibleClient(
        model="openai/gpt-5.6-luna",
        model_spec=load_model_catalog().models["gpt-5.6-luna"],
        provider="openrouter",
        billing_source="openrouter-emergency",
        route="openrouter-gpt-5.6-luna",
        base_url="https://openrouter.test/api/v1",
        api_key="or-test-key",
        provider_preferences=preferences,
        transport=httpx.MockTransport(handler),
    )
    response = client.complete(
        system="system",
        messages=[{"role": "user", "content": "Question"}],
        max_tokens=100,
    )

    assert captured["payload"]["provider"] == preferences
    assert response.provider_cost_microusd == 321


def test_openrouter_http_200_provider_error_is_typed_and_meterable():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "error": {
                    "code": 429,
                    "message": "sensitive upstream detail",
                    "metadata": {"error_type": "rate_limit_exceeded"},
                },
                "choices": [],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 0,
                    "cost": 0.0001,
                },
            },
        )

    client = OpenAICompatibleClient(
        model="openai/gpt-5.6-luna",
        model_spec=load_model_catalog().models["gpt-5.6-luna"],
        provider="openrouter",
        billing_source="openrouter-emergency",
        route="openrouter-gpt-5.6-luna",
        base_url="https://openrouter.test/api/v1",
        api_key="or-test-key",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(LLMProviderError) as caught:
        client.complete(
            system="system",
            messages=[{"role": "user", "content": "Question"}],
            max_tokens=100,
        )

    error = caught.value
    assert error.status_code == 429
    assert error.error_type == "rate_limit_exceeded"
    assert error.retryable is True
    assert error.outage_candidate is True
    assert error.provider_cost_microusd == 100
    assert error.usage["input_tokens"] == 100
    assert "sensitive upstream detail" not in str(error)


@pytest.mark.parametrize("status", [408, 429, 500, 503])
def test_openai_compatible_classifies_service_failures_for_retry(status):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {"message": "do not expose this"}})

    spec = load_model_catalog().models["gpt-5.6-luna"]
    client = OpenAICompatibleClient(
        model="openai/gpt-5.6-luna",
        model_spec=spec,
        provider="openrouter",
        billing_source="openrouter-emergency",
        route="fallback",
        base_url="https://openrouter.test/api/v1",
        api_key="secret",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(LLMProviderError) as caught:
        client.complete(
            system="system",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=10,
        )
    assert caught.value.retryable is True
    assert caught.value.outage_candidate is True
    assert caught.value.billing_uncertain is False
    assert "do not expose" not in str(caught.value)


@pytest.mark.parametrize(
    ("error_type", "billing_uncertain"),
    [
        (httpx.ConnectTimeout, False),
        (httpx.ConnectError, False),
        (httpx.ReadTimeout, True),
        (httpx.WriteError, True),
    ],
)
def test_openai_compatible_distinguishes_predispatch_and_ambiguous_transport_failures(
    error_type,
    billing_uncertain,
):
    def handler(request: httpx.Request) -> httpx.Response:
        raise error_type("synthetic transport failure", request=request)

    client = OpenAICompatibleClient(
        model="openai/gpt-5.6-luna",
        model_spec=load_model_catalog().models["gpt-5.6-luna"],
        provider="openrouter",
        billing_source="openrouter-emergency",
        route="fallback",
        base_url="https://openrouter.test/api/v1",
        api_key="secret",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(LLMProviderError) as caught:
        client.complete(
            system="system",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=10,
        )

    assert caught.value.retryable is True
    assert caught.value.outage_candidate is True
    assert caught.value.billing_uncertain is billing_uncertain


def test_openai_compatible_marks_invalid_success_response_as_billing_uncertain():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    client = OpenAICompatibleClient(
        model="openai/gpt-5.6-luna",
        model_spec=load_model_catalog().models["gpt-5.6-luna"],
        provider="openrouter",
        billing_source="openrouter-emergency",
        route="fallback",
        base_url="https://openrouter.test/api/v1",
        api_key="secret",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(LLMProviderError) as caught:
        client.complete(
            system="system",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=10,
        )

    assert caught.value.billing_uncertain is True


def test_openrouter_tool_validation_failure_preserves_usage_and_cost():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "not a tool"},
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 10,
                    "cost": 0.0002,
                },
            },
        )

    client = OpenAICompatibleClient(
        model="google/gemini-3.7-flash",
        model_spec=load_model_catalog().models["gemini-3.7-flash"],
        provider="openrouter",
        billing_source="openrouter-emergency",
        route="fallback",
        base_url="https://openrouter.test/api/v1",
        api_key="secret",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(LLMProviderError) as caught:
        client.tool_call(
            system="system",
            messages=[{"role": "user", "content": "hi"}],
            tool={"name": "propose", "input_schema": {"type": "object"}},
            max_tokens=10,
        )

    assert caught.value.usage["input_tokens"] == 100
    assert caught.value.usage["output_tokens"] == 10
    assert caught.value.provider_cost_microusd == 200
    assert caught.value.billing_uncertain is False


def test_openrouter_malformed_usage_is_a_conservative_validation_failure():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": "malformed"}],
                "usage": "malformed",
            },
        )

    client = OpenAICompatibleClient(
        model="google/gemini-3.7-flash",
        model_spec=load_model_catalog().models["gemini-3.7-flash"],
        provider="openrouter",
        billing_source="openrouter-emergency",
        route="fallback",
        base_url="https://openrouter.test/api/v1",
        api_key="secret",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(LLMProviderError) as caught:
        client.tool_call(
            system="system",
            messages=[{"role": "user", "content": "hi"}],
            tool={"name": "propose", "input_schema": {"type": "object"}},
            max_tokens=10,
        )

    assert caught.value.usage == {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    }
    assert caught.value.provider_cost_microusd is None
    assert caught.value.billing_uncertain is True


def test_openai_compatible_does_not_fail_over_on_authentication_error():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    spec = load_model_catalog().models["gpt-5.6-luna"]
    client = OpenAICompatibleClient(
        model="model",
        model_spec=spec,
        provider="openrouter",
        billing_source="byok",
        route="byok",
        base_url="https://openrouter.test/api/v1",
        api_key="secret",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(LLMProviderError) as caught:
        client.complete(
            system="system",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=10,
        )
    assert caught.value.retryable is False
    assert caught.value.outage_candidate is False


def test_openai_responses_complete_uses_privacy_and_reasoning_fields():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "model": "gpt-5.6-terra-2026-07-09",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": "Native response"}
                        ],
                    }
                ],
                "usage": {
                    "input_tokens": 140,
                    "output_tokens": 35,
                    "input_tokens_details": {
                        "cached_tokens": 50,
                        "cache_write_tokens": 20,
                    },
                },
            },
        )

    spec = load_model_catalog().models["gpt-5.6-terra"]
    client = OpenAIResponsesClient(
        model="gpt-5.6-terra",
        model_spec=spec,
        provider="openai",
        billing_source="byok",
        route="byok:openai:gpt-5.6-terra",
        base_url="https://api.openai.test/v1",
        api_key="test-key",
        reasoning_effort="low",
        safety_identifier="privacy-preserving-id",
        transport=httpx.MockTransport(handler),
    )
    result = client.complete(
        system="Ground the answer",
        messages=[{"role": "user", "content": "Question"}],
        max_tokens=400,
    )
    assert captured["url"] == "https://api.openai.test/v1/responses"
    payload = captured["payload"]
    assert payload["store"] is False
    assert payload["reasoning"] == {"effort": "low"}
    assert payload["safety_identifier"] == "privacy-preserving-id"
    assert payload["max_output_tokens"] == 400
    assert result.text == "Native response"
    assert result.usage["input_tokens"] == 70
    assert result.usage["cache_read_input_tokens"] == 50
    assert result.usage["cache_creation_input_tokens"] == 20


def test_openai_responses_returns_refusal_text():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "refusal",
                                "refusal": "I cannot help with that request.",
                            }
                        ],
                    }
                ],
                "usage": {"input_tokens": 20, "output_tokens": 8},
            },
        )

    client = OpenAIResponsesClient(
        model="gpt-5.6-terra",
        model_spec=load_model_catalog().models["gpt-5.6-terra"],
        provider="openai",
        billing_source="byok",
        route="byok:openai:gpt-5.6-terra",
        base_url="https://api.openai.test/v1",
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )

    response = client.complete(
        system="system",
        messages=[{"role": "user", "content": "question"}],
        max_tokens=20,
    )

    assert response.text == "I cannot help with that request."


def test_openai_responses_tool_call_uses_flat_function_shape():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "model": "gpt-5.5",
                "output": [
                    {
                        "type": "function_call",
                        "name": "review_edit",
                        "call_id": "call-1",
                        "arguments": '{"issues":[]}',
                    }
                ],
                "usage": {"input_tokens": 90, "output_tokens": 10},
            },
        )

    spec = load_model_catalog().models["gpt-5.5"]
    client = OpenAIResponsesClient(
        model="gpt-5.5",
        model_spec=spec,
        provider="azure-foundry",
        billing_source="cloudbank",
        route="cloudbank-gpt-5.5",
        base_url="https://azure.test/openai/v1",
        api_key="test-key",
        auth_style="api-key",
        transport=httpx.MockTransport(handler),
    )
    result = client.tool_call(
        system="Review",
        messages=[{"role": "user", "content": "Review the edit"}],
        tool={
            "name": "review_edit",
            "description": "Review one edit",
            "input_schema": {
                "type": "object",
                "properties": {"issues": {"type": "array"}},
                "required": ["issues"],
                "additionalProperties": False,
            },
        },
        max_tokens=200,
    )
    tool = captured["payload"]["tools"][0]
    assert tool["type"] == "function"
    assert tool["name"] == "review_edit"
    assert "function" not in tool
    assert tool["strict"] is False
    assert captured["payload"]["tool_choice"] == {
        "type": "function",
        "name": "review_edit",
    }
    assert result.tool_input == {"issues": []}


def test_gemini_complete_maps_native_request_and_response():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "modelVersion": "gemini-3.6-flash-001",
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": "Gemini answer"}]},
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 75,
                    "candidatesTokenCount": 12,
                    "cachedContentTokenCount": 20,
                },
            },
        )

    spec = load_model_catalog().models["gemini-3.6-flash"]
    client = GeminiClient(
        model="gemini-3.6-flash",
        model_spec=spec,
        api_key="google-test-key",
        transport=httpx.MockTransport(handler),
    )
    result = client.complete(
        system="Ground answers",
        messages=[
            {"role": "user", "content": "Question"},
            {"role": "assistant", "content": "Earlier answer"},
            {"role": "user", "content": "Follow-up"},
        ],
        max_tokens=500,
    )

    assert captured["url"].endswith("/models/gemini-3.6-flash:generateContent")
    assert captured["headers"]["x-goog-api-key"] == "google-test-key"
    assert captured["payload"]["systemInstruction"]["parts"][0]["text"] == "Ground answers"
    assert [item["role"] for item in captured["payload"]["contents"]] == [
        "user",
        "model",
        "user",
    ]
    assert result.text == "Gemini answer"
    assert result.usage["input_tokens"] == 55
    assert result.usage["cache_read_input_tokens"] == 20


def test_gemini_safety_block_is_not_retried_as_an_outage():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "promptFeedback": {"blockReason": "SAFETY"},
                "usageMetadata": {"promptTokenCount": 18},
            },
        )

    client = GeminiClient(
        model="gemini-3.7-flash",
        model_spec=load_model_catalog().models["gemini-3.7-flash"],
        api_key="google-test-key",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(LLMProviderError) as caught:
        client.complete(
            system="system",
            messages=[{"role": "user", "content": "question"}],
            max_tokens=20,
        )

    assert caught.value.error_type == "content_blocked"
    assert caught.value.retryable is False
    assert caught.value.outage_candidate is False
    assert caught.value.usage["input_tokens"] == 18


def test_gemini_rejects_empty_billed_text():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "MAX_TOKENS",
                        "content": {"parts": []},
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 18,
                    "candidatesTokenCount": 2,
                },
            },
        )

    client = GeminiClient(
        model="gemini-3.7-flash",
        model_spec=load_model_catalog().models["gemini-3.7-flash"],
        api_key="google-test-key",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(LLMProviderError) as caught:
        client.complete(
            system="system",
            messages=[{"role": "user", "content": "question"}],
            max_tokens=20,
        )

    assert caught.value.error_type == "invalid_response"
    assert caught.value.retryable is False
    assert caught.value.usage["output_tokens"] == 2


def test_http_provider_clients_close_their_connection_pools():
    spec = load_model_catalog().models["gemini-3.7-flash"]
    openai = OpenAICompatibleClient(
        model="google/gemini-3.7-flash",
        model_spec=spec,
        provider="openrouter",
        billing_source="byok",
        route="byok:openrouter:gemini-3.7-flash",
        base_url="https://openrouter.test/api/v1",
        api_key="secret",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200)),
    )
    gemini = GeminiClient(
        model="gemini-3.7-flash",
        model_spec=spec,
        api_key="secret",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200)),
    )

    openai.close()
    gemini.close()

    assert openai._client.is_closed is True
    assert gemini._client.is_closed is True


def test_gemini_tool_call_uses_forced_function_calling():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "parts": [
                                {
                                    "functionCall": {
                                        "name": "review_edit",
                                        "args": {"issues": []},
                                    }
                                }
                            ]
                        },
                    }
                ],
                "usageMetadata": {"promptTokenCount": 80, "candidatesTokenCount": 8},
            },
        )

    spec = load_model_catalog().models["gemini-3.6-flash"]
    client = GeminiClient(
        model="gemini-3.6-flash",
        model_spec=spec,
        api_key="google-test-key",
        transport=httpx.MockTransport(handler),
    )
    result = client.tool_call(
        system="Review",
        messages=[{"role": "user", "content": "Review this"}],
        tool={
            "name": "review_edit",
            "input_schema": {
                "type": "object",
                "properties": {"issues": {"type": "array"}},
                "required": ["issues"],
            },
        },
        max_tokens=100,
    )
    forced = captured["payload"]["toolConfig"]["functionCallingConfig"]
    assert forced == {"mode": "ANY", "allowedFunctionNames": ["review_edit"]}
    assert result.tool_input == {"issues": []}
