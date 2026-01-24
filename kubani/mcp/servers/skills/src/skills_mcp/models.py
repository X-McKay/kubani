"""
Data models for Skills MCP Server.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ExecutionStatus(str, Enum):
    """Status of skill execution."""

    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"


class SkillMetadata(BaseModel):
    """Metadata from SKILL.md frontmatter."""

    model_config = {"populate_by_name": True}

    domain: str = ""
    category: str = ""
    requires_approval: bool = Field(default=False, alias="requires-approval")
    confidence: float = 0.5
    mcp_servers: list[str] | None = Field(default=None, alias="mcp-servers")


class SkillInfo(BaseModel):
    """Information about a discovered skill."""

    path: str  # e.g., "k8s/diagnostic/check-pod-health"
    name: str
    version: str = "1.0.0"
    description: str = ""
    metadata: SkillMetadata = Field(default_factory=SkillMetadata)
    content: str = ""  # Full SKILL.md content (markdown body)
    scripts: list[str] = Field(default_factory=list)  # Available scripts in scripts/
    has_tests: bool = False
    skill_dir: str = ""  # Absolute path to skill directory


class ExecutionResult(BaseModel):
    """Result of skill execution."""

    skill_path: str
    status: ExecutionStatus
    output: str = ""
    error: str | None = None
    exit_code: int = 0
    duration_ms: float = 0.0
    executed_at: datetime = Field(default_factory=datetime.utcnow)
    context: dict[str, Any] = Field(default_factory=dict)
    sandbox_id: str | None = None  # Microsandbox sandbox ID if used


class ExecutionOutcome(BaseModel):
    """Outcome record for learning system."""

    skill_path: str
    agent_id: str | None = None
    status: ExecutionStatus
    success: bool
    duration_ms: float
    context: dict[str, Any] = Field(default_factory=dict)
    output_summary: str = ""
    error: str | None = None
    executed_at: datetime = Field(default_factory=datetime.utcnow)


# Response models for MCP tools


class SkillListResult(BaseModel):
    """Result of list_skills tool."""

    skills: list[SkillInfo]
    count: int
    domain: str | None = None
    category: str | None = None


class SkillDetailResult(BaseModel):
    """Result of get_skill tool."""

    skill: SkillInfo
    found: bool = True


class SkillExecuteResult(BaseModel):
    """Result of execute_skill tool."""

    skill_path: str
    status: ExecutionStatus
    output: str = ""
    error: str | None = None
    duration_ms: float = 0.0
    sandbox_used: bool = False
