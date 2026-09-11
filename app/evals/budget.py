"""Durable, process-safe accounting for the authorized CloudBank evaluation.

Every physical provider attempt reserves its maximum possible charge before
dispatch. Pending reservations survive a crash and remain committed until a
verified reconciliation settles them. Opening a new run never resets spend.
"""
from __future__ import annotations

import os
import json
import socket
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from app.llm.routing import PaidRunCapReached, SpendCapReservation


# The owner raised the cumulative ceiling on September 11, retaining all
# prior charges in the original ledger. Existing ledgers require an explicit
# operator amendment; constructing a run never raises a stored ceiling.
MAX_CLOUDBANK_EVALUATION_MICROUSD = 150_000_000
DEFAULT_BUDGET_PATH = (
    Path(__file__).resolve().parents[2]
    / "artifacts" / "evals" / "cloudbank-budget.sqlite3"
)
BUDGET_ID = "demo-revision-20260909-cloudbank"


class EvaluationBudgetError(RuntimeError):
    """A ledger failure prevents safe dispatch or reconciliation."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PersistentSpendCap:
    """A per-run view of one shared, non-resetting $150 budget.

    ``path`` exists for isolated tests and installations. The production CLI
    always uses ``DEFAULT_BUDGET_PATH`` and exposes no path/reset option.
    SQLite's immediate transaction serializes reservations across processes.
    A process interrupted after reserve cannot make its unused allowance
    available to another process without a positive billing receipt.
    """

    def __init__(
        self,
        *,
        path: Path = DEFAULT_BUDGET_PATH,
        run_id: str | None = None,
        run_limit_microusd: int = MAX_CLOUDBANK_EVALUATION_MICROUSD,
        phase: str = "baseline",
        mutex_timeout_seconds: float = 30.0,
    ) -> None:
        if not 0 < run_limit_microusd <= MAX_CLOUDBANK_EVALUATION_MICROUSD:
            raise ValueError("evaluation run limit must be within the authorized $150")
        if phase not in {"availability", "baseline", "tuning", "regression"}:
            raise ValueError("unknown evaluation phase")
        self.path = path.resolve()
        self.run_id = run_id or uuid4().hex
        self.limit_microusd = MAX_CLOUDBANK_EVALUATION_MICROUSD
        self.run_limit_microusd = run_limit_microusd
        self.phase = phase
        self.mutex_timeout_seconds = mutex_timeout_seconds
        self._reached = False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(descriptor)
        with self._transaction() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS evaluation_budget ("
                "id TEXT PRIMARY KEY, limit_microusd INTEGER NOT NULL, "
                "blocked_reason TEXT, created_at TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS evaluation_runs ("
                "id TEXT PRIMARY KEY, budget_id TEXT NOT NULL, "
                "limit_microusd INTEGER NOT NULL, phase TEXT NOT NULL, "
                "created_at TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS evaluation_reservations ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, budget_id TEXT NOT NULL, "
                "run_id TEXT NOT NULL, amount_microusd INTEGER NOT NULL CHECK(amount_microusd > 0), "
                "actual_microusd INTEGER CHECK(actual_microusd >= 0), "
                "status TEXT NOT NULL CHECK(status IN ('pending', 'settled', 'released')), "
                "created_at TEXT NOT NULL, reconciled_at TEXT)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS evaluation_adjustments ("
                "id TEXT PRIMARY KEY, budget_id TEXT NOT NULL, run_id TEXT NOT NULL, "
                "amount_microusd INTEGER NOT NULL CHECK(amount_microusd > 0), "
                "reason TEXT NOT NULL, evidence_sha256 TEXT NOT NULL, created_at TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT OR IGNORE INTO evaluation_budget VALUES (?, ?, NULL, ?)",
                (BUDGET_ID, self.limit_microusd, _now()),
            )
            stored = connection.execute(
                "SELECT limit_microusd FROM evaluation_budget WHERE id = ?",
                (BUDGET_ID,),
            ).fetchone()
            if stored is None or stored[0] != self.limit_microusd:
                raise EvaluationBudgetError("the shared evaluation budget has an invalid ceiling")
            connection.execute(
                "INSERT OR IGNORE INTO evaluation_runs VALUES (?, ?, ?, ?, ?)",
                (self.run_id, BUDGET_ID, run_limit_microusd, phase, _now()),
            )
            run = connection.execute(
                "SELECT budget_id, limit_microusd, phase FROM evaluation_runs WHERE id = ?",
                (self.run_id,),
            ).fetchone()
            if run != (BUDGET_ID, run_limit_microusd, phase):
                raise EvaluationBudgetError("a resumed evaluation cannot change its run limits or phase")

    @contextmanager
    def _filesystem_mutex(self) -> Iterator[None]:
        """Secondary network-filesystem lock, independent of SQLite fcntl locks.

        Atomic directory creation is serialized by the filesystem server. Never
        delete an existing lock merely because its timestamp is old: a paused or
        disconnected writer may still be alive. Interrupted locks require proof
        that the recorded host/process or Slurm job has stopped before recovery.
        """
        lock = self.path.with_name(self.path.name + ".lock")
        deadline = time.monotonic() + self.mutex_timeout_seconds
        while True:
            try:
                lock.mkdir(mode=0o700)
                break
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise EvaluationBudgetError("evaluation ledger writer lock is occupied; no calls may proceed") from None
                time.sleep(0.025)
        owner_path = lock / "owner.json"
        owner = {"host": socket.gethostname(), "pid": os.getpid(), "slurm_job_id": os.getenv("SLURM_JOB_ID"), "created_at": _now()}
        try:
            with owner_path.open("x", encoding="utf-8") as handle:
                json.dump(owner, handle)
                handle.flush()
                os.fsync(handle.fileno())
            yield
        finally:
            # This context owns the directory; no timeout-based taker can race
            # its release. An external operator must verify stopped ownership.
            owner_path.unlink(missing_ok=True)
            lock.rmdir()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._filesystem_mutex():
            connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
            try:
                connection.execute("PRAGMA journal_mode=DELETE")
                connection.execute("PRAGMA synchronous=FULL")
                connection.execute("BEGIN IMMEDIATE")
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
            finally:
                connection.close()

    @staticmethod
    def _totals(connection: sqlite3.Connection, run_id: str | None = None) -> tuple[int, int]:
        values = (BUDGET_ID, run_id, run_id)
        row = connection.execute(
            "SELECT COALESCE(SUM(CASE WHEN status = 'settled' THEN actual_microusd ELSE 0 END), 0), "
            "COALESCE(SUM(CASE WHEN status = 'pending' THEN amount_microusd ELSE 0 END), 0) "
            "FROM evaluation_reservations WHERE budget_id = ? AND (? IS NULL OR run_id = ?)",
            values,
        ).fetchone()
        adjustment = connection.execute(
            "SELECT COALESCE(SUM(amount_microusd), 0) FROM evaluation_adjustments "
            "WHERE budget_id = ? AND (? IS NULL OR run_id = ?)",
            values,
        ).fetchone()[0]
        return int(row[0]) + int(adjustment), int(row[1])

    def snapshot(self) -> dict[str, int | str | None]:
        with self._transaction() as connection:
            spent, reserved = self._totals(connection)
            run_spent, run_reserved = self._totals(connection, self.run_id)
            reason = connection.execute(
                "SELECT blocked_reason FROM evaluation_budget WHERE id = ?", (BUDGET_ID,)
            ).fetchone()[0]
            attempts = connection.execute(
                "SELECT COUNT(*) FROM evaluation_reservations WHERE budget_id = ? AND status != 'released'",
                (BUDGET_ID,),
            ).fetchone()[0]
            adjustments = connection.execute(
                "SELECT COALESCE(SUM(amount_microusd), 0) FROM evaluation_adjustments WHERE budget_id = ?",
                (BUDGET_ID,),
            ).fetchone()[0]
        return {
            "budget_id": BUDGET_ID,
            "limit_microusd": self.limit_microusd,
            "spent_microusd": spent,
            "reserved_microusd": reserved,
            "remaining_microusd": max(0, self.limit_microusd - spent - reserved),
            "run_id": self.run_id,
            "run_limit_microusd": self.run_limit_microusd,
            "run_spent_microusd": run_spent,
            "run_reserved_microusd": run_reserved,
            "physical_attempts_reserved": attempts,
            "accounting_adjustments_microusd": adjustments,
            "blocked_reason": reason,
            "phase": self.phase,
        }

    @property
    def spent_microusd(self) -> int:
        return int(self.snapshot()["spent_microusd"])

    @property
    def reserved_microusd(self) -> int:
        return int(self.snapshot()["reserved_microusd"])

    @property
    def reached(self) -> bool:
        state = self.snapshot()
        return self._reached or bool(state["blocked_reason"]) or int(state["remaining_microusd"]) == 0

    def reserve(self, amount_microusd: int) -> SpendCapReservation:
        if isinstance(amount_microusd, bool) or not isinstance(amount_microusd, int) or amount_microusd < 1:
            raise ValueError("evaluation reservations must be positive integer microdollars")
        with self._transaction() as connection:
            blocked = connection.execute(
                "SELECT blocked_reason FROM evaluation_budget WHERE id = ?", (BUDGET_ID,)
            ).fetchone()[0]
            if blocked:
                raise EvaluationBudgetError("evaluation budget is blocked pending verified billing reconciliation")
            spent, reserved = self._totals(connection)
            run_spent, run_reserved = self._totals(connection, self.run_id)
            remaining = min(
                self.limit_microusd - spent - reserved,
                self.run_limit_microusd - run_spent - run_reserved,
            )
            if amount_microusd > remaining:
                self._reached = True
                raise PaidRunCapReached("the shared CloudBank evaluation budget cannot accommodate another call")
            cursor = connection.execute(
                "INSERT INTO evaluation_reservations "
                "(budget_id, run_id, amount_microusd, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
                (BUDGET_ID, self.run_id, amount_microusd, _now()),
            )
            return SpendCapReservation(token=int(cursor.lastrowid), amount_microusd=amount_microusd)

    def _reconcile(self, reservation: SpendCapReservation, actual_microusd: int | None) -> None:
        if actual_microusd is not None and (
            isinstance(actual_microusd, bool) or not isinstance(actual_microusd, int) or actual_microusd < 0
        ):
            raise ValueError("settled evaluation spend must be nonnegative integer microdollars")
        exceeded = False
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT amount_microusd, status FROM evaluation_reservations "
                "WHERE id = ? AND budget_id = ? AND run_id = ?",
                (reservation.token, BUDGET_ID, self.run_id),
            ).fetchone()
            if row != (reservation.amount_microusd, "pending"):
                raise EvaluationBudgetError("evaluation reservation is not pending in this run")
            exceeded = actual_microusd is not None and actual_microusd > reservation.amount_microusd
            if exceeded:
                # Preserve the real charge and disable all future runs. Never
                # roll back a known billable charge or erase the reservation.
                connection.execute(
                    "UPDATE evaluation_budget SET blocked_reason = ? WHERE id = ?",
                    ("a provider charge exceeded its conservative reservation", BUDGET_ID),
                )
            connection.execute(
                "UPDATE evaluation_reservations SET actual_microusd = ?, status = ?, reconciled_at = ? WHERE id = ?",
                (actual_microusd, "released" if actual_microusd is None else "settled", _now(), reservation.token),
            )
        if exceeded:
            raise EvaluationBudgetError("provider charge exceeded the evaluation reservation; further dispatch is blocked")

    def settle(self, reservation: SpendCapReservation, actual_microusd: int) -> None:
        self._reconcile(reservation, actual_microusd)

    def release(self, reservation: SpendCapReservation) -> None:
        self._reconcile(reservation, None)

    def adjust_upward(self, *, adjustment_id: str, amount_microusd: int, reason: str, evidence_sha256: str) -> None:
        """Record a verified pricing correction without rewriting a call receipt.

        Corrections only consume allowance. The stable adjustment ID makes an
        interrupted reconciliation safely repeatable, and the evidence hash
        binds it to a separate before/after pricing receipt. An operator pause
        blocks generation, not recording a known additional charge.
        """
        if isinstance(amount_microusd, bool) or not isinstance(amount_microusd, int) or amount_microusd < 1:
            raise ValueError("evaluation adjustments must be positive integer microdollars")
        if not adjustment_id.strip() or not reason.strip():
            raise ValueError("evaluation adjustments require an identity and reason")
        if len(evidence_sha256) != 64 or any(character not in "0123456789abcdef" for character in evidence_sha256):
            raise ValueError("evaluation adjustments require a SHA-256 evidence receipt")
        values = (BUDGET_ID, self.run_id, amount_microusd, reason, evidence_sha256)
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT budget_id, run_id, amount_microusd, reason, evidence_sha256 "
                "FROM evaluation_adjustments WHERE id = ?", (adjustment_id,),
            ).fetchone()
            if existing is not None:
                if existing != values:
                    raise EvaluationBudgetError("an existing accounting adjustment cannot be changed")
                return
            connection.execute(
                "INSERT INTO evaluation_adjustments VALUES (?, ?, ?, ?, ?, ?, ?)",
                (adjustment_id, *values, _now()),
            )
            spent, reserved = self._totals(connection)
            run_spent, run_reserved = self._totals(connection, self.run_id)
            if spent + reserved > self.limit_microusd or run_spent + run_reserved > self.run_limit_microusd:
                connection.execute(
                    "UPDATE evaluation_budget SET blocked_reason = ? WHERE id = ?",
                    ("verified accounting corrections exceed the authorized evaluation allowance", BUDGET_ID),
                )
