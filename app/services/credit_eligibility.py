"""One introductory allocation per known verified email or sign-in identity.

HMAC markers remain for the credit program's lifetime. They are pseudonymous
eligibility records, not proof that different identities belong to one human.
The caller owns the transaction; a refused claim never increments a budget.
"""
from __future__ import annotations

import hashlib
import hmac
import json

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import (
    CreditEligibilityMarker, CreditEligibilityPolicy, Identity,
    NamedCreditEntitlement, TrialGrant, User, utc_now,
)
from app.services.billing_lock import lock_billing_accounts

POLICY_KEY = "introductory-credit-v1"


class CreditEligibilityError(RuntimeError):
    """Eligibility storage or key configuration is unavailable; fail closed."""


class IntroductoryCreditAlreadyUsedError(RuntimeError):
    """The verified identity has a prior introductory allocation."""


def _digest(kind: str, value: object) -> str:
    settings = get_settings()
    secret = getattr(settings, "credit_eligibility_pepper", settings.session_secret)
    if len(secret) < 32:
        raise CreditEligibilityError("the introductory-credit eligibility key is not configured")
    material = json.dumps([POLICY_KEY, kind, value], ensure_ascii=False, separators=(",", ":"))
    return hmac.new(secret.encode(), material.encode(), hashlib.sha256).hexdigest()


def _insert(session: Session):
    return sqlite_insert if session.get_bind().dialect.name == "sqlite" else postgres_insert


def _check_policy(session: Session) -> CreditEligibilityPolicy:
    policy = session.get(CreditEligibilityPolicy, POLICY_KEY)
    if policy is None:
        raise CreditEligibilityError("initialize introductory-credit eligibility before accepting grants")
    if not hmac.compare_digest(policy.key_fingerprint, _digest("key-check", POLICY_KEY)):
        raise CreditEligibilityError(
            "the introductory-credit eligibility key does not match retained markers; "
            "restore the original key before granting credit"
        )
    return policy


def _user_markers(session: Session, user: User) -> list[tuple[str, str]]:
    values = [("email", _digest("email", user.email.strip().lower()))]
    for identity in session.scalars(select(Identity).where(Identity.user_id == user.id)):
        values.append(("identity", _digest("identity", [identity.issuer, identity.subject])))
    return values


def _record(session: Session, *, kind: str, digest: str, user_id: str | None) -> None:
    session.execute(_insert(session)(CreditEligibilityMarker).values(
        digest=digest, kind=kind, user_id=user_id, claimed_at=utc_now(),
    ).on_conflict_do_nothing(index_elements=["digest"]))


def initialize_credit_eligibility(session: Session) -> None:
    """Seed extant grants and known named retirements without replacing history.

    A prior public deletion has no recoverable verified identity in the database.
    Such historical omissions cannot be reconstructed from an anonymous total.
    """
    if session.get(CreditEligibilityPolicy, POLICY_KEY) is None and session.scalar(
        select(CreditEligibilityMarker.digest).limit(1)
    ) is not None:
        raise CreditEligibilityError(
            "retained introductory-credit markers have no key policy; "
            "restore the original policy record before granting credit"
        )
    session.execute(_insert(session)(CreditEligibilityPolicy).values(
        key=POLICY_KEY, key_fingerprint=_digest("key-check", POLICY_KEY), seeded_at=utc_now(),
    ).on_conflict_do_nothing(index_elements=["key"]))
    _check_policy(session)
    grantee_ids = set(session.scalars(select(TrialGrant.user_id)))
    bound_entitlements = list(session.execute(select(
        NamedCreditEntitlement.email, NamedCreditEntitlement.user_id,
    ).where(NamedCreditEntitlement.bound_at.is_not(None))))
    # A marker insert takes both a unique-key lock and a User foreign-key lock.
    # Sign-in already holds User before recording changed identifiers. Match that
    # order here so startup seeding cannot hold the unique key while awaiting User.
    lock_billing_accounts(session, grantee_ids | {
        user_id for _, user_id in bound_entitlements if user_id is not None
    })
    # Refresh after waiting: deletion may have removed an account or retired a
    # named binding. New grants outside this snapshot record their own markers.
    for user in session.scalars(select(User).join(TrialGrant, TrialGrant.user_id == User.id)
                                .where(User.id.in_(grantee_ids))
                                .execution_options(populate_existing=True)):
        for kind, digest in _user_markers(session, user):
            _record(session, kind=kind, digest=digest, user_id=user.id)
    for entitlement in session.scalars(select(NamedCreditEntitlement).where(
        NamedCreditEntitlement.email.in_([email for email, _ in bound_entitlements]),
        NamedCreditEntitlement.bound_at.is_not(None),
    ).execution_options(populate_existing=True)):
        _record(session, kind="email", digest=_digest("email", entitlement.email),
                user_id=entitlement.user_id)


def claim_credit_eligibility(session: Session, user: User) -> None:
    """Claim current identifiers atomically, preserving existing-owner claims."""
    _check_policy(session)
    markers = _user_markers(session, user)
    # Upsert before the read serializes absent-row races under PostgreSQL too.
    # Lock ordering is stable across different identity combinations.
    for kind, digest in sorted(markers, key=lambda item: item[1]):
        _record(session, kind=kind, digest=digest, user_id=user.id)
        marker = session.scalar(select(CreditEligibilityMarker).where(
            CreditEligibilityMarker.digest == digest,
        ).with_for_update().execution_options(populate_existing=True))
        if marker is None:
            raise CreditEligibilityError("the introductory-credit eligibility record is missing")
        if marker.user_id != user.id:
            raise IntroductoryCreditAlreadyUsedError(
                "introductory credit has already been used for this verified identity; "
                "sign-in and self-funded model access remain available"
            )


def remember_granted_identity(session: Session, user: User) -> None:
    """Record new verified identifiers of an account that already received credit.

    Existing claims from a different account are never reassigned or cleared.
    This does not change the current account's grant or authentication result.
    """
    if session.get(TrialGrant, user.id) is None:
        return
    _check_policy(session)
    for kind, digest in _user_markers(session, user):
        _record(session, kind=kind, digest=digest, user_id=user.id)


def retained_marker_count(session: Session, user: User) -> int:
    """Count the account's pseudonymous records without disclosing their values."""
    return len(list(session.scalars(select(CreditEligibilityMarker.digest).where(
        CreditEligibilityMarker.user_id == user.id,
    ))))
