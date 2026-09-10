"""Smooth synthetic calls across processes without changing public routing."""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any

from app.evals.budget import PersistentSpendCap
from app.llm.routing import _request_size_tokens


@dataclass(frozen=True)
class DeploymentRate:
    requests_per_minute: int
    tokens_per_minute: int

    def __post_init__(self) -> None:
        if self.requests_per_minute < 1 or self.tokens_per_minute < 1:
            raise ValueError("evaluation pacing limits must be positive")


def parse_rate_limits(values: list[str]) -> dict[str, DeploymentRate]:
    rates = {}
    for value in values:
        try:
            route, rpm, tpm = value.rsplit(":", 2)
            rate = DeploymentRate(int(rpm), int(tpm))
        except (ValueError, TypeError) as exc:
            raise ValueError("rate limit must be ROUTE:REQUESTS_PER_MINUTE:TOKENS_PER_MINUTE") from exc
        if not route or route in rates:
            raise ValueError("each evaluation route may have only one pacing limit")
        rates[route] = rate
    return rates


class EvaluationPacer:
    """Reserve a shared deployment slot before a logical provider invocation.

    The token estimate is for throughput planning, not financial accounting.
    UTF-8 bytes/3 plus the output allowance conservatively estimates this English
    suite's input. Reserve capacity for both possible physical attempts and use
    only 80 percent of the configured target. Provider limits remain dynamic;
    the authoritative spend guard separately reserves its stricter byte bound
    before every physical dispatch. Abandoned pacing slots are never refunded.
    """

    def __init__(
        self, *, budget: PersistentSpendCap, deployment: str,
        rate: DeploymentRate, physical_attempts: int,
    ) -> None:
        self.budget = budget
        self.deployment = deployment
        self.rate = rate
        self.physical_attempts = max(1, min(2, physical_attempts))
        with self.budget._transaction() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS evaluation_pacing ("
                "deployment TEXT PRIMARY KEY, next_slot_unix REAL NOT NULL)"
            )

    def before_call(self, request: dict[str, Any]) -> dict[str, Any]:
        byte_bound = _request_size_tokens(
            system=request["system"], messages=request["messages"],
            tool=request.get("tool"),
        )
        planned_tokens = math.ceil(byte_bound / 3) + int(request["max_tokens"])
        weighted_tokens = planned_tokens * self.physical_attempts
        seconds = max(
            60 * self.physical_attempts / self.rate.requests_per_minute,
            60 * weighted_tokens / self.rate.tokens_per_minute,
        ) / 0.8
        started = time.time()
        with self.budget._transaction() as connection:
            row = connection.execute(
                "SELECT next_slot_unix FROM evaluation_pacing WHERE deployment = ?",
                (self.deployment,),
            ).fetchone()
            scheduled = max(time.time(), row[0] if row else 0)
            connection.execute(
                "INSERT INTO evaluation_pacing VALUES (?, ?) "
                "ON CONFLICT(deployment) DO UPDATE SET next_slot_unix = excluded.next_slot_unix",
                (self.deployment, scheduled + seconds),
            )
        while (remaining := scheduled - time.time()) > 0:
            time.sleep(min(remaining, 30.0))
        return {
            "deployment": self.deployment,
            "requests_per_minute": self.rate.requests_per_minute,
            "tokens_per_minute": self.rate.tokens_per_minute,
            "planned_tokens_per_attempt": planned_tokens,
            "physical_attempts_allowed": self.physical_attempts,
            "scheduled_at_unix": scheduled,
            "wait_ms": round((time.time() - started) * 1000),
        }
