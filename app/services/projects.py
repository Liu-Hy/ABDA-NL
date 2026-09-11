"""Private project storage, optimistic updates, and revocable share links."""
from __future__ import annotations

import hashlib
import json
import secrets
import threading
from contextlib import nullcontext
from datetime import datetime, timezone

from sqlalchemy import delete, func, select, tuple_, update
from sqlalchemy.orm import Session

from app.db.models import Project, ScenarioSubmission, ShareLink, User, utc_now
from app.scenario.catalog import load_bundled_scenario
from app.scenario.loader import scenario_from_dict
from app.scenario.serialize import scenario_to_dict
from app.scenario.state import compute_state_bundle


class ProjectNotFoundError(LookupError):
    pass


class ProjectValidationError(ValueError):
    """A bounded project input error safe to disclose to the requesting owner."""


class ProjectVersionConflictError(RuntimeError):
    pass


class ShareLinkNotFoundError(LookupError):
    pass


class ProjectLimitError(RuntimeError):
    pass


class ShareLinkLimitError(RuntimeError):
    pass


MAX_ACTIVE_PROJECTS = 100
MAX_TOTAL_PROJECTS = 500
MAX_ACTIVE_SHARE_LINKS = 20
MAX_TOTAL_SHARE_LINKS = 500
MAX_PROJECT_SCENARIO_BYTES = 1_500_000
_SQLITE_PROJECT_LOCK = threading.RLock()


def _clean_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise ProjectValidationError("scenario name cannot be empty")
    if len(cleaned) > 120:
        raise ProjectValidationError("scenario name cannot exceed 120 characters")
    return cleaned


def _clean_description(description: str) -> str:
    cleaned = description.strip()
    if len(cleaned) > 4000:
        raise ProjectValidationError("scenario description cannot exceed 4000 characters")
    return cleaned


def normalize_project_scenario(raw: dict, source_scenario_id: str | None) -> dict:
    scenario = scenario_from_dict(raw)
    normalized = scenario_to_dict(scenario)
    encoded_size = len(
        json.dumps(normalized, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    if encoded_size > MAX_PROJECT_SCENARIO_BYTES:
        raise ProjectValidationError(
            f"scenario cannot exceed {MAX_PROJECT_SCENARIO_BYTES} encoded bytes"
        )
    project_corpus = list(normalized.get("corpus") or [])
    if source_scenario_id:
        source = load_bundled_scenario(source_scenario_id)
        if project_corpus != list(source.corpus or []):
            raise ProjectValidationError("scenario references must match its fixed built-in source scenario")
    elif project_corpus:
        raise ProjectValidationError("a scenario with bundled reference files must name a built-in source scenario")
    # Enforce portability at save time, including full bundled PDF text and
    # curated context, not just the user's newly attached documents.
    from app.scenario.portable import export_scenario
    export_scenario(normalized, source_scenario_id)
    # Project details always include the computed argumentation framework. Prove
    # that this exact scenario can be analyzed before any create or update is
    # committed, so a rejected request cannot leave an unreopenable project.
    compute_state_bundle(scenario)
    return normalized


def list_projects(session: Session, owner: User, *, archived: bool = False) -> list[Project]:
    return list(
        session.scalars(
            select(Project)
            .where(Project.owner_user_id == owner.id,
                   Project.archived_at.is_not(None) if archived else Project.archived_at.is_(None))
            .order_by(Project.updated_at.desc())
        )
    )


def project_statuses(session: Session, owner: User, projects: list[Project]) -> dict[str, dict]:
    """Bounded owner-only summaries, independent of the submission queue page."""
    ids = [project.id for project in projects]
    result = {project.id: {"active_share_count": 0, "submissions": []} for project in projects}
    if not ids:
        return result
    for project_id, count in session.execute(
        select(ShareLink.project_id, func.count(ShareLink.id))
        .where(ShareLink.project_id.in_(ids), ShareLink.revoked_at.is_(None),
               (ShareLink.expires_at.is_(None) | (ShareLink.expires_at > utc_now())))
        .group_by(ShareLink.project_id)
    ):
        result[project_id]["active_share_count"] = count
    for item in session.execute(
        select(ScenarioSubmission.id, ScenarioSubmission.project_id,
               ScenarioSubmission.project_version, ScenarioSubmission.status,
               ScenarioSubmission.reviewed_at)
        .where(ScenarioSubmission.project_id.in_(ids), ScenarioSubmission.submitter_id == owner.id)
        .order_by(ScenarioSubmission.project_version.desc())
    ):
        result[item.project_id]["submissions"].append({
            "id": item.id, "project_version": item.project_version,
            "status": item.status, "reviewed_at": item.reviewed_at,
        })
    for project in projects:
        if project.archived_at:
            result[project.id]["active_share_count"] = 0
    return result


def get_project(session: Session, owner: User, project_id: str) -> Project:
    project = session.scalar(
        select(Project).where(
            Project.id == project_id,
            Project.owner_user_id == owner.id,
            Project.archived_at.is_(None),
        )
    )
    if project is None:
        raise ProjectNotFoundError("scenario not found")
    return project


def _lock_active_owner(session: Session, owner_id: str) -> User:
    """Serialize project mutations with account suspension and refresh status."""
    owner = session.scalar(
        select(User)
        .where(User.id == owner_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if owner is None or owner.status != "active":
        session.rollback()
        raise ProjectNotFoundError("account not found")
    return owner


def _create_project(
    session: Session,
    owner: User,
    *,
    name: str,
    description: str,
    scenario: dict,
    source_scenario_id: str | None,
) -> Project:
    _lock_active_owner(session, owner.id)
    active_count = int(
        session.scalar(
            select(func.count(Project.id)).where(
                Project.owner_user_id == owner.id,
                Project.archived_at.is_(None),
            )
        )
        or 0
    )
    total_count = int(
        session.scalar(
            select(func.count(Project.id)).where(Project.owner_user_id == owner.id)
        )
        or 0
    )
    if active_count >= MAX_ACTIVE_PROJECTS:
        raise ProjectLimitError(
            f"an account can have at most {MAX_ACTIVE_PROJECTS} active private scenarios"
        )
    if total_count >= MAX_TOTAL_PROJECTS:
        raise ProjectLimitError(
            f"an account can have at most {MAX_TOTAL_PROJECTS} private scenario records"
        )
    source_id = (source_scenario_id or "").strip()[:100] or None
    project = Project(
        owner_user_id=owner.id,
        name=_clean_name(name),
        description=_clean_description(description),
        scenario_json=normalize_project_scenario(scenario, source_id),
        source_scenario_id=source_id,
    )
    session.add(project)
    session.commit()
    return project


def create_project(
    session: Session,
    owner: User,
    *,
    name: str,
    description: str,
    scenario: dict,
    source_scenario_id: str | None,
) -> Project:
    kwargs = {
        "name": name,
        "description": description,
        "scenario": scenario,
        "source_scenario_id": source_scenario_id,
    }
    if session.get_bind().dialect.name == "sqlite":
        with _SQLITE_PROJECT_LOCK:
            return _create_project(session, owner, **kwargs)
    return _create_project(session, owner, **kwargs)


def update_project(
    session: Session,
    owner: User,
    project_id: str,
    *,
    expected_version: int,
    name: str | None = None,
    description: str | None = None,
    scenario: dict | None = None,
) -> Project:
    if expected_version < 1:
        raise ProjectValidationError("expected_version must be positive")
    if name is None and description is None and scenario is None:
        raise ProjectValidationError("provide a name, description, or scenario to update")
    _lock_active_owner(session, owner.id)
    values: dict = {"version": expected_version + 1, "updated_at": utc_now()}
    if name is not None:
        values["name"] = _clean_name(name)
    if description is not None:
        values["description"] = _clean_description(description)
    if scenario is not None:
        current = get_project(session, owner, project_id)
        values["scenario_json"] = normalize_project_scenario(
            scenario, current.source_scenario_id
        )

    result = session.execute(
        update(Project)
        .where(
            Project.id == project_id,
            Project.owner_user_id == owner.id,
            Project.archived_at.is_(None),
            Project.version == expected_version,
        )
        .values(**values)
    )
    if result.rowcount != 1:
        session.rollback()
        existing = session.scalar(
            select(Project.id).where(
                Project.id == project_id,
                Project.owner_user_id == owner.id,
                Project.archived_at.is_(None),
            )
        )
        if existing is None:
            raise ProjectNotFoundError("scenario not found")
        raise ProjectVersionConflictError("scenario changed since it was loaded")
    session.commit()
    return get_project(session, owner, project_id)


def archive_project(
    session: Session, owner: User, project_id: str, *, expected_version: int
) -> None:
    _lock_active_owner(session, owner.id)
    result = session.execute(
        update(Project)
        .where(
            Project.id == project_id,
            Project.owner_user_id == owner.id,
            Project.archived_at.is_(None),
            Project.version == expected_version,
        )
        .values(
            archived_at=utc_now(),
            updated_at=utc_now(),
            version=expected_version + 1,
        )
    )
    if result.rowcount != 1:
        session.rollback()
        existing = session.scalar(
            select(Project.id).where(
                Project.id == project_id,
                Project.owner_user_id == owner.id,
                Project.archived_at.is_(None),
            )
        )
        if existing is None:
            raise ProjectNotFoundError("scenario not found")
        raise ProjectVersionConflictError("scenario changed since it was loaded")
    session.commit()


def restore_project(
    session: Session, owner: User, project_id: str, *, expected_version: int
) -> Project:
    """Restore privately. Old bearer links must never become usable again."""
    if expected_version < 1:
        raise ProjectValidationError("expected_version must be positive")
    with (_SQLITE_PROJECT_LOCK if session.get_bind().dialect.name == "sqlite" else nullcontext()):
        try:
            current_owner = _lock_active_owner(session, owner.id)
            if not current_owner.email_verified:
                raise ProjectNotFoundError("account not found")
            project = session.scalar(
                select(Project).where(Project.id == project_id, Project.owner_user_id == owner.id)
                .with_for_update().execution_options(populate_existing=True)
            )
            if project is None:
                raise ProjectNotFoundError("scenario not found")
            if project.version != expected_version or project.archived_at is None:
                raise ProjectVersionConflictError("scenario changed since it was loaded")
            active_count = session.scalar(select(func.count(Project.id)).where(
                Project.owner_user_id == owner.id, Project.archived_at.is_(None))) or 0
            if active_count >= MAX_ACTIVE_PROJECTS:
                raise ProjectLimitError(f"an account can have at most {MAX_ACTIVE_PROJECTS} active private scenarios")
            # A historical project must still be openable under the current
            # deterministic and portability limits before it consumes a slot.
            normalize_project_scenario(project.scenario_json, project.source_scenario_id)
            now = utc_now()
            changed = session.execute(update(Project).where(
                Project.id == project.id, Project.owner_user_id == owner.id,
                Project.archived_at.is_not(None), Project.version == expected_version,
            ).values(archived_at=None, version=expected_version + 1, updated_at=now))
            if changed.rowcount != 1:
                raise ProjectVersionConflictError("scenario changed since it was loaded")
            session.execute(update(ShareLink).where(
                ShareLink.project_id == project.id, ShareLink.revoked_at.is_(None),
            ).values(revoked_at=now))
            session.commit()
            session.refresh(project)
            return project
        except Exception:
            session.rollback()
            raise


def delete_archived_projects(
    session: Session, owner: User, *, targets: list[tuple[str, int]]
) -> list[str]:
    """Delete only confirmed archived project versions, atomically for all targets."""
    if not 1 <= len(targets) <= MAX_TOTAL_PROJECTS:
        raise ProjectValidationError(f"select between 1 and {MAX_TOTAL_PROJECTS} archived scenarios")
    if any(not isinstance(identifier, str) or not 1 <= len(identifier) <= 36
           or type(version) is not int or version < 1 for identifier, version in targets):
        raise ProjectValidationError("each scenario needs an id and a positive expected_version")
    expected = dict(targets)
    if len(expected) != len(targets):
        raise ProjectValidationError("each scenario must appear only once")

    with (_SQLITE_PROJECT_LOCK if session.get_bind().dialect.name == "sqlite" else nullcontext()):
        try:
            current_owner = _lock_active_owner(session, owner.id)
            if not current_owner.email_verified:
                raise ProjectNotFoundError("account not found")
            projects = list(session.execute(
                select(Project.id, Project.version, Project.archived_at)
                .where(Project.owner_user_id == current_owner.id, Project.id.in_(expected))
                .order_by(Project.id).with_for_update()
            ))
            if len(projects) != len(expected):
                raise ProjectNotFoundError("scenario not found")
            if any(item.archived_at is None or item.version != expected[item.id] for item in projects):
                raise ProjectVersionConflictError("archived scenarios changed since they were loaded")

            # Keep the complete confirmed id/version set in the write predicate.
            # A concurrent restore or later archive must never expand this set.
            eligible_owner = select(User.id).where(
                User.id == current_owner.id, User.status == "active", User.email_verified.is_(True),
            ).exists()
            changed = session.execute(delete(Project).where(
                Project.owner_user_id == current_owner.id,
                Project.archived_at.is_not(None),
                tuple_(Project.id, Project.version).in_(targets),
                eligible_owner,
            ))
            if changed.rowcount != len(expected):
                raise ProjectVersionConflictError("archived scenarios changed since they were loaded")
            # Existing foreign keys remove obsolete bearer links and detach
            # submission pointers. Consented snapshots and audit rows survive.
            session.commit()
            return list(expected)
        except Exception:
            session.rollback()
            raise


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _create_share_link(
    session: Session,
    owner: User,
    project_id: str,
    *,
    expires_at: datetime | None = None,
) -> tuple[ShareLink, str]:
    _lock_active_owner(session, owner.id)
    project = get_project(session, owner, project_id)
    session.scalar(
        select(Project).where(Project.id == project.id).with_for_update()
    )
    now = utc_now()
    active_count = int(
        session.scalar(
            select(func.count(ShareLink.id)).where(
                ShareLink.project_id == project.id,
                ShareLink.revoked_at.is_(None),
                (ShareLink.expires_at.is_(None) | (ShareLink.expires_at > now)),
            )
        )
        or 0
    )
    total_count = int(
        session.scalar(
            select(func.count(ShareLink.id)).where(ShareLink.project_id == project.id)
        )
        or 0
    )
    if active_count >= MAX_ACTIVE_SHARE_LINKS:
        raise ShareLinkLimitError(
            f"a scenario can have at most {MAX_ACTIVE_SHARE_LINKS} active share links"
        )
    if total_count >= MAX_TOTAL_SHARE_LINKS:
        raise ShareLinkLimitError(
            f"a scenario can have at most {MAX_TOTAL_SHARE_LINKS} share-link records"
        )
    if expires_at is not None:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= utc_now():
            raise ProjectValidationError("share-link expiration must be in the future")
    token = secrets.token_urlsafe(32)
    link = ShareLink(
        project_id=project.id,
        token_hash=_token_hash(token),
        permission="view",
        expires_at=expires_at,
    )
    session.add(link)
    session.commit()
    return link, token


def create_share_link(
    session: Session,
    owner: User,
    project_id: str,
    *,
    expires_at: datetime | None = None,
) -> tuple[ShareLink, str]:
    if session.get_bind().dialect.name == "sqlite":
        with _SQLITE_PROJECT_LOCK:
            return _create_share_link(
                session,
                owner,
                project_id,
                expires_at=expires_at,
            )
    return _create_share_link(
        session,
        owner,
        project_id,
        expires_at=expires_at,
    )


def list_share_links(session: Session, owner: User, project_id: str) -> list[ShareLink]:
    project = get_project(session, owner, project_id)
    return list(
        session.scalars(
            select(ShareLink)
            .where(ShareLink.project_id == project.id)
            .order_by(ShareLink.created_at.desc())
        )
    )


def revoke_share_link(
    session: Session, owner: User, project_id: str, share_link_id: str
) -> None:
    project = get_project(session, owner, project_id)
    link = session.scalar(
        select(ShareLink).where(
            ShareLink.id == share_link_id,
            ShareLink.project_id == project.id,
        )
    )
    if link is None:
        raise ShareLinkNotFoundError("share link not found")
    if link.revoked_at is None:
        link.revoked_at = utc_now()
        session.commit()


def resolve_share_link(session: Session, token: str) -> Project:
    if not token or len(token) > 256:
        raise ShareLinkNotFoundError("share link not found")
    link = session.scalar(select(ShareLink).where(ShareLink.token_hash == _token_hash(token)))
    if link is None or link.revoked_at is not None:
        raise ShareLinkNotFoundError("share link not found")
    now = utc_now()
    expires_at = link.expires_at
    if expires_at is not None:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now:
            raise ShareLinkNotFoundError("share link not found")
    project = session.scalar(
        select(Project)
        .join(User, User.id == Project.owner_user_id)
        .where(
            Project.id == link.project_id,
            Project.archived_at.is_(None),
            User.status == "active",
        )
    )
    if project is None:
        raise ShareLinkNotFoundError("share link not found")
    link.last_accessed_at = now
    session.commit()
    return project
