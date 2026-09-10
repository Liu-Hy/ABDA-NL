"""Launch the evaluator in a child that never receives backup credentials.

Usage: python -m app.evals.funded --route ROUTE [evaluation arguments]
Only funded-provider variables are copied from the private environment file.
No values or raw provider errors are printed by this launcher.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Mapping

from app.llm.catalog import ModelCatalog, load_model_catalog


# Supported by the funded adapters and their ADC loader. Provider prefixes are
# not an allowlist: GOOGLE_API_KEY, for example, is a separate personal API.
_FUNDED_VARIABLES = frozenset({
    "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_AUTH_TOKEN", "AZURE_OPENAI_ENDPOINT",
    "AZURE_ANTHROPIC_API_KEY", "AZURE_ANTHROPIC_ENDPOINT",
    "ANTHROPIC_FOUNDRY_API_KEY", "ANTHROPIC_FOUNDRY_AUTH_TOKEN",
    "ANTHROPIC_FOUNDRY_BASE_URL", "ANTHROPIC_FOUNDRY_RESOURCE",
    "ANTHROPIC_FOUNDRY_PROJECT_ENDPOINT",
    "GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_VERTEX_ACCESS_TOKEN",
    "GOOGLE_CLOUD_PROJECT", "GOOGLE_PROJECT_ID", "GOOGLE_CLOUD_LOCATION",
    "GOOGLE_CLOUD_QUOTA_PROJECT",
})
_PROVIDER_PREFIXES = (
    "AZURE_", "ANTHROPIC_", "GOOGLE_", "GCLOUD_", "GCP_", "VERTEX_",
    "OPENROUTER_", "OPENAI_", "GEMINI_", "CLAUDE_", "CODEX_",
    "DEEPSEEK_", "MOONSHOT_", "MOONSHOTAI_", "QWEN_", "ZAI_", "XAI_",
)


def funded_variable_names(catalog: ModelCatalog | None = None) -> frozenset[str]:
    """Include explicit deployment overrides from funded routes in the catalog."""
    active_catalog = catalog or load_model_catalog()
    overrides = {
        name
        for route in active_catalog.routes.values()
        if route.billing_source == "cloudbank" and route.provider in {"azure-foundry", "gcp-vertex"}
        for name in (route.model_env, route.endpoint_env, route.api_key_env)
        if name
    }
    return _FUNDED_VARIABLES | overrides


def funded_environment(
    source: Mapping[str, str | None], *, catalog: ModelCatalog | None = None,
) -> dict[str, str]:
    """Return only explicit funded settings from a private source."""
    allowed = funded_variable_names(catalog)
    return {
        name: value
        for name, value in source.items()
        if value and name in allowed and "OPENROUTER" not in name.upper()
    }


def funded_child_environment(
    inherited: Mapping[str, str], source: Mapping[str, str | None],
    *, catalog: ModelCatalog | None = None,
) -> dict[str, str]:
    """Preserve runtime settings while excluding inherited personal providers."""
    allowed = funded_variable_names(catalog)
    environment = {
        name: value for name, value in inherited.items()
        if "OPENROUTER" not in name.upper()
        and (name in allowed or not name.upper().startswith(_PROVIDER_PREFIXES))
    }
    for name, value in funded_environment(source, catalog=catalog).items():
        environment.setdefault(name, value)
    environment["ABDA_OPENROUTER_FAILOVER_ENABLED"] = "false"
    return environment


def main() -> None:
    from dotenv import dotenv_values

    root = Path(__file__).resolve().parents[2]
    environment = funded_child_environment(os.environ, dotenv_values(root / ".env"))
    # Avoid using the production accounts database for synthetic eval receipts.
    environment["ABDA_DATABASE_URL"] = "sqlite+pysqlite:///" + str(
        root / "artifacts" / "evals" / "usage.sqlite3"
    )
    environment["ABDA_ENVIRONMENT"] = "test"
    environment["ABDA_AUTH_MODE"] = "dev"
    environment["ABDA_AUTO_CREATE_DB"] = "1"
    (root / "artifacts" / "evals").mkdir(parents=True, exist_ok=True)
    # Replace this process with the fixed evaluator module, using argv and the
    # filtered environment directly. No shell interprets evaluation arguments.
    os.execve(  # noqa: S606
        sys.executable,
        [sys.executable, "-m", "app.evals.llm_eval", *sys.argv[1:]],
        environment,
    )


if __name__ == "__main__":
    main()
