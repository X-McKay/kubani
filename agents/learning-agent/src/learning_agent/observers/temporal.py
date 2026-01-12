"""
Temporal Workflow Observer.

Polls Temporal for completed workflows and extracts execution data
for the learning pipeline.

Uses the Temporal SDK directly for reliable workflow querying.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class WorkflowResult:
    """Result of a completed workflow."""

    workflow_id: str
    run_id: str
    workflow_type: str
    task_queue: str
    status: str
    start_time: datetime
    close_time: datetime | None = None
    result: dict[str, Any] | None = None
    history: list[dict[str, Any]] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float | None:
        """Calculate workflow duration."""
        if self.close_time and self.start_time:
            return (self.close_time - self.start_time).total_seconds()
        return None

    @property
    def is_success(self) -> bool:
        """Check if workflow completed successfully."""
        return self.status.lower() in ("completed", "complete")

    @property
    def agent_name(self) -> str:
        """Extract agent name from task queue."""
        # Task queue is typically the agent name
        return self.task_queue.replace("-", "_")


class WorkflowObserver:
    """
    Observes Temporal workflows for completed executions.

    Uses the Temporal SDK directly to query workflow state and history.
    """

    def __init__(
        self,
        temporal_host: str = "localhost:7233",
        temporal_namespace: str = "default",
    ):
        """
        Initialize the workflow observer.

        Args:
            temporal_host: Temporal server host:port
            temporal_namespace: Temporal namespace to query
        """
        self.temporal_host = temporal_host
        self.temporal_namespace = temporal_namespace
        self._client = None
        self._seen_workflows: set[str] = set()
        self._max_seen_cache = 10000

    async def _get_client(self):
        """Get or create Temporal client."""
        if self._client is None:
            try:
                from temporalio.client import Client

                self._client = await Client.connect(
                    self.temporal_host,
                    namespace=self.temporal_namespace,
                )
                logger.info(
                    f"Connected to Temporal at {self.temporal_host} "
                    f"(namespace: {self.temporal_namespace})"
                )
            except Exception as e:
                logger.warning(f"Failed to connect to Temporal: {e}")
                raise
        return self._client

    async def close(self) -> None:
        """Close Temporal client."""
        # Temporal client doesn't have explicit close
        self._client = None

    async def poll_completed_workflows(
        self,
        since: datetime | None = None,
        task_queues: list[str] | None = None,
        limit: int = 50,
    ) -> list[WorkflowResult]:
        """
        Poll for recently completed workflows.

        Args:
            since: Only return workflows completed after this time
            task_queues: Filter by specific task queues (agent names)
            limit: Maximum workflows to return

        Returns:
            List of completed workflow results
        """
        if since is None:
            since = datetime.now(UTC) - timedelta(minutes=5)

        try:
            client = await self._get_client()
            workflows = []
            count = 0

            # Build query - list recent completed workflows
            query = "ExecutionStatus = 'Completed'"

            # Filter by close time
            close_time_str = since.strftime("%Y-%m-%dT%H:%M:%SZ")
            query += f" AND CloseTime > '{close_time_str}'"

            async for wf in client.list_workflows(query=query):
                if count >= limit:
                    break

                workflow_id = wf.id

                # Skip if already seen
                if workflow_id in self._seen_workflows:
                    continue

                # Filter by task queue if specified
                task_queue = wf.task_queue or ""
                if task_queues and task_queue not in task_queues:
                    continue

                workflow = WorkflowResult(
                    workflow_id=workflow_id,
                    run_id=wf.run_id or "",
                    workflow_type=wf.workflow_type or "unknown",
                    task_queue=task_queue,
                    status=str(wf.status.name) if wf.status else "unknown",
                    start_time=wf.start_time or datetime.now(UTC),
                    close_time=wf.close_time,
                )

                workflows.append(workflow)
                self._mark_seen(workflow_id)
                count += 1

            logger.debug(f"Found {len(workflows)} new completed workflows")
            return workflows

        except Exception as e:
            logger.warning(f"Failed to poll workflows: {e}")
            return []

    async def get_workflow_result(self, workflow_id: str) -> dict[str, Any] | None:
        """
        Get the result of a completed workflow.

        Args:
            workflow_id: The workflow identifier

        Returns:
            Workflow result dict or None if not available
        """
        try:
            client = await self._get_client()
            handle = client.get_workflow_handle(workflow_id)

            # Get result with short timeout
            import asyncio

            result = await asyncio.wait_for(handle.result(), timeout=5.0)

            if isinstance(result, dict):
                return result
            return {"value": result}

        except Exception as e:
            logger.debug(f"Failed to get workflow result for {workflow_id}: {e}")
            return None

    async def get_workflow_history(
        self,
        workflow_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Get the event history of a workflow.

        Args:
            workflow_id: The workflow identifier
            limit: Maximum events to return

        Returns:
            List of workflow history events
        """
        try:
            client = await self._get_client()
            handle = client.get_workflow_handle(workflow_id)

            events = []
            async for event in handle.fetch_history_events():
                events.append(
                    {
                        "eventId": event.event_id,
                        "eventType": event.event_type.name,
                        "eventTime": (
                            event.event_time.ToDatetime().isoformat() if event.event_time else None
                        ),
                    }
                )
                if len(events) >= limit:
                    break

            return events

        except Exception as e:
            logger.debug(f"Failed to get workflow history for {workflow_id}: {e}")
            return []

    async def get_workflow_with_details(self, workflow_id: str) -> WorkflowResult | None:
        """
        Get a workflow with its result and history populated.

        Args:
            workflow_id: The workflow identifier

        Returns:
            WorkflowResult with details or None
        """
        try:
            client = await self._get_client()
            handle = client.get_workflow_handle(workflow_id)
            desc = await handle.describe()

            workflow = WorkflowResult(
                workflow_id=workflow_id,
                run_id=desc.run_id or "",
                workflow_type=desc.workflow_type or "unknown",
                task_queue=desc.task_queue or "",
                status=str(desc.status.name) if desc.status else "unknown",
                start_time=desc.start_time or datetime.now(UTC),
                close_time=desc.close_time,
            )

            # Get result if completed
            if workflow.is_success:
                workflow.result = await self.get_workflow_result(workflow_id)

            # Get history
            workflow.history = await self.get_workflow_history(workflow_id)

            return workflow

        except Exception as e:
            logger.warning(f"Failed to get workflow details for {workflow_id}: {e}")
            return None

    def _mark_seen(self, workflow_id: str) -> None:
        """Mark a workflow as seen to avoid reprocessing."""
        self._seen_workflows.add(workflow_id)

        # Prune cache if too large
        if len(self._seen_workflows) > self._max_seen_cache:
            # Remove oldest half
            to_remove = list(self._seen_workflows)[: self._max_seen_cache // 2]
            for wf_id in to_remove:
                self._seen_workflows.discard(wf_id)

    def reset_seen(self) -> None:
        """Reset the seen workflows cache."""
        self._seen_workflows.clear()
