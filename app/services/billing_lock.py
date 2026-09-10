"""Consistent account locks and local SQLite billing serialization."""
from __future__ import annotations

from collections.abc import Iterable
import threading

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import User


BILLING_LOCK = threading.RLock()


def lock_billing_accounts(session: Session, user_ids: Iterable[str | None]) -> None:
    """Lock accounts before their reservations, grants, programs, and budgets.

    Usage inserts also lock their referenced User through PostgreSQL foreign
    keys. Acquiring this lock last can deadlock with account deletion. Pending
    work must still settle for suspended accounts, so this is not an access check.
    """
    identifiers = {user_id for user_id in user_ids if user_id is not None}
    if identifiers:
        list(session.scalars(select(User).where(User.id.in_(identifiers))
             .order_by(User.id).with_for_update()
             .execution_options(populate_existing=True)))
