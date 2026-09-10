"""Combined trial, emergency, and provider-usage accounting for LLM calls."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    EmergencyBudget,
    EmergencyUsageReservation,
    LLMUsageEvent,
    TrialGrant,
    TrialProgram,
    UsageReservation,
    utc_now,
)
from app.services.billing_lock import BILLING_LOCK, lock_billing_accounts
from app.services.emergency_budget import (
    release_emergency_budget,
    reserve_emergency_budget,
    settle_emergency_budget,
)
from app.services.trials import (
    release_trial_credit,
    reserve_trial_credit,
    settle_trial_credit,
)


@dataclass(frozen=True)
class CallReservation:
    amount_microusd: int
    trial_reservation_id: str | None = None
    emergency_reservation_id: str | None = None


def _lock_call_accounts(
    session: Session, reservation: CallReservation, *, event_user_id: str | None,
) -> None:
    # Resolve both sides before taking any reservation or budget lock. Normally
    # they reference the same account, but sorting all keys also protects callers
    # whose recorded usage has a separate account reference.
    identifiers = [event_user_id]
    for model, reservation_id in (
        (UsageReservation, reservation.trial_reservation_id),
        (EmergencyUsageReservation, reservation.emergency_reservation_id),
    ):
        if reservation_id:
            identifiers.append(session.scalar(select(model.user_id).where(model.id == reservation_id)))
    lock_billing_accounts(session, identifiers)


def reserve_llm_call(
    session: Session,
    *,
    amount_microusd: int,
    user_id: str | None,
    provider: str,
    route: str,
    model: str,
    request_kind: str,
    charge_trial: bool,
    charge_emergency: bool,
) -> CallReservation:
    if charge_trial and not user_id:
        raise ValueError("trial-funded calls require a user")

    def reserve() -> CallReservation:
        try:
            lock_billing_accounts(session, [user_id])
            trial = None
            emergency = None
            if charge_trial:
                trial = reserve_trial_credit(
                    session,
                    user_id or "",
                    amount_microusd=amount_microusd,
                    provider=provider,
                    model=model,
                    request_kind=request_kind,
                    commit=False,
                )
            if charge_emergency:
                emergency = reserve_emergency_budget(
                    session,
                    amount_microusd=amount_microusd,
                    user_id=user_id,
                    provider=provider,
                    route=route,
                    model=model,
                    request_kind=request_kind,
                    commit=False,
                )
            session.commit()
            return CallReservation(
                amount_microusd=amount_microusd,
                trial_reservation_id=trial.id if trial else None,
                emergency_reservation_id=emergency.id if emergency else None,
            )
        except Exception:
            session.rollback()
            raise

    if session.bind is not None and session.bind.dialect.name == "sqlite":
        with BILLING_LOCK:
            return reserve()
    return reserve()


def settle_llm_call(
    session: Session,
    reservation: CallReservation,
    *,
    actual_microusd: int,
    event: LLMUsageEvent,
) -> None:
    def settle() -> None:
        try:
            _lock_call_accounts(session, reservation, event_user_id=event.user_id)
            if reservation.trial_reservation_id:
                settle_trial_credit(
                    session,
                    reservation.trial_reservation_id,
                    actual_microusd=actual_microusd,
                    commit=False,
                )
            if reservation.emergency_reservation_id:
                settle_emergency_budget(
                    session,
                    reservation.emergency_reservation_id,
                    actual_microusd=actual_microusd,
                    commit=False,
                )
            session.add(event)
            session.commit()
        except Exception:
            session.rollback()
            raise

    if session.bind is not None and session.bind.dialect.name == "sqlite":
        with BILLING_LOCK:
            settle()
    else:
        settle()


def release_llm_call(
    session: Session,
    reservation: CallReservation,
    *,
    event: LLMUsageEvent | None = None,
) -> None:
    def release() -> None:
        try:
            _lock_call_accounts(session, reservation, event_user_id=event.user_id if event else None)
            if reservation.trial_reservation_id:
                release_trial_credit(
                    session, reservation.trial_reservation_id, commit=False
                )
            if reservation.emergency_reservation_id:
                release_emergency_budget(
                    session, reservation.emergency_reservation_id, commit=False
                )
            if event is not None:
                session.add(event)
            session.commit()
        except Exception:
            session.rollback()
            raise

    if session.bind is not None and session.bind.dialect.name == "sqlite":
        with BILLING_LOCK:
            release()
    else:
        release()


def record_llm_event(session: Session, event: LLMUsageEvent) -> None:
    session.add(event)
    session.commit()


def usage_event(
    *,
    request_id: str | None,
    user_id: str | None,
    provider: str,
    route: str,
    model: str,
    billing_source: str,
    request_kind: str,
    status: str,
    usage: dict[str, int] | None = None,
    cost_microusd: int = 0,
    latency_ms: int = 0,
    error_type: str | None = None,
) -> LLMUsageEvent:
    counts = usage or {}
    return LLMUsageEvent(
        request_id=(request_id or "")[:100] or None,
        user_id=user_id,
        provider=provider[:64],
        route=route[:120],
        model=model[:200],
        billing_source=billing_source[:40],
        request_kind=request_kind[:40],
        status=status[:20],
        input_tokens=max(0, int(counts.get("input_tokens", 0))),
        output_tokens=max(0, int(counts.get("output_tokens", 0))),
        cache_read_input_tokens=max(
            0, int(counts.get("cache_read_input_tokens", 0))
        ),
        cache_creation_input_tokens=max(
            0, int(counts.get("cache_creation_input_tokens", 0))
        ),
        cost_microusd=max(0, cost_microusd),
        latency_ms=max(0, latency_ms),
        error_type=(error_type or "")[:100] or None,
    )


def reconcile_stale_llm_reservations(
    session: Session, *, apply: bool = True,
) -> tuple[int, int]:
    """Conservatively charge expired reservations after a crash or worker loss.

    Once a provider request may have started, the database cannot prove that it
    was not billed. Charging the full conservative reservation keeps both hard
    budgets safe. A normal provider failure is released synchronously before it
    can become stale. Operator previews use ``apply=False`` and roll back all
    changes. Expiry never establishes that the provider waived the charge.
    """
    now = datetime.now(timezone.utc)

    def reconcile() -> tuple[int, int]:
        trial_count = 0
        emergency_count = 0
        try:
            # Discover a fixed candidate set before locking accounts. Refresh
            # those rows after the locks: a concurrent transfer may have changed
            # their pool, and a finalizer may have completed or removed them.
            trial_candidates = list(session.execute(select(
                UsageReservation.id, UsageReservation.user_id,
            ).where(UsageReservation.status == "pending", UsageReservation.expires_at <= now)))
            emergency_candidates = list(session.execute(select(
                EmergencyUsageReservation.id, EmergencyUsageReservation.user_id,
            ).where(EmergencyUsageReservation.status == "pending", EmergencyUsageReservation.expires_at <= now)))
            lock_billing_accounts(session, [
                user_id for _, user_id in trial_candidates + emergency_candidates
            ])
            trial_reservations = list(
                session.scalars(
                    select(UsageReservation)
                    .where(
                        UsageReservation.id.in_([identifier for identifier, _ in trial_candidates]),
                        UsageReservation.status == "pending",
                        UsageReservation.expires_at <= now,
                    )
                    .order_by(UsageReservation.id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            )
            # Lock every affected grant before retaining a shared program lock.
            # Otherwise a fresh reservation could hold a later grant while
            # waiting for a program already held by this multi-account sweep.
            grants = {item.user_id: item for item in session.scalars(
                select(TrialGrant).where(TrialGrant.user_id.in_(
                    {item.user_id for item in trial_reservations}
                )).order_by(TrialGrant.user_id).with_for_update()
                .execution_options(populate_existing=True)
            )}
            programs = {item.key: item for item in session.scalars(
                select(TrialProgram).where(TrialProgram.key.in_(
                    {item.program_key for item in trial_reservations}
                )).order_by(TrialProgram.key).with_for_update()
                .execution_options(populate_existing=True)
            )}
            for reservation in trial_reservations:
                grant = grants.get(reservation.user_id)
                program = programs.get(reservation.program_key)
                if (
                    grant is None or program is None
                    or grant.program_key != reservation.program_key
                    or grant.reserved_microusd < reservation.reserved_microusd
                ):
                    raise RuntimeError(
                        "cannot reconcile a stale trial reservation with missing or inconsistent accounting records"
                    )
                grant.reserved_microusd -= reservation.reserved_microusd
                grant.spent_microusd += reservation.reserved_microusd
                program.spent_microusd += reservation.reserved_microusd
                reservation.status = "expired_charged"
                reservation.actual_microusd = reservation.reserved_microusd
                reservation.finalized_at = utc_now()
                trial_count += 1

            emergency_reservations = list(
                session.scalars(
                    select(EmergencyUsageReservation)
                    .where(
                        EmergencyUsageReservation.id.in_([identifier for identifier, _ in emergency_candidates]),
                        EmergencyUsageReservation.status == "pending",
                        EmergencyUsageReservation.expires_at <= now,
                    )
                    .order_by(EmergencyUsageReservation.id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            )
            budgets = {item.key: item for item in session.scalars(
                select(EmergencyBudget).where(EmergencyBudget.key.in_(
                    {item.budget_key for item in emergency_reservations}
                )).order_by(EmergencyBudget.key).with_for_update()
                .execution_options(populate_existing=True)
            )}
            for reservation in emergency_reservations:
                budget = budgets.get(reservation.budget_key)
                if budget is None or budget.reserved_microusd < reservation.reserved_microusd:
                    raise RuntimeError(
                        "cannot reconcile a stale emergency reservation with a missing or inconsistent budget"
                    )
                budget.reserved_microusd -= reservation.reserved_microusd
                budget.spent_microusd += reservation.reserved_microusd
                reservation.status = "expired_charged"
                reservation.actual_microusd = reservation.reserved_microusd
                reservation.finalized_at = utc_now()
                emergency_count += 1
            session.commit() if apply else session.rollback()
            return trial_count, emergency_count
        except Exception:
            session.rollback()
            raise

    if session.bind is not None and session.bind.dialect.name == "sqlite":
        with BILLING_LOCK:
            return reconcile()
    return reconcile()
