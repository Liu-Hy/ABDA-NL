"""Real PostgreSQL acceptance for the production database privilege boundary."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from dataclasses import replace
import os
from threading import Barrier, Event
import time
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from app.cli.migrate import provision_application_role
from app.core.config import get_settings, reset_settings_cache
from app.services.scenario_submissions import submit_scenario, public_id, resolve_public_scenario
from app.db.session import (
    _alembic_config,
    get_engine,
    get_session_factory,
    initialize_database,
    reset_database_caches,
)
from app.db.models import (
    CreditEligibilityMarker, EmergencyBudget, EmergencyUsageReservation, Identity,
    LLMUsageEvent, Project, RateLimitBucket, ShareLink, TrialGrant, TrialProgram, UsageReservation, User, utc_now,
)
from app.scenario.catalog import load_bundled_scenario
from app.scenario.serialize import scenario_to_dict
from app.services.accounts import IdentityError, upsert_verified_identity
from app.services.credit_eligibility import (
    claim_credit_eligibility, initialize_credit_eligibility, remember_granted_identity,
)
from app.services.llm_billing import (
    reconcile_stale_llm_reservations, release_llm_call, reserve_llm_call, settle_llm_call, usage_event,
)
from app.services.mcp_tokens import (
    MCPTokenError,
    authenticate_mcp_token,
    create_mcp_token,
    revoke_mcp_token,
)
from app.services.privacy_requests import (
    PrivacyDeletionNotReadyError,
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
    AutomaticCreditUnavailableError,
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
        "ABDA_CREDIT_ELIGIBILITY_PEPPER": "postgres-test-stable-eligibility-pepper-distinct-and-long",
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


def _concurrent_database_calls(action, *, workers: int = 4):
    """Exercise independent transactions, with bounded waits if locking regresses."""
    barrier = Barrier(workers)

    def invoke(index: int):
        with get_session_factory()() as session:
            session.execute(text("SET LOCAL lock_timeout = '5s'"))
            session.execute(text("SET LOCAL statement_timeout = '10s'"))
            barrier.wait(timeout=10)
            return action(session, index)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        return list(executor.map(invoke, range(workers)))


def _assert_concurrent_eligibility_claim_and_deletion_preserve_lifetime_limit() -> None:
    suffix = uuid4().hex
    email = f"postgres-eligibility-{suffix}@example.edu"
    with get_session_factory()() as session:
        program = session.get(TrialProgram, "global")
        before = (program.activation_count, program.allocated_microusd)
        user = upsert_verified_identity(
            session, issuer="https://identity.example.test", subject=f"eligibility-{suffix}",
            email=email, email_verified=True,
        )
        user_id = user.id

    def claim(session, _index):
        # Call the marker service directly so an outer account lock cannot
        # hide races between PostgreSQL's absent-row upserts.
        claim_credit_eligibility(session, session.get(User, user_id))
        session.commit()

    _concurrent_database_calls(claim)
    with get_session_factory()() as session:
        markers = list(session.scalars(select(CreditEligibilityMarker).where(
            CreditEligibilityMarker.user_id == user_id,
        )))
        retained = {marker.digest for marker in markers}
        assert len(markers) == 2
        assert {marker.kind for marker in markers} == {"email", "identity"}

    def activate(session, _index):
        return activate_trial(session, session.get(User, user_id)).granted_microusd

    assert _concurrent_database_calls(activate) == [5_000_000] * 4
    with get_session_factory()() as session:
        assert session.scalar(select(func.count(TrialGrant.user_id)).where(
            TrialGrant.user_id == user_id,
        )) == 1
        prepare_privacy_deletion(session, email, request_reference="POSTGRES-ELIGIBILITY-001")
        receipt = delete_privacy_account(
            session, email, request_reference="POSTGRES-ELIGIBILITY-001",
        )
        assert receipt.retained_credit_eligibility_marker_count == 2
        assert session.get(User, user_id) is None
        assert all(marker.user_id is None for marker in session.scalars(
            select(CreditEligibilityMarker).where(CreditEligibilityMarker.digest.in_(retained)),
        ))
        replacement = upsert_verified_identity(
            session, issuer="https://new-identity.example.test", subject=f"replacement-{suffix}",
            email=email, email_verified=True,
        )
        replacement_id = replacement.id
        assert replacement.status == "active"

    def repeat(session, _index):
        try:
            activate_trial(session, session.get(User, replacement_id))
        except AutomaticCreditUnavailableError as exc:
            return exc.code
        pytest.fail("a deleted grantee received another introductory allocation")

    assert _concurrent_database_calls(repeat) == ["introductory_credit_already_used"] * 4
    with get_session_factory()() as session:
        program = session.get(TrialProgram, "global")
        assert (program.activation_count, program.allocated_microusd) == (
            before[0] + 1, before[1] + 5_000_000,
        )
        assert session.get(TrialGrant, replacement_id) is None
        assert session.scalar(select(func.count(CreditEligibilityMarker.digest)).where(
            CreditEligibilityMarker.user_id == replacement_id,
        )) == 0
        assert set(session.scalars(select(CreditEligibilityMarker.digest).where(
            CreditEligibilityMarker.digest.in_(retained),
            CreditEligibilityMarker.user_id.is_(None),
        ))) == retained


def _assert_concurrent_stale_sweeps_conserve_both_ledgers() -> None:
    suffix = uuid4().hex
    expired = []
    user_ids = []
    with get_session_factory()() as session:
        emergency = session.get(EmergencyBudget, "openrouter")
        was_enabled = emergency.enabled
        emergency.enabled = True
        emergency_before = emergency.spent_microusd
        program_before = session.get(TrialProgram, "global").spent_microusd
        session.commit()
        for index, amount in enumerate((100, 120)):
            user = upsert_verified_identity(
                session, issuer="https://identity.example.test", subject=f"sweep-{suffix}-{index}",
                email=f"postgres-sweep-{suffix}-{index}@example.edu", email_verified=True,
            )
            activate_trial(session, user)
            user_ids.append(user.id)
            reservation = reserve_llm_call(
                session, user_id=user.id, amount_microusd=amount, provider="test",
                route="postgres-sweep", model="test-model", request_kind="postgres-sweep",
                charge_trial=True, charge_emergency=True,
            )
            session.get(UsageReservation, reservation.trial_reservation_id).expires_at = (
                utc_now() - timedelta(minutes=1)
            )
            session.get(EmergencyUsageReservation, reservation.emergency_reservation_id).expires_at = (
                utc_now() - timedelta(minutes=1)
            )
            session.commit()
            expired.append(reservation)
        pending = reserve_llm_call(
            session, user_id=user_ids[0], amount_microusd=80, provider="test",
            route="postgres-sweep", model="test-model", request_kind="postgres-sweep",
            charge_trial=True, charge_emergency=True,
        )
        assert reconcile_stale_llm_reservations(session, apply=False) == (2, 2)
        assert session.get(TrialProgram, "global").spent_microusd == program_before
        emergency = session.get(EmergencyBudget, "openrouter")
        assert (emergency.spent_microusd, emergency.reserved_microusd) == (emergency_before, 300)

    results = _concurrent_database_calls(
        lambda session, _index: reconcile_stale_llm_reservations(session), workers=2,
    )
    assert sorted(results) == [(0, 0), (2, 2)]
    with get_session_factory()() as session:
        for reservation in expired:
            trial = session.get(UsageReservation, reservation.trial_reservation_id)
            emergency_reservation = session.get(EmergencyUsageReservation, reservation.emergency_reservation_id)
            for row in (trial, emergency_reservation):
                assert row.status == "expired_charged"
                assert row.actual_microusd == reservation.amount_microusd
        for model, reservation_id in (
            (UsageReservation, pending.trial_reservation_id),
            (EmergencyUsageReservation, pending.emergency_reservation_id),
        ):
            assert session.get(model, reservation_id).status == "pending"
        grant = session.get(TrialGrant, user_ids[0])
        assert (grant.spent_microusd, grant.reserved_microusd) == (100, 80)
        grant = session.get(TrialGrant, user_ids[1])
        assert (grant.spent_microusd, grant.reserved_microusd) == (120, 0)
        assert session.get(TrialProgram, "global").spent_microusd == program_before + 220
        emergency = session.get(EmergencyBudget, "openrouter")
        assert (emergency.spent_microusd, emergency.reserved_microusd) == (emergency_before + 220, 80)
        # Unexpired work can still settle normally after concurrent sweeps.
        settle_llm_call(session, pending, actual_microusd=20, event=usage_event(
            request_id="postgres-sweep", user_id=user_ids[0], provider="test",
            route="postgres-sweep", model="test-model", billing_source="trial",
            request_kind="postgres-sweep", status="succeeded", cost_microusd=20,
        ))
        assert reconcile_stale_llm_reservations(session) == (0, 0)
        assert session.get(TrialProgram, "global").spent_microusd == program_before + 240
        emergency = session.get(EmergencyBudget, "openrouter")
        assert (emergency.spent_microusd, emergency.reserved_microusd) == (emergency_before + 240, 0)
        emergency.enabled = was_enabled
        session.commit()


def _wait_for_blocked_worker(session, *, owner_pid, worker_pid, future) -> None:
    deadline = time.monotonic() + 5
    while owner_pid not in session.scalar(
        text("SELECT pg_blocking_pids(:pid)"), {"pid": worker_pid},
    ):
        if future.done():
            future.result()
            pytest.fail("the worker bypassed the held account lock")
        assert time.monotonic() < deadline, "the worker did not wait for the account lock"
        time.sleep(0.01)


def _assert_finalization_and_privacy_deletion_use_consistent_account_locks() -> None:
    """A finalizer must not hold the grant while waiting for deletion's User lock."""
    for disposition in ("settle", "release"):
        suffix = uuid4().hex
        email = f"postgres-finalize-{suffix}@example.edu"
        request_id = f"postgres-finalize-{suffix}"
        with get_session_factory()() as session:
            user = upsert_verified_identity(
                session, issuer="https://identity.example.test", subject=f"finalize-{suffix}",
                email=email, email_verified=True,
            )
            activate_trial(session, user)
            user_id = user.id
            reservation = reserve_llm_call(
                session, user_id=user_id, amount_microusd=100, provider="test",
                route="postgres-finalization", model="test-model", request_kind="postgres-finalization",
                charge_trial=True, charge_emergency=False,
            )
            prepare_privacy_deletion(session, email, request_reference="POSTGRES-FINALIZATION-001")

        started = Event()
        worker = {}

        def finalize(worker, started, request_id, user_id, disposition, reservation):
            with get_session_factory()() as session:
                session.execute(text("SET LOCAL lock_timeout = '10s'"))
                session.execute(text("SET LOCAL statement_timeout = '15s'"))
                worker["pid"] = session.scalar(text("SELECT pg_backend_pid()"))
                started.set()
                event = usage_event(
                    request_id=request_id, user_id=user_id, provider="test",
                    route="postgres-finalization", model="test-model", billing_source="trial",
                    request_kind="postgres-finalization", status="succeeded" if disposition == "settle" else "failed",
                    cost_microusd=25 if disposition == "settle" else 0,
                )
                if disposition == "settle":
                    settle_llm_call(session, reservation, actual_microusd=25, event=event)
                else:
                    release_llm_call(session, reservation, event=event)

        with get_session_factory()() as deletion, ThreadPoolExecutor(max_workers=1) as executor:
            deletion.execute(text("SET LOCAL statement_timeout = '10s'"))
            deletion.scalar(select(User).where(User.id == user_id).with_for_update())
            owner_pid = deletion.scalar(text("SELECT pg_backend_pid()"))
            future = executor.submit(finalize, worker, started, request_id, user_id, disposition, reservation)
            try:
                assert started.wait(timeout=5), "the finalization worker did not start"
                _wait_for_blocked_worker(
                    deletion, owner_pid=owner_pid, worker_pid=worker["pid"], future=future,
                )
                # With the old order the worker holds the grant and waits on
                # User through its usage-event FK. This deletion then deadlocks.
                # With account-first locking it sees pending work and rolls back,
                # which releases the worker to finish the existing reservation.
                with pytest.raises(PrivacyDeletionNotReadyError, match="unsettled"):
                    delete_privacy_account(
                        deletion, email, request_reference="POSTGRES-FINALIZATION-001",
                    )
            finally:
                deletion.rollback()
            future.result(timeout=10)

        with get_session_factory()() as session:
            grant = session.get(TrialGrant, user_id)
            expected_cost = 25 if disposition == "settle" else 0
            assert (grant.spent_microusd, grant.reserved_microusd) == (expected_cost, 0)
            row = session.get(UsageReservation, reservation.trial_reservation_id)
            assert row.status == ("settled" if disposition == "settle" else "released")
            assert session.scalar(select(LLMUsageEvent.cost_microusd).where(
                LLMUsageEvent.request_id == request_id,
            )) == expected_cost
            receipt = delete_privacy_account(
                session, email, request_reference="POSTGRES-FINALIZATION-001",
            )
            assert receipt.retained_trial_spent_microusd == expected_cost


def _assert_startup_seeding_and_sign_in_do_not_invert_marker_fk_locks() -> None:
    suffix = uuid4().hex
    email = f"postgres-marker-new-{suffix}@example.edu"
    with get_session_factory()() as session:
        user = upsert_verified_identity(
            session, issuer="https://identity.example.test", subject=f"marker-{suffix}",
            email=f"postgres-marker-old-{suffix}@example.edu", email_verified=True,
        )
        activate_trial(session, user)
        user_id = user.id
        retained = set(session.scalars(select(CreditEligibilityMarker.digest).where(
            CreditEligibilityMarker.user_id == user_id,
        )))
        assert len(retained) == 2
        # Sign-in commits the verified identity update before ensuring credit.
        # Stage that boundary, where the new email does not have a marker yet.
        user.email = email
        identity = session.scalar(select(Identity).where(Identity.user_id == user_id))
        identity.provider_email = email
        session.commit()

    started = Event()
    worker = {}

    def seed():
        with get_session_factory()() as session:
            session.execute(text("SET LOCAL lock_timeout = '10s'"))
            session.execute(text("SET LOCAL statement_timeout = '15s'"))
            worker["pid"] = session.scalar(text("SELECT pg_backend_pid()"))
            started.set()
            initialize_credit_eligibility(session)
            session.commit()

    with get_session_factory()() as sign_in, ThreadPoolExecutor(max_workers=1) as executor:
        sign_in.execute(text("SET LOCAL statement_timeout = '10s'"))
        user = sign_in.scalar(select(User).where(User.id == user_id).with_for_update())
        owner_pid = sign_in.scalar(text("SELECT pg_backend_pid()"))
        future = executor.submit(seed)
        try:
            assert started.wait(timeout=5), "the eligibility initializer did not start"
            _wait_for_blocked_worker(
                sign_in, owner_pid=owner_pid, worker_pid=worker["pid"], future=future,
            )
            # The previous initializer inserted the new unique marker before
            # waiting on its User FK. Sign-in then waited on that marker and
            # deadlocked. Account-first seeding leaves the marker free to claim.
            remember_granted_identity(sign_in, user)
            sign_in.commit()
        finally:
            sign_in.rollback()
        future.result(timeout=10)

    with get_session_factory()() as session:
        markers = set(session.scalars(select(CreditEligibilityMarker.digest).where(
            CreditEligibilityMarker.user_id == user_id,
        )))
        assert retained < markers
        assert len(markers) == 3
        grant = session.get(TrialGrant, user_id)
        assert (grant.granted_microusd, grant.spent_microusd, grant.reserved_microusd) == (5_000_000, 0, 0)
        prepare_privacy_deletion(session, email, request_reference="POSTGRES-MARKER-001")
        receipt = delete_privacy_account(session, email, request_reference="POSTGRES-MARKER-001")
        assert receipt.retained_credit_eligibility_marker_count == 3


def _assert_concurrent_private_restores_share_the_owner_capacity_lock() -> None:
    """Two archived projects cannot both take the last available active slot."""
    from app.services import projects as service

    suffix = uuid4().hex
    scenario = {"title": "Restore test", "facts": {"ready": {"description": "Ready"}}}
    with get_session_factory()() as session:
        user = upsert_verified_identity(
            session, issuer="https://identity.example.test", subject=f"restore-{suffix}",
            email=f"restore-{suffix}@example.edu", email_verified=True,
        )
        user_id = user.id
        projects = [service.create_project(session, user, name=f"Private project {index}",
                    description="", scenario=scenario, source_scenario_id=None) for index in range(3)]
        archived_ids = []
        for project in projects[:2]:
            service.create_share_link(session, user, project.id)
            service.archive_project(session, user, project.id, expected_version=1)
            archived_ids.append(project.id)

    starts = [Event(), Event()]
    workers = [{}, {}]

    def restore(index):
        with get_session_factory()() as session:
            session.execute(text("SET LOCAL lock_timeout = '10s'"))
            session.execute(text("SET LOCAL statement_timeout = '15s'"))
            owner = session.get(User, user_id)
            workers[index]["pid"] = session.scalar(text("SELECT pg_backend_pid()"))
            starts[index].set()
            try:
                service.restore_project(session, owner, archived_ids[index], expected_version=2)
                return "restored"
            except service.ProjectLimitError:
                return "limited"

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(service, "MAX_ACTIVE_PROJECTS", 2)
        with get_session_factory()() as held, ThreadPoolExecutor(max_workers=2) as executor:
            held.scalar(select(User).where(User.id == user_id).with_for_update())
            owner_pid = held.scalar(text("SELECT pg_backend_pid()"))
            futures = [executor.submit(restore, index) for index in range(2)]
            try:
                for index, future in enumerate(futures):
                    assert starts[index].wait(timeout=5)
                    _wait_for_blocked_worker(held, owner_pid=owner_pid, worker_pid=workers[index]["pid"], future=future)
            finally:
                held.rollback()
            assert sorted(future.result(timeout=10) for future in futures) == ["limited", "restored"]
    with get_session_factory()() as session:
        assert session.scalar(select(func.count(Project.id)).where(
            Project.owner_user_id == user_id, Project.archived_at.is_(None))) == 2
        for project_id in archived_ids:
            project = session.get(Project, project_id)
            share = session.scalar(select(ShareLink).where(ShareLink.project_id == project_id))
            if project.archived_at is None:
                assert project.version == 3 and share.revoked_at is not None
            else:
                assert project.version == 2 and share.revoked_at is None


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
        _assert_concurrent_eligibility_claim_and_deletion_preserve_lifetime_limit()
        _assert_concurrent_stale_sweeps_conserve_both_ledgers()
        _assert_finalization_and_privacy_deletion_use_consistent_account_locks()
        _assert_startup_seeding_and_sign_in_do_not_invert_marker_fk_locks()
        _assert_concurrent_private_restores_share_the_owner_capacity_lock()
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
            # The restricted web role can use the additive public catalog table.
            # Publication retains immutable bundled-corpus provenance.
            catalog_settings = replace(get_settings(), scenario_admin_emails=(user.email,))
            submission = submit_scenario(session, user, catalog_settings, project_id=project.id,
                                         expected_version=project.version, publish=True)
            resolved, source_id = resolve_public_scenario(session, public_id(submission))
            assert source_id == "fire_prevention"
            assert resolved.title == project.name
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
            assert receipt.deleted_scenario_submission_count == 1
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
