"""Test-only catalog fixtures, never evidence for a live model's qualification."""
from dataclasses import replace

from app.llm.catalog import ModelCatalog, _validate_catalog


def admit_catalog_models(catalog: ModelCatalog, *model_ids: str) -> ModelCatalog:
    """Admit explicit existing candidate routes for isolated adapter tests."""
    selected = set(model_ids)
    profiles = {
        key: replace(profile, public_ready=True)
        if catalog.routes[profile.primary_route].model in selected else profile
        for key, profile in catalog.profiles.items()
    }
    admitted = {catalog.routes[profile.primary_route].model for profile in profiles.values()
                if profile.public_ready}
    assert selected <= admitted, "test models must have candidate profiles"
    admitted_routes = {
        route_id for profile in profiles.values() if profile.public_ready
        for route_id in (profile.primary_route, profile.fallback_route) if route_id
    }
    routes = {key: replace(route, metadata_confirmed=True, configuration_confirmed=True,
                           funded_feature_qualified=route.billing_source == "cloudbank",
                           live_inference_verified=route.billing_source == "cloudbank")
              if key in admitted_routes else route
              for key, route in catalog.routes.items()}
    result = replace(catalog, profiles=profiles, routes=routes)
    _validate_catalog(result)
    return result
