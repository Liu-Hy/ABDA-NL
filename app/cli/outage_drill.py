"""Operator-only, isolated OpenRouter outage-fallback acceptance drill."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from typing import Any, Sequence
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.db.models import (
    EmergencyBudget,
    EmergencyUsageReservation,
    LLMUsageEvent,
    UsageReservation,
    User,
)
from app.db.session import database_is_ready, get_session_factory
from app.llm.client import LLMResponse, ToolCallResponse
from app.llm.providers import LLMProviderError
from app.llm.routing import CallContext, CircuitRegistry, FailoverClient, LLMRouter
from app.services.accounts import IdentityError, normalize_email
from app.services.emergency_budget import get_emergency_balance
from app.services.trials import get_trial_balance


_EMAIL_ENV = "ABDA_OUTAGE_DRILL_USER_EMAIL"
_CONFIRMATION_ENV = "ABDA_OUTAGE_DRILL_CONFIRMATION"
_CONFIRMATION = "RUN_STAGING_OPENROUTER_OUTAGE_DRILL"
_PROFILE_ID = "balanced"
_PRIMARY_ROUTE = "cloudbank-claude-sonnet-4-6"
_FALLBACK_ROUTE = "openrouter-gemini-3.7-flash"
_REQUEST_KIND_PREFIX = "outage-drill"
_RESPONSE_MARKER = "ABDA_NL_OPENROUTER_DRILL_OK"
_MAX_TOKENS = 32


class OutageDrillError(RuntimeError):
    """A safe precondition or postcondition for the outage drill failed."""


class _ForcedQualifyingOutage:
    """A zero-cost primary that exercises the real FailoverClient transition."""

    model = "claude-sonnet-4-6"
    provider = "azure-foundry"
    billing_source = "cloudbank"
    route = _PRIMARY_ROUTE

    @staticmethod
    def _raise() -> None:
        raise LLMProviderError(
            "operator-injected qualifying staging outage",
            provider="azure-foundry",
            status_code=503,
            retryable=True,
            outage_candidate=True,
            error_type="operator_outage_drill",
        )

    def complete(self, **_kwargs: Any) -> LLMResponse:
        self._raise()
        raise AssertionError("the forced outage unexpectedly returned")

    def tool_call(self, **_kwargs: Any) -> ToolCallResponse:
        self._raise()
        raise AssertionError("the forced outage unexpectedly returned")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="abda-nl-outage-drill",
        description=(
            "Dry-run or execute one isolated staging OpenRouter fallback and "
            "combined-ledger acceptance drill"
        ),
    )
    parser.add_argument(
        "--expected-origin",
        required=True,
        help="exact HTTPS staging origin expected in ABDA_PUBLIC_BASE_URL",
    )
    parser.add_argument(
        "--email-env",
        default=_EMAIL_ENV,
        help="environment variable containing an active trial user's verified email",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="perform one paid fallback call after the exact confirmation",
    )
    return parser


def _email_from_environment(name: str) -> str:
    value = os.getenv(name)
    if value:
        return value
    if sys.stdin.isatty():
        return getpass.getpass("Verified ABDA-NL trial account email: ")
    raise OutageDrillError(
        f"set {name} or run interactively so the account email never enters shell history"
    )


def _require_confirmation() -> None:
    supplied = (os.getenv(_CONFIRMATION_ENV) or "").strip()
    if supplied == _CONFIRMATION:
        return
    if sys.stdin.isatty():
        supplied = input(f"Type {_CONFIRMATION} to run one paid staging call: ").strip()
    if supplied != _CONFIRMATION:
        raise OutageDrillError(
            f"set {_CONFIRMATION_ENV} to the exact value {_CONFIRMATION!r} "
            "or type it at the interactive prompt"
        )


def _json_ready(value: dict[str, Any]) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)


def _validate_settings(settings: Settings, expected_origin: str) -> None:
    normalized_origin = expected_origin.strip().rstrip("/")
    if settings.environment != "staging":
        raise OutageDrillError("the outage drill is restricted to ABDA_ENVIRONMENT=staging")
    if normalized_origin != settings.public_base_url:
        raise OutageDrillError("the expected origin does not match ABDA_PUBLIC_BASE_URL")
    if settings.openrouter_failover_enabled:
        raise OutageDrillError(
            "public OpenRouter failover must remain disabled during the isolated drill"
        )
    if not (os.getenv("OPENROUTER_API_KEY") or "").strip():
        raise OutageDrillError("the OpenRouter credential is not configured")


def _validated_routes(router: LLMRouter) -> tuple[str, str]:
    profile = router.catalog.profiles.get(_PROFILE_ID)
    if profile is None or not profile.public_ready:
        raise OutageDrillError("the balanced profile is not public-ready")
    if profile.primary_route != _PRIMARY_ROUTE:
        raise OutageDrillError("the balanced primary route changed")
    if profile.fallback_route != _FALLBACK_ROUTE:
        raise OutageDrillError("the balanced fallback route changed")
    primary = router.catalog.routes[_PRIMARY_ROUTE]
    fallback = router.catalog.routes[_FALLBACK_ROUTE]
    if primary.provider != "azure-foundry" or primary.billing_source != "cloudbank":
        raise OutageDrillError("the expected CloudBank primary route changed")
    if fallback.provider != "openrouter" or fallback.billing_source != "openrouter-emergency":
        raise OutageDrillError("the expected OpenRouter emergency route changed")
    return primary.id, fallback.id


def _active_trial_user(session: Session, email: str) -> User:
    normalized = normalize_email(email)
    user = session.scalar(select(User).where(User.email == normalized))
    if user is None:
        raise OutageDrillError("the verified trial account was not found")
    if not user.email_verified or user.status != "active":
        raise OutageDrillError("the trial account is not active and email-verified")
    trial = get_trial_balance(session, user.id)
    if not trial.active:
        raise OutageDrillError("the account has not activated funded trial credit")
    if trial.reserved_microusd:
        raise OutageDrillError("the trial account has an in-flight usage reservation")
    if trial.available_microusd < 25_000:
        raise OutageDrillError("the trial account needs at least $0.025 available for the drill")
    return user


def _snapshot(
    factory: sessionmaker[Session],
    email: str,
) -> tuple[str, dict[str, int | bool]]:
    with factory() as session:
        user = _active_trial_user(session, email)
        trial = get_trial_balance(session, user.id)
        emergency = get_emergency_balance(session)
        pending_emergency = session.scalar(
            select(func.count(EmergencyUsageReservation.id)).where(
                EmergencyUsageReservation.status == "pending"
            )
        )
        if emergency.enabled:
            raise OutageDrillError("the emergency budget is already enabled")
        if emergency.reserved_microusd or pending_emergency:
            raise OutageDrillError("the emergency budget has an in-flight reservation")
        return user.id, {
            "trial_spent_microusd": trial.spent_microusd,
            "trial_reserved_microusd": trial.reserved_microusd,
            "trial_available_microusd": trial.available_microusd,
            "openrouter_enabled": emergency.enabled,
            "openrouter_budget_microusd": emergency.hard_limit_microusd,
            "openrouter_spent_microusd": emergency.spent_microusd,
            "openrouter_reserved_microusd": emergency.reserved_microusd,
        }


def _set_emergency_enabled(
    factory: sessionmaker[Session],
    *,
    enabled: bool,
    expected_current: bool,
) -> None:
    with factory() as session:
        budget = session.scalar(
            select(EmergencyBudget).where(EmergencyBudget.key == "openrouter").with_for_update()
        )
        if budget is None:
            raise OutageDrillError("the OpenRouter emergency budget is not configured")
        if budget.enabled is not expected_current:
            raise OutageDrillError("the emergency budget changed during the outage drill")
        budget.enabled = enabled
        session.commit()


def _audit_execution(
    factory: sessionmaker[Session],
    *,
    user_id: str,
    request_id: str,
    request_kind: str,
    before: dict[str, int | bool],
    response: LLMResponse,
) -> dict[str, int | bool]:
    with factory() as session:
        trial = get_trial_balance(session, user_id)
        emergency = get_emergency_balance(session)
        events = list(
            session.scalars(select(LLMUsageEvent).where(LLMUsageEvent.request_id == request_id))
        )
        trial_reservations = list(
            session.scalars(
                select(UsageReservation).where(
                    UsageReservation.user_id == user_id,
                    UsageReservation.request_kind == request_kind,
                )
            )
        )
        emergency_reservations = list(
            session.scalars(
                select(EmergencyUsageReservation).where(
                    EmergencyUsageReservation.user_id == user_id,
                    EmergencyUsageReservation.request_kind == request_kind,
                )
            )
        )

    if not trial_reservations or len(trial_reservations) != len(emergency_reservations):
        raise OutageDrillError("the drill did not create matching ledger reservations")
    if any(item.status == "pending" for item in trial_reservations):
        raise OutageDrillError("a trial outage-drill reservation remained pending")
    if any(item.status == "pending" for item in emergency_reservations):
        raise OutageDrillError("an emergency outage-drill reservation remained pending")
    trial_recorded_cost = sum(item.actual_microusd or 0 for item in trial_reservations)
    emergency_recorded_cost = sum(item.actual_microusd or 0 for item in emergency_reservations)
    event_recorded_cost = sum(event.cost_microusd for event in events)
    if (
        trial_recorded_cost <= 0
        or trial_recorded_cost != emergency_recorded_cost
        or trial_recorded_cost != event_recorded_cost
    ):
        raise OutageDrillError("the per-call trial, emergency, and event costs differ")

    successful = [event for event in events if event.status == "succeeded"]
    if len(successful) != 1:
        raise OutageDrillError("the fallback did not produce exactly one successful usage event")
    event = successful[0]
    if (
        event.provider != "openrouter"
        or event.route != _FALLBACK_ROUTE
        or event.billing_source != "openrouter-emergency"
        or event.request_kind != request_kind
    ):
        raise OutageDrillError("the successful usage event is not the expected fallback route")
    if event.cost_microusd <= 0 or response.cost_microusd != event.cost_microusd:
        raise OutageDrillError("the fallback did not record a positive settled provider cost")
    if trial.spent_microusd < int(before["trial_spent_microusd"]) + trial_recorded_cost:
        raise OutageDrillError("the trial ledger did not retain the drill cost")
    if emergency.spent_microusd < (
        int(before["openrouter_spent_microusd"]) + emergency_recorded_cost
    ):
        raise OutageDrillError("the emergency ledger did not retain the drill cost")
    if emergency.reserved_microusd:
        raise OutageDrillError("an emergency budget reservation remained after the outage drill")
    if emergency.enabled:
        raise OutageDrillError("the temporary emergency budget switch was not restored")
    return {
        "settled_cost_microusd": event.cost_microusd,
        "trial_recorded_cost_microusd": trial_recorded_cost,
        "openrouter_recorded_cost_microusd": emergency_recorded_cost,
        "provider_attempt_count": len(events),
        "trial_reserved_microusd": trial.reserved_microusd,
        "openrouter_reserved_microusd": emergency.reserved_microusd,
        "openrouter_enabled_restored": not emergency.enabled,
    }


def _run(args: argparse.Namespace) -> dict[str, Any]:
    settings = get_settings()
    _validate_settings(settings, args.expected_origin)
    if not database_is_ready():
        raise OutageDrillError("the configured ABDA-NL database is not ready")
    factory = get_session_factory()
    router = LLMRouter(settings=settings, session_factory=factory)
    primary_route, fallback_route = _validated_routes(router)
    email = _email_from_environment(args.email_env)
    user_id, before = _snapshot(factory, email)
    if before["openrouter_budget_microusd"] != settings.openrouter_budget_microusd:
        raise OutageDrillError("the database and deployment OpenRouter budgets differ")
    planned = {
        "action": "openrouter-outage-drill",
        "environment": settings.environment,
        "public_origin": settings.public_base_url,
        "profile": _PROFILE_ID,
        "primary_route": primary_route,
        "injected_primary_status": 503,
        "fallback_route": fallback_route,
        "max_output_tokens": _MAX_TOKENS,
        "before": before,
    }
    if not args.execute:
        return {
            **planned,
            "confirmation": _CONFIRMATION,
            "mutated": False,
            "result": "DRY_RUN_READY",
        }

    _require_confirmation()
    drill_nonce = uuid.uuid4().hex
    request_id = f"outage-drill-{drill_nonce}"
    request_kind = f"{_REQUEST_KIND_PREFIX}-{drill_nonce[:12]}"
    context = CallContext(
        user_id=user_id,
        request_id=request_id,
        request_kind=request_kind,
        charge_trial=True,
    )
    fallback = router.evaluation_route(
        fallback_route,
        context=context,
        allow_emergency_spend=True,
    )
    client = FailoverClient(
        _ForcedQualifyingOutage(),
        fallback,
        cooldown_seconds=settings.llm_circuit_cooldown_seconds,
        circuits=CircuitRegistry(),
    )

    _set_emergency_enabled(factory, enabled=True, expected_current=False)
    try:
        response = client.complete(
            system=(
                "This is an ABDA-NL service connectivity drill. Reply with exactly "
                f"{_RESPONSE_MARKER} and no other text."
            ),
            messages=[
                {
                    "role": "user",
                    "content": f"Return exactly: {_RESPONSE_MARKER}",
                }
            ],
            max_tokens=_MAX_TOKENS,
            cache=False,
        )
    finally:
        _set_emergency_enabled(factory, enabled=False, expected_current=True)

    if response.route != fallback_route or response.provider != "openrouter":
        raise OutageDrillError("the forced outage did not return through OpenRouter")
    if _RESPONSE_MARKER not in response.text:
        raise OutageDrillError("the OpenRouter response did not contain the drill marker")
    audit = _audit_execution(
        factory,
        user_id=user_id,
        request_id=request_id,
        request_kind=request_kind,
        before=before,
        response=response,
    )
    return {
        **planned,
        "request_id": request_id,
        "marker_verified": True,
        "audit": audit,
        "mutated": True,
        "result": "OPENROUTER_OUTAGE_DRILL_PASSED",
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = _run(args)
    except (OutageDrillError, IdentityError) as exc:
        print(f"outage drill refused: {exc}", file=sys.stderr)
        return 1
    except LLMProviderError:
        print("outage drill failed: the provider request did not complete", file=sys.stderr)
        return 1
    except Exception:
        print(
            "outage drill failed; inspect private application logs before retrying",
            file=sys.stderr,
        )
        return 1
    print(_json_ready(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
