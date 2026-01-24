"""Base trace backend interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from skill_dev_tools.trace import ExecutionTrace


class TraceQuery:
    """Query parameters for trace search."""

    def __init__(
        self,
        skill_name: str | None = None,
        agent_name: str | None = None,
        since: timedelta | None = None,
        limit: int = 100,
        status: str | None = None,
    ):
        self.skill_name = skill_name
        self.agent_name = agent_name
        self.since = since
        self.limit = limit
        self.status = status


class TraceMetrics:
    """Aggregated metrics for traces."""

    def __init__(
        self,
        total_executions: int = 0,
        success_rate: float = 0.0,
        avg_duration_ms: float = 0.0,
        avg_tokens: float = 0.0,
    ):
        self.total_executions = total_executions
        self.success_rate = success_rate
        self.avg_duration_ms = avg_duration_ms
        self.avg_tokens = avg_tokens


class TraceBackend(ABC):
    """Abstract interface for trace storage."""

    @abstractmethod
    async def record(self, trace: ExecutionTrace) -> str:
        """
        Store a trace.

        Args:
            trace: The execution trace to store

        Returns:
            Trace ID
        """
        pass

    @abstractmethod
    async def get(self, trace_id: str) -> ExecutionTrace | None:
        """
        Retrieve a trace by ID.

        Args:
            trace_id: The trace ID

        Returns:
            The trace, or None if not found
        """
        pass

    @abstractmethod
    async def query(self, query: TraceQuery) -> list[ExecutionTrace]:
        """
        Query traces.

        Args:
            query: Query parameters

        Returns:
            List of matching traces
        """
        pass

    @abstractmethod
    async def get_metrics(
        self,
        name: str,
        window: timedelta,
    ) -> TraceMetrics:
        """
        Get aggregated metrics for a skill or agent.

        Args:
            name: Skill or agent name
            window: Time window for aggregation

        Returns:
            Aggregated metrics
        """
        pass

    async def close(self) -> None:
        """Close the backend (cleanup resources)."""
        pass
