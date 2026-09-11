"""Run the versioned ABDA model suite against isolated provider routes."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import time
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4

import yaml
from sqlalchemy import select

from app.core.config import get_settings, reset_settings_cache
from app.db.models import LLMUsageEvent
from app.db.session import initialize_database
from app.evals.budget import MAX_CLOUDBANK_EVALUATION_MICROUSD, PersistentSpendCap
from app.evals.evidence import RecordingClient, coverage_matrix, digest, implementation_fingerprint
from app.evals.isolation import assert_no_openrouter_credentials, funded_network_only
from app.evals.pacing import DeploymentRate, EvaluationPacer, parse_rate_limits
from app.llm.catalog import load_model_catalog, reset_model_catalog_cache
from app.llm.chat_service import MAX_TOKENS_PER_RESPONSE, run_turn
from app.llm.client import close_llm_client
from app.llm.edit_service import MAX_TOKENS_PER_PROPOSE, MAX_TOKENS_PER_REVIEW, ProposerRetryExhausted, run_propose, run_review
from app.llm.routing import CallContext, LLMRouter
from app.llm.corpus import _read_corpus_file
from app.scenario.catalog import EXAMPLES_ROOT, load_bundled_scenario
from app.scenario.diff_ops import apply as apply_ops
from app.scenario.loader import scenario_from_dict
from app.scenario.serialize import scenario_to_dict
from app.scenario.state import compute_state_bundle


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SUITE = REPOSITORY_ROOT / "evals" / "llm_suite.yaml"
DEFAULT_PAID_RUN_CAP_MICROUSD = MAX_CLOUDBANK_EVALUATION_MICROUSD
CASE_REQUEST_SECONDS = 180.0


class EvaluationConfigurationError(RuntimeError):
    pass


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvaluationConfigurationError(f"{name} must be a mapping")
    return value


def load_suite(path: Path) -> tuple[dict[str, Any], str]:
    data = path.read_bytes()
    parsed = yaml.safe_load(data)
    suite = _mapping(parsed, "evaluation suite")
    if int(suite.get("version", 0)) < 1:
        raise EvaluationConfigurationError("evaluation suite version must be positive")
    cases = suite.get("cases")
    if not isinstance(cases, list) or not cases:
        raise EvaluationConfigurationError("evaluation suite must contain cases")
    seen: set[str] = set()
    for index, raw_case in enumerate(cases):
        case = _mapping(raw_case, f"cases[{index}]")
        case_id = str(case.get("id") or "")
        if not case_id or case_id in seen:
            raise EvaluationConfigurationError("evaluation case ids must be unique")
        seen.add(case_id)
        if case.get("kind") not in {"chat", "propose", "review"}:
            raise EvaluationConfigurationError(
                f"case {case_id!r} has an unsupported kind"
            )
        if not isinstance(case.get("scenario_id"), str):
            raise EvaluationConfigurationError(
                f"case {case_id!r} must identify a scenario"
            )
        if suite.get("requires_answer_review"):
            if not case.get("features") or case.get("case_type") not in suite.get("required_case_types", []):
                raise EvaluationConfigurationError(f"case {case_id!r} needs feature and case-type coverage metadata")
            if case["kind"] == "propose" and not case.get("expected"):
                raise EvaluationConfigurationError(f"case {case_id!r} needs concrete proposal expectations")
    for feature in suite.get("required_features") or []:
        covered = {case["case_type"] for case in cases if feature in case.get("features", [])}
        missing = set(suite.get("required_case_types") or []) - covered
        if missing:
            raise EvaluationConfigurationError(f"feature {feature!r} lacks case types: {', '.join(sorted(missing))}")
    missing_scenarios = set(suite.get("required_scenarios") or []) - {case["scenario_id"] for case in cases}
    if missing_scenarios:
        raise EvaluationConfigurationError("suite lacks bundled scenarios: " + ", ".join(sorted(missing_scenarios)))
    return suite, hashlib.sha256(data).hexdigest()


def _scenario_for_case(case: dict[str, Any]):
    scenario_id = str(case["scenario_id"])
    if "scenario" in case:
        baseline = scenario_from_dict(deepcopy(_mapping(case["scenario"], "scenario")))
        scenario_dir = None
    else:
        baseline = load_bundled_scenario(scenario_id)
        scenario_dir = EXAMPLES_ROOT / scenario_id
    if case.get("scenario_overrides"):
        raw = scenario_to_dict(baseline)
        for name, value in _mapping(case["scenario_overrides"], "scenario_overrides").items():
            raw[name] = deepcopy(value)
        baseline = scenario_from_dict(raw)
    operations = case.get("diff_ops") or []
    if not isinstance(operations, list):
        raise EvaluationConfigurationError(
            f"case {case['id']!r} diff_ops must be a list"
        )
    scenario = apply_ops(baseline, operations)
    bundle = compute_state_bundle(scenario)
    for literal, expected in _mapping(case.get("engine_expectations") or {}, "engine_expectations").items():
        if bundle["af"]["labels_by_proposition"].get(literal) != expected:
            raise EvaluationConfigurationError(f"case {case['id']!r} has an invalid deterministic expectation for {literal!r}")
    return scenario, bundle, operations, scenario_dir


def _normalize_quote(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _chat_semantic_checks(case, text, scenario, bundle, scenario_dir) -> dict[str, bool]:
    """Check inspectable semantic facts without substituting keyword scores for review."""
    checks: dict[str, bool] = {}
    lower = text.casefold()
    references = case.get("context_refs") or []
    selected_literal = None
    if len(references) == 1 and not case.get("argument_rules"):
        reference = references[0]
        if reference.get("kind") in {"conclusion", "proposition", "fact", "assumption"}:
            selected_literal = reference.get("id")
    direct_answer = re.match(
        r"\s*it(?:['’]s|\s+is)\s+(?:currently\s+)?"
        r"(accepted|rejected|undecided|absent)(?:\s*[.!?](?=\s|$)|\s*$)",
        lower,
    )
    if case.get("forbidden_claims"):
        checks["forbidden_claims_absent"] = not any(str(value).casefold() in lower for value in case["forbidden_claims"])
    for number, assertion in enumerate(case.get("label_assertions") or []):
        literal, expected = assertion["literal"], assertion["label"]
        if bundle["af"]["labels_by_proposition"].get(literal) != expected:
            raise EvaluationConfigurationError(f"case {case['id']} label assertion disagrees with the engine")
        clauses = re.split(r"[.!?;\n]+", lower)
        relevant = [clause for clause in clauses if any(str(phrase).casefold() in clause for phrase in assertion["phrases"])]
        observed = []
        for clause in relevant:
            mentions = [match for phrase in assertion["phrases"] for match in re.finditer(re.escape(str(phrase).casefold()), clause)]
            labels = list(re.finditer(r"\b(?:accept(?:ed|s)?|reject(?:ed|s)?|undecided|absent)\b", clause))
            for mention in mentions:
                if labels:
                    label = min(labels, key=lambda value: min(abs(value.start() - mention.end()), abs(mention.start() - value.end())))
                    value = label.group()
                    if value.startswith("accept"):
                        value = "accepted"
                    elif value.startswith("reject"):
                        value = "rejected"
                    negated = bool(re.search(
                        r"\b(?:not|never|doesn't|isn't|aren't|cannot|can't)\s+(?:currently\s+)?$",
                        clause[max(0, label.start() - 30):label.start()],
                    ))
                    observed.append(value if not negated else "not " + value)
        # A direct first-sentence answer can refer to the single selected item.
        # It cannot override an explicit label claim or resolve multiple items.
        if not observed and literal == selected_literal and direct_answer:
            observed.append(direct_answer.group(1))
        checks[f"label_{number}_{literal}"] = expected in observed
    required_sources = case.get("required_exact_quotes") or []
    if required_sources:
        source_texts = {source["filename"]: source["text"] for source in getattr(scenario, "sources", [])}
        for filename in scenario.corpus:
            if scenario_dir is not None:
                source_texts[filename] = _read_corpus_file(scenario_dir / "corpus" / filename)
        quotes = [
            (match.start(), match.end(), _normalize_quote(next(value for value in match.groups() if value is not None)))
            for match in re.finditer(r'"([^"\n]+)"|“([^”\n]+)”|^>\s*(.+)$', text, re.MULTILINE)
        ]
        quotes = [(start, end, quote) for start, end, quote in quotes if len(quote.split()) >= 4]
        for filename in required_sources:
            source = _normalize_quote(source_texts.get(filename, ""))
            checks[f"exact_quote_{filename}"] = any(
                quote in source and filename in text[max(0, start - 200):end + 200]
                for start, end, quote in quotes
            )
        checks["all_substantial_quotes_grounded"] = bool(quotes) and all(
            any(quote in _normalize_quote(source) for source in source_texts.values())
            for _, _, quote in quotes
        )
    if case.get("forbid_document_citations"):
        checks["no_invented_source"] = not re.search(r"\[[^\]\n]+\.(?:txt|pdf|md)\]", text)
    return checks


def _concept_checks(
    text: str, groups: list[Any]
) -> tuple[bool, list[list[str]]]:
    normalized = text.casefold()
    missing: list[list[str]] = []
    for raw_group in groups:
        if not isinstance(raw_group, list) or not raw_group:
            raise EvaluationConfigurationError(
                "required concept groups must be nonempty lists"
            )
        group = [str(term) for term in raw_group]
        if not any(term.casefold() in normalized for term in group):
            missing.append(group)
    return not missing, missing


def evaluate_chat(case: dict[str, Any], client) -> dict[str, Any]:
    scenario, bundle, operations, scenario_dir = _scenario_for_case(case)
    context_refs = deepcopy(case.get("context_refs") or [])
    for rule_id in case.get("argument_rules") or []:
        argument = next((item for item in bundle["af"]["arguments"] if item["top_rule"] == rule_id), None)
        if argument is None:
            raise EvaluationConfigurationError(f"case {case['id']} cannot select its expected argument")
        context_refs.append({"kind": "argument", "id": argument["id"]})
    result = run_turn(
        scenario,
        bundle["af"],
        operations,
        deepcopy(case.get("history") or []) + [{"role": "user", "content": str(case["question"])}],
        scenario_dir=scenario_dir,
        client=client,
        context_refs=context_refs,
    )
    concepts_passed, missing = _concept_checks(
        result.text, list(case.get("required_concepts") or [])
    )
    grounded = not result.validator_flags and result.stop_reason != "grounding_rejected"
    semantic_checks = _chat_semantic_checks(case, result.text, scenario, bundle, scenario_dir)
    for source in case.get("required_highlight_sources", []):
        semantic_checks[f"highlight_{source}"] = any(
            item.get("kind") == "source" and item.get("source") == source
            and item.get("verified") and item.get("end", 0) > item.get("start", 0)
            for item in result.evidence
        )
    return {
        "passed": grounded and concepts_passed and all(semantic_checks.values()),
        "grounded": grounded,
        "concepts_passed": concepts_passed,
        "missing_concepts": missing,
        "semantic_checks": semantic_checks,
        "engine_labels": bundle["af"]["labels_by_proposition"],
        "context_refs": context_refs,
        "evidence": result.evidence,
        "text": result.text,
        "retried": result.retried,
        "validator_flags": result.validator_flags,
        "result_latency_ms": result.latency_ms,
        "result_cost_microusd": result.cost_microusd,
        "model": result.model,
        "provider": result.provider,
        "route": result.route,
        "billing_source": result.billing_source,
    }


def _description_for_op(operation: dict[str, Any]) -> str:
    for key in ("fact", "assumption", "rule"):
        payload = operation.get(key)
        if isinstance(payload, dict):
            return str(payload.get("description") or "")
    return ""


def _check_proposal(operation: dict[str, Any], expected: dict[str, Any]) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    if "op" in expected:
        checks["op"] = operation.get("op") == expected["op"]
    if "id" in expected:
        checks["id"] = operation.get("id") == expected["id"]
    if "source_origin" in expected:
        if expected["source_origin"] != "user":
            raise EvaluationConfigurationError("unsupported expected source origin")
        payload = next((operation[key] for key in ("fact", "assumption", "rule") if isinstance(operation.get(key), dict)), {})
        source = str(payload.get("source") or "").strip()
        checks["source_origin"] = not source or (
            bool(re.search(r"\buser\b", source, re.I))
            and not re.search(r"\.(?:txt|pdf|md)\b", source, re.I)
        )
    rule = operation.get("rule")
    if "premises_include" in expected:
        premises = set(rule.get("premises") or []) if isinstance(rule, dict) else set()
        checks["premises_include"] = set(expected["premises_include"]).issubset(premises)
    if "conclusion" in expected:
        conclusion = rule.get("conclusion") if isinstance(rule, dict) else None
        checks["conclusion"] = conclusion == expected["conclusion"]
    if "rule_fields" in expected:
        expected_fields = _mapping(expected["rule_fields"], "expected rule_fields")
        checks["rule_fields"] = isinstance(rule, dict) and all(
            rule.get(field) == value for field, value in expected_fields.items()
        )
    for field in ("fact", "assumption"):
        if field + "_fields" in expected:
            value = operation.get(field)
            checks[field + "_fields"] = isinstance(value, dict) and all(
                value.get(key) == item for key, item in expected[field + "_fields"].items()
            )
    if "id_not_in" in expected:
        checks["no_id_collision"] = operation.get("id") not in expected["id_not_in"]
    if "premises_equal" in expected:
        checks["premises_equal"] = isinstance(rule, dict) and set(rule.get("premises") or []) == set(expected["premises_equal"])
    if "new_premise_notes_min" in expected:
        notes = operation.get("new_premise_notes") or []
        checks["new_premise_notes_min"] = (
            isinstance(notes, list)
            and len(notes) >= int(expected["new_premise_notes_min"])
        )
    if "description_contains_any" in expected:
        description = _description_for_op(operation).casefold()
        checks["description_contains_any"] = any(
            str(term).casefold() in description
            for term in expected["description_contains_any"]
        )
    return checks


def evaluate_propose(case: dict[str, Any], client) -> dict[str, Any]:
    scenario, bundle, operations, scenario_dir = _scenario_for_case(case)
    baseline = scenario_to_dict(scenario)
    previous = None
    if case.get("initial_instruction"):
        # Refine clears the preview and submits a replacement instruction. It
        # does not apply the old proposal or insert it into scenario history.
        previous = run_propose(
            scenario, bundle["af"], operations, task=str(case["task"]),
            instruction=str(case["initial_instruction"]), existing_id=case.get("existing_id"),
            scenario_dir=scenario_dir, client=client,
        )
    result = run_propose(
        scenario,
        bundle["af"],
        operations,
        task=str(case["task"]),
        instruction=str(case["instruction"]),
        existing_id=case.get("existing_id"),
        scenario_dir=scenario_dir,
        client=client,
    )
    expected = _mapping(case.get("expected") or {}, f"case {case['id']} expected")
    checks = _check_proposal(result.op, expected)
    if case.get("forbidden_description_terms"):
        description = _description_for_op(result.op).casefold()
        checks["description_preserves_assertion_type"] = not any(
            re.search(r"\b" + re.escape(str(term).casefold()) + r"\b", description)
            for term in case["forbidden_description_terms"]
        )
    applied = apply_ops(scenario, [result.op])
    checks["baseline_unchanged_until_apply"] = scenario_to_dict(scenario) == baseline
    if case.get("preserve_rule_fields"):
        original = baseline["rules"][case["existing_id"]]
        updated = scenario_to_dict(applied)["rules"][case["existing_id"]]
        checks["unrequested_rule_fields_preserved"] = all(
            original.get(field) == updated.get(field) for field in case["preserve_rule_fields"]
        )
    labels_after = compute_state_bundle(applied)["af"]["labels_by_proposition"]
    for literal, label in (case.get("expected_labels_after") or {}).items():
        checks[f"engine_after_{literal}"] = labels_after.get(literal) == label
    return {
        "passed": bool(checks) and all(checks.values()),
        "checks": checks,
        "operation": result.op,
        "initial_operation": previous.op if previous else None,
        "engine_labels_after": labels_after,
        "proposer_attempts": result.proposer_attempts,
        "reviewed": result.reviewed,
        "review_issues": [issue.to_dict() for issue in result.review_issues],
        "result_latency_ms": result.latency_ms,
        "result_cost_microusd": result.cost_microusd,
        "model": result.model,
        "provider": result.provider,
        "route": result.route,
        "billing_source": result.billing_source,
    }


def evaluate_review(case: dict[str, Any], client) -> dict[str, Any]:
    scenario, bundle, operations, scenario_dir = _scenario_for_case(case)
    proposed_edit = _mapping(
        case.get("proposed_edit"), f"case {case['id']} proposed_edit"
    )
    result = run_review(
        scenario,
        bundle["af"],
        operations,
        user_instruction=str(case["instruction"]),
        proposed_edit=proposed_edit,
        scenario_dir=scenario_dir,
        client=client,
    )
    expected = _mapping(case.get("expected") or {}, f"case {case['id']} expected")
    min_issues = int(expected.get("min_issues", 0))
    max_issues = int(expected.get("max_issues", 2**31 - 1))
    allowed = {str(value) for value in expected.get("severities_any") or []}
    count_passed = min_issues <= len(result.issues) <= max_issues
    severity_passed = not allowed or any(issue.severity in allowed for issue in result.issues)
    return {
        "passed": count_passed and severity_passed,
        "count_passed": count_passed,
        "severity_passed": severity_passed,
        "issues": [issue.to_dict() for issue in result.issues],
        "result_latency_ms": result.latency_ms,
        "result_cost_microusd": result.cost_microusd,
        "model": result.model,
        "provider": result.provider,
        "route": result.route,
        "billing_source": result.billing_source,
    }


def _audit_totals(router: LLMRouter, request_id: str) -> dict[str, Any]:
    with router.session_factory() as session:
        events = list(
            session.scalars(
                select(LLMUsageEvent)
                .where(LLMUsageEvent.request_id == request_id)
                .order_by(LLMUsageEvent.created_at, LLMUsageEvent.id)
            )
        )
    return {
        "provider_calls": len(events),
        "successful_provider_calls": sum(event.status == "succeeded" for event in events),
        "failed_provider_calls": sum(event.status == "failed" for event in events),
        "cost_microusd": sum(event.cost_microusd for event in events),
        "latency_ms": sum(event.latency_ms for event in events),
        "input_tokens": sum(event.input_tokens for event in events),
        "output_tokens": sum(event.output_tokens for event in events),
        "cache_read_input_tokens": sum(
            event.cache_read_input_tokens for event in events
        ),
        "cache_creation_input_tokens": sum(
            event.cache_creation_input_tokens for event in events
        ),
        "routes": sorted({event.route for event in events}),
        "models": sorted({event.model for event in events}),
        "attempts": [
            {
                "id": event.id, "provider": event.provider, "model": event.model,
                "route": event.route, "billing_source": event.billing_source,
                "status": event.status, "cost_microusd": event.cost_microusd,
                "latency_ms": event.latency_ms, "error_type": event.error_type,
                "input_tokens": event.input_tokens, "output_tokens": event.output_tokens,
                "cache_read_input_tokens": event.cache_read_input_tokens,
                "cache_creation_input_tokens": event.cache_creation_input_tokens,
            }
            for event in events
        ],
    }


def evaluate_case(
    case: dict[str, Any],
    *,
    router: LLMRouter,
    route_id: str,
    repetition: int,
    allow_emergency_spend: bool,
    spend_cap: PersistentSpendCap | None = None,
    pacer: EvaluationPacer | None = None,
) -> dict[str, Any]:
    assert_no_openrouter_credentials()
    if allow_emergency_spend:
        raise EvaluationConfigurationError("paid OpenRouter evaluations are prohibited")
    if hasattr(router, "catalog"):
        route = router.catalog.routes.get(route_id)
        if route is None or route.provider not in {"azure-foundry", "gcp-vertex"} or route.billing_source != "cloudbank":
            raise EvaluationConfigurationError("evaluation requires an isolated CloudBank route")
        if not isinstance(spend_cap, PersistentSpendCap):
            raise EvaluationConfigurationError("live evaluations require the persistent shared CloudBank budget")
    request_id = "eval-" + uuid4().hex
    started = datetime.now(timezone.utc)
    payload: dict[str, Any]
    error: dict[str, str] | None = None
    client = None
    try:
        client = RecordingClient(router.evaluation_route(
            route_id,
            context=CallContext(
                user_id=None,
                request_id=request_id,
                request_kind=f"eval-{case['kind']}",
                charge_trial=False,
            ),
            allow_emergency_spend=allow_emergency_spend,
            spend_cap=spend_cap,
        ), pacer=pacer, request_timeout_seconds=CASE_REQUEST_SECONDS)
        with funded_network_only():
            if case["kind"] == "chat":
                payload = evaluate_chat(case, client)
            elif case["kind"] == "propose":
                payload = evaluate_propose(case, client)
            else:
                payload = evaluate_review(case, client)
    except ProposerRetryExhausted as exc:
        payload = {
            "passed": False,
            "proposer_attempts": exc.attempts,
            "validator_issues": [issue.to_dict() for issue in exc.last_issues],
        }
        error = {"type": type(exc).__name__, "message": str(exc)}
    except Exception as exc:  # noqa: BLE001
        payload = {"passed": False}
        error = {
            "type": type(exc).__name__,
            "message": "application evaluation did not complete",
            "status_code": getattr(exc, "status_code", None),
        }
    finally:
        close_llm_client(client)

    audit = _audit_totals(router, request_id)
    finished = datetime.now(timezone.utc)
    evidence = getattr(client, "calls", [])
    wall_time_ms = int((finished - started).total_seconds() * 1000)
    pacing_time_ms = round(getattr(client, "pacing_seconds", 0.0) * 1000)
    return {
        "case_id": case["id"],
        "kind": case["kind"],
        "features": case.get("features", []),
        "case_type": case.get("case_type", "unspecified"),
        "scenario_id": case["scenario_id"],
        "route_id": route_id,
        "repetition": repetition,
        "request_id": request_id,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "wall_time_ms": wall_time_ms,
        "pacing_time_ms": pacing_time_ms,
        "application_time_ms": max(0, wall_time_ms - pacing_time_ms),
        "error": error,
        "audit": audit,
        "calls": evidence,
        "provider_configuration": getattr(client, "configuration", {}),
        "evidence_sha256": digest(evidence),
        "semantic_review": {"approved": False, "status": "pending answer inspection"},
        **payload,
    }


def _rate(results: list[dict[str, Any]]) -> float:
    if not results:
        return 0.0
    return sum(bool(result.get("passed")) for result in results) / len(results)


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return ordered[index]


def summarize_route(
    route_id: str,
    results: list[dict[str, Any]],
    gates: dict[str, Any],
) -> dict[str, Any]:
    by_kind = {
        kind: [result for result in results if result["kind"] == kind]
        for kind in ("chat", "propose", "review")
    }
    by_case: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        by_case.setdefault(str(result["case_id"]), []).append(result)
    case_pass_rates = {
        case_id: _rate(case_results)
        for case_id, case_results in sorted(by_case.items())
    }
    minimum_case_pass_rate = min(case_pass_rates.values(), default=0.0)
    total_cost = sum(result["audit"]["cost_microusd"] for result in results)
    average_cost = total_cost / len(results) if results else 0.0
    p95_latency = _p95([int(result["wall_time_ms"]) for result in results])
    p95_application_latency = _p95([int(result.get("application_time_ms", result["wall_time_ms"])) for result in results])
    error_count = sum(result.get("error") is not None for result in results)
    metrics = {
        "route_id": route_id,
        "case_count": len(results),
        "passed_count": sum(bool(result.get("passed")) for result in results),
        "overall_pass_rate": _rate(results),
        "chat_pass_rate": _rate(by_kind["chat"]),
        "propose_pass_rate": _rate(by_kind["propose"]),
        "review_pass_rate": _rate(by_kind["review"]),
        "case_pass_rates": case_pass_rates,
        "minimum_case_pass_rate": minimum_case_pass_rate,
        "failed_case_ids": [
            case_id
            for case_id, pass_rate in case_pass_rates.items()
            if pass_rate < float(gates.get("min_case_pass_rate", 0))
        ],
        "error_count": error_count,
        "total_cost_microusd": total_cost,
        "average_cost_microusd": average_cost,
        "p95_wall_time_ms": p95_latency,
        "p95_application_time_ms": p95_application_latency,
        "pacing_time_ms": sum(result.get("pacing_time_ms", 0) for result in results),
        "provider_calls": sum(
            result["audit"]["provider_calls"] for result in results
        ),
    }
    comparisons = {
        "overall_pass_rate": metrics["overall_pass_rate"]
        >= float(gates.get("min_overall_pass_rate", 0)),
        "chat_pass_rate": not by_kind["chat"]
        or metrics["chat_pass_rate"] >= float(gates.get("min_chat_pass_rate", 0)),
        "propose_pass_rate": not by_kind["propose"]
        or metrics["propose_pass_rate"]
        >= float(gates.get("min_propose_pass_rate", 0)),
        "review_pass_rate": not by_kind["review"]
        or metrics["review_pass_rate"]
        >= float(gates.get("min_review_pass_rate", 0)),
        "minimum_case_pass_rate": minimum_case_pass_rate
        >= float(gates.get("min_case_pass_rate", 0)),
        "error_count": error_count <= int(gates.get("max_error_count", 0)),
        "p95_application_time_ms": p95_application_latency
        <= int(gates.get("max_p95_latency_ms", 2**31 - 1)),
        "average_cost_microusd": average_cost
        <= float(gates.get("max_average_cost_microusd", 2**63 - 1)),
    }
    return {**metrics, "gate_checks": comparisons, "gate_passed": all(comparisons.values())}


def _selected_cases(
    suite: dict[str, Any], *, smoke: bool, case_ids: set[str]
) -> list[dict[str, Any]]:
    cases = [dict(case) for case in suite["cases"]]
    if smoke:
        cases = [case for case in cases if case.get("smoke") is True]
    if case_ids:
        known = {str(case["id"]) for case in cases}
        missing = sorted(case_ids - known)
        if missing:
            raise EvaluationConfigurationError(
                "unknown or filtered evaluation cases: " + ", ".join(missing)
            )
        cases = [case for case in cases if case["id"] in case_ids]
    if not cases:
        raise EvaluationConfigurationError("no evaluation cases were selected")
    return cases


def _read_checkpoint(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    data = path.read_bytes()
    complete = data.rsplit(b"\n", 1)[0] + b"\n" if not data.endswith(b"\n") else data
    if not data.endswith(b"\n"):
        # A Slurm time limit can interrupt the last append. Preserve that tail
        # for inspection, then resume only complete, fsynced case records.
        if b"\n" not in data:
            raise EvaluationConfigurationError("evaluation checkpoint has no complete header")
        tail = data[len(complete):]
        partial = path.with_name(path.name + ".partial-" + uuid4().hex)
        partial.write_bytes(tail)
        with path.open("r+b") as handle:
            handle.truncate(len(complete))
            handle.flush()
            os.fsync(handle.fileno())
    records = [json.loads(line) for line in complete.splitlines() if line.strip()]
    if not records:
        raise EvaluationConfigurationError("evaluation checkpoint is empty")
    return records[0], [record["result"] for record in records[1:]]


def run_evaluation(
    suite: dict[str, Any],
    *,
    suite_hash: str,
    route_ids: list[str],
    router: LLMRouter,
    repetitions: int,
    smoke: bool,
    case_ids: set[str],
    allow_emergency_spend: bool,
    paid_run_cap_microusd: int,
    spend_cap: PersistentSpendCap | None = None,
    phase: str = "baseline",
    checkpoint_path: Path | None = None,
    resume: bool = False,
    rate_limits: dict[str, DeploymentRate] | None = None,
    stop_after_unix: float | None = None,
    stop_file: Path | None = None,
) -> dict[str, Any]:
    assert_no_openrouter_credentials()
    if allow_emergency_spend:
        raise EvaluationConfigurationError("paid OpenRouter evaluations are prohibited by the CloudBank-only authorization")
    if not 0 < paid_run_cap_microusd <= MAX_CLOUDBANK_EVALUATION_MICROUSD:
        raise EvaluationConfigurationError("evaluation cap must be within the authorized $150")
    cases = _selected_cases(suite, smoke=smoke, case_ids=case_ids)
    rate_limits = rate_limits or {}
    if rate_limits and not set(route_ids).issubset(rate_limits):
        raise EvaluationConfigurationError("pacing needs a configured limit for every selected route")
    gates = _mapping(suite.get("gates") or {}, "gates")
    catalog = router.catalog
    unknown_routes = sorted(set(route_ids) - set(catalog.routes))
    if unknown_routes:
        raise EvaluationConfigurationError(
            "unknown routes: " + ", ".join(unknown_routes)
        )
    if any(
        catalog.routes[route_id].provider not in {"azure-foundry", "gcp-vertex"}
        or catalog.routes[route_id].billing_source not in {"cloudbank", "cloudbank-azure", "cloudbank-gcp"}
        for route_id in route_ids
    ):
        raise EvaluationConfigurationError("evaluation routes must be funded by CloudBank Azure or GCP")

    results: list[dict[str, Any]] = []
    fingerprint = implementation_fingerprint()
    model_evidence = {
        route_id: {
            "route": asdict(catalog.routes[route_id]),
            "model": asdict(catalog.model_for_route(catalog.routes[route_id])),
            "deployment": (os.getenv(catalog.routes[route_id].model_env, "") if catalog.routes[route_id].model_env else "") or catalog.routes[route_id].request_model,
            "prompt_sha256": {name: value for name, value in fingerprint["files"].items() if name.startswith("app/prompts/")},
            "implementation_sha256": fingerprint["sha256"],
            "physical_retry_attempts": router.settings.llm_retry_attempts,
            "cache_requested": True,
        }
        for route_id in route_ids
    }
    run_id = spend_cap.run_id if spend_cap else uuid4().hex
    metadata = {
        "suite_sha256": suite_hash, "routes": route_ids, "repetitions": repetitions,
        "case_ids": [case["id"] for case in cases], "phase": phase,
        "execution_order": "case_then_repetition",
        "implementation_sha256": fingerprint["sha256"], "run_limit_microusd": paid_run_cap_microusd,
        "model_configuration_sha256": digest(model_evidence),
        "rate_limits": {route: asdict(rate_limits[route]) for route in route_ids if route in rate_limits},
    }
    if resume:
        if checkpoint_path is None or not checkpoint_path.is_file():
            raise EvaluationConfigurationError("resume needs an existing evaluation checkpoint")
        header, results = _read_checkpoint(checkpoint_path)
        if header.get("metadata") != metadata:
            raise EvaluationConfigurationError("resume must use the exact same code, prompts, suite, routes, cases, and settings")
        run_id = header["run_id"]
        if spend_cap is not None and spend_cap.run_id != run_id:
            raise EvaluationConfigurationError("resumed evaluation must use its original budget run")
    if spend_cap is not None and (spend_cap.run_limit_microusd != paid_run_cap_microusd or spend_cap.phase != phase):
        raise EvaluationConfigurationError("evaluation budget view must match this run's cap and phase")
    spend_cap = spend_cap or PersistentSpendCap(run_id=run_id, run_limit_microusd=paid_run_cap_microusd, phase=phase)
    if checkpoint_path is not None:
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        if not resume:
            with checkpoint_path.open("x", encoding="utf-8") as handle:
                handle.write(json.dumps({"run_id": run_id, "metadata": metadata}, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())

    def record(result):
        results.append(result)
        if checkpoint_path is not None:
            with checkpoint_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"result": result}, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())

    completed = {(result["route_id"], result["case_id"], result["repetition"]) for result in results}
    stopped_reason = None
    with funded_network_only():
        for route_id in route_ids:
            route = catalog.routes[route_id]
            pacer = EvaluationPacer(
                budget=spend_cap,
                deployment=f"{route.provider}:{model_evidence[route_id]['deployment'] or route.model}",
                rate=rate_limits[route_id], physical_attempts=router.settings.llm_retry_attempts,
            ) if route_id in rate_limits else None
            # Keep repetitions adjacent so unchanged prompt prefixes can use
            # provider caching. Every observation still has a fresh client and
            # independently recorded output, usage, and accounting.
            for case in cases:
                for repetition in range(1, repetitions + 1):
                    if (route_id, case["id"], repetition) in completed:
                        continue
                    if stop_file is not None and stop_file.exists():
                        stopped_reason = "operator stop requested at a case boundary"
                    elif stop_after_unix is not None and time.time() + CASE_REQUEST_SECONDS >= stop_after_unix:
                        stopped_reason = "runtime limit reached at a case boundary"
                    if stopped_reason:
                        break
                    if spend_cap.reached:
                        record(
                            {
                                "case_id": case["id"], "kind": case["kind"],
                                "route_id": route_id, "repetition": repetition,
                                "request_id": None, "passed": False, "skipped": True,
                                "error": {"type": "PaidRunCapReached", "message": "the shared CloudBank evaluation cap was reached"},
                                "audit": {"provider_calls": 0, "cost_microusd": 0}, "wall_time_ms": 0,
                            }
                        )
                        continue
                    result = evaluate_case(
                        case, router=router, route_id=route_id, repetition=repetition,
                        allow_emergency_spend=False, spend_cap=spend_cap,
                        pacer=pacer,
                    )
                    record(result)
                if stopped_reason:
                    break
            if stopped_reason:
                break

    budget_snapshot = spend_cap.snapshot()

    summaries = {
        route_id: summarize_route(
            route_id,
            [result for result in results if result["route_id"] == route_id],
            gates,
        )
        for route_id in route_ids
    }
    expected_observations = len(route_ids) * repetitions * len(cases)
    all_observations_recorded = len(results) == expected_observations
    return {
        "schema_version": 3,
        "usage_contract": "exclusive-input-cache-v1",
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "suite_name": suite.get("name"),
        "suite_version": suite.get("version"),
        "suite_sha256": suite_hash,
        "suite_definition": suite,
        "implementation": fingerprint,
        "implementation_unchanged": implementation_fingerprint()["sha256"] == fingerprint["sha256"],
        "catalog_version": catalog.version,
        "catalog_updated": catalog.updated,
        "routes": route_ids,
        "repetitions": repetitions,
        "stopped_reason": stopped_reason,
        "expected_observations": expected_observations,
        "remaining_observations": max(0, expected_observations - len(results)),
        "pacing": metadata["rate_limits"],
        "smoke": smoke,
        "allow_emergency_spend": False,
        "paid_run_cap_microusd": paid_run_cap_microusd,
        "paid_spend_microusd": budget_snapshot["run_spent_microusd"],
        "cloudbank_budget": budget_snapshot,
        "route_configuration": {route_id: asdict(catalog.routes[route_id]) for route_id in route_ids},
        "model_evidence": model_evidence,
        "decoding_configuration": {
            "case_request_timeout_seconds": CASE_REQUEST_SECONDS,
            "chat_max_output_tokens": MAX_TOKENS_PER_RESPONSE, "propose_max_output_tokens": MAX_TOKENS_PER_PROPOSE,
            "review_max_output_tokens": MAX_TOKENS_PER_REVIEW, "physical_retry_attempts": router.settings.llm_retry_attempts,
            "cache_requested": True,
        },
        "gates": gates,
        "summaries": summaries,
        "results": results,
        "coverage_matrix": coverage_matrix(suite, results, route_ids, repetitions=repetitions, configurations=model_evidence),
        "application_accepted": False,
        "prompt_tuning_policy": "Tune when and only when reviewed application failures demonstrate a need. Passing prompts remain unchanged.",
        "automated_gate_passed": all_observations_recorded and all(summary["gate_passed"] for summary in summaries.values()),
        "gate_passed": all_observations_recorded and all(summary["gate_passed"] for summary in summaries.values()) and not suite.get("requires_answer_review", False),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate ABDA prompts against isolated model routes"
    )
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--route", action="append", dest="routes")
    parser.add_argument("--case", action="append", dest="cases", default=[])
    parser.add_argument("--repetitions", type=int)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--list-routes", action="store_true")
    parser.add_argument("--allow-openrouter-spend", action="store_true")
    parser.add_argument(
        "--paid-run-cap-microusd",
        type=int,
        default=DEFAULT_PAID_RUN_CAP_MICROUSD,
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--phase", choices=("availability", "baseline", "tuning", "regression"), default="baseline")
    parser.add_argument("--resume", action="store_true", help="resume the checkpoint beside --output without resetting spend")
    parser.add_argument("--rate-limit", action="append", default=[], help="ROUTE:RPM:TPM evaluation pacing target")
    parser.add_argument("--stop-after-unix", type=float, help="finish the current case after this UTC timestamp, then checkpoint")
    parser.add_argument("--stop-file", type=Path, help="finish the current case if this operator stop file exists")
    parser.add_argument("--no-fail-on-gate", action="store_true")
    return parser


def _default_output() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return REPOSITORY_ROOT / "artifacts" / "evals" / f"{stamp}.json"


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    # This process must never load the root .env because it contains backup
    # credentials. The separate funded launcher selects only funded settings.
    reset_settings_cache()
    reset_model_catalog_cache()
    catalog = load_model_catalog()
    if args.list_routes:
        for route in catalog.routes.values():
            # Billing metadata is intentionally omitted. Operators need the
            # stable route selector, provider, and model here, while funding
            # details remain in the validated catalog and evaluation report.
            print(f"{route.id}\t{route.provider}\t{route.model}")
        return 0
    if not args.routes:
        print("At least one --route is required.", file=sys.stderr)
        return 2
    if args.repetitions is not None and args.repetitions < 1:
        print("--repetitions must be positive.", file=sys.stderr)
        return 2
    if args.paid_run_cap_microusd < 1:
        print("--paid-run-cap-microusd must be positive.", file=sys.stderr)
        return 2

    try:
        assert_no_openrouter_credentials()
        try:
            rate_limits = parse_rate_limits(args.rate_limit)
        except ValueError as exc:
            raise EvaluationConfigurationError(str(exc)) from exc
        suite, suite_hash = load_suite(args.suite.resolve())
        repetitions = args.repetitions or int(suite.get("default_repetitions", 1))
        initialize_database()
        router = LLMRouter(settings=get_settings(), catalog=catalog)
        output = (args.output or _default_output()).resolve()
        if args.resume and args.output is None:
            raise EvaluationConfigurationError("--resume requires --output to identify the original checkpoint")
        report = run_evaluation(
            suite,
            suite_hash=suite_hash,
            route_ids=list(dict.fromkeys(args.routes)),
            router=router,
            repetitions=repetitions,
            smoke=args.smoke,
            case_ids=set(args.cases),
            allow_emergency_spend=args.allow_openrouter_spend,
            paid_run_cap_microusd=args.paid_run_cap_microusd,
            phase=args.phase,
            checkpoint_path=output.with_suffix(".checkpoint.jsonl"),
            resume=args.resume,
            rate_limits=rate_limits,
            stop_after_unix=args.stop_after_unix,
            stop_file=args.stop_file,
        )
    except (EvaluationConfigurationError, RuntimeError, OSError) as exc:
        print(f"Evaluation could not start: {exc}", file=sys.stderr)
        return 2

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    summary = {
        "gate_passed": report["gate_passed"],
        "paid_spend_microusd": report["paid_spend_microusd"],
        "output": str(output),
        "summaries": report["summaries"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    if report["gate_passed"] or args.no_fail_on_gate:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
