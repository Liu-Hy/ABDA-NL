"""Task profiles, bounded retries, failover, BYOK, and per-call metering."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_CEILING
from typing import Any

import httpx
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.safe_logging import exception_diagnostic
from app.db.session import get_session_factory
from app.llm.catalog import (
    ModelCatalog,
    ModelSpec,
    RouteSpec,
    TokenPricing,
    load_model_catalog,
)
from app.llm.client import (
    ClaudeClient,
    LLMClient,
    LLMResponse,
    ToolCallResponse,
    close_llm_client,
)
from app.llm.providers import (
    GeminiClient,
    LLMProviderError,
    OpenAICompatibleClient,
    OpenAIResponsesClient,
    transport_billing_uncertainty,
)
from app.services.llm_billing import (
    CallReservation,
    record_llm_event,
    release_llm_call,
    reserve_llm_call,
    settle_llm_call,
    usage_event,
)


log = logging.getLogger(__name__)


OPENROUTER_REQUEST_MODELS = {
    "claude-sonnet-4-6": "anthropic/claude-sonnet-4.6",
    "claude-sonnet-5": "anthropic/claude-sonnet-5",
    "gpt-5.4-mini": "openai/gpt-5.4-mini",
    "gpt-5.5": "openai/gpt-5.5",
    "gpt-5.6-luna": "openai/gpt-5.6-luna",
    "gpt-5.6-terra": "openai/gpt-5.6-terra",
    "gpt-5.6-sol": "openai/gpt-5.6-sol",
    "gemini-3.6-flash": "google/gemini-3.6-flash",
    "gemini-3.7-flash": "google/gemini-3.7-flash",
    "deepseek-v4-flash": "deepseek/deepseek-v4-flash",
    "deepseek-v4-pro": "deepseek/deepseek-v4-pro",
}


class LLMRouteConfigurationError(RuntimeError):
    pass


class BYOKValidationError(ValueError):
    pass


class PaidRunCapReached(RuntimeError):
    """Raised before a paid provider call that cannot fit within a run cap."""


@dataclass(frozen=True)
class SpendCapReservation:
    token: int
    amount_microusd: int


class LocalSpendCap:
    """Thread-safe in-process reservation ledger for one evaluation run."""

    def __init__(self, limit_microusd: int) -> None:
        if limit_microusd < 1:
            raise ValueError("the paid run cap must be positive")
        self.limit_microusd = limit_microusd
        self._spent_microusd = 0
        self._reserved_microusd = 0
        self._next_token = 1
        self._pending: dict[int, int] = {}
        self._reached = False
        self._lock = threading.Lock()

    @property
    def spent_microusd(self) -> int:
        with self._lock:
            return self._spent_microusd

    @property
    def reserved_microusd(self) -> int:
        with self._lock:
            return self._reserved_microusd

    @property
    def reached(self) -> bool:
        with self._lock:
            return self._reached

    def reserve(self, amount_microusd: int) -> SpendCapReservation:
        if amount_microusd < 1:
            raise ValueError("spend cap reservations must be positive")
        with self._lock:
            committed = self._spent_microusd + self._reserved_microusd
            if amount_microusd > self.limit_microusd - committed:
                self._reached = True
                raise PaidRunCapReached(
                    "the evaluation paid-route cap cannot accommodate another call"
                )
            token = self._next_token
            self._next_token += 1
            self._pending[token] = amount_microusd
            self._reserved_microusd += amount_microusd
            return SpendCapReservation(
                token=token,
                amount_microusd=amount_microusd,
            )

    def settle(
        self,
        reservation: SpendCapReservation,
        actual_microusd: int,
    ) -> None:
        if actual_microusd < 0:
            raise ValueError("settled spend cannot be negative")
        if actual_microusd > reservation.amount_microusd:
            raise RuntimeError("settled spend exceeds its conservative reservation")
        with self._lock:
            amount = self._pending.pop(reservation.token, None)
            if amount != reservation.amount_microusd:
                raise RuntimeError("spend cap reservation is not pending")
            self._reserved_microusd -= amount
            self._spent_microusd += actual_microusd

    def release(self, reservation: SpendCapReservation) -> None:
        with self._lock:
            amount = self._pending.pop(reservation.token, None)
            if amount != reservation.amount_microusd:
                raise RuntimeError("spend cap reservation is not pending")
            self._reserved_microusd -= amount


@dataclass(frozen=True)
class BYOKCredential:
    provider: str
    api_key: str = field(repr=False)
    model: str | None = None


@dataclass(frozen=True)
class CallContext:
    user_id: str | None
    request_id: str | None
    request_kind: str
    charge_trial: bool


def _env(name: str) -> str | None:
    value = (os.getenv(name) or "").strip()
    return value or None


def _azure_v1_base_url() -> str:
    endpoint = (
        _env("AZURE_OPENAI_ENDPOINT")
        or _env("ANTHROPIC_FOUNDRY_PROJECT_ENDPOINT")
        or ""
    ).rstrip("/")
    if not endpoint:
        raise LLMRouteConfigurationError("the Azure OpenAI endpoint is not configured")
    if endpoint.endswith("/openai/v1"):
        return endpoint
    return f"{endpoint}/openai/v1"


def _privacy_identifier(user_id: str | None, secret: str) -> str | None:
    if not user_id:
        return None
    return hmac.new(
        secret.encode("utf-8"), user_id.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def _request_size_tokens(
    *,
    system: str | list[dict[str, Any]],
    messages: list[dict[str, Any]],
    tool: dict[str, Any] | None,
) -> int:
    serialized = json.dumps(
        {"system": system, "messages": messages, "tool": tool},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return max(1, len(serialized) + 1024)


def _multiply_cost_microusd(cost_microusd: int, multiplier: Decimal) -> int:
    return int(
        (Decimal(max(0, cost_microusd)) * multiplier).to_integral_value(
            rounding=ROUND_CEILING
        )
    )


def _has_positive_usage(usage: dict[str, int]) -> bool:
    return any(
        isinstance(value, int) and not isinstance(value, bool) and value > 0
        for value in usage.values()
    )


def _openrouter_provider_preferences(
    pricing: TokenPricing | None = None,
) -> dict[str, Any]:
    preferences: dict[str, Any] = {
        "sort": "price",
        "allow_fallbacks": True,
        "require_parameters": True,
        "data_collection": "deny",
        "zdr": True,
    }
    if pricing is not None:
        preferences["max_price"] = {
            "prompt": float(pricing.input_usd_per_million),
            "completion": float(pricing.output_usd_per_million),
        }
    return preferences


def _classified_error(exc: Exception, provider: str) -> LLMProviderError | None:
    if isinstance(exc, LLMProviderError):
        return exc
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return LLMProviderError(
            f"{provider} could not be reached",
            provider=provider,
            retryable=True,
            outage_candidate=True,
            billing_uncertain=transport_billing_uncertainty(exc) is not False,
        )
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        retryable = status in {408, 409, 425, 429} or status >= 500
        outage = status in {408, 425, 429} or status >= 500
        return LLMProviderError(
            f"{provider} returned HTTP {status}",
            provider=provider,
            status_code=status,
            retryable=retryable,
            outage_candidate=outage,
        )
    name = type(exc).__name__.lower()
    if "timeout" in name or "connection" in name:
        uncertainty = transport_billing_uncertainty(exc)
        return LLMProviderError(
            f"{provider} could not be reached",
            provider=provider,
            retryable=True,
            outage_candidate=True,
            billing_uncertain=(
                uncertainty if uncertainty is not None else True
            ),
        )
    return None


class MeteredClient:
    """Reserve, invoke, settle, and audit one physical provider attempt."""

    def __init__(
        self,
        inner: LLMClient,
        *,
        model_spec: ModelSpec,
        cost_ceiling: TokenPricing | None = None,
        use_provider_reported_cost: bool = False,
        billing_multiplier: Decimal = Decimal("1"),
        context: CallContext,
        charge_emergency: bool,
        spend_cap: LocalSpendCap | None = None,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        self.inner = inner
        self.model_spec = model_spec
        self.cost_ceiling = cost_ceiling or model_spec.pricing
        self.use_provider_reported_cost = use_provider_reported_cost
        self.billing_multiplier = billing_multiplier
        self.context = context
        self.charge_emergency = charge_emergency
        self.spend_cap = spend_cap
        self.session_factory = session_factory or get_session_factory()
        self.model = getattr(inner, "model", model_spec.id)
        self.provider = getattr(inner, "provider", "unknown")
        self.billing_source = getattr(inner, "billing_source", "unknown")
        self.route = getattr(inner, "route", "unknown")

    def close(self) -> None:
        close_llm_client(self.inner)

    def _settled_cost_microusd(
        self,
        usage: dict[str, int],
        provider_cost_microusd: int | None,
    ) -> int:
        reported_cost = (
            provider_cost_microusd
            if self.use_provider_reported_cost
            else None
        )
        base_cost = (
            reported_cost
            if reported_cost is not None
            else self.cost_ceiling.cost_microusd(usage)
        )
        return _multiply_cost_microusd(base_cost, self.billing_multiplier)

    def _invoke(
        self,
        method: str,
        *,
        system: str | list[dict[str, Any]],
        messages: list[dict[str, Any]],
        max_tokens: int,
        cache: bool,
        tool: dict[str, Any] | None = None,
    ) -> LLMResponse | ToolCallResponse:
        estimated_input = _request_size_tokens(
            system=system,
            messages=messages,
            tool=tool,
        )
        amount = _multiply_cost_microusd(
            self.cost_ceiling.conservative_cost_microusd(
                estimated_input_tokens=estimated_input,
                max_output_tokens=max_tokens,
            ),
            self.billing_multiplier,
        )
        spend_reservation = self.spend_cap.reserve(amount) if self.spend_cap else None
        reservation = CallReservation(amount_microusd=amount)
        try:
            if self.context.charge_trial or self.charge_emergency:
                with self.session_factory() as session:
                    reservation = reserve_llm_call(
                        session,
                        amount_microusd=amount,
                        user_id=self.context.user_id,
                        provider=self.provider,
                        route=self.route,
                        model=self.model_spec.id,
                        request_kind=self.context.request_kind,
                        charge_trial=self.context.charge_trial,
                        charge_emergency=self.charge_emergency,
                    )
        except Exception:
            if spend_reservation is not None:
                self.spend_cap.release(spend_reservation)
            raise

        try:
            call = getattr(self.inner, method)
            kwargs: dict[str, Any] = {
                "system": system,
                "messages": messages,
                "max_tokens": max_tokens,
                "cache": cache,
            }
            if tool is not None:
                kwargs["tool"] = tool
            response = call(**kwargs)
        except Exception as exc:
            classified = _classified_error(exc, self.provider)
            accounting_error = classified or exc
            failed_usage = getattr(accounting_error, "usage", {})
            if not isinstance(failed_usage, dict):
                failed_usage = {}
            failed_provider_cost = getattr(
                accounting_error, "provider_cost_microusd", None
            )
            billing_uncertain = bool(
                getattr(accounting_error, "billing_uncertain", False)
            )
            has_usage = _has_positive_usage(failed_usage)
            if failed_provider_cost is not None or has_usage:
                failed_cost = self._settled_cost_microusd(
                    failed_usage,
                    failed_provider_cost,
                )
            elif billing_uncertain:
                failed_cost = reservation.amount_microusd
            else:
                failed_cost = 0
            provider_error_type = getattr(accounting_error, "error_type", None)
            error_type = type(exc).__name__
            if provider_error_type:
                error_type += f":{provider_error_type}"
            if billing_uncertain:
                error_type += ":billing_uncertain"
            event = usage_event(
                request_id=self.context.request_id,
                user_id=self.context.user_id,
                provider=self.provider,
                route=self.route,
                model=self.model_spec.id,
                billing_source=self.billing_source,
                request_kind=self.context.request_kind,
                status="failed",
                usage=failed_usage,
                cost_microusd=failed_cost,
                error_type=error_type,
            )
            try:
                with self.session_factory() as session:
                    if reservation.trial_reservation_id or reservation.emergency_reservation_id:
                        if failed_cost:
                            settle_llm_call(
                                session,
                                reservation,
                                actual_microusd=failed_cost,
                                event=event,
                            )
                        else:
                            release_llm_call(session, reservation, event=event)
                    else:
                        record_llm_event(session, event)
            except Exception as accounting_exc:  # noqa: BLE001
                diagnostic = exception_diagnostic(accounting_exc)
                log.error(
                    "llm_failure_accounting_failed route=%s exception=%s location=%s",
                    self.route,
                    diagnostic.kind,
                    diagnostic.location,
                )
            if spend_reservation is not None:
                if failed_cost:
                    self.spend_cap.settle(spend_reservation, failed_cost)
                else:
                    self.spend_cap.release(spend_reservation)
            raise

        billing_uncertain = (
            response.provider_cost_microusd is None
            and not _has_positive_usage(response.usage)
        )
        actual_cost = (
            reservation.amount_microusd
            if billing_uncertain
            else self._settled_cost_microusd(
                response.usage,
                response.provider_cost_microusd,
            )
        )
        response.cost_microusd = actual_cost
        event = usage_event(
            request_id=self.context.request_id,
            user_id=self.context.user_id,
            provider=response.provider,
            route=response.route,
            model=self.model_spec.id,
            billing_source=response.billing_source,
            request_kind=self.context.request_kind,
            status="succeeded",
            usage=response.usage,
            cost_microusd=actual_cost,
            latency_ms=response.latency_ms,
            error_type="billing_uncertain" if billing_uncertain else None,
        )
        try:
            with self.session_factory() as session:
                if reservation.trial_reservation_id or reservation.emergency_reservation_id:
                    settle_llm_call(
                        session,
                        reservation,
                        actual_microusd=actual_cost,
                        event=event,
                    )
                else:
                    record_llm_event(session, event)
        finally:
            if spend_reservation is not None:
                self.spend_cap.settle(spend_reservation, actual_cost)
        return response

    def complete(
        self,
        *,
        system: str | list[dict[str, Any]],
        messages: list[dict[str, Any]],
        max_tokens: int,
        cache: bool = True,
    ) -> LLMResponse:
        result = self._invoke(
            "complete",
            system=system,
            messages=messages,
            max_tokens=max_tokens,
            cache=cache,
        )
        if not isinstance(result, LLMResponse):
            raise TypeError("complete returned an unexpected response type")
        return result

    def tool_call(
        self,
        *,
        system: str | list[dict[str, Any]],
        messages: list[dict[str, Any]],
        tool: dict[str, Any],
        max_tokens: int,
        cache: bool = True,
    ) -> ToolCallResponse:
        result = self._invoke(
            "tool_call",
            system=system,
            messages=messages,
            tool=tool,
            max_tokens=max_tokens,
            cache=cache,
        )
        if not isinstance(result, ToolCallResponse):
            raise TypeError("tool_call returned an unexpected response type")
        return result


class RetryingClient:
    def __init__(self, inner: LLMClient, *, attempts: int) -> None:
        self.inner = inner
        self.attempts = attempts
        self.model = getattr(inner, "model", "unknown")
        self.provider = getattr(inner, "provider", "unknown")
        self.billing_source = getattr(inner, "billing_source", "unknown")
        self.route = getattr(inner, "route", "unknown")

    def close(self) -> None:
        close_llm_client(self.inner)

    def _invoke(self, method: str, **kwargs: Any) -> Any:
        last_error: LLMProviderError | None = None
        for attempt in range(1, self.attempts + 1):
            try:
                return getattr(self.inner, method)(**kwargs)
            except Exception as exc:
                classified = _classified_error(exc, self.provider)
                if classified is None:
                    raise
                last_error = classified
                if not classified.retryable or attempt >= self.attempts:
                    raise classified from exc
                delay = min(1.0, 0.15 * (2 ** (attempt - 1)))
                log.info(
                    "llm_retry route=%s attempt=%d max_attempts=%d status=%s",
                    self.route,
                    attempt,
                    self.attempts,
                    classified.status_code,
                )
                time.sleep(delay)
        if last_error is not None:
            raise last_error
        raise RuntimeError("retry loop completed without a result")

    def complete(self, **kwargs: Any) -> LLMResponse:
        return self._invoke("complete", **kwargs)

    def tool_call(self, **kwargs: Any) -> ToolCallResponse:
        return self._invoke("tool_call", **kwargs)


@dataclass
class _CircuitState:
    open_until: float = 0.0


class CircuitRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._states: dict[str, _CircuitState] = {}

    def primary_allowed(self, route: str) -> bool:
        with self._lock:
            state = self._states.setdefault(route, _CircuitState())
            return time.monotonic() >= state.open_until

    def open(self, route: str, cooldown_seconds: int) -> None:
        with self._lock:
            state = self._states.setdefault(route, _CircuitState())
            state.open_until = time.monotonic() + cooldown_seconds

    def close(self, route: str) -> None:
        with self._lock:
            self._states.setdefault(route, _CircuitState()).open_until = 0.0


_CIRCUITS = CircuitRegistry()


class FailoverClient:
    def __init__(
        self,
        primary: LLMClient,
        fallback: LLMClient | None,
        *,
        cooldown_seconds: int,
        circuits: CircuitRegistry = _CIRCUITS,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.cooldown_seconds = cooldown_seconds
        self.circuits = circuits
        self.model = getattr(primary, "model", "unknown")
        self.provider = getattr(primary, "provider", "unknown")
        self.billing_source = getattr(primary, "billing_source", "unknown")
        self.route = getattr(primary, "route", "unknown")

    def close(self) -> None:
        close_llm_client(self.primary)
        if self.fallback is not None and self.fallback is not self.primary:
            close_llm_client(self.fallback)

    def _invoke(self, method: str, **kwargs: Any) -> Any:
        if self.fallback is None:
            return getattr(self.primary, method)(**kwargs)
        if self.circuits.primary_allowed(self.route):
            try:
                result = getattr(self.primary, method)(**kwargs)
                self.circuits.close(self.route)
                return result
            except LLMProviderError as exc:
                if not exc.outage_candidate:
                    raise
                self.circuits.open(self.route, self.cooldown_seconds)
                log.error(
                    "llm_circuit_open primary=%s fallback=%s cooldown_seconds=%d",
                    self.route,
                    getattr(self.fallback, "route", "unknown"),
                    self.cooldown_seconds,
                )
        return getattr(self.fallback, method)(**kwargs)

    def complete(self, **kwargs: Any) -> LLMResponse:
        return self._invoke("complete", **kwargs)

    def tool_call(self, **kwargs: Any) -> ToolCallResponse:
        return self._invoke("tool_call", **kwargs)


class LLMRouter:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        catalog: ModelCatalog | None = None,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.catalog = catalog or load_model_catalog()
        self.session_factory = session_factory or get_session_factory()

    def _raw_route(
        self, route: RouteSpec, *, user_id: str | None
    ) -> tuple[LLMClient, ModelSpec]:
        model_spec = self.catalog.model_for_route(route)
        request_model = _env(route.model_env) if route.model_env else None
        request_model = request_model or route.request_model
        if route.adapter == "anthropic":
            if route.provider != "azure-foundry":
                raise LLMRouteConfigurationError("unsupported funded Anthropic route")
            client: LLMClient = ClaudeClient(
                model=request_model,
                provider="foundry",
                billing_source=route.billing_source,
                route=route.id,
                sdk_max_retries=0,
            )
            return client, model_spec
        if route.provider == "azure-foundry":
            key = _env("AZURE_OPENAI_API_KEY") or _env("AZURE_ANTHROPIC_API_KEY")
            if not key:
                raise LLMRouteConfigurationError("the Azure API key is not configured")
            common: dict[str, Any] = {
                "model": request_model,
                "model_spec": model_spec,
                "provider": route.provider,
                "billing_source": route.billing_source,
                "route": route.id,
                "base_url": _azure_v1_base_url(),
                "api_key": key,
                "auth_style": "api-key",
            }
            if route.adapter == "openai-responses":
                client = OpenAIResponsesClient(
                    **common,
                    reasoning_effort="low",
                    safety_identifier=_privacy_identifier(
                        user_id, self.settings.session_secret
                    ),
                )
            else:
                client = OpenAICompatibleClient(**common)
            return client, model_spec
        if route.provider == "openrouter":
            key = _env("OPENROUTER_API_KEY")
            if not key:
                raise LLMRouteConfigurationError("the OpenRouter API key is not configured")
            client = OpenAICompatibleClient(
                model=request_model,
                model_spec=model_spec,
                provider="openrouter",
                billing_source=route.billing_source,
                route=route.id,
                base_url="https://openrouter.ai/api/v1",
                api_key=key,
                headers={
                    "HTTP-Referer": self.settings.public_base_url
                    or "https://github.com/idaks/ABDA-NL",
                    "X-Title": "ABDA-NL",
                },
                provider_preferences=_openrouter_provider_preferences(
                    self.catalog.cost_ceiling_for_route(route)
                ),
            )
            return client, model_spec
        raise LLMRouteConfigurationError(f"unsupported route provider {route.provider!r}")

    def _metered_retrying(
        self,
        route: RouteSpec,
        *,
        context: CallContext,
        spend_cap: LocalSpendCap | None = None,
    ) -> LLMClient:
        raw, model_spec = self._raw_route(route, user_id=context.user_id)
        metered = MeteredClient(
            raw,
            model_spec=model_spec,
            cost_ceiling=self.catalog.cost_ceiling_for_route(route),
            use_provider_reported_cost=route.use_provider_reported_cost,
            billing_multiplier=route.billing_multiplier,
            context=context,
            charge_emergency=route.billing_source == "openrouter-emergency",
            spend_cap=spend_cap,
            session_factory=self.session_factory,
        )
        return RetryingClient(metered, attempts=self.settings.llm_retry_attempts)

    def funded(self, profile_id: str | None, *, context: CallContext) -> LLMClient:
        chosen = (profile_id or self.settings.llm_default_profile).strip().lower()
        try:
            profile = self.catalog.profiles[chosen]
        except KeyError as exc:
            raise LLMRouteConfigurationError(f"unknown model profile {chosen!r}") from exc
        primary_route = self.catalog.routes[profile.primary_route]
        primary = self._metered_retrying(primary_route, context=context)
        fallback: LLMClient | None = None
        if self.settings.openrouter_failover_enabled and profile.fallback_route:
            fallback_route = self.catalog.routes[profile.fallback_route]
            try:
                fallback = self._metered_retrying(fallback_route, context=context)
            except LLMRouteConfigurationError:
                log.warning("OpenRouter failover is enabled but not configured")
        return FailoverClient(
            primary,
            fallback,
            cooldown_seconds=self.settings.llm_circuit_cooldown_seconds,
        )

    def evaluation_route(
        self,
        route_id: str,
        *,
        context: CallContext,
        allow_emergency_spend: bool = False,
        spend_cap: LocalSpendCap | None = None,
    ) -> LLMClient:
        """Build one isolated route for reproducible quality evaluation."""
        try:
            route = self.catalog.routes[route_id]
        except KeyError as exc:
            raise LLMRouteConfigurationError(
                f"unknown evaluation route {route_id!r}"
            ) from exc
        if (
            route.billing_source == "openrouter-emergency"
            and not allow_emergency_spend
        ):
            raise LLMRouteConfigurationError(
                "OpenRouter evaluation requires explicit paid-route permission"
            )
        return self._metered_retrying(route, context=context, spend_cap=spend_cap)

    def byok(self, credential: BYOKCredential, *, context: CallContext) -> LLMClient:
        if not self.settings.llm_allow_byok:
            raise BYOKValidationError("BYOK is disabled on this deployment")
        provider = credential.provider.strip().lower()
        if provider not in self.catalog.byok_defaults:
            raise BYOKValidationError("unsupported BYOK provider")
        if not credential.api_key.strip() or len(credential.api_key) > 4096:
            raise BYOKValidationError("invalid provider API key")
        default = self.catalog.byok_defaults[provider]
        model_id = (credential.model or default.model).strip()
        try:
            model_spec = self.catalog.models[model_id]
        except KeyError as exc:
            raise BYOKValidationError("unsupported BYOK model") from exc
        if provider != "openrouter" and model_spec.family != provider:
            raise BYOKValidationError("the selected model does not match the provider")

        request_model = (
            default.request_model if model_id == default.model else model_id
        )
        if provider == "openrouter" and model_id != default.model:
            request_model = OPENROUTER_REQUEST_MODELS.get(model_id, "")
            if not request_model:
                raise BYOKValidationError("unsupported OpenRouter model")

        safety_identifier = _privacy_identifier(
            context.user_id, self.settings.session_secret
        )
        if provider == "anthropic":
            raw: LLMClient = ClaudeClient(
                model=request_model,
                provider="anthropic",
                api_key=credential.api_key,
                billing_source="byok",
                route=f"byok:anthropic:{model_id}",
                sdk_max_retries=0,
            )
        elif provider == "openai":
            raw = OpenAIResponsesClient(
                model=request_model,
                model_spec=model_spec,
                provider="openai",
                billing_source="byok",
                route=f"byok:openai:{model_id}",
                base_url="https://api.openai.com/v1",
                api_key=credential.api_key,
                reasoning_effort="low",
                safety_identifier=safety_identifier,
            )
        elif provider == "google":
            raw = GeminiClient(
                model=request_model,
                model_spec=model_spec,
                api_key=credential.api_key,
                route=f"byok:google:{model_id}",
            )
        else:
            raw = OpenAICompatibleClient(
                model=request_model,
                model_spec=model_spec,
                provider="openrouter",
                billing_source="byok",
                route=f"byok:openrouter:{model_id}",
                base_url="https://openrouter.ai/api/v1",
                api_key=credential.api_key,
                headers={
                    "HTTP-Referer": self.settings.public_base_url
                    or "https://github.com/idaks/ABDA-NL",
                    "X-Title": "ABDA-NL",
                },
                provider_preferences=_openrouter_provider_preferences(),
            )
        metered = MeteredClient(
            raw,
            model_spec=model_spec,
            use_provider_reported_cost=provider == "openrouter",
            billing_multiplier=(
                Decimal("1.055") if provider == "openrouter" else Decimal("1")
            ),
            context=CallContext(
                user_id=context.user_id,
                request_id=context.request_id,
                request_kind=context.request_kind,
                charge_trial=False,
            ),
            charge_emergency=False,
            session_factory=self.session_factory,
        )
        return RetryingClient(metered, attempts=self.settings.llm_retry_attempts)
