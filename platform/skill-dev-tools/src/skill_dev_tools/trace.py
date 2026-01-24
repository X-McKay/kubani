"""Execution trace models - OpenTelemetry compatible."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class SpanKind(str, Enum):
    """Type of trace span."""

    SKILL = "skill"
    AGENT = "agent"
    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    MCP_CALL = "mcp_call"


class TraceEvent(BaseModel):
    """A single event within a trace span."""

    timestamp: datetime = Field(default_factory=datetime.utcnow)
    name: str = Field(..., description="Event name")
    attributes: dict[str, Any] = Field(default_factory=dict)


class TraceSpan(BaseModel):
    """A span within an execution trace."""

    span_id: str = Field(default_factory=lambda: uuid4().hex[:16])
    parent_span_id: str | None = Field(default=None)

    name: str = Field(..., description="Span name (e.g., 'skill.investigate-pod')")
    kind: SpanKind = Field(..., description="Type of span")

    start_time: datetime = Field(default_factory=datetime.utcnow)
    end_time: datetime | None = Field(default=None)

    attributes: dict[str, Any] = Field(default_factory=dict)
    events: list[TraceEvent] = Field(default_factory=list)

    # For LLM calls
    input_tokens: int | None = Field(default=None)
    output_tokens: int | None = Field(default=None)

    # Status
    status: str = Field(default="ok")  # ok, error
    error_message: str | None = Field(default=None)

    @property
    def duration_ms(self) -> float | None:
        """Duration in milliseconds."""
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time).total_seconds() * 1000

    def add_event(self, name: str, **attributes: Any) -> None:
        """Add an event to the span."""
        self.events.append(TraceEvent(name=name, attributes=attributes))

    def end(self, status: str = "ok", error: str | None = None) -> None:
        """Mark the span as ended."""
        self.end_time = datetime.utcnow()
        self.status = status
        if error:
            self.error_message = error


class ExecutionTrace(BaseModel):
    """Complete execution trace for a skill or agent run."""

    trace_id: str = Field(default_factory=lambda: uuid4().hex)

    # What was executed
    execution_type: str = Field(..., description="'skill' or 'agent'")
    name: str = Field(..., description="Skill or agent name")
    version: str = Field(default="unknown")

    # Timing
    start_time: datetime = Field(default_factory=datetime.utcnow)
    end_time: datetime | None = Field(default=None)

    # Input/Output
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)

    # Execution details
    spans: list[TraceSpan] = Field(default_factory=list)

    # Metrics
    metrics: dict[str, Any] = Field(default_factory=dict)

    # Evaluation (filled in by evaluator)
    evaluation: dict[str, Any] | None = Field(default=None)

    @property
    def duration_ms(self) -> float | None:
        """Total duration in milliseconds."""
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time).total_seconds() * 1000

    @property
    def total_tokens(self) -> int:
        """Total tokens used across all LLM calls."""
        total = 0
        for span in self.spans:
            if span.input_tokens:
                total += span.input_tokens
            if span.output_tokens:
                total += span.output_tokens
        return total

    @property
    def llm_calls(self) -> int:
        """Number of LLM calls."""
        return sum(1 for s in self.spans if s.kind == SpanKind.LLM_CALL)

    @property
    def tool_calls(self) -> int:
        """Number of tool/MCP calls."""
        return sum(1 for s in self.spans if s.kind in (SpanKind.TOOL_CALL, SpanKind.MCP_CALL))

    def add_span(self, span: TraceSpan) -> None:
        """Add a span to the trace."""
        self.spans.append(span)

    def end(self, output: dict[str, Any] | None = None) -> None:
        """Mark the trace as ended."""
        self.end_time = datetime.utcnow()
        if output:
            self.output = output
        self.metrics = {
            "duration_ms": self.duration_ms,
            "total_tokens": self.total_tokens,
            "llm_calls": self.llm_calls,
            "tool_calls": self.tool_calls,
        }

    def to_jsonl(self) -> str:
        """Serialize to JSONL format."""
        return self.model_dump_json()
