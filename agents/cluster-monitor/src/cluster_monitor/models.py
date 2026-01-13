"""
Data models for the cluster-monitor agent.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class InvestigationStage(str, Enum):
    """Stages of an investigation."""

    CORRELATING = "correlating"
    ANALYZING = "analyzing"
    QUERYING_MEMORY = "querying_memory"
    INVESTIGATING = "investigating"
    PLANNING_REMEDIATION = "planning_remediation"
    EXECUTING_ACTION = "executing_action"
    VERIFYING = "verifying"
    SUMMARIZING = "summarizing"
    COMPLETED = "completed"
    FAILED = "failed"


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


class InvestigationState(BaseModel):
    """State of an ongoing investigation."""

    investigation_id: str
    correlation_id: str
    stage: InvestigationStage
    discord_thread_id: str | None = None
    events: list[K8sEvent] = Field(default_factory=list)
    findings: dict[str, Any] = Field(default_factory=dict)
    actions_taken: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    def update_stage(self, new_stage: InvestigationStage) -> None:
        """Update the investigation stage and timestamp."""
        self.stage = new_stage
        self.updated_at = datetime.now(UTC).isoformat()


class WorkerTask(BaseModel):
    """Task for a worker agent."""

    task_id: str
    task_type: str  # "investigate", "query_memory", "remediate", "narrate"
    context: dict[str, Any]
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class WorkerResult(BaseModel):
    """Result from a worker agent."""

    task_id: str
    success: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    completed_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class CorrelatedIssue(BaseModel):
    """A correlated group of related events."""

    correlation_id: str
    events: list[K8sEvent]
    pattern_type: str  # "timeout", "crash_loop", "resource_exhaustion", etc.
    affected_namespaces: list[str]
    affected_resources: list[str]
    severity: Severity
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
