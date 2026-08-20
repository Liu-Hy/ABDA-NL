"""Relational persistence model for accounts, projects, sharing, and trial credit."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


def usage_reservation_expiry() -> datetime:
    return utc_now() + timedelta(minutes=15)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    identities: Mapped[List[Identity]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    projects: Mapped[List[Project]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
    mcp_access_tokens: Mapped[List[MCPAccessToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Identity(Base):
    __tablename__ = "identities"
    __table_args__ = (UniqueConstraint("issuer", "subject", name="uq_identity_issuer_subject"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    issuer: Mapped[str] = mapped_column(String(512), nullable=False)
    subject: Mapped[str] = mapped_column(String(512), nullable=False)
    provider_email: Mapped[Optional[str]] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    last_login_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    user: Mapped[User] = relationship(back_populates="identities")


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_project_positive_version"),
        Index("ix_projects_owner_updated", "owner_user_id", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_scenario_id: Mapped[Optional[str]] = mapped_column(String(100))
    scenario_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    owner: Mapped[User] = relationship(back_populates="projects")
    share_links: Mapped[List[ShareLink]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class ShareLink(Base):
    __tablename__ = "share_links"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    permission: Mapped[str] = mapped_column(String(20), nullable=False, default="view")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_accessed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    project: Mapped[Project] = relationship(back_populates="share_links")


class MCPAccessToken(Base):
    __tablename__ = "mcp_access_tokens"
    __table_args__ = (
        Index("ix_mcp_tokens_user_created", "user_id", "created_at"),
        Index(
            "ix_mcp_tokens_user_active",
            "user_id",
            "revoked_at",
            "expires_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    token_prefix: Mapped[str] = mapped_column(String(24), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    scopes: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="mcp_access_tokens")


class RateLimitBucket(Base):
    """Privacy-preserving fixed-window counters shared by all web replicas."""

    __tablename__ = "rate_limit_buckets"
    __table_args__ = (
        CheckConstraint("request_count >= 1", name="ck_rate_limit_positive_count"),
        Index("ix_rate_limit_expiry", "expires_at"),
    )

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    scope: Mapped[str] = mapped_column(String(40), nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    window_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TrialProgram(Base):
    __tablename__ = "trial_programs"
    __table_args__ = (
        CheckConstraint("max_users >= 0", name="ck_trial_program_max_users"),
        CheckConstraint("grant_microusd >= 0", name="ck_trial_program_grant"),
        CheckConstraint("budget_microusd >= 0", name="ck_trial_program_budget"),
        CheckConstraint("activation_count >= 0", name="ck_trial_program_activations"),
        CheckConstraint("activation_count <= max_users", name="ck_trial_program_user_cap"),
        CheckConstraint("allocated_microusd >= 0", name="ck_trial_program_allocated"),
        CheckConstraint(
            "allocated_microusd <= budget_microusd", name="ck_trial_program_budget_cap"
        ),
        CheckConstraint("spent_microusd >= 0", name="ck_trial_program_spent"),
        CheckConstraint("spent_microusd <= allocated_microusd", name="ck_trial_program_spend_cap"),
    )

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    max_users: Mapped[int] = mapped_column(Integer, nullable=False)
    grant_microusd: Mapped[int] = mapped_column(Integer, nullable=False)
    budget_microusd: Mapped[int] = mapped_column(Integer, nullable=False)
    activation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    allocated_microusd: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    spent_microusd: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class TrialGrant(Base):
    __tablename__ = "trial_grants"
    __table_args__ = (
        CheckConstraint("granted_microusd >= 0", name="ck_trial_grant_amount"),
        CheckConstraint("spent_microusd >= 0", name="ck_trial_grant_spent"),
        CheckConstraint("reserved_microusd >= 0", name="ck_trial_grant_reserved"),
        CheckConstraint(
            "spent_microusd + reserved_microusd <= granted_microusd",
            name="ck_trial_grant_balance",
        ),
    )

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    program_key: Mapped[str] = mapped_column(
        ForeignKey("trial_programs.key"), nullable=False, default="global"
    )
    granted_microusd: Mapped[int] = mapped_column(Integer, nullable=False)
    spent_microusd: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reserved_microusd: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class UsageReservation(Base):
    __tablename__ = "usage_reservations"
    __table_args__ = (
        CheckConstraint("reserved_microusd > 0", name="ck_usage_reservation_positive"),
        CheckConstraint(
            "actual_microusd IS NULL OR actual_microusd >= 0",
            name="ck_usage_reservation_actual",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    program_key: Mapped[str] = mapped_column(
        ForeignKey("trial_programs.key"), nullable=False, default="global"
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    request_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    reserved_microusd: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_microusd: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=usage_reservation_expiry
    )
    finalized_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class EmergencyBudget(Base):
    __tablename__ = "emergency_budgets"
    __table_args__ = (
        CheckConstraint("hard_limit_microusd >= 0", name="ck_emergency_budget_limit"),
        CheckConstraint("spent_microusd >= 0", name="ck_emergency_budget_spent"),
        CheckConstraint("reserved_microusd >= 0", name="ck_emergency_budget_reserved"),
        CheckConstraint(
            "spent_microusd + reserved_microusd <= hard_limit_microusd",
            name="ck_emergency_budget_balance",
        ),
    )

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hard_limit_microusd: Mapped[int] = mapped_column(Integer, nullable=False)
    spent_microusd: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reserved_microusd: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class EmergencyUsageReservation(Base):
    __tablename__ = "emergency_usage_reservations"
    __table_args__ = (
        CheckConstraint(
            "reserved_microusd > 0", name="ck_emergency_reservation_positive"
        ),
        CheckConstraint(
            "actual_microusd IS NULL OR actual_microusd >= 0",
            name="ck_emergency_reservation_actual",
        ),
        Index("ix_emergency_reservations_status_expiry", "status", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    budget_key: Mapped[str] = mapped_column(
        ForeignKey("emergency_budgets.key"), nullable=False, default="openrouter"
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    route: Mapped[str] = mapped_column(String(120), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    request_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    reserved_microusd: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_microusd: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=usage_reservation_expiry
    )
    finalized_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class LLMUsageEvent(Base):
    __tablename__ = "llm_usage_events"
    __table_args__ = (
        CheckConstraint("cost_microusd >= 0", name="ck_llm_usage_cost"),
        Index("ix_llm_usage_created", "created_at"),
        Index("ix_llm_usage_user_created", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    request_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    route: Mapped[str] = mapped_column(String(120), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    billing_source: Mapped[str] = mapped_column(String(40), nullable=False)
    request_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    input_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cache_read_input_tokens: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    cache_creation_input_tokens: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    cost_microusd: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_type: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
