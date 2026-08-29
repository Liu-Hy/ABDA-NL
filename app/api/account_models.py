"""HTTP models for accounts, durable projects, sharing, and trial credit."""
from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.api.models import (
    MAX_DIFF_OPS,
    ChatMessage,
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


class ProjectWorkingStateRequest(BaseModel):
    """Apply temporary operations to the saved project version."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    diff_ops: List[DiffOp] = Field(default_factory=list, max_length=MAX_DIFF_OPS)


class ProjectChatRequest(ProjectWorkingStateRequest):
    messages: List[ChatMessage] = Field(min_length=1, max_length=50)
    llm: Optional[LLMRequestOptions] = None


class ProjectProposeRequest(ProjectWorkingStateRequest):
    task: Literal["add-rule", "modify-rule", "add-fact", "add-assumption"]
    instruction: str = Field(min_length=1, max_length=20_000)
    existing_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    llm: Optional[LLMRequestOptions] = None


class ProjectSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    source_scenario_id: Optional[str]
    version: int
    created_at: datetime
    updated_at: datetime


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
