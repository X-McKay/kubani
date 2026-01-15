"""
Data models for the cluster-swarm agent.

Reuses most models from cluster-monitor but adds swarm-specific types.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Severity(str, Enum):
    """Issue severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class K8sEvent(BaseModel):
    """Kubernetes event from Sentinel."""

    event_id: str
    event_type: str  # "Warning", "Error", "Normal"
    reason: str  # e.g., "CrashLoopBackOff", "Unhealthy"
    message: str
    namespace: str
    resource_name: str
    resource_kind: str  # "Pod", "Deployment", etc.
    severity: Severity
    timestamp: str
    count: int = 1


class CorrelatedIssue(BaseModel):
    """A correlated group of related events."""

    correlation_id: str
    events: list[K8sEvent]
    pattern_type: str  # "timeout", "crash_loop", "resource_exhaustion", etc.
    affected_namespaces: list[str]
    affected_resources: list[str]
    severity: Severity
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class SwarmContext(BaseModel):
    """
    Context shared across swarm agents during an investigation.

    This is passed between agents via handoffs and accumulates
    findings as the investigation progresses.
    """

    correlation_id: str
    events: list[K8sEvent]
    pattern_type: str
    severity: Severity

    # Accumulated findings
    diagnostic_findings: dict[str, Any] = Field(default_factory=dict)
    past_incidents: list[dict[str, Any]] = Field(default_factory=list)
    remediation_plan: dict[str, Any] | None = None
    actions_taken: list[dict[str, Any]] = Field(default_factory=list)

    # Communication tracking
    discord_thread_id: str | None = None
    messages_posted: list[str] = Field(default_factory=list)

    # Metadata
    started_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    current_agent: str | None = None


class InvestigationState(BaseModel):
    """
    Compact state passed between agents via handoff context.

    This replaces full conversation accumulation with structured data
    to reduce context size and improve handoff clarity.

    Usage:
        # When handing off to another agent:
        handoff_to_agent(
            agent_name="investigator",
            message="Investigate pod crash",
            context=state.model_dump()
        )

        # Receiving agent extracts from context:
        state = InvestigationState(**context)
    """

    # Issue identity
    correlation_id: str
    pattern_type: str
    severity: str
    affected_pods: list[str] = Field(default_factory=list)

    # Compact findings (not full tool results)
    root_cause: str | None = None  # One sentence summary
    key_findings: list[str] = Field(default_factory=list)  # Max 5 bullet points
    error_snippets: list[str] = Field(default_factory=list)  # Max 3 relevant snippets

    # Action tracking
    actions_taken: list[str] = Field(default_factory=list)
    remediation_needed: bool = False
    remediation_result: str | None = None

    # Discord tracking
    discord_messages_posted: int = 0

    def add_finding(self, finding: str) -> None:
        """Add a finding, keeping max 5."""
        if len(self.key_findings) < 5:
            self.key_findings.append(finding[:200])  # Truncate long findings

    def add_error_snippet(self, snippet: str) -> None:
        """Add an error snippet, keeping max 3."""
        if len(self.error_snippets) < 3:
            self.error_snippets.append(snippet[:300])  # Truncate long snippets

    def add_action(self, action: str) -> None:
        """Record an action taken."""
        if len(self.actions_taken) < 5:
            self.actions_taken.append(action[:150])

    @classmethod
    def from_correlated_issue(cls, issue: "CorrelatedIssue") -> "InvestigationState":
        """Create initial state from a correlated issue."""
        return cls(
            correlation_id=issue.correlation_id,
            pattern_type=issue.pattern_type,
            severity=issue.severity.value,
            affected_pods=[
                r.split("/")[1] if "/" in r else r for r in issue.affected_resources[:5]
            ],
        )
