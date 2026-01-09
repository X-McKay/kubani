"""
Workflow Graph - Runtime representation of a workflow.

Provides the graph structure and traversal logic for workflow execution.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any, Optional

from core_agents.workflows.builder import (
    WorkflowDefinition,
    WorkflowNode,
    WorkflowEdge,
    NodeType,
)

logger = logging.getLogger(__name__)


@dataclass
class NodeExecution:
    """Record of a node execution."""

    node_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: str = "running"  # running, completed, failed, skipped
    input_data: dict[str, Any] = field(default_factory=dict)
    output_data: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    retries: int = 0


@dataclass
class WorkflowExecution:
    """Record of a complete workflow execution."""

    workflow_name: str
    execution_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: str = "running"  # running, completed, failed
    node_executions: list[NodeExecution] = field(default_factory=list)
    input_data: dict[str, Any] = field(default_factory=dict)
    output_data: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class WorkflowGraph:
    """
    Runtime workflow graph.

    Manages the graph structure and provides traversal methods.
    """

    def __init__(self, definition: WorkflowDefinition):
        """
        Initialize from a workflow definition.

        Args:
            definition: The workflow definition to use
        """
        self.definition = definition
        self.name = definition.name

        # Build adjacency list
        self._outgoing: dict[str, list[WorkflowEdge]] = {}
        self._incoming: dict[str, list[WorkflowEdge]] = {}

        for node_id in definition.nodes:
            self._outgoing[node_id] = []
            self._incoming[node_id] = []

        for edge in definition.edges:
            self._outgoing[edge.source_id].append(edge)
            self._incoming[edge.target_id].append(edge)

        # Sort outgoing edges by priority (descending)
        for node_id in self._outgoing:
            self._outgoing[node_id].sort(key=lambda e: -e.priority)

    def get_node(self, node_id: str) -> Optional[WorkflowNode]:
        """Get a node by ID."""
        return self.definition.nodes.get(node_id)

    def get_entry_node(self) -> WorkflowNode:
        """Get the entry node."""
        return self.definition.nodes[self.definition.entry_node_id]

    def is_exit_node(self, node_id: str) -> bool:
        """Check if a node is an exit node."""
        return node_id in self.definition.exit_node_ids

    def get_next_nodes(
        self,
        node_id: str,
        node_output: dict[str, Any],
    ) -> list[WorkflowNode]:
        """
        Get the next nodes to execute based on edge conditions.

        Args:
            node_id: Current node ID
            node_output: Output from the current node

        Returns:
            List of next nodes to execute
        """
        next_nodes = []

        for edge in self._outgoing.get(node_id, []):
            # Check condition if present
            if edge.condition is not None:
                try:
                    if not edge.condition(node_output):
                        continue
                except Exception as e:
                    logger.warning(f"Edge condition error: {e}")
                    continue

            target_node = self.get_node(edge.target_id)
            if target_node:
                next_nodes.append(target_node)

                # If this edge has no condition (default), stop checking
                if edge.condition is None:
                    break

        return next_nodes

    def get_parallel_nodes(self, node_id: str) -> list[WorkflowNode]:
        """
        Get nodes that can be executed in parallel from a given node.

        Returns nodes connected by unconditional edges.
        """
        parallel = []

        for edge in self._outgoing.get(node_id, []):
            if edge.condition is None:
                target = self.get_node(edge.target_id)
                if target:
                    parallel.append(target)

        return parallel

    def get_predecessors(self, node_id: str) -> list[WorkflowNode]:
        """Get all predecessor nodes."""
        return [
            self.get_node(edge.source_id)
            for edge in self._incoming.get(node_id, [])
            if self.get_node(edge.source_id)
        ]

    def get_successors(self, node_id: str) -> list[WorkflowNode]:
        """Get all successor nodes (ignoring conditions)."""
        return [
            self.get_node(edge.target_id)
            for edge in self._outgoing.get(node_id, [])
            if self.get_node(edge.target_id)
        ]

    def topological_sort(self) -> list[str]:
        """
        Get nodes in topological order.

        Returns:
            List of node IDs in execution order
        """
        in_degree = {node_id: 0 for node_id in self.definition.nodes}

        for edges in self._incoming.values():
            for edge in edges:
                in_degree[edge.target_id] = in_degree.get(edge.target_id, 0) + 1

        # Start with nodes that have no incoming edges
        queue = [node_id for node_id, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            node_id = queue.pop(0)
            result.append(node_id)

            for edge in self._outgoing.get(node_id, []):
                in_degree[edge.target_id] -= 1
                if in_degree[edge.target_id] == 0:
                    queue.append(edge.target_id)

        return result

    def to_mermaid(self) -> str:
        """
        Generate Mermaid diagram syntax for visualization.

        Returns:
            Mermaid flowchart syntax
        """
        lines = ["flowchart TD"]

        # Add nodes
        for node_id, node in self.definition.nodes.items():
            shape = {
                NodeType.DETERMINISTIC: f"[{node.name}]",
                NodeType.AGENT: f"({node.name})",
                NodeType.PARALLEL: f"[/{node.name}/]",
                NodeType.CONDITIONAL: f"{{{node.name}}}",
            }.get(node.node_type, f"[{node.name}]")

            lines.append(f"    {node_id}{shape}")

        # Add edges
        for edge in self.definition.edges:
            arrow = "-->" if edge.condition is None else "-.->|condition|"
            lines.append(f"    {edge.source_id} {arrow} {edge.target_id}")

        return "\n".join(lines)
