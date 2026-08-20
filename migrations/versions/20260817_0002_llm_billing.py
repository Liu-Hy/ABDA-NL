"""Add emergency budget reservations and provider usage events."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from alembic import op


revision = "20260817_0002"
down_revision = "20260816_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "usage_reservations",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    usage_reservations = sa.table(
        "usage_reservations",
        sa.column("expires_at", sa.DateTime(timezone=True)),
    )
    op.execute(
        usage_reservations.update().values(
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15)
        )
    )
    with op.batch_alter_table("usage_reservations") as batch:
        batch.alter_column("expires_at", existing_type=sa.DateTime(timezone=True), nullable=False)

    op.create_table(
        "emergency_budgets",
        sa.Column("key", sa.String(length=50), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("hard_limit_microusd", sa.Integer(), nullable=False),
        sa.Column("spent_microusd", sa.Integer(), nullable=False),
        sa.Column("reserved_microusd", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "spent_microusd + reserved_microusd <= hard_limit_microusd",
            name="ck_emergency_budget_balance",
        ),
        sa.CheckConstraint(
            "hard_limit_microusd >= 0", name="ck_emergency_budget_limit"
        ),
        sa.CheckConstraint(
            "reserved_microusd >= 0", name="ck_emergency_budget_reserved"
        ),
        sa.CheckConstraint("spent_microusd >= 0", name="ck_emergency_budget_spent"),
        sa.PrimaryKeyConstraint("key"),
    )
    op.bulk_insert(
        sa.table(
            "emergency_budgets",
            sa.column("key", sa.String()),
            sa.column("enabled", sa.Boolean()),
            sa.column("hard_limit_microusd", sa.Integer()),
            sa.column("spent_microusd", sa.Integer()),
            sa.column("reserved_microusd", sa.Integer()),
            sa.column("updated_at", sa.DateTime(timezone=True)),
        ),
        [
            {
                "key": "openrouter",
                "enabled": False,
                "hard_limit_microusd": 500_000_000,
                "spent_microusd": 0,
                "reserved_microusd": 0,
                "updated_at": datetime.now(timezone.utc),
            }
        ],
    )
    op.create_table(
        "emergency_usage_reservations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("budget_key", sa.String(length=50), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("route", sa.String(length=120), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("request_kind", sa.String(length=40), nullable=False),
        sa.Column("reserved_microusd", sa.Integer(), nullable=False),
        sa.Column("actual_microusd", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "actual_microusd IS NULL OR actual_microusd >= 0",
            name="ck_emergency_reservation_actual",
        ),
        sa.CheckConstraint(
            "reserved_microusd > 0", name="ck_emergency_reservation_positive"
        ),
        sa.ForeignKeyConstraint(["budget_key"], ["emergency_budgets.key"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_emergency_reservations_status_expiry",
        "emergency_usage_reservations",
        ["status", "expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_emergency_usage_reservations_user_id"),
        "emergency_usage_reservations",
        ["user_id"],
        unique=False,
    )
    op.create_table(
        "llm_usage_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("request_id", sa.String(length=100), nullable=True),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("route", sa.String(length=120), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("billing_source", sa.String(length=40), nullable=False),
        sa.Column("request_kind", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("input_tokens", sa.BigInteger(), nullable=False),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False),
        sa.Column("cache_read_input_tokens", sa.BigInteger(), nullable=False),
        sa.Column("cache_creation_input_tokens", sa.BigInteger(), nullable=False),
        sa.Column("cost_microusd", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("error_type", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("cost_microusd >= 0", name="ck_llm_usage_cost"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_llm_usage_created", "llm_usage_events", ["created_at"], unique=False)
    op.create_index(
        op.f("ix_llm_usage_events_request_id"),
        "llm_usage_events",
        ["request_id"],
        unique=False,
    )
    op.create_index(
        "ix_llm_usage_user_created",
        "llm_usage_events",
        ["user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_llm_usage_user_created", table_name="llm_usage_events")
    op.drop_index(op.f("ix_llm_usage_events_request_id"), table_name="llm_usage_events")
    op.drop_index("ix_llm_usage_created", table_name="llm_usage_events")
    op.drop_table("llm_usage_events")
    op.drop_index(
        op.f("ix_emergency_usage_reservations_user_id"),
        table_name="emergency_usage_reservations",
    )
    op.drop_index(
        "ix_emergency_reservations_status_expiry",
        table_name="emergency_usage_reservations",
    )
    op.drop_table("emergency_usage_reservations")
    op.drop_table("emergency_budgets")
    with op.batch_alter_table("usage_reservations") as batch:
        batch.drop_column("expires_at")
