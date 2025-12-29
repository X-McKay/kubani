"""
Unified observability hooks for Strands agents.

Provides standardized observability across all agents:
- Token usage tracking
- Latency metrics (per-agent, per-tool, per-model-call)
- Agent handoff tracing
- Error rate tracking
- Structured logging with correlation IDs

Based on OpenTelemetry semantic conventions for GenAI.
"""

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from strands.hooks import HookProvider, HookRegistry
from strands.hooks.events import (
    AfterInvocationEvent,
    AfterModelCallEvent,
    AfterToolCallEvent,
    AgentInitializedEvent,
    BeforeInvocationEvent,
    BeforeModelCallEvent,
    BeforeToolCallEvent,
)

logger = logging.getLogger(__name__)


@dataclass
class TokenUsage:
    """Token usage statistics for a single model call."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ToolCallMetric:
    """Metrics for a single tool call."""

    tool_name: str
    duration_ms: float
    success: bool
    error_message: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class AgentHandoff:
    """Record of an agent handoff."""

    from_agent: str
    to_agent: str
    reason: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class RequestMetrics:
    """Aggregated metrics for a single agent request."""

    request_id: str
    agent_name: str
    start_time: datetime
    end_time: datetime | None = None

    # Token usage
    token_usage: list[TokenUsage] = field(default_factory=list)
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0

    # Latency
    total_duration_ms: float = 0.0
    model_call_duration_ms: float = 0.0
    tool_call_duration_ms: float = 0.0

    # Counts
    model_call_count: int = 0
    tool_call_count: int = 0
    tool_call_success_count: int = 0
    tool_call_error_count: int = 0

    # Tool details
    tool_metrics: list[ToolCallMetric] = field(default_factory=list)

    # Handoffs (for swarm/multi-agent)
    handoffs: list[AgentHandoff] = field(default_factory=list)

    # Outcome
    success: bool = True
    error_message: str | None = None


class ObservabilityHooks(HookProvider):
    """
    Strands hook provider for unified observability.

    Tracks metrics across the agent lifecycle and provides
    callbacks for metric export and logging.

    Usage:
        from core_agents.observability import ObservabilityHooks

        hooks = ObservabilityHooks(
            on_request_complete=lambda m: print(f"Request took {m.total_duration_ms}ms"),
            enable_debug_logging=True,
        )
        agent = Agent(hooks=[hooks])

    For custom metric backends (Prometheus, CloudWatch, etc.):
        def export_metrics(metrics: RequestMetrics):
            # Push to your metrics backend
            prometheus_histogram.observe(metrics.total_duration_ms)

        hooks = ObservabilityHooks(on_request_complete=export_metrics)
    """

    def __init__(
        self,
        on_request_complete: Callable[[RequestMetrics], None] | None = None,
        on_tool_call: Callable[[ToolCallMetric], None] | None = None,
        on_error: Callable[[str, Exception | None], None] | None = None,
        enable_debug_logging: bool = False,
        log_token_usage: bool = True,
    ):
        """
        Initialize observability hooks.

        Args:
            on_request_complete: Callback when a request completes with full metrics
            on_tool_call: Callback after each tool call with tool metrics
            on_error: Callback on errors with context and exception
            enable_debug_logging: Log detailed debug info for each event
            log_token_usage: Log token usage after each model call
        """
        self._on_request_complete = on_request_complete
        self._on_tool_call = on_tool_call
        self._on_error = on_error
        self._enable_debug_logging = enable_debug_logging
        self._log_token_usage = log_token_usage

        # Request-scoped state (reset on each invocation)
        self._current_metrics: RequestMetrics | None = None
        self._request_start: float = 0.0
        self._model_call_start: float = 0.0
        self._tool_call_start: float = 0.0
        self._current_tool_name: str = "unknown"  # Track tool name between before/after

    def register_hooks(self, registry: HookRegistry) -> None:
        """Register all observability callbacks with the hook registry."""
        # Agent lifecycle
        registry.add_callback(AgentInitializedEvent, self._on_agent_initialized)

        # Request lifecycle
        registry.add_callback(BeforeInvocationEvent, self._on_before_invocation)
        registry.add_callback(AfterInvocationEvent, self._on_after_invocation)

        # Model calls
        registry.add_callback(BeforeModelCallEvent, self._on_before_model_call)
        registry.add_callback(AfterModelCallEvent, self._on_after_model_call)

        # Tool calls
        registry.add_callback(BeforeToolCallEvent, self._on_before_tool_call)
        registry.add_callback(AfterToolCallEvent, self._on_after_tool_call)

    def _on_agent_initialized(self, event: AgentInitializedEvent) -> None:
        """Log agent initialization."""
        agent_name = getattr(event.agent, "name", "unnamed")
        if self._enable_debug_logging:
            logger.debug(f"Agent initialized: {agent_name}")

    def _on_before_invocation(self, event: BeforeInvocationEvent) -> None:
        """Initialize metrics for a new request."""
        agent_name = getattr(event.agent, "name", "unnamed")
        request_id = str(uuid.uuid4())[:8]

        self._current_metrics = RequestMetrics(
            request_id=request_id,
            agent_name=agent_name,
            start_time=datetime.now(UTC),
        )
        self._request_start = time.perf_counter()

        if self._enable_debug_logging:
            logger.debug(f"[{request_id}] Request started for agent: {agent_name}")

    def _on_after_invocation(self, event: AfterInvocationEvent) -> None:
        """Finalize metrics and call completion callback."""
        if not self._current_metrics:
            return

        # Calculate total duration
        self._current_metrics.end_time = datetime.now(UTC)
        self._current_metrics.total_duration_ms = (time.perf_counter() - self._request_start) * 1000

        # Aggregate token usage
        for usage in self._current_metrics.token_usage:
            self._current_metrics.total_prompt_tokens += usage.prompt_tokens
            self._current_metrics.total_completion_tokens += usage.completion_tokens
            self._current_metrics.total_tokens += usage.total_tokens

        # Check for errors in result
        if event.result and hasattr(event.result, "status"):
            from strands.multiagent.base import Status

            if event.result.status == Status.FAILED:
                self._current_metrics.success = False
                self._current_metrics.error_message = "Agent execution failed"

        # Log summary
        metrics = self._current_metrics
        logger.info(
            f"[{metrics.request_id}] {metrics.agent_name} completed: "
            f"{metrics.total_duration_ms:.1f}ms, "
            f"{metrics.total_tokens} tokens, "
            f"{metrics.model_call_count} model calls, "
            f"{metrics.tool_call_count} tool calls"
        )

        # Call completion callback
        if self._on_request_complete:
            try:
                self._on_request_complete(metrics)
            except Exception as e:
                logger.warning(f"Metrics callback failed: {e}")

        # Reset state
        self._current_metrics = None

    def _on_before_model_call(self, event: BeforeModelCallEvent) -> None:
        """Track model call start time."""
        self._model_call_start = time.perf_counter()

        if self._enable_debug_logging and self._current_metrics:
            logger.debug(f"[{self._current_metrics.request_id}] Model call starting")

    def _on_after_model_call(self, event: AfterModelCallEvent) -> None:
        """Record model call metrics including token usage."""
        if not self._current_metrics:
            return

        # Calculate duration
        duration_ms = (time.perf_counter() - self._model_call_start) * 1000
        self._current_metrics.model_call_duration_ms += duration_ms
        self._current_metrics.model_call_count += 1

        # Extract token usage if available
        # Note: strands-agents 1.20+ uses stop_response instead of response
        response = getattr(event, "stop_response", None) or getattr(event, "response", None)
        if response:
            usage = self._extract_token_usage(response)
            if usage:
                self._current_metrics.token_usage.append(usage)

                if self._log_token_usage:
                    logger.debug(
                        f"[{self._current_metrics.request_id}] Model call: "
                        f"{duration_ms:.1f}ms, {usage.total_tokens} tokens"
                    )

    def _extract_token_usage(self, response: Any) -> TokenUsage | None:
        """Extract token usage from model response."""
        try:
            # Handle different response formats
            usage_data = None

            if hasattr(response, "usage"):
                usage_data = response.usage
            elif isinstance(response, dict) and "usage" in response:
                usage_data = response["usage"]

            if usage_data:
                if isinstance(usage_data, dict):
                    return TokenUsage(
                        prompt_tokens=usage_data.get("prompt_tokens", 0),
                        completion_tokens=usage_data.get("completion_tokens", 0),
                        total_tokens=usage_data.get("total_tokens", 0),
                    )
                elif hasattr(usage_data, "prompt_tokens"):
                    return TokenUsage(
                        prompt_tokens=getattr(usage_data, "prompt_tokens", 0),
                        completion_tokens=getattr(usage_data, "completion_tokens", 0),
                        total_tokens=getattr(usage_data, "total_tokens", 0),
                    )
        except Exception:
            pass

        return None

    def _on_before_tool_call(self, event: BeforeToolCallEvent) -> None:
        """Track tool call start time."""
        self._tool_call_start = time.perf_counter()

        # strands-agents 1.20+ removed tool attribute from events
        # Try to get tool name from event if available, otherwise use "unknown"
        self._current_tool_name = getattr(getattr(event, "tool", None), "name", "unknown")

        if self._enable_debug_logging and self._current_metrics:
            logger.debug(f"[{self._current_metrics.request_id}] Tool call starting: {self._current_tool_name}")

    def _on_after_tool_call(self, event: AfterToolCallEvent) -> None:
        """Record tool call metrics."""
        if not self._current_metrics:
            return

        # Calculate duration
        duration_ms = (time.perf_counter() - self._tool_call_start) * 1000
        self._current_metrics.tool_call_duration_ms += duration_ms
        self._current_metrics.tool_call_count += 1

        # Use tool name captured in before hook (strands-agents 1.20+ removed tool from event)
        tool_name = self._current_tool_name
        success = event.exception is None
        error_message = str(event.exception) if event.exception else None

        if success:
            self._current_metrics.tool_call_success_count += 1
        else:
            self._current_metrics.tool_call_error_count += 1
            if self._on_error:
                self._on_error(f"Tool {tool_name} failed", event.exception)

        # Record metric
        metric = ToolCallMetric(
            tool_name=tool_name,
            duration_ms=duration_ms,
            success=success,
            error_message=error_message,
        )
        self._current_metrics.tool_metrics.append(metric)

        # Call tool callback
        if self._on_tool_call:
            try:
                self._on_tool_call(metric)
            except Exception as e:
                logger.warning(f"Tool metrics callback failed: {e}")

        if self._enable_debug_logging:
            status = "success" if success else f"failed: {error_message}"
            logger.debug(
                f"[{self._current_metrics.request_id}] Tool {tool_name}: "
                f"{duration_ms:.1f}ms, {status}"
            )

    def get_current_metrics(self) -> RequestMetrics | None:
        """Get metrics for the current in-flight request."""
        return self._current_metrics


def create_observability_hooks(
    *,
    enable_debug_logging: bool = False,
    log_token_usage: bool = True,
    on_request_complete: Callable[[RequestMetrics], None] | None = None,
    on_tool_call: Callable[[ToolCallMetric], None] | None = None,
    on_error: Callable[[str, Exception | None], None] | None = None,
) -> ObservabilityHooks:
    """
    Create observability hooks with sensible defaults.

    This is the recommended way to add observability to agents.

    Args:
        enable_debug_logging: Enable verbose debug logs for each event
        log_token_usage: Log token usage after model calls
        on_request_complete: Callback with full metrics when request completes
        on_tool_call: Callback after each tool call
        on_error: Callback on errors

    Returns:
        Configured ObservabilityHooks instance

    Example:
        from core_agents import create_agent
        from core_agents.observability import create_observability_hooks

        hooks = create_observability_hooks(enable_debug_logging=True)
        agent = create_agent(
            name="my-agent",
            ...,
            hooks=[hooks],
        )
    """
    return ObservabilityHooks(
        on_request_complete=on_request_complete,
        on_tool_call=on_tool_call,
        on_error=on_error,
        enable_debug_logging=enable_debug_logging,
        log_token_usage=log_token_usage,
    )


class MetricsAggregator:
    """
    Aggregates metrics across multiple requests for reporting.

    Useful for periodic metric reporting to monitoring systems.

    Usage:
        aggregator = MetricsAggregator()
        hooks = create_observability_hooks(
            on_request_complete=aggregator.record
        )

        # Later, get aggregated stats
        stats = aggregator.get_stats()
        print(f"Total requests: {stats['total_requests']}")
        print(f"Avg latency: {stats['avg_duration_ms']:.1f}ms")

        # Reset for next reporting period
        aggregator.reset()
    """

    def __init__(self):
        self._metrics: list[RequestMetrics] = []

    def record(self, metrics: RequestMetrics) -> None:
        """Record a completed request's metrics."""
        self._metrics.append(metrics)

    def get_stats(self) -> dict[str, Any]:
        """Get aggregated statistics."""
        if not self._metrics:
            return {
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "total_tokens": 0,
                "total_duration_ms": 0,
                "avg_duration_ms": 0,
                "avg_tokens_per_request": 0,
            }

        total_requests = len(self._metrics)
        successful = sum(1 for m in self._metrics if m.success)
        total_tokens = sum(m.total_tokens for m in self._metrics)
        total_duration = sum(m.total_duration_ms for m in self._metrics)

        # Tool stats
        total_tool_calls = sum(m.tool_call_count for m in self._metrics)
        tool_success = sum(m.tool_call_success_count for m in self._metrics)
        tool_duration = sum(m.tool_call_duration_ms for m in self._metrics)

        # Model stats
        total_model_calls = sum(m.model_call_count for m in self._metrics)
        model_duration = sum(m.model_call_duration_ms for m in self._metrics)

        return {
            "total_requests": total_requests,
            "successful_requests": successful,
            "failed_requests": total_requests - successful,
            "success_rate": successful / total_requests if total_requests > 0 else 0,
            # Token stats
            "total_tokens": total_tokens,
            "avg_tokens_per_request": total_tokens / total_requests,
            # Latency stats
            "total_duration_ms": total_duration,
            "avg_duration_ms": total_duration / total_requests,
            # Model call stats
            "total_model_calls": total_model_calls,
            "avg_model_calls_per_request": total_model_calls / total_requests,
            "total_model_duration_ms": model_duration,
            # Tool call stats
            "total_tool_calls": total_tool_calls,
            "tool_success_rate": tool_success / total_tool_calls if total_tool_calls > 0 else 0,
            "total_tool_duration_ms": tool_duration,
        }

    def reset(self) -> None:
        """Reset aggregated metrics."""
        self._metrics.clear()

    def get_metrics(self) -> list[RequestMetrics]:
        """Get all recorded metrics."""
        return list(self._metrics)
