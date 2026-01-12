"""
Temporal MCP Server data models.

Pydantic models for Temporal workflow and schedule data.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WorkflowResult(BaseModel):
    """Result model for a single workflow execution."""

    workflow_id: str = Field(description="Unique workflow identifier")
    run_id: str | None = Field(default=None, description="Run ID for this execution")
    workflow_type: str | None = Field(default=None, description="Workflow type/name")
    status: str = Field(description="Current execution status")
    start_time: datetime | None = Field(default=None, description="When the workflow started")
    close_time: datetime | None = Field(default=None, description="When the workflow completed")
    task_queue: str | None = Field(default=None, description="Task queue the workflow runs on")


class WorkflowsResult(BaseModel):
    """Result model for listing workflows."""

    workflows: list[WorkflowResult] = Field(description="List of workflow executions")
    count: int = Field(description="Number of workflows returned")


class WorkflowHistoryEvent(BaseModel):
    """A single event in workflow history."""

    event_id: int = Field(description="Event ID in the history")
    event_type: str = Field(description="Type of event")
    timestamp: datetime | None = Field(default=None, description="When the event occurred")


class WorkflowHistoryResult(BaseModel):
    """Result model for workflow history."""

    workflow_id: str = Field(description="Workflow identifier")
    run_id: str | None = Field(default=None, description="Run ID")
    events: list[dict[str, Any]] = Field(description="History events")
    count: int = Field(description="Number of events returned")


class ActivityResult(BaseModel):
    """Result model for activity information."""

    activity_id: str = Field(description="Activity identifier")
    activity_type: str = Field(description="Activity type/name")
    status: str = Field(description="Activity status")
    started_at: datetime | None = Field(default=None, description="When activity started")
    completed_at: datetime | None = Field(default=None, description="When activity completed")
    attempt: int = Field(default=1, description="Current attempt number")
    last_failure: str | None = Field(default=None, description="Last failure reason if any")


class ScheduleInfo(BaseModel):
    """Information about a schedule."""

    schedule_id: str = Field(description="Schedule identifier")
    workflow_type: str | None = Field(default=None, description="Workflow type this schedule runs")
    paused: bool = Field(default=False, description="Whether the schedule is paused")
    recent_actions: int = Field(default=0, description="Number of recent actions")
    next_action_time: datetime | None = Field(default=None, description="Next scheduled action time")


class SchedulesResult(BaseModel):
    """Result model for listing schedules."""

    schedules: list[ScheduleInfo] = Field(description="List of schedules")
    count: int = Field(description="Number of schedules returned")


class ScheduleResult(BaseModel):
    """Result model for schedule operations."""

    schedule_id: str = Field(description="Schedule identifier")
    action: str = Field(description="Action performed")
    note: str | None = Field(default=None, description="Optional note")
