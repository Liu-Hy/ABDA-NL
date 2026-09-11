"""Scoped MCP tools over the same account and project invariants as the web API."""
from __future__ import annotations

import logging
import os
import inspect
from contextlib import contextmanager
from dataclasses import dataclass, replace
from functools import wraps
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
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from app.abda_bridge import ArgumentComplexityError, ArgumentConstructionError
from app.api.llm_access import (
    HANDLED_LLM_ERRORS,
    llm_http_exception,
    select_request_llm_client,
)
from app.api.models import DiffOp, LLMRequestOptions
from app.api.abuse import _client_subject
from app.core.config import get_settings
from app.services.scenario_submissions import list_published_scenarios, resolve_public_scenario
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
from app.scenario.materials import MaterialError
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
    ProjectValidationError,
    ShareLinkLimitError,
    create_project as create_project_record,
    get_project as get_project_record,
    list_projects as list_project_records,
    update_project as update_project_record,
)
from app.services.rate_limits import ACCOUNT_LLM_RATE_SCOPE, consume_rate_limit


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


class MCPAuthenticationRateLimitMiddleware:
    """Bound transport authentication attempts before bearer verification.

    Every transport request consumes a network slot, including valid tokens.
    No positive authentication cache is used, so revocation takes effect on the
    next allowed request. Browser token revocation uses a separate HTTP route.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        settings = get_settings()
        if scope["type"] != "http" or not settings.abuse_protection_enabled:
            await self.app(scope, receive, send)
            return
        subject = _client_subject(Request(scope), settings)

        def consume():
            with get_session_factory()() as session:
                return consume_rate_limit(
                    session, scope="mcp_transport_auth", subject=subject,
                    # Transport includes initialization and protocol messages.
                    # Keep its network ceiling distinct from per-account tools.
                    limit=max(60, settings.anonymous_requests_per_minute * 2),
                    window_seconds=60, secret=settings.session_secret,
                )

        result = await anyio.to_thread.run_sync(consume)
        if not result.allowed:
            response = JSONResponse(
                {"error": "rate_limit_exceeded", "error_description": "Too many requests. Try again later."},
                status_code=429,
                headers={"Retry-After": str(result.retry_after_seconds), "Cache-Control": "no-store"},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


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
        ProjectValidationError,
        MaterialError,
    ) as exc:
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
            ACCOUNT_LLM_RATE_SCOPE,
            get_settings().llm_requests_per_minute,
        )
        project = get_project_record(session, user, project_id)
        source_id = project.source_scenario_id
        if source_id and not (EXAMPLES_ROOT / source_id).is_dir():
            raise MCPToolUserError(
                "This scenario has no bundled source corpus for language model tools."
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
    *, user: User, profile: str | None, request_id: str, request_kind: str
):
    if not _llm_enabled():
        raise MCPToolUserError("Language model tools are disabled on this server.")
    return select_request_llm_client(
        LLMRequestOptions(profile=profile or get_settings().llm_default_profile),
        user=user,
        request_id=request_id,
        request_kind=request_kind,
        legacy_factory=_legacy_llm_client,
        # Personal MCP access is always account-funded, including on a local
        # demo whose anonymous browser LLM setting is relaxed for development.
        settings=replace(get_settings(), llm_require_auth=True),
    )


_UNCERTAIN_BILLING_NOTICE = (
    " Some usage was conservatively charged because the final provider cost is unconfirmed."
)


def _llm_error(exc: Exception, *, client=None) -> MCPToolUserError:
    uncertain = getattr(client, "settled_billing_uncertain_count", 0) > 0
    translated = llm_http_exception(exc, byok=False, billing_uncertain=uncertain)
    detail = translated.detail
    if isinstance(detail, dict):
        message = str(detail.get("message") or "Language model request failed.")
        if detail.get("billing_uncertain"):
            message += _UNCERTAIN_BILLING_NOTICE
        return MCPToolUserError(message)
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
    """List built-in and reviewed community scenarios. Requires projects:read."""
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
            examples.extend(list_published_scenarios(session))
            return {"examples": examples}


@_mcp_tool(annotations=READ_ONLY)
def get_example(
    scenario_id: str,
    include_argument_graph: bool = False,
) -> dict[str, Any]:
    """Read one built-in or community scenario and its grounded outcomes. Requires projects:read."""
    with _tool_boundary("get_example"):
        with get_session_factory()() as session:
            user = _active_user(session, MCP_SCOPE_PROJECTS_READ)
            _limit_mcp_read(session, user)
            scenario, _ = resolve_public_scenario(session, scenario_id)
            return {
                "id": scenario_id,
                **_state_payload(
                    scenario,
                    include_argument_graph=include_argument_graph,
                ),
            }


@_mcp_tool(annotations=READ_ONLY)
def list_projects() -> dict[str, Any]:
    """List the authenticated user's private scenarios. Requires projects:read."""
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
    """Read a private scenario and grounded outcomes. Requires projects:read."""
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
    diff_ops: list[DiffOp] | None = None,
) -> dict[str, Any]:
    """Create a private scenario from a built-in or community scenario. Requires projects:write; no ABDA credit."""
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
            baseline, corpus_source_id = resolve_public_scenario(session, source_scenario_id)
            scenario = apply_ops(baseline, operations)
            project = create_project_record(
                session,
                user,
                name=name,
                description=description,
                scenario=scenario_to_dict(scenario),
                source_scenario_id=corpus_source_id,
            )
            return _project_payload(project)


@_mcp_tool(annotations=PROJECT_EDIT)
def apply_project_ops(
    project_id: str,
    expected_version: int,
    diff_ops: list[DiffOp],
) -> dict[str, Any]:
    """Apply a user-approved edit at the observed version and recompute outcomes.

    Requires projects:write; no ABDA credit or server LLM. Read the project first
    to get its version and valid identifiers. Never apply a stale proposal.
    """
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
    """Rename or describe a private scenario. Requires projects:write."""
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
    profile: str | None = None,
) -> dict[str, Any]:
    """Ask the ABDA server LLM about a project. Requires llm:use and ABDA credit.

    This spends ABDA credit even with a Codex or Claude Code subscription. To
    use your client's own model without ABDA credit, read get_project instead.
    """
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
                scenario_dir=EXAMPLES_ROOT / project.source_scenario_id if project.source_scenario_id else None,
                client=client,
            )
        except HANDLED_LLM_ERRORS as exc:
            raise _llm_error(exc, client=client) from exc
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
            "billing_uncertain": bool(getattr(result, "billing_uncertain", False)),
            "resolved_model_version": getattr(result, "resolved_model_version", None),
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
    profile: str | None = None,
) -> dict[str, Any]:
    """Ask the ABDA server LLM for an edit, without applying it. Spends ABDA credit.

    Requires llm:use even with a client subscription. The client's own model can
    instead construct diff operations from get_project and apply them after
    user approval, using projects:read and projects:write without ABDA credit.
    """
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
                scenario_dir=EXAMPLES_ROOT / project.source_scenario_id if project.source_scenario_id else None,
                client=client,
            )
        except ProposerRetryExhausted as exc:
            message = "No valid edit was produced. Rephrase the instruction and try again."
            if getattr(client, "settled_billing_uncertain_count", 0):
                message += _UNCERTAIN_BILLING_NOTICE
            raise MCPToolUserError(message) from exc
        except HANDLED_LLM_ERRORS as exc:
            raise _llm_error(exc, client=client) from exc
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
            "billing_uncertain": bool(getattr(result, "billing_uncertain", False)),
            "resolved_model_version": getattr(result, "resolved_model_version", None),
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


def _catalog_profile_tool(function):
    """Expose the current shared model pool in each fresh MCP tool schema."""
    from app.llm.catalog import public_profile_ids

    signature = inspect.signature(function, eval_str=True)
    if "profile" not in signature.parameters:
        return function
    profiles = public_profile_ids()
    profile_type = Literal[profiles] | None if profiles else type(None)

    @wraps(function)
    def selected_model_tool(**kwargs):
        return function(**kwargs)

    selected_model_tool.__signature__ = signature.replace(parameters=[
        parameter.replace(annotation=profile_type)
        if parameter.name == "profile" else parameter
        for parameter in signature.parameters.values()
    ])
    return selected_model_tool


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
            "Saved ABDA-NL scenarios are private to the authenticated user. Read a private scenario before "
            "changing it. Edits require the current expected_version and return a new version. "
            "Read tools and tools that write private scenarios use no ABDA server LLM and work with zero ABDA credit. "
            "With a Codex or Claude Code subscription, use your own model to explain the returned "
            "formal outcomes or construct an edit. Show the proposed edit to the user, apply it "
            "only when authorized, and read back the changed scenario and grounded outcomes. "
            "ask_project and propose_project_edit invoke the ABDA server LLM, require llm:use, "
            "and consume ABDA credit even with a client subscription. Language model proposals "
            "never apply themselves. Never send provider API keys "
            "through MCP; browser BYOK keeps keys in one request."
        ),
        website_url=settings.public_base_url,
        version="0.3.0",
    )
    for function, tool_annotations in _TOOL_REGISTRATIONS:
        server.add_tool(_catalog_profile_tool(function), annotations=tool_annotations)
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
    return MCPRuntime(server=server, app=MCPAuthenticationRateLimitMiddleware(authenticated_app))


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
