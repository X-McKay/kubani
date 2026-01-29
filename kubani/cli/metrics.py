"""
Metrics collection and export for kubani.

Provides tools for collecting, viewing, and exporting agent metrics.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, UTC, timedelta
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class MetricPoint:
    """A single metric data point."""

    name: str
    value: float
    timestamp: datetime
    labels: dict[str, str] = field(default_factory=dict)


@dataclass
class MetricSummary:
    """Summary statistics for a metric."""

    name: str
    count: int = 0
    total: float = 0.0
    min_value: float = float("inf")
    max_value: float = float("-inf")
    last_value: float = 0.0
    last_updated: Optional[datetime] = None

    @property
    def average(self) -> float:
        """Calculate average value."""
        return self.total / self.count if self.count > 0 else 0.0

    def record(self, value: float, timestamp: Optional[datetime] = None) -> None:
        """Record a new value."""
        self.count += 1
        self.total += value
        self.min_value = min(self.min_value, value)
        self.max_value = max(self.max_value, value)
        self.last_value = value
        self.last_updated = timestamp or datetime.now(UTC)


class MetricsCollector:
    """
    Collects and aggregates agent metrics.

    Supports:
    - Counter metrics (monotonically increasing)
    - Gauge metrics (point-in-time values)
    - Histogram metrics (distribution of values)
    """

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self._metrics: dict[str, MetricSummary] = {}
        self._history: list[MetricPoint] = []
        self._max_history = 10000

    def record(
        self,
        name: str,
        value: float,
        labels: Optional[dict[str, str]] = None,
    ) -> None:
        """Record a metric value."""
        timestamp = datetime.now(UTC)

        # Update summary
        if name not in self._metrics:
            self._metrics[name] = MetricSummary(name=name)
        self._metrics[name].record(value, timestamp)

        # Add to history
        self._history.append(
            MetricPoint(
                name=name,
                value=value,
                timestamp=timestamp,
                labels=labels or {},
            )
        )

        # Trim history
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    def get_summary(self, name: str) -> Optional[MetricSummary]:
        """Get summary for a metric."""
        return self._metrics.get(name)

    def get_all_summaries(self) -> dict[str, MetricSummary]:
        """Get all metric summaries."""
        return dict(self._metrics)

    def get_history(
        self,
        name: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> list[MetricPoint]:
        """Get metric history with optional filtering."""
        history = self._history

        if name:
            history = [p for p in history if p.name == name]

        if since:
            history = [p for p in history if p.timestamp >= since]

        return history[-limit:]

    def export_prometheus(self) -> str:
        """Export metrics in Prometheus format."""
        lines = []

        for name, summary in self._metrics.items():
            # Sanitize metric name for Prometheus
            prom_name = name.replace(".", "_").replace("-", "_")

            lines.extend(
                [
                    f"# HELP {prom_name} {name}",
                    f"# TYPE {prom_name} gauge",
                    f"{prom_name} {summary.last_value}",
                    f"{prom_name}_total {summary.total}",
                    f"{prom_name}_count {summary.count}",
                ]
            )

        return "\n".join(lines)

    def export_json(self) -> str:
        """Export metrics as JSON."""
        data = {
            "timestamp": datetime.now(UTC).isoformat(),
            "metrics": {
                name: {
                    "count": s.count,
                    "total": s.total,
                    "average": s.average,
                    "min": s.min_value if s.min_value != float("inf") else None,
                    "max": s.max_value if s.max_value != float("-inf") else None,
                    "last": s.last_value,
                    "last_updated": s.last_updated.isoformat() if s.last_updated else None,
                }
                for name, s in self._metrics.items()
            },
        }
        return json.dumps(data, indent=2)


class AgentMetrics:
    """
    Pre-defined metrics for agent monitoring.

    Provides standard metrics that all agents should track.
    """

    def __init__(self, collector: MetricsCollector, agent_name: str):
        self.collector = collector
        self.agent_name = agent_name
        self._prefix = f"agent.{agent_name}"

    def record_task_started(self) -> None:
        """Record a task start."""
        self.collector.record(f"{self._prefix}.tasks.started", 1)

    def record_task_completed(self, success: bool, duration_ms: float) -> None:
        """Record a task completion."""
        self.collector.record(f"{self._prefix}.tasks.completed", 1)
        self.collector.record(
            f"{self._prefix}.tasks.success" if success else f"{self._prefix}.tasks.failed",
            1,
        )
        self.collector.record(f"{self._prefix}.tasks.duration_ms", duration_ms)

    def record_tool_call(self, tool_name: str, duration_ms: float, success: bool) -> None:
        """Record a tool call."""
        self.collector.record(f"{self._prefix}.tools.calls", 1)
        self.collector.record(f"{self._prefix}.tools.{tool_name}.calls", 1)
        self.collector.record(f"{self._prefix}.tools.{tool_name}.duration_ms", duration_ms)
        if not success:
            self.collector.record(f"{self._prefix}.tools.{tool_name}.errors", 1)

    def record_llm_call(self, tokens_in: int, tokens_out: int, duration_ms: float) -> None:
        """Record an LLM call."""
        self.collector.record(f"{self._prefix}.llm.calls", 1)
        self.collector.record(f"{self._prefix}.llm.tokens_in", tokens_in)
        self.collector.record(f"{self._prefix}.llm.tokens_out", tokens_out)
        self.collector.record(f"{self._prefix}.llm.duration_ms", duration_ms)

    def record_memory_operation(self, operation: str, tier: str) -> None:
        """Record a memory operation."""
        self.collector.record(f"{self._prefix}.memory.{operation}", 1)
        self.collector.record(f"{self._prefix}.memory.{tier}.{operation}", 1)


class MetricsViewer:
    """
    View and format metrics for display.
    """

    def __init__(self, collector: MetricsCollector):
        self.collector = collector

    def format_summary(self, agent: Optional[str] = None) -> str:
        """Format metrics summary for display."""
        summaries = self.collector.get_all_summaries()

        if agent:
            prefix = f"agent.{agent}"
            summaries = {k: v for k, v in summaries.items() if k.startswith(prefix)}

        if not summaries:
            return "No metrics collected"

        lines = [
            f"{'Metric':<50} {'Count':>8} {'Avg':>10} {'Last':>10}",
            "-" * 80,
        ]

        for name, summary in sorted(summaries.items()):
            lines.append(
                f"{name[:48]:<50} "
                f"{summary.count:>8} "
                f"{summary.average:>10.2f} "
                f"{summary.last_value:>10.2f}"
            )

        return "\n".join(lines)

    def format_agent_dashboard(self, agent_name: str) -> str:
        """Format agent-specific dashboard."""
        prefix = f"agent.{agent_name}"
        summaries = self.collector.get_all_summaries()

        # Extract key metrics
        tasks_started = summaries.get(f"{prefix}.tasks.started", MetricSummary(name="")).count
        tasks_completed = summaries.get(f"{prefix}.tasks.completed", MetricSummary(name="")).count
        tasks_success = summaries.get(f"{prefix}.tasks.success", MetricSummary(name="")).count
        tasks_failed = summaries.get(f"{prefix}.tasks.failed", MetricSummary(name="")).count
        avg_duration = summaries.get(f"{prefix}.tasks.duration_ms", MetricSummary(name="")).average
        tool_calls = summaries.get(f"{prefix}.tools.calls", MetricSummary(name="")).count
        llm_calls = summaries.get(f"{prefix}.llm.calls", MetricSummary(name="")).count
        tokens_in = summaries.get(f"{prefix}.llm.tokens_in", MetricSummary(name="")).total
        tokens_out = summaries.get(f"{prefix}.llm.tokens_out", MetricSummary(name="")).total

        success_rate = (tasks_success / tasks_completed * 100) if tasks_completed > 0 else 0

        lines = [
            f"Agent: {agent_name}",
            "=" * 40,
            "",
            "Tasks:",
            f"  Started:    {tasks_started:>8}",
            f"  Completed:  {tasks_completed:>8}",
            f"  Success:    {tasks_success:>8} ({success_rate:.1f}%)",
            f"  Failed:     {tasks_failed:>8}",
            f"  Avg Time:   {avg_duration:>8.0f}ms",
            "",
            "Tools:",
            f"  Total Calls: {tool_calls:>7}",
            "",
            "LLM:",
            f"  Calls:      {llm_calls:>8}",
            f"  Tokens In:  {tokens_in:>8.0f}",
            f"  Tokens Out: {tokens_out:>8.0f}",
        ]

        return "\n".join(lines)
