"""
Approval flow schema definitions.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ApprovalStatus(str, Enum):
    """Status of an approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"
    ERROR = "error"


class ApprovalRequest(BaseModel):
    """
    Request for human approval before executing an action.

    Used when a skill or agent needs to perform a potentially
    dangerous action that requires human oversight.
    """

    id: str = Field(default="", description="Unique request ID (auto-generated)")
    action: str = Field(description="Name of the action requiring approval")
    resource: str = Field(description="Resource being acted upon")
    reason: str = Field(description="Why this action is needed")

    # Optional context
    skill_id: str | None = Field(default=None, description="Skill requesting approval")
    agent: str = Field(default="unknown", description="Agent requesting approval")
    context: dict[str, Any] = Field(
        default_factory=dict, description="Additional context for the approver"
    )

    # Timing
    timeout_seconds: int = Field(
        default=300, description="How long to wait for approval (5 min default)"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def format_discord_message(self) -> str:
        """Format the request for Discord display."""
        lines = [
            "**Approval Required**",
            "",
            f"**Action:** `{self.action}`",
            f"**Resource:** `{self.resource}`",
            f"**Reason:** {self.reason}",
        ]

        if self.skill_id:
            lines.append(f"**Skill:** `{self.skill_id}`")

        lines.append(f"**Agent:** `{self.agent}`")

        if self.context:
            lines.append("")
            lines.append("**Context:**")
            for key, value in self.context.items():
                lines.append(f"  • {key}: `{value}`")

        lines.extend(
            [
                "",
                f"_Expires in {self.timeout_seconds // 60} minutes_",
                "",
                "React with ✅ to approve or ❌ to reject",
            ]
        )

        return "\n".join(lines)


class ApprovalResult(BaseModel):
    """Result of an approval request."""

    request_id: str = Field(description="ID of the original request")
    status: ApprovalStatus = Field(description="Final status")
    approved: bool = Field(description="Whether the action was approved")

    # Response details
    responder: str | None = Field(default=None, description="Who approved/rejected (if known)")
    response_reason: str | None = Field(default=None, description="Reason given for the decision")
    responded_at: datetime | None = Field(
        default=None, description="When the response was received"
    )

    # Timing
    requested_at: datetime = Field(description="When the request was made")
    elapsed_seconds: float = Field(default=0.0, description="Time from request to response")

    @classmethod
    def approved_result(
        cls,
        request: ApprovalRequest,
        responder: str | None = None,
    ) -> "ApprovalResult":
        """Create an approved result."""
        now = datetime.utcnow()
        return cls(
            request_id=request.id,
            status=ApprovalStatus.APPROVED,
            approved=True,
            responder=responder,
            responded_at=now,
            requested_at=request.created_at,
            elapsed_seconds=(now - request.created_at).total_seconds(),
        )

    @classmethod
    def rejected_result(
        cls,
        request: ApprovalRequest,
        responder: str | None = None,
        reason: str | None = None,
    ) -> "ApprovalResult":
        """Create a rejected result."""
        now = datetime.utcnow()
        return cls(
            request_id=request.id,
            status=ApprovalStatus.REJECTED,
            approved=False,
            responder=responder,
            response_reason=reason,
            responded_at=now,
            requested_at=request.created_at,
            elapsed_seconds=(now - request.created_at).total_seconds(),
        )

    @classmethod
    def timeout_result(cls, request: ApprovalRequest) -> "ApprovalResult":
        """Create a timeout result."""
        now = datetime.utcnow()
        return cls(
            request_id=request.id,
            status=ApprovalStatus.TIMEOUT,
            approved=False,
            responded_at=now,
            requested_at=request.created_at,
            elapsed_seconds=(now - request.created_at).total_seconds(),
        )

    @classmethod
    def error_result(
        cls,
        request: ApprovalRequest,
        error: str,
    ) -> "ApprovalResult":
        """Create an error result."""
        now = datetime.utcnow()
        return cls(
            request_id=request.id,
            status=ApprovalStatus.ERROR,
            approved=False,
            response_reason=error,
            responded_at=now,
            requested_at=request.created_at,
            elapsed_seconds=(now - request.created_at).total_seconds(),
        )


class Approver(ABC):
    """
    Abstract base class for approval mechanisms.

    Implementations can use different channels:
    - Discord reactions
    - Slack buttons
    - CLI prompts
    - Event-based confirmation
    """

    @abstractmethod
    async def request_approval(self, request: ApprovalRequest) -> ApprovalResult:
        """
        Request approval for an action.

        Args:
            request: The approval request

        Returns:
            Result indicating approval, rejection, timeout, or error
        """
        ...
