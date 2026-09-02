"""Contracts for the bounded public capacity smoke gate."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from deploy.azure.gate17_public_capacity_smoke import (
    BASELINE_REQUESTS,
    CapacitySmokeError,
    MAX_CONCURRENCY,
    Observation,
    PUBLIC_ORIGIN,
    REQUESTS_PER_PHASE,
    run_smoke,
    summarize_phase,
)


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "deploy" / "azure" / "gate17_public_capacity_smoke.py"


def test_gate_has_a_fixed_bounded_public_contract():
    source = GATE.read_text(encoding="utf-8")
    assert PUBLIC_ORIGIN == "https://demo.abda-nl.org"
    assert REQUESTS_PER_PHASE == 40
    assert MAX_CONCURRENCY == 20
    assert BASELINE_REQUESTS == 3
    assert "OPENROUTER_API_KEY" not in source
    assert "AZURE_OPENAI_API_KEY" not in source
    assert "/chat" not in source
    assert "/propose" not in source
    assert "LIVE_PUBLIC_BOUNDED_CAPACITY_SMOKE_VERIFIED" in source


def test_summary_rejects_http_failures_and_response_drift():
    expected = "a" * 64
    valid = [Observation(10, 200, expected) for _ in range(REQUESTS_PER_PHASE)]
    summary = summarize_phase(
        "valid", valid, expected_sha256=expected, p95_limit_ms=100
    )
    assert summary.requests == REQUESTS_PER_PHASE
    assert summary.p95_ms == 10

    failed = [*valid[:-1], Observation(10, 503, expected)]
    with pytest.raises(CapacitySmokeError, match="http_503=1"):
        summarize_phase("failed", failed, expected_sha256=expected, p95_limit_ms=100)

    drifted = [*valid[:-1], Observation(10, 200, "b" * 64)]
    with pytest.raises(CapacitySmokeError, match="1 inconsistent"):
        summarize_phase("drifted", drifted, expected_sha256=expected, p95_limit_ms=100)


def test_summary_rejects_slow_p95():
    expected = "a" * 64
    observations = [
        Observation(10 if index < 37 else 101, 200, expected)
        for index in range(REQUESTS_PER_PHASE)
    ]
    with pytest.raises(CapacitySmokeError, match="p95 latency 101 ms exceeds 100 ms"):
        summarize_phase(
            "slow", observations, expected_sha256=expected, p95_limit_ms=100
        )


def test_smoke_exercises_all_three_content_free_paths():
    state = {
        "scenario": {"id": "popov_v_hayashi"},
        "af": {"arguments": [], "attacks": []},
    }
    ready_bytes = json.dumps({"status": "ready"}).encode()
    state_bytes = json.dumps(state).encode()
    counts = {"ready": 0, "scenario": 0, "state": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health/ready":
            counts["ready"] += 1
            return httpx.Response(200, content=ready_bytes)
        if request.url.path == "/scenarios/popov_v_hayashi":
            counts["scenario"] += 1
            return httpx.Response(200, content=state_bytes)
        if request.url.path == "/state" and request.method == "POST":
            counts["state"] += 1
            assert json.loads(request.content) == {
                "scenario_id": "popov_v_hayashi",
                "diff_ops": [],
            }
            return httpx.Response(200, content=state_bytes)
        return httpx.Response(404)

    summaries = asyncio.run(
        run_smoke(
            origin="https://capacity.test",
            transport=httpx.MockTransport(handler),
        )
    )
    assert [item.name for item in summaries] == ["readiness", "scenario", "state"]
    assert counts == {
        "ready": REQUESTS_PER_PHASE + 2,
        "scenario": REQUESTS_PER_PHASE + 1,
        "state": REQUESTS_PER_PHASE,
    }
