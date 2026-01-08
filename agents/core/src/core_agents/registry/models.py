"""Pydantic models for the registry client."""

from datetime import datetime

from pydantic import BaseModel, Field


class AgentCapability(BaseModel):
    """Capability provided by an agent."""

    name: str
    description: str | None = None
    input_schema: dict = Field(default_factory=dict)
    output_schema: dict = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class AgentInfo(BaseModel):
    """Information about a registered agent."""

    id: str
    name: str
    description: str | None = None
    version: str | None = None
    endpoint: str | None = None
    task_queue: str | None = None
    status: str = "unknown"
    last_heartbeat: datetime | None = None
    metadata: dict = Field(default_factory=dict)
    capabilities: list[AgentCapability] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MCPServer(BaseModel):
    """Registered MCP server."""

    id: str
    name: str
    description: str | None = None
    transport: str  # stdio, sse, streamable-http
    connection_config: dict
    capabilities: list[str] = Field(default_factory=list)
    namespaces: list[str] | None = None
    read_only: bool = False
    status: str = "active"
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MCPPolicy(BaseModel):
    """Policy for MCP server access."""

    id: int | None = None
    agent_pattern: str
    server_id: str
    allowed_tools: list[str] | None = None
    require_approval: list[str] = Field(default_factory=list)
    namespace_restrictions: dict | None = None
    priority: int = 0
    created_at: datetime | None = None


class EffectivePolicy(BaseModel):
    """Effective MCP policy for an agent."""

    agent_id: str
    servers: list[MCPServer] = Field(default_factory=list)
    policies: list[MCPPolicy] = Field(default_factory=list)


class SkillMetadata(BaseModel):
    """Metadata for a skill (content stored in Qdrant)."""

    id: str
    name: str
    domain: str
    category: str
    status: str = "proposed"
    confidence: float = 0.5
    success_count: int = 0
    failure_count: int = 0
    requires_approval: bool = False
    created_at: datetime | None = None
    validated_at: datetime | None = None
    last_used: datetime | None = None


class Deployment(BaseModel):
    """Deployment record for an agent."""

    id: int | None = None
    agent_id: str
    version: str
    image_tag: str | None = None
    git_sha: str | None = None
    deployed_at: datetime | None = None
    deployed_by: str | None = None
    config_snapshot: dict | None = None
    status: str = "active"
    rollback_from: int | None = None


class Model(BaseModel):
    """LLM model in the registry."""

    id: str  # e.g., "nvidia/Qwen3-14B-FP4"
    name: str
    model_type: str  # general, coding, embeddings, vision
    provider: str | None = None
    quantization: str | None = None
    context_length: int | None = None
    vram_required_gb: float | None = None
    capabilities: dict = Field(default_factory=dict)
    local_path: str | None = None
    status: str = "available"
    created_at: datetime | None = None
    metadata: dict = Field(default_factory=dict)


class Endpoint(BaseModel):
    """Service endpoint in the cluster."""

    id: str  # e.g., "vllm-general", "temporal-frontend"
    name: str
    service_type: str  # llm, embeddings, mcp, temporal, database
    internal_url: str | None = None
    external_url: str | None = None
    health_check_path: str = "/health"
    status: str = "unknown"
    last_health_check: datetime | None = None
    namespace: str | None = None
    environment: str = "production"
    metadata: dict = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ResolvedEndpoint(BaseModel):
    """Resolved endpoint URL."""

    endpoint_id: str
    url: str
    is_internal: bool
    status: str


class HeartbeatResponse(BaseModel):
    """Response from heartbeat update."""

    success: bool
    status: str
    last_heartbeat: datetime
