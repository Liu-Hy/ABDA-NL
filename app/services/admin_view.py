"""Voluntary browser-scoped reduction of scenario curator privileges.

The mode is independent of account identity, credit, and MCP tokens. Only mode
and authentication responses write its cookie, so a late ordinary response
cannot restore an older mode through Starlette's refreshed session cookie.
Requests already dispatched before switching can still complete.
"""

from __future__ import annotations

from itsdangerous import BadSignature, URLSafeSerializer
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import Settings
from app.db.models import User
from app.services.scenario_submissions import is_scenario_admin


def can_switch_admin_view(user: User | None, settings: Settings) -> bool:
    """Switch availability never grants scenario curator authority."""
    return is_scenario_admin(user, settings)


def admin_view_cookie_name(settings: Settings) -> str:
    # Preserve the hosted auth cookie's __Host- restriction (secure, host-only,
    # path=/), while permitting plain HTTP in development and tests.
    return f"{settings.session_cookie}_view_mode"


def _serializer(settings: Settings) -> URLSafeSerializer:
    return URLSafeSerializer(settings.session_secret, salt="abda-admin-view-v1")


def normal_user_view(request: Request, user: User | None, settings: Settings) -> bool:
    if user is None or not can_switch_admin_view(user, settings):
        return False
    cookie = request.cookies.get(admin_view_cookie_name(settings))
    if not cookie:
        return False
    try:
        payload = _serializer(settings).loads(cookie)
    except BadSignature:
        return False
    return isinstance(payload, dict) and payload == {"user_id": user.id}


def set_admin_view_cookie(response: Response, user: User, settings: Settings) -> None:
    # A browser-session cookie has no rolling expiry that could silently restore
    # curator access while the ordinary authentication session is still active.
    response.set_cookie(
        admin_view_cookie_name(settings),
        _serializer(settings).dumps({"user_id": user.id}),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_admin_view_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        admin_view_cookie_name(settings),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
