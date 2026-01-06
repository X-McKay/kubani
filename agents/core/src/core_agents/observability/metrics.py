"""
Prometheus metrics for agent observability.

Provides pre-defined metrics for tracking agent performance,
skill execution, and system health.
"""

import os
from typing import Any

# Lazy initialization to avoid import errors if prometheus_client not installed
_metrics_initialized = False
_metrics: dict[str, Any] = {}


def _ensure_metrics_initialized() -> None:
    """Lazy initialization of Prometheus metrics."""
    global _metrics_initialized, _metrics

    if _metrics_initialized:
        return

    try:
        from prometheus_client import Counter, Gauge, Histogram, Info

        # Agent metrics
        _metrics["agent_requests_total"] = Counter(
            "agent_requests_total",
            "Total number of agent requests",
            ["agent", "status"],
        )

        _metrics["agent_request_duration_seconds"] = Histogram(
            "agent_request_duration_seconds",
            "Agent request duration in seconds",
            ["agent"],
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0],
        )

        _metrics["agent_tokens_total"] = Counter(
            "agent_tokens_total",
            "Total tokens used by agents",
            ["agent", "type"],  # type = prompt, completion
        )

        # Skill metrics
        _metrics["skill_executions_total"] = Counter(
            "skill_executions_total",
            "Total number of skill executions",
            ["skill_id", "domain", "category", "outcome"],
        )

        _metrics["skill_execution_duration_seconds"] = Histogram(
            "skill_execution_duration_seconds",
            "Skill execution duration in seconds",
            ["skill_id"],
            buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
        )

        _metrics["skill_confidence"] = Gauge(
            "skill_confidence",
            "Current confidence score for skills",
            ["skill_id", "domain"],
        )

        _metrics["skill_library_size"] = Gauge(
            "skill_library_size",
            "Number of skills in the library",
            ["domain", "category"],
        )

        # MCP metrics
        _metrics["mcp_calls_total"] = Counter(
            "mcp_calls_total",
            "Total MCP server tool calls",
            ["server", "tool", "outcome"],
        )

        _metrics["mcp_call_duration_seconds"] = Histogram(
            "mcp_call_duration_seconds",
            "MCP tool call duration in seconds",
            ["server", "tool"],
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
        )

        # Event bus metrics
        _metrics["events_published_total"] = Counter(
            "events_published_total",
            "Total events published to the event bus",
            ["event_type", "source"],
        )

        _metrics["events_processed_total"] = Counter(
            "events_processed_total",
            "Total events processed by subscribers",
            ["event_type", "consumer"],
        )

        # Approval metrics
        _metrics["approvals_requested_total"] = Counter(
            "approvals_requested_total",
            "Total approval requests",
            ["action", "skill_id"],
        )

        _metrics["approvals_completed_total"] = Counter(
            "approvals_completed_total",
            "Total completed approval requests",
            ["action", "status"],  # status = approved, rejected, timeout
        )

        _metrics["approval_latency_seconds"] = Histogram(
            "approval_latency_seconds",
            "Time from approval request to response",
            ["action"],
            buckets=[10, 30, 60, 120, 300, 600],
        )

        # System info
        _metrics["agent_info"] = Info(
            "agent_info",
            "Agent system information",
        )

        _metrics_initialized = True

    except ImportError:
        # prometheus_client not installed - metrics disabled
        _metrics_initialized = True


def get_metric(name: str) -> Any | None:
    """Get a metric by name, or None if metrics are disabled."""
    _ensure_metrics_initialized()
    return _metrics.get(name)


# Convenience functions for recording metrics


def record_agent_request(
    agent: str,
    duration_seconds: float,
    success: bool,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> None:
    """Record metrics for an agent request."""
    _ensure_metrics_initialized()

    status = "success" if success else "error"

    if counter := _metrics.get("agent_requests_total"):
        counter.labels(agent=agent, status=status).inc()

    if histogram := _metrics.get("agent_request_duration_seconds"):
        histogram.labels(agent=agent).observe(duration_seconds)

    if counter := _metrics.get("agent_tokens_total"):
        if prompt_tokens > 0:
            counter.labels(agent=agent, type="prompt").inc(prompt_tokens)
        if completion_tokens > 0:
            counter.labels(agent=agent, type="completion").inc(completion_tokens)


def record_skill_execution(
    skill_id: str,
    domain: str,
    category: str,
    success: bool,
    duration_seconds: float,
) -> None:
    """Record metrics for a skill execution."""
    _ensure_metrics_initialized()

    outcome = "success" if success else "failure"

    if counter := _metrics.get("skill_executions_total"):
        counter.labels(
            skill_id=skill_id,
            domain=domain,
            category=category,
            outcome=outcome,
        ).inc()

    if histogram := _metrics.get("skill_execution_duration_seconds"):
        histogram.labels(skill_id=skill_id).observe(duration_seconds)


def update_skill_confidence(skill_id: str, domain: str, confidence: float) -> None:
    """Update the confidence gauge for a skill."""
    _ensure_metrics_initialized()

    if gauge := _metrics.get("skill_confidence"):
        gauge.labels(skill_id=skill_id, domain=domain).set(confidence)


def record_mcp_call(
    server: str,
    tool: str,
    success: bool,
    duration_seconds: float,
) -> None:
    """Record metrics for an MCP tool call."""
    _ensure_metrics_initialized()

    outcome = "success" if success else "error"

    if counter := _metrics.get("mcp_calls_total"):
        counter.labels(server=server, tool=tool, outcome=outcome).inc()

    if histogram := _metrics.get("mcp_call_duration_seconds"):
        histogram.labels(server=server, tool=tool).observe(duration_seconds)


def record_event_published(event_type: str, source: str) -> None:
    """Record an event published to the bus."""
    _ensure_metrics_initialized()

    if counter := _metrics.get("events_published_total"):
        counter.labels(event_type=event_type, source=source).inc()


def record_event_processed(event_type: str, consumer: str) -> None:
    """Record an event processed by a consumer."""
    _ensure_metrics_initialized()

    if counter := _metrics.get("events_processed_total"):
        counter.labels(event_type=event_type, consumer=consumer).inc()


def record_approval_request(action: str, skill_id: str | None = None) -> None:
    """Record an approval request."""
    _ensure_metrics_initialized()

    if counter := _metrics.get("approvals_requested_total"):
        counter.labels(action=action, skill_id=skill_id or "none").inc()


def record_approval_completed(
    action: str,
    status: str,
    latency_seconds: float,
) -> None:
    """Record a completed approval."""
    _ensure_metrics_initialized()

    if counter := _metrics.get("approvals_completed_total"):
        counter.labels(action=action, status=status).inc()

    if histogram := _metrics.get("approval_latency_seconds"):
        histogram.labels(action=action).observe(latency_seconds)


def set_agent_info(version: str, **labels: str) -> None:
    """Set agent system information."""
    _ensure_metrics_initialized()

    if info := _metrics.get("agent_info"):
        info.info({"version": version, **labels})


def start_metrics_server(port: int | None = None) -> None:
    """Start a Prometheus metrics HTTP server."""
    _ensure_metrics_initialized()

    port = port or int(os.getenv("METRICS_PORT", "9090"))

    try:
        from prometheus_client import start_http_server

        start_http_server(port)
    except ImportError:
        pass
