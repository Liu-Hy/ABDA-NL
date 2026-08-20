"""Safe adoption of legacy SQLite schemas created before Alembic tracking."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, text

from app.db import session as session_module
from app.core.config import reset_settings_cache
from app.db.session import (
    _alembic_config,
    _require_restricted_postgres_role,
    get_engine,
    initialize_database,
    reset_database_caches,
)


@pytest.fixture
def database_environment(monkeypatch):
    reset_database_caches()
    reset_settings_cache()
    monkeypatch.setenv("ABDA_ENVIRONMENT", "development")
    monkeypatch.setenv("ABDA_AUTH_MODE", "dev")
    monkeypatch.setenv("ABDA_AUTO_CREATE_DB", "1")
    yield
    reset_database_caches()
    reset_settings_cache()


def _point_application_at(monkeypatch, database_path: Path) -> str:
    database_url = f"sqlite+pysqlite:///{database_path}"
    monkeypatch.setenv("ABDA_DATABASE_URL", database_url)
    reset_database_caches()
    reset_settings_cache()
    return database_url


def test_exact_revision_one_schema_is_backed_up_stamped_and_upgraded(
    tmp_path, monkeypatch, database_environment
):
    database_path = tmp_path / "legacy.db"
    database_url = _point_application_at(monkeypatch, database_path)
    command.upgrade(_alembic_config(database_url), "20260816_0001")

    legacy_engine = create_engine(database_url)
    with legacy_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users "
                "(id, email, email_verified, display_name, status, created_at, updated_at) "
                "VALUES "
                "('legacy-user', 'legacy@example.edu', 1, NULL, 'active', "
                "'2026-08-17 00:00:00', '2026-08-17 00:00:00')"
            )
        )
        connection.execute(text("DELETE FROM alembic_version"))
    legacy_engine.dispose()

    initialize_database()

    engine = get_engine()
    inspector = inspect(engine)
    assert inspector.has_table("llm_usage_events")
    assert inspector.has_table("emergency_budgets")
    assert "expires_at" in {
        column["name"] for column in inspector.get_columns("usage_reservations")
    }
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one() == "20260817_0004"
        assert connection.execute(
            text("SELECT email FROM users WHERE id = 'legacy-user'")
        ).scalar_one() == "legacy@example.edu"

    backups = list(tmp_path.glob("legacy.db.pre-alembic-*.bak"))
    assert len(backups) == 1
    assert backups[0].stat().st_mode & 0o777 == 0o600
    backup_engine = create_engine(f"sqlite+pysqlite:///{backups[0]}")
    with backup_engine.connect() as connection:
        assert connection.execute(
            text("SELECT email FROM users WHERE id = 'legacy-user'")
        ).scalar_one() == "legacy@example.edu"
    backup_engine.dispose()


def test_partial_unversioned_schema_is_never_stamped(
    tmp_path, monkeypatch, database_environment
):
    database_path = tmp_path / "partial.db"
    database_url = _point_application_at(monkeypatch, database_path)
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
    engine.dispose()

    with pytest.raises(RuntimeError, match="refusing to stamp"):
        initialize_database()

    assert not list(tmp_path.glob("partial.db.pre-alembic-*.bak"))
    check_engine = create_engine(database_url)
    with check_engine.connect() as connection:
        assert connection.execute(
            text("SELECT COUNT(*) FROM alembic_version")
        ).scalar_one() == 0
    check_engine.dispose()


def test_migration_command_needs_only_the_database_url(tmp_path):
    database_path = tmp_path / "production-migration.db"
    repository_root = Path(__file__).resolve().parents[1]
    environment = {
        "ABDA_DATABASE_URL": f"sqlite+pysqlite:///{database_path}",
        "ABDA_ENVIRONMENT": "production",
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(repository_root),
    }
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=repository_root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    engine = create_engine(environment["ABDA_DATABASE_URL"])
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one() == "20260817_0004"
    engine.dispose()


def test_operator_managed_database_must_be_at_application_head(
    tmp_path, monkeypatch, database_environment
):
    database_path = tmp_path / "operator-managed.db"
    database_url = _point_application_at(monkeypatch, database_path)
    command.upgrade(_alembic_config(database_url), "head")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE alembic_version "
                "SET version_num = '20260817_0003'"
            )
        )
    engine.dispose()

    monkeypatch.setenv("ABDA_AUTO_CREATE_DB", "0")
    reset_database_caches()
    reset_settings_cache()
    with pytest.raises(RuntimeError, match="expected 20260817_0004"):
        initialize_database()


def test_operator_managed_database_at_application_head_starts(
    tmp_path, monkeypatch, database_environment
):
    database_path = tmp_path / "operator-managed-current.db"
    database_url = _point_application_at(monkeypatch, database_path)
    command.upgrade(_alembic_config(database_url), "head")

    monkeypatch.setenv("ABDA_AUTO_CREATE_DB", "0")
    reset_database_caches()
    reset_settings_cache()
    initialize_database()

    with get_engine().connect() as connection:
        assert connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one() == "20260817_0004"


def test_installed_package_does_not_require_repository_alembic_ini(
    tmp_path, monkeypatch
):
    package_root = tmp_path / "site-packages"
    fake_module = package_root / "app" / "db" / "session.py"
    (package_root / "migrations").mkdir(parents=True)
    monkeypatch.setattr(session_module, "__file__", str(fake_module))

    config = session_module._alembic_config("sqlite+pysqlite:///:memory:")

    assert config.config_file_name is None
    assert config.get_main_option("script_location") == str(
        package_root / "migrations"
    )


class _PrivilegeResult:
    def __init__(self, values):
        self.values = values

    def mappings(self):
        return self

    def one_or_none(self):
        return self.values


class _PrivilegeConnection:
    def __init__(self, values):
        self.values = values

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, _query):
        return _PrivilegeResult(self.values)


class _PrivilegeEngine:
    def __init__(self, values):
        self.values = values

    def connect(self):
        return _PrivilegeConnection(self.values)


def _restricted_role_values(**overrides):
    values = {
        "superuser": False,
        "create_role": False,
        "create_database": False,
        "replication": False,
        "bypass_row_security": False,
        "inherits_roles": False,
        "create_schema_objects": False,
        "create_schemas": False,
        "create_temporary": False,
        "owns_public_objects": False,
        "role_membership": False,
    }
    values.update(overrides)
    return values


def test_restricted_postgres_web_role_passes_startup_check():
    _require_restricted_postgres_role(_PrivilegeEngine(_restricted_role_values()))


@pytest.mark.parametrize(
    "privilege",
    [
        "superuser",
        "create_role",
        "create_database",
        "replication",
        "bypass_row_security",
        "inherits_roles",
        "create_schema_objects",
        "create_schemas",
        "create_temporary",
        "owns_public_objects",
        "role_membership",
    ],
)
def test_overprivileged_postgres_web_role_is_rejected(privilege):
    with pytest.raises(RuntimeError, match=privilege):
        _require_restricted_postgres_role(
            _PrivilegeEngine(_restricted_role_values(**{privilege: True}))
        )
