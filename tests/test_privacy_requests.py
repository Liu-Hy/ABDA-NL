"""Privacy access export and two-phase permanent deletion acceptance."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.cli import privacy as privacy_cli
from app.db.models import (
    Base,
    EmergencyBudget,
    EmergencyUsageReservation,
    Identity,
    LLMUsageEvent,
    MCPAccessToken,
    Project,
    ShareLink,
    TrialGrant,
    TrialProgram,
    UsageReservation,
    User,
    utc_now,
)
from app.services.privacy_requests import (
    PrivacyAccountNotFoundError,
    PrivacyDeletionNotReadyError,
    delete_privacy_account,
    export_privacy_account,
    inspect_privacy_account,
    prepare_privacy_deletion,
    public_summary,
)


EMAIL = "privacy-researcher@example.edu"
TOKEN_HASH = "a" * 64
SHARE_HASH = "b" * 64


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    engine.dispose()


def _populate(factory: sessionmaker[Session]) -> str:
    now = utc_now()
    with factory() as session:
        user = User(
            email=EMAIL,
            email_verified=True,
            display_name="Privacy Researcher",
            created_at=now,
            updated_at=now,
            last_login_at=now,
        )
        session.add(user)
        session.flush()
        session.add(
            Identity(
                user_id=user.id,
                issuer="https://identity.example.test",
                subject="privacy-subject",
                provider_email=EMAIL,
                created_at=now,
                last_login_at=now,
            )
        )
        project = Project(
            owner_user_id=user.id,
            name="Private research project",
            description="Private content for export and deletion testing",
            source_scenario_id="fire_prevention",
            scenario_json={"title": "Private scenario", "language": {"p": "Private"}},
            version=2,
            created_at=now,
            updated_at=now,
        )
        session.add(project)
        session.flush()
        session.add(
            ShareLink(
                project_id=project.id,
                token_hash=SHARE_HASH,
                permission="view",
                created_at=now,
            )
        )
        session.add(
            MCPAccessToken(
                user_id=user.id,
                name="Privacy test token",
                token_prefix="abda_mcp_display",
                token_hash=TOKEN_HASH,
                scopes="projects:read projects:write",
                created_at=now,
                expires_at=now + timedelta(days=365),
            )
        )
        session.add(
            TrialProgram(
                key="global",
                enabled=True,
                max_users=10,
                grant_microusd=5_000_000,
                budget_microusd=50_000_000,
                activation_count=1,
                allocated_microusd=5_000_000,
                spent_microusd=25,
            )
        )
        session.flush()
        session.add(
            TrialGrant(
                user_id=user.id,
                program_key="global",
                granted_microusd=5_000_000,
                spent_microusd=25,
                reserved_microusd=0,
                activated_at=now,
            )
        )
        session.add(
            UsageReservation(
                user_id=user.id,
                program_key="global",
                provider="foundry",
                model="claude-sonnet-4-6",
                request_kind="chat",
                reserved_microusd=1_000,
                actual_microusd=25,
                status="settled",
                created_at=now,
                expires_at=now,
                finalized_at=now,
            )
        )
        session.add(
            EmergencyBudget(
                key="openrouter",
                enabled=False,
                hard_limit_microusd=500_000_000,
                spent_microusd=10,
                reserved_microusd=0,
            )
        )
        session.flush()
        session.add(
            EmergencyUsageReservation(
                budget_key="openrouter",
                user_id=user.id,
                provider="openrouter",
                route="openrouter-gemini-3.7-flash",
                model="gemini-3.7-flash",
                request_kind="chat",
                reserved_microusd=1_000,
                actual_microusd=10,
                status="settled",
                created_at=now,
                expires_at=now,
                finalized_at=now,
            )
        )
        session.add(
            LLMUsageEvent(
                request_id="privacy-request-event",
                user_id=user.id,
                provider="foundry",
                route="cloudbank-claude-sonnet-4-6",
                model="claude-sonnet-4-6",
                billing_source="trial",
                request_kind="chat",
                status="succeeded",
                input_tokens=10,
                output_tokens=5,
                cost_microusd=25,
                latency_ms=100,
                created_at=now,
            )
        )
        session.commit()
        return user.id


def test_privacy_export_contains_user_data_but_no_bearer_hashes(session_factory):
    _populate(session_factory)
    with session_factory() as session:
        summary = inspect_privacy_account(session, EMAIL.upper())
        exported = export_privacy_account(session, EMAIL)

    serialized = json.dumps(exported, sort_keys=True)
    public = json.dumps(public_summary(summary), sort_keys=True)
    assert EMAIL in serialized
    assert "Private research project" in serialized
    assert TOKEN_HASH not in serialized
    assert SHARE_HASH not in serialized
    assert "token_hash" not in serialized
    assert summary.identity_count == 1
    assert summary.active_project_count == 1
    assert summary.share_link_count == 1
    assert summary.mcp_token_count == 1
    assert summary.active_mcp_token_count == 1
    assert summary.trial_spent_microusd == 25
    assert EMAIL not in public
    assert summary.account_fingerprint in public


def test_two_phase_deletion_revokes_access_and_preserves_anonymous_costs(
    session_factory,
):
    user_id = _populate(session_factory)
    with session_factory() as session:
        with pytest.raises(PrivacyDeletionNotReadyError):
            delete_privacy_account(
                session,
                EMAIL,
                request_reference="PRIV-20260828-001",
            )

        prepared = prepare_privacy_deletion(
            session,
            EMAIL,
            request_reference="PRIV-20260828-001",
        )
        assert prepared.status == "deletion_pending"
        assert prepared.active_mcp_token_count == 0
        assert (
            session.scalar(
                select(MCPAccessToken.revoked_at).where(MCPAccessToken.user_id == user_id)
            )
            is not None
        )
        assert session.scalar(select(ShareLink.revoked_at)) is not None

        receipt = delete_privacy_account(
            session,
            EMAIL,
            request_reference="PRIV-20260828-001",
        )
        assert receipt.deleted_project_count == 1
        assert receipt.deleted_mcp_token_count == 1
        assert receipt.anonymized_llm_usage_event_count == 1
        assert receipt.retained_trial_granted_microusd == 5_000_000
        assert session.get(User, user_id) is None
        assert session.scalar(select(LLMUsageEvent.user_id)) is None
        assert session.scalar(select(EmergencyUsageReservation.user_id)) is None
        assert session.scalar(select(TrialProgram.activation_count)) == 1
        assert session.scalar(select(TrialProgram.allocated_microusd)) == 5_000_000
        assert session.scalar(select(TrialProgram.spent_microusd)) == 25
        assert session.scalar(select(EmergencyBudget.spent_microusd)) == 10

        with pytest.raises(PrivacyAccountNotFoundError):
            inspect_privacy_account(session, EMAIL)


def test_deletion_refuses_unsettled_model_reservations(session_factory):
    user_id = _populate(session_factory)
    with session_factory() as session:
        grant = session.get(TrialGrant, user_id)
        assert grant is not None
        grant.reserved_microusd = 100
        session.add(
            UsageReservation(
                user_id=user_id,
                program_key="global",
                provider="foundry",
                model="claude-sonnet-4-6",
                request_kind="chat",
                reserved_microusd=100,
                status="pending",
            )
        )
        session.commit()
        prepare_privacy_deletion(
            session,
            EMAIL,
            request_reference="PRIV-20260828-002",
        )
        with pytest.raises(PrivacyDeletionNotReadyError):
            delete_privacy_account(
                session,
                EMAIL,
                request_reference="PRIV-20260828-002",
            )
        assert session.get(User, user_id) is not None


def test_privacy_cli_is_dry_run_by_default_and_writes_private_export(
    session_factory,
    monkeypatch,
    capsys,
    tmp_path: Path,
):
    user_id = _populate(session_factory)
    monkeypatch.setenv("ABDA_PRIVACY_USER_EMAIL", EMAIL)
    monkeypatch.setattr(privacy_cli, "database_is_ready", lambda: True)
    monkeypatch.setattr(privacy_cli, "get_session_factory", lambda: session_factory)

    assert privacy_cli.main(["inspect"]) == 0
    inspect_output = capsys.readouterr().out
    assert EMAIL not in inspect_output
    assert '"mutated": false' in inspect_output

    assert privacy_cli.main(["prepare-delete", "--request-reference", "PRIV-20260828-003"]) == 0
    planned = capsys.readouterr().out
    assert '"mutated": false' in planned
    with session_factory() as session:
        assert session.get(User, user_id).status == "active"

    assert privacy_cli.main(["prepare-delete", "--request-reference", "invalid reference"]) == 1
    assert "request reference" in capsys.readouterr().err
    with session_factory() as session:
        assert session.get(User, user_id).status == "active"

    assert (
        privacy_cli.main(
            [
                "prepare-delete",
                "--request-reference",
                "PRIV-20260828-003",
                "--execute",
            ]
        )
        == 1
    )
    assert "exact value" in capsys.readouterr().err

    monkeypatch.setenv(
        "ABDA_PRIVACY_CONFIRMATION",
        "PREPARE:PRIV-20260828-003",
    )
    assert (
        privacy_cli.main(
            [
                "prepare-delete",
                "--request-reference",
                "PRIV-20260828-003",
                "--execute",
            ]
        )
        == 0
    )
    assert '"mutated": true' in capsys.readouterr().out

    export_root = tmp_path / "private-export"
    export_root.mkdir(mode=0o700)
    os.chmod(export_root, 0o700)
    export_path = export_root / "access.json"
    assert privacy_cli.main(["export", "--output", str(export_path)]) == 0
    assert '"output_mode": "0600"' in capsys.readouterr().out
    assert stat.S_IMODE(export_path.stat().st_mode) == 0o600
    assert json.loads(export_path.read_text(encoding="utf-8"))["account"]["email"] == EMAIL

    monkeypatch.setenv(
        "ABDA_PRIVACY_CONFIRMATION",
        "DELETE:PRIV-20260828-003",
    )
    assert (
        privacy_cli.main(
            [
                "delete",
                "--request-reference",
                "PRIV-20260828-003",
                "--execute",
            ]
        )
        == 0
    )
    deleted_output = capsys.readouterr().out
    assert EMAIL not in deleted_output
    assert '"mutated": true' in deleted_output
    with session_factory() as session:
        assert session.get(User, user_id) is None
