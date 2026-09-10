"""Named grants remain bounded, idempotent and separate from public funding."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings, reset_settings_cache
from app.db.models import (
    Base, EmergencyBudget, NamedCreditEntitlement, TrialGrant, TrialProgram,
    UsageReservation, User, utc_now,
)
from app.services.accounts import upsert_verified_identity
from app.services.credit_eligibility import initialize_credit_eligibility
from app.services.credit_policy import (
    NAMED_CREDIT_EMAILS, NAMED_CREDIT_GRANT_MICROUSD, NAMED_CREDIT_PROGRAM,
)
from app.services.llm_billing import reconcile_stale_llm_reservations
from app.services.scenario_submissions import is_scenario_admin
from app.services.trials import (
    TrialUnavailableError, activate_trial, ensure_named_credit, get_trial_balance,
    initialize_named_credit, reconcile_named_credit, release_trial_credit,
    reserve_trial_credit, settle_trial_credit,
)


@pytest.fixture
def credit_factory(tmp_path):
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'named-credit.db'}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        session.add(TrialProgram(
            key="global", enabled=True, max_users=100,
            grant_microusd=5_000_000, budget_microusd=500_000_000,
        ))
        session.add(EmergencyBudget(
            key="openrouter", enabled=True, hard_limit_microusd=500_000_000,
            spent_microusd=345, reserved_microusd=123,
        ))
        initialize_named_credit(session)
        initialize_credit_eligibility(session)
        session.commit()
    yield factory
    engine.dispose()


def _user(session, email, **kwargs):
    user = User(email=email, email_verified=True, **kwargs)
    session.add(user)
    session.commit()
    return user


def _reservation(session, user, amount):
    return reserve_trial_credit(
        session, user.id, amount_microusd=amount, provider="azure-foundry",
        model="test-model", request_kind="chat",
    )


@pytest.mark.parametrize("email", NAMED_CREDIT_EMAILS)
def test_named_credit_and_base_curator_role_respect_effective_permission_demotion(credit_factory, email):
    with credit_factory() as session:
        user = upsert_verified_identity(
            session, issuer="https://identity.example", subject=email,
            email=email.upper(), email_verified=True,
        )
        assert get_trial_balance(session, user.id).granted_microusd == 50_000_000
        assert activate_trial(session, user).granted_microusd == 50_000_000
        repeated = upsert_verified_identity(
            session, issuer="https://identity.example", subject=email,
            email=email, email_verified=True,
        )
        assert repeated.id == user.id
        named = session.get(TrialProgram, NAMED_CREDIT_PROGRAM)
        public = session.get(TrialProgram, "global")
        assert (named.activation_count, named.allocated_microusd) == (1, 50_000_000)
        assert (public.activation_count, public.allocated_microusd) == (0, 0)
        assert is_scenario_admin(user, get_settings())
        assert not is_scenario_admin(user, replace(get_settings(), scenario_admin_emails=()))


def test_all_named_grants_leave_all_100_public_grants_available(credit_factory):
    with credit_factory() as session:
        for email in NAMED_CREDIT_EMAILS:
            activate_trial(session, _user(session, email))
        for index in range(100):
            grant = activate_trial(session, _user(session, f"public-{index}@illinois.edu"))
            assert grant.granted_microusd == 5_000_000
        with pytest.raises(TrialUnavailableError, match="claimed"):
            activate_trial(session, _user(session, "public-overflow@illinois.edu"))
        named = session.get(TrialProgram, NAMED_CREDIT_PROGRAM)
        public = session.get(TrialProgram, "global")
        assert (named.activation_count, named.allocated_microusd) == (5, 250_000_000)
        assert (public.activation_count, public.allocated_microusd) == (100, 500_000_000)
        emergency = session.get(EmergencyBudget, "openrouter")
        assert (emergency.hard_limit_microusd, emergency.spent_microusd,
                emergency.reserved_microusd) == (500_000_000, 345, 123)


def test_mixed_version_rollout_defers_transfers_until_explicit_reconciliation(
    credit_factory, monkeypatch,
):
    monkeypatch.setenv("ABDA_NAMED_CREDIT_AUTO_ACTIVATE", "false")
    reset_settings_cache()
    try:
        with credit_factory() as session:
            first = upsert_verified_identity(
                session, issuer="https://identity.example", subject="rollout-first",
                email=NAMED_CREDIT_EMAILS[0], email_verified=True,
            )
            second = upsert_verified_identity(
                session, issuer="https://identity.example", subject="rollout-second",
                email=NAMED_CREDIT_EMAILS[1], email_verified=True,
            )
            assert session.get(TrialGrant, first.id) is None
            assert activate_trial(session, first).granted_microusd == 5_000_000
            assert activate_trial(session, second).granted_microusd == 5_000_000
            pending = _reservation(session, first, 400_000)
            assert ensure_named_credit(session, first) is None
            assert set(session.scalars(select(TrialGrant.program_key))) == {"global"}
            assert set(session.scalars(select(UsageReservation.program_key))) == {"global"}
            assert all(row.user_id is None for row in session.scalars(select(NamedCreditEntitlement)))
            # Reservations made during mixed-version traffic still settle in
            # the global pool, as required by the previous application's code.
            settle_trial_credit(session, pending.id, actual_microusd=100_000)
            assert session.get(TrialProgram, "global").spent_microusd == 100_000

            preview = reconcile_named_credit(session)
            assert preview[0]["after_granted_microusd"] == 50_000_000
            assert session.get(TrialGrant, first.id).program_key == "global"
            # The operator runs this after all incompatible writers stop.
            reconcile_named_credit(session, apply=True)
            grant = session.get(TrialGrant, first.id)
            assert (grant.program_key, grant.granted_microusd, grant.spent_microusd) == (
                "administrators", 50_000_000, 100_000,
            )
            # An overlapping 0006 replica whose flag remains false cannot
            # undo the transfer or allocate a second public grant.
            assert activate_trial(session, first).granted_microusd == 50_000_000
            assert ensure_named_credit(session, first) is None
            assert session.get(TrialProgram, "global").activation_count == 0

            monkeypatch.setenv("ABDA_NAMED_CREDIT_AUTO_ACTIVATE", "true")
            reset_settings_cache()
            assert ensure_named_credit(session, first).spent_microusd == 100_000
            third = upsert_verified_identity(
                session, issuer="https://identity.example", subject="rollout-third",
                email=NAMED_CREDIT_EMAILS[2], email_verified=True,
            )
            assert get_trial_balance(session, third.id).granted_microusd == 50_000_000
            named = session.get(TrialProgram, "administrators")
            assert (named.activation_count, named.allocated_microusd) == (3, 150_000_000)
            assert session.get(TrialProgram, "global").allocated_microusd == 0
    finally:
        reset_settings_cache()


def test_existing_credit_transfer_preserves_usage_and_pending_settlement(credit_factory):
    with credit_factory() as session:
        user = _user(session, "before-named@example.edu")
        activate_trial(session, user)
        settled = _reservation(session, user, 2_000_000)
        settle_trial_credit(session, settled.id, actual_microusd=1_500_000)
        pending = _reservation(session, user, 700_000)
        releasing = _reservation(session, user, 200_000)
        user.email = NAMED_CREDIT_EMAILS[0]
        session.commit()
        history = [(row.id, row.status, row.actual_microusd, row.reserved_microusd)
                   for row in session.scalars(select(UsageReservation))]

        preview = reconcile_named_credit(session)
        assert preview[0]["before_granted_microusd"] == 5_000_000
        assert preview[0]["after_granted_microusd"] == 50_000_000
        assert get_trial_balance(session, user.id).granted_microusd == 5_000_000
        assert session.get(NamedCreditEntitlement, user.email).user_id is None
        assert session.get(TrialProgram, "global").allocated_microusd == 5_000_000

        applied = reconcile_named_credit(session, apply=True)
        assert applied[0]["spent_microusd"] == 1_500_000
        assert applied[0]["reserved_microusd"] == 900_000
        assert [(row.id, row.status, row.actual_microusd, row.reserved_microusd)
                for row in session.scalars(select(UsageReservation))] == history
        assert set(session.scalars(select(UsageReservation.program_key))) == {NAMED_CREDIT_PROGRAM}
        public = session.get(TrialProgram, "global")
        assert (public.activation_count, public.allocated_microusd, public.spent_microusd) == (0, 0, 0)
        assert reconcile_named_credit(session, apply=True)[0]["status"] == "unchanged"
        settle_trial_credit(session, pending.id, actual_microusd=400_000)
        released = release_trial_credit(session, releasing.id)
        assert (released.granted_microusd, released.spent_microusd,
                released.reserved_microusd) == (50_000_000, 1_900_000, 0)
        assert session.get(TrialProgram, NAMED_CREDIT_PROGRAM).spent_microusd == 1_900_000
        assert session.get(TrialProgram, "global").spent_microusd == 0


def test_expired_reservations_charge_the_transferred_pool(credit_factory):
    with credit_factory() as session:
        user = _user(session, "legacy-expiring@example.edu")
        activate_trial(session, user)
        reservation = _reservation(session, user, 123_456)
        user.email = NAMED_CREDIT_EMAILS[1]
        session.commit()
        ensure_named_credit(session, user)
        reservation.expires_at = utc_now() - timedelta(hours=1)
        session.commit()
        assert reconcile_stale_llm_reservations(session) == (1, 0)
        assert get_trial_balance(session, user.id).spent_microusd == 123_456
        assert session.get(TrialProgram, NAMED_CREDIT_PROGRAM).spent_microusd == 123_456
        assert session.get(TrialProgram, "global").spent_microusd == 0


def test_named_entitlement_stays_bound_after_verified_email_changes(credit_factory):
    with credit_factory() as session:
        user = _user(session, NAMED_CREDIT_EMAILS[0])
        ensure_named_credit(session, user)
        user.email = "new-address@example.edu"
        session.commit()
        assert ensure_named_credit(session, user).granted_microusd == 50_000_000
        replacement = _user(session, NAMED_CREDIT_EMAILS[0])
        with pytest.raises(TrialUnavailableError, match="already bound"):
            ensure_named_credit(session, replacement)
        assert session.get(TrialGrant, replacement.id) is None
        assert session.get(TrialProgram, NAMED_CREDIT_PROGRAM).activation_count == 1


@pytest.mark.parametrize("active, verified", [(False, True), (True, False)])
def test_suspended_and_unverified_accounts_cannot_receive_named_credit(
    credit_factory, active, verified,
):
    with credit_factory() as session:
        user = _user(session, NAMED_CREDIT_EMAILS[0], status="active" if active else "suspended")
        user.email_verified = verified
        session.commit()
        with pytest.raises(TrialUnavailableError, match="verified active"):
            activate_trial(session, user)
        with pytest.raises(TrialUnavailableError, match="verified active"):
            ensure_named_credit(session, user)
        row = reconcile_named_credit(session, apply=True)[0]
        assert row["status"] == ("unverified" if active else "inactive")
        assert session.get(TrialGrant, user.id) is None


def test_concurrent_activation_and_reconciliation_mint_one_grant(credit_factory):
    with credit_factory() as session:
        user_id = _user(session, NAMED_CREDIT_EMAILS[2]).id

    def activate(index):
        with credit_factory() as session:
            if index % 2:
                reconcile_named_credit(session, apply=True)
                return get_trial_balance(session, user_id).granted_microusd
            return activate_trial(session, session.get(User, user_id)).granted_microusd

    with ThreadPoolExecutor(max_workers=8) as executor:
        assert list(executor.map(activate, range(24))) == [50_000_000] * 24
    with credit_factory() as session:
        assert session.scalar(select(func.count()).select_from(TrialGrant)) == 1
        named = session.get(TrialProgram, NAMED_CREDIT_PROGRAM)
        assert (named.activation_count, named.allocated_microusd) == (1, NAMED_CREDIT_GRANT_MICROUSD)


def test_account_deletion_retires_credit_without_blocking_privacy_cleanup(credit_factory):
    from app.services.privacy_requests import (
        delete_privacy_account, export_privacy_account, prepare_privacy_deletion,
    )

    email = NAMED_CREDIT_EMAILS[0]
    with credit_factory() as session:
        user = _user(session, email)
        user_id = user.id
        ensure_named_credit(session, user)
        exported = export_privacy_account(session, email)
        assert exported["named_credit_entitlement"]["email"] == email
        assert exported["named_credit_entitlement"]["bound_at"]
        prepare_privacy_deletion(session, email, request_reference="NAMED-CREDIT-DELETE")
        receipt = delete_privacy_account(session, email, request_reference="NAMED-CREDIT-DELETE")
        assert receipt.retained_trial_granted_microusd == 50_000_000
        session.expire_all()
        assert session.get(User, user_id) is None
        entitlement = session.get(NamedCreditEntitlement, email)
        assert entitlement.user_id is None
        assert entitlement.bound_at is not None
        replacement = _user(session, email)
        with pytest.raises(TrialUnavailableError, match="already bound"):
            ensure_named_credit(session, replacement)
        assert reconcile_named_credit(session, apply=True)[0]["status"] == "retired_after_account_deletion"
        assert session.get(TrialGrant, replacement.id) is None
        assert session.get(TrialProgram, NAMED_CREDIT_PROGRAM).activation_count == 1
