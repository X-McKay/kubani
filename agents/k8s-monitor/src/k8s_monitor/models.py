"""
Pydantic models for the Kubernetes monitoring and remediation agent.

Defines data structures for health reports, remediation attempts,
and Discord notifications.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class HealthStatus(str, Enum):
    """Cluster health status levels."""

    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    ERROR = "error"


class RemediationStatus(str, Enum):
    """Status of a remediation attempt."""

    PENDING = "pending"
    INVESTIGATING = "investigating"
    ATTEMPTING_FIX = "attempting_fix"
    SUCCESS = "success"
    FAILED = "failed"
    ESCALATED = "escalated"


class Issue(BaseModel):
    """Represents a detected cluster issue."""

    id: str = Field(description="Unique identifier for the issue")
    title: str = Field(description="Short title describing the issue")
    description: str = Field(description="Detailed description of the issue")
    severity: HealthStatus = Field(description="Severity level")
    resource_type: str = Field(description="Type of K8s resource affected (e.g., Pod, Deployment)")
    resource_name: str = Field(description="Name of the affected resource")
    namespace: str = Field(description="Namespace of the affected resource")
    detected_at: str = Field(description="ISO timestamp when issue was detected")
    raw_data: dict[str, Any] = Field(default_factory=dict, description="Raw data from K8s API")


class Investigation(BaseModel):
    """Results of investigating an issue."""

    issue_id: str = Field(description="ID of the issue being investigated")
    findings: str = Field(description="Detailed findings from investigation")
    root_cause: str = Field(description="Identified root cause")
    proposed_fix: str = Field(description="Proposed remediation action")
    fix_command: str = Field(description="Specific command/action to execute")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in the proposed fix (0-1)")
    investigated_at: str = Field(description="ISO timestamp of investigation")


class FixAttempt(BaseModel):
    """Record of an attempted fix."""

    attempt_number: int = Field(ge=1, le=3, description="Which attempt this is (1-3)")
    action_taken: str = Field(description="Description of the action taken")
    command_executed: str = Field(description="Actual command or API call executed")
    result: str = Field(description="Result of the action")
    success: bool = Field(description="Whether the fix resolved the issue")
    error_message: str | None = Field(default=None, description="Error message if failed")
    attempted_at: str = Field(description="ISO timestamp of the attempt")


class RemediationRecord(BaseModel):
    """Complete record of a remediation process."""

    issue: Issue = Field(description="The original issue")
    status: RemediationStatus = Field(description="Current status of remediation")
    investigations: list[Investigation] = Field(default_factory=list)
    fix_attempts: list[FixAttempt] = Field(default_factory=list)
    final_outcome: str | None = Field(default=None, description="Final outcome description")
    started_at: str = Field(description="ISO timestamp when remediation started")
    completed_at: str | None = Field(default=None, description="ISO timestamp when completed")

    @property
    def current_attempt(self) -> int:
        """Return the current attempt number (0 if none yet)."""
        return len(self.fix_attempts)

    @property
    def can_retry(self) -> bool:
        """Check if more retry attempts are allowed."""
        return self.current_attempt < 3 and self.status == RemediationStatus.FAILED


class ClusterHealthReport(BaseModel):
    """Result of cluster health analysis."""

    summary: str = Field(description="Human-readable health summary")
    status: HealthStatus = Field(description="Overall cluster health status")
    timestamp: str = Field(description="ISO format timestamp of the analysis")
    issues: list[Issue] = Field(default_factory=list, description="Detected issues")
    error: str | None = Field(default=None, description="Error message if analysis failed")

    model_config = {"frozen": True}


class DiscordPostResult(BaseModel):
    """Result of posting to Discord."""

    success: bool = Field(description="Whether the post was successful")
    message_id: str | None = Field(default=None, description="Discord message ID if successful")
    error: str | None = Field(default=None, description="Error message if failed")


class DiscordMessageType(str, Enum):
    """Types of Discord messages for different remediation stages."""

    ISSUE_DETECTED = "issue_detected"
    INVESTIGATION_COMPLETE = "investigation_complete"
    FIX_ATTEMPTED = "fix_attempted"
    FIX_SUCCESS = "fix_success"
    FIX_FAILED = "fix_failed"
    ESCALATION = "escalation"
    HEALTH_REPORT = "health_report"
