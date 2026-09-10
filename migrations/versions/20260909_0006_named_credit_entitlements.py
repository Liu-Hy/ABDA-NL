"""Bind the five named credit allocations to stable account identities."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260909_0006"
down_revision = "20260908_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "named_credit_entitlements",
        sa.Column("email", sa.String(320), primary_key=True),
        sa.Column(
            "user_id", sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"), unique=True,
        ),
        sa.Column("bound_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    # An allocation must never become claimable again after losing its binding.
    connection = op.get_bind()
    bound = connection.execute(sa.text(
        "SELECT COUNT(*) FROM named_credit_entitlements WHERE bound_at IS NOT NULL"
    )).scalar_one()
    if bound:
        raise RuntimeError("cannot remove bound named credit entitlements")
    op.drop_table("named_credit_entitlements")
