"""Run schema migrations and provision the restricted PostgreSQL web role."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from typing import Any

import psycopg
from alembic import command
from psycopg import sql
from sqlalchemy.engine import URL, make_url

from app.db.session import _alembic_config


_ROLE_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,62}\Z")
_RESERVED_ROLES = frozenset({"azure_pg_admin", "azuresu", "postgres", "public"})


def _required_environment(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value:
        raise RuntimeError(f"{name} is required")
    return value


def _validated_inputs(
    database_url: str,
    app_login: str,
    app_password: str,
) -> URL:
    parsed = make_url(database_url)
    if parsed.get_backend_name() != "postgresql":
        raise RuntimeError("the managed migration command requires PostgreSQL")
    if not parsed.host or not parsed.database or not parsed.username or parsed.password is None:
        raise RuntimeError("ABDA_DATABASE_URL must include PostgreSQL admin credentials")
    if not _ROLE_PATTERN.fullmatch(app_login) or app_login in _RESERVED_ROLES:
        raise RuntimeError(
            "ABDA_DATABASE_APP_LOGIN must be a nonreserved lowercase PostgreSQL role name"
        )
    if app_login == parsed.username:
        raise RuntimeError("the application and administrator database logins must differ")
    if len(app_password) < 32 or app_password != app_password.strip() or "\x00" in app_password:
        raise RuntimeError(
            "ABDA_DATABASE_APP_PASSWORD must contain at least 32 characters "
            "without leading or trailing whitespace"
        )
    if app_password == parsed.password:
        raise RuntimeError("the application and administrator database passwords must differ")
    return parsed


def _connection_parameters(parsed: URL) -> dict[str, Any]:
    parameters: dict[str, Any] = {
        "host": parsed.host,
        "port": parsed.port or 5432,
        "dbname": parsed.database,
        "user": parsed.username,
        "password": parsed.password,
    }
    sslmode = parsed.query.get("sslmode")
    if sslmode:
        if not isinstance(sslmode, str):
            raise RuntimeError("ABDA_DATABASE_URL must contain one sslmode value")
        parameters["sslmode"] = sslmode
    return parameters


def _scram_password_verifier(connection, app_login: str, app_password: str) -> str:
    encoding = connection.info.encoding
    verifier = connection.pgconn.encrypt_password(
        app_password.encode(encoding),
        app_login.encode(encoding),
        b"scram-sha-256",
    )
    return verifier.decode("ascii")


def provision_application_role(
    database_url: str,
    app_login: str,
    app_password: str,
    *,
    connect: Callable[..., Any] = psycopg.connect,
) -> None:
    """Create or rotate the least-privilege role used by web replicas."""
    parsed = _validated_inputs(database_url, app_login, app_password)
    role = sql.Identifier(app_login)
    database = sql.Identifier(parsed.database or "")

    with connect(**_connection_parameters(parsed)) as connection:
        password_verifier = _scram_password_verifier(
            connection,
            app_login,
            app_password,
        )
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = %s)",
                (app_login,),
            )
            exists = bool(cursor.fetchone()[0])
            if not exists:
                cursor.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(role))

            cursor.execute(
                """
                SELECT granted_role.rolname
                FROM pg_catalog.pg_auth_members membership
                JOIN pg_catalog.pg_roles granted_role
                  ON granted_role.oid = membership.roleid
                JOIN pg_catalog.pg_roles member_role
                  ON member_role.oid = membership.member
                WHERE member_role.rolname = %s
                """,
                (app_login,),
            )
            for (granted_role,) in cursor.fetchall():
                cursor.execute(
                    sql.SQL("REVOKE {} FROM {}").format(
                        sql.Identifier(str(granted_role)),
                        role,
                    )
                )

            cursor.execute(
                """
                SELECT EXISTS (
                  SELECT 1
                  FROM pg_catalog.pg_class owned_object
                  JOIN pg_catalog.pg_namespace object_namespace
                    ON object_namespace.oid = owned_object.relnamespace
                  JOIN pg_catalog.pg_roles owner
                    ON owner.oid = owned_object.relowner
                  WHERE owner.rolname = %s
                    AND object_namespace.nspname = 'public'
                )
                """,
                (app_login,),
            )
            if bool(cursor.fetchone()[0]):
                raise RuntimeError(
                    "the application role owns public objects; transfer ownership before deployment"
                )

            cursor.execute(
                sql.SQL(
                    "ALTER ROLE {} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                    "NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD {}"
                ).format(role, sql.Literal(password_verifier))
            )
            cursor.execute(
                sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(database)
            )
            cursor.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
            cursor.execute(
                sql.SQL("REVOKE ALL PRIVILEGES ON DATABASE {} FROM {}").format(
                    database,
                    role,
                )
            )
            cursor.execute(
                sql.SQL("REVOKE ALL PRIVILEGES ON SCHEMA public FROM {}").format(role)
            )
            cursor.execute(
                sql.SQL(
                    "REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM {}"
                ).format(role)
            )
            cursor.execute(
                sql.SQL(
                    "REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM {}"
                ).format(role)
            )
            cursor.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(database, role)
            )
            cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(role))
            cursor.execute(
                sql.SQL(
                    "GRANT SELECT, INSERT, UPDATE, DELETE "
                    "ON ALL TABLES IN SCHEMA public TO {}"
                ).format(role)
            )
            cursor.execute(
                sql.SQL(
                    "REVOKE INSERT, UPDATE, DELETE "
                    "ON TABLE public.alembic_version FROM {}"
                ).format(role)
            )
            cursor.execute(
                sql.SQL(
                    "GRANT USAGE, SELECT, UPDATE "
                    "ON ALL SEQUENCES IN SCHEMA public TO {}"
                ).format(role)
            )
            cursor.execute(
                sql.SQL(
                    "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                    "REVOKE ALL PRIVILEGES ON TABLES FROM {}"
                ).format(role)
            )
            cursor.execute(
                sql.SQL(
                    "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                    "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}"
                ).format(role)
            )
            cursor.execute(
                sql.SQL(
                    "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                    "REVOKE ALL PRIVILEGES ON SEQUENCES FROM {}"
                ).format(role)
            )
            cursor.execute(
                sql.SQL(
                    "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                    "GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO {}"
                ).format(role)
            )
            cursor.execute(
                sql.SQL("ALTER ROLE {} IN DATABASE {} SET search_path TO public").format(
                    role,
                    database,
                )
            )


def main() -> int:
    database_url = _required_environment("ABDA_DATABASE_URL")
    app_login = (os.getenv("ABDA_DATABASE_APP_LOGIN") or "abda_app").strip()
    app_password = _required_environment("ABDA_DATABASE_APP_PASSWORD")
    _validated_inputs(database_url, app_login, app_password)

    command.upgrade(_alembic_config(database_url), "head")
    provision_application_role(database_url, app_login, app_password)
    print("Database migration and restricted application role provisioning completed.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
