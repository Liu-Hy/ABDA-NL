"""HTTP adapters for OpenAI-compatible and Google Gemini providers."""
from __future__ import annotations

import json
import logging
import math
import os
import re
import time
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from app.llm.catalog import ModelSpec
from app.llm.client import (
    LLMRequestDeadlineError,
    LLMResponse,
    ToolCallResponse,
    remaining_request_seconds,
    request_timeout,
)


log = logging.getLogger(__name__)


_TERMINAL_ERROR_TYPES = frozenset({
    "accounting_unavailable", "authentication_required",
    "content_blocked", "content_filter", "content_policy_violation",
    "invalid_request", "invalid_request_error", "invalid_response",
    "request_deadline", "safety", "semantic_validation",
    "trial_exhausted", "user_quota_exceeded",
})
# Provider quota codes on an HTTP 429 describe an unavailable API route. ABDA
# credit exhaustion uses local reservation exceptions, before provider dispatch.


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
        retry_after_seconds: float | None = None,
        diagnostics: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code
        terminal = str(error_type or "").lower() in _TERMINAL_ERROR_TYPES
        self.retryable = retryable and not terminal
        self.outage_candidate = outage_candidate and not terminal
        self.error_type = error_type
        self.usage = dict(usage or {})
        self.provider_cost_microusd = provider_cost_microusd
        self.billing_uncertain = billing_uncertain
        self.retry_after_seconds = retry_after_seconds
        # Synthetic evaluation may explicitly capture this allowlisted record.
        # It is deliberately absent from the public exception message and logs.
        self.diagnostics = dict(diagnostics or {})


def provider_error_is_terminal(error: LLMProviderError) -> bool:
    return str(error.error_type or "").lower() in _TERMINAL_ERROR_TYPES


def parse_retry_after(headers: Any, *, now: float | None = None) -> float | None:
    """Parse standard and Azure/Anthropic retry delays with a two-second cap."""
    if not headers:
        return None
    for name, scale in (("retry-after-ms", 0.001), ("x-ms-retry-after-ms", 0.001),
                        ("retry-after", 1.0)):
        raw = headers.get(name)
        if raw is None or len(str(raw)) > 128:
            continue
        value = str(raw).strip()
        try:
            delay = float(value) * scale
        except ValueError:
            if name != "retry-after":
                continue
            try:
                parsed = parsedate_to_datetime(value)
                if parsed.tzinfo is None:
                    continue
                delay = parsed.timestamp() - (time.time() if now is None else now)
            except (TypeError, ValueError, OverflowError):
                continue
        if math.isfinite(delay):
            return min(2.0, max(0.0, delay))
    return None


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
        metadata.get("error_type") or data.get("error_type") or raw_error.get("type")
        or (raw_error.get("code") if isinstance(raw_error.get("code"), str) else "")
        or ""
    ).strip().lower()
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
    if status in {400, 401, 402, 403, 404, 422}:
        retryable = outage = False
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


def provider_http_error(
    provider: str, status: int, *, headers: Any = None, data: dict[str, Any] | None = None,
) -> LLMProviderError:
    if data is not None:
        # Anthropic SDK bodies sometimes contain the error object directly.
        envelope = data if "error" in data else {"error": data}
        error = _provider_error_from_payload(envelope, provider=provider, default_status=status)
        if error is not None:
            if error.retryable:
                error.retry_after_seconds = parse_retry_after(headers)
            return error
    retryable = status in {408, 409, 425, 429} or status >= 500
    outage = status in {408, 425, 429} or status >= 500
    return LLMProviderError(
        f"{provider} returned HTTP {status}",
        provider=provider,
        status_code=status,
        retryable=retryable,
        outage_candidate=outage,
        retry_after_seconds=parse_retry_after(headers) if retryable else None,
    )


def _decode_provider_response(response: httpx.Response, *, provider: str) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError as exc:
        if response.status_code >= 400:
            raise provider_http_error(provider, response.status_code, headers=response.headers) from exc
        raise LLMProviderError(
            f"{provider} returned an invalid JSON response", provider=provider,
            error_type="invalid_response", billing_uncertain=True,
        ) from exc
    if response.status_code >= 400:
        raise provider_http_error(
            provider, response.status_code, headers=response.headers,
            data=data if isinstance(data, dict) else None,
        )
    if not isinstance(data, dict):
        raise LLMProviderError(
            f"{provider} returned an unexpected response", provider=provider,
            error_type="invalid_response", billing_uncertain=True,
        )
    error = _provider_error_from_payload(data, provider=provider)
    if error is not None:
        if error.retryable:
            error.retry_after_seconds = parse_retry_after(response.headers)
        raise error
    return data


def _post_json(client: Any, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    timeout = request_timeout(
        client._client.timeout, client.request_deadline, provider=client.provider,
    )
    try:
        client.request_dispatched = True
        response = client._client.post(path, json=payload, timeout=timeout)
    except httpx.TransportError as exc:
        uncertain = transport_billing_uncertainty(exc) is not False
        if client.request_deadline is not None and time.monotonic() >= client.request_deadline:
            raise LLMRequestDeadlineError(
                provider=client.provider, billing_uncertain=uncertain,
            ) from exc
        raise LLMProviderError(
            f"{client.provider} could not be reached", provider=client.provider,
            retryable=True, outage_candidate=True, billing_uncertain=uncertain,
        ) from exc
    return _decode_provider_response(response, provider=client.provider)


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
        elif item.get("type") == "refusal" and isinstance(item.get("refusal"), str):
            parts.append(item["refusal"])
    return "".join(parts)


def _parse_diagnostics(
    *, finish_reason: Any, max_tokens: int, model: Any, visible_content: str,
    tool_calls: Any, usage: dict[str, int], reasoning_tokens: Any,
) -> dict[str, Any]:
    """Keep visible model output for synthetic replay, never transport or thoughts."""
    calls = []
    for call in tool_calls if isinstance(tool_calls, list) else []:
        function = _mapping(_mapping(call).get("function"))
        if not function:
            continue
        calls.append({"function": {
            "name": str(function.get("name") or ""),
            "arguments": function.get("arguments"),
        }})
    return {
        "finish_reason": finish_reason if isinstance(finish_reason, str) else None,
        "requested_max_tokens": max_tokens,
        "actual_model": str(model),
        "visible_content": visible_content,
        "tool_calls": calls,
        "usage": dict(usage),
        "reasoning_tokens": (
            _nonnegative_int(reasoning_tokens) if reasoning_tokens is not None else None
        ),
    }


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
        self.request_deadline: float | None = None
        self.request_dispatched = False
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

    def close(self) -> None:
        self._client.close()

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        return _post_json(self, "chat/completions", payload)

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
        effort = self.model_spec.reasoning_effort
        if effort and self.provider == "openrouter" and self.model_spec.family in {
            "openai", "google", "z-ai", "moonshotai",
        }:
            payload["reasoning"] = {"effort": effort}
        elif effort and self.provider == "azure-foundry" and self.model_spec.family in {
            "z-ai", "moonshotai",
        }:
            # Fireworks exposes its OpenAI-compatible effort field on Foundry.
            # Do not send OpenRouter's reasoning object or a numeric budget here.
            payload["reasoning_effort"] = effort
        return payload

    def _diagnostics(self, data: dict[str, Any], max_tokens: int) -> dict[str, Any]:
        choices = data.get("choices")
        choice = _mapping(choices[0]) if isinstance(choices, list) and choices else {}
        message = _mapping(choice.get("message"))
        details = _mapping(_mapping(data.get("usage")).get("completion_tokens_details"))
        return _parse_diagnostics(
            finish_reason=choice.get("finish_reason"), max_tokens=max_tokens,
            model=data.get("model") or self.model,
            visible_content=_text_content(message.get("content")),
            tool_calls=message.get("tool_calls"), usage=_usage_envelope(data.get("usage")),
            reasoning_tokens=details.get("reasoning_tokens"),
        )

    def _first_choice(self, data: dict[str, Any], max_tokens: int) -> dict[str, Any]:
        provider = self.provider
        provider_error = _provider_error_from_payload(data, provider=provider)
        if provider_error is not None:
            raise provider_error
        choices = data.get("choices") or []
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            usage, provider_cost, billing_uncertain = _response_billing_fields(data)
            raise LLMProviderError(
                f"{provider} returned no completion candidate",
                provider=provider,
                error_type="invalid_response",
                usage=usage,
                provider_cost_microusd=provider_cost,
                billing_uncertain=billing_uncertain,
                diagnostics=self._diagnostics(data, max_tokens),
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
        choice = self._first_choice(data, max_tokens)
        message = _mapping(choice.get("message"))
        usage = _usage_envelope(data.get("usage"))
        text = _text_content(message.get("content"))
        if not text.strip() and isinstance(message.get("refusal"), str):
            text = message["refusal"]
        if not text.strip():
            usage, provider_cost, billing_uncertain = _response_billing_fields(data)
            raise LLMProviderError(
                f"{self.provider} returned no text output",
                provider=self.provider,
                retryable=False,
                outage_candidate=False,
                error_type="invalid_response",
                usage=usage,
                provider_cost_microusd=provider_cost,
                billing_uncertain=billing_uncertain,
                diagnostics=self._diagnostics(data, max_tokens),
            )
        return LLMResponse(
            text=text,
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
        # Kimi K3 always reasons and its native provider rejects named choice
        # while thinking. A single advertised function plus required is portable.
        payload["tool_choice"] = (
            "required" if self.model_spec.id == "kimi-k3"
            else {"type": "function", "function": {"name": tool_name}}
        )
        if self.provider != "openrouter":
            payload["parallel_tool_calls"] = False

        start = time.monotonic()
        data = self._post(payload)
        latency_ms = int((time.monotonic() - start) * 1000)
        choice = self._first_choice(data, max_tokens)
        message = _mapping(choice.get("message"))
        calls = message.get("tool_calls") or []
        usage, provider_cost, billing_uncertain = _response_billing_fields(data)
        if not isinstance(calls, list) or len(calls) != 1 or not isinstance(calls[0], dict):
            raise LLMProviderError(
                f"{self.provider} did not return exactly one required tool call",
                provider=self.provider,
                retryable=False,
                outage_candidate=False,
                error_type="invalid_response",
                usage=usage,
                provider_cost_microusd=provider_cost,
                billing_uncertain=billing_uncertain,
                diagnostics=self._diagnostics(data, max_tokens),
            )
        function = _mapping(calls[0].get("function"))
        returned_name = str(function.get("name") or "")
        if returned_name != tool_name:
            raise LLMProviderError(
                f"{self.provider} returned the wrong tool",
                provider=self.provider,
                retryable=False,
                outage_candidate=False,
                error_type="invalid_response",
                usage=usage,
                provider_cost_microusd=provider_cost,
                billing_uncertain=billing_uncertain,
                diagnostics=self._diagnostics(data, max_tokens),
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
                error_type="invalid_response",
                usage=usage,
                provider_cost_microusd=provider_cost,
                billing_uncertain=billing_uncertain,
                diagnostics=self._diagnostics(data, max_tokens),
            ) from exc
        if not isinstance(tool_input, dict):
            raise LLMProviderError(
                f"{self.provider} returned non-object tool arguments",
                provider=self.provider,
                retryable=False,
                outage_candidate=False,
                error_type="invalid_response",
                usage=usage,
                provider_cost_microusd=provider_cost,
                billing_uncertain=billing_uncertain,
                diagnostics=self._diagnostics(data, max_tokens),
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
        return _post_json(self, "responses", payload)

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

    def _diagnostics(self, data: dict[str, Any], max_tokens: int) -> dict[str, Any]:
        output = data.get("output")
        items = (
            [item for item in output if isinstance(item, dict)]
            if isinstance(output, list) else []
        )
        details = _mapping(_mapping(data.get("usage")).get("output_tokens_details"))
        return _parse_diagnostics(
            finish_reason=self._responses_stop_reason(data), max_tokens=max_tokens,
            model=data.get("model") or self.model,
            visible_content="".join(
                _text_content(item.get("content")) for item in items if item.get("type") == "message"
            ),
            tool_calls=[{"function": item} for item in items if item.get("type") == "function_call"],
            usage=self._responses_usage(data), reasoning_tokens=details.get("reasoning_tokens"),
        )

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
                if not isinstance(content, dict):
                    continue
                if content.get("type") == "output_text" and isinstance(
                    content.get("text"), str
                ):
                    text_parts.append(content["text"])
                elif content.get("type") == "refusal" and isinstance(
                    content.get("refusal"), str
                ):
                    text_parts.append(content["refusal"])
        text = "".join(text_parts)
        if not text.strip():
            usage = self._responses_usage(data)
            raise LLMProviderError(
                f"{self.provider} returned no text output",
                provider=self.provider,
                retryable=False,
                outage_candidate=False,
                error_type="invalid_response",
                usage=usage,
                billing_uncertain=not any(value > 0 for value in usage.values()),
                diagnostics=self._diagnostics(data, max_tokens),
            )
        return LLMResponse(
            text=text,
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
                error_type="invalid_response",
                usage=usage,
                billing_uncertain=billing_uncertain,
                diagnostics=self._diagnostics(data, max_tokens),
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
                error_type="invalid_response",
                usage=usage,
                billing_uncertain=billing_uncertain,
                diagnostics=self._diagnostics(data, max_tokens),
            ) from exc
        if not isinstance(tool_input, dict):
            raise LLMProviderError(
                f"{self.provider} returned non-object tool arguments",
                provider=self.provider,
                retryable=False,
                outage_candidate=False,
                error_type="invalid_response",
                usage=usage,
                billing_uncertain=billing_uncertain,
                diagnostics=self._diagnostics(data, max_tokens),
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
        self.request_deadline: float | None = None
        self.request_dispatched = False
        self._client = httpx.Client(
            base_url=base_url.rstrip("/") + "/",
            headers={"x-goog-api-key": api_key},
            timeout=httpx.Timeout(timeout_seconds, connect=10.0),
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

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
        return _post_json(self, f"models/{self.model}:generateContent", payload)

    def _candidate(self, data: dict[str, Any], max_tokens: int) -> dict[str, Any]:
        candidates = data.get("candidates") or []
        if not isinstance(candidates, list) or not candidates or not isinstance(candidates[0], dict):
            usage = GeminiClient._usage(data)
            prompt_feedback = _mapping(data.get("promptFeedback"))
            blocked = bool(str(prompt_feedback.get("blockReason") or "").strip())
            raise LLMProviderError(
                (
                    "Google Gemini declined the request"
                    if blocked
                    else "Google Gemini returned no candidate"
                ),
                provider=self.provider,
                retryable=False,
                outage_candidate=False,
                error_type="content_blocked" if blocked else "invalid_response",
                usage=usage,
                billing_uncertain=not any(value > 0 for value in usage.values()),
                diagnostics=self._diagnostics(data, max_tokens),
            )
        return candidates[0]

    @staticmethod
    def _usage(data: dict[str, Any]) -> dict[str, int]:
        usage = _mapping(data.get("usageMetadata"))
        total_input = _nonnegative_int(usage.get("promptTokenCount"))
        tool_input = _nonnegative_int(usage.get("toolUsePromptTokenCount"))
        cache_read = _nonnegative_int(usage.get("cachedContentTokenCount"))
        generated = (
            _nonnegative_int(usage.get("candidatesTokenCount"))
            + _nonnegative_int(usage.get("thoughtsTokenCount"))
        )
        # totalTokenCount includes prompt, tool inputs, candidates, and thoughts.
        # Preserve billable output when a provider omits an individual count.
        generated = max(generated, _nonnegative_int(usage.get("totalTokenCount"))
                        - total_input - tool_input)
        return {
            "input_tokens": _exclusive_input_tokens(total_input, cache_read) + tool_input,
            "output_tokens": generated,
            "cache_read_input_tokens": cache_read,
            "cache_creation_input_tokens": 0,
        }

    def _diagnostics(self, data: dict[str, Any], max_tokens: int) -> dict[str, Any]:
        candidates = data.get("candidates")
        candidate = _mapping(candidates[0]) if isinstance(candidates, list) and candidates else {}
        raw_parts = _mapping(candidate.get("content")).get("parts")
        parts = (
            [part for part in raw_parts if isinstance(part, dict) and part.get("thought") is not True]
            if isinstance(raw_parts, list) else []
        )
        calls = [_mapping(part.get("functionCall")) for part in parts if part.get("functionCall")]
        return _parse_diagnostics(
            finish_reason=candidate.get("finishReason"), max_tokens=max_tokens,
            model=data.get("modelVersion") or self.model,
            visible_content="".join(
                part["text"] for part in parts if isinstance(part.get("text"), str)
            ),
            tool_calls=[
                {"function": {"name": call.get("name"), "arguments": call.get("args")}}
                for call in calls
            ],
            usage=self._usage(data),
            reasoning_tokens=_mapping(data.get("usageMetadata")).get("thoughtsTokenCount"),
        )

    def _base_payload(
        self,
        *,
        system: str | list[dict[str, Any]],
        messages: list[dict[str, Any]],
        max_tokens: int,
    ) -> dict[str, Any]:
        if max_tokens < 1 or max_tokens > self.model_spec.max_output_tokens:
            raise ValueError("requested output exceeds the selected model's token limit")
        # The hard output cap includes thoughts. Never add a separate thinking
        # allowance beyond the amount reserved by MeteredClient.
        generation: dict[str, Any] = {
            "maxOutputTokens": max_tokens, "temperature": 0, "candidateCount": 1,
        }
        if self.model.startswith("gemini-3") and self.model_spec.reasoning_effort:
            effort = self.model_spec.reasoning_effort.lower()
            if effort not in {"minimal", "low", "medium", "high"}:
                raise ValueError("unsupported Gemini thinking level")
            generation["thinkingConfig"] = {"thinkingLevel": effort.upper()}
        return {
            "systemInstruction": {"parts": [{"text": _flatten_system(system)}]},
            "contents": self._contents(messages),
            "generationConfig": generation,
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
        candidate = self._candidate(data, max_tokens)
        parts = _mapping(candidate.get("content")).get("parts") or []
        text = "".join(
            str(part.get("text"))
            for part in parts
            if isinstance(part, dict) and part.get("thought") is not True
            and isinstance(part.get("text"), str)
        )
        usage = self._usage(data)
        if not text.strip():
            raise LLMProviderError(
                "Google Gemini returned no text output",
                provider=self.provider,
                retryable=False,
                outage_candidate=False,
                error_type="invalid_response",
                usage=usage,
                billing_uncertain=not any(value > 0 for value in usage.values()),
                diagnostics=self._diagnostics(data, max_tokens),
            )
        return LLMResponse(
            text=text,
            stop_reason=str(candidate.get("finishReason") or "STOP"),
            usage=usage,
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
        candidate = self._candidate(data, max_tokens)
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
                error_type="invalid_response",
                usage=usage,
                billing_uncertain=not any(value > 0 for value in usage.values()),
                diagnostics=self._diagnostics(data, max_tokens),
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


class VertexGeminiClient(GeminiClient):
    """Gemini through the configured CloudBank GCP project, using OAuth/ADC."""

    def __init__(
        self, *, model: str, model_spec: ModelSpec, project: str,
        location: str = "global", route: str | None = None,
        token_provider: Any = None, timeout_seconds: float = 45.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9-]{4,61}[a-z0-9]", project):
            raise ValueError("a valid CloudBank GCP project is required")
        if not re.fullmatch(r"[a-z][a-z0-9-]{1,62}", location):
            raise ValueError("a valid Vertex AI location is required")
        self.model = model
        self.model_spec = model_spec
        self.provider = "gcp-vertex"
        self.billing_source = "cloudbank"
        self.route = route or f"gcp-vertex:{model}"
        self.request_deadline: float | None = None
        self.request_dispatched = False
        self.project = project
        self._token_provider = token_provider or self._access_token
        host = "aiplatform.googleapis.com" if location == "global" else f"{location}-aiplatform.googleapis.com"
        self._client = httpx.Client(
            base_url=f"https://{host}/v1/projects/{project}/locations/{location}/publishers/google/",
            timeout=httpx.Timeout(timeout_seconds, connect=10.0), transport=transport,
        )
        self._credentials: Any = None

    def _access_token(self) -> str:
        # A short-lived token can be injected by the controlled evaluation
        # launcher. Hosted deployments should use ADC/workload identity.
        token = (os.getenv("GOOGLE_VERTEX_ACCESS_TOKEN") or "").strip()
        if token:
            return token
        try:
            import google.auth
            from google.auth.transport.requests import Request
            auth_request = Request()

            def bounded_request(*args: Any, **kwargs: Any) -> Any:
                remaining = remaining_request_seconds(self.request_deadline, provider=self.provider)
                configured = kwargs.get("timeout")
                bound = min(float(configured), 45.0) if isinstance(configured, (int, float)) else 45.0
                kwargs["timeout"] = min(bound, remaining) if remaining is not None else bound
                return auth_request(*args, **kwargs)

            if self._credentials is None:
                self._credentials, _ = google.auth.default(
                    scopes=["https://www.googleapis.com/auth/cloud-platform"],
                    quota_project_id=self.project,
                    request=bounded_request,
                )
            if not self._credentials.valid:
                self._credentials.refresh(bounded_request)
            if not self._credentials.token:
                raise RuntimeError("no access token")
            return str(self._credentials.token)
        except LLMRequestDeadlineError:
            raise
        except Exception as exc:
            raise LLMProviderError(
                "CloudBank GCP authentication is unavailable", provider=self.provider,
                status_code=401, error_type="provider_configuration",
            ) from exc

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        remaining_request_seconds(self.request_deadline, provider=self.provider)
        self._client.headers["Authorization"] = f"Bearer {self._token_provider()}"
        self._client.headers["x-goog-user-project"] = self.project
        return super()._post(payload)
