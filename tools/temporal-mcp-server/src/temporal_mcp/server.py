"""
Temporal MCP Server implementation.

Provides MCP tools for interacting with Temporal workflows and activities.
Enables agents and Claude Code to manage, monitor, and debug Temporal workflows.
"""

import logging
import os
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from temporalio.client import Client

from temporal_mcp.models import (
    ScheduleInfo,
    ScheduleResult,
    SchedulesResult,
    WorkflowHistoryResult,
    WorkflowResult,
    WorkflowsResult,
)

logger = logging.getLogger(__name__)

# Global Temporal client
_temporal_client: Client | None = None


async def connect_temporal() -> Client:
    """Connect to Temporal at server startup."""
    global _temporal_client

    if _temporal_client is not None:
        return _temporal_client

    host = os.environ.get("TEMPORAL_HOST", "localhost")
    port = int(os.environ.get("TEMPORAL_PORT", "7233"))
    namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")

    logger.info(f"Connecting to Temporal at {host}:{port} (namespace: {namespace})...")
    _temporal_client = await Client.connect(
        f"{host}:{port}",
        namespace=namespace,
    )
    logger.info("Temporal client connected")

    return _temporal_client


async def disconnect_temporal() -> None:
    """Disconnect from Temporal at server shutdown."""
    global _temporal_client
    # Temporal client doesn't have explicit disconnect
    _temporal_client = None


def _get_client_or_error() -> Client:
    """Get the Temporal client or raise an error."""
    if _temporal_client is None:
        raise RuntimeError(
            "Temporal client not initialized. "
            "Ensure connect_temporal() was called at server startup."
        )
    return _temporal_client


@asynccontextmanager
async def lifespan(server: FastMCP):
    """MCP session lifespan."""
    yield


def create_server() -> FastMCP:
    """Create and configure the Temporal MCP server."""
    allowed_hosts_env = os.environ.get("MCP_ALLOWED_HOSTS", "")
    allowed_hosts = ["localhost:*", "127.0.0.1:*"]
    if allowed_hosts_env:
        allowed_hosts.extend(h.strip() for h in allowed_hosts_env.split(",") if h.strip())

    mcp = FastMCP(
        name="Temporal MCP Server",
        instructions=(
            "Temporal workflow orchestration for AI agents. "
            "Use these tools to start, query, signal, and manage Temporal workflows. "
            "Useful for long-running tasks, scheduled jobs, and distributed processing."
        ),
        lifespan=lifespan,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=allowed_hosts,
        ),
    )

    # =========================================================================
    # Workflow Management Tools
    # =========================================================================

    @mcp.tool()
    async def list_workflows(
        query: str | None = None,
        limit: int = 20,
        status: str | None = None,
    ) -> WorkflowsResult:
        """
        List workflows in the Temporal namespace.

        Args:
            query: Optional query string to filter workflows (Temporal query syntax)
            limit: Maximum number of workflows to return (default: 20, max: 100)
            status: Filter by status: running, completed, failed, canceled, terminated

        Returns:
            List of workflow executions
        """
        client = _get_client_or_error()
        limit = min(limit, 100)

        # Build query
        query_parts = []
        if status:
            status_map = {
                "running": "Running",
                "completed": "Completed",
                "failed": "Failed",
                "canceled": "Canceled",
                "terminated": "Terminated",
            }
            if status.lower() in status_map:
                query_parts.append(f"ExecutionStatus = '{status_map[status.lower()]}'")

        if query:
            query_parts.append(query)

        full_query = " AND ".join(query_parts) if query_parts else None

        workflows = []
        async for workflow in client.list_workflows(query=full_query):
            workflows.append(
                WorkflowResult(
                    workflow_id=workflow.id,
                    run_id=workflow.run_id,
                    workflow_type=workflow.workflow_type,
                    status=str(workflow.status.name) if workflow.status else "unknown",
                    start_time=workflow.start_time,
                    close_time=workflow.close_time,
                    task_queue=workflow.task_queue,
                )
            )
            if len(workflows) >= limit:
                break

        return WorkflowsResult(
            workflows=workflows,
            count=len(workflows),
        )

    @mcp.tool()
    async def get_workflow(
        workflow_id: str,
        run_id: str | None = None,
    ) -> WorkflowResult:
        """
        Get details of a specific workflow execution.

        Args:
            workflow_id: The workflow ID
            run_id: Optional run ID (uses latest if not specified)

        Returns:
            Workflow execution details
        """
        client = _get_client_or_error()
        handle = client.get_workflow_handle(workflow_id, run_id=run_id)
        desc = await handle.describe()

        return WorkflowResult(
            workflow_id=desc.id,
            run_id=desc.run_id,
            workflow_type=desc.workflow_type,
            status=str(desc.status.name) if desc.status else "unknown",
            start_time=desc.start_time,
            close_time=desc.close_time,
            task_queue=desc.task_queue,
        )

    @mcp.tool()
    async def get_workflow_history(
        workflow_id: str,
        run_id: str | None = None,
        limit: int = 50,
    ) -> WorkflowHistoryResult:
        """
        Get the event history of a workflow execution.

        Args:
            workflow_id: The workflow ID
            run_id: Optional run ID (uses latest if not specified)
            limit: Maximum number of events to return (default: 50)

        Returns:
            Workflow event history
        """
        client = _get_client_or_error()
        handle = client.get_workflow_handle(workflow_id, run_id=run_id)

        events = []
        async for event in handle.fetch_history_events():
            events.append(
                {
                    "event_id": event.event_id,
                    "event_type": event.event_type.name,
                    "timestamp": event.event_time.ToDatetime() if event.event_time else None,
                }
            )
            if len(events) >= limit:
                break

        return WorkflowHistoryResult(
            workflow_id=workflow_id,
            run_id=run_id,
            events=events,
            count=len(events),
        )

    @mcp.tool()
    async def start_workflow(
        workflow_type: str,
        workflow_id: str,
        task_queue: str,
        args: list[Any] | None = None,
        execution_timeout_seconds: int | None = None,
    ) -> WorkflowResult:
        """
        Start a new workflow execution.

        Args:
            workflow_type: The workflow type/name to execute
            workflow_id: Unique ID for this workflow execution
            task_queue: The task queue to use
            args: Optional arguments to pass to the workflow
            execution_timeout_seconds: Optional timeout for the entire workflow

        Returns:
            Information about the started workflow
        """
        client = _get_client_or_error()

        execution_timeout = None
        if execution_timeout_seconds:
            execution_timeout = timedelta(seconds=execution_timeout_seconds)

        handle = await client.start_workflow(
            workflow_type,
            args or [],
            id=workflow_id,
            task_queue=task_queue,
            execution_timeout=execution_timeout,
        )

        desc = await handle.describe()
        return WorkflowResult(
            workflow_id=desc.id,
            run_id=desc.run_id,
            workflow_type=desc.workflow_type,
            status=str(desc.status.name) if desc.status else "unknown",
            start_time=desc.start_time,
            close_time=desc.close_time,
            task_queue=desc.task_queue,
        )

    @mcp.tool()
    async def signal_workflow(
        workflow_id: str,
        signal_name: str,
        args: list[Any] | None = None,
        run_id: str | None = None,
    ) -> dict[str, str]:
        """
        Send a signal to a running workflow.

        Args:
            workflow_id: The workflow ID
            signal_name: Name of the signal to send
            args: Optional arguments for the signal
            run_id: Optional run ID (uses latest if not specified)

        Returns:
            Confirmation of signal sent
        """
        client = _get_client_or_error()
        handle = client.get_workflow_handle(workflow_id, run_id=run_id)
        await handle.signal(signal_name, args or [])

        return {
            "status": "signal_sent",
            "workflow_id": workflow_id,
            "signal_name": signal_name,
        }

    @mcp.tool()
    async def query_workflow(
        workflow_id: str,
        query_name: str,
        args: list[Any] | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Query a workflow for its current state.

        Args:
            workflow_id: The workflow ID
            query_name: Name of the query to execute
            args: Optional arguments for the query
            run_id: Optional run ID (uses latest if not specified)

        Returns:
            Query result from the workflow
        """
        client = _get_client_or_error()
        handle = client.get_workflow_handle(workflow_id, run_id=run_id)
        result = await handle.query(query_name, args or [])

        return {
            "workflow_id": workflow_id,
            "query_name": query_name,
            "result": result,
        }

    @mcp.tool()
    async def cancel_workflow(
        workflow_id: str,
        run_id: str | None = None,
    ) -> dict[str, str]:
        """
        Request cancellation of a running workflow.

        Args:
            workflow_id: The workflow ID
            run_id: Optional run ID (uses latest if not specified)

        Returns:
            Confirmation of cancellation request
        """
        client = _get_client_or_error()
        handle = client.get_workflow_handle(workflow_id, run_id=run_id)
        await handle.cancel()

        return {
            "status": "cancellation_requested",
            "workflow_id": workflow_id,
        }

    @mcp.tool()
    async def terminate_workflow(
        workflow_id: str,
        reason: str | None = None,
        run_id: str | None = None,
    ) -> dict[str, str]:
        """
        Forcefully terminate a running workflow.

        Args:
            workflow_id: The workflow ID
            reason: Optional reason for termination
            run_id: Optional run ID (uses latest if not specified)

        Returns:
            Confirmation of termination
        """
        client = _get_client_or_error()
        handle = client.get_workflow_handle(workflow_id, run_id=run_id)
        await handle.terminate(reason=reason)

        return {
            "status": "terminated",
            "workflow_id": workflow_id,
            "reason": reason,
        }

    # =========================================================================
    # Schedule Management Tools
    # =========================================================================

    @mcp.tool()
    async def list_schedules(
        limit: int = 20,
    ) -> SchedulesResult:
        """
        List all schedules in the namespace.

        Args:
            limit: Maximum number of schedules to return (default: 20)

        Returns:
            List of schedules
        """
        client = _get_client_or_error()
        limit = min(limit, 100)

        schedules = []
        async for schedule in client.list_schedules():
            schedules.append(
                ScheduleInfo(
                    schedule_id=schedule.id,
                    workflow_type=schedule.info.workflow_type if schedule.info else None,
                    paused=schedule.info.paused if schedule.info else False,
                    recent_actions=schedule.info.num_actions if schedule.info else 0,
                )
            )
            if len(schedules) >= limit:
                break

        return SchedulesResult(
            schedules=schedules,
            count=len(schedules),
        )

    @mcp.tool()
    async def pause_schedule(
        schedule_id: str,
        note: str | None = None,
    ) -> ScheduleResult:
        """
        Pause a schedule.

        Args:
            schedule_id: The schedule ID
            note: Optional note explaining why it was paused

        Returns:
            Confirmation of pause
        """
        client = _get_client_or_error()
        handle = client.get_schedule_handle(schedule_id)
        await handle.pause(note=note)

        return ScheduleResult(
            schedule_id=schedule_id,
            action="paused",
            note=note,
        )

    @mcp.tool()
    async def unpause_schedule(
        schedule_id: str,
        note: str | None = None,
    ) -> ScheduleResult:
        """
        Unpause a schedule.

        Args:
            schedule_id: The schedule ID
            note: Optional note explaining why it was unpaused

        Returns:
            Confirmation of unpause
        """
        client = _get_client_or_error()
        handle = client.get_schedule_handle(schedule_id)
        await handle.unpause(note=note)

        return ScheduleResult(
            schedule_id=schedule_id,
            action="unpaused",
            note=note,
        )

    @mcp.tool()
    async def trigger_schedule(
        schedule_id: str,
    ) -> ScheduleResult:
        """
        Trigger a schedule to run immediately.

        Args:
            schedule_id: The schedule ID

        Returns:
            Confirmation of trigger
        """
        client = _get_client_or_error()
        handle = client.get_schedule_handle(schedule_id)
        await handle.trigger()

        return ScheduleResult(
            schedule_id=schedule_id,
            action="triggered",
        )

    # =========================================================================
    # Debugging Tools
    # =========================================================================

    @mcp.tool()
    async def get_workflow_result(
        workflow_id: str,
        run_id: str | None = None,
        timeout_seconds: int = 30,
    ) -> dict[str, Any]:
        """
        Wait for and get the result of a workflow execution.

        Args:
            workflow_id: The workflow ID
            run_id: Optional run ID (uses latest if not specified)
            timeout_seconds: Maximum time to wait for result (default: 30)

        Returns:
            The workflow result
        """
        import asyncio

        client = _get_client_or_error()
        handle = client.get_workflow_handle(workflow_id, run_id=run_id)

        try:
            result = await asyncio.wait_for(
                handle.result(),
                timeout=timeout_seconds,
            )
            return {
                "workflow_id": workflow_id,
                "status": "completed",
                "result": result,
            }
        except TimeoutError:
            return {
                "workflow_id": workflow_id,
                "status": "timeout",
                "message": f"Workflow did not complete within {timeout_seconds} seconds",
            }
        except Exception as e:
            return {
                "workflow_id": workflow_id,
                "status": "error",
                "error": str(e),
            }

    @mcp.tool()
    async def get_worker_task_queues() -> dict[str, Any]:
        """
        Get information about task queues and their workers.

        Returns:
            Information about active task queues
        """
        client = _get_client_or_error()

        # Note: This requires additional setup to track task queues
        # For now, return basic info
        return {
            "namespace": client.namespace,
            "note": "Use list_workflows to see active task queues from running workflows",
        }

    return mcp


async def main():
    """Main entry point for the Temporal MCP server."""
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        await connect_temporal()
        server = create_server()

        transport = os.environ.get("MCP_TRANSPORT", "stdio")
        if transport == "stdio":
            from mcp.server.stdio import stdio_server

            async with stdio_server() as (read_stream, write_stream):
                await server.run(
                    read_stream,
                    write_stream,
                    server.create_initialization_options(),
                )
        elif transport == "sse":
            server.settings.host = os.environ.get("MCP_HOST", "0.0.0.0")
            server.settings.port = int(os.environ.get("MCP_PORT", "8080"))
            await server.run_sse_async()
        else:
            logger.error(f"Unknown transport: {transport}")
            sys.exit(1)
    finally:
        await disconnect_temporal()


def run():
    """Synchronous entry point for the Temporal MCP server."""
    import asyncio

    asyncio.run(main())


if __name__ == "__main__":
    run()
