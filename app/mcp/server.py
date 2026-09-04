"""Scoped MCP tools over the same account and project invariants as the web API."""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, Literal
from urllib.parse import urlsplit
from uuid import uuid4

import anyio
from mcp.server.auth.middleware.auth_context import AuthContextMiddleware, get_access_token
from mcp.server.auth.middleware.bearer_auth import (
    BearerAuthBackend,
    RequireAuthMiddleware,
)
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp_types import ToolAnnotations
from pydantic import TypeAdapter, ValidationError
from sqlalchemy.orm import Session
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.abda_bridge import ArgumentComplexityError, ArgumentConstructionError
from app.api.llm_access import (
    HANDLED_LLM_ERRORS,
    llm_http_exception,
    select_request_llm_client,
)
from app.api.models import DiffOp, LLMRequestOptions
from app.core.config import get_settings
from app.core.safe_logging import exception_diagnostic
from app.db.models import Project, User
from app.db.session import get_session_factory
from app.llm.chat_service import run_turn
from app.llm.client import close_llm_client
from app.llm.edit_service import ProposerRetryExhausted, run_propose
from app.scenario.catalog import (
    EXAMPLES_ROOT,
    ScenarioNotFoundError,
    load_bundled_scenario,
)
from app.scenario.diff_ops import DiffOpError, apply as apply_ops
from app.scenario.loader import ScenarioValidationError, scenario_from_dict
from app.scenario.serialize import scenario_to_dict
from app.scenario.state import compute_state_bundle
from app.services.mcp_tokens import (
    MCP_SCOPE_LLM_USE,
    MCP_SCOPE_PROJECTS_READ,
    MCP_SCOPE_PROJECTS_WRITE,
    authenticate_mcp_token,
)
from app.services.projects import (
    ProjectNotFoundError,
    ProjectLimitError,
    ProjectVersionConflictError,
    ShareLinkLimitError,
    create_project as create_project_record,
    get_project as get_project_record,
    list_projects as list_project_records,
    update_project as update_project_record,
)
from app.services.rate_limits import consume_rate_limit


log = logging.getLogger(__name__)
_DIFF_OPS = TypeAdapter(list[DiffOp])


class MCPToolUserError(RuntimeError):
    """A sanitized failure that is safe to return to an MCP client."""


class DatabaseTokenVerifier(TokenVerifier):
    """Validate high-entropy personal tokens against their HMAC digests."""

    async def verify_token(self, token: str) -> AccessToken | None:
        def verify() -> AccessToken | None:
            settings = get_settings()
            with get_session_factory()() as session:
                principal = authenticate_mcp_token(
                    session,
                    token,
                    pepper=settings.mcp_token_pepper,
                )
            if principal is None:
                return None
            issuer = settings.public_base_url or "urn:abda-nl:local"
            resource = (
                f"{settings.public_base_url}/mcp"
                if settings.public_base_url
                else None
            )
            return AccessToken(
                token=token,
                client_id=f"abda-mcp-token:{principal.token_id}",
                scopes=list(principal.scopes),
                expires_at=int(principal.expires_at.timestamp()),
                resource=resource,
                subject=principal.user_id,
                claims={"iss": issuer},
            )

        return await anyio.to_thread.run_sync(verify)


def _transport_security() -> TransportSecuritySettings:
    settings = get_settings()
    allowed_hosts = [
        "127.0.0.1",
        "127.0.0.1:*",
        "localhost",
        "localhost:*",
        "[::1]",
        "[::1]:*",
    ]
    allowed_origins = [
        "http://127.0.0.1",
        "http://127.0.0.1:*",
        "http://localhost",
        "http://localhost:*",
        "http://[::1]",
        "http://[::1]:*",
    ]
    if settings.environment == "test":
        allowed_hosts.extend(["testserver", "testserver:*"])
        allowed_origins.extend(["http://testserver", "http://testserver:*"])
    if settings.public_base_url:
        parsed = urlsplit(settings.public_base_url)
        if parsed.netloc:
            allowed_hosts.append(parsed.netloc)
        if parsed.hostname:
            allowed_hosts.extend([parsed.hostname, f"{parsed.hostname}:*"])
        allowed_origins.append(settings.public_base_url)
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=list(dict.fromkeys(allowed_hosts)),
        allowed_origins=list(dict.fromkeys(allowed_origins)),
    )


def _llm_enabled() -> bool:
    return (os.getenv("ABDA_ENABLE_LLM") or "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _access_token(scope: str) -> AccessToken:
    token = get_access_token()
    if token is None or not token.subject:
        raise MCPToolUserError("Authentication is required.")
    if scope not in token.scopes:
        raise MCPToolUserError(f"This token requires the {scope} scope.")
    return token


def _active_user(session: Session, scope: str) -> User:
    token = _access_token(scope)
    user = session.get(User, token.subject)
    if user is None or user.status != "active" or not user.email_verified:
        raise MCPToolUserError("The account is not available for MCP access.")
    return user


def _limit_mcp(session: Session, user: User, scope: str, limit: int) -> None:
    settings = get_settings()
    if not settings.abuse_protection_enabled:
        return
    result = consume_rate_limit(
        session,
        scope=scope,
        subject=f"user:{user.id}",
        limit=limit,
        window_seconds=60,
        secret=settings.session_secret,
    )
    if not result.allowed:
        raise MCPToolUserError(
            f"Too many requests. Try again in {result.retry_after_seconds} seconds."
        )


def _limit_mcp_read(session: Session, user: User) -> None:
    """Apply one shared per-account ceiling to deterministic MCP reads."""
    _limit_mcp(
        session,
        user,
        "mcp_read",
        get_settings().anonymous_requests_per_minute,
    )


@contextmanager
def _tool_boundary(operation: str) -> Iterator[None]:
    try:
        yield
    except MCPToolUserError:
        raise
    except ArgumentComplexityError as exc:
        raise MCPToolUserError(
            "This scenario is too complex to analyze safely. Reduce the number "
            "of rules or alternative derivations."
        ) from exc
    except (ArgumentConstructionError, ScenarioValidationError) as exc:
        raise MCPToolUserError(
            "This scenario cannot be analyzed. Review its rules and try again."
        ) from exc
    except DiffOpError as exc:
        raise MCPToolUserError(str(exc)) from exc
    except (
        ProjectLimitError,
        ProjectNotFoundError,
        ProjectVersionConflictError,
        ScenarioNotFoundError,
        ShareLinkLimitError,
    ) as exc:
        raise MCPToolUserError(str(exc)) from exc
    except ValueError as exc:
        raise MCPToolUserError(str(exc)) from exc
    except Exception as exc:
        diagnostic = exception_diagnostic(exc)
        log.error(
            "MCP tool failed operation=%s exception=%s location=%s",
            operation,
            diagnostic.kind,
            diagnostic.location,
        )
        raise MCPToolUserError(
            "ABDA-NL could not complete this operation. Try again later."
        ) from exc


def _validated_ops(diff_ops: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if len(diff_ops or []) > 100:
        raise MCPToolUserError("At most 100 diff operations are allowed per request.")
    try:
        parsed = _DIFF_OPS.validate_python(diff_ops or [])
    except ValidationError as exc:
        raise MCPToolUserError("One or more diff operations are invalid.") from exc
    return [operation.model_dump() for operation in parsed]


def _bounded_text(value: str, field: str, *, maximum: int = 20_000) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise MCPToolUserError(f"{field} cannot be empty.")
    if len(cleaned) > maximum:
        raise MCPToolUserError(f"{field} cannot exceed {maximum} characters.")
    return cleaned


def _af_summary(af: dict[str, Any]) -> dict[str, Any]:
    return {
        "argument_count": len(af.get("arguments") or []),
        "attack_count": len(af.get("attacks") or []),
        "labels_by_proposition": af.get("labels_by_proposition") or {},
    }


def _state_payload(scenario, *, include_argument_graph: bool) -> dict[str, Any]:
    bundle = compute_state_bundle(scenario)
    result = {
        "scenario": bundle["scenario"],
        "af_summary": _af_summary(bundle["af"]),
    }
    if include_argument_graph:
        result["af"] = bundle["af"]
    return result


def _project_payload(
    project: Project, *, include_argument_graph: bool = False
) -> dict[str, Any]:
    state = _state_payload(
        scenario_from_dict(project.scenario_json),
        include_argument_graph=include_argument_graph,
    )
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "source_scenario_id": project.source_scenario_id,
        "version": project.version,
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat(),
        **state,
    }


def _project_summary(project: Project) -> dict[str, Any]:
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "source_scenario_id": project.source_scenario_id,
        "version": project.version,
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat(),
    }


def _load_project_for_llm(project_id: str) -> tuple[User, Project, Any, dict[str, Any]]:
    with get_session_factory()() as session:
        user = _active_user(session, MCP_SCOPE_LLM_USE)
        _limit_mcp(
            session,
            user,
            "mcp_llm_request",
            get_settings().llm_requests_per_minute,
        )
        project = get_project_record(session, user, project_id)
        source_id = project.source_scenario_id
        if not source_id or not (EXAMPLES_ROOT / source_id).is_dir():
            raise MCPToolUserError(
                "This project has no bundled source corpus for language model tools."
            )
        scenario = scenario_from_dict(project.scenario_json)
        bundle = compute_state_bundle(scenario)
        session.expunge(user)
        session.expunge(project)
        return user, project, scenario, bundle


def _request_id(ctx: Context) -> str:
    try:
        return str(ctx.request_id)
    except ValueError:
        return uuid4().hex


def _legacy_llm_client():
    from app.llm import make_llm_client

    return make_llm_client()


def _select_mcp_llm_client(
    *, user: User, profile: str, request_id: str, request_kind: str
):
    if not _llm_enabled():
        raise MCPToolUserError("Language model tools are disabled on this server.")
    return select_request_llm_client(
        LLMRequestOptions(profile=profile),
        user=user,
        request_id=request_id,
        request_kind=request_kind,
        legacy_factory=_legacy_llm_client,
    )


def _llm_error(exc: Exception) -> MCPToolUserError:
    translated = llm_http_exception(exc, byok=False)
    detail = translated.detail
    if isinstance(detail, dict):
        return MCPToolUserError(str(detail.get("message") or "Language model request failed."))
    return MCPToolUserError("Language model request failed.")


READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)
ADDITIVE_WRITE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=False,
    open_world_hint=False,
)
PROJECT_EDIT = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=True,
    idempotent_hint=False,
    open_world_hint=False,
)
METERED_LLM = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=False,
    open_world_hint=True,
)


_TOOL_REGISTRATIONS: list[tuple[Any, ToolAnnotations]] = []


def _mcp_tool(*, annotations: ToolAnnotations):
    def decorator(function):
        _TOOL_REGISTRATIONS.append((function, annotations))
        return function

    return decorator


@_mcp_tool(annotations=READ_ONLY)
def list_examples() -> dict[str, Any]:
    """List immutable bundled examples. Requires projects:read."""
    with _tool_boundary("list_examples"):
        with get_session_factory()() as session:
            user = _active_user(session, MCP_SCOPE_PROJECTS_READ)
            _limit_mcp_read(session, user)
            examples = []
            for child in sorted(EXAMPLES_ROOT.iterdir(), key=lambda path: path.name):
                if not child.is_dir() or not (child / "scenario.yaml").is_file():
                    continue
                try:
                    scenario = load_bundled_scenario(child.name)
                except Exception:
                    log.warning("Skipping invalid MCP example scenario_id=%s", child.name)
                    continue
                examples.append(
                    {
                        "id": child.name,
                        "title": scenario.title,
                        "description": scenario.description,
                    }
                )
            return {"examples": examples}


@_mcp_tool(annotations=READ_ONLY)
def get_example(
    scenario_id: str,
    include_argument_graph: bool = False,
) -> dict[str, Any]:
    """Read one bundled example and its grounded outcomes. Requires projects:read."""
    with _tool_boundary("get_example"):
        with get_session_factory()() as session:
            user = _active_user(session, MCP_SCOPE_PROJECTS_READ)
            _limit_mcp_read(session, user)
            scenario = load_bundled_scenario(scenario_id)
            return {
                "id": scenario_id,
                **_state_payload(
                    scenario,
                    include_argument_graph=include_argument_graph,
                ),
            }


@_mcp_tool(annotations=READ_ONLY)
def list_projects() -> dict[str, Any]:
    """List the authenticated user's private projects. Requires projects:read."""
    with _tool_boundary("list_projects"):
        with get_session_factory()() as session:
            user = _active_user(session, MCP_SCOPE_PROJECTS_READ)
            _limit_mcp_read(session, user)
            projects = list_project_records(session, user)
            return {"projects": [_project_summary(project) for project in projects]}


@_mcp_tool(annotations=READ_ONLY)
def get_project(
    project_id: str,
    include_argument_graph: bool = False,
) -> dict[str, Any]:
    """Read a private project and grounded outcomes. Requires projects:read."""
    with _tool_boundary("get_project"):
        with get_session_factory()() as session:
            user = _active_user(session, MCP_SCOPE_PROJECTS_READ)
            _limit_mcp_read(session, user)
            project = get_project_record(session, user, project_id)
            return _project_payload(
                project,
                include_argument_graph=include_argument_graph,
            )


@_mcp_tool(annotations=ADDITIVE_WRITE)
def create_project(
    name: str,
    source_scenario_id: str,
    description: str = "",
    diff_ops: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a private project from an example. Requires projects:write."""
    with _tool_boundary("create_project"):
        operations = _validated_ops(diff_ops)
        with get_session_factory()() as session:
            user = _active_user(session, MCP_SCOPE_PROJECTS_WRITE)
            _limit_mcp(
                session,
                user,
                "mcp_project_mutation",
                get_settings().mutation_requests_per_minute,
            )
            scenario = apply_ops(load_bundled_scenario(source_scenario_id), operations)
            project = create_project_record(
                session,
                user,
                name=name,
                description=description,
                scenario=scenario_to_dict(scenario),
                source_scenario_id=source_scenario_id,
            )
            return _project_payload(project)


@_mcp_tool(annotations=PROJECT_EDIT)
def apply_project_ops(
    project_id: str,
    expected_version: int,
    diff_ops: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply reviewed diff operations to a project. Requires projects:write."""
    with _tool_boundary("apply_project_ops"):
        operations = _validated_ops(diff_ops)
        if not operations:
            raise MCPToolUserError("Provide at least one diff operation.")
        with get_session_factory()() as session:
            user = _active_user(session, MCP_SCOPE_PROJECTS_WRITE)
            _limit_mcp(
                session,
                user,
                "mcp_project_mutation",
                get_settings().mutation_requests_per_minute,
            )
            current = get_project_record(session, user, project_id)
            scenario = apply_ops(scenario_from_dict(current.scenario_json), operations)
            project = update_project_record(
                session,
                user,
                project_id,
                expected_version=expected_version,
                scenario=scenario_to_dict(scenario),
            )
            return _project_payload(project)


@_mcp_tool(annotations=ADDITIVE_WRITE)
def update_project_metadata(
    project_id: str,
    expected_version: int,
    name: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Rename or describe a private project. Requires projects:write."""
    with _tool_boundary("update_project_metadata"):
        if name is None and description is None:
            raise MCPToolUserError("Provide a name or description to update.")
        with get_session_factory()() as session:
            user = _active_user(session, MCP_SCOPE_PROJECTS_WRITE)
            _limit_mcp(
                session,
                user,
                "mcp_project_mutation",
                get_settings().mutation_requests_per_minute,
            )
            project = update_project_record(
                session,
                user,
                project_id,
                expected_version=expected_version,
                name=name,
                description=description,
            )
            return _project_payload(project)


@_mcp_tool(annotations=METERED_LLM)
def ask_project(
    project_id: str,
    question: str,
    ctx: Context,
    profile: Literal["balanced"] = "balanced",
) -> dict[str, Any]:
    """Ask a grounded question about a project. Requires llm:use and trial credit."""
    with _tool_boundary("ask_project"):
        question = _bounded_text(question, "question")
        user, project, scenario, bundle = _load_project_for_llm(project_id)
        request_id = _request_id(ctx)
        client = None
        try:
            client = _select_mcp_llm_client(
                user=user,
                profile=profile,
                request_id=request_id,
                request_kind="mcp-chat",
            )
            result = run_turn(
                scenario,
                bundle["af"],
                [],
                [{"role": "user", "content": question}],
                scenario_dir=EXAMPLES_ROOT / str(project.source_scenario_id),
                client=client,
            )
        except HANDLED_LLM_ERRORS as exc:
            raise _llm_error(exc) from exc
        finally:
            close_llm_client(client)
        return {
            "message": result.text,
            "stop_reason": result.stop_reason,
            "model": result.model,
            "provider": result.provider,
            "billing_source": result.billing_source,
            "route": result.route,
            "cost_microusd": result.cost_microusd,
            "usage": result.usage,
            "latency_ms": result.latency_ms,
            "request_id": request_id,
            "retried": result.retried,
        }


@_mcp_tool(annotations=METERED_LLM)
def propose_project_edit(
    project_id: str,
    task: Literal["add-rule", "modify-rule", "add-fact", "add-assumption"],
    instruction: str,
    ctx: Context,
    existing_id: str | None = None,
    profile: Literal["balanced"] = "balanced",
) -> dict[str, Any]:
    """Propose but do not apply a project edit. Requires llm:use and trial credit."""
    with _tool_boundary("propose_project_edit"):
        instruction = _bounded_text(instruction, "instruction")
        user, project, scenario, bundle = _load_project_for_llm(project_id)
        request_id = _request_id(ctx)
        client = None
        try:
            client = _select_mcp_llm_client(
                user=user,
                profile=profile,
                request_id=request_id,
                request_kind="mcp-propose",
            )
            result = run_propose(
                scenario,
                bundle["af"],
                [],
                task=task,
                instruction=instruction,
                existing_id=existing_id,
                scenario_dir=EXAMPLES_ROOT / str(project.source_scenario_id),
                client=client,
            )
        except ProposerRetryExhausted as exc:
            raise MCPToolUserError(
                "No valid edit was produced. Rephrase the instruction and try again."
            ) from exc
        except HANDLED_LLM_ERRORS as exc:
            raise _llm_error(exc) from exc
        finally:
            close_llm_client(client)
        return {
            "project_id": project.id,
            "expected_version": project.version,
            "op": result.op,
            "reviewed": result.reviewed,
            "review_issues": [issue.to_dict() for issue in result.review_issues],
            "proposer_attempts": result.proposer_attempts,
            "model": result.model,
            "provider": result.provider,
            "billing_source": result.billing_source,
            "route": result.route,
            "cost_microusd": result.cost_microusd,
            "usage": result.usage,
            "latency_ms": result.latency_ms,
            "request_id": request_id,
            "next_step": (
                "Review the operation and issues, then call apply_project_ops with "
                "this expected_version if the edit is acceptable."
            ),
        }


@dataclass(frozen=True)
class MCPRuntime:
    server: MCPServer
    app: ASGIApp


def create_mcp_runtime() -> MCPRuntime:
    """Create a fresh SDK runtime for one ASGI application lifespan."""
    settings = get_settings()
    server = MCPServer(
        name="abda-nl",
        title="ABDA-NL",
        description=(
            "Natural-language exploration of assumption-based defeasible argumentation."
        ),
        instructions=(
            "ABDA-NL projects are private to the authenticated user. Read a project before "
            "changing it. Every write requires the current expected_version and returns a new "
            "version. Language model proposals never apply themselves and consume trial credit. "
            "Review a proposed diff, then apply it explicitly. Never send provider API keys "
            "through MCP; browser BYOK keeps keys in one request."
        ),
        website_url=settings.public_base_url,
        version="0.2.0",
    )
    for function, tool_annotations in _TOOL_REGISTRATIONS:
        server.add_tool(function, annotations=tool_annotations)
    transport_app = server.streamable_http_app(
        streamable_http_path="/",
        json_response=True,
        stateless_http=True,
        max_request_body_size=1_048_576,
        transport_security=_transport_security(),
    )
    protected_app = RequireAuthMiddleware(transport_app, required_scopes=[])
    context_app = AuthContextMiddleware(protected_app)
    authenticated_app = AuthenticationMiddleware(
        context_app,
        backend=BearerAuthBackend(DatabaseTokenVerifier()),
    )
    return MCPRuntime(server=server, app=authenticated_app)


class MCPApplicationProxy:
    """Delegate to the runtime bound by the current host lifespan."""

    def __init__(self) -> None:
        self._app: ASGIApp | None = None

    def bind(self, app: ASGIApp) -> None:
        self._app = app

    def unbind(self, app: ASGIApp) -> None:
        if self._app is app:
            self._app = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        app = self._app
        if app is None:
            response = JSONResponse(
                {"error": "mcp_unavailable", "error_description": "MCP is not running"},
                status_code=503,
            )
            await response(scope, receive, send)
            return
        await app(scope, receive, send)


mcp_http_app = MCPApplicationProxy()
