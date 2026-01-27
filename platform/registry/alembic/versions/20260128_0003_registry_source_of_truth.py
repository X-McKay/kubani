"""Registry as source of truth - add OCI support and versioning

Revision ID: 20260128_0003
Revises: 20260120_0002
Create Date: 2026-01-28 00:00:00.000000

This migration adds:
- syndicates and syndicate_versions tables for multi-agent orchestration
- agent_versions table for versioned agent definitions
- OCI columns to skills, skill_versions, and agents for registry-first architecture
- Additional skill metadata fields (confidence, success/failure counts, etc.)
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260128_0003"
down_revision = "20260120_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =========================================================================
    # 1. Create syndicates table
    # =========================================================================
    op.create_table(
        "syndicates",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("current_version", sa.String(50), nullable=True),
        sa.Column("oci_repository", sa.String(512), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("created_by", sa.String(255), nullable=True),
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
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.create_index("ix_syndicates_status", "syndicates", ["status"])

    # =========================================================================
    # 2. Create syndicate_versions table
    # =========================================================================
    op.create_table(
        "syndicate_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "syndicate_id",
            sa.String(255),
            sa.ForeignKey("syndicates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("oci_tag", sa.String(100), nullable=True),
        sa.Column("oci_digest", sa.String(128), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column(
            "agent_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("changelog", sa.Text(), nullable=True),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("promoted_by", sa.String(255), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.UniqueConstraint("syndicate_id", "version", name="uq_syndicate_version"),
    )
    op.create_index("ix_syndicate_versions_status", "syndicate_versions", ["status"])

    # =========================================================================
    # 3. Create agent_versions table
    # =========================================================================
    op.create_table(
        "agent_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "agent_id",
            sa.String(255),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("oci_tag", sa.String(100), nullable=True),
        sa.Column("oci_digest", sa.String(128), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("changelog", sa.Text(), nullable=True),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("promoted_by", sa.String(255), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.UniqueConstraint("agent_id", "version", name="uq_agent_version"),
    )
    op.create_index("ix_agent_versions_status", "agent_versions", ["status"])

    # =========================================================================
    # 4. Add OCI columns to agents table
    # =========================================================================
    op.add_column("agents", sa.Column("current_version", sa.String(50), nullable=True))
    op.add_column("agents", sa.Column("oci_repository", sa.String(512), nullable=True))
    op.add_column("agents", sa.Column("created_by", sa.String(255), nullable=True))

    # =========================================================================
    # 5. Add OCI and metadata columns to skills table
    # =========================================================================
    op.add_column("skills", sa.Column("oci_repository", sa.String(512), nullable=True))
    op.add_column("skills", sa.Column("domain", sa.String(100), nullable=True))
    op.add_column(
        "skills", sa.Column("confidence", sa.Float(), server_default="0.5", nullable=True)
    )
    op.add_column(
        "skills", sa.Column("success_count", sa.Integer(), server_default="0", nullable=True)
    )
    op.add_column(
        "skills", sa.Column("failure_count", sa.Integer(), server_default="0", nullable=True)
    )
    op.add_column(
        "skills",
        sa.Column("requires_approval", sa.Boolean(), server_default="false", nullable=True),
    )
    op.add_column("skills", sa.Column("last_used", sa.DateTime(timezone=True), nullable=True))
    op.add_column("skills", sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True))

    # =========================================================================
    # 6. Add OCI and status columns to skill_versions table
    # =========================================================================
    op.add_column("skill_versions", sa.Column("oci_tag", sa.String(100), nullable=True))
    op.add_column("skill_versions", sa.Column("oci_digest", sa.String(128), nullable=True))
    op.add_column(
        "skill_versions",
        sa.Column("status", sa.String(50), server_default="draft", nullable=True),
    )
    op.add_column(
        "skill_versions", sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("skill_versions", sa.Column("promoted_by", sa.String(255), nullable=True))
    op.create_index("ix_skill_versions_status", "skill_versions", ["status"])


def downgrade() -> None:
    # =========================================================================
    # 6. Remove OCI and status columns from skill_versions table
    # =========================================================================
    op.drop_index("ix_skill_versions_status", table_name="skill_versions")
    op.drop_column("skill_versions", "promoted_by")
    op.drop_column("skill_versions", "promoted_at")
    op.drop_column("skill_versions", "status")
    op.drop_column("skill_versions", "oci_digest")
    op.drop_column("skill_versions", "oci_tag")

    # =========================================================================
    # 5. Remove OCI and metadata columns from skills table
    # =========================================================================
    op.drop_column("skills", "validated_at")
    op.drop_column("skills", "last_used")
    op.drop_column("skills", "requires_approval")
    op.drop_column("skills", "failure_count")
    op.drop_column("skills", "success_count")
    op.drop_column("skills", "confidence")
    op.drop_column("skills", "domain")
    op.drop_column("skills", "oci_repository")

    # =========================================================================
    # 4. Remove OCI columns from agents table
    # =========================================================================
    op.drop_column("agents", "created_by")
    op.drop_column("agents", "oci_repository")
    op.drop_column("agents", "current_version")

    # =========================================================================
    # 3. Drop agent_versions table
    # =========================================================================
    op.drop_index("ix_agent_versions_status", table_name="agent_versions")
    op.drop_table("agent_versions")

    # =========================================================================
    # 2. Drop syndicate_versions table
    # =========================================================================
    op.drop_index("ix_syndicate_versions_status", table_name="syndicate_versions")
    op.drop_table("syndicate_versions")

    # =========================================================================
    # 1. Drop syndicates table
    # =========================================================================
    op.drop_index("ix_syndicates_status", table_name="syndicates")
    op.drop_table("syndicates")
