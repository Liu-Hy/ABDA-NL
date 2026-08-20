"""Atomic reservations against the project-paid emergency provider budget."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EmergencyBudget, EmergencyUsageReservation, utc_now
from app.services.billing_lock import BILLING_LOCK


class EmergencyBudgetUnavailableError(RuntimeError):
    pass


class EmergencyBudgetExceededError(RuntimeError):
    pass


class EmergencyReservationError(RuntimeError):
    pass


@dataclass(frozen=True)
class EmergencyBalance:
    enabled: bool
    hard_limit_microusd: int
    spent_microusd: int
    reserved_microusd: int
    available_microusd: int


def _balance(budget: EmergencyBudget) -> EmergencyBalance:
    return EmergencyBalance(
        enabled=budget.enabled,
        hard_limit_microusd=budget.hard_limit_microusd,
        spent_microusd=budget.spent_microusd,
        reserved_microusd=budget.reserved_microusd,
        available_microusd=(
            budget.hard_limit_microusd
            - budget.spent_microusd
            - budget.reserved_microusd
        ),
    )


def get_emergency_balance(
    session: Session, budget_key: str = "openrouter"
) -> EmergencyBalance:
    budget = session.get(EmergencyBudget, budget_key)
    if budget is None:
        raise EmergencyBudgetUnavailableError("the emergency budget is not configured")
    return _balance(budget)


def _locked_budget(session: Session, budget_key: str) -> EmergencyBudget | None:
    return session.scalar(
        select(EmergencyBudget)
        .where(EmergencyBudget.key == budget_key)
        .with_for_update()
    )


def _reserve(
    session: Session,
    *,
    amount_microusd: int,
    user_id: str | None,
    provider: str,
    route: str,
    model: str,
    request_kind: str,
    budget_key: str,
    commit: bool,
) -> EmergencyUsageReservation:
    if amount_microusd <= 0:
        raise ValueError("reservation amount must be positive")
    budget = _locked_budget(session, budget_key)
    if budget is None:
        raise EmergencyBudgetUnavailableError("the emergency budget is not configured")
    if not budget.enabled:
        raise EmergencyBudgetUnavailableError("the emergency provider is disabled")
    available = (
        budget.hard_limit_microusd
        - budget.spent_microusd
        - budget.reserved_microusd
    )
    if amount_microusd > available:
        raise EmergencyBudgetExceededError("the OpenRouter emergency budget is exhausted")
    reservation = EmergencyUsageReservation(
        budget_key=budget_key,
        user_id=user_id,
        provider=provider[:64],
        route=route[:120],
        model=model[:200],
        request_kind=request_kind[:40],
        reserved_microusd=amount_microusd,
    )
    budget.reserved_microusd += amount_microusd
    session.add(reservation)
    if commit:
        session.commit()
    else:
        session.flush()
    return reservation


def reserve_emergency_budget(
    session: Session,
    *,
    amount_microusd: int,
    user_id: str | None,
    provider: str,
    route: str,
    model: str,
    request_kind: str,
    budget_key: str = "openrouter",
    commit: bool = True,
) -> EmergencyUsageReservation:
    kwargs = {
        "amount_microusd": amount_microusd,
        "user_id": user_id,
        "provider": provider,
        "route": route,
        "model": model,
        "request_kind": request_kind,
        "budget_key": budget_key,
        "commit": commit,
    }
    if session.bind is not None and session.bind.dialect.name == "sqlite":
        with BILLING_LOCK:
            return _reserve(session, **kwargs)
    return _reserve(session, **kwargs)


def _pending(
    session: Session, reservation_id: str
) -> EmergencyUsageReservation:
    reservation = session.scalar(
        select(EmergencyUsageReservation)
        .where(EmergencyUsageReservation.id == reservation_id)
        .with_for_update()
    )
    if reservation is None:
        raise EmergencyReservationError("emergency usage reservation not found")
    if reservation.status != "pending":
        raise EmergencyReservationError("emergency usage reservation is already finalized")
    return reservation


def _settle(
    session: Session,
    reservation_id: str,
    *,
    actual_microusd: int,
    commit: bool,
) -> EmergencyBalance:
    if actual_microusd < 0:
        raise ValueError("actual usage cost cannot be negative")
    reservation = _pending(session, reservation_id)
    if actual_microusd > reservation.reserved_microusd:
        raise EmergencyReservationError(
            "actual emergency usage exceeded its conservative reservation"
        )
    budget = _locked_budget(session, reservation.budget_key)
    if budget is None:
        raise EmergencyReservationError("emergency budget not found")
    budget.reserved_microusd -= reservation.reserved_microusd
    budget.spent_microusd += actual_microusd
    reservation.actual_microusd = actual_microusd
    reservation.status = "settled"
    reservation.finalized_at = utc_now()
    if commit:
        session.commit()
    else:
        session.flush()
    return _balance(budget)


def settle_emergency_budget(
    session: Session,
    reservation_id: str,
    *,
    actual_microusd: int,
    commit: bool = True,
) -> EmergencyBalance:
    if session.bind is not None and session.bind.dialect.name == "sqlite":
        with BILLING_LOCK:
            return _settle(
                session,
                reservation_id,
                actual_microusd=actual_microusd,
                commit=commit,
            )
    return _settle(
        session,
        reservation_id,
        actual_microusd=actual_microusd,
        commit=commit,
    )


def _release(
    session: Session, reservation_id: str, *, commit: bool
) -> EmergencyBalance:
    reservation = _pending(session, reservation_id)
    budget = _locked_budget(session, reservation.budget_key)
    if budget is None:
        raise EmergencyReservationError("emergency budget not found")
    budget.reserved_microusd -= reservation.reserved_microusd
    reservation.actual_microusd = 0
    reservation.status = "released"
    reservation.finalized_at = utc_now()
    if commit:
        session.commit()
    else:
        session.flush()
    return _balance(budget)


def release_emergency_budget(
    session: Session, reservation_id: str, *, commit: bool = True
) -> EmergencyBalance:
    if session.bind is not None and session.bind.dialect.name == "sqlite":
        with BILLING_LOCK:
            return _release(session, reservation_id, commit=commit)
    return _release(session, reservation_id, commit=commit)
