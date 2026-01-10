"""
Trace management for kubani-dev.

Provides tools for viewing, analyzing, and managing agent execution traces.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class TraceStep:
    """A single step in an execution trace."""

    step_id: str
    timestamp: datetime
    action: str
    tool: str = ""
    input_data: dict[str, Any] = field(default_factory=dict)
    output_data: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    status: str = "success"
    error: str = ""


@dataclass
class Trace:
    """An execution trace for an agent run."""

    trace_id: str
    agent: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: str = "running"
    steps: list[TraceStep] = field(default_factory=list)
    input_data: dict[str, Any] = field(default_factory=dict)
    output_data: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        """Total duration in milliseconds."""
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds() * 1000
        return 0.0

    @property
    def step_count(self) -> int:
        """Number of steps in the trace."""
        return len(self.steps)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "trace_id": self.trace_id,
            "agent": self.agent,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "step_count": self.step_count,
            "steps": [
                {
                    "step_id": s.step_id,
                    "timestamp": s.timestamp.isoformat(),
                    "action": s.action,
                    "tool": s.tool,
                    "duration_ms": s.duration_ms,
                    "status": s.status,
                }
                for s in self.steps
            ],
            "input_data": self.input_data,
            "output_data": self.output_data,
            "metadata": self.metadata,
        }


class TraceStore:
    """
    Store and retrieve execution traces.

    Supports both local file storage and Redis-based storage.
    """

    def __init__(
        self,
        project_root: Path,
        redis_url: Optional[str] = None,
    ):
        self.project_root = project_root
        self.traces_dir = project_root / ".kubani-dev" / "traces"
        self.traces_dir.mkdir(parents=True, exist_ok=True)
        self._redis = None
        self._redis_url = redis_url

    async def _get_redis(self):
        """Get Redis client if configured."""
        if self._redis is None and self._redis_url:
            try:
                import redis.asyncio as aioredis

                self._redis = aioredis.from_url(
                    self._redis_url, decode_responses=True
                )
            except Exception as e:
                logger.warning(f"Failed to connect to Redis: {e}")
        return self._redis

    async def save_trace(self, trace: Trace) -> None:
        """Save a trace to storage."""
        # Save to file
        trace_file = self.traces_dir / f"{trace.trace_id}.json"
        with open(trace_file, "w") as f:
            json.dump(trace.to_dict(), f, indent=2)

        # Save to Redis if available
        redis = await self._get_redis()
        if redis:
            try:
                await redis.set(
                    f"trace:{trace.trace_id}",
                    json.dumps(trace.to_dict()),
                    ex=86400 * 7,  # 7 days
                )
                # Add to agent's trace list
                await redis.lpush(f"traces:{trace.agent}", trace.trace_id)
                await redis.ltrim(f"traces:{trace.agent}", 0, 999)  # Keep last 1000
            except Exception as e:
                logger.warning(f"Failed to save trace to Redis: {e}")

    async def get_trace(self, trace_id: str) -> Optional[Trace]:
        """Get a trace by ID."""
        # Try Redis first
        redis = await self._get_redis()
        if redis:
            try:
                data = await redis.get(f"trace:{trace_id}")
                if data:
                    return self._parse_trace(json.loads(data))
            except Exception as e:
                logger.debug(f"Redis lookup failed: {e}")

        # Fall back to file
        trace_file = self.traces_dir / f"{trace_id}.json"
        if trace_file.exists():
            with open(trace_file) as f:
                return self._parse_trace(json.load(f))

        return None

    async def list_traces(
        self,
        agent: Optional[str] = None,
        limit: int = 50,
        status: Optional[str] = None,
    ) -> list[Trace]:
        """List traces with optional filtering."""
        traces = []

        # Try Redis first
        redis = await self._get_redis()
        if redis and agent:
            try:
                trace_ids = await redis.lrange(f"traces:{agent}", 0, limit - 1)
                for tid in trace_ids:
                    trace = await self.get_trace(tid)
                    if trace and (status is None or trace.status == status):
                        traces.append(trace)
                return traces
            except Exception as e:
                logger.debug(f"Redis list failed: {e}")

        # Fall back to files
        trace_files = sorted(
            self.traces_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        for trace_file in trace_files[:limit * 2]:  # Get more to filter
            try:
                with open(trace_file) as f:
                    trace = self._parse_trace(json.load(f))
                    if agent and trace.agent != agent:
                        continue
                    if status and trace.status != status:
                        continue
                    traces.append(trace)
                    if len(traces) >= limit:
                        break
            except Exception as e:
                logger.debug(f"Failed to load trace {trace_file}: {e}")

        return traces

    def _parse_trace(self, data: dict[str, Any]) -> Trace:
        """Parse trace from dictionary."""
        steps = []
        for step_data in data.get("steps", []):
            steps.append(
                TraceStep(
                    step_id=step_data.get("step_id", ""),
                    timestamp=datetime.fromisoformat(step_data["timestamp"]),
                    action=step_data.get("action", ""),
                    tool=step_data.get("tool", ""),
                    duration_ms=step_data.get("duration_ms", 0.0),
                    status=step_data.get("status", "success"),
                )
            )

        completed_at = None
        if data.get("completed_at"):
            completed_at = datetime.fromisoformat(data["completed_at"])

        return Trace(
            trace_id=data["trace_id"],
            agent=data["agent"],
            started_at=datetime.fromisoformat(data["started_at"]),
            completed_at=completed_at,
            status=data.get("status", "unknown"),
            steps=steps,
            input_data=data.get("input_data", {}),
            output_data=data.get("output_data", {}),
            metadata=data.get("metadata", {}),
        )


class TraceViewer:
    """
    View and analyze traces.

    Provides formatted output for trace inspection.
    """

    def __init__(self, store: TraceStore):
        self.store = store

    async def show_trace(self, trace_id: str) -> str:
        """Generate detailed trace view."""
        trace = await self.store.get_trace(trace_id)
        if not trace:
            return f"Trace not found: {trace_id}"

        lines = [
            f"Trace: {trace.trace_id}",
            f"Agent: {trace.agent}",
            f"Status: {trace.status}",
            f"Started: {trace.started_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Duration: {trace.duration_ms:.0f}ms",
            f"Steps: {trace.step_count}",
            "",
            "Steps:",
            "-" * 60,
        ]

        for i, step in enumerate(trace.steps, 1):
            status_icon = "✓" if step.status == "success" else "✗"
            lines.append(
                f"  {i}. [{status_icon}] {step.action} "
                f"({step.tool or 'N/A'}) - {step.duration_ms:.0f}ms"
            )
            if step.error:
                lines.append(f"      Error: {step.error}")

        if trace.output_data:
            lines.extend(["", "Output:", "-" * 60])
            lines.append(json.dumps(trace.output_data, indent=2)[:500])

        return "\n".join(lines)

    async def list_traces(
        self,
        agent: Optional[str] = None,
        limit: int = 10,
    ) -> str:
        """Generate trace list view."""
        traces = await self.store.list_traces(agent=agent, limit=limit)

        if not traces:
            return "No traces found"

        lines = [
            f"{'ID':<20} {'Agent':<15} {'Status':<10} {'Duration':<10} {'Steps':<6} {'Time'}",
            "-" * 80,
        ]

        for trace in traces:
            lines.append(
                f"{trace.trace_id[:18]:<20} "
                f"{trace.agent[:13]:<15} "
                f"{trace.status:<10} "
                f"{trace.duration_ms:>7.0f}ms "
                f"{trace.step_count:>5} "
                f"{trace.started_at.strftime('%H:%M:%S')}"
            )

        return "\n".join(lines)
