"""Operator-only access export and permanent account deletion workflows."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import re
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.db.models import (
    EmergencyUsageReservation,
    Identity,
    LLMUsageEvent,
    MCPAccessToken,
    Project,
    ShareLink,
    TrialGrant,
    UsageReservation,
    User,
    utc_now,
)
from app.services.accounts import IdentityError, normalize_email


_REQUEST_REFERENCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{2,63}\Z")
_DELETION_PENDING = "deletion_pending"


class PrivacyRequestError(RuntimeError):
    """Base error whose message is safe for operator output."""


class PrivacyAccountNotFoundError(PrivacyRequestError):
    pass


class PrivacyDeletionNotReadyError(PrivacyRequestError):
    pass


@dataclass(frozen=True)
class PrivacyAccountSummary:
    account_fingerprint: str
    status: str
    created_at: datetime
    identity_count: int
    active_project_count: int
    archived_project_count: int
    share_link_count: int
    mcp_token_count: int
    active_mcp_token_count: int
    trial_granted_microusd: int
    trial_spent_microusd: int
    trial_reserved_microusd: int
    trial_reservation_count: int
    pending_trial_reservation_count: int
    llm_usage_event_count: int
    emergency_reservation_count: int
    pending_emergency_reservation_count: int


@dataclass(frozen=True)
class PrivacyDeletionReceipt:
    request_reference: str
    deleted_at: datetime
    deleted_account_fingerprint: str
    deleted_identity_count: int
    deleted_project_count: int
    deleted_share_link_count: int
    deleted_mcp_token_count: int
    deleted_trial_reservation_count: int
    anonymized_llm_usage_event_count: int
    anonymized_emergency_reservation_count: int
    retained_trial_granted_microusd: int
    retained_trial_spent_microusd: int


def _normalized_email(email: str) -> str:
    try:
        return normalize_email(email)
    except IdentityError as exc:
        raise PrivacyRequestError("a valid verified account email is required") from exc


def _account_fingerprint(normalized_email: str) -> str:
    material = f"ABDA-NL privacy account v1\n{normalized_email}".encode()
    return hashlib.sha256(material).hexdigest()[:16]


def _validated_reference(request_reference: str) -> str:
    value = request_reference.strip()
    if not _REQUEST_REFERENCE.fullmatch(value):
        raise PrivacyRequestError(
            "the request reference must contain 3 to 64 letters, digits, dots, underscores, or hyphens"
        )
    return value


def validate_privacy_request_reference(request_reference: str) -> str:
    """Validate a content-free operator case reference."""
    return _validated_reference(request_reference)


def _find_user(session: Session, email: str, *, lock: bool = False) -> User:
    normalized = _normalized_email(email)
    statement = select(User).where(User.email == normalized)
    if lock:
        statement = statement.with_for_update()
    user = session.scalar(statement)
    if user is None:
        raise PrivacyAccountNotFoundError("no ABDA-NL account matches the verified address")
    return user


def _count(session: Session, statement) -> int:
    return int(session.scalar(statement) or 0)


def _summary_for_user(session: Session, user: User) -> PrivacyAccountSummary:
    project_ids = select(Project.id).where(Project.owner_user_id == user.id)
    grant = session.get(TrialGrant, user.id)
    now = utc_now()
    return PrivacyAccountSummary(
        account_fingerprint=_account_fingerprint(user.email),
        status=user.status,
        created_at=user.created_at,
        identity_count=_count(
            session,
            select(func.count(Identity.id)).where(Identity.user_id == user.id),
        ),
        active_project_count=_count(
            session,
            select(func.count(Project.id)).where(
                Project.owner_user_id == user.id,
                Project.archived_at.is_(None),
            ),
        ),
        archived_project_count=_count(
            session,
            select(func.count(Project.id)).where(
                Project.owner_user_id == user.id,
                Project.archived_at.is_not(None),
            ),
        ),
        share_link_count=_count(
            session,
            select(func.count(ShareLink.id)).where(ShareLink.project_id.in_(project_ids)),
        ),
        mcp_token_count=_count(
            session,
            select(func.count(MCPAccessToken.id)).where(MCPAccessToken.user_id == user.id),
        ),
        active_mcp_token_count=_count(
            session,
            select(func.count(MCPAccessToken.id)).where(
                MCPAccessToken.user_id == user.id,
                MCPAccessToken.revoked_at.is_(None),
                MCPAccessToken.expires_at > now,
            ),
        ),
        trial_granted_microusd=grant.granted_microusd if grant else 0,
        trial_spent_microusd=grant.spent_microusd if grant else 0,
        trial_reserved_microusd=grant.reserved_microusd if grant else 0,
        trial_reservation_count=_count(
            session,
            select(func.count(UsageReservation.id)).where(UsageReservation.user_id == user.id),
        ),
        pending_trial_reservation_count=_count(
            session,
            select(func.count(UsageReservation.id)).where(
                UsageReservation.user_id == user.id,
                UsageReservation.status == "pending",
            ),
        ),
        llm_usage_event_count=_count(
            session,
            select(func.count(LLMUsageEvent.id)).where(LLMUsageEvent.user_id == user.id),
        ),
        emergency_reservation_count=_count(
            session,
            select(func.count(EmergencyUsageReservation.id)).where(
                EmergencyUsageReservation.user_id == user.id
            ),
        ),
        pending_emergency_reservation_count=_count(
            session,
            select(func.count(EmergencyUsageReservation.id)).where(
                EmergencyUsageReservation.user_id == user.id,
                EmergencyUsageReservation.status == "pending",
            ),
        ),
    )


def inspect_privacy_account(session: Session, email: str) -> PrivacyAccountSummary:
    """Return content-free counts for a verified operator request."""
    return _summary_for_user(session, _find_user(session, email))


def _time(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def export_privacy_account(session: Session, email: str) -> dict[str, Any]:
    """Build a user access export without bearer-token hashes or API keys."""
    user = _find_user(session, email)
    identities = list(
        session.scalars(
            select(Identity).where(Identity.user_id == user.id).order_by(Identity.created_at)
        )
    )
    projects = list(
        session.scalars(
            select(Project).where(Project.owner_user_id == user.id).order_by(Project.created_at)
        )
    )
    project_ids = [project.id for project in projects]
    shares = (
        list(
            session.scalars(
                select(ShareLink)
                .where(ShareLink.project_id.in_(project_ids))
                .order_by(ShareLink.created_at)
            )
        )
        if project_ids
        else []
    )
    shares_by_project: dict[str, list[dict[str, Any]]] = {}
    for share in shares:
        shares_by_project.setdefault(share.project_id, []).append(
            {
                "id": share.id,
                "permission": share.permission,
                "created_at": _time(share.created_at),
                "expires_at": _time(share.expires_at),
                "revoked_at": _time(share.revoked_at),
                "last_accessed_at": _time(share.last_accessed_at),
            }
        )
    mcp_tokens = list(
        session.scalars(
            select(MCPAccessToken)
            .where(MCPAccessToken.user_id == user.id)
            .order_by(MCPAccessToken.created_at)
        )
    )
    trial_grant = session.get(TrialGrant, user.id)
    trial_reservations = list(
        session.scalars(
            select(UsageReservation)
            .where(UsageReservation.user_id == user.id)
            .order_by(UsageReservation.created_at)
        )
    )
    emergency_reservations = list(
        session.scalars(
            select(EmergencyUsageReservation)
            .where(EmergencyUsageReservation.user_id == user.id)
            .order_by(EmergencyUsageReservation.created_at)
        )
    )
    usage_events = list(
        session.scalars(
            select(LLMUsageEvent)
            .where(LLMUsageEvent.user_id == user.id)
            .order_by(LLMUsageEvent.created_at)
        )
    )
    return {
        "schema_version": 1,
        "exported_at": _time(utc_now()),
        "account": {
            "email": user.email,
            "email_verified": user.email_verified,
            "display_name": user.display_name,
            "status": user.status,
            "created_at": _time(user.created_at),
            "updated_at": _time(user.updated_at),
            "last_login_at": _time(user.last_login_at),
            "identities": [
                {
                    "issuer": identity.issuer,
                    "subject": identity.subject,
                    "provider_email": identity.provider_email,
                    "created_at": _time(identity.created_at),
                    "last_login_at": _time(identity.last_login_at),
                }
                for identity in identities
            ],
        },
        "projects": [
            {
                "id": project.id,
                "name": project.name,
                "description": project.description,
                "source_scenario_id": project.source_scenario_id,
                "scenario": project.scenario_json,
                "version": project.version,
                "created_at": _time(project.created_at),
                "updated_at": _time(project.updated_at),
                "archived_at": _time(project.archived_at),
                "share_links": shares_by_project.get(project.id, []),
            }
            for project in projects
        ],
        "mcp_tokens": [
            {
                "id": token.id,
                "name": token.name,
                "token_prefix": token.token_prefix,
                "scopes": token.scopes.split(),
                "created_at": _time(token.created_at),
                "expires_at": _time(token.expires_at),
                "last_used_at": _time(token.last_used_at),
                "revoked_at": _time(token.revoked_at),
            }
            for token in mcp_tokens
        ],
        "trial_grant": (
            {
                "program_key": trial_grant.program_key,
                "granted_microusd": trial_grant.granted_microusd,
                "spent_microusd": trial_grant.spent_microusd,
                "reserved_microusd": trial_grant.reserved_microusd,
                "activated_at": _time(trial_grant.activated_at),
            }
            if trial_grant
            else None
        ),
        "trial_reservations": [
            {
                "id": item.id,
                "program_key": item.program_key,
                "provider": item.provider,
                "model": item.model,
                "request_kind": item.request_kind,
                "reserved_microusd": item.reserved_microusd,
                "actual_microusd": item.actual_microusd,
                "status": item.status,
                "created_at": _time(item.created_at),
                "expires_at": _time(item.expires_at),
                "finalized_at": _time(item.finalized_at),
            }
            for item in trial_reservations
        ],
        "emergency_reservations": [
            {
                "id": item.id,
                "budget_key": item.budget_key,
                "provider": item.provider,
                "route": item.route,
                "model": item.model,
                "request_kind": item.request_kind,
                "reserved_microusd": item.reserved_microusd,
                "actual_microusd": item.actual_microusd,
                "status": item.status,
                "created_at": _time(item.created_at),
                "expires_at": _time(item.expires_at),
                "finalized_at": _time(item.finalized_at),
            }
            for item in emergency_reservations
        ],
        "llm_usage_events": [
            {
                "id": item.id,
                "request_id": item.request_id,
                "provider": item.provider,
                "route": item.route,
                "model": item.model,
                "billing_source": item.billing_source,
                "request_kind": item.request_kind,
                "status": item.status,
                "input_tokens": item.input_tokens,
                "output_tokens": item.output_tokens,
                "cache_read_input_tokens": item.cache_read_input_tokens,
                "cache_creation_input_tokens": item.cache_creation_input_tokens,
                "cost_microusd": item.cost_microusd,
                "latency_ms": item.latency_ms,
                "error_type": item.error_type,
                "created_at": _time(item.created_at),
            }
            for item in usage_events
        ],
    }


def prepare_privacy_deletion(
    session: Session,
    email: str,
    *,
    request_reference: str,
) -> PrivacyAccountSummary:
    """Suspend an account and revoke bearer access before permanent deletion."""
    _validated_reference(request_reference)
    try:
        user = _find_user(session, email, lock=True)
        if user.status not in {"active", _DELETION_PENDING}:
            raise PrivacyDeletionNotReadyError(
                "the account status does not permit deletion preparation"
            )
        now = utc_now()
        user.status = _DELETION_PENDING
        session.execute(
            update(MCPAccessToken)
            .where(
                MCPAccessToken.user_id == user.id,
                MCPAccessToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        project_ids = select(Project.id).where(Project.owner_user_id == user.id)
        session.execute(
            update(ShareLink)
            .where(
                ShareLink.project_id.in_(project_ids),
                ShareLink.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        session.commit()
        return _summary_for_user(session, user)
    except Exception:
        session.rollback()
        raise


def delete_privacy_account(
    session: Session,
    email: str,
    *,
    request_reference: str,
) -> PrivacyDeletionReceipt:
    """Permanently remove account content while retaining anonymous cost totals."""
    reference = _validated_reference(request_reference)
    try:
        candidate = _find_user(session, email)
        session.scalar(
            select(TrialGrant).where(TrialGrant.user_id == candidate.id).with_for_update()
        )
        user = session.scalar(select(User).where(User.id == candidate.id).with_for_update())
        if user is None:
            raise PrivacyAccountNotFoundError("no ABDA-NL account matches the verified address")
        summary = _summary_for_user(session, user)
        if summary.status != _DELETION_PENDING:
            raise PrivacyDeletionNotReadyError(
                "prepare deletion before permanently deleting the account"
            )
        if (
            summary.pending_trial_reservation_count
            or summary.pending_emergency_reservation_count
            or summary.trial_reserved_microusd
        ):
            raise PrivacyDeletionNotReadyError(
                "the account has unsettled model reservations; wait for settlement and inspect again"
            )

        session.execute(
            update(LLMUsageEvent).where(LLMUsageEvent.user_id == user.id).values(user_id=None)
        )
        session.execute(
            update(EmergencyUsageReservation)
            .where(EmergencyUsageReservation.user_id == user.id)
            .values(user_id=None)
        )
        project_ids = select(Project.id).where(Project.owner_user_id == user.id)
        session.execute(delete(ShareLink).where(ShareLink.project_id.in_(project_ids)))
        session.execute(delete(Project).where(Project.owner_user_id == user.id))
        session.execute(delete(MCPAccessToken).where(MCPAccessToken.user_id == user.id))
        session.execute(delete(UsageReservation).where(UsageReservation.user_id == user.id))
        session.execute(delete(TrialGrant).where(TrialGrant.user_id == user.id))
        session.execute(delete(Identity).where(Identity.user_id == user.id))
        session.execute(delete(User).where(User.id == user.id))
        session.commit()
        return PrivacyDeletionReceipt(
            request_reference=reference,
            deleted_at=utc_now(),
            deleted_account_fingerprint=summary.account_fingerprint,
            deleted_identity_count=summary.identity_count,
            deleted_project_count=(summary.active_project_count + summary.archived_project_count),
            deleted_share_link_count=summary.share_link_count,
            deleted_mcp_token_count=summary.mcp_token_count,
            deleted_trial_reservation_count=summary.trial_reservation_count,
            anonymized_llm_usage_event_count=summary.llm_usage_event_count,
            anonymized_emergency_reservation_count=summary.emergency_reservation_count,
            retained_trial_granted_microusd=summary.trial_granted_microusd,
            retained_trial_spent_microusd=summary.trial_spent_microusd,
        )
    except Exception:
        session.rollback()
        raise


def public_summary(summary: PrivacyAccountSummary) -> dict[str, Any]:
    """Convert a summary to JSON-ready values without adding account content."""
    value = asdict(summary)
    value["created_at"] = _time(summary.created_at)
    return value


def public_receipt(receipt: PrivacyDeletionReceipt) -> dict[str, Any]:
    """Convert a deletion receipt to JSON-ready, content-free evidence."""
    value = asdict(receipt)
    value["deleted_at"] = _time(receipt.deleted_at)
    return value
