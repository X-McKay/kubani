"""SQLAlchemy ORM models for the Kubani Registry."""

from datetime import datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class Agent(Base):
    """Registered agent in the Kubani ecosystem."""

    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    version: Mapped[str | None] = mapped_column(String(50))
    endpoint: Mapped[str | None] = mapped_column(String(512))
    task_queue: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50), default="unknown")
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # OCI registry fields
    current_version: Mapped[str | None] = mapped_column(String(50))
    oci_repository: Mapped[str | None] = mapped_column(String(512))
    created_by: Mapped[str | None] = mapped_column(String(255))

    # Relationships
    capabilities: Mapped[list["AgentCapability"]] = relationship(
        back_populates="agent", cascade="all, delete-orphan"
    )
    versions: Mapped[list["AgentVersion"]] = relationship(
        back_populates="agent", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        """Convert to dictionary with metadata field."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "endpoint": self.endpoint,
            "task_queue": self.task_queue,
            "status": self.status,
            "last_heartbeat": self.last_heartbeat,
            "metadata": self.metadata_ or {},
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "current_version": self.current_version,
            "oci_repository": self.oci_repository,
            "created_by": self.created_by,
            "capabilities": [
                {
                    "name": c.name,
                    "description": c.description,
                    "input_schema": c.input_schema,
                    "output_schema": c.output_schema,
                    "tags": c.tags or [],
                }
                for c in self.capabilities
            ],
        }


class AgentCapability(Base):
    """Capability provided by an agent."""

    __tablename__ = "agent_capabilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    input_schema: Mapped[dict] = mapped_column(JSONB, default=dict)
    output_schema: Mapped[dict] = mapped_column(JSONB, default=dict)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(100)), default=list)

    # Relationships
    agent: Mapped["Agent"] = relationship(back_populates="capabilities")

    __table_args__ = (UniqueConstraint("agent_id", "name", name="uq_agent_capability"),)


class MCPServer(Base):
    """Registered MCP server."""

    __tablename__ = "mcp_servers"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    transport: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # stdio, sse, streamable-http
    connection_config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    capabilities: Mapped[list[str]] = mapped_column(ARRAY(String(255)), default=list)
    namespaces: Mapped[list[str] | None] = mapped_column(ARRAY(String(255)))
    read_only: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(50), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    policies: Mapped[list["MCPPolicy"]] = relationship(
        back_populates="server", cascade="all, delete-orphan"
    )


class MCPPolicy(Base):
    """Policy governing agent access to MCP servers."""

    __tablename__ = "mcp_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_pattern: Mapped[str] = mapped_column(String(255), nullable=False)  # glob pattern
    server_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("mcp_servers.id", ondelete="CASCADE"), nullable=False
    )
    allowed_tools: Mapped[list[str] | None] = mapped_column(ARRAY(String(255)))
    require_approval: Mapped[list[str]] = mapped_column(ARRAY(String(255)), default=list)
    namespace_restrictions: Mapped[dict | None] = mapped_column(JSONB)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    server: Mapped["MCPServer"] = relationship(back_populates="policies")


class SkillMetadata(Base):
    """Metadata for skills stored in Qdrant."""

    __tablename__ = "skill_metadata"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="proposed")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Deployment(Base):
    """Deployment history for agents."""

    __tablename__ = "deployments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    image_tag: Mapped[str | None] = mapped_column(String(255))
    git_sha: Mapped[str | None] = mapped_column(String(40))
    deployed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    deployed_by: Mapped[str | None] = mapped_column(String(100))
    config_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(50), default="active")
    rollback_from: Mapped[int | None] = mapped_column(Integer, ForeignKey("deployments.id"))


class Model(Base):
    """LLM model in the registry."""

    __tablename__ = "models"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # general, coding, embeddings, vision
    provider: Mapped[str | None] = mapped_column(String(100))
    quantization: Mapped[str | None] = mapped_column(String(50))
    context_length: Mapped[int | None] = mapped_column(Integer)
    vram_required_gb: Mapped[float | None] = mapped_column(Float)
    capabilities: Mapped[dict] = mapped_column(JSONB, default=dict)
    local_path: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(50), default="available")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)

    # Relationships
    model_endpoints: Mapped[list["ModelEndpoint"]] = relationship(
        back_populates="model", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        """Convert to dictionary with metadata field."""
        return {
            "id": self.id,
            "name": self.name,
            "model_type": self.model_type,
            "provider": self.provider,
            "quantization": self.quantization,
            "context_length": self.context_length,
            "vram_required_gb": self.vram_required_gb,
            "capabilities": self.capabilities,
            "local_path": self.local_path,
            "status": self.status,
            "created_at": self.created_at,
            "metadata": self.metadata_ or {},
        }


class Endpoint(Base):
    """Service endpoint in the cluster."""

    __tablename__ = "endpoints"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    service_type: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # llm, embeddings, mcp, temporal
    internal_url: Mapped[str | None] = mapped_column(String(512))
    external_url: Mapped[str | None] = mapped_column(String(512))
    health_check_path: Mapped[str] = mapped_column(String(255), default="/health")
    status: Mapped[str] = mapped_column(String(50), default="unknown")
    last_health_check: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    namespace: Mapped[str | None] = mapped_column(String(255))
    environment: Mapped[str] = mapped_column(String(50), default="production")
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    model_endpoints: Mapped[list["ModelEndpoint"]] = relationship(
        back_populates="endpoint", cascade="all, delete-orphan"
    )
    dependencies: Mapped[list["EndpointDependency"]] = relationship(
        back_populates="endpoint", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        """Convert to dictionary with metadata field."""
        return {
            "id": self.id,
            "name": self.name,
            "service_type": self.service_type,
            "internal_url": self.internal_url,
            "external_url": self.external_url,
            "health_check_path": self.health_check_path,
            "status": self.status,
            "last_health_check": self.last_health_check,
            "namespace": self.namespace,
            "environment": self.environment,
            "metadata": self.metadata_ or {},
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class ModelEndpoint(Base):
    """Association between models and endpoints."""

    __tablename__ = "model_endpoints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("models.id", ondelete="CASCADE"), nullable=False
    )
    endpoint_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("endpoints.id", ondelete="CASCADE"), nullable=False
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    model: Mapped["Model"] = relationship(back_populates="model_endpoints")
    endpoint: Mapped["Endpoint"] = relationship(back_populates="model_endpoints")

    __table_args__ = (UniqueConstraint("model_id", "endpoint_id", name="uq_model_endpoint"),)


class EndpointDependency(Base):
    """Dependency relationship between agents/services and endpoints."""

    __tablename__ = "endpoint_dependencies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dependent_id: Mapped[str] = mapped_column(String(255), nullable=False)
    dependent_type: Mapped[str] = mapped_column(String(50), nullable=False)  # agent, service
    endpoint_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("endpoints.id", ondelete="CASCADE"), nullable=False
    )
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    endpoint: Mapped["Endpoint"] = relationship(back_populates="dependencies")

    __table_args__ = (
        UniqueConstraint(
            "dependent_id", "dependent_type", "endpoint_id", name="uq_endpoint_dependency"
        ),
    )


class Skill(Base):
    """Skill in the development workflow."""

    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(100), nullable=False)  # core, agent-specific
    agent_name: Mapped[str | None] = mapped_column(String(255))  # For agent-specific skills
    current_version: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(
        String(50), default="development"
    )  # development, production, deprecated
    git_path: Mapped[str | None] = mapped_column(String(512))  # Path in Git repository
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    # OCI registry fields
    oci_repository: Mapped[str | None] = mapped_column(String(512))
    # Skill metadata fields
    domain: Mapped[str | None] = mapped_column(String(100))
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    last_used: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    versions: Mapped[list["SkillVersion"]] = relationship(
        back_populates="skill", cascade="all, delete-orphan"
    )
    evaluations: Mapped[list["SkillEvaluation"]] = relationship(
        back_populates="skill", cascade="all, delete-orphan"
    )


class SkillVersion(Base):
    """Version of a skill."""

    __tablename__ = "skill_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    skill_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    git_sha: Mapped[str | None] = mapped_column(String(40))
    git_path: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(255))  # agent or user
    changelog: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    # OCI registry fields
    oci_tag: Mapped[str | None] = mapped_column(String(100))
    oci_digest: Mapped[str | None] = mapped_column(String(128))
    # Version lifecycle
    status: Mapped[str] = mapped_column(String(50), default="draft")
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    promoted_by: Mapped[str | None] = mapped_column(String(255))

    # Relationships
    skill: Mapped["Skill"] = relationship(back_populates="versions")

    __table_args__ = (UniqueConstraint("skill_id", "version", name="uq_skill_version"),)


class SkillEvaluation(Base):
    """Evaluation result for a skill."""

    __tablename__ = "skill_evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    skill_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[str | None] = mapped_column(String(50))  # Null for development
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    evaluated_by: Mapped[str | None] = mapped_column(String(255))  # agent or user
    sandbox_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # microsandbox, docker, cluster
    accuracy: Mapped[float] = mapped_column(Float, nullable=False)
    avg_latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    tests_total: Mapped[int] = mapped_column(Integer, nullable=False)
    tests_passed: Mapped[int] = mapped_column(Integer, nullable=False)
    tests_failed: Mapped[int] = mapped_column(Integer, nullable=False)
    total_duration_ms: Mapped[float] = mapped_column(Float, nullable=False)
    test_results: Mapped[dict] = mapped_column(JSONB, nullable=False)  # Full test results
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)

    # Relationships
    skill: Mapped["Skill"] = relationship(back_populates="evaluations")


class SkillSyncStatus(Base):
    """Tracks synchronization status between cluster and Git."""

    __tablename__ = "skill_sync_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    skill_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    last_sync_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    sync_direction: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # cluster_to_git, git_to_cluster
    git_sha: Mapped[str | None] = mapped_column(String(40))
    pr_number: Mapped[int | None] = mapped_column(Integer)
    pr_status: Mapped[str | None] = mapped_column(String(50))  # open, merged, closed
    sync_status: Mapped[str] = mapped_column(
        String(50), default="pending"
    )  # pending, in_progress, completed, failed
    error_message: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)


class Syndicate(Base):
    """Syndicate (multi-agent orchestration) definition."""

    __tablename__ = "syndicates"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    current_version: Mapped[str | None] = mapped_column(String(50))
    oci_repository: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(50), default="draft")
    created_by: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)

    # Relationships
    versions: Mapped[list["SyndicateVersion"]] = relationship(
        back_populates="syndicate", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "current_version": self.current_version,
            "oci_repository": self.oci_repository,
            "status": self.status,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata_ or {},
        }


class SyndicateVersion(Base):
    """Version of a syndicate."""

    __tablename__ = "syndicate_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    syndicate_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("syndicates.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    oci_tag: Mapped[str | None] = mapped_column(String(100))
    oci_digest: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(50), default="draft")
    agent_refs: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(255))
    changelog: Mapped[str | None] = mapped_column(Text)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    promoted_by: Mapped[str | None] = mapped_column(String(255))
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)

    # Relationships
    syndicate: Mapped["Syndicate"] = relationship(back_populates="versions")

    __table_args__ = (UniqueConstraint("syndicate_id", "version", name="uq_syndicate_version"),)


class AgentVersion(Base):
    """Version of an agent definition."""

    __tablename__ = "agent_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    oci_tag: Mapped[str | None] = mapped_column(String(100))
    oci_digest: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(50), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(255))
    changelog: Mapped[str | None] = mapped_column(Text)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    promoted_by: Mapped[str | None] = mapped_column(String(255))
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)

    # Relationships
    agent: Mapped["Agent"] = relationship(back_populates="versions")

    __table_args__ = (UniqueConstraint("agent_id", "version", name="uq_agent_version"),)
