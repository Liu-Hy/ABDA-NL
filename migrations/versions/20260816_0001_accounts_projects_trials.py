"""Create accounts, projects, share links, and capped trial accounting."""
from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op


revision = "20260816_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("email_verified", sa.Boolean(), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "trial_programs",
        sa.Column("key", sa.String(length=50), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("max_users", sa.Integer(), nullable=False),
        sa.Column("grant_microusd", sa.Integer(), nullable=False),
        sa.Column("budget_microusd", sa.Integer(), nullable=False),
        sa.Column("activation_count", sa.Integer(), nullable=False),
        sa.Column("allocated_microusd", sa.Integer(), nullable=False),
        sa.Column("spent_microusd", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("activation_count >= 0", name="ck_trial_program_activations"),
        sa.CheckConstraint("activation_count <= max_users", name="ck_trial_program_user_cap"),
        sa.CheckConstraint("allocated_microusd >= 0", name="ck_trial_program_allocated"),
        sa.CheckConstraint(
            "allocated_microusd <= budget_microusd", name="ck_trial_program_budget_cap"
        ),
        sa.CheckConstraint("budget_microusd >= 0", name="ck_trial_program_budget"),
        sa.CheckConstraint("grant_microusd >= 0", name="ck_trial_program_grant"),
        sa.CheckConstraint("max_users >= 0", name="ck_trial_program_max_users"),
        sa.CheckConstraint("spent_microusd >= 0", name="ck_trial_program_spent"),
        sa.CheckConstraint(
            "spent_microusd <= allocated_microusd", name="ck_trial_program_spend_cap"
        ),
        sa.PrimaryKeyConstraint("key"),
    )
    op.bulk_insert(
        sa.table(
            "trial_programs",
            sa.column("key", sa.String()),
            sa.column("enabled", sa.Boolean()),
            sa.column("max_users", sa.Integer()),
            sa.column("grant_microusd", sa.Integer()),
            sa.column("budget_microusd", sa.Integer()),
            sa.column("activation_count", sa.Integer()),
            sa.column("allocated_microusd", sa.Integer()),
            sa.column("spent_microusd", sa.Integer()),
            sa.column("updated_at", sa.DateTime(timezone=True)),
        ),
        [
            {
                "key": "global",
                "enabled": True,
                "max_users": 100,
                "grant_microusd": 5_000_000,
                "budget_microusd": 500_000_000,
                "activation_count": 0,
                "allocated_microusd": 0,
                "spent_microusd": 0,
                "updated_at": datetime.now(timezone.utc),
            }
        ],
    )
    op.create_table(
        "identities",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("issuer", sa.String(length=512), nullable=False),
        sa.Column("subject", sa.String(length=512), nullable=False),
        sa.Column("provider_email", sa.String(length=320), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("issuer", "subject", name="uq_identity_issuer_subject"),
    )
    op.create_index(op.f("ix_identities_user_id"), "identities", ["user_id"], unique=False)
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_user_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source_scenario_id", sa.String(length=100), nullable=True),
        sa.Column("scenario_json", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("version >= 1", name="ck_project_positive_version"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_projects_owner_updated", "projects", ["owner_user_id", "updated_at"], unique=False
    )
    op.create_table(
        "trial_grants",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("program_key", sa.String(length=50), nullable=False),
        sa.Column("granted_microusd", sa.Integer(), nullable=False),
        sa.Column("spent_microusd", sa.Integer(), nullable=False),
        sa.Column("reserved_microusd", sa.Integer(), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "spent_microusd + reserved_microusd <= granted_microusd",
            name="ck_trial_grant_balance",
        ),
        sa.CheckConstraint("granted_microusd >= 0", name="ck_trial_grant_amount"),
        sa.CheckConstraint("reserved_microusd >= 0", name="ck_trial_grant_reserved"),
        sa.CheckConstraint("spent_microusd >= 0", name="ck_trial_grant_spent"),
        sa.ForeignKeyConstraint(["program_key"], ["trial_programs.key"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "share_links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("permission", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(op.f("ix_share_links_project_id"), "share_links", ["project_id"], unique=False)
    op.create_table(
        "usage_reservations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("program_key", sa.String(length=50), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("request_kind", sa.String(length=40), nullable=False),
        sa.Column("reserved_microusd", sa.Integer(), nullable=False),
        sa.Column("actual_microusd", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "actual_microusd IS NULL OR actual_microusd >= 0",
            name="ck_usage_reservation_actual",
        ),
        sa.CheckConstraint("reserved_microusd > 0", name="ck_usage_reservation_positive"),
        sa.ForeignKeyConstraint(["program_key"], ["trial_programs.key"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_usage_reservations_user_id"),
        "usage_reservations",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_usage_reservations_user_id"), table_name="usage_reservations")
    op.drop_table("usage_reservations")
    op.drop_index(op.f("ix_share_links_project_id"), table_name="share_links")
    op.drop_table("share_links")
    op.drop_table("trial_grants")
    op.drop_index("ix_projects_owner_updated", table_name="projects")
    op.drop_table("projects")
    op.drop_index(op.f("ix_identities_user_id"), table_name="identities")
    op.drop_table("identities")
    op.drop_table("trial_programs")
    op.drop_table("users")
