"""Validated model, route, and profile catalog for LLM routing."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import yaml


CATALOG_PATH = Path(__file__).with_name("models.yaml")
USAGE_KEYS = {
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
}


@dataclass(frozen=True)
class TokenPricing:
    """Token prices in USD per million tokens."""

    input_usd_per_million: Decimal
    output_usd_per_million: Decimal
    cache_read_usd_per_million: Decimal
    cache_write_usd_per_million: Decimal

    def cost_microusd(self, usage: Mapping[str, int]) -> int:
        """Price mutually exclusive usage categories, rounded up."""
        components = (
            (usage.get("input_tokens", 0), self.input_usd_per_million),
            (usage.get("output_tokens", 0), self.output_usd_per_million),
            (usage.get("cache_read_input_tokens", 0), self.cache_read_usd_per_million),
            (
                usage.get("cache_creation_input_tokens", 0),
                self.cache_write_usd_per_million,
            ),
        )
        total = sum(Decimal(max(0, int(tokens))) * rate for tokens, rate in components)
        return int(total.to_integral_value(rounding=ROUND_CEILING))

    def conservative_cost_microusd(
        self,
        *,
        estimated_input_tokens: int,
        max_output_tokens: int,
    ) -> int:
        """Reserve enough for uncached input and the full output allowance."""
        input_rate = max(
            self.input_usd_per_million,
            self.cache_read_usd_per_million,
            self.cache_write_usd_per_million,
        )
        total = (
            Decimal(max(1, estimated_input_tokens)) * input_rate
            + Decimal(max(1, max_output_tokens)) * self.output_usd_per_million
        )
        return max(1, int(total.to_integral_value(rounding=ROUND_CEILING)))


@dataclass(frozen=True)
class ModelSpec:
    id: str
    family: str
    display_name: str
    input_usd_per_million: Decimal
    output_usd_per_million: Decimal
    cache_read_usd_per_million: Decimal
    cache_write_usd_per_million: Decimal
    context_tokens: int
    structured_tools: bool
    max_token_field: str = "max_tokens"  # noqa: S105  (request field, not a secret)

    @property
    def pricing(self) -> TokenPricing:
        return TokenPricing(
            input_usd_per_million=self.input_usd_per_million,
            output_usd_per_million=self.output_usd_per_million,
            cache_read_usd_per_million=self.cache_read_usd_per_million,
            cache_write_usd_per_million=self.cache_write_usd_per_million,
        )

    def cost_microusd(self, usage: Mapping[str, int]) -> int:
        return self.pricing.cost_microusd(usage)

    def conservative_cost_microusd(
        self,
        *,
        estimated_input_tokens: int,
        max_output_tokens: int,
    ) -> int:
        return self.pricing.conservative_cost_microusd(
            estimated_input_tokens=estimated_input_tokens,
            max_output_tokens=max_output_tokens,
        )


@dataclass(frozen=True)
class RouteSpec:
    id: str
    adapter: str
    provider: str
    billing_source: str
    model: str
    request_model: str
    model_env: str | None = None
    cost_ceiling: TokenPricing | None = None
    use_provider_reported_cost: bool = False
    billing_multiplier: Decimal = Decimal("1")


@dataclass(frozen=True)
class ProfileSpec:
    id: str
    display_name: str
    description: str
    public_ready: bool
    primary_route: str
    fallback_route: str | None


@dataclass(frozen=True)
class ByokDefault:
    provider: str
    display_name: str
    model: str
    request_model: str


@dataclass(frozen=True)
class ModelCatalog:
    version: int
    updated: str
    models: dict[str, ModelSpec]
    routes: dict[str, RouteSpec]
    profiles: dict[str, ProfileSpec]
    byok_defaults: dict[str, ByokDefault]

    def model_for_route(self, route: RouteSpec) -> ModelSpec:
        try:
            return self.models[route.model]
        except KeyError as exc:
            raise RuntimeError(
                f"route {route.id!r} references unknown model {route.model!r}"
            ) from exc

    def cost_ceiling_for_route(self, route: RouteSpec) -> TokenPricing:
        return route.cost_ceiling or self.model_for_route(route).pricing


def _decimal(value: Any, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"invalid decimal in model catalog field {field}") from exc
    if not parsed.is_finite() or parsed < 0:
        raise RuntimeError(f"model catalog field {field} must be finite and nonnegative")
    return parsed


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError(f"model catalog field {field} must be a mapping")
    return value


def _token_pricing(value: Any, field: str) -> TokenPricing:
    item = _mapping(value, field)
    return TokenPricing(
        input_usd_per_million=_decimal(
            item["input_usd_per_million"], f"{field}.input"
        ),
        output_usd_per_million=_decimal(
            item["output_usd_per_million"], f"{field}.output"
        ),
        cache_read_usd_per_million=_decimal(
            item.get("cache_read_usd_per_million", 0), f"{field}.cache_read"
        ),
        cache_write_usd_per_million=_decimal(
            item.get("cache_write_usd_per_million", 0), f"{field}.cache_write"
        ),
    )


@lru_cache(maxsize=1)
def load_model_catalog(path: Path = CATALOG_PATH) -> ModelCatalog:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    root = _mapping(raw, "root")

    models: dict[str, ModelSpec] = {}
    for model_id, value in _mapping(root.get("models"), "models").items():
        item = _mapping(value, f"models.{model_id}")
        models[model_id] = ModelSpec(
            id=model_id,
            family=str(item["family"]),
            display_name=str(item["display_name"]),
            input_usd_per_million=_decimal(
                item["input_usd_per_million"], f"models.{model_id}.input"
            ),
            output_usd_per_million=_decimal(
                item["output_usd_per_million"], f"models.{model_id}.output"
            ),
            cache_read_usd_per_million=_decimal(
                item.get("cache_read_usd_per_million", 0),
                f"models.{model_id}.cache_read",
            ),
            cache_write_usd_per_million=_decimal(
                item.get("cache_write_usd_per_million", 0),
                f"models.{model_id}.cache_write",
            ),
            context_tokens=int(item["context_tokens"]),
            structured_tools=bool(item.get("structured_tools", False)),
            max_token_field=str(item.get("max_token_field", "max_tokens")),
        )

    routes: dict[str, RouteSpec] = {}
    for route_id, value in _mapping(root.get("routes"), "routes").items():
        item = _mapping(value, f"routes.{route_id}")
        model_id = str(item["model"])
        routes[route_id] = RouteSpec(
            id=route_id,
            adapter=str(item["adapter"]),
            provider=str(item["provider"]),
            billing_source=str(item["billing_source"]),
            model=model_id,
            request_model=str(item.get("request_model") or model_id),
            model_env=str(item["model_env"]) if item.get("model_env") else None,
            cost_ceiling=(
                _token_pricing(item["cost_ceiling"], f"routes.{route_id}.cost_ceiling")
                if item.get("cost_ceiling") is not None
                else None
            ),
            use_provider_reported_cost=bool(
                item.get("use_provider_reported_cost", False)
            ),
            billing_multiplier=_decimal(
                item.get("billing_multiplier", 1),
                f"routes.{route_id}.billing_multiplier",
            ),
        )

    profiles: dict[str, ProfileSpec] = {}
    for profile_id, value in _mapping(root.get("profiles"), "profiles").items():
        item = _mapping(value, f"profiles.{profile_id}")
        profiles[profile_id] = ProfileSpec(
            id=profile_id,
            display_name=str(item["display_name"]),
            description=str(item["description"]),
            public_ready=bool(item.get("public_ready", False)),
            primary_route=str(item["primary_route"]),
            fallback_route=(str(item["fallback_route"]) if item.get("fallback_route") else None),
        )

    byok_defaults: dict[str, ByokDefault] = {}
    for provider, value in _mapping(root.get("byok_defaults"), "byok_defaults").items():
        item = _mapping(value, f"byok_defaults.{provider}")
        byok_defaults[provider] = ByokDefault(
            provider=provider,
            display_name=str(item["display_name"]),
            model=str(item["model"]),
            request_model=str(item["request_model"]),
        )

    catalog = ModelCatalog(
        version=int(root.get("version", 0)),
        updated=str(root.get("updated", "")),
        models=models,
        routes=routes,
        profiles=profiles,
        byok_defaults=byok_defaults,
    )
    _validate_catalog(catalog)
    return catalog


def _validate_catalog(catalog: ModelCatalog) -> None:
    if catalog.version < 1:
        raise RuntimeError("model catalog version must be positive")
    for route in catalog.routes.values():
        catalog.model_for_route(route)
        catalog.cost_ceiling_for_route(route)
        if route.adapter not in {
            "anthropic",
            "openai-compatible",
            "openai-responses",
        }:
            raise RuntimeError(f"route {route.id!r} has unsupported adapter {route.adapter!r}")
        if route.billing_multiplier < 1:
            raise RuntimeError(
                f"route {route.id!r} billing multiplier cannot be below one"
            )
        if route.use_provider_reported_cost and route.provider != "openrouter":
            raise RuntimeError(
                f"route {route.id!r} trusts provider cost outside OpenRouter"
            )
    for profile in catalog.profiles.values():
        if profile.primary_route not in catalog.routes:
            raise RuntimeError(
                f"profile {profile.id!r} references unknown primary route"
            )
        if profile.fallback_route and profile.fallback_route not in catalog.routes:
            raise RuntimeError(
                f"profile {profile.id!r} references unknown fallback route"
            )
    for default in catalog.byok_defaults.values():
        if default.model not in catalog.models:
            raise RuntimeError(
                f"BYOK provider {default.provider!r} references unknown model"
            )
        if not default.request_model.strip():
            raise RuntimeError(
                f"BYOK provider {default.provider!r} has an empty request model"
            )


def reset_model_catalog_cache() -> None:
    load_model_catalog.cache_clear()
