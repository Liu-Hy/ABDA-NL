"""Bounded, data-only YAML/JSON import for the browser scenario library."""
from __future__ import annotations

import yaml
from yaml.events import AliasEvent
from yaml.nodes import MappingNode

MAX_IMPORT_BYTES = 1_000_000
EXCHANGE_FORMAT = "abda-nl-scenario"


class ScenarioFileError(ValueError):
    pass


class _ScenarioFileLoader(yaml.SafeLoader):
    """Reject expansion, duplicate keys, and excessive nesting before construction."""

    def __init__(self, stream):
        super().__init__(stream)
        self._depth = 0
        self._nodes = 0

    def compose_node(self, parent, index):
        if self.check_event(AliasEvent):
            raise ScenarioFileError("YAML aliases are not supported. Write each value explicitly.")
        self._depth += 1
        self._nodes += 1
        try:
            if self._depth > 24 or self._nodes > 40_000:
                raise ScenarioFileError("This file is too deeply nested or contains too many entries.")
            return super().compose_node(parent, index)
        finally:
            self._depth -= 1

    def construct_mapping(self, node, deep=False):
        if not isinstance(node, MappingNode):
            raise ScenarioFileError("Expected an object with named fields.")
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise ScenarioFileError("Field names and identifiers must be text, not numbers or lists.")
            if key in result:
                raise ScenarioFileError(
                    f"Duplicate field at line {key_node.start_mark.line + 1}. Keep only one definition."
                )
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def parse_scenario_file(text: str) -> tuple[dict, str | None, list[str]]:
    """Return scenario data and safe provenance, without reading any source files.

    Version 3 exports contain actual reference text and no source dependency.
    Legacy exports may retain a bundled example identifier. Standalone YAML
    can name a local corpus, which must be attached separately during import.
    The project validator separately proves schema, references, source corpus
    integrity, and deterministic analyzability before preview or persistence.
    """
    if len(text.encode("utf-8")) > MAX_IMPORT_BYTES:
        raise ScenarioFileError("Choose a scenario file smaller than 1 MB.")
    try:
        loader = _ScenarioFileLoader(text.lstrip("\ufeff"))
        try:
            raw = loader.get_single_data()
        finally:
            loader.dispose()
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        location = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
        raise ScenarioFileError(
            f"Cannot read this YAML or JSON file{location}. Check its syntax and indentation."
        ) from exc
    if not isinstance(raw, dict):
        raise ScenarioFileError("Choose a scenario YAML or JSON file, not a document, list, or empty file.")
    source_id = None
    version = None
    if "format" in raw:
        if raw.get("format") != EXCHANGE_FORMAT or type(raw.get("version")) is not int or raw["version"] not in {1, 2, 3}:
            raise ScenarioFileError("This scenario export format or version is not supported.")
        if set(raw) - {"format", "version", "scenario", "source_scenario_id"}:
            raise ScenarioFileError("This export contains unexpected fields. Download a new scenario file.")
        source_id = raw.get("source_scenario_id")
        version = raw["version"]
        if source_id is not None and (not isinstance(source_id, str) or not 1 <= len(source_id) <= 100):
            raise ScenarioFileError("The source example identifier is invalid.")
        raw = raw.get("scenario")
        if not isinstance(raw, dict):
            raise ScenarioFileError("The export does not contain a scenario object.")
    warnings = []
    if version == 3:
        if source_id is not None or raw.get("corpus"):
            raise ScenarioFileError("A portable version 3 file must embed its references, not depend on a source server.")
    if source_id is None and raw.get("corpus"):
        raw = dict(raw, corpus=[])
        warnings.append(
            "Local source-document references were left out. Facts and rules are imported, "
            "but attached documents are not uploaded or read."
        )
    return raw, source_id, warnings
