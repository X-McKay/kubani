"""
Skill schema definitions.

Skills are KNOWLEDGE about when and how to use MCP tools.
They contain NO executable code - just structured knowledge that agents
use to make decisions.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SkillDomain(str, Enum):
    """Domain categorization for skills."""

    K8S = "k8s"
    NEWS = "news"
    GENERAL = "general"


class SkillCategory(str, Enum):
    """Functional category of skills."""

    DIAGNOSTIC = "diagnostic"  # Investigate and understand issues
    REMEDIATION = "remediation"  # Fix known issues
    COLLECTION = "collection"  # Gather data/information
    ANALYSIS = "analysis"  # Analyze patterns and trends
    OPTIMIZATION = "optimization"  # Improve performance/efficiency
    MONITORING = "monitoring"  # Continuous observation


class MCPToolReference(BaseModel):
    """
    Reference to an MCP server tool.

    This is NOT executable code - it's a pointer to an MCP tool
    that the agent should invoke when executing this skill.
    """

    server: str = Field(description="MCP server name, e.g., 'kubernetes-mcp-server'")
    tool: str = Field(description="Tool name within the server, e.g., 'pods_delete'")
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Parameter template with $variables for substitution",
    )

    def __str__(self) -> str:
        return f"{self.server}:{self.tool}"


class SkillAction(BaseModel):
    """
    A single action within a skill.

    Actions reference MCP tools rather than containing executable code.
    The agent is responsible for invoking the MCP tool with resolved parameters.
    """

    description: str = Field(description="Human-readable description of this action")
    mcp_tool: MCPToolReference = Field(description="MCP tool to invoke")
    timeout_seconds: int = Field(default=60, description="Maximum time to wait for this action")
    continue_on_failure: bool = Field(
        default=False,
        description="Whether to continue to next action if this one fails",
    )


class SkillOutcome(BaseModel):
    """Record of a skill execution outcome for learning."""

    skill_id: str
    success: bool
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    context: dict[str, Any] = Field(
        default_factory=dict, description="Context in which skill was applied"
    )
    error_message: str | None = None
    verification_details: dict[str, bool] = Field(
        default_factory=dict, description="Which success criteria passed/failed"
    )


class Skill(BaseModel):
    """
    A skill is KNOWLEDGE about when and how to use MCP tools.

    Skills do NOT contain executable code. Instead, they contain:
    - Preconditions: When this skill should be considered
    - Actions: Which MCP tools to invoke (as references, not code)
    - Success criteria: How to verify the skill worked
    - Learning metadata: Confidence based on past outcomes

    The agent uses this knowledge to:
    1. Match skills to situations (via semantic search on preconditions)
    2. Execute skills (by calling referenced MCP tools)
    3. Verify success (by checking criteria against current state)
    4. Learn (by tracking outcomes and updating confidence)
    """

    id: str = Field(description="Unique identifier for this skill")
    name: str = Field(description="Human-readable name")
    domain: SkillDomain = Field(description="Domain this skill applies to")
    category: SkillCategory = Field(description="Functional category")

    # Knowledge components
    description: str = Field(
        description="Detailed description of what this skill does and when to use it"
    )
    preconditions: list[str] = Field(
        description="Conditions that should be true before applying this skill"
    )
    actions: list[SkillAction] = Field(description="Ordered list of MCP tool invocations")
    success_criteria: list[str] = Field(description="Conditions to verify after execution")
    failure_handling: str = Field(
        default="Escalate to human operator",
        description="What to do if the skill fails",
    )
    rollback_actions: list[SkillAction] | None = Field(
        default=None, description="Actions to undo this skill if needed"
    )

    # Safety and approval
    requires_approval: bool = Field(
        default=False,
        description="Whether human approval is needed before execution",
    )
    approval_reason: str | None = Field(default=None, description="Why approval is required")

    # Composition
    prerequisite_skills: list[str] = Field(
        default_factory=list,
        description="Skill IDs that should succeed before this one",
    )
    tags: list[str] = Field(default_factory=list, description="Tags for additional categorization")

    # Learning metadata
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confidence score based on past outcomes",
    )
    success_count: int = Field(default=0, description="Number of successful uses")
    failure_count: int = Field(default=0, description="Number of failed uses")
    last_used: datetime | None = Field(default=None, description="When this skill was last applied")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str = Field(
        default="manual", description="How this skill was created: manual, extracted, generated"
    )

    def record_outcome(self, success: bool) -> None:
        """Update learning metadata based on an execution outcome."""
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1

        self.last_used = datetime.utcnow()

        # Update confidence using simple Bayesian-ish approach
        total = self.success_count + self.failure_count
        if total > 0:
            # Add prior of 1 success, 1 failure to avoid extreme values
            self.confidence = (self.success_count + 1) / (total + 2)

    def get_mcp_servers(self) -> set[str]:
        """Get all MCP servers required by this skill."""
        servers = set()
        for action in self.actions:
            servers.add(action.mcp_tool.server)
        if self.rollback_actions:
            for action in self.rollback_actions:
                servers.add(action.mcp_tool.server)
        return servers

    def get_searchable_text(self) -> str:
        """Generate text for semantic search indexing."""
        parts = [
            self.name,
            self.description,
            " ".join(self.preconditions),
            " ".join(self.tags),
        ]
        return " ".join(parts)
