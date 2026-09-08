"""Add consented scenario submissions and the reviewed public catalog."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260908_0005"
down_revision = "20260817_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scenario_submissions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "submitter_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="SET NULL")),
        sa.Column("project_version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source_scenario_id", sa.String(100)),
        sa.Column("scenario_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("review_note", sa.String(1000), nullable=False),
        sa.Column("reviewer_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("version >= 1", name="ck_submission_version"),
        sa.CheckConstraint("project_version >= 1", name="ck_submission_project_version"),
        sa.CheckConstraint(
            "status IN ('pending', 'published', 'rejected', 'withdrawn')",
            name="ck_submission_status",
        ),
        sa.UniqueConstraint("project_id", "project_version", name="uq_submission_project_version"),
    )
    op.create_index(
        "ix_submission_owner_created", "scenario_submissions", ["submitter_id", "created_at"]
    )
    op.create_index(
        "ix_submission_status_created", "scenario_submissions", ["status", "created_at"]
    )


def downgrade() -> None:
    op.drop_table("scenario_submissions")
