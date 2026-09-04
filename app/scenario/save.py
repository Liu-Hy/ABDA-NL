"""Save a diff-applied scenario to examples/<id>/.

Writes to a temporary directory first, verifies the result loads and builds
cleanly, then installs it with a recoverable directory exchange. Saves are
serialized within one server process. A later save restores the previous target
if the process stopped during an overwrite exchange.
"""
from __future__ import annotations

import re
import shutil
import threading
from pathlib import Path

import yaml

from app.abda_bridge import ArgumentationGraph, build_arguments, build_attacks
from app.scenario.loader import load_scenario, scenario_to_rule_collection
from app.scenario.model import Scenario
from app.scenario.serialize import scenario_to_dict

# Mirrors the scenario-schema `identifier` pattern. No max-length cap --
# directory names can be longer than scenario-internal ids, which are kept
# compact for labels on rules/facts/conclusions.
ID_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SAVE_LOCK = threading.RLock()

# scenario.yaml is always replaced by the diff-applied version; the copy
# exclusion for expected_labels.yaml is conditional on whether the save is
# a fresh as-new-scenario (exclude, regression snapshot belongs only to
# the baseline) or an overwrite of the source itself (preserve, the user
# is updating in place). Resolved inside save_scenario.


class SaveError(Exception):
    """Base class for save-flow failures."""


class InvalidScenarioId(SaveError):
    """save_as_id fails the identifier pattern."""


class ScenarioIdCollision(SaveError):
    """Target directory exists and overwrite was not requested."""


class SaveVerificationFailed(SaveError):
    """Post-write rebuild failed; the just-written scenario is inconsistent."""


def _internal_directory(path: Path, label: str) -> None:
    if path.is_symlink() or not path.is_dir():
        raise SaveVerificationFailed(f"refusing to replace an unexpected {label} path")


def _recover_interrupted_swap(
    *,
    target_dir: Path,
    temp_dir: Path,
    backup_dir: Path,
) -> None:
    if backup_dir.exists() or backup_dir.is_symlink():
        _internal_directory(backup_dir, "save backup")
        if target_dir.exists() or target_dir.is_symlink():
            _internal_directory(target_dir, "scenario target")
            shutil.rmtree(backup_dir)
        else:
            backup_dir.rename(target_dir)
    if temp_dir.exists() or temp_dir.is_symlink():
        _internal_directory(temp_dir, "save temporary")
        shutil.rmtree(temp_dir)


def _install_verified_directory(
    *,
    target_dir: Path,
    temp_dir: Path,
    backup_dir: Path,
) -> None:
    if not target_dir.exists():
        try:
            temp_dir.rename(target_dir)
        except OSError as exc:
            raise SaveVerificationFailed(
                "the verified scenario could not be installed"
            ) from exc
        return

    _internal_directory(target_dir, "scenario target")
    try:
        target_dir.rename(backup_dir)
    except OSError as exc:
        raise SaveVerificationFailed(
            "the existing scenario could not be prepared for a safe overwrite"
        ) from exc
    try:
        temp_dir.rename(target_dir)
    except BaseException as install_error:
        try:
            backup_dir.rename(target_dir)
        except BaseException as restore_error:
            raise SaveVerificationFailed(
                "verified scenario installation failed and the previous scenario "
                f"must be recovered from {backup_dir.name}"
            ) from restore_error
        if isinstance(install_error, Exception):
            raise SaveVerificationFailed(
                "verified scenario installation failed; the original scenario was restored"
            ) from install_error
        raise
    shutil.rmtree(backup_dir, ignore_errors=True)


def _save_scenario_locked(
    *,
    effective: Scenario,
    title: str,
    save_as_id: str,
    baseline_dir: Path,
    examples_root: Path,
    overwrite: bool = False,
) -> Path:
    """Write `effective` as a new scenario under
    `examples_root/save_as_id/`.

    `baseline_dir` is the scenario directory to copy non-YAML
    artefacts from (corpus files, corpus_summary.yaml if
    present). `title` overrides the Scenario's `title` field in the
    written YAML.

    Returns the target Path on success.

    Raises:
      InvalidScenarioId -- save_as_id fails the identifier pattern.
      ScenarioIdCollision -- target exists and `overwrite` is False.
      SaveVerificationFailed -- written YAML fails to load/build.
    """
    if not ID_PATTERN.fullmatch(save_as_id):
        raise InvalidScenarioId(
            f"save_as_id {save_as_id!r} must match [A-Za-z_][A-Za-z0-9_]*"
        )
    if not title.strip():
        raise InvalidScenarioId("title must be non-empty")

    target_dir = examples_root / save_as_id
    temp_dir = examples_root / f".tmp_save_{save_as_id}"
    backup_dir = examples_root / f".backup_save_{save_as_id}"
    _recover_interrupted_swap(
        target_dir=target_dir,
        temp_dir=temp_dir,
        backup_dir=backup_dir,
    )
    is_source_overwrite = baseline_dir.resolve() == target_dir.resolve()
    if target_dir.exists() and not overwrite:
        raise ScenarioIdCollision(
            f"scenario id {save_as_id!r} already exists"
        )

    temp_dir.mkdir(parents=True)

    # Overwriting the source scenario preserves expected_labels.yaml;
    # save-as-new excludes it (belongs to the baseline only).
    skip_names = {"scenario.yaml"}
    if not is_source_overwrite:
        skip_names.add("expected_labels.yaml")

    try:
        # 1. Copy baseline artifacts except skipped names.
        if baseline_dir.is_dir():
            for child in baseline_dir.iterdir():
                if child.name in skip_names:
                    continue
                dest = temp_dir / child.name
                if child.is_dir():
                    shutil.copytree(child, dest)
                else:
                    shutil.copy2(child, dest)

        # 2. Write the diff-applied scenario with the title override.
        #    Don't mutate effective.title -- the caller may still need
        #    the object. Patch the serialized dict instead.
        scenario_dict = scenario_to_dict(effective)
        scenario_dict["title"] = title
        with (temp_dir / "scenario.yaml").open("w") as f:
            yaml.safe_dump(
                scenario_dict,
                f,
                sort_keys=False,
                default_flow_style=False,
                allow_unicode=True,
            )

        # 3. Verify: round-trip load + AF build + grounded labelling.
        #    Matches what _compute_state_bundle will do on the next
        #    request; catches anything the diff pipeline might have
        #    missed (schema drift, orphaned refs, labelling-time
        #    consistency errors).
        try:
            check = load_scenario(temp_dir / "scenario.yaml")
            rc = scenario_to_rule_collection(check)
            arguments = build_arguments(rc.get_all_rules())
            attacks = build_attacks(arguments)
            ArgumentationGraph(arguments, attacks).get_grounded_labelling()
        except Exception as exc:
            raise SaveVerificationFailed(
                f"saved scenario failed post-write verification: {exc}"
            ) from exc

        # 4. Install the verified directory. An overwrite first moves the
        #    previous target to a private backup and restores it if installing
        #    the replacement fails.
        _install_verified_directory(
            target_dir=target_dir,
            temp_dir=temp_dir,
            backup_dir=backup_dir,
        )
        return target_dir

    except BaseException:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def save_scenario(
    *,
    effective: Scenario,
    title: str,
    save_as_id: str,
    baseline_dir: Path,
    examples_root: Path,
    overwrite: bool = False,
) -> Path:
    """Safely serialize one local scenario save within this server process."""
    with _SAVE_LOCK:
        return _save_scenario_locked(
            effective=effective,
            title=title,
            save_as_id=save_as_id,
            baseline_dir=baseline_dir,
            examples_root=examples_root,
            overwrite=overwrite,
        )
