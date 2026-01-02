"""
Observability and monitoring for AI agents.

Provides unified hooks for tracking metrics, token usage,
tool calls, and agent performance.

Modules:
    hooks: Observability hooks and metrics aggregation
    metrics: Prometheus metrics for agents, skills, and events
"""

from core_agents.observability.hooks import (
    MetricsAggregator,
    ObservabilityHooks,
    RequestMetrics,
    TokenUsage,
    ToolCallMetric,
    create_observability_hooks,
)
from core_agents.observability.metrics import (
    get_metric,
    record_agent_request,
    record_approval_completed,
    record_approval_request,
    record_event_processed,
    record_event_published,
    record_mcp_call,
    record_skill_execution,
    set_agent_info,
    start_metrics_server,
    update_skill_confidence,
)

__all__ = [
    # Hooks
    "create_observability_hooks",
    "ObservabilityHooks",
    "MetricsAggregator",
    "RequestMetrics",
    "ToolCallMetric",
    "TokenUsage",
    # Prometheus metrics
    "get_metric",
    "record_agent_request",
    "record_skill_execution",
    "update_skill_confidence",
    "record_mcp_call",
    "record_event_published",
    "record_event_processed",
    "record_approval_request",
    "record_approval_completed",
    "set_agent_info",
    "start_metrics_server",
]
