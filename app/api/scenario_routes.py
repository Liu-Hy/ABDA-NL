"""Consent, owner status, and administrator review for community examples."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, defer

from app.api.abuse import enforce_rate_limit
from app.api.dependencies import require_same_origin, require_verified_user
from app.core.config import Settings, get_settings
from app.db.models import ScenarioSubmission, User
from app.db.session import get_db
from app.services.scenario_submissions import (
    SubmissionError,
    get_submission,
    is_scenario_admin,
    public_id,
    review_submission,
    submit_scenario,
)

router = APIRouter(prefix="/api/scenario-submissions")


class SubmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(min_length=1, max_length=36)
    expected_version: int = Field(ge=1)
    publish: bool = False
    public_consent: Literal[True]

    @field_validator("public_consent", mode="before")
    @classmethod
    def explicit_consent(cls, value):
        if value is not True:
            raise ValueError("explicit public-sharing consent is required")
        return value


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    action: Literal["approve", "reject", "withdraw", "unpublish"]
    note: str = Field(default="", max_length=1000)


def require_catalog(settings: Settings = Depends(get_settings)) -> Settings:
    if not settings.community_catalog_enabled:
        raise HTTPException(
            status_code=503, detail="Scenario submissions are temporarily unavailable."
        )
    return settings


def _response(item: ScenarioSubmission, user: User, *, detail: bool = False) -> dict:
    result = {
        "id": item.id,
        "title": item.title,
        "description": item.description,
        "project_version": item.project_version,
        "status": item.status,
        "version": item.version,
        "review_note": item.review_note,
        "created_at": item.created_at,
        "reviewed_at": item.reviewed_at,
        "is_own": item.submitter_id == user.id,
        "public_scenario_id": public_id(item) if item.status == "published" else None,
    }
    if detail:
        result.update(scenario=item.scenario_json, source_scenario_id=item.source_scenario_id)
    return result


def _error(exc: SubmissionError) -> HTTPException:
    return HTTPException(
        status_code=exc.status, detail={"code": "submission_unavailable", "message": str(exc)}
    )


@router.get("")
def list_submissions(
    queue: bool = False,
    status: Literal["pending", "published", "rejected", "withdrawn"] | None = None,
    offset: int = Query(default=0, ge=0, le=100_000),
    user: User = Depends(require_verified_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(require_catalog),
) -> dict:
    if queue and not is_scenario_admin(user, settings):
        raise HTTPException(status_code=403, detail="Scenario administrator access required.")
    statement = select(ScenarioSubmission)
    if not queue:
        statement = statement.where(ScenarioSubmission.submitter_id == user.id)
    if status:
        statement = statement.where(ScenarioSubmission.status == status)
    rows = list(
        session.scalars(
            statement.options(defer(ScenarioSubmission.scenario_json))
            .order_by(ScenarioSubmission.created_at.desc(), ScenarioSubmission.id)
            .offset(offset)
            .limit(51)
        )
    )
    return {
        "submissions": [_response(item, user) for item in rows[:50]],
        "has_more": len(rows) > 50,
    }


@router.get("/{submission_id}")
def read_submission(
    submission_id: str,
    user: User = Depends(require_verified_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(require_catalog),
) -> dict:
    try:
        return _response(get_submission(session, user, settings, submission_id), user, detail=True)
    except SubmissionError as exc:
        raise _error(exc) from exc


@router.post("", status_code=201, dependencies=[Depends(require_same_origin)])
def create_submission(
    payload: SubmissionRequest,
    request: Request,
    user: User = Depends(require_verified_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(require_catalog),
) -> dict:
    enforce_rate_limit(
        request, session, settings, scope="scenario_submission", limit=10, user_id=user.id
    )
    try:
        item = submit_scenario(
            session,
            user,
            settings,
            project_id=payload.project_id,
            expected_version=payload.expected_version,
            publish=payload.publish,
        )
        return _response(item, user)
    except SubmissionError as exc:
        raise _error(exc) from exc


@router.post("/{submission_id}/review", dependencies=[Depends(require_same_origin)])
def decide_submission(
    submission_id: str,
    payload: ReviewRequest,
    request: Request,
    user: User = Depends(require_verified_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(require_catalog),
) -> dict:
    # Safety actions remain available even after submission quota exhaustion.
    if payload.action in {"approve", "reject"}:
        enforce_rate_limit(
            request, session, settings, scope="scenario_review", limit=60, user_id=user.id
        )
    try:
        item = review_submission(
            session,
            user,
            settings,
            submission_id=submission_id,
            expected_version=payload.expected_version,
            action=payload.action,
            note=payload.note,
        )
        return _response(item, user)
    except SubmissionError as exc:
        raise _error(exc) from exc
