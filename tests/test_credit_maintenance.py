"""Operator previews and sweeps preserve uncertain liabilities and fixed caps."""
from __future__ import annotations

from datetime import timedelta
import json

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import sessionmaker

from app.cli import reconcile_stale_credit
from app.db.models import (
    Base, CreditEligibilityMarker, EmergencyBudget, EmergencyUsageReservation, TrialGrant, TrialProgram,
    UsageReservation, User, utc_now,
)
from app.services.llm_billing import reserve_llm_call
from app.services.trials import TrialUnavailableError, initialize_named_credit


@pytest.fixture
def maintenance_factory(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'maintenance.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        user = User(email="maintenance@example.edu", email_verified=True)
        session.add_all([user, TrialProgram(
            key="global", enabled=True, max_users=100, grant_microusd=5_000_000,
            budget_microusd=500_000_000, activation_count=1, allocated_microusd=5_000_000,
        ), EmergencyBudget(key="openrouter", enabled=True, hard_limit_microusd=500_000_000)])
        session.flush()
        session.add(TrialGrant(user_id=user.id, program_key="global", granted_microusd=5_000_000))
        session.commit()
        for amount in (100, 80):
            receipt = reserve_llm_call(
                session, amount_microusd=amount, user_id=user.id, provider="openrouter",
                route="test-backup", model="test-model", request_kind="chat",
                charge_trial=True, charge_emergency=True,
            )
            if amount == 100:
                session.get(UsageReservation, receipt.trial_reservation_id).expires_at = (
                    utc_now() - timedelta(minutes=1)
                )
                session.get(EmergencyUsageReservation, receipt.emergency_reservation_id).expires_at = (
                    utc_now() - timedelta(minutes=1)
                )
                session.commit()
    yield factory
    engine.dispose()


def test_operator_sweep_preview_apply_and_repeat_conserve_both_budgets(
    maintenance_factory, monkeypatch, capsys,
):
    monkeypatch.setattr(reconcile_stale_credit, "get_session_factory", lambda: maintenance_factory)
    assert reconcile_stale_credit.main([]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "applied": False, "assessment": "full_reserved_amount",
        "trial_reservations": 1, "emergency_reservations": 1,
    }
    with maintenance_factory() as session:
        assert {row.status for row in session.scalars(select(UsageReservation))} == {"pending"}
        grant = session.scalar(select(TrialGrant))
        assert (grant.spent_microusd, grant.reserved_microusd) == (0, 180)
        assert session.get(TrialProgram, "global").spent_microusd == 0
        emergency = session.get(EmergencyBudget, "openrouter")
        assert (emergency.spent_microusd, emergency.reserved_microusd) == (0, 180)

    assert reconcile_stale_credit.main(["--apply"]) == 0
    assert json.loads(capsys.readouterr().out)["trial_reservations"] == 1
    assert reconcile_stale_credit.main(["--apply"]) == 0
    assert json.loads(capsys.readouterr().out)["trial_reservations"] == 0
    with maintenance_factory() as session:
        grant = session.scalar(select(TrialGrant))
        assert (grant.spent_microusd, grant.reserved_microusd) == (100, 80)
        program = session.get(TrialProgram, "global")
        assert (program.activation_count, program.allocated_microusd, program.spent_microusd) == (
            1, 5_000_000, 100,
        )
        emergency = session.get(EmergencyBudget, "openrouter")
        assert (emergency.spent_microusd, emergency.reserved_microusd) == (100, 80)
        assert {row.status for row in session.scalars(select(UsageReservation))} == {
            "pending", "expired_charged",
        }


def test_operator_sweep_hides_unexpected_driver_values(monkeypatch, capsys):
    def unavailable():
        raise RuntimeError("postgresql://private-driver-secret")

    monkeypatch.setattr(reconcile_stale_credit, "get_session_factory", unavailable)
    assert reconcile_stale_credit.main(["--apply"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "no sweep was committed" in captured.err
    assert "private-driver-secret" not in captured.err


def test_sweep_handles_multiple_accounts_without_losing_shared_program_updates(
    maintenance_factory, monkeypatch, capsys,
):
    with maintenance_factory() as session:
        user = User(email="another-maintenance@example.edu", email_verified=True)
        session.add(user)
        session.flush()
        program = session.get(TrialProgram, "global")
        program.activation_count += 1
        program.allocated_microusd += 5_000_000
        session.add(TrialGrant(user_id=user.id, program_key="global", granted_microusd=5_000_000))
        session.commit()
        receipt = reserve_llm_call(
            session, amount_microusd=120, user_id=user.id, provider="openrouter",
            route="test-backup", model="test-model", request_kind="chat",
            charge_trial=True, charge_emergency=True,
        )
        session.get(UsageReservation, receipt.trial_reservation_id).expires_at = utc_now() - timedelta(minutes=1)
        session.get(EmergencyUsageReservation, receipt.emergency_reservation_id).expires_at = utc_now() - timedelta(minutes=1)
        session.commit()
    monkeypatch.setattr(reconcile_stale_credit, "get_session_factory", lambda: maintenance_factory)
    assert reconcile_stale_credit.main(["--apply"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert (report["trial_reservations"], report["emergency_reservations"]) == (2, 2)
    with maintenance_factory() as session:
        assert session.get(TrialProgram, "global").spent_microusd == 220
        assert sum(session.scalars(select(TrialGrant.spent_microusd))) == 220
        assert session.get(EmergencyBudget, "openrouter").spent_microusd == 220


def test_sweep_rolls_back_trial_updates_if_emergency_accounting_is_missing(
    maintenance_factory, monkeypatch, capsys,
):
    with maintenance_factory() as session:
        session.delete(session.get(EmergencyBudget, "openrouter"))
        session.commit()
    monkeypatch.setattr(reconcile_stale_credit, "get_session_factory", lambda: maintenance_factory)
    assert reconcile_stale_credit.main(["--apply"]) == 1
    assert "no sweep was committed" in capsys.readouterr().err
    with maintenance_factory() as session:
        assert session.get(TrialProgram, "global").spent_microusd == 0
        assert {row.status for row in session.scalars(select(UsageReservation))} == {"pending"}


def test_fixed_named_policy_mismatch_refuses_boot_and_points_to_controlled_migration(
    maintenance_factory,
):
    with maintenance_factory() as session:
        initialize_named_credit(session)
        program = session.get(TrialProgram, "administrators")
        program.grant_microusd = 49_000_000
        session.commit()
        with pytest.raises(TrialUnavailableError, match="credit-policy-maintenance.md"):
            initialize_named_credit(session)
        session.rollback()
        assert session.get(TrialProgram, "administrators").grant_microusd == 49_000_000
        assert session.get(TrialProgram, "global").allocated_microusd == 5_000_000


def test_eligibility_migration_preserves_older_tables_and_refuses_to_drop_history(tmp_path):
    from app.db.session import _alembic_config

    url = f"sqlite+pysqlite:///{tmp_path / 'migration-eligibility.db'}"
    config = _alembic_config(url)
    command.upgrade(config, "20260910_0007")
    engine = create_engine(url)
    try:
        db = inspect(engine)
        foreign_key = db.get_foreign_keys("credit_eligibility_markers")[0]
        assert foreign_key["referred_table"] == "users"
        assert foreign_key["options"]["ondelete"] == "SET NULL"
        command.downgrade(config, "20260909_0006")
        assert inspect(engine).has_table("named_credit_entitlements")
        assert not inspect(engine).has_table("credit_eligibility_markers")
        command.upgrade(config, "20260910_0007")
        factory = sessionmaker(bind=engine)
        with factory() as session:
            session.add(CreditEligibilityMarker(digest="b" * 64, kind="email"))
            session.commit()
        with pytest.raises(RuntimeError, match="cannot remove retained"):
            command.downgrade(config, "20260909_0006")
        with factory() as session:
            assert session.get(CreditEligibilityMarker, "b" * 64) is not None
    finally:
        engine.dispose()
