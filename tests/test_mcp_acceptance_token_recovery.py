"""Contracts for the narrowly scoped MCP acceptance token recovery."""

from __future__ import annotations

from datetime import timedelta
import os
from pathlib import Path
import shlex
import subprocess
import sys

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, MCPAccessToken, User, utc_now


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy" / "azure" / "recover-mcp-acceptance-tokens.sh"
EMAIL = "mcp-recovery@example.edu"
TOKEN_NAMES = (
    "MCP scope read acceptance",
    "MCP scoped write acceptance",
)


def _runner_source() -> str:
    result = subprocess.run(
        [
            "bash",
            "-c",
            f"source {shlex.quote(str(SCRIPT))}; abda_mcp_recovery_runner_source",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    compile(result.stdout, "<mcp-acceptance-recovery>", "exec")
    return result.stdout


def _environment(database: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "ABDA_DATABASE_URL": f"sqlite+pysqlite:///{database}",
            "ABDA_ENVIRONMENT": "test",
            "ABDA_AUTH_MODE": "dev",
            "ABDA_AUTO_CREATE_DB": "0",
            "ABDA_SESSION_SECRET": "s" * 48,
            "ABDA_MCP_TOKEN_PEPPER": "p" * 48,
        }
    )
    return environment


def _seed(database: Path, *, duplicate: bool = False) -> tuple[str, str]:
    engine = create_engine(f"sqlite+pysqlite:///{database}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = utc_now()
    with factory() as session:
        user = User(email=EMAIL, email_verified=True, created_at=now, updated_at=now)
        session.add(user)
        session.flush()
        records = [
            MCPAccessToken(
                user_id=user.id,
                name=name,
                token_prefix=f"acceptance-{index}",
                token_hash=str(index) * 64,
                scopes="projects:read",
                created_at=now,
                expires_at=now + timedelta(days=30),
            )
            for index, name in enumerate(TOKEN_NAMES, start=1)
        ]
        unrelated = MCPAccessToken(
            user_id=user.id,
            name="Keep this credential",
            token_prefix="unrelated",
            token_hash="9" * 64,
            scopes="projects:read",
            created_at=now,
            expires_at=now + timedelta(days=30),
        )
        session.add_all([*records, unrelated])
        if duplicate:
            session.add(
                MCPAccessToken(
                    user_id=user.id,
                    name=TOKEN_NAMES[0],
                    token_prefix="duplicate",
                    token_hash="8" * 64,
                    scopes="projects:read",
                    created_at=now,
                    expires_at=now + timedelta(days=30),
                )
            )
        session.commit()
        result = (user.id, unrelated.id)
    engine.dispose()
    return result


def test_script_syntax_and_mutation_boundary():
    assert SCRIPT.stat().st_mode & 0o111
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
    source = SCRIPT.read_text(encoding="utf-8")
    runner = _runner_source()

    assert "REVOKE_TWO_MCP_ACCEPTANCE_TOKENS" in runner
    assert "MCP_ACCEPTANCE_TOKENS_REVOKED" in runner
    assert "getpass.getpass" in runner
    assert "RateLimitBucket" not in runner
    assert "token_hash" not in runner
    assert "az containerapp update" not in source
    assert "az containerapp delete" not in source
    assert "az group delete" not in source
    assert "az containerapp secret" not in source
    assert "\u2013" not in source and "\u2014" not in source


def test_runner_revokes_only_the_two_acceptance_credentials(tmp_path: Path):
    database = tmp_path / "recovery.sqlite3"
    user_id, unrelated_id = _seed(database)
    result = subprocess.run(
        [sys.executable, "-c", _runner_source()],
        input=f"{EMAIL}\nREVOKE_TWO_MCP_ACCEPTANCE_TOKENS\n",
        env=_environment(database),
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stderr
    assert "matching_active_acceptance_tokens: 2" in result.stdout
    assert "result: MCP_ACCEPTANCE_TOKENS_REVOKED" in result.stdout
    assert EMAIL not in result.stdout

    engine = create_engine(f"sqlite+pysqlite:///{database}")
    with sessionmaker(bind=engine)() as session:
        matching = list(
            session.scalars(
                select(MCPAccessToken).where(MCPAccessToken.user_id == user_id)
            )
        )
        by_id = {item.id: item for item in matching}
        assert all(
            item.revoked_at is not None for item in matching if item.name in TOKEN_NAMES
        )
        assert by_id[unrelated_id].revoked_at is None
    engine.dispose()


def test_runner_refuses_duplicate_active_acceptance_names(tmp_path: Path):
    database = tmp_path / "duplicate.sqlite3"
    user_id, _ = _seed(database, duplicate=True)
    result = subprocess.run(
        [sys.executable, "-c", _runner_source()],
        input=f"{EMAIL}\nREVOKE_TWO_MCP_ACCEPTANCE_TOKENS\n",
        env=_environment(database),
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode != 0
    assert "more than one active credential" in result.stderr

    engine = create_engine(f"sqlite+pysqlite:///{database}")
    with sessionmaker(bind=engine)() as session:
        matching = list(
            session.scalars(
                select(MCPAccessToken).where(
                    MCPAccessToken.user_id == user_id,
                    MCPAccessToken.name.in_(TOKEN_NAMES),
                )
            )
        )
        assert all(item.revoked_at is None for item in matching)
    engine.dispose()
