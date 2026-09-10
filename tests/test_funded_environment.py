"""Synthetic evaluator environments preserve funded ADC and exclude personal APIs."""
from dataclasses import replace

import pytest

from app.evals.funded import funded_child_environment, funded_environment
from app.llm.catalog import load_model_catalog


@pytest.mark.parametrize("name", [
    "GOOGLE_API_KEY", "GOOGLE_GEMINI_API_KEY", "GOOGLE_GENAI_USE_VERTEXAI",
    "OPENAI_API_KEY", "OPENAI_BASE_URL", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL", "ANTHROPIC_CUSTOM_HEADERS", "ANTHROPIC_PROFILE",
    "OPENROUTER_API_KEY", "ABDA_OPENROUTER_API_KEY", "GEMINI_API_KEY",
    "CLAUDE_CODE_OAUTH_TOKEN", "CODEX_API_KEY", "DEEPSEEK_API_KEY", "MOONSHOT_API_KEY",
    "QWEN_API_KEY", "ZAI_API_KEY", "XAI_API_KEY", "AZURE_UNSUPPORTED_PRIVATE_KEY",
    "GOOGLE_VERTEX_PROJECT", "GCP_UNSUPPORTED_KEY", "VERTEX_UNSUPPORTED_KEY",
])
def test_personal_or_unused_provider_variables_are_removed_from_both_sources(name):
    assert name not in funded_environment({name: "private-source-value"})
    child = funded_child_environment({name: "inherited-value"}, {name: "source-value"})
    assert name not in child
    assert child["ABDA_OPENROUTER_FAILOVER_ENABLED"] == "false"


def test_funded_adc_quota_and_catalog_overrides_are_preserved_with_runtime_precedence():
    source = {
        "GOOGLE_APPLICATION_CREDENTIALS": "/private/funded-adc.json",
        "GOOGLE_CLOUD_PROJECT": "funded-project",
        "GOOGLE_CLOUD_QUOTA_PROJECT": "funded-project",
        "GOOGLE_CLOUD_LOCATION": "global",
        "GOOGLE_VERTEX_ACCESS_TOKEN": "source-token",
        "AZURE_OPENAI_API_KEY": "source-funded-key",
        "AZURE_OPUS5_API_KEY": "source-fund-key-opus",
        "AZURE_OPUS5_ENDPOINT": "https://opus.services.ai.azure.com",
        "AZURE_OPENAI_GPT_5_4_MINI_DEPLOYMENT": "funded-candidate-deployment",
    }
    runtime = {
        "PATH": "/usr/bin", "HOME": "/private/home", "VIRTUAL_ENV": "/private/venv",
        "SLURM_JOB_ID": "synthetic-job", "SLURM_TMPDIR": "/temporary/job",
        "CLOUDSDK_CONFIG": "/private/funded-cloudsdk",
        "ABDA_EVAL_BUDGET_PATH": "/private/original-budget.sqlite3",
        "GOOGLE_VERTEX_ACCESS_TOKEN": "refreshed-token",
        "AZURE_OPENAI_API_KEY": "inherited-funded-key",
        "ABDA_OPENROUTER_FAILOVER_ENABLED": "true",
    }
    child = funded_child_environment(runtime, source)
    assert all(child[name] == value for name, value in source.items() if name not in runtime)
    assert all(child[name] == value for name, value in runtime.items()
               if name != "ABDA_OPENROUTER_FAILOVER_ENABLED")
    assert child["ABDA_OPENROUTER_FAILOVER_ENABLED"] == "false"
    assert source["GOOGLE_VERTEX_ACCESS_TOKEN"] == "source-token"
    assert runtime["ABDA_OPENROUTER_FAILOVER_ENABLED"] == "true"


def test_new_funded_route_override_is_explicitly_admitted_without_a_provider_prefix():
    catalog = load_model_catalog()
    route = replace(catalog.routes["cloudbank-claude-opus-5"],
        model_env="FUNDED_DEPLOYMENT_ID", endpoint_env="FUNDED_RESOURCE_URL", api_key_env="FUNDED_RESOURCE_KEY")
    catalog = replace(catalog, routes={**catalog.routes, route.id: route})
    values = {"FUNDED_DEPLOYMENT_ID": "deployment", "FUNDED_RESOURCE_URL": "https://test.services.ai.azure.com",
              "FUNDED_RESOURCE_KEY": "funded-secret", "AZURE_UNKNOWN_KEY": "unrelated-secret"}
    copied = funded_environment(values, catalog=catalog)
    assert set(copied) == {"FUNDED_DEPLOYMENT_ID", "FUNDED_RESOURCE_URL", "FUNDED_RESOURCE_KEY"}


def test_private_file_does_not_override_database_runtime_or_budget_settings():
    child = funded_child_environment({"ABDA_EVAL_BUDGET_PATH": "/original/ledger.sqlite3"}, {
        "ABDA_DATABASE_URL": "production-database",
        "ABDA_EVAL_BUDGET_PATH": "/different/ledger.sqlite3",
        "PATH": "/untrusted/bin",
    })
    assert child == {"ABDA_EVAL_BUDGET_PATH": "/original/ledger.sqlite3", "ABDA_OPENROUTER_FAILOVER_ENABLED": "false"}
