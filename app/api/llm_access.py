"""Request-scoped LLM access, public profile gating, and safe HTTP errors."""
from __future__ import annotations

from collections.abc import Callable

from fastapi import HTTPException, status

from app.api.models import (
    BYOKModelConfig,
    BYOKProviderConfig,
    ConfigResponse,
    LLMProfileConfig,
    LLMRequestOptions,
)
from app.core.config import Settings, get_settings
from app.db.models import User
from app.llm import LLMClient, LLMResponseValidationError, resolve_backend
from app.llm.catalog import ModelCatalog, ProfileSpec, load_model_catalog
from app.llm.client import resolve_claude_provider
from app.llm.providers import LLMProviderError
from app.llm.routing import (
    BYOKCredential,
    BYOKValidationError,
    CallContext,
    LLMRouteConfigurationError,
    LLMRouter,
    OPENROUTER_REQUEST_MODELS,
)
from app.services.emergency_budget import (
    EmergencyBudgetExceededError,
    EmergencyBudgetUnavailableError,
    EmergencyReservationError,
)
from app.services.trials import (
    InsufficientTrialCreditError,
    TrialUnavailableError,
    UsageReservationError,
)


class LLMAccessError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


HANDLED_LLM_ERRORS = (
    LLMAccessError,
    BYOKValidationError,
    LLMRouteConfigurationError,
    LLMProviderError,
    LLMResponseValidationError,
    InsufficientTrialCreditError,
    TrialUnavailableError,
    UsageReservationError,
    EmergencyBudgetExceededError,
    EmergencyBudgetUnavailableError,
    EmergencyReservationError,
)


def _require_llm_access(user: User | None, settings: Settings) -> None:
    if not settings.llm_require_auth:
        return
    if user is None:
        raise LLMAccessError(
            status.HTTP_401_UNAUTHORIZED,
            "authentication_required",
            "Sign in with a verified email address to use language models.",
        )
    if not user.email_verified:
        raise LLMAccessError(
            status.HTTP_403_FORBIDDEN,
            "email_verification_required",
            "Verify your email address to use language models.",
        )


def _profile_for_request(
    profile_id: str | None,
    *,
    settings: Settings,
    catalog: ModelCatalog,
) -> ProfileSpec:
    chosen = (profile_id or settings.llm_default_profile).strip().lower()
    profile = catalog.profiles.get(chosen)
    if profile is None:
        raise LLMAccessError(
            status.HTTP_400_BAD_REQUEST,
            "model_profile_invalid",
            "The selected model profile is not available.",
        )
    if not profile.public_ready:
        raise LLMAccessError(
            status.HTTP_400_BAD_REQUEST,
            "model_profile_not_ready",
            "The selected model profile has not passed the public quality gate.",
        )
    return profile


def _should_use_router(options: LLMRequestOptions | None, settings: Settings) -> bool:
    if options is not None and (options.profile is not None or options.byok is not None):
        return True
    if settings.environment in {"staging", "production"}:
        return True
    return resolve_backend() == "claude" and resolve_claude_provider() == "foundry"


def select_request_llm_client(
    options: LLMRequestOptions | None,
    *,
    user: User | None,
    request_id: str,
    request_kind: str,
    legacy_factory: Callable[[], LLMClient],
    settings: Settings | None = None,
    router: LLMRouter | None = None,
) -> LLMClient:
    """Select one request-scoped route without retaining a user API key."""
    active_settings = settings or get_settings()
    _require_llm_access(user, active_settings)

    if not _should_use_router(options, active_settings):
        return legacy_factory()

    active_router = router or LLMRouter(settings=active_settings)
    byok = options.byok if options is not None else None
    context = CallContext(
        user_id=user.id if user is not None else None,
        request_id=request_id,
        request_kind=request_kind,
        charge_trial=active_settings.llm_require_auth and byok is None,
    )
    if byok is not None:
        credential = BYOKCredential(
            provider=byok.provider,
            api_key=byok.api_key.get_secret_value(),
            model=byok.model,
        )
        return active_router.byok(credential, context=context)

    profile = _profile_for_request(
        options.profile if options is not None else None,
        settings=active_settings,
        catalog=active_router.catalog,
    )
    return active_router.funded(profile.id, context=context)


def _models_for_provider(
    provider: str, catalog: ModelCatalog
) -> list[BYOKModelConfig]:
    if provider == "openrouter":
        model_ids = [
            model_id
            for model_id in OPENROUTER_REQUEST_MODELS
            if model_id in catalog.models
        ]
    else:
        model_ids = [
            model.id for model in catalog.models.values() if model.family == provider
        ]
    return [
        BYOKModelConfig(id=model_id, display_name=catalog.models[model_id].display_name)
        for model_id in model_ids
    ]


def build_llm_config(
    *,
    llm_enabled: bool,
    settings: Settings | None = None,
    catalog: ModelCatalog | None = None,
) -> ConfigResponse:
    active_settings = settings or get_settings()
    active_catalog = catalog or load_model_catalog()
    profiles = [
        LLMProfileConfig(
            id=profile.id,
            display_name=profile.display_name,
            description=profile.description,
        )
        for profile in active_catalog.profiles.values()
        if profile.public_ready
    ]

    providers: list[BYOKProviderConfig] = []
    if active_settings.llm_allow_byok:
        for provider, default in active_catalog.byok_defaults.items():
            providers.append(
                BYOKProviderConfig(
                    id=provider,
                    display_name=default.display_name,
                    default_model=default.model,
                    models=_models_for_provider(provider, active_catalog),
                )
            )

    return ConfigResponse(
        llm_enabled=llm_enabled,
        llm_auth_required=active_settings.llm_require_auth,
        byok_enabled=llm_enabled and active_settings.llm_allow_byok,
        byok_keys_stored=False,
        default_profile=active_settings.llm_default_profile,
        profiles=profiles,
        byok_providers=providers,
    )


def llm_http_exception(exc: Exception, *, byok: bool) -> HTTPException:
    """Map expected provider and accounting failures to sanitized responses."""
    if isinstance(exc, LLMAccessError):
        return HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        )
    if isinstance(exc, BYOKValidationError):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "byok_configuration_invalid",
                "message": "The selected BYOK provider or model is not supported.",
            },
        )
    if isinstance(exc, InsufficientTrialCreditError):
        return HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={"code": "trial_credit_required", "message": str(exc)},
        )
    if isinstance(exc, LLMProviderError) and byok:
        response_headers: dict[str, str] | None = None
        if exc.status_code in {401, 403}:
            code = "byok_credentials_rejected"
            message = "The provider rejected this API key. Check the key and try again."
            response_status = status.HTTP_400_BAD_REQUEST
        elif exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
            code = "byok_provider_rate_limited"
            message = (
                "The provider rate-limited this key or its account quota. "
                "Check the provider account and try again later."
            )
            response_status = status.HTTP_429_TOO_MANY_REQUESTS
            response_headers = {"Retry-After": "30"}
        elif exc.error_type == "content_blocked":
            code = "byok_request_rejected"
            message = (
                "The provider declined this request. Revise it or check the "
                "provider's content policy."
            )
            response_status = status.HTTP_400_BAD_REQUEST
        elif (
            exc.status_code is not None
            and 400 <= exc.status_code < 500
            and not exc.outage_candidate
        ):
            code = "byok_request_rejected"
            message = (
                "The provider rejected this account, model, or request. "
                "Check provider billing, model access, and request settings."
            )
            response_status = status.HTTP_400_BAD_REQUEST
        else:
            code = "byok_provider_unavailable"
            message = "The selected provider is temporarily unavailable."
            response_status = status.HTTP_503_SERVICE_UNAVAILABLE
            response_headers = {"Retry-After": "30"}
        return HTTPException(
            status_code=response_status,
            detail={"code": code, "message": message},
            headers=response_headers,
        )
    if isinstance(exc, LLMResponseValidationError) and byok:
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "byok_provider_unavailable",
                "message": "The selected provider returned an unusable response.",
            },
            headers={"Retry-After": "30"},
        )
    if isinstance(exc, (EmergencyBudgetExceededError, EmergencyBudgetUnavailableError)):
        code = "backup_provider_unavailable"
        message = "The backup provider is temporarily unavailable. Please try again later."
    elif isinstance(exc, LLMRouteConfigurationError):
        code = "llm_route_unavailable"
        message = "The configured language model route is unavailable."
    elif isinstance(exc, TrialUnavailableError):
        code = "trial_unavailable"
        message = "Funded model access is temporarily unavailable."
    elif isinstance(exc, (UsageReservationError, EmergencyReservationError)):
        code = "usage_accounting_unavailable"
        message = (
            "Usage accounting is temporarily unavailable. The request may have used "
            "credit, so check the displayed balance before retrying."
        )
    else:
        code = "llm_provider_unavailable"
        message = "The language model provider is temporarily unavailable."
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"code": code, "message": message},
        headers={"Retry-After": "30"},
    )
