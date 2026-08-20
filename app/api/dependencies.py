"""Authentication dependencies shared by browser and future MCP routes."""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.models import User
from app.db.session import get_db
from app.core.config import Settings, get_settings


def current_user(
    request: Request, session: Session = Depends(get_db)
) -> Optional[User]:
    user_id = request.session.get("user_id")
    if not isinstance(user_id, str):
        return None
    user = session.get(User, user_id)
    if user is None or user.status != "active":
        request.session.clear()
        return None
    return user


def require_user(user: Optional[User] = Depends(current_user)) -> User:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "authentication_required", "message": "sign in to continue"},
        )
    return user


def require_verified_user(user: User = Depends(require_user)) -> User:
    if not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "email_verification_required",
                "message": "verify your email address to continue",
            },
        )
    return user


def require_same_origin(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> None:
    """Reject cross-origin browser mutations that carry a session cookie."""
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    fetch_site = (request.headers.get("sec-fetch-site") or "").lower()
    if fetch_site == "cross-site":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "cross_origin_request", "message": "request origin rejected"},
        )
    origin = (request.headers.get("origin") or "").rstrip("/")
    if not origin:
        if settings.environment in {"staging", "production"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "origin_required",
                    "message": "request origin is required",
                },
            )
        return
    expected = settings.public_base_url or str(request.base_url).rstrip("/")
    if origin != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "cross_origin_request", "message": "request origin rejected"},
        )
