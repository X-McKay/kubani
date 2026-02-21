"""Nexus workflow state models.

These models represent the queryable state of the Nexus Syndicate workflow.
They are designed to be serializable by Temporal and queryable by the UI
backend for real-time status display.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from kubani.nexus.models.messages import ConversationMessage


class NexusStatus(str, Enum):
    """High-level status of the Nexus agent."""

    IDLE = "idle"
    PROCESSING = "processing"
    PLANNING = "planning"
    EXECUTING = "executing"
    TOOL_EXECUTING = "tool_executing"
    WAITING_APPROVAL = "waiting_approval"
    ERROR = "error"


class PlanStep(BaseModel):
    """A single step in the agent's execution plan.

    Attributes:
        id: Sequential step identifier.
        description: Human-readable description of what this step does.
        skill_name: The name of the skill to execute (if applicable).
        status: Current status of this step.
        result_summary: Brief summary of the result (populated after execution).
        error: Error message if the step failed.
        started_at: When execution of this step began.
        completed_at: When execution of this step finished.
    """

    id: int
    description: str
    skill_name: str | None = None
    status: str = "pending"  # pending, running, completed, failed, skipped
    result_summary: str | None = None
    error: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


class ExecutionPlan(BaseModel):
    """A versioned execution plan produced by the planning activity.

    Plans are versioned so the UI can track plan changes over time.
    The agent may re-plan mid-execution if it encounters unexpected results.

    Attributes:
        version: Monotonically increasing plan version number.
        goal: The high-level goal this plan is trying to achieve.
        steps: Ordered list of steps to execute.
        created_at: When this version of the plan was created.
    """

    version: int = 1
    goal: str = ""
    steps: list[PlanStep] = Field(default_factory=list)
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def current_step(self) -> PlanStep | None:
        """Get the currently running step, if any."""
        for step in self.steps:
            if step.status == "running":
                return step
        return None

    @property
    def next_pending_step(self) -> PlanStep | None:
        """Get the next pending step."""
        for step in self.steps:
            if step.status == "pending":
                return step
        return None

    @property
    def is_complete(self) -> bool:
        """Check if all steps are completed or skipped."""
        return all(s.status in ("completed", "skipped") for s in self.steps)

    @property
    def has_failures(self) -> bool:
        """Check if any step has failed."""
        return any(s.status == "failed" for s in self.steps)


class NexusWorkflowState(BaseModel):
    """The complete, queryable state of the Nexus workflow.

    This model is returned by the Temporal query handler and consumed
    by the UI backend for real-time status display.

    Attributes:
        user_id: The primary user this agent instance serves.
        conversation_id: Current active conversation ID.
        status: High-level agent status.
        current_goal: What the agent is currently trying to accomplish.
        current_plan: The current execution plan (if any).
        conversation_history: Recent conversation messages (windowed).
        last_error: Most recent error message.
        actions_count: Total number of actions taken in this session.
        started_at: When this workflow instance started.
    """

    user_id: str
    conversation_id: str = ""
    status: NexusStatus = NexusStatus.IDLE
    current_goal: str | None = None
    current_plan: ExecutionPlan | None = None
    conversation_history: list[ConversationMessage] = Field(default_factory=list)
    tool_call_history: list[dict[str, Any]] = Field(default_factory=list)
    last_error: str | None = None
    actions_count: int = 0
    started_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def add_message(self, message: ConversationMessage) -> None:
        """Add a message to the conversation history.

        Maintains a sliding window of the last 50 messages to keep
        the workflow state size manageable.
        """
        self.conversation_history.append(message)
        # Keep only the last 50 messages in the workflow state
        # Full history is persisted in PostgreSQL
        if len(self.conversation_history) > 50:
            self.conversation_history = self.conversation_history[-50:]

    def to_dict(self) -> dict[str, Any]:
        """Serialize for Temporal queries."""
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NexusWorkflowState:
        """Deserialize from Temporal query result."""
        return cls.model_validate(data)
