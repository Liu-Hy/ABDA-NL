"""Exercise an actual schema upgrade and recovery with named reservations."""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest
from alembic import command
from sqlalchemy import inspect, select, text

from app.api.llm_access import build_llm_config
from app.core.config import get_settings, reset_settings_cache
from app.db.models import (
    CreditEligibilityMarker, CreditEligibilityPolicy, Identity, NamedCreditEntitlement,
    TrialGrant, TrialProgram, UsageReservation, User, utc_now,
)
from app.db.session import (
    _alembic_config, get_engine, get_session_factory, initialize_database,
    reset_database_caches,
)
from app.llm.catalog import _validate_catalog, load_model_catalog
from app.services.credit_policy import NAMED_CREDIT_EMAILS
from app.services.credit_eligibility import POLICY_KEY
from app.services.trials import ensure_named_credit, reserve_trial_credit, settle_trial_credit


@pytest.fixture
def recovery_database(tmp_path, monkeypatch):
    reset_database_caches()
    reset_settings_cache()
    database_url = f"sqlite+pysqlite:///{tmp_path / 'recovery.db'}"
    for key, value in {
        "ABDA_ENVIRONMENT": "test", "ABDA_AUTH_MODE": "dev",
        "ABDA_DATABASE_URL": database_url, "ABDA_AUTO_CREATE_DB": "0",
        "ABDA_TRIAL_ENABLED": "1", "ABDA_TRIAL_MAX_USERS": "100",
        "ABDA_TRIAL_GRANT_MICROUSD": "5000000",
        "ABDA_TRIAL_BUDGET_MICROUSD": "500000000",
        "ABDA_NAMED_CREDIT_AUTO_ACTIVATE": "1",
        "ABDA_CREDIT_ELIGIBILITY_PEPPER": "recovery-test-stable-eligibility-pepper-distinct-and-long",
    }.items():
        monkeypatch.setenv(key, value)
    yield database_url
    reset_database_caches()
    reset_settings_cache()


def test_0007_recovery_conserves_transferred_reservations_and_eligibility(recovery_database):
    config = _alembic_config(recovery_database)
    command.upgrade(config, "20260908_0005")
    assert not inspect(get_engine()).has_table("named_credit_entitlements")
    assert not inspect(get_engine()).has_table("credit_eligibility_markers")
    with get_session_factory()() as session:
        user = User(email=NAMED_CREDIT_EMAILS[0], email_verified=True)
        session.add(user)
        public = session.get(TrialProgram, "global")
        public.enabled = True
        public.max_users = 100
        public.grant_microusd = 5_000_000
        public.budget_microusd = 500_000_000
        public.activation_count = 1
        public.allocated_microusd = 5_000_000
        public.spent_microusd = 1_000_000
        session.flush()
        user_id = user.id
        session.add(Identity(
            user_id=user_id, issuer="https://recovery.example.test", subject="legacy-identity",
            provider_email=user.email,
        ))
        session.add(TrialGrant(
            user_id=user_id, program_key="global", granted_microusd=5_000_000,
            spent_microusd=1_000_000, reserved_microusd=700_000,
        ))
        for identifier, amount, lifetime in (("old-pending", 450_000, 300), ("old-expired", 250_000, -1)):
            session.add(UsageReservation(
                id=identifier, user_id=user_id, program_key="global",
                provider="azure-foundry", model="legacy-model", request_kind="chat",
                reserved_microusd=amount, expires_at=utc_now() + timedelta(seconds=lifetime),
            ))
        session.commit()

    command.upgrade(config, "head")
    initialize_database()
    with get_session_factory()() as session:
        assert session.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "20260910_0007"
        markers = {
            (marker.digest, marker.kind, marker.user_id, marker.claimed_at)
            for marker in session.scalars(select(CreditEligibilityMarker))
        }
        assert len(markers) == 2
        assert {marker[1] for marker in markers} == {"email", "identity"}
        assert {marker[2] for marker in markers} == {user_id}
        policy = session.get(CreditEligibilityPolicy, POLICY_KEY)
        policy_snapshot = (policy.key_fingerprint, policy.seeded_at)
        grant = session.get(TrialGrant, user_id)
        assert (grant.program_key, grant.granted_microusd, grant.spent_microusd, grant.reserved_microusd) == (
            "global", 5_000_000, 1_250_000, 450_000,
        )
        assert session.get(NamedCreditEntitlement, NAMED_CREDIT_EMAILS[0]).user_id is None
        assert session.get(UsageReservation, "old-expired").status == "expired_charged"
        ensure_named_credit(session, session.get(User, user_id))
        settle_trial_credit(session, "old-pending", actual_microusd=200_000)
        assert session.get(UsageReservation, "old-pending").program_key == "administrators"
        late = reserve_trial_credit(
            session, user_id, amount_microusd=100_000, provider="azure-foundry",
            model="recovery-model", request_kind="chat",
        )
        late.expires_at = utc_now() - timedelta(seconds=1)
        late_id = late.id
        session.commit()

    # Restart from the same compatible code after named transfers already exist.
    reset_database_caches()
    initialize_database()
    initialize_database()
    with get_session_factory()() as session:
        assert {
            (marker.digest, marker.kind, marker.user_id, marker.claimed_at)
            for marker in session.scalars(select(CreditEligibilityMarker))
        } == markers
        policy = session.get(CreditEligibilityPolicy, POLICY_KEY)
        assert (policy.key_fingerprint, policy.seeded_at) == policy_snapshot
        grant = session.get(TrialGrant, user_id)
        assert (grant.program_key, grant.granted_microusd, grant.spent_microusd, grant.reserved_microusd) == (
            "administrators", 50_000_000, 1_550_000, 0,
        )
        public = session.get(TrialProgram, "global")
        assert (public.activation_count, public.allocated_microusd, public.spent_microusd) == (0, 0, 0)
        named = session.get(TrialProgram, "administrators")
        assert (named.activation_count, named.allocated_microusd, named.spent_microusd) == (1, 50_000_000, 1_550_000)
        assert session.get(UsageReservation, late_id).status == "expired_charged"

    # A recovery catalog can expose only the historical profile without changing credit policy.
    catalog = load_model_catalog()
    catalog = replace(catalog, profiles={
        key: replace(profile, public_ready=key == "balanced") for key, profile in catalog.profiles.items()
    })
    _validate_catalog(catalog)
    model_config = build_llm_config(
        llm_enabled=True, settings=replace(get_settings(), llm_default_profile="balanced"), catalog=catalog,
    )
    assert [profile.id for profile in model_config.profiles] == ["balanced"]
