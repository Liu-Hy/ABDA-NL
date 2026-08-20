"""Add scoped and revocable MCP access tokens."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260817_0003"
down_revision = "20260817_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_access_tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("token_prefix", sa.String(length=24), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("scopes", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_mcp_tokens_user_active",
        "mcp_access_tokens",
        ["user_id", "revoked_at", "expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_mcp_tokens_user_created",
        "mcp_access_tokens",
        ["user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_mcp_tokens_user_created", table_name="mcp_access_tokens")
    op.drop_index("ix_mcp_tokens_user_active", table_name="mcp_access_tokens")
    op.drop_table("mcp_access_tokens")
