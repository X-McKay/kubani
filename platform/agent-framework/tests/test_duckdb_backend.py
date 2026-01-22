"""Tests for DuckDB trace backend."""

from datetime import timedelta
from pathlib import Path

import pytest
from agent_framework.backends import DuckDBBackend, TraceQuery
from agent_framework.trace import ExecutionTrace, SpanKind, TraceSpan


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Create a temporary database path."""
    return tmp_path / "test_traces.duckdb"


@pytest.fixture
def backend(temp_db: Path) -> DuckDBBackend:
    """Create a DuckDB backend with temp database."""
    return DuckDBBackend(temp_db)


@pytest.fixture
def sample_trace() -> ExecutionTrace:
    """Create a sample trace for testing."""
    trace = ExecutionTrace(
        execution_type="skill",
        name="test-skill",
        version="1.0.0",
        input={"test": "input"},
    )
    span = TraceSpan(
        name="test.span",
        kind=SpanKind.LLM,
        attributes={"model": "test-model"},
    )
    span.end()
    trace.add_span(span)
    trace.end(output={"status": "success", "result": "test"})
    return trace


class TestDuckDBBackend:
    """Test DuckDB backend functionality."""

    @pytest.mark.asyncio
    async def test_record_and_get(self, backend: DuckDBBackend, sample_trace: ExecutionTrace):
        """Test recording and retrieving a trace."""
        trace_id = await backend.record(sample_trace)

        assert trace_id == sample_trace.trace_id

        retrieved = await backend.get(trace_id)
        assert retrieved is not None
        assert retrieved.trace_id == sample_trace.trace_id
        assert retrieved.name == "test-skill"
        assert retrieved.execution_type == "skill"

    @pytest.mark.asyncio
    async def test_query_by_skill(self, backend: DuckDBBackend, sample_trace: ExecutionTrace):
        """Test querying traces by skill name."""
        await backend.record(sample_trace)

        # Query by skill name
        query = TraceQuery(skill_name="test-skill", limit=10)
        results = await backend.query(query)

        assert len(results) == 1
        assert results[0].name == "test-skill"

    @pytest.mark.asyncio
    async def test_query_with_limit(self, backend: DuckDBBackend):
        """Test query limit."""
        # Record multiple traces
        for i in range(5):
            trace = ExecutionTrace(
                execution_type="skill",
                name="test-skill",
                input={"index": i},
            )
            trace.end(output={"status": "success"})
            await backend.record(trace)

        # Query with limit
        query = TraceQuery(skill_name="test-skill", limit=3)
        results = await backend.query(query)

        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_get_stats(self, backend: DuckDBBackend, sample_trace: ExecutionTrace):
        """Test aggregate statistics."""
        await backend.record(sample_trace)

        stats = await backend.get_stats("test-skill")

        assert stats["total_traces"] == 1
        assert "avg_duration_ms" in stats
        assert "total_tokens" in stats

    @pytest.mark.asyncio
    async def test_get_stats_all_skills(self, backend: DuckDBBackend):
        """Test aggregate statistics across all skills."""
        # Record traces for multiple skills
        for skill in ["skill-a", "skill-b"]:
            trace = ExecutionTrace(
                execution_type="skill",
                name=skill,
                input={"skill": skill},
            )
            trace.end(output={"status": "success"})
            await backend.record(trace)

        stats = await backend.get_stats()

        assert stats["total_traces"] == 2
        assert stats["unique_skills"] == 2

    @pytest.mark.asyncio
    async def test_get_token_usage_by_skill(self, backend: DuckDBBackend):
        """Test token usage breakdown by skill."""
        # Record traces with different token counts
        for skill, tokens in [("skill-a", 100), ("skill-b", 200), ("skill-a", 150)]:
            trace = ExecutionTrace(
                execution_type="skill",
                name=skill,
                input={},
            )
            trace._total_tokens = tokens
            trace.end(output={"status": "success"})
            await backend.record(trace)

        usage = await backend.get_token_usage_by_skill()

        assert len(usage) == 2
        # skill-a has 250 total, skill-b has 200
        skill_a = next(u for u in usage if u["skill_name"] == "skill-a")
        assert skill_a["total_tokens"] == 250
        assert skill_a["executions"] == 2

    @pytest.mark.asyncio
    async def test_get_performance_over_time(
        self, backend: DuckDBBackend, sample_trace: ExecutionTrace
    ):
        """Test performance over time query."""
        await backend.record(sample_trace)

        perf = await backend.get_performance_over_time("test-skill", "day")

        assert len(perf) >= 1
        assert "time_bucket" in perf[0]
        assert "executions" in perf[0]

    @pytest.mark.asyncio
    async def test_delete(self, backend: DuckDBBackend, sample_trace: ExecutionTrace):
        """Test trace deletion."""
        trace_id = await backend.record(sample_trace)

        # Verify exists
        assert await backend.get(trace_id) is not None

        # Delete
        result = await backend.delete(trace_id)
        assert result is True

        # Verify deleted
        assert await backend.get(trace_id) is None

    @pytest.mark.asyncio
    async def test_get_metrics(self, backend: DuckDBBackend):
        """Test aggregated metrics."""
        # Record multiple traces
        for _ in range(3):
            trace = ExecutionTrace(
                execution_type="skill",
                name="metrics-skill",
                input={},
            )
            trace._total_tokens = 100
            trace.end(output={"status": "success"})
            await backend.record(trace)

        metrics = await backend.get_metrics("metrics-skill", timedelta(hours=1))

        assert metrics.total_executions == 3
        assert metrics.avg_tokens == 100.0
