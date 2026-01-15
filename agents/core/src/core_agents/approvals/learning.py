"""
Approval learning - stores and queries approval outcomes for continuous improvement.

Tracks:
- What actions were approved/rejected
- Who approved them
- Whether the action succeeded
- Enables learning from past approvals
"""

import logging
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class RiskLevel(str, Enum):
    """Risk level for actions requiring approval."""

    LOW = "low"  # Auto-approve: rollout restart, scale up
    MEDIUM = "medium"  # Require approval: pod delete, scale down
    HIGH = "high"  # Require approval + confirmation: deployment delete


class ActionOutcome(str, Enum):
    """Outcome of an executed action."""

    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"  # Action executed but verification failed


class ApprovalLearning(BaseModel):
    """
    Learning record for an approval-gated action.

    Stores the full lifecycle: request -> approval -> execution -> outcome
    """

    # Identifiers
    learning_id: str = Field(description="Unique learning ID")
    correlation_id: str | None = Field(default=None, description="Related incident correlation ID")

    # Issue context
    issue_pattern: str = Field(
        description="Pattern type: timeout, oom, crash_loop, storage, network"
    )
    resource_type: str = Field(description="Resource type: pod, deployment, statefulset")
    resource_name: str = Field(description="Name of the affected resource")
    namespace: str = Field(description="Kubernetes namespace")

    # Action context
    action: str = Field(description="Action taken: delete_pod, scale_deployment, rollout_restart")
    risk_level: RiskLevel = Field(description="Risk level of the action")

    # Approval details
    approval_status: str = Field(description="approved, rejected, timeout, auto_approved")
    approved_by: str | None = Field(default=None, description="Discord username who approved")
    approval_requested_at: datetime = Field(description="When approval was requested")
    approval_responded_at: datetime | None = Field(
        default=None, description="When approval response was received"
    )
    approval_duration_seconds: float = Field(
        default=0.0, description="Time to get approval response"
    )

    # Execution outcome
    action_executed: bool = Field(default=False, description="Whether action was executed")
    action_outcome: ActionOutcome | None = Field(default=None, description="Outcome of the action")
    execution_error: str | None = Field(
        default=None, description="Error message if execution failed"
    )

    # Verification
    verification_passed: bool | None = Field(
        default=None, description="Whether verification checks passed"
    )
    verification_details: str | None = Field(default=None, description="Details of verification")

    # Resolution summary
    resolution_summary: str = Field(description="Summary of what happened and outcome")

    # Learning metadata
    confidence: float = Field(default=0.5, description="Confidence this was the right action (0-1)")
    tags: list[str] = Field(default_factory=list, description="Tags for categorization")
    agent: str = Field(description="Agent that performed this action")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    def to_learning_content(self) -> str:
        """Format as learning content for memory storage."""
        lines = [
            f"Approval Learning: {self.action} on {self.resource_type}/{self.resource_name}",
            f"Pattern: {self.issue_pattern}",
            f"Namespace: {self.namespace}",
            f"Risk Level: {self.risk_level.value}",
            f"Approval: {self.approval_status}",
        ]

        if self.approved_by:
            lines.append(f"Approved by: {self.approved_by}")

        if self.action_executed:
            lines.append(
                f"Outcome: {self.action_outcome.value if self.action_outcome else 'unknown'}"
            )

            if self.verification_passed is not None:
                lines.append(f"Verification: {'passed' if self.verification_passed else 'failed'}")

        lines.append(f"Summary: {self.resolution_summary}")

        return "\n".join(lines)

    def to_context_dict(self) -> dict[str, Any]:
        """Convert to context dictionary for memory storage."""
        return {
            "correlation_id": self.correlation_id,
            "issue_pattern": self.issue_pattern,
            "resource_type": self.resource_type,
            "resource_name": self.resource_name,
            "namespace": self.namespace,
            "action": self.action,
            "risk_level": self.risk_level.value,
            "approval_status": self.approval_status,
            "approved_by": self.approved_by,
            "action_executed": self.action_executed,
            "action_outcome": self.action_outcome.value if self.action_outcome else None,
            "verification_passed": self.verification_passed,
        }


class PastApprovalMatch(BaseModel):
    """A matching past approval for similar issues."""

    learning_id: str
    issue_pattern: str
    action: str
    approval_status: str
    action_outcome: ActionOutcome | None
    approved_by: str | None
    resolution_summary: str
    confidence: float
    timestamp: datetime
    relevance_score: float = Field(default=0.0, description="Semantic similarity score")


class PastApprovalSummary(BaseModel):
    """Summary of past approvals for similar issues."""

    total_similar: int = Field(description="Total similar past incidents")
    approved_count: int = Field(description="How many were approved")
    rejected_count: int = Field(description="How many were rejected")
    success_count: int = Field(description="How many approved actions succeeded")
    success_rate: float = Field(description="Success rate of approved actions")
    last_similar: PastApprovalMatch | None = Field(
        default=None, description="Most recent similar approval"
    )
    matches: list[PastApprovalMatch] = Field(
        default_factory=list, description="Top matching past approvals"
    )

    def format_for_discord(self) -> str:
        """Format summary for Discord approval request."""
        if self.total_similar == 0:
            return "_No similar past incidents found_"

        lines = [
            f"Similar issue resolved {self.total_similar} time(s) before",
        ]

        if self.last_similar and self.last_similar.approved_by:
            lines.append(f"Last: by @{self.last_similar.approved_by}")

        if self.approved_count > 0:
            lines.append(f"Success rate: {self.success_rate:.0%}")

        return "\n  ".join(lines)


def calculate_confidence(
    action_outcome: ActionOutcome | None,
    verification_passed: bool | None,
    approval_status: str,
) -> float:
    """
    Calculate confidence score for a learning.

    Higher confidence = more reliable learning.
    """
    if approval_status == "rejected":
        # Rejected actions have moderate confidence (we learned what NOT to do)
        return 0.6

    if approval_status == "timeout":
        # Timeout is low confidence - we don't know what would have happened
        return 0.3

    if not action_outcome:
        return 0.4

    if action_outcome == ActionOutcome.SUCCESS:
        if verification_passed:
            return 0.95  # High confidence - action worked and verified
        return 0.8  # Good confidence - action worked

    if action_outcome == ActionOutcome.PARTIAL:
        return 0.5  # Medium confidence - partially worked

    # Failure
    return 0.7  # Moderate confidence - we learned this doesn't work
