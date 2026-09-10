"""Reproducible application evidence and explicit model-by-feature coverage."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.llm.client import close_llm_client


ROOT = Path(__file__).resolve().parents[2]
REQUIRED_FEATURES = (
    "grounded_chat", "item_questions", "corpus_questions", "sensitivity",
    "add_rule", "modify_rule", "add_fact", "add_assumption", "refinement",
    "semantic_review", "authoring_context",
)
REQUIRED_CASE_TYPES = ("routine", "ambiguous", "adversarial", "edge")


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


def implementation_fingerprint() -> dict[str, Any]:
    """Include uncommitted code, prompts, catalogs, suites, and scenario data."""
    paths = [
        path for directory in ("app/llm", "app/evals", "app/scenario", "app/prompts", "app/schemas", "evals", "examples")
        for path in (ROOT / directory).rglob("*")
        if path.is_file() and path.suffix in {".py", ".md", ".yaml", ".json", ".txt", ".pdf"}
    ]
    files = {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(paths)
    }
    return {"sha256": digest(files), "files": files}


def _safe_response_diagnostics(value: Any) -> dict[str, Any]:
    """Keep synthetic returned answers and parsing metadata, never transports."""
    if not isinstance(value, dict):
        return {}
    result: dict[str, Any] = {}
    for key in ("finish_reason", "actual_model", "visible_content"):
        if isinstance(value.get(key), str):
            result[key] = value[key]
    for key in ("requested_max_tokens", "reasoning_tokens"):
        if type(value.get(key)) is int and value[key] >= 0:
            result[key] = value[key]
    usage = value.get("usage")
    if isinstance(usage, dict):
        result["usage"] = {
            key: usage[key] for key in (
                "input_tokens", "output_tokens", "cache_read_input_tokens",
                "cache_creation_input_tokens",
            ) if type(usage.get(key)) is int and usage[key] >= 0
        }
    calls = value.get("tool_calls")
    if isinstance(calls, list):
        result["tool_calls"] = []
        for call in calls:
            function = call.get("function") if isinstance(call, dict) else None
            if not isinstance(function, dict):
                continue
            kept = {"name": function["name"]} if isinstance(function.get("name"), str) else {}
            if "arguments" in function:
                try:
                    # Arguments are generated application content, including a
                    # malformed JSON value that explains a parser rejection.
                    kept["arguments"] = json.loads(json.dumps(function["arguments"], allow_nan=False))
                except (TypeError, ValueError):
                    pass
            if kept:
                result["tool_calls"].append({"function": kept})
    return result


class RecordingClient:
    """Capture the actual requests and every draft before application validation.

    Requests contain only synthetic suite scenarios and feature prompts. Auth
    headers, keys, endpoints, exception strings, and client objects are excluded.
    The router usage audit separately records physical transport retries.
    """

    def __init__(self, inner, *, pacer=None, request_timeout_seconds: float | None = None) -> None:
        self.inner = inner
        self.pacer = pacer
        self.pacing_seconds = 0.0
        self.request_deadline = time.monotonic() + request_timeout_seconds if request_timeout_seconds is not None else None
        self.calls: list[dict[str, Any]] = []
        self.configuration: dict[str, Any] = {}
        current, seen = inner, set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            for name in ("model", "provider", "route", "billing_source", "reasoning_effort", "thinking_level", "thinking_budget"):
                value = getattr(current, name, None)
                if isinstance(value, (str, int, float, bool)) or value is None:
                    if value is not None:
                        self.configuration[name] = value
            current = getattr(current, "inner", None)
        self._propagate_deadline()

    @property
    def settled_cost_microusd(self) -> int | None:
        return getattr(self.inner, "settled_cost_microusd", None)

    @property
    def settled_billing_uncertain_count(self) -> int:
        return getattr(self.inner, "settled_billing_uncertain_count", 0)

    def _propagate_deadline(self) -> None:
        if self.request_deadline is None:
            return
        current, seen = self.inner, set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            for name in ("deadline", "request_deadline"):
                if hasattr(current, name):
                    setattr(current, name, self.request_deadline)
            current = getattr(current, "inner", None)

    def _invoke(self, method: str, **kwargs):
        entry: dict[str, Any] = {
            "method": method,
            "request": kwargs,
            "request_sha256": digest(kwargs),
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        self.calls.append(entry)
        try:
            if self.pacer is not None:
                pacing_started = time.monotonic()
                entry["pacing"] = self.pacer.before_call(kwargs)
                elapsed = time.monotonic() - pacing_started
                entry["pacing"]["elapsed_seconds"] = elapsed
                self.pacing_seconds += elapsed
                if self.request_deadline is not None:
                    self.request_deadline += elapsed
                    self._propagate_deadline()
                entry["provider_invoked_at"] = datetime.now(timezone.utc).isoformat()
            result = getattr(self.inner, method)(**kwargs)
        except BaseException as exc:
            entry["error_type"] = type(exc).__name__
            diagnostics = _safe_response_diagnostics(getattr(exc, "diagnostics", None))
            if diagnostics:
                entry["error_diagnostics"] = diagnostics
                entry["diagnostics_sha256"] = digest(diagnostics)
            raise
        else:
            entry["response"] = asdict(result) if is_dataclass(result) else {
                name: getattr(result, name, None)
                for name in ("text", "tool_input", "tool_name", "usage", "stop_reason", "model", "provider", "route")
            }
            entry["response_sha256"] = digest(entry["response"])
            return result
        finally:
            entry["finished_at"] = datetime.now(timezone.utc).isoformat()

    def complete(self, **kwargs):
        return self._invoke("complete", **kwargs)

    def tool_call(self, **kwargs):
        return self._invoke("tool_call", **kwargs)

    def close(self) -> None:
        close_llm_client(self.inner)


def coverage_matrix(
    suite: dict[str, Any], results: list[dict[str, Any]], route_ids: list[str],
    *, repetitions: int, configurations: dict[str, Any] | None = None,
) -> dict[str, Any]:
    case_definitions = {str(case["id"]): case for case in suite["cases"]}
    required_features = tuple(suite.get("required_features") or REQUIRED_FEATURES)
    required_types = set(suite.get("required_case_types") or REQUIRED_CASE_TYPES)
    matrix: dict[str, Any] = {}
    for route_id in route_ids:
        feature_rows: dict[str, Any] = {}
        for feature in required_features:
            expected = {
                case_id: case for case_id, case in case_definitions.items()
                if feature in case.get("features", [])
            }
            observations = [
                result for result in results
                if result["route_id"] == route_id and result["case_id"] in expected
            ]
            covered_types = {
                str(expected[result["case_id"]].get("case_type"))
                for result in observations if not result.get("skipped") and result.get("error") is None
            }
            covered_cases = {
                case_id: len({int(result["repetition"]) for result in observations
                              if result["case_id"] == case_id and not result.get("skipped")})
                for case_id in expected
            }
            complete = bool(expected) and required_types.issubset(covered_types) and all(
                count >= repetitions for count in covered_cases.values()
            )
            automatic_pass = complete and all(result.get("passed") for result in observations)
            reviewed = bool(observations) and all(
                result.get("semantic_review", {}).get("approved") is True for result in observations
            )
            feature_rows[feature] = {
                "configuration": (configurations or {}).get(route_id, {}),
                "expected_cases": sorted(expected),
                "case_repetitions": covered_cases,
                "required_repetitions": repetitions,
                "case_types_covered": sorted(covered_types),
                "case_types_missing": sorted(required_types - covered_types),
                "complete": complete,
                "automated_pass": automatic_pass,
                "answers_reviewed": reviewed,
                "accepted": automatic_pass and reviewed,
            }
        matrix[route_id] = feature_rows
    return matrix


def apply_semantic_reviews(report: dict[str, Any], reviews: dict[str, Any]) -> dict[str, Any]:
    """Attach an identified review to exact recorded results, never to a model name.

    The report keeps automated checks and answer inspection distinct. A reviewer
    must read the actual answers/operations and explicitly assess grounding,
    semantic fidelity, usefulness, and presentation. No keyword-based or paid
    judge-model shortcut silently turns a pending review into acceptance.
    """
    reviewer = str(reviews.get("reviewer") or "").strip()
    if not reviewer:
        raise ValueError("semantic reviews must identify their reviewer")
    annotations = reviews.get("results", {})
    if not isinstance(annotations, dict):
        raise ValueError("semantic review results must be a mapping")
    requirements = ("grounding", "semantic_fidelity", "usefulness", "presentation")
    for result in report["results"]:
        key = f"{result['route_id']}:{result['case_id']}:{result['repetition']}"
        annotation = annotations.get(key)
        if annotation is None:
            continue
        if annotation.get("response_sha256") != result.get("evidence_sha256"):
            raise ValueError(f"semantic review evidence does not match {key}")
        if not str(annotation.get("notes") or "").strip():
            raise ValueError(f"semantic review needs concrete evidence notes for {key}")
        if any(type(annotation.get(name)) is not bool for name in requirements):
            raise ValueError(f"semantic review must assess all criteria for {key}")
        result["semantic_review"] = {
            **annotation, "reviewer": reviewer,
            "approved": all(annotation[name] for name in requirements),
        }
    report["coverage_matrix"] = coverage_matrix(
        report["suite_definition"], report["results"], report["routes"], repetitions=report["repetitions"],
        configurations=report.get("model_evidence", {}),
    )
    report["application_accepted"] = bool(report["coverage_matrix"]) and all(
        cell["accepted"] for row in report["coverage_matrix"].values() for cell in row.values()
    ) and report.get("implementation_unchanged", False)
    report["gate_passed"] = report["application_accepted"] and report.get("automated_gate_passed", False)
    return report
