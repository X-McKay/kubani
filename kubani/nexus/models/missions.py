"""Nexus Mission models.

A NexusMission represents a user-defined background goal that the Nexus agent
executes autonomously on a schedule. Missions are the core primitive of the
continuously-running agent loop.

Design principles:
- Missions are bounded: every mission has a hard ``max_tool_calls`` cap that
  prevents runaway agentic loops.
- Missions are auditable: every run is recorded in the ``mission_runs`` table
  with timing, tool usage, and outcome.
- Missions are user-controlled: users can create, pause, resume, and delete
  missions at any time through natural conversation.
- Missions are policy-scoped: each mission specifies which MCP policy governs
  its tool access, defaulting to the conservative ``nexus`` policy.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MissionStatus(str, Enum):
    """Lifecycle status of a mission."""

    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class MissionRunStatus(str, Enum):
    """Status of a single mission execution run."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


class NotifyOn(str, Enum):
    """Conditions under which the agent notifies the user after a mission run."""

    ALWAYS = "always"
    ANOMALY = "anomaly"
    COMPLETION = "completion"
    ERROR = "error"
    NEVER = "never"


class NexusMission(BaseModel):
    """A user-defined background mission for the Nexus agent.

    Attributes:
        id: Unique mission identifier (auto-generated).
        user_id: The user who owns this mission.
        title: Short human-readable title (e.g., "Daily cluster health check").
        goal: Natural language description of what the agent should do.
        schedule: Cron expression controlling when the mission fires.
        status: Current lifecycle status.
        mcp_policy: Name of the MCP policy to apply during mission runs.
            Use ``nexus`` (memory + skills only) for safe missions, or
            ``nexus-proactive`` (adds kubernetes + discord) for richer ones.
        max_tool_calls: Hard cap on tool calls per mission run. Prevents
            runaway loops. Default is 20; maximum is 50.
        notify_on: List of conditions that trigger a user notification.
        last_run_at: Timestamp of the most recent run (if any).
        next_run_at: Estimated timestamp of the next scheduled run.
        run_count: Total number of completed runs.
        created_at: When the mission was created.
        updated_at: When the mission was last modified.
    """

    id: str = Field(default_factory=lambda: f"mission-{uuid.uuid4().hex[:12]}")
    user_id: str
    title: str
    goal: str
    schedule: str = "0 * * * *"  # Default: every hour
    status: MissionStatus = MissionStatus.ACTIVE
    mcp_policy: str = "nexus"
    max_tool_calls: int = Field(default=20, ge=1, le=50)
    notify_on: list[NotifyOn] = Field(
        default_factory=lambda: [NotifyOn.ANOMALY, NotifyOn.ERROR]
    )
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    run_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict (Temporal signal / DB compatible)."""
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NexusMission:
        """Deserialize from a plain dict."""
        return cls.model_validate(data)

    def should_notify(self, run_status: MissionRunStatus, found_anomaly: bool) -> bool:
        """Determine whether the agent should notify the user after a run.

        Args:
            run_status: The outcome of the mission run.
            found_anomaly: Whether the agent flagged an anomaly.

        Returns:
            True if the user should be notified.
        """
        if NotifyOn.ALWAYS in self.notify_on:
            return True
        if NotifyOn.NEVER in self.notify_on:
            return False
        if NotifyOn.ERROR in self.notify_on and run_status in (
            MissionRunStatus.FAILED,
            MissionRunStatus.TIMED_OUT,
        ):
            return True
        if NotifyOn.ANOMALY in self.notify_on and found_anomaly:
            return True
        if NotifyOn.COMPLETION in self.notify_on and run_status == MissionRunStatus.COMPLETED:
            return True
        return False


class MissionRun(BaseModel):
    """A record of a single mission execution.

    Attributes:
        id: Auto-generated run identifier.
        mission_id: The mission this run belongs to.
        user_id: The user who owns the mission.
        status: Outcome of the run.
        tool_calls_made: Number of tool calls consumed.
        found_anomaly: Whether the agent flagged something noteworthy.
        notification_text: The text sent to the user (if any).
        error_message: Error details if the run failed.
        started_at: When the run started.
        completed_at: When the run finished.
        duration_ms: Wall-clock duration in milliseconds.
    """

    id: str = Field(default_factory=lambda: f"run-{uuid.uuid4().hex[:12]}")
    mission_id: str
    user_id: str
    status: MissionRunStatus = MissionRunStatus.RUNNING
    tool_calls_made: int = 0
    found_anomaly: bool = False
    notification_text: str = ""
    error_message: str = ""
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        return self.model_dump(mode="json")
