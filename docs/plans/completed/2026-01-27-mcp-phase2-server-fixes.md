# Phase 2: Server Fixes & Standardization

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Update all 5 MCP servers to use `kubani.framework.mcp.server`, fix inconsistencies, and add missing registry entries.

**Architecture:** Each server inherits from `MCPServerBase`, uses standardized transport handling, and is registered in the MCP registry.

**Tech Stack:** Python 3.11+, kubani-framework, FastMCP

**Prerequisites:** Complete Phase 1 (kubani/framework/mcp/server/ module exists)

---

## Task 1: Add Framework Dependency to All Servers

**Files:**
- Modify: `kubani/mcp/servers/discord/pyproject.toml`
- Modify: `kubani/mcp/servers/temporal/pyproject.toml`
- Modify: `kubani/mcp/servers/qdrant/pyproject.toml`
- Modify: `kubani/mcp/servers/memory/pyproject.toml`
- Modify: `kubani/mcp/servers/skills/pyproject.toml`

**Step 1: Update discord/pyproject.toml**

Add to dependencies:
```toml
dependencies = [
    "mcp>=1.0.0",
    "discord.py>=2.3.0",
    "pydantic>=2.0.0",
    "kubani-framework",  # ADD THIS LINE
]
```

**Step 2: Update temporal/pyproject.toml**

Add to dependencies:
```toml
dependencies = [
    "mcp>=1.0.0",
    "temporalio>=1.7.0",
    "pydantic>=2.0.0",
    "kubani-framework",  # ADD THIS LINE
]
```

**Step 3: Update qdrant/pyproject.toml**

Add to dependencies:
```toml
dependencies = [
    "mcp>=1.0.0",
    "qdrant-client>=1.9.0",
    "pydantic>=2.0.0",
    "kubani-framework",  # ADD THIS LINE
]
```

**Step 4: Update memory/pyproject.toml**

Add to dependencies:
```toml
dependencies = [
    "mcp>=1.0.0",
    "qdrant-client>=1.9.0",
    "neo4j>=5.0.0",
    "redis>=5.0.0",
    "httpx>=0.27.0",
    "pydantic>=2.0.0",
    "kubani-framework",  # ADD THIS LINE
]
```

**Step 5: Update skills/pyproject.toml**

Add to dependencies:
```toml
dependencies = [
    "mcp>=1.0.0",
    "pydantic>=2.0.0",
    "pyyaml>=6.0.0",
    "python-frontmatter>=1.0.0",
    "microsandbox>=0.1.0",
    "kubani-framework",  # ADD THIS LINE
]
```

**Step 6: Commit**

```bash
git add kubani/mcp/servers/*/pyproject.toml
git commit -m "chore(mcp): add kubani-framework dependency to all servers

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Standardize Discord Server

**Files:**
- Modify: `kubani/mcp/servers/discord/src/discord_mcp/server.py`
- Modify: `kubani/mcp/servers/discord/src/discord_mcp/__init__.py`

**Step 1: Refactor server.py to use MCPServerBase pattern**

The Discord server is the most mature. We'll keep most tools but standardize the entry point.

Replace the `main()` function at the end of `server.py`:

```python
# Replace everything from line 708 to end with:

def main():
    """Entry point for the Discord MCP server."""
    import sys

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
    async def run_with_discord():
        try:
            await connect_discord()
            await run_server_async(mcp, config)
        finally:
            await disconnect_discord()

    import anyio
    anyio.run(run_with_discord)


if __name__ == "__main__":
    main()
```

Note: Discord server keeps its current structure because it has complex connection management. We use the transport utilities for consistency but don't inherit from MCPServerBase since it manages a persistent Discord client differently.

**Step 2: Verify tests still pass**

```bash
cd kubani/mcp/servers/discord && uv run pytest -v
```

**Step 3: Commit**

```bash
git add kubani/mcp/servers/discord/
git commit -m "refactor(mcp): standardize Discord server transport handling

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Refactor Temporal Server to Use Base Class

**Files:**
- Modify: `kubani/mcp/servers/temporal/src/temporal_mcp/server.py`
- Modify: `kubani/mcp/servers/temporal/src/temporal_mcp/__init__.py`

**Step 1: Rewrite server.py using MCPServerBase**

Replace entire file with:

```python
"""
Temporal MCP Server implementation.

Provides MCP tools for interacting with Temporal workflows and activities.
Enables agents and Claude Code to manage, monitor, and debug Temporal workflows.
"""

import logging
import os
from datetime import timedelta
from typing import Any

from mcp.server.fastmcp import FastMCP

from kubani.framework.mcp.server import MCPServerBase, TransportConfig
from kubani.framework.mcp.server.transport import run_server_async

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


class TemporalMCPServer(MCPServerBase):
    """Temporal MCP Server providing workflow management tools."""

    name = "Temporal MCP Server"
    description = (
        "Temporal workflow orchestration for AI agents. "
        "Use these tools to start, query, signal, and manage Temporal workflows. "
        "Useful for long-running tasks, scheduled jobs, and distributed processing."
    )

    def __init__(self):
        super().__init__()
        self._client: Client | None = None

    @property
    def client(self) -> Client:
        """Get the Temporal client, ensuring connected."""
        self.ensure_connected()
        if self._client is None:
            raise RuntimeError("Client not initialized")
        return self._client

    async def connect_backend(self) -> None:
        """Connect to Temporal server."""
        host = os.environ.get("TEMPORAL_HOST", "localhost")
        port = int(os.environ.get("TEMPORAL_PORT", "7233"))
        namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")

        logger.info(f"Connecting to Temporal at {host}:{port} (namespace: {namespace})...")
        self._client = await Client.connect(
            f"{host}:{port}",
            namespace=namespace,
        )
        logger.info("Temporal client connected")

    async def disconnect_backend(self) -> None:
        """Disconnect from Temporal (client doesn't require explicit disconnect)."""
        self._client = None

    def register_tools(self, mcp: FastMCP) -> None:
        """Register Temporal workflow management tools."""

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
            async for workflow in self.client.list_workflows(query=full_query):
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
            handle = self.client.get_workflow_handle(workflow_id, run_id=run_id)
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
            handle = self.client.get_workflow_handle(workflow_id, run_id=run_id)

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
            execution_timeout = None
            if execution_timeout_seconds:
                execution_timeout = timedelta(seconds=execution_timeout_seconds)

            handle = await self.client.start_workflow(
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
            handle = self.client.get_workflow_handle(workflow_id, run_id=run_id)
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
            handle = self.client.get_workflow_handle(workflow_id, run_id=run_id)
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
            handle = self.client.get_workflow_handle(workflow_id, run_id=run_id)
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
            handle = self.client.get_workflow_handle(workflow_id, run_id=run_id)
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
            limit = min(limit, 100)

            schedules = []
            async for schedule in self.client.list_schedules():
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
            handle = self.client.get_schedule_handle(schedule_id)
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
            handle = self.client.get_schedule_handle(schedule_id)
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
            handle = self.client.get_schedule_handle(schedule_id)
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

            handle = self.client.get_workflow_handle(workflow_id, run_id=run_id)

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
            return {
                "namespace": self.client.namespace,
                "note": "Use list_workflows to see active task queues from running workflows",
            }


# Factory function for backward compatibility
def create_server() -> FastMCP:
    """Create and configure the Temporal MCP server."""
    server = TemporalMCPServer()
    return server.create_server()


def main():
    """Entry point for the Temporal MCP server."""
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr,
    )

    server = TemporalMCPServer()
    mcp = server.create_server()
    config = TransportConfig.from_args()

    async def run_with_temporal():
        try:
            await server.startup()
            await run_server_async(mcp, config)
        finally:
            await server.shutdown()

    import anyio
    anyio.run(run_with_temporal)


# Alias for backward compatibility
run = main


if __name__ == "__main__":
    main()
```

**Step 2: Update __init__.py**

```python
"""
Temporal MCP Server.

Provides MCP tools for managing Temporal workflows and schedules.
"""

from temporal_mcp.models import (
    ActivityResult,
    ScheduleInfo,
    ScheduleResult,
    SchedulesResult,
    WorkflowHistoryResult,
    WorkflowResult,
    WorkflowsResult,
)
from temporal_mcp.server import TemporalMCPServer, create_server, main

__all__ = [
    "TemporalMCPServer",
    "create_server",
    "main",
    "ActivityResult",
    "ScheduleInfo",
    "ScheduleResult",
    "SchedulesResult",
    "WorkflowHistoryResult",
    "WorkflowResult",
    "WorkflowsResult",
]
```

**Step 3: Commit**

```bash
git add kubani/mcp/servers/temporal/
git commit -m "refactor(mcp): standardize Temporal server with MCPServerBase

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Refactor Qdrant Server (Similar Pattern)

**Files:**
- Modify: `kubani/mcp/servers/qdrant/src/qdrant_mcp/server.py`

**Step 1: Refactor to use MCPServerBase**

Apply same pattern as Temporal:
- Create `QdrantMCPServer(MCPServerBase)` class
- Move tools to `register_tools()` method
- Use `self.client` property with `ensure_connected()`
- Standardize entry point with `TransportConfig`

The tools remain the same, just wrapped in the class structure.

**Step 2: Commit**

```bash
git add kubani/mcp/servers/qdrant/
git commit -m "refactor(mcp): standardize Qdrant server with MCPServerBase

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Refactor Memory Server (Similar Pattern)

**Files:**
- Modify: `kubani/mcp/servers/memory/src/memory_mcp/server.py`

**Step 1: Refactor to use MCPServerBase**

Memory server has 3 backends (Qdrant, Neo4j, Redis). Create:
- `MemoryMCPServer(MCPServerBase)` class
- Store all 3 backends as instance variables
- `connect_backend()` connects all 3
- `disconnect_backend()` disconnects all 3

Consider: Add `health_check()` override that checks all 3 backends.

**Step 2: Commit**

```bash
git add kubani/mcp/servers/memory/
git commit -m "refactor(mcp): standardize Memory server with MCPServerBase

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Refactor Skills Server (Similar Pattern)

**Files:**
- Modify: `kubani/mcp/servers/skills/src/skills_mcp/server.py`

**Step 1: Refactor to use MCPServerBase**

Skills server doesn't have a persistent connection but uses discovery + executor.
- `connect_backend()` initializes discovery and executor manager
- `disconnect_backend()` is a no-op

**Step 2: Commit**

```bash
git add kubani/mcp/servers/skills/
git commit -m "refactor(mcp): standardize Skills server with MCPServerBase

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Add Missing Servers to Registry

**Files:**
- Create: `kubani/mcp/registry/servers/temporal.json`
- Create: `kubani/mcp/registry/servers/qdrant.json`
- Create: `kubani/mcp/registry/servers/memory.json`
- Create: `kubani/mcp/registry/servers/skills.json`
- Modify: `kubani/mcp/registry/registry.json` (auto-generated)

**Step 1: Create temporal.json**

```json
{
  "name": "temporal-mcp-server",
  "description": "Temporal workflow orchestration - start, query, signal, and manage workflows",
  "transport": "sse",
  "url": "https://temporal-mcp.almckay.io/sse",
  "capabilities": [
    "workflows.list",
    "workflows.get",
    "workflows.start",
    "workflows.signal",
    "workflows.query",
    "workflows.cancel",
    "workflows.terminate",
    "schedules.list",
    "schedules.pause",
    "schedules.unpause",
    "schedules.trigger"
  ],
  "readOnly": false
}
```

**Step 2: Create qdrant.json**

```json
{
  "name": "qdrant-mcp-server",
  "description": "Vector database operations - search, store, and manage embeddings",
  "transport": "sse",
  "url": "https://qdrant-mcp.almckay.io/sse",
  "capabilities": [
    "collections.list",
    "collections.create",
    "collections.delete",
    "vectors.upsert",
    "vectors.search",
    "vectors.get",
    "vectors.delete"
  ],
  "readOnly": false
}
```

**Step 3: Create memory.json**

```json
{
  "name": "memory-mcp-server",
  "description": "Unified memory system - store and query learnings, knowledge, and relationships",
  "transport": "sse",
  "url": "https://memory-mcp.almckay.io/sse",
  "capabilities": [
    "learnings.store",
    "learnings.query",
    "knowledge.store",
    "knowledge.query",
    "knowledge.graph",
    "relationships.create",
    "relationships.get",
    "cache.get",
    "cache.set",
    "cache.delete",
    "articles.store",
    "articles.query",
    "trends.store",
    "trends.get"
  ],
  "readOnly": false
}
```

**Step 4: Create skills.json**

```json
{
  "name": "skills-mcp-server",
  "description": "Skill discovery and execution - list, get, and execute Kubani skills",
  "transport": "sse",
  "url": "https://skills-mcp.almckay.io/sse",
  "capabilities": [
    "skills.list",
    "skills.get",
    "skills.execute",
    "skills.refresh"
  ],
  "readOnly": false
}
```

**Step 5: Regenerate registry.json**

```bash
cd infrastructure/scripts && ./sync-mcp-registry.sh
```

**Step 6: Commit**

```bash
git add kubani/mcp/registry/
git commit -m "feat(mcp): add Temporal, Qdrant, Memory, Skills to registry

All 5 internal MCP servers are now registered with capabilities.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Update Policies for New Servers

**Files:**
- Modify: `kubani/mcp/registry/policies/default.json`
- Modify: `kubani/mcp/registry/policies/k8s-monitor.json`

**Step 1: Update default.json**

```json
{
  "allowedServers": [
    "kubernetes",
    "cloudflare-docs",
    "discord",
    "temporal",
    "qdrant",
    "memory",
    "skills"
  ],
  "requireApproval": [
    "pods.delete",
    "deployments.scale",
    "resources.delete",
    "channels.delete",
    "webhooks.delete",
    "workflows.terminate",
    "collections.delete"
  ],
  "auditLog": true
}
```

**Step 2: Update k8s-monitor.json**

```json
{
  "allowedServers": [
    "kubernetes",
    "discord",
    "temporal",
    "memory"
  ],
  "requireApproval": [
    "pods.delete",
    "channels.delete",
    "workflows.terminate"
  ],
  "auditLog": true,
  "namespaceRestrictions": {
    "deny": [
      "kube-system",
      "flux-system"
    ]
  }
}
```

**Step 3: Regenerate and commit**

```bash
cd infrastructure/scripts && ./sync-mcp-registry.sh
git add kubani/mcp/registry/
git commit -m "feat(mcp): update policies to include new servers

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Summary

Phase 2 standardizes all 5 MCP servers:

| Server | Before | After |
|--------|--------|-------|
| Discord | Custom main() | TransportConfig + managed lifecycle |
| Temporal | asyncio.run(main()) | MCPServerBase + TransportConfig |
| Qdrant | asyncio.run(main()) | MCPServerBase + TransportConfig |
| Memory | asyncio.run(main()) | MCPServerBase + TransportConfig |
| Skills | Custom main() | MCPServerBase + TransportConfig |

All servers are now:
- Using consistent entry points
- Registered in the MCP registry with capabilities
- Following the same connection lifecycle pattern

**Proceed to:** `2026-01-27-mcp-phase3-testing.md`
