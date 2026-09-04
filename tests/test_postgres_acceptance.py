"""Real PostgreSQL acceptance for the production database privilege boundary."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import os
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from app.cli.migrate import provision_application_role
from app.core.config import reset_settings_cache
from app.db.session import (
    _alembic_config,
    get_engine,
    get_session_factory,
    initialize_database,
    reset_database_caches,
)
from app.db.models import Identity, LLMUsageEvent, RateLimitBucket, User, utc_now
from app.scenario.catalog import load_bundled_scenario
from app.scenario.serialize import scenario_to_dict
from app.services.accounts import IdentityError, upsert_verified_identity
from app.services.llm_billing import reserve_llm_call, settle_llm_call, usage_event
from app.services.mcp_tokens import (
    MCPTokenError,
    authenticate_mcp_token,
    create_mcp_token,
    revoke_mcp_token,
)
from app.services.privacy_requests import (
    delete_privacy_account,
    prepare_privacy_deletion,
)
from app.services.projects import (
    ProjectNotFoundError,
    ShareLinkNotFoundError,
    create_project,
    create_share_link,
    resolve_share_link,
    revoke_share_link,
    update_project,
)
from app.services.rate_limits import consume_rate_limit
from app.services.trials import (
    TrialUnavailableError,
    activate_trial,
    reserve_trial_credit,
)


pytestmark = pytest.mark.skipif(
    not os.getenv("ABDA_POSTGRES_TEST_ADMIN_URL"),
    reason="set ABDA_POSTGRES_TEST_ADMIN_URL for the isolated PostgreSQL CI service",
)


def _configure_staging(monkeypatch, database_url: str) -> None:
    values = {
        "ABDA_ENVIRONMENT": "staging",
        "ABDA_AUTH_MODE": "oidc",
        "ABDA_DATABASE_URL": database_url,
        "ABDA_AUTO_CREATE_DB": "0",
        "ABDA_SESSION_SECRET": "postgres-test-session-secret-at-least-32-characters",
        "ABDA_MCP_TOKEN_PEPPER": "postgres-test-mcp-pepper-different-and-long-enough",
        "ABDA_METRICS_TOKEN": "postgres-test-metrics-token-at-least-32-characters",
        "ABDA_PUBLIC_BASE_URL": "https://staging.example.test",
        "ABDA_TRUSTED_HOSTS": "staging.example.test",
        "ABDA_OIDC_METADATA_URL": "https://identity.example.test/.well-known/openid-configuration",
        "ABDA_OIDC_ISSUER": "https://identity.example.test/",
        "ABDA_OIDC_CLIENT_ID": "postgres-test-client",
        "ABDA_OIDC_CLIENT_SECRET": "postgres-test-oidc-secret",
        "ABDA_LLM_REQUIRE_AUTH": "1",
        "ABDA_PROXY_MODE": "azure-container-apps",
        "ABDA_ABUSE_PROTECTION_ENABLED": "1",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    reset_settings_cache()
    reset_database_caches()


def _assert_statement_denied(statement: str) -> None:
    with get_engine().connect() as connection:
        transaction = connection.begin()
        try:
            with pytest.raises(DBAPIError):
                connection.execute(text(statement))
        finally:
            transaction.rollback()


def _assert_concurrent_identity_login_is_idempotent() -> None:
    suffix = uuid4().hex
    subject = f"postgres-concurrent-{suffix}"
    email = f"postgres-concurrent-{suffix}@example.edu"

    def login(_index: int) -> str:
        with get_session_factory()() as session:
            return upsert_verified_identity(
                session,
                issuer="https://identity.example.test",
                subject=subject,
                email=email,
                email_verified=True,
            ).id

    with ThreadPoolExecutor(max_workers=8) as executor:
        user_ids = list(executor.map(login, range(12)))

    assert len(set(user_ids)) == 1
    with get_session_factory()() as session:
        assert session.scalar(
            select(func.count(User.id)).where(User.email == email)
        ) == 1
        assert session.scalar(
            select(func.count(Identity.id)).where(
                Identity.issuer == "https://identity.example.test",
                Identity.subject == subject,
            )
        ) == 1

    competing_email = f"postgres-competing-{suffix}@example.edu"

    def claim_email(index: int) -> str:
        with get_session_factory()() as session:
            try:
                upsert_verified_identity(
                    session,
                    issuer="https://identity.example.test",
                    subject=f"postgres-competing-{suffix}-{index}",
                    email=competing_email,
                    email_verified=True,
                )
            except IdentityError as exc:
                return exc.code
            return "created"

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(claim_email, range(12)))

    assert results.count("created") == 1
    assert results.count("account_link_required") == 11
    with get_session_factory()() as session:
        assert session.scalar(
            select(func.count(User.id)).where(User.email == competing_email)
        ) == 1
        assert session.scalar(
            select(func.count(Identity.id)).where(
                Identity.provider_email == competing_email
            )
        ) == 1


def _assert_privacy_suspension_closes_stale_mutations() -> None:
    suffix = uuid4().hex
    email = f"postgres-suspension-{suffix}@example.edu"
    with get_session_factory()() as seed:
        user = upsert_verified_identity(
            seed,
            issuer="https://identity.example.test",
            subject=f"postgres-suspension-{suffix}",
            email=email,
            email_verified=True,
        )
        scenario = scenario_to_dict(load_bundled_scenario("fire_prevention"))
        project = create_project(
            seed,
            user,
            name="PostgreSQL suspension boundary",
            description="Must become immutable after privacy preparation",
            scenario=scenario,
            source_scenario_id="fire_prevention",
        )
        _, share_token = create_share_link(seed, user, project.id)
        activate_trial(seed, user)
        user_id = user.id
        project_id = project.id
        project_version = project.version

    stale_update = get_session_factory()()
    stale_share = get_session_factory()()
    stale_mcp = get_session_factory()()
    stale_trial = get_session_factory()()
    stale_reservation = get_session_factory()()
    try:
        update_user = stale_update.get(User, user_id)
        share_user = stale_share.get(User, user_id)
        mcp_user = stale_mcp.get(User, user_id)
        trial_user = stale_trial.get(User, user_id)
        reservation_user = stale_reservation.get(User, user_id)
        assert all((update_user, share_user, mcp_user, trial_user, reservation_user))
        for session in (
            stale_update,
            stale_share,
            stale_mcp,
            stale_trial,
            stale_reservation,
        ):
            session.commit()

        with get_session_factory()() as operator:
            prepared = prepare_privacy_deletion(
                operator,
                email,
                request_reference="POSTGRES-SUSPENSION-001",
            )
            assert prepared.status == "deletion_pending"

        with get_session_factory()() as reader:
            with pytest.raises(ShareLinkNotFoundError):
                resolve_share_link(reader, share_token)
        with pytest.raises(ProjectNotFoundError):
            update_project(
                stale_update,
                update_user,
                project_id,
                expected_version=project_version,
                name="Must not persist",
            )
        with pytest.raises(ProjectNotFoundError):
            create_share_link(stale_share, share_user, project_id)
        with pytest.raises(MCPTokenError):
            create_mcp_token(
                stale_mcp,
                mcp_user,
                name="Must not exist",
                pepper=os.environ["ABDA_MCP_TOKEN_PEPPER"],
            )
        with pytest.raises(TrialUnavailableError):
            activate_trial(stale_trial, trial_user)
        with pytest.raises(TrialUnavailableError):
            reserve_trial_credit(
                stale_reservation,
                user_id,
                amount_microusd=1_000,
                provider="foundry",
                model="claude-sonnet-4-6",
                request_kind="chat",
            )
    finally:
        stale_update.close()
        stale_share.close()
        stale_mcp.close()
        stale_trial.close()
        stale_reservation.close()

    with get_session_factory()() as operator:
        receipt = delete_privacy_account(
            operator,
            email,
            request_reference="POSTGRES-SUSPENSION-001",
        )
        assert receipt.deleted_project_count == 1


def test_restricted_role_supports_application_flows_but_not_ddl(monkeypatch):
    import app.services.rate_limits as rate_limits_module

    admin_url = os.environ["ABDA_POSTGRES_TEST_ADMIN_URL"]
    app_password = os.environ["ABDA_POSTGRES_TEST_APP_PASSWORD"]
    app_login = "abda_app"

    command.upgrade(_alembic_config(admin_url), "head")
    provision_application_role(admin_url, app_login, app_password)
    app_url = make_url(admin_url).set(username=app_login, password=app_password)
    _configure_staging(
        monkeypatch,
        app_url.render_as_string(hide_password=False),
    )

    try:
        initialize_database()
        _assert_concurrent_identity_login_is_idempotent()
        _assert_privacy_suspension_closes_stale_mutations()
        with get_session_factory()() as session:
            user = upsert_verified_identity(
                session,
                issuer="https://identity.example.test",
                subject="postgres-acceptance-user",
                email="postgres-acceptance@example.edu",
                email_verified=True,
                display_name="PostgreSQL Acceptance",
            )
            assert activate_trial(session, user).granted_microusd == 5_000_000
            scenario = scenario_to_dict(load_bundled_scenario("fire_prevention"))
            project = create_project(
                session,
                user,
                name="PostgreSQL acceptance",
                description="Restricted role CRUD verification",
                scenario=scenario,
                source_scenario_id="fire_prevention",
            )
            share, raw_share = create_share_link(session, user, project.id)
            assert share.project_id == project.id
            assert raw_share
            assert resolve_share_link(session, raw_share).id == project.id
            project = update_project(
                session,
                user,
                project.id,
                expected_version=project.version,
                description="Restricted role update verification",
            )
            assert project.version == 2
            revoke_share_link(session, user, project.id, share.id)
            with pytest.raises(ShareLinkNotFoundError):
                resolve_share_link(session, raw_share)
            active_share, active_raw_share = create_share_link(
                session,
                user,
                project.id,
            )
            assert active_share.project_id == project.id
            assert resolve_share_link(session, active_raw_share).id == project.id
            token, raw_token = create_mcp_token(
                session,
                user,
                name="PostgreSQL acceptance",
                pepper=os.environ["ABDA_MCP_TOKEN_PEPPER"],
            )
            assert token.user_id == user.id
            assert raw_token.startswith("abda_mcp_")
            principal = authenticate_mcp_token(
                session,
                raw_token,
                pepper=os.environ["ABDA_MCP_TOKEN_PEPPER"],
            )
            assert principal is not None
            assert principal.user_id == user.id
            revoke_mcp_token(session, user, token.id)
            assert (
                authenticate_mcp_token(
                    session,
                    raw_token,
                    pepper=os.environ["ABDA_MCP_TOKEN_PEPPER"],
                )
                is None
            )
            active_token, active_raw_token = create_mcp_token(
                session,
                user,
                name="PostgreSQL privacy preparation",
                pepper=os.environ["ABDA_MCP_TOKEN_PEPPER"],
            )
            assert active_token.user_id == user.id
            assert (
                authenticate_mcp_token(
                    session,
                    active_raw_token,
                    pepper=os.environ["ABDA_MCP_TOKEN_PEPPER"],
                )
                is not None
            )
            rate_limit_now = utc_now()
            session.add(
                RateLimitBucket(
                    key="expired-postgres-acceptance",
                    scope="postgres-test",
                    request_count=1,
                    window_started_at=rate_limit_now - timedelta(minutes=2),
                    expires_at=rate_limit_now - timedelta(minutes=1),
                )
            )
            session.commit()
            monkeypatch.setattr(
                rate_limits_module, "_next_rate_limit_cleanup_monotonic", 0.0
            )
            assert consume_rate_limit(
                session,
                scope="postgres-test",
                subject=user.id,
                limit=2,
                window_seconds=60,
                secret=os.environ["ABDA_SESSION_SECRET"],
                now=rate_limit_now,
            ).allowed
            assert session.get(RateLimitBucket, "expired-postgres-acceptance") is None
            assert session.scalar(
                select(func.count(RateLimitBucket.key)).where(
                    RateLimitBucket.scope == "postgres-test"
                )
            ) == 1
            reservation = reserve_llm_call(
                session,
                user_id=user.id,
                amount_microusd=100,
                provider="test",
                route="postgres-acceptance",
                model="test-model",
                request_kind="postgres-acceptance",
                charge_trial=True,
                charge_emergency=False,
            )
            settle_llm_call(
                session,
                reservation,
                actual_microusd=25,
                event=usage_event(
                    request_id="postgres-acceptance",
                    user_id=user.id,
                    provider="test",
                    route="postgres-acceptance",
                    model="test-model",
                    billing_source="trial",
                    request_kind="postgres-acceptance",
                    status="succeeded",
                    usage={"input_tokens": 1, "output_tokens": 1},
                    cost_microusd=25,
                ),
            )
            prepared = prepare_privacy_deletion(
                session,
                "postgres-acceptance@example.edu",
                request_reference="POSTGRES-PRIVACY-001",
            )
            assert prepared.status == "deletion_pending"
            assert prepared.active_mcp_token_count == 0
            assert (
                authenticate_mcp_token(
                    session,
                    active_raw_token,
                    pepper=os.environ["ABDA_MCP_TOKEN_PEPPER"],
                )
                is None
            )
            with pytest.raises(ShareLinkNotFoundError):
                resolve_share_link(session, active_raw_share)
            receipt = delete_privacy_account(
                session,
                "postgres-acceptance@example.edu",
                request_reference="POSTGRES-PRIVACY-001",
            )
            assert receipt.deleted_project_count == 1
            assert session.get(User, user.id) is None
            assert (
                session.scalar(
                    select(LLMUsageEvent.user_id).where(
                        LLMUsageEvent.request_id == "postgres-acceptance"
                    )
                )
                is None
            )

        _assert_statement_denied("CREATE TABLE public.abda_privilege_probe (id integer)")
        _assert_statement_denied("CREATE TEMP TABLE abda_temp_probe (id integer)")
        _assert_statement_denied("ALTER TABLE users ADD COLUMN abda_privilege_probe integer")
        _assert_statement_denied("CREATE ROLE abda_privilege_probe")
    finally:
        reset_database_caches()
        reset_settings_cache()
