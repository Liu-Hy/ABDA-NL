"""Add explicit snapshot metadata without exposing existing account names."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260910_0008"
down_revision = "20260910_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scenario_submissions", sa.Column("public_summary", sa.String(400), nullable=False, server_default=""))
    op.add_column("scenario_submissions", sa.Column("author_note", sa.String(1000), nullable=False, server_default=""))
    # A missing value means no opt-in. Never backfill from the account profile.
    op.add_column("scenario_submissions", sa.Column("attribution_name", sa.String(200), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("scenario_submissions") as batch:
        batch.drop_column("attribution_name")
        batch.drop_column("author_note")
        batch.drop_column("public_summary")
