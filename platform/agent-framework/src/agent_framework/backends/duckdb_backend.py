"""DuckDB trace backend for local development with analytical query capability."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import duckdb

from agent_framework.backends.base import TraceBackend, TraceMetrics, TraceQuery

if TYPE_CHECKING:
    from agent_framework.trace import ExecutionTrace

logger = logging.getLogger(__name__)


class DuckDBBackend(TraceBackend):
    """
    DuckDB trace backend for local development.

    Optimized for analytical queries on traces:
    - Columnar storage for fast aggregations
    - Vectorized execution
    - Native JSON querying
    - Parquet export for archival
    """

    def __init__(self, db_path: str | Path = "traces.duckdb"):
        """
        Initialize DuckDB backend.

        Args:
            db_path: Path to DuckDB database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: duckdb.DuckDBPyConnection | None = None
        self._init_db()

    def _get_conn(self) -> duckdb.DuckDBPyConnection:
        """Get or create database connection."""
        if self._conn is None:
            self._conn = duckdb.connect(str(self.db_path))
        return self._conn

    def _init_db(self) -> None:
        """Initialize database schema."""
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS traces (
                trace_id VARCHAR PRIMARY KEY,
                execution_type VARCHAR NOT NULL,
                name VARCHAR NOT NULL,
                version VARCHAR,
                start_time TIMESTAMP NOT NULL,
                end_time TIMESTAMP,
                duration_ms DOUBLE,
                input_json JSON,
                output_json JSON,
                spans_json JSON,
                total_tokens INTEGER DEFAULT 0,
                llm_calls INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    async def record(self, trace: ExecutionTrace) -> str:
        """Record a trace to DuckDB."""
        conn = self._get_conn()
        conn.execute(
            """
            INSERT OR REPLACE INTO traces
            (trace_id, execution_type, name, version, start_time, end_time,
             duration_ms, input_json, output_json, spans_json,
             total_tokens, llm_calls)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                trace.trace_id,
                trace.execution_type,
                trace.name,
                trace.version,
                trace.start_time,
                trace.end_time,
                trace.duration_ms,
                json.dumps(trace.input, default=str),
                json.dumps(trace.output, default=str),
                json.dumps([s.model_dump() for s in trace.spans], default=str),
                trace.total_tokens,
                trace.llm_calls,
            ],
        )

        logger.debug(f"Recorded trace {trace.trace_id} to DuckDB")
        return trace.trace_id

    async def query(self, query: TraceQuery) -> list[ExecutionTrace]:
        """Query traces from DuckDB."""
        conn = self._get_conn()

        sql = "SELECT * FROM traces WHERE 1=1"
        params: list[Any] = []

        if query.skill_name:
            sql += " AND name = ? AND execution_type = 'skill'"
            params.append(query.skill_name)

        if query.agent_name:
            sql += " AND name = ? AND execution_type = 'agent'"
            params.append(query.agent_name)

        if query.since:
            cutoff = datetime.now(UTC) - query.since
            sql += " AND start_time > ?"
            params.append(cutoff)

        if query.status:
            # Check output JSON for status field using DuckDB JSON functions
            if query.status == "error":
                sql += " AND json_extract_string(output_json, '$.status') = 'failure'"
            elif query.status == "ok":
                sql += " AND json_extract_string(output_json, '$.status') = 'success'"

        sql += " ORDER BY start_time DESC"

        if query.limit:
            sql += " LIMIT ?"
            params.append(query.limit)

        result = conn.execute(sql, params).fetchall()
        columns = [desc[0] for desc in conn.description]

        return [self._row_to_trace(dict(zip(columns, row))) for row in result]

    async def get(self, trace_id: str) -> ExecutionTrace | None:
        """Get a specific trace by ID."""
        conn = self._get_conn()
        result = conn.execute(
            "SELECT * FROM traces WHERE trace_id = ?",
            [trace_id],
        ).fetchone()

        if result:
            columns = [desc[0] for desc in conn.description]
            return self._row_to_trace(dict(zip(columns, result)))
        return None

    async def delete(self, trace_id: str) -> bool:
        """Delete a trace."""
        conn = self._get_conn()
        conn.execute("DELETE FROM traces WHERE trace_id = ?", [trace_id])
        return True

    async def get_metrics(
        self,
        name: str,
        window: timedelta,
    ) -> TraceMetrics:
        """Get aggregated metrics for a skill or agent."""
        conn = self._get_conn()
        cutoff = datetime.now(UTC) - window

        sql = """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN json_extract_string(output_json, '$.status') = 'success' THEN 1 ELSE 0 END) as successes,
                AVG(duration_ms) as avg_duration,
                AVG(total_tokens) as avg_tokens
            FROM traces
            WHERE name = ? AND start_time > ?
        """

        result = conn.execute(sql, [name, cutoff]).fetchone()

        if not result or result[0] == 0:
            return TraceMetrics()

        total, successes, avg_duration, avg_tokens = result

        return TraceMetrics(
            total_executions=total,
            success_rate=successes / total if total > 0 else 0.0,
            avg_duration_ms=avg_duration or 0.0,
            avg_tokens=avg_tokens or 0.0,
        )

    async def get_stats(self, skill_name: str | None = None) -> dict[str, Any]:
        """
        Get aggregate statistics.

        This is a convenience method beyond the TraceBackend interface,
        useful for CLI commands and dashboards.
        """
        conn = self._get_conn()

        sql = """
            SELECT
                COUNT(*) as total_traces,
                COALESCE(SUM(total_tokens), 0) as total_tokens,
                COALESCE(AVG(duration_ms), 0) as avg_duration_ms,
                COALESCE(AVG(total_tokens), 0) as avg_tokens,
                MIN(start_time) as first_trace,
                MAX(start_time) as last_trace,
                COALESCE(SUM(llm_calls), 0) as total_llm_calls,
                COUNT(DISTINCT name) as unique_skills
            FROM traces
        """
        params: list[Any] = []

        if skill_name:
            sql += " WHERE name = ?"
            params.append(skill_name)

        result = conn.execute(sql, params).fetchone()
        columns = [desc[0] for desc in conn.description]

        stats = dict(zip(columns, result)) if result else {}

        # Format timestamps
        if stats.get("first_trace"):
            ts = stats["first_trace"]
            stats["first_trace"] = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
        if stats.get("last_trace"):
            ts = stats["last_trace"]
            stats["last_trace"] = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)

        return stats

    async def get_token_usage_by_skill(self) -> list[dict[str, Any]]:
        """Get token usage breakdown by skill (DuckDB analytical query)."""
        conn = self._get_conn()
        result = conn.execute("""
            SELECT
                name as skill_name,
                COUNT(*) as executions,
                SUM(total_tokens) as total_tokens,
                AVG(total_tokens) as avg_tokens,
                AVG(duration_ms) as avg_duration_ms
            FROM traces
            GROUP BY name
            ORDER BY total_tokens DESC
        """).fetchall()

        columns = ["skill_name", "executions", "total_tokens", "avg_tokens", "avg_duration_ms"]
        return [dict(zip(columns, row)) for row in result]

    async def get_performance_over_time(
        self,
        skill_name: str | None = None,
        bucket: str = "day",
    ) -> list[dict[str, Any]]:
        """Get performance metrics over time (DuckDB time-series query)."""
        conn = self._get_conn()

        bucket_expr = {
            "hour": "DATE_TRUNC('hour', start_time)",
            "day": "DATE_TRUNC('day', start_time)",
            "week": "DATE_TRUNC('week', start_time)",
        }.get(bucket, "DATE_TRUNC('day', start_time)")

        sql = f"""
            SELECT
                {bucket_expr} as time_bucket,
                COUNT(*) as executions,
                AVG(duration_ms) as avg_duration_ms,
                AVG(total_tokens) as avg_tokens,
                SUM(total_tokens) as total_tokens
            FROM traces
        """
        params: list[Any] = []

        if skill_name:
            sql += " WHERE name = ?"
            params.append(skill_name)

        sql += f" GROUP BY {bucket_expr} ORDER BY time_bucket"

        result = conn.execute(sql, params).fetchall()
        columns = ["time_bucket", "executions", "avg_duration_ms", "avg_tokens", "total_tokens"]

        rows = []
        for row in result:
            row_dict = dict(zip(columns, row))
            if row_dict.get("time_bucket"):
                ts = row_dict["time_bucket"]
                row_dict["time_bucket"] = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
            rows.append(row_dict)

        return rows

    async def export_to_parquet(
        self, output_path: str | Path, skill_name: str | None = None
    ) -> str:
        """Export traces to Parquet format for archival."""
        conn = self._get_conn()
        output_path = Path(output_path)

        sql = "SELECT * FROM traces"
        if skill_name:
            sql += f" WHERE name = '{skill_name}'"

        conn.execute(f"COPY ({sql}) TO '{output_path}' (FORMAT PARQUET)")
        logger.info(f"Exported traces to {output_path}")

        return str(output_path)

    def _row_to_trace(self, row: dict[str, Any]) -> ExecutionTrace:
        """Convert database row to ExecutionTrace."""
        from agent_framework.trace import ExecutionTrace, TraceSpan

        spans_json = row["spans_json"]
        if isinstance(spans_json, str):
            spans_data = json.loads(spans_json)
        elif spans_json:
            spans_data = spans_json
        else:
            spans_data = []
        spans = [TraceSpan(**s) for s in spans_data]

        start_time = row["start_time"]
        end_time = row["end_time"]

        # Handle DuckDB datetime objects
        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time)

        if end_time and isinstance(end_time, str):
            end_time = datetime.fromisoformat(end_time)

        input_json = row["input_json"]
        output_json = row["output_json"]

        if isinstance(input_json, str):
            input_data = json.loads(input_json)
        elif input_json:
            input_data = input_json
        else:
            input_data = {}

        if isinstance(output_json, str):
            output_data = json.loads(output_json)
        elif output_json:
            output_data = output_json
        else:
            output_data = {}

        return ExecutionTrace(
            trace_id=row["trace_id"],
            execution_type=row["execution_type"],
            name=row["name"],
            version=row["version"],
            start_time=start_time,
            end_time=end_time,
            input=input_data,
            output=output_data,
            spans=spans,
        )

    async def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
