"""Data-only source documents and glossary import, with no remote fetching."""

from __future__ import annotations

from copy import deepcopy
import json
import re
from urllib.parse import urlsplit

MAX_SOURCE_BYTES = 1_000_000
MAX_SOURCE_TEXT = 100_000
MAX_TOTAL_SOURCE_BYTES = 400_000
MAX_SOURCES = 10
FILENAME = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9_. -]{0,116}\.(?:txt|md|pdf)\Z")
LITERAL = re.compile(r"-?[A-Za-z_][A-Za-z0-9_]{0,99}\Z")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class MaterialError(ValueError):
    pass


def validate_sources(sources: list[dict], corpus: list[str] = ()) -> None:
    if len(sources) > MAX_SOURCES:
        raise MaterialError("Use at most 10 reference documents per scenario.")
    names = {name.casefold() for name in corpus}
    total = 0
    for item in sources:
        name, text = item["filename"], item["text"]
        if len(name) > 120 or not FILENAME.fullmatch(name):
            raise MaterialError("Use a simple .txt, .md, or .pdf source filename without paths.")
        if name.casefold() in names:
            raise MaterialError(
                "Each reference needs a distinct filename, including bundled sources."
            )
        names.add(name.casefold())
        if not text.strip() or len(text) > MAX_SOURCE_TEXT or _CONTROL.search(text):
            raise MaterialError(
                "Each reference must contain readable text of at most 100,000 characters."
            )
        total += len(text.encode("utf-8"))
        url = item.get("url", "")
        if url:
            try:
                parsed = urlsplit(url)
                valid = (
                    parsed.scheme == "https"
                    and parsed.hostname
                    and not parsed.username
                    and not parsed.password
                    and not any(c.isspace() for c in url)
                    and not _CONTROL.search(url)
                    and len(url) <= 2000
                )
            except ValueError:
                valid = False
            if not valid:
                raise MaterialError(
                    "A source link must be an HTTPS URL without embedded credentials."
                )
    if total > MAX_TOTAL_SOURCE_BYTES:
        raise MaterialError(
            "Reference text exceeds 400 KB in total. Use relevant excerpts or summaries."
        )


def parse_glossary(text: str) -> dict[str, str]:
    """Read the app's id = meaning glossary, or a flat YAML/JSON mapping."""
    from app.scenario.exchange import _ScenarioFileLoader
    import yaml

    if len(text.encode("utf-8")) > 200_000:
        raise MaterialError("The glossary is too large.")
    if not text.strip():
        return {}
    pairs = {}
    lines = [line.strip().removeprefix("#").strip() for line in text.splitlines()]
    meaningful = [line for line in lines if line and not line.startswith("Glossary")]
    if meaningful and all(re.match(r"-?[A-Za-z_]\w*\s*=", line) for line in meaningful):
        for line in meaningful:
            key, value = (part.strip() for part in line.split("=", 1))
            if value.startswith('"'):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError as exc:
                    raise MaterialError("Check the quoted glossary definition.") from exc
            if key in pairs:
                raise MaterialError("The glossary defines the same symbol more than once.")
            pairs[key] = value
    else:
        try:
            loader = _ScenarioFileLoader(text)
            try:
                pairs = loader.get_single_data()
            finally:
                loader.dispose()
        except (ValueError, yaml.YAMLError) as exc:
            raise MaterialError(
                "Use one symbol = definition per line, or a flat YAML/JSON glossary."
            ) from exc
    if not isinstance(pairs, dict) or len(pairs) > 1000:
        raise MaterialError("The glossary must map symbols to definitions.")
    for key, value in pairs.items():
        if (
            not isinstance(key, str)
            or not LITERAL.fullmatch(key)
            or not isinstance(value, str)
            or not value.strip()
            or len(value) > 2000
            or _CONTROL.search(value)
        ):
            raise MaterialError(
                "Use valid symbols and nonempty definitions of at most 2,000 characters."
            )
    return {key: value.strip() for key, value in pairs.items()}


def apply_glossary(raw: dict, definitions: dict[str, str]) -> dict:
    result = deepcopy(raw)
    statements = {
        key: value
        for section in ("facts", "assumptions", "propositions", "conclusions")
        for key, value in result.get(section, {}).items()
    }
    for literal, meaning in definitions.items():
        identifier = literal.removeprefix("-")
        target = statements.get(identifier)
        if target is None and literal.startswith("-"):
            target = result.get("rules", {}).get(identifier)
        if target is None:
            raise MaterialError("The glossary contains a symbol not declared by this scenario.")
        target["negated_description" if literal.startswith("-") else "description"] = meaning
    return result
