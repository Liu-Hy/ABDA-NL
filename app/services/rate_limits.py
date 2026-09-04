"""Database-backed fixed-window rate limits for public abuse control."""
from __future__ import annotations

import hashlib
import hmac
import logging
import math
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.safe_logging import exception_diagnostic
from app.db.models import RateLimitBucket


log = logging.getLogger(__name__)
_SQLITE_RATE_LIMIT_LOCK = threading.RLock()
_RATE_LIMIT_CLEANUP_LOCK = threading.Lock()
_RATE_LIMIT_CLEANUP_INTERVAL_SECONDS = 60 * 60
_RATE_LIMIT_CLEANUP_RETRY_SECONDS = 5 * 60
_next_rate_limit_cleanup_monotonic = (
    time.monotonic() + _RATE_LIMIT_CLEANUP_INTERVAL_SECONDS
)


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int


def _utc(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _subject_digest(scope: str, subject: str, secret: str) -> str:
    if len(secret) < 32:
        raise ValueError("rate-limit secret must contain at least 32 characters")
    material = f"ABDA-NL rate limit v1\n{scope}\n{subject}".encode()
    return hmac.new(secret.encode(), material, hashlib.sha256).hexdigest()


def _consume(
    session: Session,
    *,
    scope: str,
    subject: str,
    limit: int,
    window_seconds: int,
    secret: str,
    now: datetime | None,
) -> RateLimitResult:
    if not scope or len(scope) > 40:
        raise ValueError("rate-limit scope must contain at most 40 characters")
    if not subject:
        raise ValueError("rate-limit subject cannot be empty")
    if limit < 1 or window_seconds < 1:
        raise ValueError("rate-limit values must be positive")

    current = _utc(now)
    epoch = int(current.timestamp())
    window_epoch = epoch - (epoch % window_seconds)
    window_start = datetime.fromtimestamp(window_epoch, tz=timezone.utc)
    expires_at = window_start + timedelta(seconds=window_seconds)
    digest = _subject_digest(scope, subject, secret)
    key = f"{scope}:{digest}:{window_epoch}"
    values = {
        "key": key,
        "scope": scope,
        "request_count": 1,
        "window_started_at": window_start,
        "expires_at": expires_at,
    }

    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        statement = postgresql_insert(RateLimitBucket).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=[RateLimitBucket.key],
            set_={"request_count": RateLimitBucket.request_count + 1},
        ).returning(RateLimitBucket.request_count)
        count = int(session.execute(statement).scalar_one())
    elif dialect == "sqlite":
        statement = sqlite_insert(RateLimitBucket).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=[RateLimitBucket.key],
            set_={"request_count": RateLimitBucket.request_count + 1},
        ).returning(RateLimitBucket.request_count)
        count = int(session.execute(statement).scalar_one())
    else:
        bucket = session.scalar(
            select(RateLimitBucket)
            .where(RateLimitBucket.key == key)
            .with_for_update()
        )
        if bucket is None:
            bucket = RateLimitBucket(**values)
            session.add(bucket)
            count = 1
        else:
            bucket.request_count += 1
            count = bucket.request_count
    session.commit()

    retry_after = max(1, math.ceil((expires_at - current).total_seconds()))
    return RateLimitResult(
        allowed=count <= limit,
        limit=limit,
        remaining=max(0, limit - count),
        retry_after_seconds=retry_after,
    )


def consume_rate_limit(
    session: Session,
    *,
    scope: str,
    subject: str,
    limit: int,
    window_seconds: int,
    secret: str,
    now: datetime | None = None,
) -> RateLimitResult:
    """Consume one slot without storing the raw account or network identifier."""
    if session.get_bind().dialect.name == "sqlite":
        with _SQLITE_RATE_LIMIT_LOCK:
            result = _consume(
                session,
                scope=scope,
                subject=subject,
                limit=limit,
                window_seconds=window_seconds,
                secret=secret,
                now=now,
            )
            delete_expired_rate_limits_if_due(session, now=now)
            return result
    result = _consume(
        session,
        scope=scope,
        subject=subject,
        limit=limit,
        window_seconds=window_seconds,
        secret=secret,
        now=now,
    )
    delete_expired_rate_limits_if_due(session, now=now)
    return result


def delete_expired_rate_limits(
    session: Session, *, now: datetime | None = None
) -> int:
    """Delete counters from completed windows."""
    result = session.execute(
        delete(RateLimitBucket).where(RateLimitBucket.expires_at <= _utc(now))
    )
    session.commit()
    return int(result.rowcount or 0)


def delete_expired_rate_limits_if_due(
    session: Session,
    *,
    now: datetime | None = None,
    monotonic_now: float | None = None,
) -> int | None:
    """Best-effort hourly cleanup after traffic, with a bounded failure retry."""
    global _next_rate_limit_cleanup_monotonic

    observed = time.monotonic() if monotonic_now is None else monotonic_now
    if observed < _next_rate_limit_cleanup_monotonic:
        return None
    if not _RATE_LIMIT_CLEANUP_LOCK.acquire(blocking=False):
        return None
    try:
        if observed < _next_rate_limit_cleanup_monotonic:
            return None
        _next_rate_limit_cleanup_monotonic = (
            observed + _RATE_LIMIT_CLEANUP_INTERVAL_SECONDS
        )
        try:
            deleted = delete_expired_rate_limits(session, now=now)
        except Exception as exc:
            _next_rate_limit_cleanup_monotonic = (
                observed + _RATE_LIMIT_CLEANUP_RETRY_SECONDS
            )
            try:
                session.rollback()
            except Exception as rollback_exc:
                rollback_diagnostic = exception_diagnostic(rollback_exc)
                log.error(
                    "rate_limit_cleanup_rollback_failed exception=%s location=%s",
                    rollback_diagnostic.kind,
                    rollback_diagnostic.location,
                )
            diagnostic = exception_diagnostic(exc)
            log.error(
                "rate_limit_cleanup_failed exception=%s location=%s",
                diagnostic.kind,
                diagnostic.location,
            )
            return None
        if deleted:
            log.info("rate_limit_cleanup_complete deleted=%d", deleted)
        return deleted
    finally:
        _RATE_LIMIT_CLEANUP_LOCK.release()
