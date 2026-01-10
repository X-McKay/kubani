"""
Workflow Builder - Fluent API for constructing workflows.

Provides a builder pattern for creating hybrid workflow-agent graphs
with type safety and validation.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class NodeType(Enum):
    """Type of workflow node."""

    DETERMINISTIC = "deterministic"  # Fixed logic, always same behavior
    AGENT = "agent"  # AI-powered, can adapt
    PARALLEL = "parallel"  # Executes child nodes in parallel
    CONDITIONAL = "conditional"  # Routes based on condition


@dataclass
class WorkflowNode:
    """A node in the workflow graph."""

    id: str
    name: str
    node_type: NodeType
    handler: Callable[..., Any]
    description: str = ""
    timeout_seconds: float = 60.0
    retry_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __hash__(self) -> int:
        return hash(self.id)


@dataclass
class WorkflowEdge:
    """An edge connecting two nodes."""

    source_id: str
    target_id: str
    condition: Callable[[dict], bool] | None = None
    priority: int = 0  # Higher priority edges evaluated first
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowDefinition:
    """Complete workflow definition."""

    name: str
    description: str
    nodes: dict[str, WorkflowNode]
    edges: list[WorkflowEdge]
    entry_node_id: str
    exit_node_ids: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)


class WorkflowBuilder:
    """
    Fluent builder for constructing workflows.

    Example:
        workflow = (
            WorkflowBuilder("my-workflow")
            .description("Handles incident response")
            .add_node("start", NodeType.DETERMINISTIC, start_handler)
            .add_node("classify", NodeType.AGENT, classifier)
            .add_node("remediate", NodeType.AGENT, healer)
            .add_edge("start", "classify")
            .add_edge("classify", "remediate", condition=is_actionable)
            .set_entry("start")
            .set_exit("remediate")
            .build()
        )
    """

    def __init__(self, name: str):
        """
        Initialize the workflow builder.

        Args:
            name: Unique name for this workflow
        """
        self._name = name
        self._description = ""
        self._nodes: dict[str, WorkflowNode] = {}
        self._edges: list[WorkflowEdge] = []
        self._entry_node_id: str | None = None
        self._exit_node_ids: list[str] = []
        self._metadata: dict[str, Any] = {}

    def description(self, desc: str) -> "WorkflowBuilder":
        """Set workflow description."""
        self._description = desc
        return self

    def metadata(self, key: str, value: Any) -> "WorkflowBuilder":
        """Add metadata to the workflow."""
        self._metadata[key] = value
        return self

    def add_node(
        self,
        node_id: str,
        node_type: NodeType,
        handler: Callable[..., Any],
        name: str | None = None,
        description: str = "",
        timeout: float = 60.0,
        retries: int = 0,
        **metadata: Any,
    ) -> "WorkflowBuilder":
        """
        Add a node to the workflow.

        Args:
            node_id: Unique identifier for this node
            node_type: Type of node (DETERMINISTIC, AGENT, etc.)
            handler: Function or agent to execute
            name: Human-readable name (defaults to node_id)
            description: Description of what this node does
            timeout: Execution timeout in seconds
            retries: Number of retry attempts on failure
            **metadata: Additional metadata

        Returns:
            Self for chaining
        """
        if node_id in self._nodes:
            raise ValueError(f"Node {node_id} already exists")

        self._nodes[node_id] = WorkflowNode(
            id=node_id,
            name=name or node_id,
            node_type=node_type,
            handler=handler,
            description=description,
            timeout_seconds=timeout,
            retry_count=retries,
            metadata=metadata,
        )

        # First node becomes entry by default
        if self._entry_node_id is None:
            self._entry_node_id = node_id

        return self

    def add_agent_node(
        self,
        node_id: str,
        agent: Any,
        name: str | None = None,
        description: str = "",
        timeout: float = 120.0,
        **metadata: Any,
    ) -> "WorkflowBuilder":
        """
        Convenience method to add an agent node.

        Args:
            node_id: Unique identifier
            agent: The agent instance
            name: Human-readable name
            description: Node description
            timeout: Execution timeout
            **metadata: Additional metadata

        Returns:
            Self for chaining
        """
        return self.add_node(
            node_id=node_id,
            node_type=NodeType.AGENT,
            handler=agent,
            name=name,
            description=description,
            timeout=timeout,
            **metadata,
        )

    def add_deterministic_node(
        self,
        node_id: str,
        handler: Callable[..., Any],
        name: str | None = None,
        description: str = "",
        **metadata: Any,
    ) -> "WorkflowBuilder":
        """
        Convenience method to add a deterministic node.

        Args:
            node_id: Unique identifier
            handler: Function to execute
            name: Human-readable name
            description: Node description
            **metadata: Additional metadata

        Returns:
            Self for chaining
        """
        return self.add_node(
            node_id=node_id,
            node_type=NodeType.DETERMINISTIC,
            handler=handler,
            name=name,
            description=description,
            **metadata,
        )

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        condition: Callable[[dict], bool] | None = None,
        priority: int = 0,
        **metadata: Any,
    ) -> "WorkflowBuilder":
        """
        Add an edge between nodes.

        Args:
            source_id: Source node ID
            target_id: Target node ID
            condition: Optional condition function (receives node output)
            priority: Edge priority (higher = evaluated first)
            **metadata: Additional metadata

        Returns:
            Self for chaining
        """
        self._edges.append(
            WorkflowEdge(
                source_id=source_id,
                target_id=target_id,
                condition=condition,
                priority=priority,
                metadata=metadata,
            )
        )
        return self

    def add_conditional_edges(
        self,
        source_id: str,
        conditions: dict[str, Callable[[dict], bool]],
        default: str | None = None,
    ) -> "WorkflowBuilder":
        """
        Add multiple conditional edges from a source node.

        Args:
            source_id: Source node ID
            conditions: Dict mapping target_id to condition function
            default: Default target if no conditions match

        Returns:
            Self for chaining
        """
        priority = len(conditions)
        for target_id, condition in conditions.items():
            self.add_edge(source_id, target_id, condition=condition, priority=priority)
            priority -= 1

        if default:
            self.add_edge(source_id, default, priority=0)

        return self

    def set_entry(self, node_id: str) -> "WorkflowBuilder":
        """Set the entry node."""
        if node_id not in self._nodes:
            raise ValueError(f"Node {node_id} not found")
        self._entry_node_id = node_id
        return self

    def set_exit(self, *node_ids: str) -> "WorkflowBuilder":
        """Set exit node(s)."""
        for node_id in node_ids:
            if node_id not in self._nodes:
                raise ValueError(f"Node {node_id} not found")
            if node_id not in self._exit_node_ids:
                self._exit_node_ids.append(node_id)
        return self

    def validate(self) -> list[str]:
        """
        Validate the workflow definition.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Check entry node
        if not self._entry_node_id:
            errors.append("No entry node defined")
        elif self._entry_node_id not in self._nodes:
            errors.append(f"Entry node {self._entry_node_id} not found")

        # Check exit nodes
        if not self._exit_node_ids:
            # Auto-detect exit nodes (nodes with no outgoing edges)
            nodes_with_outgoing = {e.source_id for e in self._edges}
            self._exit_node_ids = [n for n in self._nodes if n not in nodes_with_outgoing]

        # Check edge references
        for edge in self._edges:
            if edge.source_id not in self._nodes:
                errors.append(f"Edge source {edge.source_id} not found")
            if edge.target_id not in self._nodes:
                errors.append(f"Edge target {edge.target_id} not found")

        # Check for unreachable nodes
        reachable = {self._entry_node_id}
        changed = True
        while changed:
            changed = False
            for edge in self._edges:
                if edge.source_id in reachable and edge.target_id not in reachable:
                    reachable.add(edge.target_id)
                    changed = True

        unreachable = set(self._nodes.keys()) - reachable
        if unreachable:
            errors.append(f"Unreachable nodes: {unreachable}")

        return errors

    def build(self) -> "WorkflowDefinition":
        """
        Build the workflow definition.

        Returns:
            WorkflowDefinition ready for execution

        Raises:
            ValueError: If validation fails
        """
        errors = self.validate()
        if errors:
            raise ValueError(f"Workflow validation failed: {errors}")

        return WorkflowDefinition(
            name=self._name,
            description=self._description,
            nodes=self._nodes,
            edges=self._edges,
            entry_node_id=self._entry_node_id,
            exit_node_ids=self._exit_node_ids,
            metadata=self._metadata,
        )
