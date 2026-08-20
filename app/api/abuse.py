"""HTTP-facing request limits with privacy-preserving subjects."""
from __future__ import annotations

import ipaddress
import logging

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.services.rate_limits import consume_rate_limit


log = logging.getLogger(__name__)


def _client_subject(request: Request, settings: Settings) -> str:
    """Return a trusted network subject for anonymous request limits."""
    host = request.client.host if request.client is not None else "unknown"
    if settings.proxy_mode == "azure-container-apps":
        forwarded_for = request.headers.get("x-forwarded-for") or ""
        candidate = forwarded_for.rsplit(",", maxsplit=1)[-1].strip()
        if candidate:
            try:
                host = ipaddress.ip_address(candidate).compressed
            except ValueError:
                # Azure appends the only trusted address on the right. Never
                # fall back to a client-supplied value elsewhere in the list.
                log.warning("forwarded_client_rejected proxy_mode=azure-container-apps")
    return f"client:{host}"


def enforce_rate_limit(
    request: Request,
    session: Session,
    settings: Settings,
    *,
    scope: str,
    limit: int,
    user_id: str | None = None,
    window_seconds: int = 60,
) -> None:
    if not settings.abuse_protection_enabled:
        return
    subject = f"user:{user_id}" if user_id else _client_subject(request, settings)
    result = consume_rate_limit(
        session,
        scope=scope,
        subject=subject,
        limit=limit,
        window_seconds=window_seconds,
        secret=settings.session_secret,
    )
    if result.allowed:
        return
    request_id = getattr(request.state, "request_id", None)
    log.warning(
        "request_rate_limited request_id=%s scope=%s retry_after_seconds=%d",
        request_id,
        scope,
        result.retry_after_seconds,
    )
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={
            "code": "rate_limit_exceeded",
            "message": "Too many requests. Please wait and try again.",
            "request_id": request_id,
        },
        headers={
            "Retry-After": str(result.retry_after_seconds),
            "X-RateLimit-Limit": str(result.limit),
            "X-RateLimit-Remaining": "0",
        },
    )
