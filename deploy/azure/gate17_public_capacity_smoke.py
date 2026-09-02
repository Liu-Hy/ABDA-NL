#!/usr/bin/env python3
"""Run a bounded, content-free burst against the public deterministic service."""

from __future__ import annotations

import asyncio
import hashlib
import math
import time
from dataclasses import dataclass
from typing import Any

import httpx


PUBLIC_ORIGIN = "https://demo.abda-nl.org"
REQUESTS_PER_PHASE = 40
MAX_CONCURRENCY = 20
BASELINE_REQUESTS = 3
REQUEST_TIMEOUT_SECONDS = 15.0
READY_P95_LIMIT_MS = 2_500
DETERMINISTIC_P95_LIMIT_MS = 6_000
EXPECTED_READY = {"status": "ready"}
STATE_REQUEST = {"scenario_id": "popov_v_hayashi", "diff_ops": []}


class CapacitySmokeError(RuntimeError):
    """A bounded public capacity invariant failed."""


@dataclass(frozen=True)
class Observation:
    elapsed_ms: int
    status_code: int
    body_sha256: str
    error: str | None = None


@dataclass(frozen=True)
class PhaseSummary:
    name: str
    requests: int
    p50_ms: int
    p95_ms: int
    maximum_ms: int


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _percentile(values: list[int], quantile: float) -> int:
    if not values:
        raise CapacitySmokeError("a capacity phase returned no observations")
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * quantile) - 1)
    return ordered[index]


def summarize_phase(
    name: str,
    observations: list[Observation],
    *,
    expected_sha256: str,
    p95_limit_ms: int | None,
) -> PhaseSummary:
    if len(observations) != REQUESTS_PER_PHASE:
        raise CapacitySmokeError(
            f"{name} completed {len(observations)} of {REQUESTS_PER_PHASE} requests"
        )
    failures = [item for item in observations if item.error or item.status_code != 200]
    if failures:
        status_counts: dict[str, int] = {}
        for item in failures:
            key = item.error or f"http_{item.status_code}"
            status_counts[key] = status_counts.get(key, 0) + 1
        compact = ", ".join(
            f"{key}={count}" for key, count in sorted(status_counts.items())
        )
        raise CapacitySmokeError(f"{name} request failures: {compact}")
    mismatches = sum(item.body_sha256 != expected_sha256 for item in observations)
    if mismatches:
        raise CapacitySmokeError(f"{name} returned {mismatches} inconsistent responses")
    elapsed = [item.elapsed_ms for item in observations]
    summary = PhaseSummary(
        name=name,
        requests=len(observations),
        p50_ms=_percentile(elapsed, 0.50),
        p95_ms=_percentile(elapsed, 0.95),
        maximum_ms=max(elapsed),
    )
    if p95_limit_ms is not None and summary.p95_ms > p95_limit_ms:
        raise CapacitySmokeError(
            f"{name} p95 latency {summary.p95_ms} ms exceeds {p95_limit_ms} ms"
        )
    return summary


async def _observe(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
) -> Observation:
    started = time.monotonic()
    try:
        response = await client.request(method, path, json=body)
    except httpx.TimeoutException:
        return Observation(
            elapsed_ms=int((time.monotonic() - started) * 1000),
            status_code=0,
            body_sha256="",
            error="timeout",
        )
    except httpx.TransportError:
        return Observation(
            elapsed_ms=int((time.monotonic() - started) * 1000),
            status_code=0,
            body_sha256="",
            error="transport_error",
        )
    return Observation(
        elapsed_ms=int((time.monotonic() - started) * 1000),
        status_code=response.status_code,
        body_sha256=_digest(response.content),
    )


async def _phase(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
) -> list[Observation]:
    pending = [
        asyncio.create_task(_observe(client, method, path, body=body))
        for _ in range(REQUESTS_PER_PHASE)
    ]
    return list(await asyncio.gather(*pending))


async def run_smoke(
    *,
    origin: str = PUBLIC_ORIGIN,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[PhaseSummary]:
    timeout = httpx.Timeout(REQUEST_TIMEOUT_SECONDS, connect=5.0)
    limits = httpx.Limits(
        max_connections=MAX_CONCURRENCY,
        max_keepalive_connections=MAX_CONCURRENCY,
    )
    async with httpx.AsyncClient(
        base_url=origin,
        timeout=timeout,
        limits=limits,
        transport=transport,
        follow_redirects=False,
        headers={"User-Agent": "ABDA-NL-public-capacity-smoke/1"},
    ) as client:
        ready = await client.get("/health/ready")
        if ready.status_code != 200 or ready.json() != EXPECTED_READY:
            raise CapacitySmokeError("the public readiness baseline failed")
        scenario = await client.get("/scenarios/popov_v_hayashi")
        if scenario.status_code != 200:
            raise CapacitySmokeError("the deterministic scenario baseline failed")
        scenario_payload = scenario.json()
        if not isinstance(scenario_payload.get("scenario"), dict) or not isinstance(
            scenario_payload.get("af"), dict
        ):
            raise CapacitySmokeError("the deterministic scenario shape changed")
        expected_ready_sha256 = _digest(ready.content)
        expected_scenario_sha256 = _digest(scenario.content)

        ready_observations = await _phase(client, "GET", "/health/ready")
        scenario_observations = await _phase(
            client, "GET", "/scenarios/popov_v_hayashi"
        )
        state_observations = await _phase(
            client,
            "POST",
            "/state",
            body=STATE_REQUEST,
        )
        final_ready = await client.get("/health/ready")
        if final_ready.status_code != 200 or final_ready.json() != EXPECTED_READY:
            raise CapacitySmokeError("the public readiness check failed after the burst")

    summaries = [
        summarize_phase(
            "readiness",
            ready_observations,
            expected_sha256=expected_ready_sha256,
            p95_limit_ms=None,
        ),
        summarize_phase(
            "scenario",
            scenario_observations,
            expected_sha256=expected_scenario_sha256,
            p95_limit_ms=None,
        ),
        summarize_phase(
            "state",
            state_observations,
            expected_sha256=expected_scenario_sha256,
            p95_limit_ms=None,
        ),
    ]
    limits = {
        "readiness": READY_P95_LIMIT_MS,
        "scenario": DETERMINISTIC_P95_LIMIT_MS,
        "state": DETERMINISTIC_P95_LIMIT_MS,
    }
    violations = [
        item for item in summaries if item.p95_ms > limits[item.name]
    ]
    if violations:
        failed = ", ".join(
            f"{item.name} p95 {item.p95_ms} ms exceeds {limits[item.name]} ms"
            for item in violations
        )
        observed = "; ".join(
            f"{item.name} p50={item.p50_ms} p95={item.p95_ms} max={item.maximum_ms} ms"
            for item in summaries
        )
        raise CapacitySmokeError(f"{failed}; all observations: {observed}")
    return summaries


def main() -> int:
    print("ABDA-NL public bounded capacity smoke revision: 1")
    print("This gate sends 120 measured requests plus three baseline checks.")
    print("Measured requests use at most 20 concurrent connections.")
    print("It never signs in, calls a model, creates a project, or changes Azure settings.")
    print("The 40 POST requests create only an automatically expiring rate-limit counter.\n")
    try:
        summaries = asyncio.run(run_smoke())
    except (CapacitySmokeError, httpx.HTTPError, ValueError) as exc:
        print(f"STOP: {exc}")
        return 1
    print("ABDA-NL public bounded capacity smoke status:")
    print(f"public_origin: {PUBLIC_ORIGIN}")
    measured_requests = sum(item.requests for item in summaries)
    print(f"requests_total: {measured_requests + BASELINE_REQUESTS}")
    print(f"measured_requests: {measured_requests}")
    print(f"max_concurrency: {MAX_CONCURRENCY}")
    for item in summaries:
        print(f"{item.name}_requests: {item.requests}")
        print(f"{item.name}_p50_ms: {item.p50_ms}")
        print(f"{item.name}_p95_ms: {item.p95_ms}")
        print(f"{item.name}_maximum_ms: {item.maximum_ms}")
    print("http_failures: 0")
    print("response_mismatches: 0")
    print("authenticated_requests: false")
    print("model_provider_called: false")
    print("azure_configuration_changed: false")
    print("result: LIVE_PUBLIC_BOUNDED_CAPACITY_SMOKE_VERIFIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
