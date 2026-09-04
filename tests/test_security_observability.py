"""Public request boundaries, shared rate limits, and safe telemetry."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.api.abuse import _client_subject
from app.api import main as main_module
from app.api.main import app
from app.core.config import Settings
from app.core.config import get_settings
from app.db.models import Base, RateLimitBucket, User
from app.scenario.catalog import load_bundled_scenario
from app.scenario.serialize import scenario_to_dict
from app.services.projects import (
    ProjectLimitError,
    ShareLinkLimitError,
    create_project,
    create_share_link,
    get_project,
    update_project,
)
from app.services.rate_limits import (
    consume_rate_limit,
    delete_expired_rate_limits,
    delete_expired_rate_limits_if_due,
)
from app.observability import RequestMetrics


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def test_request_body_limit_rejects_before_json_parsing(client: TestClient):
    response = client.post(
        "/state",
        content=b"x" * 2_000_001,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "request_too_large"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-request-id"]


def test_untrusted_host_is_rejected_with_security_headers(client: TestClient):
    response = client.get("/", headers={"Host": "attacker.example"})
    assert response.status_code == 400
    assert response.headers["x-frame-options"] == "DENY"


def test_private_api_responses_are_not_browser_cached(client: TestClient):
    response = client.get("/api/auth/session")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"


def _network_request(*, forwarded_for: str | None = None) -> Request:
    headers = []
    if forwarded_for is not None:
        headers.append((b"x-forwarded-for", forwarded_for.encode("ascii")))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "http",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": headers,
            "client": ("10.42.0.7", 40000),
            "server": ("127.0.0.1", 8000),
        }
    )


def test_cancelled_request_releases_in_flight_metric(monkeypatch):
    metrics = RequestMetrics()
    monkeypatch.setattr(main_module, "REQUEST_METRICS", metrics)
    request = _network_request()

    async def cancel_request(_request):
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(main_module._request_context(request, cancel_request))

    rendered = metrics.render()
    assert "abda_http_requests_in_flight 0" in rendered
    assert 'method="GET"' not in rendered


def test_direct_proxy_mode_ignores_forwarded_client_header():
    settings = replace(get_settings(), proxy_mode="direct")
    request = _network_request(forwarded_for="198.51.100.8")
    assert _client_subject(request, settings) == "client:10.42.0.7"


def test_azure_proxy_mode_uses_only_rightmost_platform_address():
    settings = replace(get_settings(), proxy_mode="azure-container-apps")
    request = _network_request(
        forwarded_for="192.0.2.9, 198.51.100.8, 203.0.113.11"
    )
    assert _client_subject(request, settings) == "client:203.0.113.11"


def test_azure_proxy_mode_rejects_malformed_rightmost_address():
    settings = replace(get_settings(), proxy_mode="azure-container-apps")
    request = _network_request(forwarded_for="198.51.100.8, not-an-address")
    assert _client_subject(request, settings) == "client:10.42.0.7"


@pytest.mark.parametrize(
    ("environment", "expected"),
    [
        ("development", False),
        ("test", False),
        ("staging", True),
        ("production", True),
    ],
)
def test_managed_service_boundary(environment: str, expected: bool):
    settings = replace(get_settings(), environment=environment)
    assert settings.is_managed_service is expected


def test_internal_metrics_are_low_cardinality_and_include_budget_totals(
    client: TestClient,
):
    client.get("/health/live")
    client.get("/not-a-route/private-path-value")
    response = client.get("/internal/metrics")
    assert response.status_code == 200
    body = response.text
    assert "abda_http_requests_total" in body
    assert "abda_database_pool_capacity 5" in body
    assert "abda_database_pool_checked_out" in body
    assert 'route="/health/live"' in body
    assert "abda_trial_activations" in body
    assert "abda_trial_enabled 1" in body
    assert "abda_trial_max_users 100" in body
    assert "abda_trial_grant_microusd 5000000" in body
    assert "abda_trial_budget_microusd 500000000" in body
    assert "abda_trial_reserved_microusd 0" in body
    assert "abda_trial_uncertain_charged_reservations 0" in body
    assert "abda_trial_uncertain_charged_microusd 0" in body
    assert "abda_openrouter_budget_microusd" in body
    assert "abda_openrouter_enabled" in body
    assert "abda_openrouter_uncertain_charged_reservations 0" in body
    assert "abda_openrouter_uncertain_charged_microusd 0" in body
    assert "example.edu" not in body
    assert "private-path-value" not in body
    assert 'route="<unmatched>"' in body


def test_nonstandard_http_method_is_normalized_in_metrics_and_logs(
    client: TestClient,
    caplog,
):
    attacker_method = "PRIVATE-METHOD-MARKER"
    with caplog.at_level("INFO", logger="app.api.main"):
        response = client.request(attacker_method, "/health/live")

    assert response.status_code == 405
    metrics = client.get("/internal/metrics").text
    assert 'method="OTHER"' in metrics
    assert attacker_method not in metrics
    assert attacker_method not in caplog.text
    assert "method=OTHER" in caplog.text


def test_http_rate_limit_returns_retry_contract(client: TestClient):
    limited = replace(
        get_settings(),
        abuse_protection_enabled=True,
        anonymous_requests_per_minute=1,
    )
    app.dependency_overrides[get_settings] = lambda: limited
    try:
        first = client.post(
            "/api/auth/dev/login",
            json={"email": "rate-limit-contract@example.edu"},
        )
        second = client.post(
            "/api/auth/dev/login",
            json={"email": "rate-limit-contract@example.edu"},
        )
    finally:
        app.dependency_overrides.pop(get_settings, None)
    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["detail"]["code"] == "rate_limit_exceeded"
    assert int(second.headers["retry-after"]) >= 1
    assert second.headers["x-ratelimit-remaining"] == "0"


@pytest.fixture
def rate_limit_factory(tmp_path):
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'limits.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    engine.dispose()


def test_rate_limit_is_exact_and_does_not_store_raw_subject(rate_limit_factory):
    now = datetime(2026, 8, 17, 12, 0, 5, tzinfo=timezone.utc)
    secret = "rate-limit-test-secret-with-32-characters"
    results = []
    with rate_limit_factory() as session:
        for _ in range(4):
            results.append(
                consume_rate_limit(
                    session,
                    scope="test_scope",
                    subject="user:private-user-id",
                    limit=3,
                    window_seconds=60,
                    secret=secret,
                    now=now,
                )
            )
        bucket = session.scalar(select(RateLimitBucket))
        assert bucket is not None
        assert "private-user-id" not in bucket.key
        assert bucket.request_count == 4

    assert [result.allowed for result in results] == [True, True, True, False]
    assert results[-1].remaining == 0
    assert results[-1].retry_after_seconds == 55

    with rate_limit_factory() as session:
        next_window = consume_rate_limit(
            session,
            scope="test_scope",
            subject="user:private-user-id",
            limit=3,
            window_seconds=60,
            secret=secret,
            now=now + timedelta(minutes=1),
        )
        assert next_window.allowed is True
        assert delete_expired_rate_limits(
            session, now=now + timedelta(minutes=1)
        ) == 1


def test_rate_limit_cap_is_exact_under_concurrency(rate_limit_factory):
    now = datetime(2026, 8, 17, 13, 0, tzinfo=timezone.utc)
    secret = "concurrent-rate-limit-secret-32-characters"

    def consume(_index: int) -> bool:
        with rate_limit_factory() as session:
            return consume_rate_limit(
                session,
                scope="concurrent",
                subject="user:one",
                limit=5,
                window_seconds=60,
                secret=secret,
                now=now,
            ).allowed

    with ThreadPoolExecutor(max_workers=8) as executor:
        allowed = list(executor.map(consume, range(20)))
    assert sum(allowed) == 5


def test_due_rate_limit_cleanup_deletes_only_expired_rows(
    rate_limit_factory, monkeypatch
):
    import app.services.rate_limits as rate_limits_module

    now = datetime(2026, 8, 17, 14, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(
        rate_limits_module, "_next_rate_limit_cleanup_monotonic", 0.0
    )
    with rate_limit_factory() as session:
        session.add_all(
            [
                RateLimitBucket(
                    key="expired",
                    scope="cleanup",
                    request_count=1,
                    window_started_at=now - timedelta(minutes=2),
                    expires_at=now - timedelta(minutes=1),
                ),
                RateLimitBucket(
                    key="active",
                    scope="cleanup",
                    request_count=1,
                    window_started_at=now,
                    expires_at=now + timedelta(minutes=1),
                ),
            ]
        )
        session.commit()

        assert delete_expired_rate_limits_if_due(
            session, now=now, monotonic_now=100.0
        ) == 1
        assert delete_expired_rate_limits_if_due(
            session, now=now, monotonic_now=101.0
        ) is None
        assert session.scalars(select(RateLimitBucket.key)).all() == ["active"]


def test_rate_limit_cleanup_failure_does_not_fail_accounting_or_log_secrets(
    rate_limit_factory, monkeypatch, caplog
):
    import app.services.rate_limits as rate_limits_module

    def fail_cleanup(*_args, **_kwargs):
        raise RuntimeError("private-account@example.edu bearer-private-value")

    monkeypatch.setattr(
        rate_limits_module, "_next_rate_limit_cleanup_monotonic", 0.0
    )
    monkeypatch.setattr(
        rate_limits_module, "delete_expired_rate_limits", fail_cleanup
    )
    monkeypatch.setattr(rate_limits_module.time, "monotonic", lambda: 100.0)
    now = datetime(2026, 8, 17, 15, 0, tzinfo=timezone.utc)
    with caplog.at_level("ERROR", logger="app.services.rate_limits"):
        with rate_limit_factory() as session:
            result = consume_rate_limit(
                session,
                scope="cleanup_failure",
                subject="user:private-user-id",
                limit=2,
                window_seconds=60,
                secret="cleanup-failure-rate-limit-secret-32-characters",
                now=now,
            )
            bucket = session.scalar(select(RateLimitBucket))

    assert result.allowed is True
    assert bucket is not None
    assert bucket.request_count == 1
    assert "rate_limit_cleanup_failed exception=RuntimeError" in caplog.text
    assert "private-account@example.edu" not in caplog.text
    assert "bearer-private-value" not in caplog.text
    assert rate_limits_module._next_rate_limit_cleanup_monotonic == 400.0


def test_project_and_share_record_caps_are_enforced(
    rate_limit_factory, monkeypatch
):
    import app.services.projects as projects_module

    monkeypatch.setattr(projects_module, "MAX_ACTIVE_PROJECTS", 1)
    monkeypatch.setattr(projects_module, "MAX_ACTIVE_SHARE_LINKS", 1)
    scenario = scenario_to_dict(load_bundled_scenario("fire_prevention"))
    with rate_limit_factory() as session:
        user = User(email="project-cap@example.edu", email_verified=True)
        session.add(user)
        session.commit()
        project = create_project(
            session,
            user,
            name="First",
            description="",
            scenario=scenario,
            source_scenario_id="fire_prevention",
        )
        with pytest.raises(ProjectLimitError, match="active projects"):
            create_project(
                session,
                user,
                name="Second",
                description="",
                scenario=scenario,
                source_scenario_id="fire_prevention",
            )
        session.rollback()
        create_share_link(session, user, project.id)
        with pytest.raises(ShareLinkLimitError, match="active share links"):
            create_share_link(session, user, project.id)


def test_project_service_rejects_empty_update_without_advancing_version(
    rate_limit_factory,
):
    scenario = scenario_to_dict(load_bundled_scenario("fire_prevention"))
    with rate_limit_factory() as session:
        user = User(email="empty-service-update@example.edu", email_verified=True)
        session.add(user)
        session.commit()
        project = create_project(
            session,
            user,
            name="Stable service project",
            description="",
            scenario=scenario,
            source_scenario_id="fire_prevention",
        )

        with pytest.raises(ValueError, match="name, description, or scenario"):
            update_project(
                session,
                user,
                project.id,
                expected_version=project.version,
            )

        assert get_project(session, user, project.id).version == 1


def _production_environment(monkeypatch) -> None:
    values = {
        "ABDA_ENVIRONMENT": "production",
        "ABDA_AUTH_MODE": "oidc",
        "ABDA_DATABASE_URL": "postgresql+psycopg://user:pass@db.example/abda",
        "ABDA_AUTO_CREATE_DB": "0",
        "ABDA_SESSION_SECRET": "production-session-secret-at-least-32-characters",
        "ABDA_MCP_TOKEN_PEPPER": "production-mcp-pepper-different-and-long-enough",
        "ABDA_METRICS_TOKEN": "production-metrics-token-at-least-32-characters",
        "ABDA_PUBLIC_BASE_URL": "https://demo.abda-nl.org",
        "ABDA_OIDC_METADATA_URL": "https://login.example/.well-known/openid-configuration",
        "ABDA_OIDC_ISSUER": "https://login.example/",
        "ABDA_OIDC_CLIENT_ID": "abda-client",
        "ABDA_OIDC_CLIENT_SECRET": "oidc-secret",
        "ABDA_LLM_REQUIRE_AUTH": "1",
        "ABDA_PROXY_MODE": "azure-container-apps",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("ABDA_SESSION_COOKIE", raising=False)
    monkeypatch.delenv("ABDA_COOKIE_SECURE", raising=False)
    monkeypatch.delenv("ABDA_ABUSE_PROTECTION_ENABLED", raising=False)


def test_production_defaults_use_host_cookie_and_exact_trusted_host(monkeypatch):
    _production_environment(monkeypatch)
    settings = Settings.from_environment()
    assert settings.session_cookie == "__Host-abda_session"
    assert settings.cookie_secure is True
    assert settings.trusted_hosts == (
        "127.0.0.1",
        "localhost",
        "[::1]",
        "testserver",
        "demo.abda-nl.org",
    )
    assert settings.proxy_mode == "azure-container-apps"
    assert settings.database_pool_size == 4
    assert settings.database_max_overflow == 1
    assert settings.database_pool_timeout_seconds == 10


def test_production_normalizes_explicit_trusted_hostnames(monkeypatch):
    _production_environment(monkeypatch)
    monkeypatch.setenv(
        "ABDA_TRUSTED_HOSTS",
        "GENERATED.EXAMPLE.ORG, DEMO.ABDA-NL.ORG",
    )
    settings = Settings.from_environment()
    assert settings.trusted_hosts == (
        "generated.example.org",
        "demo.abda-nl.org",
    )


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("ABDA_COOKIE_SECURE", "0", "secure session cookies"),
        ("ABDA_SESSION_COOKIE", "abda_session", "__Host-"),
        ("ABDA_ABUSE_PROTECTION_ENABLED", "0", "abuse protection"),
        ("ABDA_PUBLIC_BASE_URL", "https://example.org/path", "HTTPS origin"),
        ("ABDA_PUBLIC_BASE_URL", "https://example.org:0", "HTTPS origin"),
        ("ABDA_PUBLIC_BASE_URL", "https://example.org:70000", "HTTPS origin"),
        ("ABDA_PUBLIC_BASE_URL", "https://[invalid", "HTTPS origin"),
        ("ABDA_TRUSTED_HOSTS", "*.abda-nl.org", "exact trusted hostnames"),
        ("ABDA_TRUSTED_HOSTS", "generated.example.org", "public hostname"),
        (
            "ABDA_OIDC_METADATA_URL",
            "https://user:secret@login.example/.well-known/openid-configuration",
            "safe HTTPS OIDC metadata URL",
        ),
        (
            "ABDA_OIDC_METADATA_URL",
            "https://login.example/.well-known/openid-configuration?tenant=abda",
            "safe HTTPS OIDC metadata URL",
        ),
        (
            "ABDA_OIDC_ISSUER",
            "https://login.example/#unexpected",
            "safe HTTPS OIDC issuer",
        ),
        ("ABDA_OIDC_SCOPE", "openid profile", "openid and email"),
        ("ABDA_PROXY_MODE", "trust-everything", "ABDA_PROXY_MODE"),
    ],
)
def test_production_rejects_unsafe_boundaries(monkeypatch, name, value, message):
    _production_environment(monkeypatch)
    monkeypatch.setenv(name, value)
    with pytest.raises(RuntimeError, match=message):
        Settings.from_environment()


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("ABDA_DATABASE_POOL_SIZE", "51", "POOL_SIZE"),
        ("ABDA_DATABASE_MAX_OVERFLOW", "51", "MAX_OVERFLOW"),
        ("ABDA_DATABASE_POOL_TIMEOUT_SECONDS", "121", "POOL_TIMEOUT"),
    ],
)
def test_database_pool_settings_reject_unbounded_values(
    monkeypatch, name, value, message
):
    monkeypatch.setenv(name, value)
    with pytest.raises(RuntimeError, match=message):
        Settings.from_environment()


def test_postgres_engine_applies_the_configured_pool_budget(monkeypatch):
    from app.db import session as session_module

    settings = replace(
        get_settings(),
        database_url="postgresql+psycopg://user:password@db.example/abda",
        database_pool_size=4,
        database_max_overflow=1,
        database_pool_timeout_seconds=10,
    )
    captured: dict = {}
    sentinel = object()

    def fake_create_engine(database_url, **kwargs):
        captured["database_url"] = database_url
        captured["kwargs"] = kwargs
        return sentinel

    monkeypatch.setattr(session_module, "get_settings", lambda: settings)
    monkeypatch.setattr(session_module, "create_engine", fake_create_engine)

    assert session_module.get_engine.__wrapped__() is sentinel
    assert captured == {
        "database_url": settings.database_url,
        "kwargs": {
            "pool_pre_ping": True,
            "pool_size": 4,
            "max_overflow": 1,
            "pool_timeout": 10,
        },
    }
