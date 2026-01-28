"""Add skill workflow tables

Revision ID: 20260120_0002
Revises: 001
Create Date: 2026-01-20 20:20:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260120_0002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create skills table
    op.create_table(
        "skills",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("agent_name", sa.String(length=255), nullable=True),
        sa.Column("current_version", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="development"),
        sa.Column("git_path", sa.String(length=512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # Create skill_versions table
    op.create_table(
        "skill_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("skill_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("git_sha", sa.String(length=40), nullable=True),
        sa.Column("git_path", sa.String(length=512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("changelog", sa.Text(), nullable=True),
        sa.Column(
            "metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"
        ),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("skill_id", "version", name="uq_skill_version"),
    )

    # Create skill_evaluations table
    op.create_table(
        "skill_evaluations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("skill_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=True),
        sa.Column(
            "evaluated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("evaluated_by", sa.String(length=255), nullable=True),
        sa.Column("sandbox_type", sa.String(length=50), nullable=False),
        sa.Column("accuracy", sa.Float(), nullable=False),
        sa.Column("avg_latency_ms", sa.Float(), nullable=False),
        sa.Column("tests_total", sa.Integer(), nullable=False),
        sa.Column("tests_passed", sa.Integer(), nullable=False),
        sa.Column("tests_failed", sa.Integer(), nullable=False),
        sa.Column("total_duration_ms", sa.Float(), nullable=False),
        sa.Column("test_results", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"
        ),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create skill_sync_status table
    op.create_table(
        "skill_sync_status",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("skill_name", sa.String(length=255), nullable=False),
        sa.Column(
            "last_sync_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("sync_direction", sa.String(length=50), nullable=False),
        sa.Column("git_sha", sa.String(length=40), nullable=True),
        sa.Column("pr_number", sa.Integer(), nullable=True),
        sa.Column("pr_status", sa.String(length=50), nullable=True),
        sa.Column("sync_status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("skill_name"),
    )

    # Create indexes
    op.create_index("ix_skills_category", "skills", ["category"])
    op.create_index("ix_skills_status", "skills", ["status"])
    op.create_index("ix_skill_evaluations_skill_id", "skill_evaluations", ["skill_id"])
    op.create_index("ix_skill_evaluations_evaluated_at", "skill_evaluations", ["evaluated_at"])


def downgrade() -> None:
    op.drop_index("ix_skill_evaluations_evaluated_at")
    op.drop_index("ix_skill_evaluations_skill_id")
    op.drop_index("ix_skills_status")
    op.drop_index("ix_skills_category")
    op.drop_table("skill_sync_status")
    op.drop_table("skill_evaluations")
    op.drop_table("skill_versions")
    op.drop_table("skills")
