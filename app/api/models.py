"""Pydantic request/response models for the ABDA-NL HTTP API.

Built for Pydantic v2 and current FastAPI releases.

Op shapes are a discriminated union on `op`; Pydantic rejects unknown
op kinds at the HTTP boundary. Payload dicts (`fact`, `assumption`,
`rule`) are passed through as free-form dicts and validated downstream
by `app.scenario.diff_ops` against the scenario JSON schema -- one
source of truth for payload shape.
"""
from __future__ import annotations

from typing import List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from typing_extensions import Annotated, Self


MAX_DIFF_OPS = 100

# --- Op models (one per kind; discriminated on "op") ---


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _OpBase(_StrictModel):
    pass


class ToggleAssumptionOp(_OpBase):
    op: Literal["toggle-assumption"]
    id: str = Field(min_length=1, max_length=100)


class ToggleRuleOp(_OpBase):
    op: Literal["toggle-rule"]
    id: str = Field(min_length=1, max_length=100)


class _NewPremiseNote(_StrictModel):
    """NL description for a premise not yet in the scenario."""
    id: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=2000)

class ModifyRuleOp(_OpBase):
    op: Literal["modify-rule"]
    id: str = Field(min_length=1, max_length=100)
    rule: dict
    new_premise_notes: Optional[List[_NewPremiseNote]] = None


class AddRuleOp(_OpBase):
    op: Literal["add-rule"]
    id: str = Field(min_length=1, max_length=100)
    rule: dict
    new_premise_notes: Optional[List[_NewPremiseNote]] = None


class RemoveRuleOp(_OpBase):
    op: Literal["remove-rule"]
    id: str = Field(min_length=1, max_length=100)


class SetBlockOp(_OpBase):
    op: Literal["set-block"]
    target: Literal["rule", "assumption"]
    id: str = Field(min_length=1, max_length=100)
    block: int = Field(ge=1, le=1000)


class AddFactOp(_OpBase):
    op: Literal["add-fact"]
    id: str = Field(min_length=1, max_length=100)
    fact: dict


class RemoveFactOp(_OpBase):
    op: Literal["remove-fact"]
    id: str = Field(min_length=1, max_length=100)


class AddAssumptionOp(_OpBase):
    op: Literal["add-assumption"]
    id: str = Field(min_length=1, max_length=100)
    assumption: dict


class RemoveAssumptionOp(_OpBase):
    op: Literal["remove-assumption"]
    id: str = Field(min_length=1, max_length=100)


DiffOp = Annotated[
    Union[
        ToggleAssumptionOp,
        ToggleRuleOp,
        ModifyRuleOp,
        AddRuleOp,
        RemoveRuleOp,
        SetBlockOp,
        AddFactOp,
        RemoveFactOp,
        AddAssumptionOp,
        RemoveAssumptionOp,
    ],
    Field(discriminator="op"),
]


# --- Request / response envelopes ---


class StateRequest(_StrictModel):
    scenario_id: str = Field(min_length=1, max_length=100)
    diff_ops: List[DiffOp] = Field(default_factory=list, max_length=MAX_DIFF_OPS)

class StateResponse(_StrictModel):
    """Bundled state. Returned by both `GET /scenarios/{id}`
    (baseline, zero ops) and `POST /state` (after applying ops).
    """
    scenario: dict
    af: dict

class ScenarioListItem(BaseModel):
    id: str
    title: str
    description: str = ""


class ScenarioListResponse(BaseModel):
    scenarios: List[ScenarioListItem]


class LLMProfileConfig(_StrictModel):
    id: str
    display_name: str
    description: str


class BYOKModelConfig(_StrictModel):
    id: str
    display_name: str


class BYOKProviderConfig(_StrictModel):
    id: Literal["anthropic", "openai", "google", "openrouter"]
    display_name: str
    default_model: str
    models: List[BYOKModelConfig]


class ConfigResponse(_StrictModel):
    llm_enabled: bool
    llm_auth_required: bool
    byok_enabled: bool
    byok_keys_stored: Literal[False] = False
    default_profile: str
    profiles: List[LLMProfileConfig] = Field(default_factory=list)
    byok_providers: List[BYOKProviderConfig] = Field(default_factory=list)


# --- Chat ---


class ChatMessage(_StrictModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20_000)


class BYOKRequest(_StrictModel):
    provider: Literal["anthropic", "openai", "google", "openrouter"]
    api_key: SecretStr
    model: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    )

    @field_validator("api_key")
    @classmethod
    def _api_key_is_nonempty(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value().strip()
        if not secret or len(secret) > 4096:
            raise ValueError("API key must contain between 1 and 4096 characters")
        return SecretStr(secret)


class LLMRequestOptions(_StrictModel):
    profile: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9-]*$",
    )
    byok: Optional[BYOKRequest] = None

    @model_validator(mode="after")
    def _profile_or_byok(self) -> Self:
        if self.profile is not None and self.byok is not None:
            raise ValueError("choose either a funded profile or BYOK, not both")
        return self


class ChatRequest(_StrictModel):
    scenario_id: str = Field(min_length=1, max_length=100)
    diff_ops: List[DiffOp] = Field(default_factory=list, max_length=MAX_DIFF_OPS)
    messages: List[ChatMessage] = Field(min_length=1, max_length=50)
    llm: Optional[LLMRequestOptions] = None

class ChatUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


class ChatResponse(_StrictModel):
    message: str
    stop_reason: str
    model: str
    provider: str
    billing_source: str
    route: str
    cost_microusd: int = Field(ge=0)
    request_id: str
    usage: ChatUsage
    latency_ms: int
    retried: bool = False

# --- Propose ---


class ProposeRequest(_StrictModel):
    scenario_id: str = Field(min_length=1, max_length=100)
    diff_ops: List[DiffOp] = Field(default_factory=list, max_length=MAX_DIFF_OPS)
    task: Literal["add-rule", "modify-rule", "add-fact", "add-assumption"]
    instruction: str = Field(min_length=1, max_length=20_000)
    existing_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    llm: Optional[LLMRequestOptions] = None

class ReviewIssueModel(_StrictModel):
    severity: Literal["blocker", "warning", "note"]
    message: str

# --- Save as new scenario ---


class SaveScenarioRequest(_StrictModel):
    source_id: str = Field(min_length=1, max_length=100)
    diff_ops: List[DiffOp] = Field(default_factory=list, max_length=MAX_DIFF_OPS)
    save_as_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    overwrite: bool = False

class SaveScenarioResponse(_StrictModel):
    """Response after a successful save. Bundled state so the UI can
    pivot to the saved scenario without a follow-up fetch.
    """
    id: str
    title: str
    scenario: dict
    af: dict

class ProposeResponse(_StrictModel):
    op: dict  # a ready-to-apply diff_op
    stop_reason: str
    model: str
    provider: str
    billing_source: str
    route: str
    cost_microusd: int = Field(ge=0)
    request_id: str
    usage: ChatUsage
    latency_ms: int
    # Number of Proposer attempts it took to pass deterministic
    # validation.  1 = no retry; 2-3 = Validator flagged early
    # attempt(s) and the Proposer corrected on retry.
    proposer_attempts: int = 1
    # Whether the LLM Reviewer was run on this op. False for trivial
    # edits (add-fact / add-assumption) where the Reviewer is skipped.
    reviewed: bool = False
    # Advisory semantic issues from the Reviewer. Never blocks; the UI
    # surfaces them alongside the op and the user decides whether to
    # Apply, Refine, or Cancel.
    review_issues: List[ReviewIssueModel] = Field(default_factory=list)

# --- Error envelope ---


class ErrorDetail(BaseModel):
    code: str
    path: str = "<root>"
    message: str


class ErrorResponse(BaseModel):
    errors: List[ErrorDetail]
