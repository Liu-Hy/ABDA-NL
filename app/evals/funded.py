"""Launch the evaluator in a child that never receives backup credentials.

Usage: python -m app.evals.funded --route ROUTE [evaluation arguments]
Only funded-provider variables are copied from the private environment file.
No values or raw provider errors are printed by this launcher.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def funded_environment(source: dict[str, str | None]) -> dict[str, str]:
    """Return only the funded provider settings from a private source."""
    prefixes = ("AZURE_", "ANTHROPIC_FOUNDRY_", "GOOGLE_", "GCP_", "VERTEX_")
    return {
        name: value
        for name, value in source.items()
        if value and name.startswith(prefixes) and "OPENROUTER" not in name
    }


def main() -> None:
    from dotenv import dotenv_values

    root = Path(__file__).resolve().parents[2]
    environment = {
        name: value
        for name, value in os.environ.items()
        if not (
            "OPENROUTER" in name.upper()
            or name in {"ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"}
        )
    }
    values = funded_environment(dict(dotenv_values(root / ".env")))
    for name, value in values.items():
        environment.setdefault(name, value)
    environment["ABDA_OPENROUTER_FAILOVER_ENABLED"] = "false"
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
