"""The allocation command previews without changing accounts or pool rows."""
from __future__ import annotations

import json

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.cli import reconcile_named_credit as command
from app.db.models import Base, NamedCreditEntitlement, TrialGrant, TrialProgram, User


def test_preview_does_not_persist_seeded_pool_and_apply_is_idempotent(tmp_path, monkeypatch, capsys):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'cli.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        session.add(User(email="caminadam@cardiff.ac.uk", email_verified=True))
        session.commit()
    monkeypatch.setattr(command, "get_engine", lambda: engine)
    monkeypatch.setattr(command, "get_session_factory", lambda: factory)
    assert command.main([]) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["applied"] is False
    assert preview["allocations"][3]["after_granted_microusd"] == 50_000_000
    with factory() as session:
        for model in (TrialProgram, TrialGrant, NamedCreditEntitlement):
            assert session.scalar(select(func.count()).select_from(model)) == 0
    assert command.main(["--apply"]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["applied"] is True
    assert command.main(["--apply"]) == 0
    repeated = json.loads(capsys.readouterr().out)
    assert repeated["allocations"][3]["status"] == "unchanged"
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(TrialGrant)) == 1
        program = session.get(TrialProgram, "administrators")
        assert (program.activation_count, program.allocated_microusd) == (1, 50_000_000)
    engine.dispose()
