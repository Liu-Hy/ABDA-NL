"""HTTP adapters for OpenAI-compatible and Google Gemini providers."""
from __future__ import annotations

import json
import logging
import time
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from typing import Any

import httpx

from app.llm.catalog import ModelSpec
from app.llm.client import LLMResponse, ToolCallResponse


log = logging.getLogger(__name__)


class LLMProviderError(RuntimeError):
    """Sanitized provider failure with enough detail for routing decisions."""

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        status_code: int | None = None,
        retryable: bool = False,
        outage_candidate: bool = False,
        error_type: str | None = None,
        usage: dict[str, int] | None = None,
        provider_cost_microusd: int | None = None,
        billing_uncertain: bool = False,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code
        self.retryable = retryable
        self.outage_candidate = outage_candidate
        self.error_type = error_type
        self.usage = dict(usage or {})
        self.provider_cost_microusd = provider_cost_microusd
        self.billing_uncertain = billing_uncertain


_NO_DISPATCH_TRANSPORT_ERRORS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
    httpx.ProxyError,
    httpx.UnsupportedProtocol,
)


def transport_billing_uncertainty(exc: BaseException) -> bool | None:
    """Classify whether a transport failure may follow provider dispatch.

    ``False`` means the available exception chain identifies a pre-dispatch
    connection or pool failure. ``True`` means the request may have reached the
    provider. ``None`` means the chain contains no recognized HTTP transport
    exception.
    """
    current: BaseException | None = exc
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if isinstance(current, _NO_DISPATCH_TRANSPORT_ERRORS):
            return False
        if isinstance(current, httpx.TransportError):
            return True
        current = current.__cause__ or current.__context__
    return None


def _flatten_system(system: str | list[dict[str, Any]]) -> str:
    if isinstance(system, str):
        return system
    return "\n\n".join(
        str(block.get("text"))
        for block in (system or [])
        if isinstance(block, dict) and isinstance(block.get("text"), str)
    )


def _exclusive_input_tokens(
    total_input_tokens: int,
    cache_read_input_tokens: int = 0,
    cache_creation_input_tokens: int = 0,
) -> int:
    """Return the normal-rate input after removing cached token categories."""
    total = max(0, int(total_input_tokens))
    cache_read = max(0, int(cache_read_input_tokens))
    cache_creation = max(0, int(cache_creation_input_tokens))
    return max(0, total - cache_read - cache_creation)


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


def _usage_envelope(raw: Any) -> dict[str, int]:
    usage = _mapping(raw)
    prompt_details = _mapping(usage.get("prompt_tokens_details"))
    total_input = _nonnegative_int(
        usage.get("prompt_tokens") or usage.get("input_tokens")
    )
    cache_read = _nonnegative_int(
        prompt_details.get("cached_tokens")
        or usage.get("cache_read_input_tokens")
    )
    cache_creation = _nonnegative_int(
        prompt_details.get("cache_write_tokens")
        or usage.get("cache_creation_input_tokens")
    )
    return {
        "input_tokens": _exclusive_input_tokens(
            total_input,
            cache_read,
            cache_creation,
        ),
        "output_tokens": _nonnegative_int(
            usage.get("completion_tokens") or usage.get("output_tokens")
        ),
        "cache_read_input_tokens": cache_read,
        "cache_creation_input_tokens": cache_creation,
    }


def _reported_cost_microusd(raw: Any) -> int | None:
    """Convert an OpenRouter usage cost in USD to whole microdollars."""
    value = _mapping(raw).get("cost")
    if value is None:
        return None
    try:
        cost = Decimal(str(value))
    except (InvalidOperation, ValueError):
        log.warning("llm_provider_invalid_reported_cost")
        return None
    if not cost.is_finite() or cost < 0:
        log.warning("llm_provider_invalid_reported_cost")
        return None
    return int((cost * Decimal("1000000")).to_integral_value(rounding=ROUND_CEILING))


def _response_billing_fields(
    data: dict[str, Any],
) -> tuple[dict[str, int], int | None, bool]:
    usage = _usage_envelope(data.get("usage"))
    provider_cost = _reported_cost_microusd(data.get("usage"))
    has_usage = any(value > 0 for value in usage.values())
    return usage, provider_cost, provider_cost is None and not has_usage


_RETRYABLE_ERROR_TYPES = {
    "rate_limit_exceeded",
    "provider_overloaded",
    "provider_unavailable",
    "server",
    "timeout",
    "unmapped",
}


def _error_status(value: Any) -> int | None:
    try:
        status = int(value)
    except (TypeError, ValueError):
        return None
    return status if 400 <= status <= 599 else None


def _provider_error_from_payload(
    data: dict[str, Any],
    *,
    provider: str,
    default_status: int | None = None,
) -> LLMProviderError | None:
    raw_error = data.get("error")
    if not isinstance(raw_error, dict):
        return None
    metadata = raw_error.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    error_type = str(
        metadata.get("error_type") or data.get("error_type") or ""
    ).strip()
    status = (
        _error_status(raw_error.get("code"))
        or _error_status(raw_error.get("status"))
        or default_status
    )
    retryable = error_type in _RETRYABLE_ERROR_TYPES or (
        status in {408, 409, 425, 429} or (status is not None and status >= 500)
    )
    outage = error_type in _RETRYABLE_ERROR_TYPES or (
        status in {408, 425, 429} or (status is not None and status >= 500)
    )
    label = error_type or (f"HTTP {status}" if status is not None else "an error")
    return LLMProviderError(
        f"{provider} returned {label}",
        provider=provider,
        status_code=status,
        retryable=retryable,
        outage_candidate=outage,
        error_type=error_type or None,
        usage=_usage_envelope(data.get("usage")),
        provider_cost_microusd=_reported_cost_microusd(data.get("usage")),
    )


def _http_provider_error(provider: str, status: int) -> LLMProviderError:
    retryable = status in {408, 409, 425, 429} or status >= 500
    outage = status in {408, 425, 429} or status >= 500
    return LLMProviderError(
        f"{provider} returned HTTP {status}",
        provider=provider,
        status_code=status,
        retryable=retryable,
        outage_candidate=outage,
    )


def _text_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        return ""
    parts: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        if item.get("type") in {"text", "output_text"} and isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "".join(parts)


class OpenAICompatibleClient:
    """Chat Completions adapter for Azure Foundry, OpenAI, and OpenRouter."""

    def __init__(
        self,
        *,
        model: str,
        model_spec: ModelSpec,
        provider: str,
        billing_source: str,
        route: str,
        base_url: str,
        api_key: str,
        auth_style: str = "bearer",
        headers: dict[str, str] | None = None,
        provider_preferences: dict[str, Any] | None = None,
        timeout_seconds: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise RuntimeError(f"{provider} API key is not configured")
        self.model = model
        self.model_spec = model_spec
        self.provider = provider
        self.billing_source = billing_source
        self.route = route
        self.provider_preferences = dict(provider_preferences or {})
        request_headers = dict(headers or {})
        if auth_style == "api-key":
            request_headers["api-key"] = api_key
        elif auth_style == "bearer":
            request_headers["Authorization"] = f"Bearer {api_key}"
        else:
            raise ValueError(f"unknown auth style {auth_style!r}")
        self._client = httpx.Client(
            base_url=base_url.rstrip("/") + "/",
            headers=request_headers,
            timeout=httpx.Timeout(timeout_seconds, connect=10.0),
            transport=transport,
        )

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.post("chat/completions", json=payload)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise LLMProviderError(
                f"{self.provider} could not be reached",
                provider=self.provider,
                retryable=True,
                outage_candidate=True,
                billing_uncertain=transport_billing_uncertainty(exc) is not False,
            ) from exc
        try:
            data = response.json()
        except ValueError as exc:
            if response.status_code >= 400:
                raise _http_provider_error(
                    self.provider, response.status_code
                ) from exc
            raise LLMProviderError(
                f"{self.provider} returned an invalid JSON response",
                provider=self.provider,
                retryable=True,
                outage_candidate=True,
                billing_uncertain=True,
            ) from exc
        if not isinstance(data, dict):
            if response.status_code >= 400:
                raise _http_provider_error(self.provider, response.status_code)
            raise LLMProviderError(
                f"{self.provider} returned an unexpected response",
                provider=self.provider,
                retryable=True,
                outage_candidate=True,
                billing_uncertain=True,
            )
        provider_error = _provider_error_from_payload(
            data,
            provider=self.provider,
            default_status=(response.status_code if response.status_code >= 400 else None),
        )
        if provider_error is not None:
            log.warning(
                "llm_provider_error provider=%s route=%s status=%s type=%s",
                self.provider,
                self.route,
                provider_error.status_code,
                provider_error.error_type,
            )
            raise provider_error
        if response.status_code >= 400:
            status = response.status_code
            log.warning(
                "llm_provider_http_error provider=%s route=%s status=%d",
                self.provider,
                self.route,
                status,
            )
            raise _http_provider_error(self.provider, status)
        return data

    def _base_payload(
        self,
        *,
        system: str | list[dict[str, Any]],
        messages: list[dict[str, Any]],
        max_tokens: int,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _flatten_system(system)},
                *messages,
            ],
        }
        if self.provider_preferences:
            payload["provider"] = self.provider_preferences
        payload[self.model_spec.max_token_field] = max_tokens
        return payload

    @staticmethod
    def _first_choice(data: dict[str, Any], provider: str) -> dict[str, Any]:
        provider_error = _provider_error_from_payload(data, provider=provider)
        if provider_error is not None:
            raise provider_error
        choices = data.get("choices") or []
        if not choices or not isinstance(choices[0], dict):
            usage, provider_cost, billing_uncertain = _response_billing_fields(data)
            raise LLMProviderError(
                f"{provider} returned provider_unavailable",
                provider=provider,
                status_code=502,
                retryable=True,
                outage_candidate=True,
                error_type="provider_unavailable",
                usage=usage,
                provider_cost_microusd=provider_cost,
                billing_uncertain=billing_uncertain,
            )
        choice_error = choices[0].get("error")
        if isinstance(choice_error, dict):
            provider_error = _provider_error_from_payload(
                {"error": choice_error, "usage": data.get("usage")},
                provider=provider,
            )
            if provider_error is not None:
                raise provider_error
        return choices[0]

    def complete(
        self,
        *,
        system: str | list[dict[str, Any]],
        messages: list[dict[str, Any]],
        max_tokens: int,
        cache: bool = True,
    ) -> LLMResponse:
        del cache
        payload = self._base_payload(
            system=system,
            messages=messages,
            max_tokens=max_tokens,
        )
        start = time.monotonic()
        data = self._post(payload)
        latency_ms = int((time.monotonic() - start) * 1000)
        choice = self._first_choice(data, self.provider)
        message = _mapping(choice.get("message"))
        usage = _usage_envelope(data.get("usage"))
        return LLMResponse(
            text=_text_content(message.get("content")),
            stop_reason=str(choice.get("finish_reason") or "stop"),
            usage=usage,
            latency_ms=latency_ms,
            model=str(data.get("model") or self.model),
            provider=self.provider,
            billing_source=self.billing_source,
            route=self.route,
            provider_cost_microusd=_reported_cost_microusd(data.get("usage")),
        )

    def tool_call(
        self,
        *,
        system: str | list[dict[str, Any]],
        messages: list[dict[str, Any]],
        tool: dict[str, Any],
        max_tokens: int,
        cache: bool = True,
    ) -> ToolCallResponse:
        del cache
        tool_name = str(tool.get("name") or "tool")
        payload = self._base_payload(
            system=system,
            messages=messages,
            max_tokens=max_tokens,
        )
        payload["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": str(tool.get("description") or "Return structured output."),
                    "parameters": tool.get("input_schema") or {"type": "object"},
                },
            }
        ]
        payload["tool_choice"] = {"type": "function", "function": {"name": tool_name}}
        if self.provider != "openrouter":
            payload["parallel_tool_calls"] = False

        start = time.monotonic()
        data = self._post(payload)
        latency_ms = int((time.monotonic() - start) * 1000)
        choice = self._first_choice(data, self.provider)
        message = _mapping(choice.get("message"))
        calls = message.get("tool_calls") or []
        usage, provider_cost, billing_uncertain = _response_billing_fields(data)
        if not calls or not isinstance(calls[0], dict):
            raise LLMProviderError(
                f"{self.provider} did not return the required tool call",
                provider=self.provider,
                retryable=False,
                outage_candidate=False,
                usage=usage,
                provider_cost_microusd=provider_cost,
                billing_uncertain=billing_uncertain,
            )
        function = _mapping(calls[0].get("function"))
        returned_name = str(function.get("name") or "")
        if returned_name != tool_name:
            raise LLMProviderError(
                f"{self.provider} returned the wrong tool",
                provider=self.provider,
                retryable=False,
                outage_candidate=False,
                usage=usage,
                provider_cost_microusd=provider_cost,
                billing_uncertain=billing_uncertain,
            )
        arguments = function.get("arguments")
        try:
            tool_input = json.loads(arguments) if isinstance(arguments, str) else arguments
        except (TypeError, ValueError) as exc:
            raise LLMProviderError(
                f"{self.provider} returned invalid tool arguments",
                provider=self.provider,
                retryable=False,
                outage_candidate=False,
                usage=usage,
                provider_cost_microusd=provider_cost,
                billing_uncertain=billing_uncertain,
            ) from exc
        if not isinstance(tool_input, dict):
            raise LLMProviderError(
                f"{self.provider} returned non-object tool arguments",
                provider=self.provider,
                retryable=False,
                outage_candidate=False,
                usage=usage,
                provider_cost_microusd=provider_cost,
                billing_uncertain=billing_uncertain,
            )
        return ToolCallResponse(
            tool_name=returned_name,
            tool_input=tool_input,
            stop_reason=str(choice.get("finish_reason") or "tool_calls"),
            usage=usage,
            latency_ms=latency_ms,
            model=str(data.get("model") or self.model),
            provider=self.provider,
            billing_source=self.billing_source,
            route=self.route,
            provider_cost_microusd=provider_cost,
        )


class OpenAIResponsesClient(OpenAICompatibleClient):
    """Native Responses API adapter for direct OpenAI and Azure OpenAI routes."""

    def __init__(
        self,
        *,
        reasoning_effort: str | None = "low",
        safety_identifier: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.reasoning_effort = reasoning_effort
        self.safety_identifier = safety_identifier

    def _post_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.post("responses", json=payload)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise LLMProviderError(
                f"{self.provider} could not be reached",
                provider=self.provider,
                retryable=True,
                outage_candidate=True,
                billing_uncertain=transport_billing_uncertainty(exc) is not False,
            ) from exc
        if response.status_code >= 400:
            status = response.status_code
            retryable = status in {408, 409, 425, 429} or status >= 500
            outage = status in {408, 425, 429} or status >= 500
            log.warning(
                "llm_provider_http_error provider=%s route=%s status=%d api=responses",
                self.provider,
                self.route,
                status,
            )
            raise LLMProviderError(
                f"{self.provider} returned HTTP {status}",
                provider=self.provider,
                status_code=status,
                retryable=retryable,
                outage_candidate=outage,
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise LLMProviderError(
                f"{self.provider} returned an invalid JSON response",
                provider=self.provider,
                retryable=True,
                outage_candidate=True,
                billing_uncertain=True,
            ) from exc
        if not isinstance(data, dict):
            raise LLMProviderError(
                f"{self.provider} returned an unexpected response",
                provider=self.provider,
                retryable=True,
                outage_candidate=True,
                billing_uncertain=True,
            )
        return data

    def _responses_payload(
        self,
        *,
        system: str | list[dict[str, Any]],
        messages: list[dict[str, Any]],
        max_tokens: int,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "instructions": _flatten_system(system),
            "input": [
                {"role": item.get("role"), "content": item.get("content")}
                for item in messages
                if item.get("role") in {"user", "assistant"}
                and isinstance(item.get("content"), str)
            ],
            "max_output_tokens": max_tokens,
            "store": False,
        }
        if self.reasoning_effort:
            payload["reasoning"] = {"effort": self.reasoning_effort}
        if self.safety_identifier:
            payload["safety_identifier"] = self.safety_identifier
        return payload

    @staticmethod
    def _responses_usage(data: dict[str, Any]) -> dict[str, int]:
        usage = _mapping(data.get("usage"))
        details = _mapping(usage.get("input_tokens_details"))
        total_input = _nonnegative_int(usage.get("input_tokens"))
        cache_read = _nonnegative_int(details.get("cached_tokens"))
        cache_creation = _nonnegative_int(details.get("cache_write_tokens"))
        return {
            "input_tokens": _exclusive_input_tokens(
                total_input,
                cache_read,
                cache_creation,
            ),
            "output_tokens": _nonnegative_int(usage.get("output_tokens")),
            "cache_read_input_tokens": cache_read,
            "cache_creation_input_tokens": cache_creation,
        }

    @staticmethod
    def _responses_stop_reason(data: dict[str, Any]) -> str:
        status = str(data.get("status") or "completed")
        if status == "incomplete":
            details = _mapping(data.get("incomplete_details"))
            return str(details.get("reason") or status)
        return status

    def complete(
        self,
        *,
        system: str | list[dict[str, Any]],
        messages: list[dict[str, Any]],
        max_tokens: int,
        cache: bool = True,
    ) -> LLMResponse:
        del cache
        payload = self._responses_payload(
            system=system,
            messages=messages,
            max_tokens=max_tokens,
        )
        start = time.monotonic()
        data = self._post_response(payload)
        latency_ms = int((time.monotonic() - start) * 1000)
        text_parts: list[str] = []
        for item in data.get("output") or []:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            for content in item.get("content") or []:
                if (
                    isinstance(content, dict)
                    and content.get("type") == "output_text"
                    and isinstance(content.get("text"), str)
                ):
                    text_parts.append(content["text"])
        if not text_parts:
            usage = self._responses_usage(data)
            raise LLMProviderError(
                f"{self.provider} returned no text output",
                provider=self.provider,
                retryable=False,
                outage_candidate=False,
                usage=usage,
                billing_uncertain=not any(value > 0 for value in usage.values()),
            )
        return LLMResponse(
            text="".join(text_parts),
            stop_reason=self._responses_stop_reason(data),
            usage=self._responses_usage(data),
            latency_ms=latency_ms,
            model=str(data.get("model") or self.model),
            provider=self.provider,
            billing_source=self.billing_source,
            route=self.route,
        )

    def tool_call(
        self,
        *,
        system: str | list[dict[str, Any]],
        messages: list[dict[str, Any]],
        tool: dict[str, Any],
        max_tokens: int,
        cache: bool = True,
    ) -> ToolCallResponse:
        del cache
        tool_name = str(tool.get("name") or "tool")
        payload = self._responses_payload(
            system=system,
            messages=messages,
            max_tokens=max_tokens,
        )
        payload["tools"] = [
            {
                "type": "function",
                "name": tool_name,
                "description": str(tool.get("description") or "Return structured output."),
                "parameters": tool.get("input_schema") or {"type": "object"},
                "strict": False,
            }
        ]
        payload["tool_choice"] = {"type": "function", "name": tool_name}
        payload["parallel_tool_calls"] = False
        start = time.monotonic()
        data = self._post_response(payload)
        latency_ms = int((time.monotonic() - start) * 1000)
        function_call = next(
            (
                item
                for item in data.get("output") or []
                if isinstance(item, dict) and item.get("type") == "function_call"
            ),
            None,
        )
        usage = self._responses_usage(data)
        billing_uncertain = not any(value > 0 for value in usage.values())
        if not function_call or function_call.get("name") != tool_name:
            raise LLMProviderError(
                f"{self.provider} did not return the required tool call",
                provider=self.provider,
                retryable=False,
                outage_candidate=False,
                usage=usage,
                billing_uncertain=billing_uncertain,
            )
        arguments = function_call.get("arguments")
        try:
            tool_input = json.loads(arguments) if isinstance(arguments, str) else arguments
        except (TypeError, ValueError) as exc:
            raise LLMProviderError(
                f"{self.provider} returned invalid tool arguments",
                provider=self.provider,
                retryable=False,
                outage_candidate=False,
                usage=usage,
                billing_uncertain=billing_uncertain,
            ) from exc
        if not isinstance(tool_input, dict):
            raise LLMProviderError(
                f"{self.provider} returned non-object tool arguments",
                provider=self.provider,
                retryable=False,
                outage_candidate=False,
                usage=usage,
                billing_uncertain=billing_uncertain,
            )
        return ToolCallResponse(
            tool_name=tool_name,
            tool_input=tool_input,
            stop_reason=self._responses_stop_reason(data),
            usage=usage,
            latency_ms=latency_ms,
            model=str(data.get("model") or self.model),
            provider=self.provider,
            billing_source=self.billing_source,
            route=self.route,
        )


class GeminiClient:
    """Google Gemini Developer API adapter for user-provided API keys."""

    DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/"

    def __init__(
        self,
        *,
        model: str,
        model_spec: ModelSpec,
        api_key: str,
        billing_source: str = "byok",
        route: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise RuntimeError("Google Gemini API key is not configured")
        self.model = model
        self.model_spec = model_spec
        self.provider = "google"
        self.billing_source = billing_source
        self.route = route or f"google:{model}"
        self._client = httpx.Client(
            base_url=base_url.rstrip("/") + "/",
            headers={"x-goog-api-key": api_key},
            timeout=httpx.Timeout(timeout_seconds, connect=10.0),
            transport=transport,
        )

    @staticmethod
    def _contents(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        contents: list[dict[str, Any]] = []
        for message in messages:
            role = "model" if message.get("role") == "assistant" else "user"
            content = message.get("content")
            if isinstance(content, str):
                contents.append({"role": role, "parts": [{"text": content}]})
        return contents

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        path = f"models/{self.model}:generateContent"
        try:
            response = self._client.post(path, json=payload)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise LLMProviderError(
                "Google Gemini could not be reached",
                provider=self.provider,
                retryable=True,
                outage_candidate=True,
                billing_uncertain=transport_billing_uncertainty(exc) is not False,
            ) from exc
        if response.status_code >= 400:
            status = response.status_code
            retryable = status in {408, 409, 425, 429} or status >= 500
            raise LLMProviderError(
                f"Google Gemini returned HTTP {status}",
                provider=self.provider,
                status_code=status,
                retryable=retryable,
                outage_candidate=retryable,
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise LLMProviderError(
                "Google Gemini returned invalid JSON",
                provider=self.provider,
                retryable=True,
                outage_candidate=True,
                billing_uncertain=True,
            ) from exc
        if not isinstance(data, dict):
            raise LLMProviderError(
                "Google Gemini returned an unexpected response",
                provider=self.provider,
                retryable=True,
                outage_candidate=True,
                billing_uncertain=True,
            )
        return data

    @staticmethod
    def _candidate(data: dict[str, Any]) -> dict[str, Any]:
        candidates = data.get("candidates") or []
        if not candidates or not isinstance(candidates[0], dict):
            usage = GeminiClient._usage(data)
            raise LLMProviderError(
                "Google Gemini returned no candidate",
                provider="google",
                retryable=True,
                outage_candidate=True,
                usage=usage,
                billing_uncertain=not any(value > 0 for value in usage.values()),
            )
        return candidates[0]

    @staticmethod
    def _usage(data: dict[str, Any]) -> dict[str, int]:
        usage = _mapping(data.get("usageMetadata"))
        total_input = _nonnegative_int(usage.get("promptTokenCount"))
        cache_read = _nonnegative_int(usage.get("cachedContentTokenCount"))
        return {
            "input_tokens": _exclusive_input_tokens(total_input, cache_read),
            "output_tokens": _nonnegative_int(usage.get("candidatesTokenCount")),
            "cache_read_input_tokens": cache_read,
            "cache_creation_input_tokens": 0,
        }

    def _base_payload(
        self,
        *,
        system: str | list[dict[str, Any]],
        messages: list[dict[str, Any]],
        max_tokens: int,
    ) -> dict[str, Any]:
        return {
            "systemInstruction": {"parts": [{"text": _flatten_system(system)}]},
            "contents": self._contents(messages),
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0},
        }

    def complete(
        self,
        *,
        system: str | list[dict[str, Any]],
        messages: list[dict[str, Any]],
        max_tokens: int,
        cache: bool = True,
    ) -> LLMResponse:
        del cache
        payload = self._base_payload(
            system=system,
            messages=messages,
            max_tokens=max_tokens,
        )
        start = time.monotonic()
        data = self._post(payload)
        latency_ms = int((time.monotonic() - start) * 1000)
        candidate = self._candidate(data)
        parts = _mapping(candidate.get("content")).get("parts") or []
        text = "".join(
            str(part.get("text"))
            for part in parts
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        )
        return LLMResponse(
            text=text,
            stop_reason=str(candidate.get("finishReason") or "STOP"),
            usage=self._usage(data),
            latency_ms=latency_ms,
            model=str(data.get("modelVersion") or self.model),
            provider=self.provider,
            billing_source=self.billing_source,
            route=self.route,
        )

    def tool_call(
        self,
        *,
        system: str | list[dict[str, Any]],
        messages: list[dict[str, Any]],
        tool: dict[str, Any],
        max_tokens: int,
        cache: bool = True,
    ) -> ToolCallResponse:
        del cache
        tool_name = str(tool.get("name") or "tool")
        payload = self._base_payload(
            system=system,
            messages=messages,
            max_tokens=max_tokens,
        )
        payload["tools"] = [
            {
                "functionDeclarations": [
                    {
                        "name": tool_name,
                        "description": str(tool.get("description") or "Return structured output."),
                        "parameters": tool.get("input_schema") or {"type": "object"},
                    }
                ]
            }
        ]
        payload["toolConfig"] = {
            "functionCallingConfig": {
                "mode": "ANY",
                "allowedFunctionNames": [tool_name],
            }
        }
        start = time.monotonic()
        data = self._post(payload)
        latency_ms = int((time.monotonic() - start) * 1000)
        candidate = self._candidate(data)
        parts = _mapping(candidate.get("content")).get("parts") or []
        usage = self._usage(data)
        call = next(
            (
                part.get("functionCall")
                for part in parts
                if isinstance(part, dict) and isinstance(part.get("functionCall"), dict)
            ),
            None,
        )
        if not call or call.get("name") != tool_name or not isinstance(call.get("args"), dict):
            raise LLMProviderError(
                "Google Gemini did not return the required tool call",
                provider=self.provider,
                retryable=False,
                outage_candidate=False,
                usage=usage,
                billing_uncertain=not any(value > 0 for value in usage.values()),
            )
        return ToolCallResponse(
            tool_name=tool_name,
            tool_input=dict(call["args"]),
            stop_reason=str(candidate.get("finishReason") or "STOP"),
            usage=usage,
            latency_ms=latency_ms,
            model=str(data.get("modelVersion") or self.model),
            provider=self.provider,
            billing_source=self.billing_source,
            route=self.route,
        )
