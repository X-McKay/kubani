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
# Swarm Pattern Types
# =============================================================================


@dataclass
class SwarmTask:
    """A task in the swarm task pool.

    Attributes:
        task_id: Unique task identifier
        swarm_id: ID of the parent swarm request
        requested_capability: Capability needed to handle this task
        target_agent: Optional specific agent to handle (None = any capable)
        message: Task description/prompt
        context: Task context (shared memory, prior work)
        status: Task status (open, leased, done, failed)
        parent_task_id: ID of parent task (for sub-tasks)
        leased_by: Agent ID that leased this task
        lease_expires_at: When the lease expires
        priority: Task priority (higher = more urgent)
        depth: Task depth (for limiting recursion)
    """

    task_id: str
    swarm_id: str
    requested_capability: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)
    target_agent: str | None = None
    status: str = "open"  # open, leased, done, failed
    parent_task_id: str | None = None
    leased_by: str | None = None
    lease_expires_at: datetime | None = None
    priority: int = 0
    depth: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "task_id": self.task_id,
            "swarm_id": self.swarm_id,
            "requested_capability": self.requested_capability,
            "target_agent": self.target_agent,
            "message": self.message,
            "context": self.context,
            "status": self.status,
            "parent_task_id": self.parent_task_id,
            "leased_by": self.leased_by,
            "lease_expires_at": self.lease_expires_at.isoformat()
            if self.lease_expires_at
            else None,
            "priority": self.priority,
            "depth": self.depth,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SwarmTask":
        """Create from dictionary."""
        lease_expires = data.get("lease_expires_at")
        if lease_expires and isinstance(lease_expires, str):
            lease_expires = datetime.fromisoformat(lease_expires)

        return cls(
            task_id=data["task_id"],
            swarm_id=data["swarm_id"],
            requested_capability=data["requested_capability"],
            target_agent=data.get("target_agent"),
            message=data["message"],
            context=data.get("context", {}),
            status=data.get("status", "open"),
            parent_task_id=data.get("parent_task_id"),
            leased_by=data.get("leased_by"),
            lease_expires_at=lease_expires,
            priority=data.get("priority", 0),
            depth=data.get("depth", 0),
        )


@dataclass
class SwarmStatus:
    """Status of a swarm request.

    Attributes:
        swarm_id: Swarm request ID
        status: Overall status
        message: Status message
        tasks_total: Total tasks created
        tasks_completed: Tasks completed successfully
        tasks_failed: Tasks that failed
        tasks_in_progress: Tasks currently being worked
        current_depth: Current task depth
        agents_involved: Set of agents that have worked on this
        events: Recent events
    """

    swarm_id: str
    status: WorkflowStatus
    message: str
    tasks_total: int = 0
    tasks_completed: int = 0
    tasks_failed: int = 0
    tasks_in_progress: int = 0
    current_depth: int = 0
    agents_involved: list[str] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "swarm_id": self.swarm_id,
            "status": self.status.value,
            "message": self.message,
            "tasks_total": self.tasks_total,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "tasks_in_progress": self.tasks_in_progress,
            "current_depth": self.current_depth,
            "agents_involved": self.agents_involved,
            "events": self.events,
        }


# =============================================================================
# Request Tracker Workflow
# =============================================================================


@workflow.defn
class RequestTrackerWorkflow(ObservableWorkflowMixin):
    """Tracks the status of a swarm request without dispatching work.

    This workflow provides observability into swarm execution:
    - Tracks task creation, leasing, and completion
    - Records which agents are involved
    - Maintains event history
    - Answers status queries

    It does NOT dispatch work - agents pull tasks from the pool themselves.
    This separation ensures no central bottleneck in swarm execution.

    Usage:
        # Start tracker for a swarm request
        handle = await client.start_workflow(
            RequestTrackerWorkflow.run,
            SwarmRequest(swarm_id="swarm-123", ...),
            id="tracker-swarm-123",
            task_queue="swarm-trackers",
        )

        # Query status from another workflow or service
        status = await handle.query(RequestTrackerWorkflow.get_swarm_status)

        # Record events via updates
        await handle.execute_update(
            RequestTrackerWorkflow.record_event,
            args=["task_completed", "Agent finished classification", {...}],
        )
    """

    def __init__(self) -> None:
        """Initialize the tracker."""
        self._swarm_status: SwarmStatus | None = None
        self._init_observability("RequestTrackerWorkflow")

    @workflow.run
    async def run(
        self, swarm_id: str, initial_message: str, timeout_hours: int = 24
    ) -> dict[str, Any]:
        """Run the tracker until completion or timeout.

        Args:
            swarm_id: ID of the swarm to track
            initial_message: Initial request message
            timeout_hours: Hours before auto-completing

        Returns:
            Final status dict
        """
        self._swarm_status = SwarmStatus(
            swarm_id=swarm_id,
            status=WorkflowStatus.RUNNING,
            message=initial_message,
        )

        self._set_status(WorkflowStatus.RUNNING, f"Tracking swarm {swarm_id}")
        self._log_event("swarm_started", initial_message, swarm_id=swarm_id)

        # Wait for completion signal or timeout
        try:
            await workflow.wait_condition(
                lambda: self._swarm_status.status
                in (WorkflowStatus.COMPLETED, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED),
                timeout=workflow.timedelta(hours=timeout_hours),
            )
        except workflow.CancelledError:
            self._swarm_status.status = WorkflowStatus.CANCELLED
            self._swarm_status.message = "Tracker cancelled"

        self._set_status(self._swarm_status.status, self._swarm_status.message)
        return self._swarm_status.to_dict()

    # =========================================================================
    # Status Queries
    # =========================================================================

    @workflow.query
    def get_swarm_status(self) -> dict[str, Any]:
        """Query current swarm status."""
        if self._swarm_status:
            return self._swarm_status.to_dict()
        return {"status": "unknown", "message": "Tracker not initialized"}

    @workflow.query
    def get_agents_involved(self) -> list[str]:
        """Get list of agents that have worked on this swarm."""
        if self._swarm_status:
            return self._swarm_status.agents_involved
        return []

    # =========================================================================
    # Update Handlers (for recording progress)
    # =========================================================================

    @workflow.update
    def record_event(
        self,
        kind: str,
        message: str,
        totals: dict[str, int] | None = None,
        phase: str | None = None,
    ) -> dict[str, Any]:
        """Record a swarm event.

        Args:
            kind: Event kind (task_created, task_completed, error, etc.)
            message: Event message
            totals: Optional task count updates
            phase: Optional phase name

        Returns:
            Updated status dict
        """
        if not self._swarm_status:
            return {"error": "Tracker not initialized"}

        # Update totals if provided
        if totals:
            if "total" in totals:
                self._swarm_status.tasks_total = totals["total"]
            if "completed" in totals:
                self._swarm_status.tasks_completed = totals["completed"]
            if "failed" in totals:
                self._swarm_status.tasks_failed = totals["failed"]
            if "in_progress" in totals:
                self._swarm_status.tasks_in_progress = totals["in_progress"]

        # Log event
        self._log_event(kind, message, totals=totals, phase=phase)

        # Add to swarm events (keep bounded)
        event = {"kind": kind, "message": message, "timestamp": datetime.now().isoformat()}
        self._swarm_status.events.append(event)
        if len(self._swarm_status.events) > 100:
            self._swarm_status.events = self._swarm_status.events[-100:]

        return self._swarm_status.to_dict()

    @workflow.update
    def set_lease(self, task_id: str, agent_id: str, capability: str) -> dict[str, Any]:
        """Record that an agent leased a task.

        Args:
            task_id: Task being leased
            agent_id: Agent leasing the task
            capability: Capability being exercised

        Returns:
            Updated status dict
        """
        if not self._swarm_status:
            return {"error": "Tracker not initialized"}

        # Track agent involvement
        if agent_id not in self._swarm_status.agents_involved:
            self._swarm_status.agents_involved.append(agent_id)

        self._swarm_status.tasks_in_progress += 1

        self._log_event(
            "task_leased",
            f"Agent {agent_id} leased task {task_id}",
            task_id=task_id,
            agent_id=agent_id,
            capability=capability,
        )

        return self._swarm_status.to_dict()

    @workflow.update
    def clear_lease(
        self, task_id: str, success: bool = True, error: str | None = None
    ) -> dict[str, Any]:
        """Record task completion.

        Args:
            task_id: Task that completed
            success: Whether it succeeded
            error: Error message if failed

        Returns:
            Updated status dict
        """
        if not self._swarm_status:
            return {"error": "Tracker not initialized"}

        self._swarm_status.tasks_in_progress = max(0, self._swarm_status.tasks_in_progress - 1)

        if success:
            self._swarm_status.tasks_completed += 1
            self._log_event("task_completed", f"Task {task_id} completed", task_id=task_id)
        else:
            self._swarm_status.tasks_failed += 1
            self._log_event(
                "task_failed", f"Task {task_id} failed: {error}", task_id=task_id, error=error
            )

        # Check if swarm is complete
        total_finished = self._swarm_status.tasks_completed + self._swarm_status.tasks_failed
        if (
            total_finished >= self._swarm_status.tasks_total
            and self._swarm_status.tasks_in_progress == 0
        ):
            if self._swarm_status.tasks_failed > 0:
                self._swarm_status.status = WorkflowStatus.FAILED
                self._swarm_status.message = (
                    f"Completed with {self._swarm_status.tasks_failed} failures"
                )
            else:
                self._swarm_status.status = WorkflowStatus.COMPLETED
                self._swarm_status.message = "All tasks completed successfully"

        return self._swarm_status.to_dict()

    @workflow.update
    def add_task(self, task_id: str, capability: str, depth: int = 0) -> dict[str, Any]:
        """Record that a new task was added to the pool.

        Args:
            task_id: New task ID
            capability: Required capability
            depth: Task depth

        Returns:
            Updated status dict
        """
        if not self._swarm_status:
            return {"error": "Tracker not initialized"}

        self._swarm_status.tasks_total += 1
        self._swarm_status.current_depth = max(self._swarm_status.current_depth, depth)

        self._log_event(
            "task_created",
            f"Task {task_id} created requiring {capability}",
            task_id=task_id,
            capability=capability,
            depth=depth,
        )

        return self._swarm_status.to_dict()

    @workflow.signal
    async def complete_swarm(self, success: bool = True, message: str = "") -> None:
        """Signal that the swarm is complete.

        Args:
            success: Whether the swarm succeeded overall
            message: Completion message
        """
        if self._swarm_status:
            self._swarm_status.status = (
                WorkflowStatus.COMPLETED if success else WorkflowStatus.FAILED
            )
            self._swarm_status.message = message or (
                "Swarm completed successfully" if success else "Swarm failed"
            )
            self._log_event("swarm_completed", self._swarm_status.message, success=success)


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
    # Swarm pattern
    "SwarmTask",
    "SwarmStatus",
    "RequestTrackerWorkflow",
]
