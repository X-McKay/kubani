"""
Workflow Executor - Executes workflow graphs.

Handles the runtime execution of workflows including:
- Sequential and parallel node execution
- Error handling and retries
- State management
- Observability integration
"""

import asyncio
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from core_agents.workflows.builder import NodeType, WorkflowDefinition
from core_agents.workflows.graph import (
    NodeExecution,
    WorkflowExecution,
    WorkflowGraph,
)

logger = logging.getLogger(__name__)


class ExecutionContext:
    """Context passed through workflow execution."""

    def __init__(
        self,
        execution_id: str,
        input_data: dict[str, Any],
    ):
        self.execution_id = execution_id
        self.input_data = input_data
        self.state: dict[str, Any] = {}
        self.node_outputs: dict[str, Any] = {}

    def get_node_output(self, node_id: str) -> dict[str, Any] | None:
        """Get output from a previously executed node."""
        return self.node_outputs.get(node_id)

    def set_node_output(self, node_id: str, output: dict[str, Any]) -> None:
        """Store output from a node."""
        self.node_outputs[node_id] = output

    def get_state(self, key: str, default: Any = None) -> Any:
        """Get a value from execution state."""
        return self.state.get(key, default)

    def set_state(self, key: str, value: Any) -> None:
        """Set a value in execution state."""
        self.state[key] = value


class WorkflowExecutor:
    """
    Executes workflow graphs.

    Supports:
    - Sequential execution
    - Parallel execution of independent nodes
    - Conditional branching
    - Error handling and retries
    - Execution tracing
    """

    def __init__(
        self,
        graph: WorkflowGraph,
        on_node_start: Callable[[str, dict], None] | None = None,
        on_node_complete: Callable[[str, dict], None] | None = None,
        on_node_error: Callable[[str, Exception], None] | None = None,
    ):
        """
        Initialize the executor.

        Args:
            graph: The workflow graph to execute
            on_node_start: Callback when a node starts
            on_node_complete: Callback when a node completes
            on_node_error: Callback when a node errors
        """
        self.graph = graph
        self.on_node_start = on_node_start
        self.on_node_complete = on_node_complete
        self.on_node_error = on_node_error

    async def execute(
        self,
        input_data: dict[str, Any],
        execution_id: str | None = None,
    ) -> WorkflowExecution:
        """
        Execute the workflow.

        Args:
            input_data: Input data for the workflow
            execution_id: Optional execution ID (generated if not provided)

        Returns:
            WorkflowExecution with results
        """
        execution_id = execution_id or str(uuid.uuid4())

        execution = WorkflowExecution(
            workflow_name=self.graph.name,
            execution_id=execution_id,
            started_at=datetime.now(UTC),
            input_data=input_data,
        )

        context = ExecutionContext(execution_id, input_data)

        logger.info(f"Starting workflow {self.graph.name} (id={execution_id})")

        try:
            # Start from entry node
            entry_node = self.graph.get_entry_node()
            await self._execute_node(entry_node.id, context, execution)

            execution.status = "completed"
            execution.output_data = context.node_outputs

        except Exception as e:
            logger.error(f"Workflow {self.graph.name} failed: {e}")
            execution.status = "failed"
            execution.error = str(e)

        finally:
            execution.completed_at = datetime.now(UTC)

        logger.info(
            f"Workflow {self.graph.name} {execution.status} "
            f"(duration={(execution.completed_at - execution.started_at).total_seconds():.2f}s)"
        )

        return execution

    async def _execute_node(
        self,
        node_id: str,
        context: ExecutionContext,
        execution: WorkflowExecution,
    ) -> dict[str, Any]:
        """Execute a single node and its successors."""
        node = self.graph.get_node(node_id)
        if not node:
            raise ValueError(f"Node {node_id} not found")

        # Create execution record
        node_execution = NodeExecution(
            node_id=node_id,
            started_at=datetime.now(UTC),
            input_data=dict(context.node_outputs),
        )
        execution.node_executions.append(node_execution)

        # Notify start
        if self.on_node_start:
            self.on_node_start(node_id, context.node_outputs)

        logger.debug(f"Executing node {node_id} ({node.node_type.value})")

        # Execute with retries
        output = None
        last_error = None

        for attempt in range(node.retry_count + 1):
            try:
                output = await self._invoke_handler(node, context)
                break
            except Exception as e:
                last_error = e
                node_execution.retries = attempt + 1
                logger.warning(f"Node {node_id} attempt {attempt + 1} failed: {e}")

                if attempt < node.retry_count:
                    await asyncio.sleep(2**attempt)  # Exponential backoff

        if output is None and last_error:
            node_execution.status = "failed"
            node_execution.error = str(last_error)
            node_execution.completed_at = datetime.now(UTC)

            if self.on_node_error:
                self.on_node_error(node_id, last_error)

            raise last_error

        # Store output
        context.set_node_output(node_id, output or {})
        node_execution.output_data = output or {}
        node_execution.status = "completed"
        node_execution.completed_at = datetime.now(UTC)

        # Notify complete
        if self.on_node_complete:
            self.on_node_complete(node_id, output or {})

        # Check if exit node
        if self.graph.is_exit_node(node_id):
            return output or {}

        # Get next nodes
        next_nodes = self.graph.get_next_nodes(node_id, output or {})

        if not next_nodes:
            return output or {}

        # Execute next nodes
        if len(next_nodes) == 1:
            # Sequential execution
            return await self._execute_node(next_nodes[0].id, context, execution)
        else:
            # Parallel execution
            tasks = [self._execute_node(n.id, context, execution) for n in next_nodes]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Check for errors
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    raise result

            # Merge results
            merged = {}
            for result in results:
                if isinstance(result, dict):
                    merged.update(result)

            return merged

    async def _invoke_handler(
        self,
        node: Any,
        context: ExecutionContext,
    ) -> dict[str, Any]:
        """Invoke the node handler."""
        handler = node.handler

        # Prepare input
        input_data = {
            "context": context.input_data,
            "state": context.state,
            "previous_outputs": context.node_outputs,
        }

        # Handle different node types
        if node.node_type == NodeType.AGENT:
            # Agent nodes - invoke the agent
            if callable(handler):
                # Direct callable (agent)
                result = handler(str(input_data))
                if hasattr(result, "message"):
                    return {"response": result.message}
                return {"response": str(result)}
            else:
                raise ValueError(f"Invalid agent handler for node {node.id}")

        elif node.node_type == NodeType.DETERMINISTIC:
            # Deterministic nodes - call the function
            if asyncio.iscoroutinefunction(handler):
                return await handler(input_data)
            else:
                return handler(input_data)

        elif node.node_type == NodeType.PARALLEL:
            # Parallel nodes should be handled by the executor
            return input_data

        else:
            raise ValueError(f"Unknown node type: {node.node_type}")


async def execute_workflow(
    definition: WorkflowDefinition,
    input_data: dict[str, Any],
) -> WorkflowExecution:
    """
    Convenience function to execute a workflow.

    Args:
        definition: Workflow definition
        input_data: Input data

    Returns:
        WorkflowExecution with results
    """
    graph = WorkflowGraph(definition)
    executor = WorkflowExecutor(graph)
    return await executor.execute(input_data)
