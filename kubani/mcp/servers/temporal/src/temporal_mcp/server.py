"""
Temporal MCP Server implementation.

Provides MCP tools for interacting with Temporal workflows and activities.
Enables agents and Claude Code to manage, monitor, and debug Temporal workflows.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any

from kubani.framework.mcp.server.health import HealthCheckManager
from kubani.framework.mcp.server.metrics import MetricsCollector
from kubani.framework.mcp.server.registry import RegistryClient
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

# Global framework components
_health_manager: HealthCheckManager | None = None
_metrics_collector: MetricsCollector | None = None
_registry_client: RegistryClient | None = None
_heartbeat_task: asyncio.Task | None = None


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
    global _health_manager, _metrics_collector, _registry_client, _heartbeat_task

    # Initialize framework components
    _health_manager = HealthCheckManager(version="1.0.0")
    _metrics_collector = MetricsCollector(server_name="temporal-mcp")

    # Register health check for Temporal server
    async def check_temporal_server():
        """Check if Temporal server is accessible."""
        try:
            client = _get_client_or_error()
            # Try to list workflows as a health check
            count = 0
            async for _ in client.list_workflows():
                count += 1
                if count >= 1:  # Just check if we can list at least one
                    break
            return True
        except Exception:
            return False

    _health_manager.register("temporal_server", check_temporal_server, timeout=5.0)

    # Register with registry if URL provided
    registry_url = os.environ.get("REGISTRY_URL")
    if registry_url:
        _registry_client = RegistryClient(
            registry_url=registry_url,
            server_id="temporal-mcp",
        )

        # Get connection config from environment
        external_url = os.environ.get("EXTERNAL_URL", "http://temporal-mcp.almckay.io/sse")
        internal_url = os.environ.get(
            "INTERNAL_URL", "http://temporal-mcp-server.ai-agents.svc:8080/sse"
        )

        # Get tool names for capabilities
        capabilities = [
            "list_workflows",
            "get_workflow",
            "get_workflow_history",
            "start_workflow",
            "signal_workflow",
            "query_workflow",
            "cancel_workflow",
            "terminate_workflow",
            "list_schedules",
            "pause_schedule",
            "unpause_schedule",
            "trigger_schedule",
            "get_workflow_result",
            "get_worker_task_queues",
        ]

        await _registry_client.register(
            name="Temporal MCP Server",
            description="Temporal workflow orchestration for AI agents",
            transport="sse",
            connection_config={
                "url": external_url,
                "internal_url": internal_url,
            },
            capabilities=capabilities,
        )

        # Start heartbeat task
        async def get_backend_status():
            health = await _health_manager.check_all()
            return {name: backend.status.value for name, backend in health.backends.items()}

        _heartbeat_task = asyncio.create_task(
            _registry_client.start_heartbeat(interval=30, get_backend_status=get_backend_status)
        )

    yield

    # Cleanup
    if _heartbeat_task:
        _heartbeat_task.cancel()
        try:
            await _heartbeat_task
        except asyncio.CancelledError:
            pass

    if _registry_client:
        await _registry_client.unregister()


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

        if _metrics_collector:
            with _metrics_collector.track_request("list_workflows"):
                with _metrics_collector.track_backend("temporal_server"):
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
        else:
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
            # Resolve event_type to a readable name
            event_type = event.event_type
            if hasattr(event_type, "name"):
                event_type_str = event_type.name
            else:
                # Protobuf enum as int — resolve via EventType descriptor
                from temporalio.api.enums.v1 import EventType

                try:
                    event_type_str = EventType.Name(event_type)
                except ValueError:
                    event_type_str = str(event_type)
            events.append(
                {
                    "event_id": event.event_id,
                    "event_type": event_type_str,
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
        async for schedule in await client.list_schedules():
            workflow_type = None
            if schedule.schedule and schedule.schedule.action:
                action = schedule.schedule.action
                workflow_type = getattr(action, "workflow", None)
            paused = False
            if schedule.schedule and schedule.schedule.state:
                paused = schedule.schedule.state.paused
            recent_actions = len(schedule.info.recent_actions) if schedule.info else 0
            next_action_time = None
            if schedule.info and schedule.info.next_action_times:
                next_action_time = schedule.info.next_action_times[0]

            schedules.append(
                ScheduleInfo(
                    schedule_id=schedule.id,
                    workflow_type=workflow_type,
                    paused=paused,
                    recent_actions=recent_actions,
                    next_action_time=next_action_time,
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

    # =========================================================================
    # Health and Metrics Tools
    # =========================================================================

    @mcp.tool()
    async def health() -> dict[str, Any]:
        """
        Check the health of the Temporal MCP server.

        Returns:
            Health status including Temporal server connectivity
        """
        if _health_manager:
            health_response = await _health_manager.check_all()
            return health_response.to_dict()

        # Fallback if health manager not initialized
        try:
            client = _get_client_or_error()
            return {
                "status": "healthy",
                "namespace": client.namespace,
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
            }

    @mcp.tool()
    async def metrics() -> dict[str, Any]:
        """
        Get Prometheus metrics for the Temporal MCP server.

        Returns:
            Metrics in Prometheus format
        """
        if _metrics_collector:
            metrics_data = _metrics_collector.get_metrics()
            return {
                "content_type": "text/plain; version=0.0.4",
                "body": metrics_data.decode("utf-8"),
            }
        return {
            "error": "Metrics collector not initialized",
        }

    return mcp


def main():
    """Entry point for the Temporal MCP server."""
    import sys

    import anyio
    from kubani.framework.mcp.server.transport import TransportConfig, run_server_async

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr,
    )

    # Parse transport config from args
    config = TransportConfig.from_args()

    # Create the server
    mcp = create_server()

    # Run with connection management
    async def run_with_temporal():
        try:
            await connect_temporal()
            await run_server_async(mcp, config)
        finally:
            await disconnect_temporal()

    anyio.run(run_with_temporal)


# Alias for backward compatibility
run = main


if __name__ == "__main__":
    run()
