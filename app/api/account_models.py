"""HTTP models for accounts, durable projects, sharing, and trial credit."""
from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.api.models import (
    MAX_DIFF_OPS,
    ChatMessage,
    ChatContextRef,
    DiffOp,
    LLMRequestOptions,
)


class UserView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    email_verified: bool
    display_name: Optional[str] = None


class AuthSessionResponse(BaseModel):
    authenticated: bool
    auth_mode: str
    login_url: Optional[str] = None
    user: Optional[UserView] = None
    scenario_admin: bool = False
    can_switch_admin_view: bool = False
    normal_user_view: bool = False
    community_catalog_enabled: bool = True


class AdminViewModeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    normal_user_view: bool = Field(strict=True)


class LogoutResponse(BaseModel):
    logout_url: str


class DevelopmentLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    display_name: Optional[str] = Field(default=None, max_length=200)


class ProjectCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=4000)
    source_scenario_id: str = Field(min_length=1, max_length=100)
    diff_ops: List[DiffOp] = Field(default_factory=list, max_length=MAX_DIFF_OPS)


class ProjectImportRequest(BaseModel):
    """Create a private project from a validated in-memory scenario."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=4000)
    source_scenario_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    scenario: dict


class ProjectUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=4000)
    scenario: Optional[dict] = None

    @model_validator(mode="after")
    def require_change(self) -> ProjectUpdateRequest:
        if self.name is None and self.description is None and self.scenario is None:
            raise ValueError("provide a name, description, or scenario to update")
        return self


class ProjectRestoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)


class ArchivedProjectDeleteTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=36, strict=True)
    expected_version: int = Field(ge=1, strict=True)


class ArchivedProjectsDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    projects: List[ArchivedProjectDeleteTarget] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def unique_projects(self) -> ArchivedProjectsDeleteRequest:
        if len({item.id for item in self.projects}) != len(self.projects):
            raise ValueError("each project must appear only once")
        return self


class ArchivedProjectsDeleteResponse(BaseModel):
    deleted_ids: List[str]
    deleted_count: int


class ScenarioFilePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=1_000_000, repr=False)


class ScenarioFilePreviewResponse(BaseModel):
    scenario: dict
    source_scenario_id: Optional[str] = None
    warnings: List[str]


class AspicPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=120)
    rules: str = Field(min_length=1, max_length=100_000, repr=False)
    glossary: str = Field(default="", max_length=200_000, repr=False)
    conclusions: str = Field(default="", max_length=5000)


class ScenarioEditorPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: dict = Field(repr=False)
    source_scenario_id: Optional[str] = Field(default=None, max_length=100)
    rules: Optional[str] = Field(default=None, max_length=100_000, repr=False)
    glossary: str = Field(default="", max_length=200_000, repr=False)


class ScenarioExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: dict = Field(repr=False)
    source_scenario_id: Optional[str] = Field(default=None, max_length=100)


class SourcePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str = Field(min_length=1, max_length=255)
    data_base64: str = Field(min_length=1, max_length=1_333_336, repr=False)


class GlossaryPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: dict = Field(repr=False)
    glossary: str = Field(max_length=200_000, repr=False)


class ProjectWorkingStateRequest(BaseModel):
    """Apply temporary operations to the saved project version."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    diff_ops: List[DiffOp] = Field(default_factory=list, max_length=MAX_DIFF_OPS)


class ProjectChatRequest(ProjectWorkingStateRequest):
    messages: List[ChatMessage] = Field(min_length=1, max_length=50)
    llm: Optional[LLMRequestOptions] = None
    context_refs: List[ChatContextRef] = Field(default_factory=list, max_length=24)


class ProjectProposeRequest(ProjectWorkingStateRequest):
    task: Literal["add-rule", "modify-rule", "add-fact", "add-assumption"]
    instruction: str = Field(min_length=1, max_length=20_000)
    existing_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    llm: Optional[LLMRequestOptions] = None


class ProjectSubmissionStatus(BaseModel):
    id: str
    project_version: int
    status: Literal["pending", "published", "rejected", "withdrawn"]
    reviewed_at: Optional[datetime] = None


class ProjectSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    source_scenario_id: Optional[str]
    version: int
    created_at: datetime
    updated_at: datetime
    archived_at: Optional[datetime] = None
    active_share_count: int = 0
    submissions: List[ProjectSubmissionStatus] = Field(default_factory=list)


class ProjectListResponse(BaseModel):
    projects: List[ProjectSummaryResponse]


class ProjectDetailResponse(ProjectSummaryResponse):
    scenario: dict
    af: dict


class ShareLinkCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expires_at: Optional[datetime] = None


class ShareLinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    permission: str
    created_at: datetime
    expires_at: Optional[datetime]
    revoked_at: Optional[datetime]
    last_accessed_at: Optional[datetime]


class ShareLinkCreatedResponse(ShareLinkResponse):
    url: str


class ShareLinkListResponse(BaseModel):
    share_links: List[ShareLinkResponse]


class ShareResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=20, max_length=256)


class SharedProjectResponse(BaseModel):
    id: str
    name: str
    description: str
    source_scenario_id: Optional[str]
    version: int
    scenario: dict
    af: dict


class TrialStatusResponse(BaseModel):
    active: bool
    granted_microusd: int
    spent_microusd: int
    reserved_microusd: int
    available_microusd: int


MCPTokenScope = Literal["projects:read", "projects:write", "llm:use"]


class MCPTokenCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="Codex or Claude Code", min_length=1, max_length=100)
    scopes: List[MCPTokenScope] = Field(
        default_factory=lambda: ["projects:read", "projects:write", "llm:use"],
        min_length=1,
        max_length=3,
    )
    expires_in_days: int = Field(default=90, ge=1, le=365)


class MCPTokenResponse(BaseModel):
    id: str
    name: str
    token_prefix: str
    scopes: List[MCPTokenScope]
    created_at: datetime
    expires_at: datetime
    last_used_at: Optional[datetime]
    revoked_at: Optional[datetime]
    active: bool


class MCPTokenCreatedResponse(MCPTokenResponse):
    token: str = Field(repr=False)
    mcp_url: str
    codex_config: str
    claude_command: str


class MCPTokenListResponse(BaseModel):
    tokens: List[MCPTokenResponse]
