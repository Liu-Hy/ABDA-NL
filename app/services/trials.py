"""Atomic free-trial activation and conservative usage reservations."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import TrialGrant, TrialProgram, UsageReservation, User, utc_now
from app.services.billing_lock import BILLING_LOCK


class TrialUnavailableError(RuntimeError):
    pass


class InsufficientTrialCreditError(RuntimeError):
    pass


class UsageReservationError(RuntimeError):
    pass


@dataclass(frozen=True)
class TrialBalance:
    active: bool
    granted_microusd: int
    spent_microusd: int
    reserved_microusd: int
    available_microusd: int


def _balance(grant: TrialGrant | None) -> TrialBalance:
    if grant is None:
        return TrialBalance(False, 0, 0, 0, 0)
    available = grant.granted_microusd - grant.spent_microusd - grant.reserved_microusd
    return TrialBalance(
        True,
        grant.granted_microusd,
        grant.spent_microusd,
        grant.reserved_microusd,
        available,
    )


def get_trial_balance(session: Session, user_id: str) -> TrialBalance:
    return _balance(session.get(TrialGrant, user_id))


def _locked_program(session: Session) -> TrialProgram | None:
    statement = select(TrialProgram).where(TrialProgram.key == "global").with_for_update()
    return session.scalar(statement)


def _activate_trial(session: Session, user: User) -> TrialBalance:
    locked_user = session.scalar(
        select(User)
        .where(User.id == user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        locked_user is None
        or locked_user.status != "active"
        or not locked_user.email_verified
    ):
        session.rollback()
        raise TrialUnavailableError("a verified active account is required")
    program = _locked_program(session)
    if program is None:
        raise TrialUnavailableError("the trial program is not configured")
    existing = session.get(TrialGrant, user.id)
    if existing is not None:
        return _balance(existing)
    if not program.enabled:
        raise TrialUnavailableError("the trial program is paused")
    if program.activation_count >= program.max_users:
        raise TrialUnavailableError("all trial grants have been claimed")
    next_allocated = program.allocated_microusd + program.grant_microusd
    if next_allocated > program.budget_microusd:
        raise TrialUnavailableError("the trial budget has been fully allocated")
    grant = TrialGrant(
        user_id=user.id,
        program_key=program.key,
        granted_microusd=program.grant_microusd,
    )
    session.add(grant)
    program.activation_count += 1
    program.allocated_microusd = next_allocated
    session.commit()
    return _balance(grant)


def activate_trial(session: Session, user: User) -> TrialBalance:
    if session.bind is not None and session.bind.dialect.name == "sqlite":
        with BILLING_LOCK:
            return _activate_trial(session, user)
    return _activate_trial(session, user)


def _reserve(
    session: Session,
    user_id: str,
    *,
    amount_microusd: int,
    provider: str,
    model: str,
    request_kind: str,
    commit: bool,
) -> UsageReservation:
    if amount_microusd <= 0:
        raise ValueError("reservation amount must be positive")
    grant = session.scalar(
        select(TrialGrant).where(TrialGrant.user_id == user_id).with_for_update()
    )
    locked_user = session.scalar(
        select(User)
        .where(User.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        locked_user is None
        or locked_user.status != "active"
        or not locked_user.email_verified
    ):
        raise TrialUnavailableError("a verified active account is required")
    if grant is None:
        raise InsufficientTrialCreditError("claim trial credit before using funded models")
    available = grant.granted_microusd - grant.spent_microusd - grant.reserved_microusd
    if amount_microusd > available:
        raise InsufficientTrialCreditError("the remaining trial credit is too low for this request")
    reservation = UsageReservation(
        user_id=user_id,
        program_key=grant.program_key,
        provider=provider[:64],
        model=model[:200],
        request_kind=request_kind[:40],
        reserved_microusd=amount_microusd,
    )
    grant.reserved_microusd += amount_microusd
    session.add(reservation)
    if commit:
        session.commit()
    else:
        session.flush()
    return reservation


def reserve_trial_credit(
    session: Session,
    user_id: str,
    *,
    amount_microusd: int,
    provider: str,
    model: str,
    request_kind: str,
    commit: bool = True,
) -> UsageReservation:
    if session.bind is not None and session.bind.dialect.name == "sqlite":
        with BILLING_LOCK:
            return _reserve(
                session,
                user_id,
                amount_microusd=amount_microusd,
                provider=provider,
                model=model,
                request_kind=request_kind,
                commit=commit,
            )
    return _reserve(
        session,
        user_id,
        amount_microusd=amount_microusd,
        provider=provider,
        model=model,
        request_kind=request_kind,
        commit=commit,
    )


def _get_pending_reservation(session: Session, reservation_id: str) -> UsageReservation:
    reservation = session.scalar(
        select(UsageReservation)
        .where(UsageReservation.id == reservation_id)
        .with_for_update()
    )
    if reservation is None:
        raise UsageReservationError("usage reservation not found")
    if reservation.status != "pending":
        raise UsageReservationError("usage reservation is already finalized")
    return reservation


def _settle(
    session: Session,
    reservation_id: str,
    actual_microusd: int,
    *,
    commit: bool,
) -> TrialBalance:
    if actual_microusd < 0:
        raise ValueError("actual usage cost cannot be negative")
    reservation = _get_pending_reservation(session, reservation_id)
    if actual_microusd > reservation.reserved_microusd:
        raise UsageReservationError("actual usage exceeded its conservative reservation")
    grant = session.scalar(
        select(TrialGrant)
        .where(TrialGrant.user_id == reservation.user_id)
        .with_for_update()
    )
    program = _locked_program(session)
    if grant is None or program is None:
        raise UsageReservationError("trial accounting records are incomplete")
    grant.reserved_microusd -= reservation.reserved_microusd
    grant.spent_microusd += actual_microusd
    program.spent_microusd += actual_microusd
    reservation.actual_microusd = actual_microusd
    reservation.status = "settled"
    reservation.finalized_at = utc_now()
    if commit:
        session.commit()
    else:
        session.flush()
    return _balance(grant)


def settle_trial_credit(
    session: Session,
    reservation_id: str,
    *,
    actual_microusd: int,
    commit: bool = True,
) -> TrialBalance:
    if session.bind is not None and session.bind.dialect.name == "sqlite":
        with BILLING_LOCK:
            return _settle(
                session, reservation_id, actual_microusd, commit=commit
            )
    return _settle(session, reservation_id, actual_microusd, commit=commit)


def _release(session: Session, reservation_id: str, *, commit: bool) -> TrialBalance:
    reservation = _get_pending_reservation(session, reservation_id)
    grant = session.scalar(
        select(TrialGrant)
        .where(TrialGrant.user_id == reservation.user_id)
        .with_for_update()
    )
    if grant is None:
        raise UsageReservationError("trial grant not found")
    grant.reserved_microusd -= reservation.reserved_microusd
    reservation.actual_microusd = 0
    reservation.status = "released"
    reservation.finalized_at = utc_now()
    if commit:
        session.commit()
    else:
        session.flush()
    return _balance(grant)


def release_trial_credit(
    session: Session, reservation_id: str, *, commit: bool = True
) -> TrialBalance:
    if session.bind is not None and session.bind.dialect.name == "sqlite":
        with BILLING_LOCK:
            return _release(session, reservation_id, commit=commit)
    return _release(session, reservation_id, commit=commit)
