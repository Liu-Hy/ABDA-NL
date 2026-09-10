"""Atomic free-trial activation and conservative usage reservations."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    NamedCreditEntitlement, TrialGrant, TrialProgram, UsageReservation, User, utc_now,
)
from app.services.billing_lock import BILLING_LOCK
from app.services.credit_policy import (
    NAMED_CREDIT_BUDGET_MICROUSD,
    NAMED_CREDIT_EMAILS,
    NAMED_CREDIT_GRANT_MICROUSD,
    NAMED_CREDIT_PROGRAM,
)


class TrialUnavailableError(RuntimeError):
    pass


class AutomaticCreditUnavailableError(TrialUnavailableError):
    """Expected allocation refusal that must not invalidate a verified sign-in."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


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


def _locked_program(session: Session, key: str = "global") -> TrialProgram | None:
    statement = (select(TrialProgram).where(TrialProgram.key == key).with_for_update()
                 .execution_options(populate_existing=True))
    return session.scalar(statement)


def initialize_named_credit(session: Session) -> None:
    """Seed the fixed pool and identity slots without granting account credit."""
    from sqlalchemy.dialects.postgresql import insert as postgres_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    insert = sqlite_insert if session.get_bind().dialect.name == "sqlite" else postgres_insert
    session.execute(insert(TrialProgram).values(
        key=NAMED_CREDIT_PROGRAM,
        enabled=True,
        max_users=len(NAMED_CREDIT_EMAILS),
        grant_microusd=NAMED_CREDIT_GRANT_MICROUSD,
        budget_microusd=NAMED_CREDIT_BUDGET_MICROUSD,
        activation_count=0,
        allocated_microusd=0,
        spent_microusd=0,
        updated_at=utc_now(),
    ).on_conflict_do_nothing(index_elements=["key"]))
    for email in NAMED_CREDIT_EMAILS:
        session.execute(insert(NamedCreditEntitlement).values(email=email)
                        .on_conflict_do_nothing(index_elements=["email"]))
    program = session.get(TrialProgram, NAMED_CREDIT_PROGRAM)
    if program is None or (
        program.max_users != len(NAMED_CREDIT_EMAILS)
        or program.grant_microusd != NAMED_CREDIT_GRANT_MICROUSD
        or program.budget_microusd != NAMED_CREDIT_BUDGET_MICROUSD
    ):
        raise TrialUnavailableError(
            "the named credit program does not match its fixed allocation "
            "(5 allocations of $50, $250 total); do not change ledger rows at boot. "
            "Use the controlled policy migration procedure in "
            "docs/operations/credit-policy-maintenance.md"
        )


def _locked_active_user(session: Session, user: User) -> User:
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
    return locked_user


def _named_entitlement(session: Session, user: User) -> NamedCreditEntitlement | None:
    # Once bound, the internal account remains the beneficiary even if its
    # verified address changes. The original address can never claim twice.
    entitlements = list(session.scalars(
        select(NamedCreditEntitlement)
        .where(NamedCreditEntitlement.email.in_(NAMED_CREDIT_EMAILS), or_(
            NamedCreditEntitlement.user_id == user.id,
            NamedCreditEntitlement.email == user.email.strip().lower(),
        ))
        .order_by(NamedCreditEntitlement.email)
        .with_for_update()
        .execution_options(populate_existing=True)
    ))
    bound = next((item for item in entitlements if item.user_id == user.id), None)
    entitlement = bound or next(iter(entitlements), None)
    if entitlement is not None and (
        entitlement.user_id not in {None, user.id}
        or (entitlement.user_id is None and entitlement.bound_at is not None)
    ):
        raise AutomaticCreditUnavailableError(
            "this named credit allocation is already bound to another account",
            code="named_credit_already_bound",
        )
    if entitlement is None and user.email.strip().lower() in NAMED_CREDIT_EMAILS:
        raise TrialUnavailableError("the named credit program is not configured")
    return entitlement


def _activate_named_credit(
    session: Session, user: User, *, automatic: bool = True,
) -> TrialBalance | None:
    if automatic:
        from app.core.config import get_settings

        # Hold named transfers during the first mixed-version rollout. Explicit
        # reconciliation runs after old writers are stopped and bypasses only
        # this gate, keeping all eligibility and accounting checks below.
        if not get_settings().named_credit_auto_activate:
            return None
    entitlement = _named_entitlement(session, user)
    if entitlement is None:
        return None

    # Settlement locks reservation, grant, then program. Use the same order
    # during transfer so pending requests cannot settle into the old pool.
    reservations = list(session.scalars(
        select(UsageReservation).where(UsageReservation.user_id == user.id)
        .order_by(UsageReservation.id).with_for_update()
        .execution_options(populate_existing=True)
    ))
    grant = session.scalar(
        select(TrialGrant).where(TrialGrant.user_id == user.id).with_for_update()
        .execution_options(populate_existing=True)
    )
    keys = {NAMED_CREDIT_PROGRAM}
    if grant is not None:
        keys.add(grant.program_key)
    programs = {item.key: item for item in session.scalars(
        select(TrialProgram).where(TrialProgram.key.in_(keys))
        .order_by(TrialProgram.key).with_for_update()
        .execution_options(populate_existing=True)
    )}
    program = programs.get(NAMED_CREDIT_PROGRAM)
    if program is None:
        raise TrialUnavailableError("the named credit program is not configured")
    old_amount = grant.granted_microusd if grant is not None else 0
    if old_amount > NAMED_CREDIT_GRANT_MICROUSD:
        raise TrialUnavailableError("existing credit exceeds the named allocation; review it before reconciliation")
    if grant is None:
        _claim_introductory_credit(session, user)
    if grant is not None and grant.program_key == NAMED_CREDIT_PROGRAM:
        added = NAMED_CREDIT_GRANT_MICROUSD - old_amount
        if added and not program.enabled:
            raise AutomaticCreditUnavailableError(
                "the named credit program is paused", code="named_credit_paused",
            )
        if program.allocated_microusd + added > program.budget_microusd:
            raise AutomaticCreditUnavailableError(
                "the named credit budget has been fully allocated", code="named_credit_exhausted",
            )
        grant.granted_microusd += added
        program.allocated_microusd += added
    else:
        if not program.enabled:
            raise AutomaticCreditUnavailableError(
                "the named credit program is paused", code="named_credit_paused",
            )
        if program.activation_count >= program.max_users:
            raise AutomaticCreditUnavailableError(
                "all named credit allocations have been claimed", code="named_credit_exhausted",
            )
        if program.allocated_microusd + NAMED_CREDIT_GRANT_MICROUSD > program.budget_microusd:
            raise AutomaticCreditUnavailableError(
                "the named credit budget has been fully allocated", code="named_credit_exhausted",
            )
        if grant is None:
            grant = TrialGrant(
                user_id=user.id, program_key=NAMED_CREDIT_PROGRAM,
                granted_microusd=NAMED_CREDIT_GRANT_MICROUSD,
                spent_microusd=0, reserved_microusd=0,
            )
            session.add(grant)
        else:
            previous = programs.get(grant.program_key)
            if previous is None or (
                previous.activation_count < 1
                or previous.allocated_microusd < old_amount
                or previous.spent_microusd < grant.spent_microusd
                or any(item.program_key != previous.key for item in reservations)
            ):
                raise UsageReservationError("named credit transfer found inconsistent accounting records")
            previous.activation_count -= 1
            previous.allocated_microusd -= old_amount
            previous.spent_microusd -= grant.spent_microusd
            program.spent_microusd += grant.spent_microusd
            grant.program_key = NAMED_CREDIT_PROGRAM
            grant.granted_microusd = NAMED_CREDIT_GRANT_MICROUSD
            for reservation in reservations:
                reservation.program_key = NAMED_CREDIT_PROGRAM
        program.activation_count += 1
        program.allocated_microusd += NAMED_CREDIT_GRANT_MICROUSD
    entitlement.user_id = user.id
    entitlement.bound_at = entitlement.bound_at or utc_now()
    session.flush()
    return _balance(grant)


def ensure_named_credit(session: Session, user: User) -> TrialBalance | None:
    """Idempotently allocate named credit on a verified sign-in."""
    def allocate() -> TrialBalance | None:
        try:
            active_user = _locked_active_user(session, user)
            if session.get(TrialGrant, active_user.id) is not None:
                from app.services.credit_eligibility import remember_granted_identity

                remember_granted_identity(session, active_user)
            result = _activate_named_credit(session, active_user)
            session.commit()
            return result
        except Exception:
            session.rollback()
            raise

    if session.get_bind().dialect.name == "sqlite":
        with BILLING_LOCK:
            return allocate()
    return allocate()


def reconcile_named_credit(session: Session, *, apply: bool = False) -> list[dict]:
    """Preview or apply all currently eligible named allocations atomically."""
    def reconcile() -> list[dict]:
        report = []
        try:
            # Acquire every affected account and reservation before holding a
            # pool lock across accounts. This matches per-call settlement and
            # avoids a batch waiting on a user whose request needs that pool.
            users = list(session.scalars(
                select(User).where(or_(
                    func.lower(User.email).in_(NAMED_CREDIT_EMAILS),
                    User.id.in_(select(NamedCreditEntitlement.user_id)
                                .where(NamedCreditEntitlement.user_id.is_not(None),
                                       NamedCreditEntitlement.email.in_(NAMED_CREDIT_EMAILS))),
                )).order_by(User.id).with_for_update()
                .execution_options(populate_existing=True)
            ))
            user_ids = [user.id for user in users]
            list(session.scalars(select(UsageReservation)
                 .where(UsageReservation.user_id.in_(user_ids))
                 .order_by(UsageReservation.id).with_for_update()
                 .execution_options(populate_existing=True)))
            list(session.scalars(select(TrialGrant).where(TrialGrant.user_id.in_(user_ids))
                 .order_by(TrialGrant.user_id).with_for_update()
                 .execution_options(populate_existing=True)))
            for email in NAMED_CREDIT_EMAILS:
                entitlement = session.get(NamedCreditEntitlement, email)
                if entitlement is None:
                    raise TrialUnavailableError("the named credit program is not configured")
                if entitlement.user_id is None and entitlement.bound_at is not None:
                    report.append({"email": email, "status": "retired_after_account_deletion"})
                    continue
                user = session.get(User, entitlement.user_id) if entitlement.user_id else session.scalar(
                    select(User).where(func.lower(User.email) == email)
                )
                if user is None or user.status != "active" or not user.email_verified:
                    status = "not_registered" if user is None else (
                        "inactive" if user.status != "active" else "unverified"
                    )
                    report.append({"email": email, "status": status})
                    continue
                previous = get_trial_balance(session, user.id)
                previous_grant = session.get(TrialGrant, user.id)
                previous_program = previous_grant.program_key if previous_grant else None
                current = _activate_named_credit(
                    session, _locked_active_user(session, user), automatic=False,
                )
                report.append({
                    "email": email, "user_id": user.id,
                    "status": "unchanged" if previous == current and previous_program == NAMED_CREDIT_PROGRAM else "allocated",
                    "before_granted_microusd": previous.granted_microusd,
                    "after_granted_microusd": current.granted_microusd,
                    "before_program": previous_program,
                    "after_program": NAMED_CREDIT_PROGRAM,
                    "spent_microusd": current.spent_microusd,
                    "reserved_microusd": current.reserved_microusd,
                })
            session.commit() if apply else session.rollback()
            return report
        except Exception:
            session.rollback()
            raise

    if session.get_bind().dialect.name == "sqlite":
        with BILLING_LOCK:
            return reconcile()
    return reconcile()


def _claim_introductory_credit(session: Session, user: User) -> None:
    from app.services.credit_eligibility import (
        IntroductoryCreditAlreadyUsedError, claim_credit_eligibility,
    )

    try:
        claim_credit_eligibility(session, user)
    except IntroductoryCreditAlreadyUsedError as exc:
        raise AutomaticCreditUnavailableError(
            str(exc), code="introductory_credit_already_used",
        ) from exc


def _activate_trial(session: Session, user: User) -> TrialBalance:
    user = _locked_active_user(session, user)
    named = _activate_named_credit(session, user)
    if named is not None:
        session.commit()
        return named
    existing = session.scalar(
        select(TrialGrant).where(TrialGrant.user_id == user.id).with_for_update()
    )
    if existing is not None:
        from app.services.credit_eligibility import remember_granted_identity

        remember_granted_identity(session, user)
        balance = _balance(existing)
        session.commit()
        return balance
    program = _locked_program(session)
    if program is None:
        raise TrialUnavailableError("the trial program is not configured")
    if not program.enabled:
        raise TrialUnavailableError("the trial program is paused")
    if program.activation_count >= program.max_users:
        raise TrialUnavailableError("all trial grants have been claimed")
    next_allocated = program.allocated_microusd + program.grant_microusd
    if next_allocated > program.budget_microusd:
        raise TrialUnavailableError("the trial budget has been fully allocated")
    _claim_introductory_credit(session, user)
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
    def activate() -> TrialBalance:
        try:
            return _activate_trial(session, user)
        except Exception:
            session.rollback()
            raise

    if session.bind is not None and session.bind.dialect.name == "sqlite":
        with BILLING_LOCK:
            return activate()
    return activate()


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
    grant = session.scalar(
        select(TrialGrant).where(TrialGrant.user_id == user_id).with_for_update()
        .execution_options(populate_existing=True)
    )
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
        .execution_options(populate_existing=True)
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
        .execution_options(populate_existing=True)
    )
    program = _locked_program(session, reservation.program_key)
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
        .execution_options(populate_existing=True)
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
