"""JSONL file backend for traces."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from agent_framework.backends.base import TraceBackend, TraceMetrics, TraceQuery

if TYPE_CHECKING:
    from agent_framework.trace import ExecutionTrace

logger = logging.getLogger(__name__)


class JsonlBackend(TraceBackend):
    """
    JSONL file backend for trace storage.

    Stores traces as append-only JSONL files, organized by date.
    Simple, portable, and git-friendly (when gitignored).

    Directory structure:
        traces/
            2026-01-21_skill_investigate-pod.jsonl
            2026-01-21_agent_k8s-monitor.jsonl
    """

    def __init__(self, base_dir: str | Path):
        """
        Initialize JSONL backend.

        Args:
            base_dir: Directory for trace files
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_file_path(self, trace: ExecutionTrace) -> Path:
        """Get the file path for a trace."""
        date_str = trace.start_time.strftime("%Y-%m-%d")
        # Sanitize name by replacing slashes with underscores
        safe_name = trace.name.replace("/", "_")
        filename = f"{date_str}_{trace.execution_type}_{safe_name}.jsonl"
        return self.base_dir / filename

    async def record(self, trace: ExecutionTrace) -> str:
        """Store a trace by appending to JSONL file."""
        file_path = self._get_file_path(trace)

        with open(file_path, "a") as f:
            f.write(trace.to_jsonl() + "\n")

        logger.debug(f"Recorded trace {trace.trace_id} to {file_path}")
        return trace.trace_id

    async def get(self, trace_id: str) -> ExecutionTrace | None:
        """Retrieve a trace by ID (scans all files)."""
        from agent_framework.trace import ExecutionTrace

        for file_path in self.base_dir.glob("*.jsonl"):
            with open(file_path) as f:
                for line in f:
                    data = json.loads(line)
                    if data.get("trace_id") == trace_id:
                        return ExecutionTrace.model_validate(data)
        return None

    async def query(self, query: TraceQuery) -> list[ExecutionTrace]:
        """Query traces from JSONL files."""
        from agent_framework.trace import ExecutionTrace

        results: list[ExecutionTrace] = []
        cutoff = None
        if query.since:
            cutoff = datetime.now(UTC) - query.since

        for file_path in sorted(self.base_dir.glob("*.jsonl"), reverse=True):
            # Filter by name in filename
            if query.skill_name and f"skill_{query.skill_name}" not in file_path.name:
                continue
            if query.agent_name and f"agent_{query.agent_name}" not in file_path.name:
                continue

            with open(file_path) as f:
                for line in f:
                    if len(results) >= query.limit:
                        return results

                    data = json.loads(line)
                    trace = ExecutionTrace.model_validate(data)

                    # Filter by time
                    if cutoff and trace.start_time < cutoff:
                        continue

                    # Filter by status
                    if query.status:
                        has_error = any(s.status == "error" for s in trace.spans)
                        if query.status == "error" and not has_error:
                            continue
                        if query.status == "ok" and has_error:
                            continue

                    results.append(trace)

        return results

    async def get_metrics(
        self,
        name: str,
        window: timedelta,
    ) -> TraceMetrics:
        """Get aggregated metrics from JSONL files."""
        traces = await self.query(
            TraceQuery(
                skill_name=name,
                since=window,
                limit=1000,
            )
        )

        if not traces:
            return TraceMetrics()

        total = len(traces)
        successes = sum(1 for t in traces if not any(s.status == "error" for s in t.spans))
        durations = [t.duration_ms for t in traces if t.duration_ms]
        tokens = [t.total_tokens for t in traces]

        return TraceMetrics(
            total_executions=total,
            success_rate=successes / total if total > 0 else 0.0,
            avg_duration_ms=sum(durations) / len(durations) if durations else 0.0,
            avg_tokens=sum(tokens) / len(tokens) if tokens else 0.0,
        )
