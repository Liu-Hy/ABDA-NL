"""SQLAlchemy engine lifecycle and FastAPI session dependency."""
from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime, timezone
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.models import Base, EmergencyBudget, TrialProgram


log = logging.getLogger(__name__)
LEGACY_SCHEMA_REVISIONS = (
    "20260817_0004",
    "20260817_0003",
    "20260817_0002",
    "20260816_0001",
)


def _prepare_sqlite_path(database_url: str) -> None:
    parsed = make_url(database_url)
    if parsed.get_backend_name() != "sqlite" or not parsed.database:
        return
    if parsed.database == ":memory:":
        return
    Path(parsed.database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    settings = get_settings()
    _prepare_sqlite_path(settings.database_url)
    parsed = make_url(settings.database_url)
    kwargs: dict = {"pool_pre_ping": True}
    if parsed.get_backend_name() == "sqlite":
        kwargs["connect_args"] = {"check_same_thread": False}
        if parsed.database == ":memory:":
            kwargs["poolclass"] = StaticPool
    else:
        kwargs.update(
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_timeout=settings.database_pool_timeout_seconds,
        )
    engine = create_engine(settings.database_url, **kwargs)

    if parsed.get_backend_name() == "sqlite":

        @event.listens_for(engine, "connect")
        def _sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def _alembic_config(database_url: str):
    from alembic.config import Config

    repository_root = Path(__file__).resolve().parents[2]
    config_path = repository_root / "alembic.ini"
    config = Config(str(config_path)) if config_path.is_file() else Config()
    config.set_main_option("script_location", str(repository_root / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def _schema_signature(engine: Engine) -> dict:
    inspector = inspect(engine)
    signature: dict = {}
    for table in sorted(
        name for name in inspector.get_table_names() if name != "alembic_version"
    ):
        columns = [
            (
                column["name"],
                str(column["type"]).upper(),
                bool(column["nullable"]),
                str(column.get("default")),
            )
            for column in inspector.get_columns(table)
        ]
        primary_key = tuple(
            (inspector.get_pk_constraint(table).get("constrained_columns") or [])
        )
        unique_constraints = sorted(
            (
                constraint.get("name") or "",
                tuple(constraint.get("column_names") or []),
            )
            for constraint in inspector.get_unique_constraints(table)
        )
        foreign_keys = sorted(
            (
                tuple(key.get("constrained_columns") or []),
                key.get("referred_table") or "",
                tuple(key.get("referred_columns") or []),
                str((key.get("options") or {}).get("ondelete") or ""),
            )
            for key in inspector.get_foreign_keys(table)
        )
        indexes = sorted(
            (
                index.get("name") or "",
                tuple(index.get("column_names") or []),
                bool(index.get("unique")),
            )
            for index in inspector.get_indexes(table)
        )
        checks = sorted(
            (
                constraint.get("name") or "",
                " ".join(str(constraint.get("sqltext") or "").split()),
            )
            for constraint in inspector.get_check_constraints(table)
        )
        signature[table] = {
            "columns": columns,
            "primary_key": primary_key,
            "unique_constraints": unique_constraints,
            "foreign_keys": foreign_keys,
            "indexes": indexes,
            "checks": checks,
        }
    return signature


def _revision_schema_signature(revision: str) -> dict:
    from alembic import command

    with TemporaryDirectory(prefix="abda-schema-") as temp_dir:
        database_path = Path(temp_dir) / "reference.db"
        database_url = f"sqlite+pysqlite:///{database_path}"
        command.upgrade(_alembic_config(database_url), revision)
        reference_engine = create_engine(database_url)
        try:
            return _schema_signature(reference_engine)
        finally:
            reference_engine.dispose()


def _has_alembic_revision(engine: Engine) -> bool:
    inspector = inspect(engine)
    if not inspector.has_table("alembic_version"):
        return False
    with engine.connect() as connection:
        return connection.execute(text("SELECT version_num FROM alembic_version")).first() is not None


def _database_alembic_heads(engine: Engine) -> frozenset[str]:
    if not inspect(engine).has_table("alembic_version"):
        return frozenset()
    with engine.connect() as connection:
        return frozenset(
            str(value)
            for value in connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalars()
        )


def _application_alembic_heads(database_url: str) -> frozenset[str]:
    from alembic.script import ScriptDirectory

    scripts = ScriptDirectory.from_config(_alembic_config(database_url))
    return frozenset(scripts.get_heads())


def _require_current_database_revision(
    engine: Engine,
    database_url: str,
) -> None:
    """Fail startup when an operator-managed database missed a migration."""
    current = _database_alembic_heads(engine)
    expected = _application_alembic_heads(database_url)
    if current == expected:
        return
    current_label = ",".join(sorted(current)) or "none"
    expected_label = ",".join(sorted(expected)) or "none"
    raise RuntimeError(
        "database migrations are required; "
        f"current Alembic revision is {current_label}, expected {expected_label}"
    )


def _require_restricted_postgres_role(engine: Engine) -> None:
    """Reject an administrative or object-creating production web login."""
    query = text(
        """
        SELECT
          role_record.rolsuper AS superuser,
          role_record.rolcreaterole AS create_role,
          role_record.rolcreatedb AS create_database,
          role_record.rolreplication AS replication,
          role_record.rolbypassrls AS bypass_row_security,
          role_record.rolinherit AS inherits_roles,
          has_schema_privilege(current_user, 'public', 'CREATE') AS create_schema_objects,
          has_database_privilege(current_user, current_database(), 'CREATE') AS create_schemas,
          has_database_privilege(current_user, current_database(), 'TEMP') AS create_temporary,
          EXISTS (
            SELECT 1
            FROM pg_catalog.pg_class owned_object
            JOIN pg_catalog.pg_namespace object_namespace
              ON object_namespace.oid = owned_object.relnamespace
            WHERE owned_object.relowner = role_record.oid
              AND object_namespace.nspname = 'public'
          ) AS owns_public_objects,
          EXISTS (
            SELECT 1
            FROM pg_catalog.pg_auth_members membership
            JOIN pg_catalog.pg_roles member_role
              ON member_role.oid = membership.member
            WHERE member_role.rolname = current_user
          ) AS role_membership
        FROM pg_catalog.pg_roles role_record
        WHERE role_record.rolname = current_user
        """
    )
    with engine.connect() as connection:
        row = connection.execute(query).mappings().one_or_none()
    if row is None:
        raise RuntimeError("cannot inspect the production PostgreSQL login")
    dangerous = sorted(name for name, enabled in row.items() if bool(enabled))
    if dangerous:
        raise RuntimeError(
            "the production PostgreSQL login is overprivileged: " + ", ".join(dangerous)
        )


def _backup_sqlite_database(engine: Engine, database_url: str) -> Path:
    parsed = make_url(database_url)
    if parsed.get_backend_name() != "sqlite" or not parsed.database:
        raise RuntimeError("legacy schema backup is supported only for file-based SQLite")
    source_path = Path(parsed.database).expanduser().resolve()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = source_path.with_name(f"{source_path.name}.pre-alembic-{stamp}.bak")
    raw_connection = engine.raw_connection()
    destination = sqlite3.connect(str(backup_path))
    try:
        source = raw_connection.driver_connection
        source.backup(destination)
    finally:
        destination.close()
        raw_connection.close()
    os.chmod(backup_path, 0o600)
    return backup_path


def _adopt_unversioned_sqlite_schema(
    engine: Engine,
    database_url: str,
) -> str | None:
    parsed = make_url(database_url)
    if parsed.get_backend_name() != "sqlite" or parsed.database in {None, ":memory:"}:
        return None
    inspector = inspect(engine)
    application_tables = set(inspector.get_table_names()) - {"alembic_version"}
    if not application_tables or _has_alembic_revision(engine):
        return None

    actual = _schema_signature(engine)
    matched_revision = next(
        (
            revision
            for revision in LEGACY_SCHEMA_REVISIONS
            if actual == _revision_schema_signature(revision)
        ),
        None,
    )
    if matched_revision is None:
        raise RuntimeError(
            "refusing to stamp an unversioned SQLite database because its schema "
            "does not exactly match a known ABDA-NL revision"
        )

    from alembic import command

    backup_path = _backup_sqlite_database(engine, database_url)
    command.stamp(_alembic_config(database_url), matched_revision)
    log.warning(
        "adopted unversioned SQLite schema revision=%s backup=%s",
        matched_revision,
        backup_path,
    )
    return matched_revision


def initialize_database() -> None:
    settings = get_settings()
    parsed = make_url(settings.database_url)
    if (
        settings.auto_create_database
        and settings.environment != "test"
        and parsed.database != ":memory:"
    ):
        from alembic import command

        engine = get_engine()
        _adopt_unversioned_sqlite_schema(engine, settings.database_url)
        alembic_config = _alembic_config(settings.database_url)
        command.upgrade(alembic_config, "head")
    elif settings.auto_create_database:
        engine = get_engine()
        Base.metadata.create_all(engine)

    engine = get_engine()
    if (
        settings.environment in {"staging", "production"}
        and parsed.get_backend_name() == "postgresql"
    ):
        _require_restricted_postgres_role(engine)
    if not settings.auto_create_database:
        _require_current_database_revision(engine, settings.database_url)
    db_inspector = inspect(engine)
    required = {"trial_programs", "emergency_budgets", "rate_limit_buckets"}
    missing = sorted(name for name in required if not db_inspector.has_table(name))
    if missing:
        raise RuntimeError(
            "database migrations are required; missing tables: " + ", ".join(missing)
        )

    with get_session_factory()() as session:
        trial = session.get(TrialProgram, "global")
        if trial is None:
            trial = TrialProgram(
                key="global",
                enabled=settings.trial_enabled,
                max_users=settings.trial_max_users,
                grant_microusd=settings.trial_grant_microusd,
                budget_microusd=settings.trial_budget_microusd,
            )
            session.add(trial)
        elif (
            settings.trial_max_users < trial.activation_count
            or settings.trial_budget_microusd < trial.allocated_microusd
        ):
            raise RuntimeError(
                "configured trial limits cannot be lower than existing allocations"
            )
        else:
            trial.enabled = settings.trial_enabled
            trial.max_users = settings.trial_max_users
            trial.grant_microusd = settings.trial_grant_microusd
            trial.budget_microusd = settings.trial_budget_microusd

        emergency = session.get(EmergencyBudget, "openrouter")
        if emergency is None:
            emergency = EmergencyBudget(
                key="openrouter",
                enabled=settings.openrouter_failover_enabled,
                hard_limit_microusd=settings.openrouter_budget_microusd,
            )
            session.add(emergency)
        elif settings.openrouter_budget_microusd < (
            emergency.spent_microusd + emergency.reserved_microusd
        ):
            raise RuntimeError(
                "configured OpenRouter budget cannot be lower than spent and reserved usage"
            )
        else:
            emergency.enabled = settings.openrouter_failover_enabled
            emergency.hard_limit_microusd = settings.openrouter_budget_microusd
        session.commit()

    from app.services.llm_billing import reconcile_stale_llm_reservations
    from app.services.rate_limits import delete_expired_rate_limits

    with get_session_factory()() as session:
        reconcile_stale_llm_reservations(session)
    with get_session_factory()() as session:
        delete_expired_rate_limits(session)


def database_is_ready() -> bool:
    try:
        engine = get_engine()
        db_inspector = inspect(engine)
        if (
            not db_inspector.has_table("users")
            or not db_inspector.has_table("trial_programs")
            or not db_inspector.has_table("emergency_budgets")
            or not db_inspector.has_table("rate_limit_buckets")
        ):
            return False
        with get_session_factory()() as session:
            session.execute(text("SELECT 1"))
            session.execute(select(TrialProgram.key).limit(1))
        return True
    except Exception:
        return False


def reset_database_caches() -> None:
    """Dispose cached state after a test changes database configuration."""
    if get_engine.cache_info().currsize:
        get_engine().dispose()
    get_session_factory.cache_clear()
    get_engine.cache_clear()
