"""Private project storage, optimistic updates, and revocable share links."""
from __future__ import annotations

import hashlib
import json
import secrets
import threading
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.db.models import Project, ShareLink, User, utc_now
from app.scenario.catalog import load_bundled_scenario
from app.scenario.loader import scenario_from_dict
from app.scenario.serialize import scenario_to_dict


class ProjectNotFoundError(LookupError):
    pass


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
        raise ValueError("project name cannot be empty")
    if len(cleaned) > 120:
        raise ValueError("project name cannot exceed 120 characters")
    return cleaned


def _clean_description(description: str) -> str:
    cleaned = description.strip()
    if len(cleaned) > 4000:
        raise ValueError("project description cannot exceed 4000 characters")
    return cleaned


def _normalize_scenario(raw: dict, source_scenario_id: str | None) -> dict:
    normalized = scenario_to_dict(scenario_from_dict(raw))
    encoded_size = len(
        json.dumps(normalized, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    if encoded_size > MAX_PROJECT_SCENARIO_BYTES:
        raise ValueError(
            f"project scenario cannot exceed {MAX_PROJECT_SCENARIO_BYTES} encoded bytes"
        )
    project_corpus = list(normalized.get("corpus") or [])
    if source_scenario_id:
        source = load_bundled_scenario(source_scenario_id)
        if project_corpus != list(source.corpus or []):
            raise ValueError("project corpus must match its immutable source example")
    elif project_corpus:
        raise ValueError("a project with corpus files must name a bundled source example")
    return normalized


def list_projects(session: Session, owner: User) -> list[Project]:
    return list(
        session.scalars(
            select(Project)
            .where(Project.owner_user_id == owner.id, Project.archived_at.is_(None))
            .order_by(Project.updated_at.desc())
        )
    )


def get_project(session: Session, owner: User, project_id: str) -> Project:
    project = session.scalar(
        select(Project).where(
            Project.id == project_id,
            Project.owner_user_id == owner.id,
            Project.archived_at.is_(None),
        )
    )
    if project is None:
        raise ProjectNotFoundError("project not found")
    return project


def _create_project(
    session: Session,
    owner: User,
    *,
    name: str,
    description: str,
    scenario: dict,
    source_scenario_id: str | None,
) -> Project:
    locked_owner = session.scalar(
        select(User).where(User.id == owner.id).with_for_update()
    )
    if locked_owner is None or locked_owner.status != "active":
        raise ProjectNotFoundError("account not found")
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
            f"an account can have at most {MAX_ACTIVE_PROJECTS} active projects"
        )
    if total_count >= MAX_TOTAL_PROJECTS:
        raise ProjectLimitError(
            f"an account can have at most {MAX_TOTAL_PROJECTS} project records"
        )
    source_id = (source_scenario_id or "").strip()[:100] or None
    project = Project(
        owner_user_id=owner.id,
        name=_clean_name(name),
        description=_clean_description(description),
        scenario_json=_normalize_scenario(scenario, source_id),
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
        raise ValueError("expected_version must be positive")
    values: dict = {"version": expected_version + 1, "updated_at": utc_now()}
    if name is not None:
        values["name"] = _clean_name(name)
    if description is not None:
        values["description"] = _clean_description(description)
    if scenario is not None:
        current = get_project(session, owner, project_id)
        values["scenario_json"] = _normalize_scenario(
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
            raise ProjectNotFoundError("project not found")
        raise ProjectVersionConflictError("project changed since it was loaded")
    session.commit()
    return get_project(session, owner, project_id)


def archive_project(
    session: Session, owner: User, project_id: str, *, expected_version: int
) -> None:
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
            raise ProjectNotFoundError("project not found")
        raise ProjectVersionConflictError("project changed since it was loaded")
    session.commit()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _create_share_link(
    session: Session,
    owner: User,
    project_id: str,
    *,
    expires_at: datetime | None = None,
) -> tuple[ShareLink, str]:
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
            f"a project can have at most {MAX_ACTIVE_SHARE_LINKS} active share links"
        )
    if total_count >= MAX_TOTAL_SHARE_LINKS:
        raise ShareLinkLimitError(
            f"a project can have at most {MAX_TOTAL_SHARE_LINKS} share-link records"
        )
    if expires_at is not None:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= utc_now():
            raise ValueError("share-link expiration must be in the future")
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
    project = session.get(Project, link.project_id)
    if project is None or project.archived_at is not None:
        raise ShareLinkNotFoundError("share link not found")
    link.last_accessed_at = now
    session.commit()
    return project
