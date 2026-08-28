"""Account, project, share-link, and free-trial HTTP routes."""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.account_models import (
    AuthSessionResponse,
    DevelopmentLoginRequest,
    MCPTokenCreateRequest,
    MCPTokenCreatedResponse,
    MCPTokenListResponse,
    MCPTokenResponse,
    ProjectCreateRequest,
    ProjectDetailResponse,
    ProjectImportRequest,
    ProjectListResponse,
    ProjectSummaryResponse,
    ProjectUpdateRequest,
    ShareLinkCreateRequest,
    ShareLinkCreatedResponse,
    ShareLinkListResponse,
    ShareLinkResponse,
    ShareResolveRequest,
    SharedProjectResponse,
    TrialStatusResponse,
    UserView,
)
from app.api.dependencies import current_user, require_same_origin, require_verified_user
from app.api.abuse import enforce_rate_limit
from app.core.config import Settings, get_settings
from app.db.models import MCPAccessToken, Project, User
from app.db.session import get_db
from app.scenario.catalog import load_bundled_scenario
from app.scenario.diff_ops import apply as apply_ops
from app.scenario.loader import scenario_from_dict
from app.scenario.serialize import scenario_to_dict
from app.scenario.state import compute_state_bundle
from app.services.accounts import IdentityError, upsert_local_development_user, upsert_verified_identity
from app.services.projects import (
    ProjectNotFoundError,
    ProjectLimitError,
    ProjectVersionConflictError,
    ShareLinkLimitError,
    ShareLinkNotFoundError,
    archive_project,
    create_project,
    create_share_link,
    get_project,
    list_projects,
    list_share_links,
    resolve_share_link,
    revoke_share_link,
    update_project,
)
from app.services.trials import (
    TrialBalance,
    TrialUnavailableError,
    activate_trial,
    get_trial_balance,
)
from app.services.mcp_tokens import (
    MCPTokenError,
    MCPTokenLimitError,
    MCPTokenNotFoundError,
    create_mcp_token,
    list_mcp_tokens,
    mcp_token_is_active,
    mcp_token_scopes,
    revoke_mcp_token,
)


log = logging.getLogger(__name__)
router = APIRouter()


def _limit_user_mutation(
    request: Request,
    session: Session,
    settings: Settings,
    user: User,
    *,
    scope: str = "account_mutation",
) -> None:
    enforce_rate_limit(
        request,
        session,
        settings,
        scope=scope,
        limit=settings.mutation_requests_per_minute,
        user_id=user.id,
    )


def _safe_next(value: Optional[str]) -> str:
    if (
        not value
        or len(value) > 1000
        or "\\" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        return "/"
    parsed = urlsplit(value)
    path = parsed.path
    if (
        parsed.scheme
        or parsed.netloc
        or parsed.fragment
        or not path.startswith("/")
        or path.startswith("//")
    ):
        return "/"
    # Return paths never need query values. Dropping them prevents an OIDC
    # round trip from copying a bearer value into a server-visible URL.
    return path


@lru_cache(maxsize=1)
def _oauth_registry():
    from authlib.integrations.starlette_client import OAuth

    settings = get_settings()
    oauth = OAuth()
    oauth.register(
        name="oidc",
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret,
        server_metadata_url=settings.oidc_metadata_url,
        client_kwargs={"scope": settings.oidc_scope},
    )
    return oauth


def _callback_url(request: Request, settings: Settings) -> str:
    if settings.public_base_url:
        return f"{settings.public_base_url}/auth/callback"
    return str(request.url_for("oidc_callback"))


def _post_logout_url(request: Request, settings: Settings) -> str:
    if settings.public_base_url:
        return f"{settings.public_base_url}/"
    return str(request.base_url)


def _safe_logout_hint(value: object) -> str | None:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 512
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        return None
    return value


async def _oidc_logout_url(
    request: Request,
    settings: Settings,
    *,
    logout_hint: str | None,
) -> str:
    if not settings.oidc_client_id:
        raise RuntimeError("OIDC logout requires a client ID")
    client = _oauth_registry().create_client("oidc")
    metadata = await client.load_server_metadata()
    endpoint = str(metadata.get("end_session_endpoint") or "").strip()
    parsed = urlsplit(endpoint)
    if (
        not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or parsed.scheme not in {"http", "https"}
        or (
            settings.environment in {"staging", "production"}
            and parsed.scheme != "https"
        )
    ):
        raise RuntimeError("OIDC discovery did not provide a safe logout endpoint")

    query = parse_qsl(parsed.query, keep_blank_values=True)
    query.extend(
        [
            ("client_id", str(settings.oidc_client_id)),
            ("post_logout_redirect_uri", _post_logout_url(request, settings)),
        ]
    )
    if logout_hint:
        query.append(("logout_hint", logout_hint))
    return urlunsplit(parsed._replace(query=urlencode(query)))


def _home_with_error(code: str) -> str:
    return f"/?{urlencode({'auth_error': code})}"


@router.get("/api/auth/session", response_model=AuthSessionResponse)
def auth_session(
    user: Optional[User] = Depends(current_user),
    settings: Settings = Depends(get_settings),
) -> AuthSessionResponse:
    return AuthSessionResponse(
        authenticated=user is not None,
        auth_mode=settings.auth_mode,
        login_url="/auth/login" if settings.auth_mode == "oidc" else None,
        user=UserView.model_validate(user) if user is not None else None,
    )


@router.post(
    "/api/auth/dev/login",
    response_model=AuthSessionResponse,
    dependencies=[Depends(require_same_origin)],
)
def development_login(
    payload: DevelopmentLoginRequest,
    request: Request,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthSessionResponse:
    if settings.auth_mode != "dev" or settings.environment not in {"development", "test"}:
        raise HTTPException(status_code=404, detail="not found")
    enforce_rate_limit(
        request,
        session,
        settings,
        scope="auth_login",
        limit=min(20, settings.anonymous_requests_per_minute),
    )
    user = upsert_local_development_user(
        session,
        email=str(payload.email),
        display_name=payload.display_name,
    )
    request.session.clear()
    request.session["user_id"] = user.id
    return AuthSessionResponse(
        authenticated=True,
        auth_mode=settings.auth_mode,
        user=UserView.model_validate(user),
    )


@router.post(
    "/api/auth/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_same_origin)],
)
def logout(request: Request) -> Response:
    request.session.clear()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/auth/logout",
    include_in_schema=False,
    dependencies=[Depends(require_same_origin)],
)
async def browser_logout(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """Clear the local session, then end the hosted OIDC browser session."""
    logout_hint = _safe_logout_hint(request.session.get("oidc_sid"))
    request.session.clear()
    destination = _post_logout_url(request, settings)
    if settings.auth_mode == "oidc":
        try:
            destination = await _oidc_logout_url(
                request,
                settings,
                logout_hint=logout_hint,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("OIDC logout discovery failed: %s", type(exc).__name__)
    return RedirectResponse(destination, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/auth/login", name="oidc_login", include_in_schema=False)
async def oidc_login(
    request: Request,
    next: Optional[str] = None,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if settings.auth_mode != "oidc":
        raise HTTPException(status_code=404, detail="not found")
    enforce_rate_limit(
        request,
        session,
        settings,
        scope="auth_login",
        limit=min(20, settings.anonymous_requests_per_minute),
    )
    request.session["post_login_path"] = _safe_next(next)
    client = _oauth_registry().create_client("oidc")
    return await client.authorize_redirect(request, _callback_url(request, settings))


@router.get("/auth/callback", name="oidc_callback", include_in_schema=False)
async def oidc_callback(
    request: Request,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if settings.auth_mode != "oidc":
        raise HTTPException(status_code=404, detail="not found")
    next_path = _safe_next(request.session.get("post_login_path"))
    try:
        client = _oauth_registry().create_client("oidc")
        token = await client.authorize_access_token(request)
        claims = token.get("userinfo") or {}
        claimed_issuer = str(claims.get("iss") or "").strip().rstrip("/")
        if (
            settings.oidc_issuer
            and claimed_issuer != settings.oidc_issuer
        ):
            raise IdentityError(
                "the login token issuer does not match this deployment",
                code="identity_claims_invalid",
            )
        user = upsert_verified_identity(
            session,
            issuer=settings.oidc_issuer or claimed_issuer,
            subject=str(claims.get("sub") or ""),
            email=str(claims.get("email") or ""),
            email_verified=claims.get("email_verified") is True,
            display_name=str(claims.get("name") or "") or None,
        )
    except IdentityError as exc:
        request.session.clear()
        log.info("OIDC login rejected: %s", exc)
        return RedirectResponse(_home_with_error(exc.code), status_code=303)
    except Exception as exc:  # noqa: BLE001
        request.session.clear()
        log.warning("OIDC callback failed: %s", type(exc).__name__)
        return RedirectResponse(_home_with_error("login_failed"), status_code=303)
    request.session.clear()
    request.session["user_id"] = user.id
    oidc_sid = _safe_logout_hint(claims.get("sid"))
    if oidc_sid:
        request.session["oidc_sid"] = oidc_sid
    return RedirectResponse(next_path, status_code=303)


def _project_detail(project: Project) -> ProjectDetailResponse:
    bundle = compute_state_bundle(scenario_from_dict(project.scenario_json))
    return ProjectDetailResponse(
        **ProjectSummaryResponse.model_validate(project).model_dump(),
        scenario=bundle["scenario"],
        af=bundle["af"],
    )


def _project_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ProjectNotFoundError):
        return HTTPException(
            status_code=404,
            detail={"code": "project_not_found", "message": str(exc)},
        )
    if isinstance(exc, ProjectVersionConflictError):
        return HTTPException(
            status_code=409,
            detail={"code": "project_version_conflict", "message": str(exc)},
        )
    if isinstance(exc, ProjectLimitError):
        return HTTPException(
            status_code=409,
            detail={"code": "project_limit", "message": str(exc)},
        )
    if isinstance(exc, ShareLinkLimitError):
        return HTTPException(
            status_code=409,
            detail={"code": "share_link_limit", "message": str(exc)},
        )
    return HTTPException(status_code=400, detail={"code": "project_invalid", "message": str(exc)})


@router.get("/api/projects", response_model=ProjectListResponse)
def get_projects(
    user: User = Depends(require_verified_user),
    session: Session = Depends(get_db),
) -> ProjectListResponse:
    return ProjectListResponse(
        projects=[ProjectSummaryResponse.model_validate(item) for item in list_projects(session, user)]
    )


@router.post(
    "/api/projects",
    response_model=ProjectDetailResponse,
    status_code=201,
    dependencies=[Depends(require_same_origin)],
)
def post_project(
    payload: ProjectCreateRequest,
    request: Request,
    response: Response,
    user: User = Depends(require_verified_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ProjectDetailResponse:
    _limit_user_mutation(request, session, settings, user)
    baseline = load_bundled_scenario(payload.source_scenario_id)
    effective = apply_ops(baseline, [item.model_dump() for item in payload.diff_ops])
    try:
        project = create_project(
            session,
            user,
            name=payload.name,
            description=payload.description,
            scenario=scenario_to_dict(effective),
            source_scenario_id=payload.source_scenario_id,
        )
    except (ProjectLimitError, ValueError) as exc:
        raise _project_error(exc)
    response.headers["ETag"] = f'"{project.version}"'
    return _project_detail(project)


@router.post(
    "/api/projects/import",
    response_model=ProjectDetailResponse,
    status_code=201,
    dependencies=[Depends(require_same_origin)],
)
def post_project_import(
    payload: ProjectImportRequest,
    request: Request,
    response: Response,
    user: User = Depends(require_verified_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ProjectDetailResponse:
    _limit_user_mutation(request, session, settings, user)
    if payload.source_scenario_id is not None:
        load_bundled_scenario(payload.source_scenario_id)
    try:
        project = create_project(
            session,
            user,
            name=payload.name,
            description=payload.description,
            scenario=payload.scenario,
            source_scenario_id=payload.source_scenario_id,
        )
    except (ProjectLimitError, ValueError) as exc:
        raise _project_error(exc)
    response.headers["ETag"] = f'"{project.version}"'
    return _project_detail(project)


@router.get("/api/projects/{project_id}", response_model=ProjectDetailResponse)
def get_project_route(
    project_id: str,
    response: Response,
    user: User = Depends(require_verified_user),
    session: Session = Depends(get_db),
) -> ProjectDetailResponse:
    try:
        project = get_project(session, user, project_id)
    except ProjectNotFoundError as exc:
        raise _project_error(exc)
    response.headers["ETag"] = f'"{project.version}"'
    return _project_detail(project)


@router.put(
    "/api/projects/{project_id}",
    response_model=ProjectDetailResponse,
    dependencies=[Depends(require_same_origin)],
)
def put_project(
    project_id: str,
    payload: ProjectUpdateRequest,
    request: Request,
    response: Response,
    user: User = Depends(require_verified_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ProjectDetailResponse:
    _limit_user_mutation(request, session, settings, user)
    try:
        project = update_project(
            session,
            user,
            project_id,
            expected_version=payload.expected_version,
            name=payload.name,
            description=payload.description,
            scenario=payload.scenario,
        )
    except (ProjectNotFoundError, ProjectVersionConflictError, ValueError) as exc:
        raise _project_error(exc)
    response.headers["ETag"] = f'"{project.version}"'
    return _project_detail(project)


@router.delete(
    "/api/projects/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_same_origin)],
)
def delete_project(
    project_id: str,
    expected_version: int,
    request: Request,
    user: User = Depends(require_verified_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    _limit_user_mutation(request, session, settings, user)
    try:
        archive_project(session, user, project_id, expected_version=expected_version)
    except (ProjectNotFoundError, ProjectVersionConflictError) as exc:
        raise _project_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/api/projects/{project_id}/shares",
    response_model=ShareLinkListResponse,
)
def get_project_shares(
    project_id: str,
    user: User = Depends(require_verified_user),
    session: Session = Depends(get_db),
) -> ShareLinkListResponse:
    try:
        links = list_share_links(session, user, project_id)
    except ProjectNotFoundError as exc:
        raise _project_error(exc)
    return ShareLinkListResponse(
        share_links=[ShareLinkResponse.model_validate(item) for item in links]
    )


@router.post(
    "/api/projects/{project_id}/shares",
    response_model=ShareLinkCreatedResponse,
    status_code=201,
    dependencies=[Depends(require_same_origin)],
)
def post_project_share(
    project_id: str,
    payload: ShareLinkCreateRequest,
    request: Request,
    user: User = Depends(require_verified_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ShareLinkCreatedResponse:
    _limit_user_mutation(request, session, settings, user, scope="share_mutation")
    try:
        link, token = create_share_link(
            session, user, project_id, expires_at=payload.expires_at
        )
    except (ProjectNotFoundError, ShareLinkLimitError, ValueError) as exc:
        raise _project_error(exc)
    base_url = settings.public_base_url or str(request.base_url).rstrip("/")
    return ShareLinkCreatedResponse(
        **ShareLinkResponse.model_validate(link).model_dump(),
        url=f"{base_url}/#share={token}",
    )


@router.delete(
    "/api/projects/{project_id}/shares/{share_link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_same_origin)],
)
def delete_project_share(
    project_id: str,
    share_link_id: str,
    request: Request,
    user: User = Depends(require_verified_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    _limit_user_mutation(request, session, settings, user, scope="share_mutation")
    try:
        revoke_share_link(session, user, project_id, share_link_id)
    except (ProjectNotFoundError, ShareLinkNotFoundError) as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "share_link_not_found", "message": str(exc)},
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/api/shares/resolve", response_model=SharedProjectResponse)
def post_resolve_share(
    payload: ShareResolveRequest,
    request: Request,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SharedProjectResponse:
    enforce_rate_limit(
        request,
        session,
        settings,
        scope="share_resolve",
        limit=min(60, settings.anonymous_requests_per_minute),
    )
    try:
        project = resolve_share_link(session, payload.token)
    except ShareLinkNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "share_link_not_found", "message": str(exc)},
        )
    detail = _project_detail(project)
    return SharedProjectResponse(
        id=detail.id,
        name=detail.name,
        description=detail.description,
        source_scenario_id=detail.source_scenario_id,
        version=detail.version,
        scenario=detail.scenario,
        af=detail.af,
    )


def _trial_response(balance: TrialBalance) -> TrialStatusResponse:
    return TrialStatusResponse(**balance.__dict__)


@router.get("/api/trial", response_model=TrialStatusResponse)
def trial_status(
    user: User = Depends(require_verified_user),
    session: Session = Depends(get_db),
) -> TrialStatusResponse:
    return _trial_response(get_trial_balance(session, user.id))


@router.post(
    "/api/trial/activate",
    response_model=TrialStatusResponse,
    dependencies=[Depends(require_same_origin)],
)
def post_trial_activation(
    request: Request,
    user: User = Depends(require_verified_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TrialStatusResponse:
    enforce_rate_limit(
        request,
        session,
        settings,
        scope="trial_activation",
        limit=5,
        window_seconds=3600,
        user_id=user.id,
    )
    try:
        return _trial_response(activate_trial(session, user))
    except TrialUnavailableError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "trial_unavailable", "message": str(exc)},
        )


def _mcp_token_response(record: MCPAccessToken) -> MCPTokenResponse:
    return MCPTokenResponse(
        id=record.id,
        name=record.name,
        token_prefix=record.token_prefix,
        scopes=list(mcp_token_scopes(record)),
        created_at=record.created_at,
        expires_at=record.expires_at,
        last_used_at=record.last_used_at,
        revoked_at=record.revoked_at,
        active=mcp_token_is_active(record),
    )


def _mcp_url(request: Request, settings: Settings) -> str:
    base_url = settings.public_base_url or str(request.base_url).rstrip("/")
    return f"{base_url}/mcp/"


@router.get("/api/mcp/tokens", response_model=MCPTokenListResponse)
def get_mcp_tokens(
    user: User = Depends(require_verified_user),
    session: Session = Depends(get_db),
) -> MCPTokenListResponse:
    return MCPTokenListResponse(
        tokens=[_mcp_token_response(item) for item in list_mcp_tokens(session, user)]
    )


@router.post(
    "/api/mcp/tokens",
    response_model=MCPTokenCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_same_origin)],
)
def post_mcp_token(
    payload: MCPTokenCreateRequest,
    request: Request,
    response: Response,
    user: User = Depends(require_verified_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MCPTokenCreatedResponse:
    enforce_rate_limit(
        request,
        session,
        settings,
        scope="mcp_token_mutation",
        limit=10,
        window_seconds=3600,
        user_id=user.id,
    )
    try:
        record, raw_token = create_mcp_token(
            session,
            user,
            name=payload.name,
            scopes=payload.scopes,
            expires_in_days=payload.expires_in_days,
            pepper=settings.mcp_token_pepper,
        )
    except MCPTokenLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "mcp_token_limit", "message": str(exc)},
        ) from exc
    except MCPTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "mcp_token_invalid", "message": str(exc)},
        ) from exc

    endpoint = _mcp_url(request, settings)
    response.headers["Cache-Control"] = "no-store"
    view = _mcp_token_response(record)
    return MCPTokenCreatedResponse(
        **view.model_dump(),
        token=raw_token,
        mcp_url=endpoint,
        codex_config=(
            "[mcp_servers.abda_nl]\n"
            f'url = "{endpoint}"\n'
            'bearer_token_env_var = "ABDA_NL_MCP_TOKEN"\n'
            'default_tools_approval_mode = "writes"\n'
            "tool_timeout_sec = 180"
        ),
        claude_command=(
            "claude mcp add --transport http --header "
            '"Authorization: Bearer ${ABDA_NL_MCP_TOKEN}" '
            f'abda-nl "{endpoint}"'
        ),
    )


@router.delete(
    "/api/mcp/tokens/{token_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_same_origin)],
)
def delete_mcp_token(
    token_id: str,
    request: Request,
    user: User = Depends(require_verified_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    enforce_rate_limit(
        request,
        session,
        settings,
        scope="mcp_token_mutation",
        limit=10,
        window_seconds=3600,
        user_id=user.id,
    )
    try:
        revoke_mcp_token(session, user, token_id)
    except MCPTokenNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "mcp_token_not_found", "message": str(exc)},
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
