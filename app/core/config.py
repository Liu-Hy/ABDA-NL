"""Environment-backed application settings with production safety checks."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit


# This deterministic development value is rejected in staging and production.
LOCAL_SESSION_SECRET = "abda-nl-local-session-secret-not-for-production"  # noqa: S105


def _truthy(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _integer(name: str, default: int, *, minimum: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value < minimum:
        raise RuntimeError(f"{name} must be at least {minimum}")
    return value


def _default_database_url() -> str:
    state_root = Path(
        os.getenv("XDG_STATE_HOME") or (Path.home() / ".local" / "state")
    ).expanduser()
    database_path = (state_root / "abda-nl" / "abda.db").resolve()
    return f"sqlite+pysqlite:///{database_path}"


def _safe_https_url(value: str | None) -> bool:
    if not value:
        return False
    try:
        parsed = urlsplit(value)
        parsed_port = parsed.port
    except ValueError:
        return False
    return bool(
        parsed.scheme == "https"
        and parsed.hostname
        and (parsed_port is None or parsed_port > 0)
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
    )


def _safe_https_origin(value: str | None) -> bool:
    if not _safe_https_url(value):
        return False
    return urlsplit(value or "").path in {"", "/"}


@dataclass(frozen=True)
class Settings:
    environment: str
    auth_mode: str
    database_url: str
    auto_create_database: bool
    database_pool_size: int
    database_max_overflow: int
    database_pool_timeout_seconds: int
    session_secret: str
    session_cookie: str
    session_max_age_seconds: int
    cookie_secure: bool
    mcp_token_pepper: str
    public_base_url: str | None
    oidc_metadata_url: str | None
    oidc_issuer: str | None
    oidc_client_id: str | None
    oidc_client_secret: str | None
    oidc_scope: str
    trial_enabled: bool
    trial_max_users: int
    trial_grant_microusd: int
    trial_budget_microusd: int
    llm_default_profile: str
    llm_allow_byok: bool
    llm_require_auth: bool
    openrouter_failover_enabled: bool
    openrouter_budget_microusd: int
    llm_retry_attempts: int
    llm_circuit_cooldown_seconds: int
    max_request_body_bytes: int
    abuse_protection_enabled: bool
    anonymous_requests_per_minute: int
    mutation_requests_per_minute: int
    llm_requests_per_minute: int
    metrics_token: str | None
    proxy_mode: str
    trusted_hosts: tuple[str, ...]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_managed_service(self) -> bool:
        """Return whether the process serves a remotely managed deployment."""
        return self.environment in {"staging", "production"}

    @property
    def auth_enabled(self) -> bool:
        return self.auth_mode in {"dev", "oidc"}

    @classmethod
    def from_environment(cls) -> "Settings":
        environment = (os.getenv("ABDA_ENVIRONMENT") or "development").strip().lower()
        if environment not in {"development", "test", "staging", "production"}:
            raise RuntimeError(
                "ABDA_ENVIRONMENT must be development, test, staging, or production"
            )

        default_auth_mode = "oidc" if environment in {"staging", "production"} else "dev"
        auth_mode = (os.getenv("ABDA_AUTH_MODE") or default_auth_mode).strip().lower()
        if auth_mode not in {"disabled", "dev", "oidc"}:
            raise RuntimeError("ABDA_AUTH_MODE must be disabled, dev, or oidc")

        public_base_url = (os.getenv("ABDA_PUBLIC_BASE_URL") or "").strip().rstrip("/") or None
        try:
            public_hostname = (
                urlsplit(public_base_url).hostname if public_base_url else None
            )
        except ValueError:
            public_hostname = None
        default_trusted_hosts = ["127.0.0.1", "localhost", "[::1]", "testserver"]
        if public_hostname:
            default_trusted_hosts.append(public_hostname)
        configured_trusted_hosts = tuple(
            item.strip().lower()
            for item in (os.getenv("ABDA_TRUSTED_HOSTS") or "").split(",")
            if item.strip()
        )
        session_secret = (os.getenv("ABDA_SESSION_SECRET") or LOCAL_SESSION_SECRET).strip()
        default_session_cookie = (
            "__Host-abda_session"
            if environment in {"staging", "production"}
            else "abda_session"
        )
        settings = cls(
            environment=environment,
            auth_mode=auth_mode,
            database_url=(os.getenv("ABDA_DATABASE_URL") or _default_database_url()).strip(),
            auto_create_database=_truthy(
                os.getenv("ABDA_AUTO_CREATE_DB"), default=environment in {"development", "test"}
            ),
            database_pool_size=_integer("ABDA_DATABASE_POOL_SIZE", 4, minimum=1),
            database_max_overflow=_integer(
                "ABDA_DATABASE_MAX_OVERFLOW", 1, minimum=0
            ),
            database_pool_timeout_seconds=_integer(
                "ABDA_DATABASE_POOL_TIMEOUT_SECONDS", 10, minimum=1
            ),
            session_secret=session_secret,
            session_cookie=(
                os.getenv("ABDA_SESSION_COOKIE") or default_session_cookie
            ).strip(),
            session_max_age_seconds=_integer(
                "ABDA_SESSION_MAX_AGE_SECONDS", 14 * 24 * 60 * 60, minimum=300
            ),
            cookie_secure=_truthy(
                os.getenv("ABDA_COOKIE_SECURE"),
                default=environment in {"staging", "production"},
            ),
            mcp_token_pepper=(
                os.getenv("ABDA_MCP_TOKEN_PEPPER") or session_secret
            ).strip(),
            public_base_url=public_base_url,
            oidc_metadata_url=(os.getenv("ABDA_OIDC_METADATA_URL") or "").strip() or None,
            oidc_issuer=(os.getenv("ABDA_OIDC_ISSUER") or "").strip().rstrip("/") or None,
            oidc_client_id=(os.getenv("ABDA_OIDC_CLIENT_ID") or "").strip() or None,
            oidc_client_secret=(os.getenv("ABDA_OIDC_CLIENT_SECRET") or "").strip() or None,
            oidc_scope=(os.getenv("ABDA_OIDC_SCOPE") or "openid profile email").strip(),
            trial_enabled=_truthy(os.getenv("ABDA_TRIAL_ENABLED"), default=True),
            trial_max_users=_integer("ABDA_TRIAL_MAX_USERS", 100, minimum=0),
            trial_grant_microusd=_integer(
                "ABDA_TRIAL_GRANT_MICROUSD", 5_000_000, minimum=0
            ),
            trial_budget_microusd=_integer(
                "ABDA_TRIAL_BUDGET_MICROUSD", 500_000_000, minimum=0
            ),
            llm_default_profile=(
                os.getenv("ABDA_LLM_DEFAULT_PROFILE") or "balanced"
            ).strip().lower(),
            llm_allow_byok=_truthy(os.getenv("ABDA_LLM_ALLOW_BYOK"), default=True),
            llm_require_auth=_truthy(
                os.getenv("ABDA_LLM_REQUIRE_AUTH"),
                default=environment in {"staging", "production"},
            ),
            openrouter_failover_enabled=_truthy(
                os.getenv("ABDA_OPENROUTER_FAILOVER_ENABLED"),
                default=bool((os.getenv("OPENROUTER_API_KEY") or "").strip()),
            ),
            openrouter_budget_microusd=_integer(
                "ABDA_OPENROUTER_BUDGET_MICROUSD", 500_000_000, minimum=0
            ),
            llm_retry_attempts=_integer("ABDA_LLM_RETRY_ATTEMPTS", 3, minimum=1),
            llm_circuit_cooldown_seconds=_integer(
                "ABDA_LLM_CIRCUIT_COOLDOWN_SECONDS", 60, minimum=5
            ),
            max_request_body_bytes=_integer(
                "ABDA_MAX_REQUEST_BODY_BYTES", 2_000_000, minimum=65_536
            ),
            abuse_protection_enabled=_truthy(
                os.getenv("ABDA_ABUSE_PROTECTION_ENABLED"),
                default=environment in {"staging", "production"},
            ),
            anonymous_requests_per_minute=_integer(
                "ABDA_ANONYMOUS_REQUESTS_PER_MINUTE", 120, minimum=1
            ),
            mutation_requests_per_minute=_integer(
                "ABDA_MUTATION_REQUESTS_PER_MINUTE", 60, minimum=1
            ),
            llm_requests_per_minute=_integer(
                "ABDA_LLM_REQUESTS_PER_MINUTE", 20, minimum=1
            ),
            metrics_token=(os.getenv("ABDA_METRICS_TOKEN") or "").strip() or None,
            proxy_mode=(os.getenv("ABDA_PROXY_MODE") or "direct").strip().lower(),
            trusted_hosts=configured_trusted_hosts or tuple(default_trusted_hosts),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if not self.database_url:
            raise RuntimeError("ABDA_DATABASE_URL cannot be empty")
        if self.database_pool_size > 50:
            raise RuntimeError("ABDA_DATABASE_POOL_SIZE cannot exceed 50")
        if self.database_max_overflow > 50:
            raise RuntimeError("ABDA_DATABASE_MAX_OVERFLOW cannot exceed 50")
        if self.database_pool_timeout_seconds > 120:
            raise RuntimeError("ABDA_DATABASE_POOL_TIMEOUT_SECONDS cannot exceed 120")
        if not self.session_cookie:
            raise RuntimeError("ABDA_SESSION_COOKIE cannot be empty")
        if not self.trusted_hosts or any(
            not host or "/" in host or "://" in host for host in self.trusted_hosts
        ):
            raise RuntimeError("ABDA_TRUSTED_HOSTS must contain hostnames only")
        if len(self.session_secret) < 32:
            raise RuntimeError("ABDA_SESSION_SECRET must contain at least 32 characters")
        if len(self.mcp_token_pepper) < 32:
            raise RuntimeError("ABDA_MCP_TOKEN_PEPPER must contain at least 32 characters")
        if self.trial_max_users * self.trial_grant_microusd > self.trial_budget_microusd:
            raise RuntimeError(
                "trial user count multiplied by per-user grant exceeds the trial budget"
            )
        if self.llm_default_profile not in {"economy", "balanced", "quality"}:
            raise RuntimeError(
                "ABDA_LLM_DEFAULT_PROFILE must be economy, balanced, or quality"
            )
        if self.llm_retry_attempts > 5:
            raise RuntimeError("ABDA_LLM_RETRY_ATTEMPTS cannot exceed 5")
        if self.max_request_body_bytes > 10_000_000:
            raise RuntimeError("ABDA_MAX_REQUEST_BODY_BYTES cannot exceed 10000000")
        if self.anonymous_requests_per_minute > 10_000:
            raise RuntimeError("ABDA_ANONYMOUS_REQUESTS_PER_MINUTE cannot exceed 10000")
        if self.mutation_requests_per_minute > 10_000:
            raise RuntimeError("ABDA_MUTATION_REQUESTS_PER_MINUTE cannot exceed 10000")
        if self.llm_requests_per_minute > 1_000:
            raise RuntimeError("ABDA_LLM_REQUESTS_PER_MINUTE cannot exceed 1000")
        if self.proxy_mode not in {"direct", "azure-container-apps"}:
            raise RuntimeError(
                "ABDA_PROXY_MODE must be direct or azure-container-apps"
            )
        if self.openrouter_budget_microusd > 1_000_000_000:
            raise RuntimeError("the OpenRouter emergency budget cannot exceed $1,000")
        if self.openrouter_budget_microusd > 500_000_000:
            acknowledgement = (
                os.getenv("ABDA_OPENROUTER_BUDGET_ACK") or ""
            ).strip()
            if acknowledgement != "I_ACCEPT_UP_TO_1000_USD":
                raise RuntimeError(
                    "an OpenRouter budget above $500 requires "
                    "ABDA_OPENROUTER_BUDGET_ACK=I_ACCEPT_UP_TO_1000_USD"
                )
        if self.auth_mode == "oidc":
            missing = [
                name
                for name, value in (
                    ("ABDA_OIDC_METADATA_URL", self.oidc_metadata_url),
                    ("ABDA_OIDC_CLIENT_ID", self.oidc_client_id),
                    ("ABDA_OIDC_CLIENT_SECRET", self.oidc_client_secret),
                )
                if not value
            ]
            if missing:
                raise RuntimeError(f"OIDC mode requires {', '.join(missing)}")
        if self.environment in {"staging", "production"}:
            if self.auth_mode != "oidc":
                raise RuntimeError("staging and production require ABDA_AUTH_MODE=oidc")
            if not self.llm_require_auth:
                raise RuntimeError(
                    "staging and production require authenticated LLM access"
                )
            if self.session_secret == LOCAL_SESSION_SECRET:
                raise RuntimeError("staging and production require a unique session secret")
            if not self.cookie_secure:
                raise RuntimeError("staging and production require secure session cookies")
            if not self.session_cookie.startswith("__Host-"):
                raise RuntimeError(
                    "staging and production require an __Host- session cookie name"
                )
            if not (os.getenv("ABDA_MCP_TOKEN_PEPPER") or "").strip():
                raise RuntimeError(
                    "staging and production require ABDA_MCP_TOKEN_PEPPER"
                )
            if self.mcp_token_pepper == self.session_secret:
                raise RuntimeError(
                    "ABDA_MCP_TOKEN_PEPPER must differ from ABDA_SESSION_SECRET"
                )
            if not self.public_base_url:
                raise RuntimeError("staging and production require an HTTPS public base URL")
            if not _safe_https_origin(self.public_base_url):
                raise RuntimeError(
                    "ABDA_PUBLIC_BASE_URL must be an HTTPS origin without a path"
                )
            public_url = urlsplit(self.public_base_url)
            if any("*" in host for host in self.trusted_hosts):
                raise RuntimeError(
                    "staging and production require exact trusted hostnames"
                )
            if public_url.hostname not in self.trusted_hosts:
                raise RuntimeError(
                    "ABDA_TRUSTED_HOSTS must include the public hostname"
                )
            if not _safe_https_url(self.oidc_metadata_url):
                raise RuntimeError(
                    "staging and production require a safe HTTPS OIDC metadata URL"
                )
            if not _safe_https_url(self.oidc_issuer):
                raise RuntimeError(
                    "staging and production require a safe HTTPS OIDC issuer"
                )
            oidc_scopes = set(self.oidc_scope.split())
            if not {"openid", "email"}.issubset(oidc_scopes):
                raise RuntimeError(
                    "staging and production require openid and email OIDC scopes"
                )
            if self.database_url.startswith("sqlite"):
                raise RuntimeError("staging and production require PostgreSQL")
            if self.auto_create_database:
                raise RuntimeError(
                    "staging and production require migrations before application startup"
                )
            if not self.abuse_protection_enabled:
                raise RuntimeError("staging and production require abuse protection")
            if not self.metrics_token or len(self.metrics_token) < 32:
                raise RuntimeError(
                    "staging and production require ABDA_METRICS_TOKEN with at least 32 characters"
                )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_environment()


def reset_settings_cache() -> None:
    """Clear cached settings for tests that construct isolated app configurations."""
    get_settings.cache_clear()
