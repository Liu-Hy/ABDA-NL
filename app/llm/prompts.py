"""Prompt template loader.

Prompts live under `app/prompts/<name>.md` and use standard Python
`str.format`-style `{var}` placeholders. Literal braces in prompt
bodies should be doubled (`{{` / `}}`).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

PROMPTS_ROOT = Path(__file__).resolve().parent.parent / "prompts"


@lru_cache(maxsize=64)
def _read_template(name: str) -> str:
    path = PROMPTS_ROOT / f"{name}.md"
    if not path.is_file():
        raise FileNotFoundError(
            f"prompt template not found: {path} "
            f"(expected under {PROMPTS_ROOT})"
        )
    return path.read_text(encoding="utf-8")


def load_prompt(name: str, **variables: str) -> str:
    """Load `app/prompts/<name>.md` and substitute `{var}`
    placeholders."""
    template = _read_template(name)
    if not variables:
        return template
    return template.format(**variables)


def model_prompt_guidance(client: Any, feature: str) -> str:
    """Return only guidance justified by recorded failures for this model.

    Billing and retry wrappers can expose a deployment name in ``model``.
    Prefer the catalog identity carried by their inner metered client. A
    failed primary can instead expose its canonical identity directly.
    """
    pending = [client]
    visited: set[int] = set()
    names: list[str] = []
    while pending and len(visited) < 32:
        current = pending.pop()
        if current is None or id(current) in visited:
            continue
        visited.add(id(current))
        specification = getattr(current, "model_spec", None)
        identity = getattr(specification, "id", None)
        if isinstance(identity, str):
            names.insert(0, identity)
            break
        identity = getattr(current, "model", None)
        if isinstance(identity, str):
            names.append(identity)
        # Prefer the primary when a funded client also carries its backup.
        pending.extend(getattr(current, attr, None) for attr in ("fallback", "inner", "primary"))

    model = names[0] if names else ""
    templates: list[str] = []
    if feature == "chat" and model in {"claude-sonnet-5", "claude-opus-5"}:
        templates.append("chat_claude_argument_counts")
        if model == "claude-opus-5":
            templates.append("chat_opus_grounded_defeats")
    if feature == "chat" and model == "gpt-5.6-terra":
        templates.append("chat_terra_mutual_defeats")
    return "".join("\n\n" + load_prompt(name).strip() for name in templates)
