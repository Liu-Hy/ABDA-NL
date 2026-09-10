"""Regression checks for configuration, deadline, and backup contract findings."""
from dataclasses import replace
import json
import threading
import time
from types import SimpleNamespace

import httpx
import pytest

from app.api.llm_access import HANDLED_LLM_ERRORS, llm_http_exception
from app.core.config import Settings
from app.llm import client as client_module
from app.llm import routing
from app.llm.catalog import _validate_catalog, load_model_catalog
from app.llm.client import ClaudeClient, LLMAccountingUnavailableError, LLMRequestDeadlineError
from app.llm.providers import OpenAICompatibleClient, VertexGeminiClient


def _configuration():
    return {
        "AZURE_OPENAI_API_KEY": "fake-azure-key",
        "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com",
        "AZURE_OPUS5_API_KEY": "fake-opus-key",
        "AZURE_OPUS5_ENDPOINT": "https://opus.services.ai.azure.com",
        "GOOGLE_CLOUD_PROJECT": "funded-project",
        "OPENROUTER_API_KEY": "fake-backup-key",
    }


@pytest.mark.parametrize("missing,route_id", [
    ("AZURE_OPENAI_API_KEY", "cloudbank-claude-sonnet-5"),
    ("AZURE_OPENAI_ENDPOINT", "cloudbank-gpt-5.6-terra"),
    ("AZURE_OPUS5_API_KEY", "cloudbank-claude-opus-5"),
    ("AZURE_OPUS5_ENDPOINT", "cloudbank-claude-opus-5"),
    ("GOOGLE_CLOUD_PROJECT", "cloudbank-gemini-3.1-pro-preview"),
    ("OPENROUTER_API_KEY", "openrouter-gemini-3.8-flash"),
])
def test_preflight_checks_every_public_primary_and_enabled_backup(missing, route_id, monkeypatch):
    def forbid(*_args, **_kwargs):
        raise AssertionError("pure configuration validation cannot construct a provider")

    monkeypatch.setattr(routing, "ClaudeClient", forbid)
    monkeypatch.setattr(routing, "VertexGeminiClient", forbid)
    monkeypatch.setattr(routing, "OpenAICompatibleClient", forbid)
    monkeypatch.setattr(routing, "OpenAIResponsesClient", forbid)
    settings = replace(Settings.from_environment(), openrouter_failover_enabled=True)
    environ = _configuration()
    routing.validate_public_route_configuration(settings, environ=environ)
    del environ[missing]
    with pytest.raises(routing.LLMRouteConfigurationError) as caught:
        routing.validate_public_route_configuration(settings, environ=environ)
    assert route_id in str(caught.value)
    assert all(value not in str(caught.value) for value in environ.values())


def test_preflight_reports_all_missing_routes_without_checking_disabled_backups():
    settings = replace(Settings.from_environment(), openrouter_failover_enabled=False)
    environ = _configuration()
    del environ["OPENROUTER_API_KEY"]
    routing.validate_public_route_configuration(settings, environ=environ)
    with pytest.raises(routing.LLMRouteConfigurationError) as caught:
        routing.validate_public_route_configuration(settings, environ={})
    catalog = load_model_catalog()
    assert all(profile.primary_route in str(caught.value) for profile in catalog.public_profiles())
    assert "openrouter-" not in str(caught.value)


@pytest.mark.parametrize("field,value", [
    ("AZURE_OPUS5_ENDPOINT", "https://credential:secret@opus.services.ai.azure.com"),
    ("AZURE_OPENAI_ENDPOINT", "https://untrusted.invalid"),
    ("GOOGLE_CLOUD_PROJECT", "invalid/project"),
    ("GOOGLE_CLOUD_LOCATION", "invalid/location"),
])
def test_preflight_rejects_invalid_local_configuration_without_echoing_it(field, value):
    environ = {**_configuration(), field: value}
    with pytest.raises(routing.LLMRouteConfigurationError) as caught:
        routing.validate_public_route_configuration(Settings.from_environment(), environ=environ)
    assert value not in str(caught.value)


def test_missing_primary_never_constructs_or_bills_backup_even_after_repeated_calls(monkeypatch, caplog):
    router = routing.LLMRouter(settings=replace(Settings.from_environment(), openrouter_failover_enabled=True))
    calls = []

    def unavailable(route, *, user_id):
        calls.append(route.id)
        if route.provider == "openrouter":
            raise AssertionError("missing local config cannot authorize backup spend")
        raise routing.LLMRouteConfigurationError("private configuration diagnostic")

    monkeypatch.setattr(router, "_raw_route", unavailable)
    context = routing.CallContext(None, "configuration-check", "chat", False)
    for _ in range(3):
        with pytest.raises(routing.LLMRouteConfigurationError):
            router.funded("balanced", context=context)
    assert calls == ["cloudbank-claude-sonnet-5"] * 3
    assert "llm_configuration_unavailable" in caplog.text
    assert "private configuration diagnostic" not in caplog.text
    assert "llm_fallback_spend" not in caplog.text


@pytest.mark.parametrize("exception", [KeyboardInterrupt, SystemExit])
def test_half_open_probe_is_released_when_base_exception_escapes(exception):
    circuits = routing.CircuitRegistry()
    circuits.open("primary", 0)

    def stop(**_kwargs):
        raise exception()

    primary = SimpleNamespace(route="primary", provider="azure-foundry", complete=stop)
    backup = SimpleNamespace(complete=lambda **_kwargs: pytest.fail("backup must not run"))
    client = routing.FailoverClient(primary, backup, cooldown_seconds=15, circuits=circuits)
    with pytest.raises(exception):
        client.complete()
    assert circuits.primary_allowed("primary")


@pytest.mark.parametrize("provider", ["anthropic", "google", "openai", "openrouter"])
def test_byok_has_one_deadline_shared_by_retry_metering_and_transport(monkeypatch, provider):
    class Raw:
        def __init__(self, **kwargs):
            self.model = kwargs["model"]
            self.provider = provider
            self.billing_source = "byok"
            self.route = kwargs["route"]

    for name in ("ClaudeClient", "GeminiClient", "OpenAIResponsesClient", "OpenAICompatibleClient"):
        monkeypatch.setattr(routing, name, Raw)
    before = time.monotonic()
    router = routing.LLMRouter(settings=replace(Settings.from_environment(), llm_allow_byok=True, llm_retry_attempts=5))
    client = router.byok(routing.BYOKCredential(provider, "fake-user-key"),
                        context=routing.CallContext("test-user", "byok-deadline", "propose", True))
    assert before + 179 < client.deadline <= time.monotonic() + 180
    assert client.deadline == client.inner.deadline == client.inner.inner.request_deadline
    assert client.attempts == 2
    assert not client.inner.context.charge_trial and not client.inner.charge_emergency
    assert client.inner.billing_source == "byok"


def test_no_deadline_internal_invocation_still_respects_provider_slots(monkeypatch):
    occupied = threading.Event()
    finished = threading.Event()
    slots = threading.BoundedSemaphore(1)
    assert slots.acquire(blocking=False)
    monkeypatch.setattr(client_module, "_PROVIDER_SLOTS", slots)

    def invoke():
        occupied.set()
        client_module.invoke_before_deadline(lambda: finished.set(), deadline=None,
                                            provider="test", client=SimpleNamespace())

    thread = threading.Thread(target=invoke)
    thread.start()
    try:
        assert occupied.wait(1)
        assert not finished.wait(.03)
    finally:
        slots.release()
        thread.join(2)
    assert not thread.is_alive() and finished.is_set()


def test_busy_provider_slots_expire_without_dispatch(monkeypatch):
    slots = threading.BoundedSemaphore(1)
    assert slots.acquire(blocking=False)
    monkeypatch.setattr(client_module, "_PROVIDER_SLOTS", slots)
    with pytest.raises(LLMRequestDeadlineError) as caught:
        client_module.invoke_before_deadline(lambda: pytest.fail("must not dispatch"),
            deadline=time.monotonic() + .02, provider="test", client=SimpleNamespace())
    assert not caught.value.billing_uncertain
    slots.release()


def test_anthropic_byok_pins_official_endpoint_despite_ambient_cli_settings(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://untrusted.invalid")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "ambient-cli-token")
    client = ClaudeClient(model="claude-sonnet-5", provider="anthropic", api_key="user-key")
    try:
        assert str(client._client.base_url) == "https://api.anthropic.com"
        assert client._client.api_key == "user-key"
        assert client._client.auth_token is None
    finally:
        client.close()


def test_native_foundry_metadata_uses_one_provider_identifier(monkeypatch):
    final = SimpleNamespace(model="claude-sonnet-5-20260901", stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text="answer")],
        usage=SimpleNamespace(input_tokens=1, output_tokens=1,
                              cache_read_input_tokens=0, cache_creation_input_tokens=0))

    class Stream:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def get_final_message(self): return final

    monkeypatch.setattr("anthropic.Anthropic", lambda **_kwargs:
                        SimpleNamespace(messages=SimpleNamespace(stream=lambda **_kwargs: Stream())))
    client = ClaudeClient(model="deployment-alias", provider="foundry", api_key="fake-key",
                          base_url="https://test.services.ai.azure.com/anthropic")
    response = client.complete(system="test", messages=[], max_tokens=8)
    assert client.provider == response.provider == "azure-foundry"
    assert response.model == "deployment-alias"
    assert response.resolved_model_version == final.model


def test_accounting_errors_use_the_sanitized_unavailable_response():
    error = LLMAccountingUnavailableError("private database diagnostic")
    assert isinstance(error, HANDLED_LLM_ERRORS)
    response = llm_http_exception(error, byok=False)
    assert response.status_code == 503
    assert response.detail["code"] == "usage_accounting_unavailable"
    assert "private" not in str(response.detail)


@pytest.mark.parametrize("byok", [False, True])
def test_hard_request_deadline_has_a_safe_public_error(byok):
    error = LLMRequestDeadlineError(provider="openai", billing_uncertain=True)
    assert isinstance(error, HANDLED_LLM_ERRORS)
    response = llm_http_exception(error, byok=byok)
    assert response.status_code == 503
    assert response.detail["code"] == "llm_request_deadline"


@pytest.mark.parametrize("field", ["metadata_confirmed", "configuration_confirmed", "funded_feature_qualified", "live_inference_verified"])
def test_primary_admission_requires_distinct_funded_evidence(field):
    catalog = load_model_catalog()
    route_id = catalog.profiles["balanced"].primary_route
    routes = {**catalog.routes, route_id: replace(catalog.routes[route_id], **{field: False})}
    with pytest.raises(RuntimeError, match="funded feature qualification"):
        _validate_catalog(replace(catalog, routes=routes))


@pytest.mark.parametrize("model_id", ["gemini-3.8-flash", "gemini-3.1-pro-preview"])
@pytest.mark.parametrize("method", ["complete", "tool_call"])
def test_gemini_backup_preserves_primary_decoding_intent(model_id, method):
    spec = load_model_catalog().models[model_id]
    captured = {}
    tool = {"name": "propose", "input_schema": {"type": "object"}}

    def vertex_response(request):
        captured["vertex"] = json.loads(request.content)
        part = {"functionCall": {"name": "propose", "args": {}}} if method == "tool_call" else {"text": "answer"}
        return httpx.Response(200, json={"modelVersion": model_id + "-snapshot",
            "candidates": [{"content": {"parts": [part]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1}})

    def backup_response(request):
        captured["backup"] = json.loads(request.content)
        message = {"tool_calls": [{"function": {"name": "propose", "arguments": "{}"}}]} if method == "tool_call" else {"content": "answer"}
        return httpx.Response(200, json={"model": "google/" + model_id,
            "choices": [{"message": message, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1}})

    primary = VertexGeminiClient(model=model_id, model_spec=spec, project="funded-project",
        token_provider=lambda: "fake-token", transport=httpx.MockTransport(vertex_response))
    backup = OpenAICompatibleClient(model="google/" + model_id, model_spec=spec, provider="openrouter",
        billing_source="openrouter-emergency", route="backup", base_url="https://openrouter.ai/api/v1",
        api_key="fake-key", provider_preferences=routing._openrouter_provider_preferences(spec.pricing),
        transport=httpx.MockTransport(backup_response))
    kwargs = {"system": "test", "messages": [{"role": "user", "content": "question"}], "max_tokens": 128}
    if method == "tool_call":
        kwargs["tool"] = tool
    try:
        result = getattr(primary, method)(**kwargs)
        fallback_result = getattr(backup, method)(**kwargs)
        assert result.resolved_model_version == model_id + "-snapshot"
        assert fallback_result.resolved_model_version == "google/" + model_id
    finally:
        primary.close()
        backup.close()
    generation = captured["vertex"]["generationConfig"]
    assert generation["temperature"] == captured["backup"]["temperature"] == 0
    assert generation["candidateCount"] == 1
    assert generation["thinkingConfig"]["thinkingLevel"].lower() == captured["backup"]["reasoning"]["effort"]
    assert generation["maxOutputTokens"] == captured["backup"]["max_tokens"] == 128
    assert captured["backup"]["provider"]["require_parameters"] is True


def test_absent_or_untrusted_returned_version_is_not_fabricated():
    assert client_module.resolved_model_version(None) is None
    assert client_module.resolved_model_version("private model\nresponse body") is None
    assert client_module.resolved_model_version("x" * 201) is None


def test_missing_adc_is_configuration_unavailable_without_generation_dispatch(monkeypatch):
    from google.auth.exceptions import DefaultCredentialsError

    def missing(**_kwargs):
        raise DefaultCredentialsError("private credential-path diagnostic")

    monkeypatch.delenv("GOOGLE_VERTEX_ACCESS_TOKEN", raising=False)
    monkeypatch.setattr("google.auth.default", missing)
    client = VertexGeminiClient(model="gemini-3.8-flash",
        model_spec=load_model_catalog().models["gemini-3.8-flash"], project="funded-project",
        transport=httpx.MockTransport(lambda _request: pytest.fail("must not dispatch")))
    try:
        with pytest.raises(client_module.LLMClientConfigurationError) as caught:
            client.complete(system="test", messages=[], max_tokens=128)
        assert not client.request_dispatched
        assert "private" not in str(caught.value)
    finally:
        client.close()


def test_auth_service_refresh_failure_remains_a_provider_outage(monkeypatch):
    from google.auth.exceptions import RefreshError
    from app.llm.providers import LLMProviderError

    def rejected(_request):
        raise RefreshError("private auth service response")

    monkeypatch.delenv("GOOGLE_VERTEX_ACCESS_TOKEN", raising=False)
    client = VertexGeminiClient(model="gemini-3.8-flash",
        model_spec=load_model_catalog().models["gemini-3.8-flash"], project="funded-project",
        transport=httpx.MockTransport(lambda _request: pytest.fail("must not dispatch generation")))
    client._credentials = SimpleNamespace(valid=False, refresh=rejected)
    try:
        with pytest.raises(LLMProviderError) as caught:
            client.complete(system="test", messages=[], max_tokens=128)
        assert caught.value.status_code == 401
        assert caught.value.provider == "gcp-vertex"
        assert not caught.value.billing_uncertain
    finally:
        client.close()
