"""Retain keyed introductory-credit eligibility for the program lifetime."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260910_0007"
down_revision = "20260909_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "credit_eligibility_policies",
        sa.Column("key", sa.String(50), primary_key=True),
        sa.Column("key_fingerprint", sa.String(64), nullable=False),
        sa.Column("seeded_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "credit_eligibility_markers",
        sa.Column("digest", sa.String(64), primary_key=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('email', 'identity')", name="ck_credit_marker_kind"),
    )
    op.create_index("ix_credit_eligibility_markers_user_id", "credit_eligibility_markers", ["user_id"])


def downgrade() -> None:
    # Losing any marker would permit a retired introductory allocation again.
    count = op.get_bind().execute(sa.text("SELECT COUNT(*) FROM credit_eligibility_markers")).scalar_one()
    if count:
        raise RuntimeError("cannot remove retained introductory-credit eligibility markers")
    op.drop_table("credit_eligibility_markers")
    op.drop_table("credit_eligibility_policies")
