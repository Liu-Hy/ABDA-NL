"""Verified OIDC identity linking and local development accounts."""
from __future__ import annotations

import threading
from datetime import datetime

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Identity, User, utc_now


class IdentityError(ValueError):
    def __init__(self, message: str, *, code: str = "identity_rejected") -> None:
        super().__init__(message)
        self.code = code


_SQLITE_IDENTITY_LOCK = threading.RLock()


def normalize_email(email: str) -> str:
    try:
        normalized = validate_email(
            email.strip(),
            check_deliverability=False,
        ).normalized.lower()
    except EmailNotValidError as exc:
        raise IdentityError(
            "a valid email address is required",
            code="identity_claims_invalid",
        ) from exc
    if len(normalized) > 320:
        raise IdentityError(
            "a valid email address is required",
            code="identity_claims_invalid",
        )
    return normalized


def _upsert_verified_identity_once(
    session: Session,
    *,
    issuer: str,
    subject: str,
    normalized_email: str,
    display_name: str | None = None,
) -> User:
    now = utc_now()

    identity = session.scalar(
        select(Identity).where(Identity.issuer == issuer, Identity.subject == subject)
    )
    if identity is not None:
        return _update_existing_identity(
            session,
            identity,
            normalized_email=normalized_email,
            display_name=display_name,
            now=now,
        )

    existing_email = session.scalar(
        select(User.id).where(User.email == normalized_email)
    )
    if existing_email is not None:
        # Under PostgreSQL READ COMMITTED, a concurrent first login can
        # commit between the identity lookup and this email lookup. Recheck
        # the stable identity before treating the address as a different
        # account. This does not link two distinct issuer and subject pairs.
        identity = session.scalar(
            select(Identity).where(
                Identity.issuer == issuer,
                Identity.subject == subject,
            )
        )
        if identity is not None and identity.user_id == existing_email:
            return _update_existing_identity(
                session,
                identity,
                normalized_email=normalized_email,
                display_name=display_name,
                now=now,
            )
        raise IdentityError(
            "this email is already linked to a different sign-in identity",
            code="account_link_required",
        )
    user = User(
        email=normalized_email,
        email_verified=True,
        display_name=(display_name or "").strip()[:200] or None,
        last_login_at=now,
    )
    session.add(user)
    session.flush()

    session.add(
        Identity(
            user_id=user.id,
            issuer=issuer,
            subject=subject,
            provider_email=normalized_email,
            last_login_at=now,
        )
    )
    session.commit()
    return user


def _update_existing_identity(
    session: Session,
    identity: Identity,
    *,
    normalized_email: str,
    display_name: str | None,
    now: datetime,
) -> User:
    user = session.get(User, identity.user_id)
    if user is None or user.status != "active":
        raise IdentityError(
            "this account is not active", code="account_unavailable"
        )
    if user.email != normalized_email:
        conflict = session.scalar(
            select(User.id).where(
                User.email == normalized_email,
                User.id != user.id,
            )
        )
        if conflict is not None:
            raise IdentityError(
                "the verified email is already assigned to another account",
                code="account_link_required",
            )
        user.email = normalized_email
    identity.provider_email = normalized_email
    identity.last_login_at = now
    user.email_verified = True
    user.last_login_at = now
    if display_name:
        user.display_name = display_name.strip()[:200]
    session.commit()
    return user


def _upsert_verified_identity_with_retry(
    session: Session,
    *,
    issuer: str,
    subject: str,
    normalized_email: str,
    display_name: str | None,
) -> User:
    kwargs = {
        "issuer": issuer,
        "subject": subject,
        "normalized_email": normalized_email,
        "display_name": display_name,
    }
    try:
        return _upsert_verified_identity_once(session, **kwargs)
    except IntegrityError:
        # Two browser callbacks for one first login can race on either the
        # unique email or the unique issuer and subject pair. After the
        # winning transaction commits, retry through the ordinary identity
        # checks so the duplicate resolves idempotently. A different identity
        # claiming the same address is still rejected by those checks.
        session.rollback()
    try:
        return _upsert_verified_identity_once(session, **kwargs)
    except IntegrityError as exc:
        session.rollback()
        raise IdentityError(
            "the sign-in identity changed concurrently; please try again",
            code="identity_retry_required",
        ) from exc


def upsert_verified_identity(
    session: Session,
    *,
    issuer: str,
    subject: str,
    email: str,
    email_verified: bool,
    display_name: str | None = None,
) -> User:
    """Resolve one verified external identity to a stable local user."""
    if not email_verified:
        raise IdentityError(
            "verify the email address with the login provider before continuing",
            code="email_verification_required",
        )
    issuer = issuer.strip().rstrip("/")
    subject = subject.strip()
    if not issuer or not subject:
        raise IdentityError(
            "the login provider did not return a stable identity",
            code="identity_claims_invalid",
        )
    normalized_email = normalize_email(email)
    kwargs = {
        "issuer": issuer,
        "subject": subject,
        "normalized_email": normalized_email,
        "display_name": display_name,
    }
    if session.get_bind().dialect.name == "sqlite":
        with _SQLITE_IDENTITY_LOCK:
            return _upsert_verified_identity_with_retry(session, **kwargs)
    return _upsert_verified_identity_with_retry(session, **kwargs)


def upsert_local_development_user(
    session: Session, *, email: str, display_name: str | None = None
) -> User:
    """Create a verified local account for explicitly non-production development."""
    normalized_email = normalize_email(email)
    subject = f"email:{normalized_email}"
    return upsert_verified_identity(
        session,
        issuer="urn:abda-nl:local-development",
        subject=subject,
        email=normalized_email,
        email_verified=True,
        display_name=display_name,
    )
