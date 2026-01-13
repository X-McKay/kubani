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
