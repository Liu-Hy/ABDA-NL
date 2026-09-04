"""Issue, authenticate, list, and revoke scoped MCP access tokens."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Collection

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import MCPAccessToken, User, utc_now


MCP_TOKEN_MARKER = "abda_mcp_"  # noqa: S105  (public token format marker)
MCP_TOKEN_PREFIX_LENGTH = 18
MCP_TOKEN_DEFAULT_DAYS = 90
MCP_TOKEN_MAX_DAYS = 365
MCP_TOKEN_MAX_ACTIVE = 10
MCP_TOKEN_LAST_USED_INTERVAL = timedelta(hours=1)

MCP_SCOPE_PROJECTS_READ = "projects:read"
MCP_SCOPE_PROJECTS_WRITE = "projects:write"
MCP_SCOPE_LLM_USE = "llm:use"
MCP_SCOPE_ORDER = (
    MCP_SCOPE_PROJECTS_READ,
    MCP_SCOPE_PROJECTS_WRITE,
    MCP_SCOPE_LLM_USE,
)
MCP_SCOPES = frozenset(MCP_SCOPE_ORDER)
MCP_DEFAULT_SCOPES = MCP_SCOPE_ORDER


class MCPTokenError(ValueError):
    pass


class MCPTokenLimitError(MCPTokenError):
    pass


class MCPTokenNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class MCPTokenPrincipal:
    token_id: str
    user_id: str
    scopes: tuple[str, ...]
    expires_at: datetime


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def normalize_mcp_scopes(scopes: Collection[str]) -> tuple[str, ...]:
    requested = {str(scope).strip() for scope in scopes}
    if not requested:
        raise MCPTokenError("select at least one MCP scope")
    invalid = sorted(requested - MCP_SCOPES)
    if invalid:
        raise MCPTokenError("unsupported MCP scope")
    return tuple(scope for scope in MCP_SCOPE_ORDER if scope in requested)


def mcp_token_scopes(record: MCPAccessToken) -> tuple[str, ...]:
    return normalize_mcp_scopes(record.scopes.split())


def mcp_token_is_active(
    record: MCPAccessToken, *, now: datetime | None = None
) -> bool:
    current = now or utc_now()
    return record.revoked_at is None and _as_utc(record.expires_at) > current


def _clean_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise MCPTokenError("token name cannot be empty")
    if len(cleaned) > 100:
        raise MCPTokenError("token name cannot exceed 100 characters")
    return cleaned


def _token_hash(token: str, pepper: str) -> str:
    if len(pepper) < 32:
        raise MCPTokenError("MCP token pepper is not configured safely")
    return hmac.new(
        pepper.encode("utf-8"),
        ("ABDA-NL MCP token v1\n" + token).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def create_mcp_token(
    session: Session,
    user: User,
    *,
    name: str,
    scopes: Collection[str] = MCP_DEFAULT_SCOPES,
    expires_in_days: int = MCP_TOKEN_DEFAULT_DAYS,
    pepper: str,
    now: datetime | None = None,
) -> tuple[MCPAccessToken, str]:
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
        raise MCPTokenError("a verified active account is required")
    if not 1 <= expires_in_days <= MCP_TOKEN_MAX_DAYS:
        raise MCPTokenError(
            f"token lifetime must be between 1 and {MCP_TOKEN_MAX_DAYS} days"
        )
    current = now or utc_now()
    active_count = session.scalar(
        select(func.count(MCPAccessToken.id)).where(
            MCPAccessToken.user_id == user.id,
            MCPAccessToken.revoked_at.is_(None),
            MCPAccessToken.expires_at > current,
        )
    )
    if int(active_count or 0) >= MCP_TOKEN_MAX_ACTIVE:
        raise MCPTokenLimitError(
            f"an account can have at most {MCP_TOKEN_MAX_ACTIVE} active MCP tokens"
        )

    raw_token = MCP_TOKEN_MARKER + secrets.token_urlsafe(32)
    record = MCPAccessToken(
        user_id=user.id,
        name=_clean_name(name),
        token_prefix=raw_token[:MCP_TOKEN_PREFIX_LENGTH],
        token_hash=_token_hash(raw_token, pepper),
        scopes=" ".join(normalize_mcp_scopes(scopes)),
        created_at=current,
        expires_at=current + timedelta(days=expires_in_days),
    )
    session.add(record)
    session.commit()
    return record, raw_token


def list_mcp_tokens(session: Session, user: User) -> list[MCPAccessToken]:
    return list(
        session.scalars(
            select(MCPAccessToken)
            .where(MCPAccessToken.user_id == user.id)
            .order_by(MCPAccessToken.created_at.desc())
            .limit(100)
        )
    )


def revoke_mcp_token(
    session: Session,
    user: User,
    token_id: str,
    *,
    now: datetime | None = None,
) -> MCPAccessToken:
    record = session.scalar(
        select(MCPAccessToken).where(
            MCPAccessToken.id == token_id,
            MCPAccessToken.user_id == user.id,
        )
    )
    if record is None:
        raise MCPTokenNotFoundError("MCP token not found")
    if record.revoked_at is None:
        record.revoked_at = now or utc_now()
        session.commit()
    return record


def authenticate_mcp_token(
    session: Session,
    raw_token: str,
    *,
    pepper: str,
    now: datetime | None = None,
) -> MCPTokenPrincipal | None:
    if (
        not raw_token.startswith(MCP_TOKEN_MARKER)
        or len(raw_token) < 40
        or len(raw_token) > 128
    ):
        return None
    candidate_hash = _token_hash(raw_token, pepper)
    row = session.execute(
        select(MCPAccessToken, User)
        .join(User, User.id == MCPAccessToken.user_id)
        .where(MCPAccessToken.token_hash == candidate_hash)
    ).one_or_none()
    if row is None:
        return None
    record, user = row
    if not hmac.compare_digest(record.token_hash, candidate_hash):
        return None
    current = now or utc_now()
    if (
        not mcp_token_is_active(record, now=current)
        or user.status != "active"
        or not user.email_verified
    ):
        return None

    last_used_at = record.last_used_at
    if last_used_at is None or _as_utc(last_used_at) <= current - MCP_TOKEN_LAST_USED_INTERVAL:
        record.last_used_at = current
        session.commit()

    return MCPTokenPrincipal(
        token_id=record.id,
        user_id=user.id,
        scopes=mcp_token_scopes(record),
        expires_at=_as_utc(record.expires_at),
    )
