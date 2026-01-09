"""
Hybrid Workflow-Agent Architecture for Kubani.

Provides support for combining deterministic workflows with AI agent
decision points using Strands Graph (when available) or a compatible
implementation.

Key concepts:
- Deterministic nodes: Fixed logic that always executes the same way
- Agent nodes: AI-powered decision points that can adapt
- Conditional edges: Route based on node outputs
- Parallel execution: Run independent nodes concurrently

Usage:
    from core_agents.workflows import WorkflowBuilder, NodeType

    # Create a workflow
    workflow = (
        WorkflowBuilder("incident-response")
        .add_node("classify", NodeType.AGENT, classifier_agent)
        .add_node("notify", NodeType.DETERMINISTIC, send_notification)
        .add_node("remediate", NodeType.AGENT, healer_agent)
        .add_edge("classify", "notify")
        .add_edge("notify", "remediate", condition=lambda x: x["severity"] == "high")
        .build()
    )

    # Execute
    result = await workflow.execute({"incident": incident_data})
"""

from core_agents.workflows.builder import (
    WorkflowBuilder,
    NodeType,
    WorkflowNode,
    WorkflowEdge,
)
from core_agents.workflows.executor import WorkflowExecutor
from core_agents.workflows.graph import WorkflowGraph

__all__ = [
    "WorkflowBuilder",
    "WorkflowExecutor",
    "WorkflowGraph",
    "NodeType",
    "WorkflowNode",
    "WorkflowEdge",
]
