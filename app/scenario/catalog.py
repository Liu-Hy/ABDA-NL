"""Read-only access to the immutable scenarios bundled with the demo."""
from __future__ import annotations

import re
from pathlib import Path

from app.scenario.loader import load_scenario
from app.scenario.model import Scenario


EXAMPLES_ROOT = Path(__file__).resolve().parents[2] / "examples"
_SCENARIO_ID = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ScenarioNotFoundError(LookupError):
    """A bundled scenario identifier did not resolve to a scenario file."""


def bundled_scenario_directory(scenario_id: str) -> Path:
    if not _SCENARIO_ID.fullmatch(scenario_id):
        raise ScenarioNotFoundError(f"scenario not found: {scenario_id!r}")
    return EXAMPLES_ROOT / scenario_id


def load_bundled_scenario(scenario_id: str) -> Scenario:
    scenario_path = bundled_scenario_directory(scenario_id) / "scenario.yaml"
    if not scenario_path.is_file():
        raise ScenarioNotFoundError(f"scenario not found: {scenario_id!r}")
    return load_scenario(scenario_path)
