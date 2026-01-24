"""Agent configuration models."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RunMode(str, Enum):
    """Agent execution mode."""

    LOCAL = "local"  # Single process, direct execution
    LOCAL_CLUSTER = "local_cluster"  # Local process, cluster services
    CLUSTER = "cluster"  # Full Temporal worker


class AgentConfig(BaseModel):
    """Configuration for an agent instance."""

    name: str = Field(..., description="Agent name (e.g., 'k8s-monitor')")
    version: str = Field(default="0.0.0", description="Agent version")
    description: str = Field(default="", description="Agent description")

    # Execution mode
    mode: RunMode = Field(default=RunMode.LOCAL, description="Execution mode")

    # LLM configuration
    llm_model: str | None = Field(default=None, description="Override LLM model")
    llm_temperature: float = Field(default=0.0, description="LLM temperature")

    # Skill configuration
    skills_dir: str | None = Field(default=None, description="Skills directory path")
    enabled_skills: list[str] = Field(default_factory=list, description="Enabled skill names")

    # MCP configuration
    mcp_servers: list[str] = Field(default_factory=list, description="Required MCP servers")

    # Observability
    enable_tracing: bool = Field(default=True, description="Enable trace collection")
    trace_backend: str = Field(default="jsonl", description="Trace backend (jsonl, sqlite, otel)")

    model_config = {"extra": "allow"}


class SkillConfig(BaseModel):
    """Configuration for skill execution."""

    name: str = Field(..., description="Skill name")
    version: str = Field(default="latest", description="Skill version")
    timeout_seconds: float = Field(default=300.0, description="Execution timeout")

    # Context provided to the skill
    context: dict[str, Any] = Field(default_factory=dict, description="Skill context")

    # Evaluation settings
    record_trace: bool = Field(default=True, description="Record execution trace")
