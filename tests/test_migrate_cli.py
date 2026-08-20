"""Tests for the managed PostgreSQL migration and role bootstrap command."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.cli import migrate


ADMIN_URL = (
    "postgresql+psycopg://abdaadmin:test-only-admin-password-123456789012345"
    "@db.example:5432/abda"
    "?sslmode=require"
)
ADMIN_PASSWORD = "test-only-admin-password-123456789012345"
APP_PASSWORD = "test-only-application-password-123456789"
PASSWORD_VERIFIER = "SCRAM-SHA-256$4096:test-salt$test-stored-key:test-server-key"


class _Cursor:
    def __init__(
        self,
        *,
        role_exists: bool = False,
        memberships: tuple[str, ...] = (),
        owns_objects: bool = False,
    ) -> None:
        self.role_exists = role_exists
        self.memberships = memberships
        self.owns_objects = owns_objects
        self.calls: list[tuple[str, object | None]] = []
        self._result: object | None = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, query, parameters=None):
        rendered = query if isinstance(query, str) else query.as_string(None)
        self.calls.append((rendered, parameters))
        if "FROM pg_catalog.pg_roles WHERE rolname" in rendered:
            self._result = (self.role_exists,)
        elif "SELECT granted_role.rolname" in rendered:
            self._result = [(name,) for name in self.memberships]
        elif "FROM pg_catalog.pg_class owned_object" in rendered:
            self._result = (self.owns_objects,)

    def fetchone(self):
        assert isinstance(self._result, tuple)
        return self._result

    def fetchall(self):
        assert isinstance(self._result, list)
        return self._result


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self._cursor = cursor
        self.info = SimpleNamespace(encoding="utf-8")
        self.pgconn = SimpleNamespace(
            encrypt_password=lambda password, login, algorithm: (
                PASSWORD_VERIFIER.encode("ascii")
                if password == APP_PASSWORD.encode()
                and login == b"abda_app"
                and algorithm == b"scram-sha-256"
                else b"unexpected"
            )
        )

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def cursor(self):
        return self._cursor


def test_provisioning_creates_and_restricts_the_web_role():
    cursor = _Cursor()
    connection_parameters: dict = {}

    def connect(**kwargs):
        connection_parameters.update(kwargs)
        return _Connection(cursor)

    migrate.provision_application_role(
        ADMIN_URL,
        "abda_app",
        APP_PASSWORD,
        connect=connect,
    )

    assert connection_parameters == {
        "host": "db.example",
        "port": 5432,
        "dbname": "abda",
        "user": "abdaadmin",
        "password": ADMIN_PASSWORD,
        "sslmode": "require",
    }
    statements = [statement for statement, _parameters in cursor.calls]
    assert statements[0].startswith("SELECT EXISTS")
    assert statements[1] == 'CREATE ROLE "abda_app" NOLOGIN'
    assert any(
        'ALTER ROLE "abda_app" WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE '
        "NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD "
        in statement
        for statement in statements
    )
    assert APP_PASSWORD not in "\n".join(statements)
    assert PASSWORD_VERIFIER in "\n".join(statements)
    assert 'REVOKE ALL ON DATABASE "abda" FROM PUBLIC' in statements
    assert "REVOKE CREATE ON SCHEMA public FROM PUBLIC" in statements
    assert (
        'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "abda_app"'
        in statements
    )
    assert (
        'GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO "abda_app"'
        in statements
    )
    assert (
        'REVOKE INSERT, UPDATE, DELETE ON TABLE public.alembic_version FROM "abda_app"'
        in statements
    )
    assert (
        'ALTER ROLE "abda_app" IN DATABASE "abda" SET search_path TO public'
        in statements
    )


def test_provisioning_rotates_an_existing_role_without_recreating_it():
    cursor = _Cursor(role_exists=True)
    migrate.provision_application_role(
        ADMIN_URL,
        "abda_app",
        APP_PASSWORD,
        connect=lambda **_kwargs: _Connection(cursor),
    )

    assert all("CREATE ROLE" not in statement for statement, _parameters in cursor.calls)
    assert any("ALTER ROLE" in statement for statement, _parameters in cursor.calls)


def test_provisioning_removes_existing_role_memberships():
    cursor = _Cursor(role_exists=True, memberships=("legacy_group",))
    migrate.provision_application_role(
        ADMIN_URL,
        "abda_app",
        APP_PASSWORD,
        connect=lambda **_kwargs: _Connection(cursor),
    )

    assert ('REVOKE "legacy_group" FROM "abda_app"', None) in cursor.calls


def test_provisioning_refuses_to_mask_existing_object_ownership():
    cursor = _Cursor(role_exists=True, owns_objects=True)
    with pytest.raises(RuntimeError, match="owns public objects"):
        migrate.provision_application_role(
            ADMIN_URL,
            "abda_app",
            APP_PASSWORD,
            connect=lambda **_kwargs: _Connection(cursor),
        )


@pytest.mark.parametrize(
    ("url", "login", "password", "message"),
    [
        ("sqlite:///local.db", "abda_app", APP_PASSWORD, "requires PostgreSQL"),
        (ADMIN_URL, "abda-admin", APP_PASSWORD, "lowercase PostgreSQL role"),
        (ADMIN_URL, "postgres", APP_PASSWORD, "lowercase PostgreSQL role"),
        (ADMIN_URL, "abdaadmin", APP_PASSWORD, "logins must differ"),
        (ADMIN_URL, "abda_app", "too-short", "at least 32"),
        (
            ADMIN_URL,
            "abda_app",
            ADMIN_PASSWORD,
            "passwords must differ",
        ),
    ],
)
def test_provisioning_rejects_unsafe_credentials(url, login, password, message):
    with pytest.raises(RuntimeError, match=message):
        migrate.provision_application_role(url, login, password, connect=lambda **_kwargs: None)


def test_main_migrates_before_provisioning(monkeypatch):
    events: list[object] = []
    monkeypatch.setenv("ABDA_DATABASE_URL", ADMIN_URL)
    monkeypatch.setenv("ABDA_DATABASE_APP_LOGIN", "abda_app")
    monkeypatch.setenv("ABDA_DATABASE_APP_PASSWORD", APP_PASSWORD)
    monkeypatch.setattr(
        migrate,
        "_alembic_config",
        lambda url: SimpleNamespace(database_url=url),
    )
    monkeypatch.setattr(
        migrate.command,
        "upgrade",
        lambda config, revision: events.append(("upgrade", config.database_url, revision)),
    )
    monkeypatch.setattr(
        migrate,
        "provision_application_role",
        lambda url, login, password: events.append(("provision", url, login, password)),
    )

    assert migrate.main() == 0
    assert events == [
        ("upgrade", ADMIN_URL, "head"),
        ("provision", ADMIN_URL, "abda_app", APP_PASSWORD),
    ]
