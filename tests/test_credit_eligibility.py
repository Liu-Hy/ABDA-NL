"""Authentication survives allocation refusal; deleted identities cannot re-grant."""
from __future__ import annotations

from dataclasses import replace
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker

from app.api import account_routes
from app.api.main import app
from app.core.config import get_settings
from app.db.models import (
    Base, CreditEligibilityMarker, CreditEligibilityPolicy, Identity,
    NamedCreditEntitlement, TrialGrant, TrialProgram, User, utc_now,
)
from app.db.session import get_db
from app.services.accounts import upsert_verified_identity
from app.services.credit_eligibility import (
    CreditEligibilityError, initialize_credit_eligibility,
)
from app.services.credit_policy import NAMED_CREDIT_EMAILS, NAMED_CREDIT_PROGRAM
from app.services.privacy_requests import (
    delete_privacy_account, export_privacy_account, prepare_privacy_deletion,
)
from app.services.trials import (
    TrialUnavailableError, UsageReservationError, activate_trial, initialize_named_credit,
)


@pytest.fixture
def credit_factory(tmp_path):
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'eligibility.db'}",
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
        initialize_named_credit(session)
        initialize_credit_eligibility(session)
        session.commit()
    yield factory
    engine.dispose()


@pytest.fixture
def credit_client(credit_factory):
    def isolated_db():
        with credit_factory() as session:
            yield session

    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = isolated_db
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)


def _identity(session, email, *, subject="original-subject"):
    return upsert_verified_identity(
        session, issuer="https://identity.example", subject=subject,
        email=email, email_verified=True,
    )


def _delete(session, email):
    prepare_privacy_deletion(session, email, request_reference="REVIEW-DELETE")
    return delete_privacy_account(session, email, request_reference="REVIEW-DELETE")


@pytest.mark.parametrize("refusal", ["retired", "bound", "paused"])
@pytest.mark.parametrize("auth_mode", ["dev", "oidc"])
def test_actual_sign_in_boundary_retains_access_when_named_credit_unavailable(
    credit_factory, credit_client, monkeypatch, caplog, refusal, auth_mode,
):
    email = NAMED_CREDIT_EMAILS[-1]
    with credit_factory() as session:
        if refusal == "paused":
            session.get(TrialProgram, NAMED_CREDIT_PROGRAM).enabled = False
            session.commit()
        else:
            original = _identity(session, email)
            if refusal == "retired":
                _delete(session, email)
            else:
                original.email = "prior-beneficiary@example.edu"
                session.commit()

    if auth_mode == "oidc":
        class FakeOIDC:
            async def authorize_access_token(self, _request):
                return {"userinfo": {
                    "iss": "https://identity.example", "sub": "replacement",
                    "email": email, "email_verified": True,
                }}

        class Registry:
            def create_client(self, _name):
                return FakeOIDC()

        monkeypatch.setattr(account_routes, "_oauth_registry", Registry)
        settings = replace(get_settings(), auth_mode="oidc", oidc_issuer="https://identity.example")
        app.dependency_overrides[get_settings] = lambda: settings
        def sign_in():
            return credit_client.get("/auth/callback", follow_redirects=False)
    else:
        def sign_in():
            return credit_client.post("/api/auth/dev/login", json={"email": email})

    with caplog.at_level("INFO", logger="app.services.accounts"):
        for _ in range(2):
            response = sign_in()
            if auth_mode == "oidc":
                assert response.status_code == 303
                assert response.headers["location"] == "/"
            else:
                assert response.status_code == 200
                assert response.json()["authenticated"] is True
            assert credit_client.get("/api/auth/session").json()["authenticated"] is True
            assert credit_client.get("/api/projects").status_code == 200
            assert credit_client.get("/api/trial").json()["active"] is False
            assert credit_client.post("/api/trial/activate").status_code == 409
    credit_logs = [record.getMessage() for record in caplog.records
                   if record.name == "app.services.accounts"]
    assert len(credit_logs) == 2
    assert all("automatic_credit_unavailable reason=" in value for value in credit_logs)
    assert all(email not in value for value in credit_logs)
    with credit_factory() as session:
        public = session.get(TrialProgram, "global")
        assert (public.activation_count, public.allocated_microusd) == (0, 0)
        assert session.scalar(select(func.count()).select_from(TrialGrant)) == (refusal == "bound")


def test_paused_program_does_not_block_existing_full_named_grant(credit_factory, credit_client):
    email = NAMED_CREDIT_EMAILS[0]
    assert credit_client.post("/api/auth/dev/login", json={"email": email}).status_code == 200
    with credit_factory() as session:
        session.get(TrialProgram, NAMED_CREDIT_PROGRAM).enabled = False
        session.commit()
    assert credit_client.post("/api/auth/dev/login", json={"email": email}).status_code == 200
    assert credit_client.get("/api/trial").json()["granted_microusd"] == 50_000_000


def test_accounting_corruption_is_not_hidden_as_unavailable_automatic_credit(
    credit_client, monkeypatch,
):
    import app.services.trials as trials

    def corrupt(*_args, **_kwargs):
        raise UsageReservationError("synthetic accounting corruption")

    monkeypatch.setattr(trials, "ensure_named_credit", corrupt)
    response = credit_client.post("/api/auth/dev/login", json={"email": NAMED_CREDIT_EMAILS[1]})
    assert response.status_code == 500
    assert credit_client.get("/api/auth/session").json()["authenticated"] is False


def test_suspended_named_identity_cannot_sign_in(credit_factory, credit_client):
    email = NAMED_CREDIT_EMAILS[2]
    first = credit_client.post("/api/auth/dev/login", json={"email": email})
    with credit_factory() as session:
        session.get(User, first.json()["user"]["id"]).status = "suspended"
        session.commit()
    response = credit_client.post("/api/auth/dev/login", json={"email": email})
    assert response.status_code >= 400
    assert credit_client.get("/api/auth/session").json()["authenticated"] is False


@pytest.mark.parametrize("same_email", [True, False])
def test_public_deletion_preserves_eligibility_but_allows_sign_in(credit_factory, same_email):
    original_email = "introductory@example.edu"
    with credit_factory() as session:
        original = _identity(session, original_email)
        activate_trial(session, original)
        exported = export_privacy_account(session, original_email)
        assert exported["introductory_credit_eligibility"]["retention"] == "credit_program_lifetime"
        assert {item["kind"] for item in exported["introductory_credit_eligibility"]["markers"]} == {
            "email", "identity",
        }
        receipt = _delete(session, original_email)
        assert receipt.retained_credit_eligibility_marker_count == 2
        assert session.scalar(select(func.count()).select_from(Identity)) == 0
        assert all(item.user_id is None for item in session.scalars(select(CreditEligibilityMarker)))
        replacement = _identity(
            session, original_email.upper() if same_email else "another-address@example.edu",
            subject="different-subject" if same_email else "original-subject",
        )
        assert replacement.status == "active"
        with pytest.raises(TrialUnavailableError, match="already been used"):
            activate_trial(session, replacement)
        program = session.get(TrialProgram, "global")
        assert (program.activation_count, program.allocated_microusd) == (1, 5_000_000)
        assert session.get(TrialGrant, replacement.id) is None
        markers = list(session.scalars(select(CreditEligibilityMarker)))
        assert len(markers) == 2  # The failed claim's additional marker rolled back.
        serialized = json.dumps([{"digest": item.digest, "kind": item.kind} for item in markers])
        assert original_email not in serialized
        assert "original-subject" not in serialized


def test_email_change_records_new_identifier_before_later_deletion(credit_factory):
    with credit_factory() as session:
        user = _identity(session, "first-address@example.edu")
        activate_trial(session, user)
        _identity(session, "second-address@example.edu")
        _delete(session, "second-address@example.edu")
        for index, email in enumerate(("first-address@example.edu", "second-address@example.edu")):
            replacement = _identity(session, email, subject=f"replacement-{index}")
            with pytest.raises(TrialUnavailableError, match="already been used"):
                activate_trial(session, replacement)
        assert session.get(TrialProgram, "global").activation_count == 1


def test_retired_named_identity_cannot_claim_public_credit_during_activation_pause(
    credit_factory, monkeypatch,
):
    from app.core import config

    email = NAMED_CREDIT_EMAILS[0]
    with credit_factory() as session:
        _identity(session, email)
        _delete(session, email)
        paused = replace(get_settings(), named_credit_auto_activate=False)
        monkeypatch.setattr(config, "get_settings", lambda: paused)
        replacement = _identity(session, email, subject="new-identity")
        with pytest.raises(TrialUnavailableError, match="already been used"):
            activate_trial(session, replacement)
        assert session.get(TrialProgram, "global").activation_count == 0
        assert session.get(TrialProgram, NAMED_CREDIT_PROGRAM).activation_count == 1


def test_initializer_seeds_existing_grants_and_named_retirements_without_regrant(credit_factory):
    with credit_factory() as session:
        user = _identity(session, "legacy-beneficiary@example.edu")
        program = session.get(TrialProgram, "global")
        program.activation_count = 1
        program.allocated_microusd = 5_000_000
        session.add(TrialGrant(user_id=user.id, program_key="global", granted_microusd=5_000_000))
        retired = session.get(NamedCreditEntitlement, NAMED_CREDIT_EMAILS[0])
        retired.bound_at = utc_now()
        session.commit()
        initialize_credit_eligibility(session)
        initialize_credit_eligibility(session)
        session.commit()
        assert session.scalar(select(func.count()).select_from(CreditEligibilityMarker)) == 3
        assert program.activation_count == 1
        assert session.scalar(select(func.count()).select_from(CreditEligibilityPolicy)) == 1


def test_key_replacement_fails_closed_without_changing_history(credit_factory, monkeypatch):
    from app.services import credit_eligibility

    with credit_factory() as session:
        user = _identity(session, "prior-key@example.edu")
        activate_trial(session, user)
        expected = set(session.scalars(select(CreditEligibilityMarker.digest)))
        settings = replace(get_settings(), credit_eligibility_pepper="different-eligibility-key" * 3)
        monkeypatch.setattr(credit_eligibility, "get_settings", lambda: settings)
        with pytest.raises(CreditEligibilityError, match="does not match"):
            initialize_credit_eligibility(session)
        session.rollback()
        replacement = User(email="new-person@example.edu", email_verified=True)
        session.add(replacement)
        session.commit()
        with pytest.raises(CreditEligibilityError, match="does not match"):
            activate_trial(session, replacement)
        assert set(session.scalars(select(CreditEligibilityMarker.digest))) == expected
        assert session.get(TrialProgram, "global").activation_count == 1


def test_missing_key_policy_cannot_reseed_an_existing_marker_generation(credit_factory):
    with credit_factory() as session:
        user = _identity(session, "retained-generation@example.edu")
        activate_trial(session, user)
        policy = session.scalar(select(CreditEligibilityPolicy))
        session.delete(policy)
        session.commit()
        with pytest.raises(CreditEligibilityError, match="no key policy"):
            initialize_credit_eligibility(session)
        session.rollback()
        assert session.scalar(select(func.count()).select_from(CreditEligibilityPolicy)) == 0
        assert session.scalar(select(func.count()).select_from(CreditEligibilityMarker)) == 2
