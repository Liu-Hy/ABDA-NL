"""Owner-consented snapshots and narrowly scoped example curation."""

from __future__ import annotations

from copy import deepcopy
from contextlib import nullcontext
import re
import threading
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import Project, ScenarioSubmission, User, utc_now
from app.scenario.catalog import ScenarioNotFoundError, load_bundled_scenario
from app.scenario.loader import scenario_from_dict
from app.services.projects import normalize_project_scenario

_SQLITE_LOCK = threading.RLock()
_PUBLIC_ID = re.compile(r"community_([a-f0-9]{32})\Z")
MAX_PENDING_PER_USER = 5
MAX_SUBMISSIONS_PER_USER = 50


class SubmissionError(ValueError):
    def __init__(self, message: str, *, status: int = 409):
        super().__init__(message)
        self.status = status


def is_scenario_admin(user: User | None, settings: Settings) -> bool:
    return bool(
        user
        and user.status == "active"
        and user.email_verified
        and user.email.lower() in settings.scenario_admin_emails
    )


def public_id(item: ScenarioSubmission) -> str:
    return "community_" + UUID(item.id).hex


def _active_owner(session: Session, owner_id: str) -> User:
    owner = session.scalar(
        select(User)
        .where(User.id == owner_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if owner is None or owner.status != "active" or not owner.email_verified:
        raise SubmissionError("This account is not available for scenario submissions.", status=404)
    return owner


def submit_scenario(
    session: Session,
    user: User,
    settings: Settings,
    *,
    project_id: str,
    expected_version: int,
    publish: bool,
) -> ScenarioSubmission:
    # PostgreSQL serializes on the owner row. SQLite is single-process only.
    with (_SQLITE_LOCK if session.get_bind().dialect.name == "sqlite" else nullcontext()):
        try:
            owner = _active_owner(session, user.id)
            admin = is_scenario_admin(owner, settings)
            if publish and not admin:
                raise SubmissionError(
                    "Only scenario administrators can publish examples.", status=403
                )
            project = session.scalar(
                select(Project)
                .where(
                    Project.id == project_id,
                    Project.owner_user_id == owner.id,
                    Project.archived_at.is_(None),
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if project is None:
                raise SubmissionError("Project not found.", status=404)
            if project.version != expected_version:
                raise SubmissionError("The project changed. Reopen it before submitting.")
            previous = session.scalar(
                select(ScenarioSubmission).where(
                    ScenarioSubmission.project_id == project.id,
                    ScenarioSubmission.project_version == expected_version,
                )
            )
            if previous:
                # A retry cannot duplicate a request or silently undo a review.
                return previous
            pending = (
                session.scalar(
                    select(func.count())
                    .select_from(ScenarioSubmission)
                    .where(
                        ScenarioSubmission.submitter_id == owner.id,
                        ScenarioSubmission.status == "pending",
                    )
                )
                or 0
            )
            total = (
                session.scalar(
                    select(func.count())
                    .select_from(ScenarioSubmission)
                    .where(ScenarioSubmission.submitter_id == owner.id)
                )
                or 0
            )
            if (
                not publish and pending >= MAX_PENDING_PER_USER
            ) or total >= MAX_SUBMISSIONS_PER_USER:
                raise SubmissionError(
                    "Submission limit reached. Withdraw a pending request or contact support.",
                    status=429,
                )
            raw = deepcopy(project.scenario_json)
            raw["title"] = project.name
            # The project description is private workspace metadata. Publish only
            # the scenario description shown in the snapshot preview.
            raw = normalize_project_scenario(raw, project.source_scenario_id)
            item = ScenarioSubmission(
                submitter_id=owner.id,
                project_id=project.id,
                project_version=project.version,
                title=project.name,
                description=raw.get("description", ""),
                scenario_json=raw,
                source_scenario_id=project.source_scenario_id,
                status="published" if publish else "pending",
                reviewer_id=owner.id if publish else None,
                reviewed_at=utc_now() if publish else None,
            )
            session.add(item)
            session.commit()
            session.refresh(item)
            return item
        except Exception:
            session.rollback()
            raise


def get_submission(
    session: Session, user: User, settings: Settings, submission_id: str
) -> ScenarioSubmission:
    statement = select(ScenarioSubmission).where(ScenarioSubmission.id == submission_id)
    if not is_scenario_admin(user, settings):
        statement = statement.where(ScenarioSubmission.submitter_id == user.id)
    item = session.scalar(statement)
    if item is None:
        raise SubmissionError("Submission not found.", status=404)
    return item


def review_submission(
    session: Session,
    user: User,
    settings: Settings,
    *,
    submission_id: str,
    expected_version: int,
    action: str,
    note: str,
) -> ScenarioSubmission:
    with (_SQLITE_LOCK if session.get_bind().dialect.name == "sqlite" else nullcontext()):
        try:
            item = get_submission(session, user, settings, submission_id)
            # Same lock order as project updates and account deletion preparation.
            _active_owner(session, item.submitter_id)
            actor = session.get(User, user.id, populate_existing=True)
            if actor is None or actor.status != "active" or not actor.email_verified:
                raise SubmissionError("This account is not available.", status=403)
            admin = is_scenario_admin(actor, settings)
            if action == "withdraw":
                allowed = item.submitter_id == user.id and item.status == "pending"
                target = "withdrawn"
            else:
                allowed = admin and (
                    (action in {"approve", "reject"} and item.status == "pending")
                    or (action == "unpublish" and item.status == "published")
                )
                target = {"approve": "published", "reject": "rejected", "unpublish": "withdrawn"}[
                    action
                ]
            if not allowed:
                raise SubmissionError(
                    "This action is not available for this submission.", status=403
                )
            if action in {"reject", "unpublish"} and not note.strip():
                raise SubmissionError("Add a short reason for the author.", status=400)
            result = session.execute(
                update(ScenarioSubmission)
                .where(
                    ScenarioSubmission.id == item.id,
                    ScenarioSubmission.status == item.status,
                    ScenarioSubmission.version == expected_version,
                )
                .values(
                    status=target,
                    version=expected_version + 1,
                    reviewer_id=user.id,
                    reviewed_at=utc_now(),
                    review_note=note.strip(),
                )
            )
            if result.rowcount != 1:
                raise SubmissionError(
                    "This submission changed. Refresh and review its latest status."
                )
            session.commit()
            session.refresh(item)
            return item
        except Exception:
            session.rollback()
            raise


def published_query():
    return (
        select(ScenarioSubmission)
        .join(User, User.id == ScenarioSubmission.submitter_id)
        .where(
            ScenarioSubmission.status == "published",
            User.status == "active",
            User.email_verified.is_(True),
        )
    )


def list_published_scenarios(session: Session) -> list[dict]:
    if not get_settings().community_catalog_enabled:
        return []
    rows = session.execute(
        published_query()
        .with_only_columns(
            ScenarioSubmission.id,
            ScenarioSubmission.title,
            ScenarioSubmission.description,
            ScenarioSubmission.source_scenario_id,
        )
        .order_by(ScenarioSubmission.created_at, ScenarioSubmission.id)
    )
    return [
        {
            "id": "community_" + UUID(row.id).hex,
            "title": row.title,
            "description": row.description,
            "category": "community",
            "source_scenario_id": row.source_scenario_id,
        }
        for row in rows
    ]


def resolve_public_scenario(session: Session, scenario_id: str):
    """Return (scenario, bundled corpus origin), never a private project."""
    if not scenario_id.startswith("community_"):
        return load_bundled_scenario(scenario_id), scenario_id
    match = _PUBLIC_ID.fullmatch(scenario_id)
    if not match or not get_settings().community_catalog_enabled:
        raise ScenarioNotFoundError("scenario not found")
    item = session.scalar(published_query().where(ScenarioSubmission.id == str(UUID(match[1]))))
    if item is None:
        raise ScenarioNotFoundError("scenario not found")
    return scenario_from_dict(deepcopy(item.scenario_json)), item.source_scenario_id
