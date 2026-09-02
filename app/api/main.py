"""FastAPI backend for ABDA-NL.

Endpoints:
  GET  /scenarios            -- list scenario ids / titles / descriptions
  GET  /scenarios/{id}       -- baseline bundled state (zero ops applied)
  POST /state                -- apply diff_ops against a baseline, return bundled state
  POST /chat                 -- corpus-grounded chat (LLM mode only)
  POST /propose              -- natural-language rule authoring (LLM mode only)
  POST /scenarios            -- save a modified scenario

State bundle shape (returned by both GET /scenarios/{id} and POST /state):
  {
    "scenario": {...mirror of scenario.yaml shape...},
    "af": {arguments, attacks, labels_by_proposition}
  }
"""
from __future__ import annotations

import logging
import os
import secrets
import time
from contextlib import asynccontextmanager
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

log = logging.getLogger(__name__)

from app.abda_bridge import init_engine
from app.api.abuse import enforce_rate_limit
from app.api.errors import register_exception_handlers
from app.api.dependencies import current_user, require_same_origin, require_verified_user
from app.api.account_models import (
    ProjectChatRequest,
    ProjectProposeRequest,
    ProjectWorkingStateRequest,
)
from app.api.llm_access import (
    HANDLED_LLM_ERRORS,
    build_llm_config,
    llm_http_exception,
    select_request_llm_client,
)
from app.api.models import (
    ChatRequest,
    ChatResponse,
    ChatUsage,
    ConfigResponse,
    ProposeRequest,
    ProposeResponse,
    SaveScenarioRequest,
    SaveScenarioResponse,
    ScenarioListItem,
    ScenarioListResponse,
    StateRequest,
    StateResponse,
)
from app.api.middleware import RequestBodyLimitMiddleware
from app.db.models import (
    EmergencyBudget,
    EmergencyUsageReservation,
    LLMUsageEvent,
    TrialGrant,
    TrialProgram,
    UsageReservation,
    User,
)
from app.db.session import get_db, get_engine
from app.observability import REQUEST_METRICS


def _read_llm_flag() -> bool:
    return os.getenv("ABDA_ENABLE_LLM", "0").strip().lower() in ("1", "true", "yes", "on")


ENABLE_LLM = _read_llm_flag()


def _preflight_llm_config(enable_llm: bool) -> None:
    """Validate that the active backend's prerequisites are satisfied."""
    from app.core.config import get_settings

    settings = get_settings()
    if settings.environment in {"staging", "production"} and not enable_llm:
        raise RuntimeError("staging and production require ABDA_ENABLE_LLM=1")
    if not enable_llm:
        return
    from app.llm import resolve_backend
    from app.llm.catalog import load_model_catalog
    from app.llm.client import foundry_credentials, resolve_claude_provider
    if settings.environment in {"staging", "production"}:
        if not settings.llm_allow_byok:
            raise RuntimeError("the public service must preserve registered-user BYOK")
        if (
            settings.environment == "production"
            and not settings.openrouter_failover_enabled
        ):
            raise RuntimeError("the public service requires OpenRouter outage failover")
        catalog = load_model_catalog()
        profile = catalog.profiles.get(settings.llm_default_profile)
        if profile is None or not profile.public_ready:
            raise RuntimeError(
                "the public default model profile must pass the quality gate"
            )
        route = catalog.routes[profile.primary_route]
        if route.provider != "azure-foundry":
            raise RuntimeError("the public funded route must use Azure Foundry")
        if route.adapter == "anthropic":
            api_key, auth_token, _ = foundry_credentials()
            if not (api_key or auth_token):
                raise RuntimeError("the public Foundry route requires Azure credentials")
        else:
            azure_key = (
                os.getenv("AZURE_OPENAI_API_KEY")
                or os.getenv("AZURE_ANTHROPIC_API_KEY")
                or ""
            ).strip()
            azure_endpoint = (
                os.getenv("AZURE_OPENAI_ENDPOINT")
                or os.getenv("ANTHROPIC_FOUNDRY_PROJECT_ENDPOINT")
                or ""
            ).strip()
            if not azure_key or not azure_endpoint:
                raise RuntimeError(
                    "the public Foundry route requires an Azure key and endpoint"
                )
        if settings.openrouter_failover_enabled and not (
            os.getenv("OPENROUTER_API_KEY") or ""
        ).strip():
            raise RuntimeError(
                "OpenRouter failover is enabled but OPENROUTER_API_KEY is not set"
            )
        return

    backend = resolve_backend()
    if backend == "claude":
        provider = resolve_claude_provider()
        if provider == "foundry":
            api_key, auth_token, _ = foundry_credentials()
            if not (api_key or auth_token):
                raise RuntimeError(
                    "ABDA's Foundry Claude route needs an Azure API key or "
                    "auth token. See README.md."
                )
        elif not os.getenv("ANTHROPIC_API_KEY"):
            raise RuntimeError(
                "ABDA_ENABLE_LLM=1 and ABDA_LLM_BACKEND=claude but "
                "ANTHROPIC_API_KEY is not set. Export the key, switch to "
                "a local backend (ABDA_LLM_BACKEND=ollama), or disable "
                "LLM features (ABDA_ENABLE_LLM=0). See README.md."
            )


# Fail fast at import time so the error is loud and local rather than
# surfacing later as a failing chat request.
_preflight_llm_config(ENABLE_LLM)
from app.scenario.diff_ops import apply as apply_ops
from app.scenario.catalog import EXAMPLES_ROOT, load_bundled_scenario
from app.scenario.loader import load_scenario, scenario_from_dict
from app.scenario.save import save_scenario
from app.scenario.state import compute_state_bundle
from app.core.config import Settings, get_settings
from app.db.session import database_is_ready, initialize_database
from app.mcp.server import create_mcp_runtime, mcp_http_app
from app.services.projects import (
    ProjectNotFoundError,
    get_project,
)

STATIC_ROOT = Path(__file__).resolve().parent.parent / "static"

# Curated scenario ordering for the dropdown. Unknown ids sort to the end
# in alphabetical order.
SCENARIO_ORDER = [
    "popov_v_hayashi",
    "fire_prevention",
    "medical_ppi",
    "nba_rebuild",
    "fried_chicken_v1",
    "fried_chicken_v2",
]


def _scenario_sort_key(scenario_id: str) -> tuple[int, str]:
    try:
        return (SCENARIO_ORDER.index(scenario_id), scenario_id)
    except ValueError:
        return (len(SCENARIO_ORDER), scenario_id)


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    init_engine()
    initialize_database()
    _warm_managed_baseline_cache(get_settings())
    mcp_runtime = create_mcp_runtime()
    mcp_http_app.bind(mcp_runtime.app)
    try:
        async with mcp_runtime.server.session_manager.run():
            yield
    finally:
        mcp_http_app.unbind(mcp_runtime.app)


app = FastAPI(
    title="ABDA-NL",
    description="Natural-language scenario explorer for argument-based reasoning.",
    version="1.0.0",
    lifespan=_lifespan,
)

_settings = get_settings()
app.add_middleware(
    SessionMiddleware,
    secret_key=_settings.session_secret,
    session_cookie=_settings.session_cookie,
    max_age=_settings.session_max_age_seconds,
    same_site="lax",
    https_only=_settings.cookie_secure,
)
app.add_middleware(
    RequestBodyLimitMiddleware,
    max_bytes=_settings.max_request_body_bytes,
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(_settings.trusted_hosts))

register_exception_handlers(app)

from app.api.account_routes import router as account_router

app.include_router(account_router)
app.mount("/mcp", mcp_http_app, name="mcp")


# Static assets get `Cache-Control: no-cache, must-revalidate` so the
# browser revalidates on each load (unchanged files still return 304).
_STATIC_SUFFIXES = (".html", ".js", ".css", ".map", ".ico", ".svg", ".png")


def _is_static_path(path: str) -> bool:
    return (
        path == "/"
        or path.endswith(_STATIC_SUFFIXES)
    )


@app.middleware("http")
async def _request_context(request: Request, call_next):
    request.state.request_id = uuid4().hex
    started_at = REQUEST_METRICS.begin()
    try:
        response = await call_next(request)
    except Exception as exc:
        log.exception(
            "request_unhandled request_id=%s exception=%s",
            request.state.request_id,
            type(exc).__name__,
        )
        response = JSONResponse(
            status_code=500,
            content={
                "detail": {
                    "code": "internal_error",
                    "message": "The request could not be completed.",
                    "request_id": request.state.request_id,
                }
            },
        )
    status_code = response.status_code
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
    )
    csp = (
        "default-src 'self'; base-uri 'none'; object-src 'none'; "
        "frame-ancestors 'none'; form-action 'self'; frame-src 'none'; "
        "script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; font-src 'self'; connect-src 'self'"
    )
    if _settings.environment in {"staging", "production"}:
        csp += "; upgrade-insecure-requests"
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    response.headers["Content-Security-Policy"] = csp
    if _is_static_path(request.url.path):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    elif request.url.path != "/health/live":
        response.headers.setdefault("Cache-Control", "no-store")
    # Unknown paths are attacker-controlled. Keep them out of logs and metric
    # labels so one request cannot introduce sensitive or unbounded values.
    route = getattr(request.scope.get("route"), "path", "<unmatched>")
    duration_ms = int(max(0.0, time.monotonic() - started_at) * 1000)
    REQUEST_METRICS.finish(request.method, route, status_code, started_at)
    if request.url.path != "/internal/metrics":
        log.info(
            "request_complete request_id=%s method=%s route=%s status=%d duration_ms=%d",
            request.state.request_id,
            request.method,
            route,
            status_code,
            duration_ms,
        )
    return response


def _load_baseline(scenario_id: str):
    return load_bundled_scenario(scenario_id)


def _compute_state_bundle(scenario) -> dict:
    return compute_state_bundle(scenario)


@lru_cache(maxsize=32)
def _cached_managed_baseline_bundle(scenario_id: str) -> dict:
    """Compile one immutable public example once per worker process."""
    return _compute_state_bundle(_load_baseline(scenario_id))


def _baseline_state_bundle(scenario_id: str, settings: Settings) -> dict:
    if settings.is_managed_service:
        return deepcopy(_cached_managed_baseline_bundle(scenario_id))
    return _compute_state_bundle(_load_baseline(scenario_id))


def _warm_managed_baseline_cache(settings: Settings) -> None:
    if not settings.is_managed_service:
        return
    for scenario_id in SCENARIO_ORDER:
        _cached_managed_baseline_bundle(scenario_id)
    log.info("managed_baseline_cache_ready scenarios=%d", len(SCENARIO_ORDER))


@app.get("/config", response_model=ConfigResponse)
def get_config() -> ConfigResponse:
    return build_llm_config(llm_enabled=_read_llm_flag())


@app.get("/health/live", include_in_schema=False)
def health_live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", include_in_schema=False)
def health_ready() -> dict[str, str]:
    if not database_is_ready():
        raise HTTPException(status_code=503, detail="database is not ready")
    return {"status": "ready"}


def _require_metrics_access(request: Request) -> None:
    expected = _settings.metrics_token
    if expected is None and _settings.environment in {"development", "test"}:
        if request.client is not None and request.client.host in {
            "127.0.0.1",
            "::1",
            "localhost",
            "testclient",
        }:
            return
    supplied = request.headers.get("authorization") or ""
    scheme, _, token = supplied.partition(" ")
    if (
        expected is None
        or scheme.lower() != "bearer"
        or not token
        or not secrets.compare_digest(token, expected)
    ):
        raise HTTPException(
            status_code=401,
            detail={"code": "metrics_authentication_required", "message": "not authorized"},
            headers={"WWW-Authenticate": "Bearer"},
        )


@app.get("/internal/metrics", include_in_schema=False)
def internal_metrics(
    request: Request,
    session: Session = Depends(get_db),
) -> PlainTextResponse:
    _require_metrics_access(request)
    trial = session.get(TrialProgram, "global")
    emergency = session.get(EmergencyBudget, "openrouter")
    llm_events = int(session.scalar(select(func.count(LLMUsageEvent.id))) or 0)
    trial_reserved = int(
        session.scalar(select(func.sum(TrialGrant.reserved_microusd))) or 0
    )
    trial_uncertain_count = int(
        session.scalar(
            select(func.count(UsageReservation.id)).where(
                UsageReservation.status == "expired_charged"
            )
        )
        or 0
    )
    trial_uncertain_cost = int(
        session.scalar(
            select(func.sum(UsageReservation.actual_microusd)).where(
                UsageReservation.status == "expired_charged"
            )
        )
        or 0
    )
    emergency_uncertain_count = int(
        session.scalar(
            select(func.count(EmergencyUsageReservation.id)).where(
                EmergencyUsageReservation.status == "expired_charged"
            )
        )
        or 0
    )
    emergency_uncertain_cost = int(
        session.scalar(
            select(func.sum(EmergencyUsageReservation.actual_microusd)).where(
                EmergencyUsageReservation.status == "expired_charged"
            )
        )
        or 0
    )
    lines = [REQUEST_METRICS.render().rstrip("\n")]
    checked_out = getattr(get_engine().pool, "checkedout", None)
    checked_out_count = int(checked_out()) if callable(checked_out) else 0
    lines.extend(
        [
            "# TYPE abda_database_pool_capacity gauge",
            "abda_database_pool_capacity "
            f"{_settings.database_pool_size + _settings.database_max_overflow}",
            "# TYPE abda_database_pool_checked_out gauge",
            f"abda_database_pool_checked_out {checked_out_count}",
        ]
    )
    if trial is not None:
        lines.extend(
            [
                "# TYPE abda_trial_enabled gauge",
                f"abda_trial_enabled {int(trial.enabled)}",
                "# TYPE abda_trial_max_users gauge",
                f"abda_trial_max_users {trial.max_users}",
                "# TYPE abda_trial_grant_microusd gauge",
                f"abda_trial_grant_microusd {trial.grant_microusd}",
                "# TYPE abda_trial_budget_microusd gauge",
                f"abda_trial_budget_microusd {trial.budget_microusd}",
                "# TYPE abda_trial_activations gauge",
                f"abda_trial_activations {trial.activation_count}",
                "# TYPE abda_trial_allocated_microusd gauge",
                f"abda_trial_allocated_microusd {trial.allocated_microusd}",
                "# TYPE abda_trial_spent_microusd gauge",
                f"abda_trial_spent_microusd {trial.spent_microusd}",
                "# TYPE abda_trial_reserved_microusd gauge",
                f"abda_trial_reserved_microusd {trial_reserved}",
                "# TYPE abda_trial_uncertain_charged_reservations gauge",
                "abda_trial_uncertain_charged_reservations "
                f"{trial_uncertain_count}",
                "# TYPE abda_trial_uncertain_charged_microusd gauge",
                f"abda_trial_uncertain_charged_microusd {trial_uncertain_cost}",
            ]
        )
    if emergency is not None:
        lines.extend(
            [
                "# TYPE abda_openrouter_enabled gauge",
                f"abda_openrouter_enabled {int(emergency.enabled)}",
                "# TYPE abda_openrouter_spent_microusd gauge",
                f"abda_openrouter_spent_microusd {emergency.spent_microusd}",
                "# TYPE abda_openrouter_reserved_microusd gauge",
                f"abda_openrouter_reserved_microusd {emergency.reserved_microusd}",
                "# TYPE abda_openrouter_budget_microusd gauge",
                f"abda_openrouter_budget_microusd {emergency.hard_limit_microusd}",
                "# TYPE abda_openrouter_uncertain_charged_reservations gauge",
                "abda_openrouter_uncertain_charged_reservations "
                f"{emergency_uncertain_count}",
                "# TYPE abda_openrouter_uncertain_charged_microusd gauge",
                "abda_openrouter_uncertain_charged_microusd "
                f"{emergency_uncertain_cost}",
            ]
        )
    lines.extend(
        [
            "# TYPE abda_llm_usage_events_total gauge",
            f"abda_llm_usage_events_total {llm_events}",
        ]
    )
    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


@app.get("/scenarios", response_model=ScenarioListResponse)
def list_scenarios() -> ScenarioListResponse:
    items: list[ScenarioListItem] = []
    if EXAMPLES_ROOT.is_dir():
        children = [c for c in EXAMPLES_ROOT.iterdir() if c.is_dir()]
        children.sort(key=lambda c: _scenario_sort_key(c.name))
        for child in children:
            scenario_path = child / "scenario.yaml"
            if not scenario_path.is_file():
                continue
            try:
                scenario = load_scenario(scenario_path)
            except Exception as exc:  # noqa: BLE001
                # Broken scenarios are skipped from the listing, but we
                # log the reason so it's visible in server output. The
                # scenario still surfaces (with its full error shape) on
                # explicit GET /scenarios/{id}.
                log.warning("skipping broken scenario %s: %s", child.name, exc)
                continue
            items.append(
                ScenarioListItem(
                    id=child.name,
                    title=scenario.title,
                    description=scenario.description,
                )
            )
    return ScenarioListResponse(scenarios=items)


@app.get("/scenarios/{scenario_id}", response_model=StateResponse)
def get_scenario(
    scenario_id: str,
    settings: Settings = Depends(get_settings),
) -> StateResponse:
    return StateResponse(**_baseline_state_bundle(scenario_id, settings))


@app.post("/state", response_model=StateResponse)
def post_state(
    payload: StateRequest,
    raw_request: Request,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> StateResponse:
    enforce_rate_limit(
        raw_request,
        session,
        settings,
        scope="state_compute",
        limit=settings.anonymous_requests_per_minute,
    )
    if not payload.diff_ops:
        return StateResponse(
            **_baseline_state_bundle(payload.scenario_id, settings)
        )
    baseline = _load_baseline(payload.scenario_id)
    ops = [op.model_dump() for op in payload.diff_ops]
    effective = apply_ops(baseline, ops)
    return StateResponse(**_compute_state_bundle(effective))


# Lazy-imported on first request so non-LLM mode never loads the
# anthropic SDK or requires an API key.
_llm_client = None


def _get_llm_client():
    global _llm_client
    if _llm_client is None:
        if not ENABLE_LLM:
            raise RuntimeError("chat is disabled; restart with ABDA_ENABLE_LLM=1")
        from app.llm import make_llm_client

        _llm_client = make_llm_client()
    return _llm_client


def _request_llm_client(
    options,
    *,
    user: User | None,
    request_id: str,
    request_kind: str,
):
    return select_request_llm_client(
        options,
        user=user,
        request_id=request_id,
        request_kind=request_kind,
        legacy_factory=_get_llm_client,
    )


def _run_chat_request(
    payload,
    raw_request: Request,
    user: User | None,
    *,
    scenario,
    bundle: dict,
    ops: list[dict],
    scenario_dir: Path,
    context_kind: str,
    context_id: str,
) -> ChatResponse:
    from app.llm.chat_service import run_turn

    uses_byok = payload.llm is not None and payload.llm.byok is not None
    try:
        client = _request_llm_client(
            payload.llm,
            user=user,
            request_id=raw_request.state.request_id,
            request_kind="chat",
        )
        result = run_turn(
            scenario,
            bundle["af"],
            ops,
            [message.model_dump() for message in payload.messages],
            scenario_dir=scenario_dir,
            client=client,
        )
    except HANDLED_LLM_ERRORS as exc:
        raise llm_http_exception(exc, byok=uses_byok) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    log.info(
        "chat_turn request_id=%s context=%s context_id=%s msgs=%d route=%s "
        "cost_microusd=%d validator_flags=%d retried=%s stop=%s",
        raw_request.state.request_id,
        context_kind,
        context_id,
        len(payload.messages),
        result.route,
        result.cost_microusd,
        len(result.validator_flags),
        result.retried,
        result.stop_reason,
    )
    return ChatResponse(
        message=result.text,
        stop_reason=result.stop_reason,
        model=result.model,
        provider=result.provider,
        billing_source=result.billing_source,
        route=result.route,
        cost_microusd=result.cost_microusd,
        request_id=raw_request.state.request_id,
        usage=ChatUsage(**result.usage),
        latency_ms=result.latency_ms,
        retried=result.retried,
    )


def _run_propose_request(
    payload,
    raw_request: Request,
    user: User | None,
    *,
    scenario,
    bundle: dict,
    ops: list[dict],
    scenario_dir: Path,
    context_kind: str,
    context_id: str,
) -> ProposeResponse:
    from app.llm.edit_service import ProposerRetryExhausted, run_propose

    if payload.task == "modify-rule" and not payload.existing_id:
        raise HTTPException(status_code=400, detail="modify-rule requires `existing_id`")

    uses_byok = payload.llm is not None and payload.llm.byok is not None
    try:
        client = _request_llm_client(
            payload.llm,
            user=user,
            request_id=raw_request.state.request_id,
            request_kind="propose",
        )
        result = run_propose(
            scenario,
            bundle["af"],
            ops,
            task=payload.task,
            instruction=payload.instruction,
            existing_id=payload.existing_id,
            scenario_dir=scenario_dir,
            client=client,
        )
    except ProposerRetryExhausted as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "proposer_retry_exhausted",
                "message": str(exc),
                "issues": [issue.to_dict() for issue in exc.last_issues],
            },
        ) from exc
    except HANDLED_LLM_ERRORS as exc:
        raise llm_http_exception(exc, byok=uses_byok) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    log.info(
        "propose_turn request_id=%s context=%s context_id=%s task=%s op_id=%s "
        "route=%s cost_microusd=%d attempts=%d reviewed=%s review_issues=%d",
        raw_request.state.request_id,
        context_kind,
        context_id,
        payload.task,
        result.op.get("id"),
        result.route,
        result.cost_microusd,
        result.proposer_attempts,
        result.reviewed,
        len(result.review_issues),
    )
    return ProposeResponse(
        op=result.op,
        stop_reason=result.stop_reason,
        model=result.model,
        provider=result.provider,
        billing_source=result.billing_source,
        route=result.route,
        cost_microusd=result.cost_microusd,
        request_id=raw_request.state.request_id,
        usage=ChatUsage(**result.usage),
        latency_ms=result.latency_ms,
        proposer_attempts=result.proposer_attempts,
        reviewed=result.reviewed,
        review_issues=[issue.to_dict() for issue in result.review_issues],
    )


def _project_version_error() -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": "project_version_conflict",
            "message": "project changed since it was loaded",
        },
    )


def _load_project_working_context(
    session: Session,
    user: User,
    project_id: str,
    expected_version: int,
    diff_ops,
):
    try:
        project = get_project(session, user, project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "project_not_found", "message": "project not found"},
        ) from exc
    if project.version != expected_version:
        raise _project_version_error()
    baseline = scenario_from_dict(project.scenario_json)
    ops = [operation.model_dump() for operation in diff_ops]
    scenario = apply_ops(baseline, ops)
    return project, scenario, _compute_state_bundle(scenario), ops


def _project_scenario_dir(project) -> Path:
    source_id = (project.source_scenario_id or "").strip()
    candidate = (EXAMPLES_ROOT / source_id).resolve()
    examples_root = EXAMPLES_ROOT.resolve()
    if not source_id or examples_root not in candidate.parents or not candidate.is_dir():
        raise HTTPException(
            status_code=409,
            detail={
                "code": "project_source_unavailable",
                "message": "the source corpus for this project is unavailable",
            },
        )
    return candidate


@app.post(
    "/chat",
    response_model=ChatResponse,
    dependencies=[Depends(require_same_origin)],
)
def post_chat(
    payload: ChatRequest,
    raw_request: Request,
    user: Optional[User] = Depends(current_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ChatResponse:
    if not ENABLE_LLM:
        raise HTTPException(
            status_code=503,
            detail="chat is disabled; restart with ABDA_ENABLE_LLM=1",
        )
    enforce_rate_limit(
        raw_request,
        session,
        settings,
        scope="llm_request",
        limit=settings.llm_requests_per_minute,
        user_id=user.id if user is not None else None,
    )

    scenario_dir = EXAMPLES_ROOT / payload.scenario_id
    baseline = _load_baseline(payload.scenario_id)
    ops = [op.model_dump() for op in payload.diff_ops]
    scenario = apply_ops(baseline, ops)
    bundle = _compute_state_bundle(scenario)
    return _run_chat_request(
        payload,
        raw_request,
        user,
        scenario=scenario,
        bundle=bundle,
        ops=ops,
        scenario_dir=scenario_dir,
        context_kind="example",
        context_id=payload.scenario_id,
    )


@app.post(
    "/propose",
    response_model=ProposeResponse,
    dependencies=[Depends(require_same_origin)],
)
def post_propose(
    payload: ProposeRequest,
    raw_request: Request,
    user: Optional[User] = Depends(current_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ProposeResponse:
    if not ENABLE_LLM:
        raise HTTPException(
            status_code=503,
            detail="edit flows are disabled; restart with ABDA_ENABLE_LLM=1",
        )
    enforce_rate_limit(
        raw_request,
        session,
        settings,
        scope="llm_request",
        limit=settings.llm_requests_per_minute,
        user_id=user.id if user is not None else None,
    )
    scenario_dir = EXAMPLES_ROOT / payload.scenario_id
    baseline = _load_baseline(payload.scenario_id)
    ops = [op.model_dump() for op in payload.diff_ops]
    scenario = apply_ops(baseline, ops)
    bundle = _compute_state_bundle(scenario)
    return _run_propose_request(
        payload,
        raw_request,
        user,
        scenario=scenario,
        bundle=bundle,
        ops=ops,
        scenario_dir=scenario_dir,
        context_kind="example",
        context_id=payload.scenario_id,
    )


@app.post("/api/projects/{project_id}/state", response_model=StateResponse)
def post_project_state(
    project_id: str,
    payload: ProjectWorkingStateRequest,
    raw_request: Request,
    user: User = Depends(require_verified_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> StateResponse:
    enforce_rate_limit(
        raw_request,
        session,
        settings,
        scope="state_compute",
        limit=settings.anonymous_requests_per_minute,
        user_id=user.id,
    )
    _project, _scenario, bundle, _ops = _load_project_working_context(
        session, user, project_id, payload.expected_version, payload.diff_ops
    )
    return StateResponse(**bundle)


@app.post(
    "/api/projects/{project_id}/chat",
    response_model=ChatResponse,
    dependencies=[Depends(require_same_origin)],
)
def post_project_chat(
    project_id: str,
    payload: ProjectChatRequest,
    raw_request: Request,
    user: User = Depends(require_verified_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ChatResponse:
    if not ENABLE_LLM:
        raise HTTPException(
            status_code=503,
            detail="chat is disabled; restart with ABDA_ENABLE_LLM=1",
        )
    enforce_rate_limit(
        raw_request,
        session,
        settings,
        scope="llm_request",
        limit=settings.llm_requests_per_minute,
        user_id=user.id,
    )
    project, scenario, bundle, ops = _load_project_working_context(
        session, user, project_id, payload.expected_version, payload.diff_ops
    )
    return _run_chat_request(
        payload,
        raw_request,
        user,
        scenario=scenario,
        bundle=bundle,
        ops=ops,
        scenario_dir=_project_scenario_dir(project),
        context_kind="project",
        context_id=project_id,
    )


@app.post(
    "/api/projects/{project_id}/propose",
    response_model=ProposeResponse,
    dependencies=[Depends(require_same_origin)],
)
def post_project_propose(
    project_id: str,
    payload: ProjectProposeRequest,
    raw_request: Request,
    user: User = Depends(require_verified_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ProposeResponse:
    if not ENABLE_LLM:
        raise HTTPException(
            status_code=503,
            detail="edit flows are disabled; restart with ABDA_ENABLE_LLM=1",
        )
    enforce_rate_limit(
        raw_request,
        session,
        settings,
        scope="llm_request",
        limit=settings.llm_requests_per_minute,
        user_id=user.id,
    )
    project, scenario, bundle, ops = _load_project_working_context(
        session, user, project_id, payload.expected_version, payload.diff_ops
    )
    return _run_propose_request(
        payload,
        raw_request,
        user,
        scenario=scenario,
        bundle=bundle,
        ops=ops,
        scenario_dir=_project_scenario_dir(project),
        context_kind="project",
        context_id=project_id,
    )


@app.post(
    "/scenarios",
    response_model=SaveScenarioResponse,
    status_code=201,
    dependencies=[Depends(require_same_origin)],
)
def post_save_scenario(
    request: SaveScenarioRequest,
    settings: Settings = Depends(get_settings),
) -> SaveScenarioResponse:
    """Save the current (baseline + diff_ops) state as a new scenario.

    Writes `examples/<save_as_id>/` with a diff-applied
    `scenario.yaml` plus a copy of the baseline's corpus
    artefacts. Post-write, the server reloads and rebuilds the
    scenario to catch any inconsistency; on verification failure the
    temp dir is cleaned up and a 500 is returned.

    Response carries the fresh bundled state so the UI can pivot to
    the saved scenario without a second fetch.

    Error codes:
      400 invalid_scenario_id -- save_as_id fails the identifier pattern
      404 scenario_not_found -- source_id doesn't exist under examples/
      409 scenario_id_collision -- target exists and overwrite=false
      500 save_verification_failed -- post-write rebuild failed (rare)
    """
    if settings.is_managed_service:
        raise HTTPException(
            status_code=403,
            detail="filesystem saves are disabled; save this work as a private project",
        )

    baseline = _load_baseline(request.source_id)
    ops = [op.model_dump() for op in request.diff_ops]
    effective = apply_ops(baseline, ops)

    target = save_scenario(
        effective=effective,
        title=request.title,
        save_as_id=request.save_as_id,
        baseline_dir=EXAMPLES_ROOT / request.source_id,
        examples_root=EXAMPLES_ROOT,
        overwrite=request.overwrite,
    )
    log.info(
        "scenario_saved source=%s saved_as=%s overwrite=%s",
        request.source_id,
        request.save_as_id,
        request.overwrite,
    )

    # Reload from disk and return the fresh bundle so the UI can pivot.
    saved = load_scenario(target / "scenario.yaml")
    bundle = _compute_state_bundle(saved)
    return SaveScenarioResponse(
        id=request.save_as_id,
        title=saved.title,
        scenario=bundle["scenario"],
        af=bundle["af"],
    )


# The frontend mount is a catch-all at "/" and must stay last — any
# endpoint registered after it becomes silently unreachable.
if STATIC_ROOT.is_dir():
    app.mount("/", StaticFiles(directory=str(STATIC_ROOT), html=True), name="static")
