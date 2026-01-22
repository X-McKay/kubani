"""Initial schema for Kubani Registry.

Revision ID: 001
Revises:
Create Date: 2026-01-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Agents table
    op.create_table(
        "agents",
        sa.Column("id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("version", sa.String(50), nullable=True),
        sa.Column("endpoint", sa.String(512), nullable=True),
        sa.Column("task_queue", sa.String(255), nullable=True),
        sa.Column("status", sa.String(50), server_default="unknown", nullable=False),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_agents_status", "agents", ["status"])
    op.create_index("idx_agents_heartbeat", "agents", ["last_heartbeat"])

    # Agent capabilities table
    op.create_table(
        "agent_capabilities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("agent_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("input_schema", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("output_schema", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.String(100)), server_default="{}", nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_id", "name", name="uq_agent_capability"),
    )
    op.create_index("idx_capabilities_name", "agent_capabilities", ["name"])
    op.create_index("idx_capabilities_tags", "agent_capabilities", ["tags"], postgresql_using="gin")

    # MCP servers table
    op.create_table(
        "mcp_servers",
        sa.Column("id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("transport", sa.String(50), nullable=False),
        sa.Column("connection_config", postgresql.JSONB(), nullable=False),
        sa.Column(
            "capabilities", postgresql.ARRAY(sa.String(255)), server_default="{}", nullable=False
        ),
        sa.Column("namespaces", postgresql.ARRAY(sa.String(255)), nullable=True),
        sa.Column("read_only", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("status", sa.String(50), server_default="active", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # MCP policies table
    op.create_table(
        "mcp_policies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("agent_pattern", sa.String(255), nullable=False),
        sa.Column("server_id", sa.String(255), nullable=False),
        sa.Column("allowed_tools", postgresql.ARRAY(sa.String(255)), nullable=True),
        sa.Column(
            "require_approval",
            postgresql.ARRAY(sa.String(255)),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("namespace_restrictions", postgresql.JSONB(), nullable=True),
        sa.Column("priority", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["server_id"], ["mcp_servers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_mcp_policies_pattern", "mcp_policies", ["agent_pattern"])

    # Skill metadata table
    op.create_table(
        "skill_metadata",
        sa.Column("id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("domain", sa.String(50), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), server_default="proposed", nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0.5", nullable=False),
        sa.Column("success_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failure_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("requires_approval", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_skills_domain", "skill_metadata", ["domain"])
    op.create_index("idx_skills_status", "skill_metadata", ["status"])
    op.create_index("idx_skills_confidence", "skill_metadata", ["confidence"])

    # Deployments table
    op.create_table(
        "deployments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("agent_id", sa.String(255), nullable=False),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("image_tag", sa.String(255), nullable=True),
        sa.Column("git_sha", sa.String(40), nullable=True),
        sa.Column(
            "deployed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("deployed_by", sa.String(100), nullable=True),
        sa.Column("config_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(50), server_default="active", nullable=False),
        sa.Column("rollback_from", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["rollback_from"], ["deployments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_deployments_agent",
        "deployments",
        ["agent_id", "deployed_at"],
        postgresql_ops={"deployed_at": "DESC"},
    )

    # Models table
    op.create_table(
        "models",
        sa.Column("id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("model_type", sa.String(50), nullable=False),
        sa.Column("provider", sa.String(100), nullable=True),
        sa.Column("quantization", sa.String(50), nullable=True),
        sa.Column("context_length", sa.Integer(), nullable=True),
        sa.Column("vram_required_gb", sa.Float(), nullable=True),
        sa.Column("capabilities", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("local_path", sa.String(512), nullable=True),
        sa.Column("status", sa.String(50), server_default="available", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("metadata", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_models_type", "models", ["model_type"])
    op.create_index("idx_models_status", "models", ["status"])

    # Endpoints table
    op.create_table(
        "endpoints",
        sa.Column("id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("service_type", sa.String(100), nullable=False),
        sa.Column("internal_url", sa.String(512), nullable=True),
        sa.Column("external_url", sa.String(512), nullable=True),
        sa.Column("health_check_path", sa.String(255), server_default="/health", nullable=False),
        sa.Column("status", sa.String(50), server_default="unknown", nullable=False),
        sa.Column("last_health_check", sa.DateTime(timezone=True), nullable=True),
        sa.Column("namespace", sa.String(255), nullable=True),
        sa.Column("environment", sa.String(50), server_default="production", nullable=False),
        sa.Column("metadata", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_endpoints_type", "endpoints", ["service_type"])
    op.create_index("idx_endpoints_status", "endpoints", ["status"])

    # Model endpoints association table
    op.create_table(
        "model_endpoints",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("model_id", sa.String(255), nullable=False),
        sa.Column("endpoint_id", sa.String(255), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["model_id"], ["models.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["endpoint_id"], ["endpoints.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_id", "endpoint_id", name="uq_model_endpoint"),
    )

    # Endpoint dependencies table
    op.create_table(
        "endpoint_dependencies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dependent_id", sa.String(255), nullable=False),
        sa.Column("dependent_type", sa.String(50), nullable=False),
        sa.Column("endpoint_id", sa.String(255), nullable=False),
        sa.Column("is_required", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["endpoint_id"], ["endpoints.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dependent_id", "dependent_type", "endpoint_id", name="uq_endpoint_dependency"
        ),
    )


def downgrade() -> None:
    op.drop_table("endpoint_dependencies")
    op.drop_table("model_endpoints")
    op.drop_table("endpoints")
    op.drop_table("models")
    op.drop_table("deployments")
    op.drop_table("skill_metadata")
    op.drop_table("mcp_policies")
    op.drop_table("mcp_servers")
    op.drop_table("agent_capabilities")
    op.drop_table("agents")
