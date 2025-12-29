"""
Observability and monitoring for AI agents.

Provides unified hooks for tracking metrics, token usage,
tool calls, and agent performance.

Modules:
    hooks: Observability hooks and metrics aggregation
"""

from core_agents.observability.hooks import (
    MetricsAggregator,
    ObservabilityHooks,
    RequestMetrics,
    TokenUsage,
    ToolCallMetric,
    create_observability_hooks,
)

__all__ = [
    "create_observability_hooks",
    "ObservabilityHooks",
    "MetricsAggregator",
    "RequestMetrics",
    "ToolCallMetric",
    "TokenUsage",
]
