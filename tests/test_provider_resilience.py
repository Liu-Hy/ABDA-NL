"""Physical timeout, provider failure, and credential isolation contracts."""

from dataclasses import replace
from email.utils import formatdate
import json
import threading
import time
from types import SimpleNamespace

import anthropic
from fastapi import HTTPException
import httpx
import pytest
from sqlalchemy.exc import TimeoutError as DatabaseTimeoutError

from app.core.config import Settings
from app.llm.catalog import load_model_catalog
from app.llm.client import (
    ClaudeClient,
    LLMRequestDeadlineError,
    invoke_before_deadline,
    request_timeout,
)
from app.llm.providers import (
    GeminiClient,
    LLMProviderError,
    OpenAICompatibleClient,
    OpenAIResponsesClient,
    VertexGeminiClient,
    parse_retry_after,
)
from app.llm.routing import (
    CallContext,
    CircuitRegistry,
    FailoverClient,
    LLMRouteConfigurationError,
    LLMRouter,
    RetryingClient,
    _classified_error,
)


CALL = {
    "system": "system",
    "messages": [{"role": "user", "content": "question"}],
    "max_tokens": 128,
}


def provider_client(kind, handler):
    catalog = load_model_catalog()
    transport = httpx.MockTransport(handler)
    if kind == "vertex":
        return VertexGeminiClient(
            model="gemini-3.8-flash",
            model_spec=catalog.models["gemini-3.8-flash"],
            project="funded-project",
            token_provider=lambda: "test-token",
            transport=transport,
        )
    if kind == "gemini":
        return GeminiClient(
            model="gemini-3.8-flash",
            model_spec=catalog.models["gemini-3.8-flash"],
            api_key="test-key",
            transport=transport,
        )
    cls = OpenAIResponsesClient if kind == "responses" else OpenAICompatibleClient
    return cls(
        model="deployment",
        model_spec=catalog.models["gpt-5.6-sol"],
        provider="azure-foundry",
        billing_source="cloudbank",
        route="test-route",
        base_url="https://provider.test/v1",
        api_key="test-key",
        transport=transport,
        timeout_seconds=45,
    )


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1.25", 1.25),
        ("99999", 2),
        ("-5", 0),
        ("nan", None),
        ("inf", None),
        ("invalid", None),
        ("1" * 129, None),
    ],
)
def test_retry_after_seconds_are_sanitized_and_bounded(raw, expected):
    assert parse_retry_after(httpx.Headers({"Retry-After": raw})) == expected


def test_retry_after_supports_http_dates_and_millisecond_headers():
    assert (
        parse_retry_after(httpx.Headers({"retry-after": formatdate(1001, usegmt=True)}), now=1000)
        == 1
    )
    assert parse_retry_after(httpx.Headers({"x-ms-retry-after-ms": "1500"})) == 1.5
    assert parse_retry_after(httpx.Headers({"retry-after-ms": "250"})) == 0.25


@pytest.mark.parametrize("kind", ["compatible", "responses", "gemini", "vertex"])
def test_http_retryable_failure_carries_bounded_retry_after(kind):
    client = provider_client(
        kind,
        lambda _r: httpx.Response(
            503, headers={"retry-after": "600"}, json={"error": {"message": "unavailable"}}
        ),
    )
    try:
        with pytest.raises(LLMProviderError) as caught:
            client.complete(**CALL)
    finally:
        client.close()
    assert caught.value.retryable and caught.value.outage_candidate
    assert caught.value.retry_after_seconds == 2


@pytest.mark.parametrize("kind", ["compatible", "responses", "gemini", "vertex"])
@pytest.mark.parametrize(
    "error_type",
    ["quota_exceeded", "insufficient_quota", "billing_hard_limit_reached", "insufficient_credits"],
)
def test_provider_quota_429_is_an_api_failure(kind, error_type):
    client = provider_client(
        kind,
        lambda _r: httpx.Response(
            429, headers={"retry-after": "1"}, json={"error": {"type": error_type}}
        ),
    )
    try:
        with pytest.raises(LLMProviderError) as caught:
            client.complete(**CALL)
    finally:
        client.close()
    assert caught.value.retryable and caught.value.outage_candidate
    assert caught.value.retry_after_seconds == 1


@pytest.mark.parametrize(
    "exc",
    [
        DatabaseTimeoutError("accounting busy"),
        ConnectionError("database offline"),
        HTTPException(status_code=503),
        HTTPException(status_code=401),
    ],
)
def test_only_actual_provider_exception_types_can_authorize_retry(exc):
    assert _classified_error(exc, "azure-foundry") is None


def test_anthropic_status_and_transport_errors_keep_provider_classification():
    request = httpx.Request("POST", "https://provider.test/messages")
    response = httpx.Response(429, headers={"retry-after": "1.5"}, request=request)
    error = anthropic.RateLimitError(
        "rate limited", response=response, body={"type": "rate_limit_error"}
    )
    classified = _classified_error(error, "azure-foundry")
    assert classified.retry_after_seconds == 1.5
    assert classified.retryable and classified.outage_candidate
    timeout = anthropic.APITimeoutError(request=request)
    assert _classified_error(timeout, "azure-foundry").billing_uncertain


def test_absolute_deadline_is_distinct_from_a_physical_timeout():
    error = _classified_error(
        LLMRequestDeadlineError(provider="azure-foundry", billing_uncertain=True), "azure-foundry"
    )
    assert error.error_type == "request_deadline" and error.billing_uncertain
    assert not error.retryable and not error.outage_candidate


@pytest.mark.parametrize("kind", ["compatible", "responses", "gemini", "vertex"])
def test_every_http_phase_uses_remaining_request_time(kind):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(503, json={"error": {"message": "unavailable"}})

    client = provider_client(kind, handler)
    client.request_deadline = time.monotonic() + 0.5
    try:
        with pytest.raises(LLMProviderError):
            client.complete(**CALL)
    finally:
        client.close()
    assert all(0 < value <= 0.5 for value in requests[0].extensions["timeout"].values())


def test_timeout_clipping_never_extends_the_existing_physical_limit():
    timeout = request_timeout(
        httpx.Timeout(45, connect=10), time.monotonic() + 100, provider="azure-foundry"
    )
    assert timeout.connect == 10 and timeout.read == 45


def test_claude_stream_uses_remaining_request_time():
    observed = {}

    class Stream:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get_final_message(self):
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text="answer")],
                usage=SimpleNamespace(input_tokens=1, output_tokens=1),
                stop_reason="end_turn",
            )

    def stream(**kwargs):
        observed.update(kwargs)
        return Stream()

    client = object.__new__(ClaudeClient)
    client._client = SimpleNamespace(messages=SimpleNamespace(stream=stream))
    client.model, client.provider, client.billing_source, client.route = (
        "test",
        "foundry",
        "cloudbank",
        "test",
    )
    client.request_deadline = time.monotonic() + 0.5
    client.complete(**CALL)
    assert all(0 < value <= 0.5 for value in observed["timeout"].as_dict().values())


def test_wall_clock_guard_stops_a_continuously_active_provider_and_closes_it():
    release, finished = threading.Event(), threading.Event()

    class StreamingClient:
        def close(self):
            release.set()

    def call():
        try:
            release.wait(2)
            return "late output"
        finally:
            finished.set()

    before = time.monotonic()
    try:
        with pytest.raises(LLMRequestDeadlineError) as caught:
            invoke_before_deadline(
                call, deadline=before + 0.05, provider="azure-foundry", client=StreamingClient()
            )
        assert time.monotonic() - before < 0.75
        assert caught.value.billing_uncertain
        assert finished.wait(0.5)
    finally:
        release.set()


def test_wall_clock_guard_never_dispatches_after_deadline():
    calls = []
    with pytest.raises(LLMRequestDeadlineError) as caught:
        invoke_before_deadline(
            lambda: calls.append(True),
            deadline=time.monotonic() - 1,
            provider="azure-foundry",
            client=SimpleNamespace(),
        )
    assert not calls and not caught.value.billing_uncertain


def test_vertex_auth_finishing_after_deadline_never_dispatches_paid_request():
    calls = []
    client = provider_client("vertex", lambda r: calls.append(r))

    def auth():
        client.request_deadline = time.monotonic() - 1
        return "test-token"

    client._token_provider = auth
    client.request_deadline = time.monotonic() + 1
    try:
        with pytest.raises(LLMRequestDeadlineError) as caught:
            client.complete(**CALL)
    finally:
        client.close()
    assert not calls and not caught.value.billing_uncertain


def test_vertex_counts_all_generated_tokens_and_keeps_one_total_ceiling():
    captured = {}

    def handler(request):
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": "answer"}]}}],
                "usageMetadata": {
                    "promptTokenCount": 100,
                    "cachedContentTokenCount": 20,
                    "candidatesTokenCount": 30,
                    "totalTokenCount": 170,
                },
            },
        )

    client = provider_client("vertex", handler)
    try:
        answer = client.complete(**CALL)
    finally:
        client.close()
    assert answer.usage["input_tokens"] == 80 and answer.usage["output_tokens"] == 70
    generation = captured["generationConfig"]
    assert generation["maxOutputTokens"] == CALL["max_tokens"]
    assert generation["candidateCount"] == 1 and generation["thinkingConfig"] == {
        "thinkingLevel": "LOW"
    }


@pytest.mark.parametrize("body", [{"promptFeedback": {"blockReason": "SAFETY"}}, {}])
def test_vertex_candidate_failures_retain_provider_and_do_not_authorize_backup(body):
    client = provider_client("vertex", lambda _r: httpx.Response(200, json=body))
    try:
        with pytest.raises(LLMProviderError) as caught:
            client.complete(**CALL)
    finally:
        client.close()
    assert caught.value.provider == "gcp-vertex"
    assert not caught.value.retryable and not caught.value.outage_candidate


class Outcomes:
    model, provider, billing_source, route = (
        "same-model",
        "azure-foundry",
        "cloudbank",
        "deadline-route",
    )

    def __init__(self, outcomes):
        self.outcomes, self.calls = iter(outcomes), 0

    def complete(self, **_kwargs):
        self.calls += 1
        outcome = next(self.outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        if callable(outcome):
            return outcome()
        return outcome


def test_retry_delay_is_clipped_to_remaining_absolute_budget(monkeypatch):
    now, delays = [100.0], []
    monkeypatch.setattr("app.llm.routing.time.monotonic", lambda: now[0])

    def sleep(delay):
        delays.append(delay)
        now[0] += delay

    monkeypatch.setattr("app.llm.routing.time.sleep", sleep)
    primary = Outcomes(
        [
            LLMProviderError(
                "busy",
                provider="azure-foundry",
                retryable=True,
                outage_candidate=True,
                retry_after_seconds=2,
            )
        ]
    )
    fallback = Outcomes(["backup"])
    client = FailoverClient(
        RetryingClient(primary, attempts=2, deadline=100.5),
        fallback,
        cooldown_seconds=15,
        circuits=CircuitRegistry(),
        deadline=100.5,
    )
    with pytest.raises(LLMProviderError, match="deadline"):
        client.complete()
    assert delays == [0.5] and primary.calls == 1 and fallback.calls == 0


def test_correction_call_reuses_original_absolute_deadline(monkeypatch):
    now = [100.0]
    monkeypatch.setattr("app.llm.routing.time.monotonic", lambda: now[0])
    primary, fallback = Outcomes(["first response", "correction"]), Outcomes(["backup"])
    client = FailoverClient(
        primary, fallback, cooldown_seconds=15, circuits=CircuitRegistry(), deadline=101
    )
    assert client.complete() == "first response"
    now[0] = 101
    with pytest.raises(LLMProviderError, match="deadline"):
        client.complete()
    assert primary.calls == 1 and fallback.calls == 0


def test_unclassified_failure_during_half_open_probe_keeps_controlled_recovery(monkeypatch):
    now = [100.0]
    monkeypatch.setattr("app.llm.routing.time.monotonic", lambda: now[0])
    registry = CircuitRegistry()
    registry.open("deadline-route", 1)
    now[0] = 102
    client = FailoverClient(
        Outcomes([DatabaseTimeoutError("accounting unavailable")]),
        Outcomes(["backup"]),
        cooldown_seconds=15,
        circuits=registry,
    )
    with pytest.raises(DatabaseTimeoutError):
        client.complete()
    assert registry.primary_allowed("deadline-route")
    assert not registry.primary_allowed("deadline-route")


@pytest.mark.parametrize(
    "adapter,client_name",
    [
        ("anthropic", "ClaudeClient"),
        ("openai-responses", "OpenAIResponsesClient"),
        ("openai-compatible", "OpenAICompatibleClient"),
    ],
)
def test_azure_route_override_uses_its_own_endpoint_and_key(monkeypatch, adapter, client_name):
    captured = {}
    monkeypatch.setattr(f"app.llm.routing.{client_name}", lambda **kw: captured.update(kw))
    monkeypatch.setenv("REVISION_ROUTE_ENDPOINT", "https://opus-resource.services.ai.azure.com")
    monkeypatch.setenv("REVISION_ROUTE_KEY", "specific-test-key")
    catalog = load_model_catalog()
    route = replace(
        catalog.routes[catalog.profiles["balanced"].primary_route],
        adapter=adapter,
        endpoint_env="REVISION_ROUTE_ENDPOINT",
        api_key_env="REVISION_ROUTE_KEY",
    )
    router = LLMRouter(
        catalog=catalog, settings=Settings.from_environment(), session_factory=object()
    )
    router._raw_route(route, user_id=None)
    assert captured["api_key"] == "specific-test-key"
    assert captured["base_url"] == "https://opus-resource.services.ai.azure.com/" + (
        "anthropic" if adapter == "anthropic" else "openai/v1"
    )
    if adapter == "anthropic":
        assert captured["auth_token"] is None


@pytest.mark.parametrize(
    "endpoint",
    [
        None,
        "http://resource.services.ai.azure.com",
        "https://example.org",
        "https://resource.services.ai.azure.com.evil.test",
        "https://user@resource.services.ai.azure.com",
        "https://resource.services.ai.azure.com?key=bad",
        "https://resource.services.ai.azure.com:8000",
    ],
)
def test_azure_route_override_rejects_missing_or_non_azure_endpoint(monkeypatch, endpoint):
    if endpoint is None:
        monkeypatch.delenv("REVISION_ROUTE_ENDPOINT", raising=False)
    else:
        monkeypatch.setenv("REVISION_ROUTE_ENDPOINT", endpoint)
    monkeypatch.setenv("REVISION_ROUTE_KEY", "specific-test-key")
    catalog = load_model_catalog()
    route = replace(
        catalog.routes[catalog.profiles["balanced"].primary_route],
        endpoint_env="REVISION_ROUTE_ENDPOINT",
        api_key_env="REVISION_ROUTE_KEY",
    )
    router = LLMRouter(
        catalog=catalog, settings=Settings.from_environment(), session_factory=object()
    )
    with pytest.raises(LLMRouteConfigurationError):
        router._raw_route(route, user_id=None)


def test_unexpected_client_construction_failure_does_not_authorize_backup(monkeypatch):
    router = LLMRouter(
        catalog=load_model_catalog(), settings=Settings.from_environment(), session_factory=object()
    )

    def fail(*_args, **_kwargs):
        raise RuntimeError("accounting connection failure")

    monkeypatch.setattr(router, "_metered_retrying", fail)
    with pytest.raises(RuntimeError, match="accounting connection"):
        router.funded("balanced", context=CallContext(None, "request", "chat", False))


@pytest.mark.parametrize("kind", ["compatible", "responses", "gemini", "vertex"])
@pytest.mark.parametrize("body", [{}, []])
def test_invalid_success_envelope_cannot_authorize_provider_switch(kind, body):
    client = provider_client(kind, lambda _request: httpx.Response(200, json=body))
    try:
        with pytest.raises(LLMProviderError) as caught:
            client.complete(**CALL)
    finally:
        client.close()
    assert not caught.value.retryable and not caught.value.outage_candidate


def test_deadline_pool_admission_is_bounded_without_provider_dispatch(monkeypatch):
    import app.llm.client as client_module

    calls = []
    occupied_slot = threading.BoundedSemaphore(1)
    occupied_slot.acquire()
    monkeypatch.setattr(client_module, "_PROVIDER_SLOTS", occupied_slot)
    try:
        with pytest.raises(LLMRequestDeadlineError) as caught:
            invoke_before_deadline(
                lambda: calls.append(True),
                deadline=time.monotonic() + 0.01,
                provider="azure-foundry",
                client=SimpleNamespace(),
            )
    finally:
        occupied_slot.release()
    assert not calls and not caught.value.billing_uncertain


def test_future_result_after_absolute_deadline_is_not_returned(monkeypatch):
    now = [100.0]
    monkeypatch.setattr("app.llm.client.time.monotonic", lambda: now[0])

    def late_result():
        now[0] = 200
        return "late output"

    with pytest.raises(LLMRequestDeadlineError):
        invoke_before_deadline(
            late_result, deadline=101, provider="azure-foundry", client=SimpleNamespace()
        )


@pytest.mark.parametrize(
    "error_type",
    ["quota_exceeded", "insufficient_quota", "billing_hard_limit_reached", "insufficient_credits"],
)
def test_provider_quota_429_retries_cloudbank_then_uses_same_model_backup(monkeypatch, error_type):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(429, json={"error": {"type": error_type}})

    monkeypatch.setattr("app.llm.routing.time.sleep", lambda _seconds: None)
    primary = provider_client("compatible", handler)
    backup = Outcomes(["same model backup"])
    backup.model = primary.model
    client = FailoverClient(
        RetryingClient(primary, attempts=2), backup, cooldown_seconds=15, circuits=CircuitRegistry()
    )
    try:
        assert client.complete(**CALL) == "same model backup"
    finally:
        primary.close()
    assert len(requests) == 2 and backup.calls == 1
    assert all(json.loads(request.content)["model"] == backup.model for request in requests)


def test_vertex_ignores_adc_default_project_and_pins_cloudbank_billing(monkeypatch):
    captured = {}
    requests = []
    credentials = SimpleNamespace(valid=True, token="synthetic-adc-token")

    def default_credentials(**kwargs):
        captured.update(kwargs)
        return credentials, "unrelated-personal-project"

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": "answer"}]}}],
                "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 2},
            },
        )

    monkeypatch.delenv("GOOGLE_VERTEX_ACCESS_TOKEN", raising=False)
    monkeypatch.setattr("google.auth.default", default_credentials)
    client = provider_client("vertex", handler)
    client._token_provider = client._access_token
    try:
        assert client.complete(**CALL).text == "answer"
    finally:
        client.close()
    assert captured["quota_project_id"] == "funded-project"
    assert "/projects/funded-project/" in requests[0].url.path
    assert requests[0].headers["x-goog-user-project"] == "funded-project"
    assert requests[0].headers["authorization"] == "Bearer synthetic-adc-token"
    assert "unrelated-personal-project" not in str(requests[0].url)
