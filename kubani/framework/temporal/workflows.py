"""Base Temporal workflow classes for Kubani syndicates.

This module provides base workflow classes that implement common patterns:
- Status queries for observability
- Event logging to the event bus
- Signal handlers for pause/resume/cancel

Both the Workflow pattern and Swarm pattern build on these base classes.

Usage:
    from kubani.framework.temporal.workflows import BaseWorkflow

    @workflow.defn
    class MyWorkflow(BaseWorkflow):
        @workflow.run
        async def run(self, input: MyInput) -> MyOutput:
            self._set_status("running", "Processing input")
            # ... workflow logic ...
            return result
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from temporalio import workflow

logger = logging.getLogger(__name__)


# =============================================================================
# Status Types
# =============================================================================


class WorkflowStatus(str, Enum):
    """Status of a workflow."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class StatusInfo:
    """Detailed status information for a workflow.

    Attributes:
        status: Current workflow status
        message: Human-readable status message
        phase: Current phase/step in the workflow
        progress: Progress percentage (0-100) if applicable
        started_at: When the workflow started
        updated_at: When status was last updated
        metadata: Additional status metadata
    """

    status: WorkflowStatus
    message: str
    phase: str | None = None
    progress: float | None = None
    started_at: datetime | None = None
    updated_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "status": self.status.value,
            "message": self.message,
            "phase": self.phase,
            "progress": self.progress,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "metadata": self.metadata,
        }


@dataclass
class WorkflowEvent:
    """An event logged during workflow execution.

    Attributes:
        kind: Event type (e.g., "agent_started", "task_completed")
        message: Event description
        timestamp: When the event occurred
        data: Additional event data
    """

    kind: str
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now())
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "kind": self.kind,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
        }


# =============================================================================
# Base Workflow Mixin
# =============================================================================


class ObservableWorkflowMixin:
    """Mixin providing observability features for workflows.

    Adds:
    - Status tracking with queries
    - Event logging
    - Pause/resume/cancel signals

    Usage:
        @workflow.defn
        class MyWorkflow(ObservableWorkflowMixin):
            def __init__(self):
                super().__init__()
                # Initialize status
                self._init_observability("MyWorkflow")
    """

    def _init_observability(self, workflow_name: str) -> None:
        """Initialize observability state.

        Call this in __init__ after super().__init__().

        Args:
            workflow_name: Name of the workflow for logging
        """
        self._workflow_name = workflow_name
        self._status = StatusInfo(
            status=WorkflowStatus.PENDING,
            message="Workflow initialized",
            started_at=datetime.now(),
            updated_at=datetime.now(),
        )
        self._events: list[WorkflowEvent] = []
        self._paused = False
        self._cancelled = False

    def _set_status(
        self,
        status: WorkflowStatus | str,
        message: str,
        phase: str | None = None,
        progress: float | None = None,
        **metadata: Any,
    ) -> None:
        """Update workflow status.

        Args:
            status: New status (WorkflowStatus or string)
            message: Status message
            phase: Current phase/step
            progress: Progress percentage (0-100)
            **metadata: Additional metadata
        """
        if isinstance(status, str):
            status = WorkflowStatus(status)

        self._status = StatusInfo(
            status=status,
            message=message,
            phase=phase,
            progress=progress,
            started_at=self._status.started_at,
            updated_at=datetime.now(),
            metadata=dict(metadata),
        )

        # Also log as event
        self._log_event(
            "status_change",
            f"Status: {status.value} - {message}",
            phase=phase,
            progress=progress,
        )

    def _log_event(self, kind: str, message: str, **data: Any) -> None:
        """Log a workflow event.

        Args:
            kind: Event type (e.g., "agent_started", "error")
            message: Event description
            **data: Additional event data
        """
        event = WorkflowEvent(
            kind=kind,
            message=message,
            timestamp=datetime.now(),
            data=dict(data),
        )
        self._events.append(event)

        # Keep event log bounded
        max_events = 1000
        if len(self._events) > max_events:
            self._events = self._events[-max_events:]

    async def _wait_if_paused(self) -> bool:
        """Wait if workflow is paused, return True if cancelled.

        Usage:
            if await self._wait_if_paused():
                return  # Workflow cancelled

        Returns:
            True if cancelled, False otherwise
        """
        if self._paused:
            self._set_status(WorkflowStatus.PAUSED, "Workflow paused")
            await workflow.wait_condition(lambda: not self._paused or self._cancelled)

        return self._cancelled

    # =========================================================================
    # Query Handlers
    # =========================================================================

    @workflow.query
    def get_status(self) -> dict[str, Any]:
        """Query current workflow status.

        Returns:
            Dict with status information
        """
        return self._status.to_dict()

    @workflow.query
    def get_events(self, limit: int = 100) -> list[dict[str, Any]]:
        """Query recent workflow events.

        Args:
            limit: Maximum number of events to return

        Returns:
            List of event dicts, most recent first
        """
        events = self._events[-limit:] if limit else self._events
        return [e.to_dict() for e in reversed(events)]

    @workflow.query
    def is_paused(self) -> bool:
        """Check if workflow is paused."""
        return self._paused

    # =========================================================================
    # Signal Handlers
    # =========================================================================

    @workflow.signal
    async def pause(self) -> None:
        """Pause workflow after current operation."""
        self._paused = True
        self._log_event("signal", "Pause signal received")

    @workflow.signal
    async def resume(self) -> None:
        """Resume paused workflow."""
        self._paused = False
        self._log_event("signal", "Resume signal received")

    @workflow.signal
    async def cancel(self) -> None:
        """Cancel workflow."""
        self._cancelled = True
        self._paused = False  # Unblock if waiting
        self._log_event("signal", "Cancel signal received")
        self._set_status(WorkflowStatus.CANCELLED, "Workflow cancelled by signal")


# =============================================================================
# Workflow Pattern Base Class
# =============================================================================


@dataclass
class WorkflowPatternInput:
    """Base input for Workflow pattern syndicates.

    Extend this for specific syndicate inputs.
    """

    correlation_id: str | None = None
    notify: bool = True
    notify_channel: str | None = None


@dataclass
class WorkflowPatternResult:
    """Base result for Workflow pattern syndicates.

    Extend this for specific syndicate results.
    """

    success: bool
    message: str
    correlation_id: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class WorkflowPatternBase(ObservableWorkflowMixin, ABC):
    """Base class for Workflow pattern syndicates.

    The Workflow pattern is for deterministic sequences where the workflow
    controls execution order. Agents are called as activities in a defined order.

    Subclasses must implement:
    - run(): Main workflow logic

    Example:
        @workflow.defn
        class NewsDigestWorkflow(WorkflowPatternBase):
            def __init__(self):
                super().__init__()
                self._init_observability("NewsDigestWorkflow")

            @workflow.run
            async def run(self, input: NewsDigestInput) -> NewsDigestResult:
                self._set_status("running", "Starting digest generation")

                # Step 1: Query collected articles
                articles = await workflow.execute_activity(...)

                # Step 2: Analyze trends
                trends = await workflow.execute_activity(...)

                # Step 3: Generate digest
                digest = await workflow.execute_activity(...)

                return NewsDigestResult(success=True, digest=digest)
    """

    @abstractmethod
    async def run(self, input: Any) -> Any:
        """Main workflow logic. Override in subclass."""
        ...


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Status types
    "WorkflowStatus",
    "StatusInfo",
    "WorkflowEvent",
    # Mixins
    "ObservableWorkflowMixin",
    # Workflow pattern
    "WorkflowPatternInput",
    "WorkflowPatternResult",
    "WorkflowPatternBase",
]
