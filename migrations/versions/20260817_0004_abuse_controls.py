"""Add shared privacy-preserving rate-limit counters."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260817_0004"
down_revision = "20260817_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rate_limit_buckets",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("scope", sa.String(length=40), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "request_count >= 1", name="ck_rate_limit_positive_count"
        ),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_index(
        "ix_rate_limit_expiry",
        "rate_limit_buckets",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_rate_limit_expiry", table_name="rate_limit_buckets")
    op.drop_table("rate_limit_buckets")
