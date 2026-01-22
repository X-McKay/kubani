# Phase 2: Agent Framework Foundation - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a unified Agent Framework with base classes, mixins, SkillExecutor, and AgentRunner that enables local-first development with cluster-ready deployment.

**Architecture:** Build on existing patterns in `agents/core/` while introducing new abstractions that decouple agent logic from deployment concerns. The framework follows the principle: "Local-first, cluster-ready."

**Tech Stack:** Python 3.11+, Pydantic, asyncio, Temporal (optional for cluster mode), existing MCP client

---

## Pre-Flight Checklist

Before starting, verify:
```bash
# On feature/restructure branch
git branch --show-current

# Phase 1 complete
ls platform/ infrastructure/ agents/skills/

# Core agents importable
python -c "from core_agents.config_unified import get_config; print('OK')"
```

---

## Task 1: Create Framework Package Structure

**Files:**
- Create: `platform/agent-framework/`
- Create: `platform/agent-framework/pyproject.toml`
- Create: `platform/agent-framework/src/agent_framework/__init__.py`

**Step 1: Create directory structure**

```bash
mkdir -p platform/agent-framework/src/agent_framework
mkdir -p platform/agent-framework/tests
```

**Step 2: Create pyproject.toml**

```toml
[project]
name = "agent-framework"
version = "0.1.0"
description = "Unified Agent Framework for Kubani"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.0",
    "structlog>=24.0",
    "httpx>=0.27",
]

[project.optional-dependencies]
temporal = ["temporalio>=1.7"]
dev = ["pytest>=8.0", "pytest-asyncio>=0.24"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/agent_framework"]
```

**Step 3: Create __init__.py**

```python
"""
Agent Framework - Local-first, cluster-ready agent development.

Core abstractions:
- AgentBase: Base class for all agents
- SkillExecutor: Run and evaluate skills in isolation
- AgentRunner: Run agents in local or cluster mode
- Mixins: Composable capabilities (MCP, Skills, Memory, etc.)
"""

from agent_framework.base import AgentBase
from agent_framework.runner import AgentRunner
from agent_framework.skill_executor import SkillExecutor

__all__ = ["AgentBase", "AgentRunner", "SkillExecutor"]
__version__ = "0.1.0"
```

**Step 4: Commit**

```bash
git add platform/agent-framework/
git commit -m "feat(framework): create agent-framework package structure

Initial package setup for unified agent framework:
- pyproject.toml with dependencies
- Package structure with __init__.py

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Create AgentConfig and AgentBase

**Files:**
- Create: `platform/agent-framework/src/agent_framework/config.py`
- Create: `platform/agent-framework/src/agent_framework/base.py`

**Step 1: Create config.py**

```python
"""Agent configuration models."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RunMode(str, Enum):
    """Agent execution mode."""
    LOCAL = "local"           # Single process, direct execution
    LOCAL_CLUSTER = "local_cluster"  # Local process, cluster services
    CLUSTER = "cluster"       # Full Temporal worker


class AgentConfig(BaseModel):
    """Configuration for an agent instance."""

    name: str = Field(..., description="Agent name (e.g., 'k8s-monitor')")
    version: str = Field(default="0.0.0", description="Agent version")
    description: str = Field(default="", description="Agent description")

    # Execution mode
    mode: RunMode = Field(default=RunMode.LOCAL, description="Execution mode")

    # LLM configuration
    llm_model: str | None = Field(default=None, description="Override LLM model")
    llm_temperature: float = Field(default=0.0, description="LLM temperature")

    # Skill configuration
    skills_dir: str | None = Field(default=None, description="Skills directory path")
    enabled_skills: list[str] = Field(default_factory=list, description="Enabled skill names")

    # MCP configuration
    mcp_servers: list[str] = Field(default_factory=list, description="Required MCP servers")

    # Observability
    enable_tracing: bool = Field(default=True, description="Enable trace collection")
    trace_backend: str = Field(default="jsonl", description="Trace backend (jsonl, sqlite, otel)")

    model_config = {"extra": "allow"}


class SkillConfig(BaseModel):
    """Configuration for skill execution."""

    name: str = Field(..., description="Skill name")
    version: str = Field(default="latest", description="Skill version")
    timeout_seconds: float = Field(default=300.0, description="Execution timeout")

    # Context provided to the skill
    context: dict[str, Any] = Field(default_factory=dict, description="Skill context")

    # Evaluation settings
    record_trace: bool = Field(default=True, description="Record execution trace")
```

**Step 2: Create base.py**

```python
"""AgentBase - Base class for all agents."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from agent_framework.config import AgentConfig, RunMode

if TYPE_CHECKING:
    from agent_framework.trace import ExecutionTrace

logger = logging.getLogger(__name__)


class AgentBase(ABC):
    """
    Base class for all Kubani agents.

    Provides standard lifecycle management and configuration.
    Agents inherit from this and implement the abstract methods.

    Lifecycle:
        1. __init__(config) - Set up configuration
        2. initialize() - Async setup (connections, resources)
        3. run() - Main execution loop
        4. shutdown() - Cleanup resources

    Example:
        class MyAgent(AgentBase):
            async def initialize(self) -> None:
                self.client = await setup_client()

            async def run(self) -> None:
                while self.running:
                    await self.process_next()

            async def shutdown(self) -> None:
                await self.client.close()
    """

    def __init__(self, config: AgentConfig) -> None:
        """Initialize agent with configuration."""
        self.config = config
        self.name = config.name
        self.version = config.version
        self._running = False
        self._initialized = False

        # Will be set by mixins
        self._mcp_client: Any = None
        self._skill_loader: Any = None
        self._memory: Any = None
        self._tracer: Any = None

    @property
    def running(self) -> bool:
        """Whether the agent is currently running."""
        return self._running

    @property
    def mode(self) -> RunMode:
        """Current execution mode."""
        return self.config.mode

    async def initialize(self) -> None:
        """
        Initialize the agent (async setup).

        Override this to set up connections, load resources, etc.
        Called once before run().
        """
        self._initialized = True
        logger.info(f"Agent {self.name} initialized in {self.mode.value} mode")

    @abstractmethod
    async def run(self) -> None:
        """
        Main agent execution.

        Override this to implement the agent's main logic.
        For long-running agents, check self.running in the loop.
        """
        pass

    async def shutdown(self) -> None:
        """
        Shutdown the agent (cleanup).

        Override this to close connections, flush buffers, etc.
        Called after run() completes or on interrupt.
        """
        self._running = False
        logger.info(f"Agent {self.name} shutdown")

    async def handle_event(self, event: dict[str, Any]) -> dict[str, Any]:
        """
        Handle a single event/trigger.

        Override this for event-driven agents.
        Default implementation raises NotImplementedError.

        Args:
            event: Event data

        Returns:
            Result of handling the event
        """
        raise NotImplementedError(
            f"Agent {self.name} does not implement handle_event(). "
            "Override this method for event-driven behavior."
        )

    async def execute_skill(
        self,
        skill_name: str,
        context: dict[str, Any] | None = None,
    ) -> "ExecutionTrace":
        """
        Execute a skill by name.

        Requires SkillLoaderMixin to be applied.

        Args:
            skill_name: Name of the skill to execute
            context: Context to pass to the skill

        Returns:
            Execution trace with results
        """
        if self._skill_loader is None:
            raise RuntimeError(
                "SkillLoaderMixin not applied. "
                "Add SkillLoaderMixin to your agent class."
            )
        return await self._skill_loader.execute(skill_name, context or {})

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} mode={self.mode.value}>"
```

**Step 3: Commit**

```bash
git add platform/agent-framework/src/agent_framework/config.py
git add platform/agent-framework/src/agent_framework/base.py
git commit -m "feat(framework): add AgentConfig and AgentBase

Core abstractions for agent framework:
- AgentConfig with run modes (local, local_cluster, cluster)
- AgentBase with lifecycle methods (initialize, run, shutdown)
- Support for event-driven and long-running agents

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Create Trace Models

**Files:**
- Create: `platform/agent-framework/src/agent_framework/trace.py`

**Step 1: Create trace.py**

```python
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
```

**Step 2: Commit**

```bash
git add platform/agent-framework/src/agent_framework/trace.py
git commit -m "feat(framework): add trace models (OTEL compatible)

Execution trace models for skill and agent runs:
- TraceSpan with LLM/tool call tracking
- ExecutionTrace with metrics aggregation
- JSONL serialization for backend storage

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Create Trace Backend Abstraction

**Files:**
- Create: `platform/agent-framework/src/agent_framework/backends/__init__.py`
- Create: `platform/agent-framework/src/agent_framework/backends/base.py`
- Create: `platform/agent-framework/src/agent_framework/backends/jsonl.py`

**Step 1: Create backends directory**

```bash
mkdir -p platform/agent-framework/src/agent_framework/backends
```

**Step 2: Create backends/__init__.py**

```python
"""Trace backends for persisting execution traces."""

from agent_framework.backends.base import TraceBackend
from agent_framework.backends.jsonl import JsonlBackend

__all__ = ["TraceBackend", "JsonlBackend"]
```

**Step 3: Create backends/base.py**

```python
"""Base trace backend interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_framework.trace import ExecutionTrace


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
    async def record(self, trace: "ExecutionTrace") -> str:
        """
        Store a trace.

        Args:
            trace: The execution trace to store

        Returns:
            Trace ID
        """
        pass

    @abstractmethod
    async def get(self, trace_id: str) -> "ExecutionTrace | None":
        """
        Retrieve a trace by ID.

        Args:
            trace_id: The trace ID

        Returns:
            The trace, or None if not found
        """
        pass

    @abstractmethod
    async def query(self, query: TraceQuery) -> list["ExecutionTrace"]:
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
```

**Step 4: Create backends/jsonl.py**

```python
"""JSONL file backend for traces."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
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

    def _get_file_path(self, trace: "ExecutionTrace") -> Path:
        """Get the file path for a trace."""
        date_str = trace.start_time.strftime("%Y-%m-%d")
        filename = f"{date_str}_{trace.execution_type}_{trace.name}.jsonl"
        return self.base_dir / filename

    async def record(self, trace: "ExecutionTrace") -> str:
        """Store a trace by appending to JSONL file."""
        file_path = self._get_file_path(trace)

        with open(file_path, "a") as f:
            f.write(trace.to_jsonl() + "\n")

        logger.debug(f"Recorded trace {trace.trace_id} to {file_path}")
        return trace.trace_id

    async def get(self, trace_id: str) -> "ExecutionTrace | None":
        """Retrieve a trace by ID (scans all files)."""
        from agent_framework.trace import ExecutionTrace

        for file_path in self.base_dir.glob("*.jsonl"):
            with open(file_path) as f:
                for line in f:
                    data = json.loads(line)
                    if data.get("trace_id") == trace_id:
                        return ExecutionTrace.model_validate(data)
        return None

    async def query(self, query: TraceQuery) -> list["ExecutionTrace"]:
        """Query traces from JSONL files."""
        from agent_framework.trace import ExecutionTrace

        results: list[ExecutionTrace] = []
        cutoff = None
        if query.since:
            cutoff = datetime.utcnow() - query.since

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
                        has_error = any(
                            s.status == "error" for s in trace.spans
                        )
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
        traces = await self.query(TraceQuery(
            skill_name=name,
            since=window,
            limit=1000,
        ))

        if not traces:
            return TraceMetrics()

        total = len(traces)
        successes = sum(
            1 for t in traces
            if not any(s.status == "error" for s in t.spans)
        )
        durations = [t.duration_ms for t in traces if t.duration_ms]
        tokens = [t.total_tokens for t in traces]

        return TraceMetrics(
            total_executions=total,
            success_rate=successes / total if total > 0 else 0.0,
            avg_duration_ms=sum(durations) / len(durations) if durations else 0.0,
            avg_tokens=sum(tokens) / len(tokens) if tokens else 0.0,
        )
```

**Step 5: Commit**

```bash
git add platform/agent-framework/src/agent_framework/backends/
git commit -m "feat(framework): add trace backend abstraction

Pluggable trace storage:
- TraceBackend abstract interface
- JsonlBackend for local development
- TraceQuery and TraceMetrics models

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Create SkillExecutor

**Files:**
- Create: `platform/agent-framework/src/agent_framework/skill_executor.py`

**Step 1: Create skill_executor.py**

```python
"""SkillExecutor - Run and evaluate skills in isolation."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agent_framework.backends.base import TraceBackend
from agent_framework.backends.jsonl import JsonlBackend
from agent_framework.config import SkillConfig
from agent_framework.trace import ExecutionTrace, SpanKind, TraceSpan

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class SkillExecutor:
    """
    Execute and evaluate skills in isolation.

    Provides a standardized way to run skills outside of a full agent,
    enabling rapid iteration and testing.

    Example:
        executor = SkillExecutor(skills_dir="agents/skills")

        # Run a skill
        result = await executor.execute(
            "investigate-pod-failure",
            context={"pod": "nginx-abc", "namespace": "default"},
        )

        # Run evaluation suite
        report = await executor.evaluate(
            "investigate-pod-failure",
            suite_path="agents/evaluations/k8s/pod_failure.yaml",
        )
    """

    def __init__(
        self,
        skills_dir: str | Path,
        trace_backend: TraceBackend | None = None,
        llm_client: Any = None,
        mcp_client: Any = None,
    ):
        """
        Initialize SkillExecutor.

        Args:
            skills_dir: Directory containing skill definitions
            trace_backend: Backend for storing traces (default: JsonlBackend)
            llm_client: LLM client for skill execution
            mcp_client: MCP client for tool calls
        """
        self.skills_dir = Path(skills_dir)
        self.trace_backend = trace_backend or JsonlBackend(
            self.skills_dir / ".traces"
        )
        self.llm_client = llm_client
        self.mcp_client = mcp_client

        # Cache loaded skills
        self._skills_cache: dict[str, Any] = {}

    async def load_skill(self, skill_name: str) -> dict[str, Any]:
        """
        Load a skill definition by name.

        Args:
            skill_name: Skill name (e.g., "k8s/investigate-pod-failure")

        Returns:
            Skill definition dict
        """
        if skill_name in self._skills_cache:
            return self._skills_cache[skill_name]

        # Try to find skill file
        skill_path = self._find_skill_path(skill_name)
        if not skill_path:
            raise ValueError(f"Skill not found: {skill_name}")

        # Load skill (assumes SKILL.md format with frontmatter)
        import frontmatter

        with open(skill_path) as f:
            post = frontmatter.load(f)

        skill = {
            "name": skill_name,
            "path": str(skill_path),
            "metadata": dict(post.metadata),
            "content": post.content,
        }

        self._skills_cache[skill_name] = skill
        return skill

    def _find_skill_path(self, skill_name: str) -> Path | None:
        """Find the path to a skill file."""
        # Try direct path
        direct = self.skills_dir / skill_name / "SKILL.md"
        if direct.exists():
            return direct

        # Try with category prefix removed
        parts = skill_name.split("/")
        if len(parts) > 1:
            for category_dir in self.skills_dir.iterdir():
                if category_dir.is_dir():
                    skill_file = category_dir / parts[-1] / "SKILL.md"
                    if skill_file.exists():
                        return skill_file

        # Search recursively
        for skill_file in self.skills_dir.rglob("SKILL.md"):
            if skill_name in str(skill_file):
                return skill_file

        return None

    async def execute(
        self,
        skill_name: str,
        context: dict[str, Any] | None = None,
        config: SkillConfig | None = None,
    ) -> ExecutionTrace:
        """
        Execute a skill with given context.

        Args:
            skill_name: Name of the skill to execute
            context: Context data for the skill
            config: Optional skill configuration

        Returns:
            Execution trace with results
        """
        config = config or SkillConfig(name=skill_name)
        context = context or {}

        # Create trace
        trace = ExecutionTrace(
            execution_type="skill",
            name=skill_name,
            input=context,
        )

        try:
            # Load skill
            skill = await self.load_skill(skill_name)
            trace.version = skill["metadata"].get("version", "unknown")

            # Create execution span
            exec_span = TraceSpan(
                name=f"skill.{skill_name}",
                kind=SpanKind.SKILL,
                attributes={
                    "skill.name": skill_name,
                    "skill.version": trace.version,
                },
            )
            trace.add_span(exec_span)

            # Execute skill logic
            # TODO: Integrate with actual LLM execution
            result = await self._execute_skill_logic(skill, context, trace)

            # End execution span
            exec_span.end()

            # Complete trace
            trace.end(output=result)

        except Exception as e:
            logger.exception(f"Skill execution failed: {skill_name}")
            trace.end(output={"error": str(e)})
            if trace.spans:
                trace.spans[-1].end(status="error", error=str(e))

        # Record trace
        if config.record_trace:
            await self.trace_backend.record(trace)

        return trace

    async def _execute_skill_logic(
        self,
        skill: dict[str, Any],
        context: dict[str, Any],
        trace: ExecutionTrace,
    ) -> dict[str, Any]:
        """
        Execute the actual skill logic.

        This is where LLM calls and tool use happen.
        """
        # Placeholder implementation
        # In real implementation, this would:
        # 1. Build prompt from skill content + context
        # 2. Call LLM with skill instructions
        # 3. Handle tool calls via MCP
        # 4. Record all spans to trace

        logger.info(f"Executing skill: {skill['name']}")

        # For now, return placeholder result
        return {
            "status": "executed",
            "skill": skill["name"],
            "context_keys": list(context.keys()),
            "note": "Placeholder - LLM integration pending",
        }

    async def evaluate(
        self,
        skill_name: str,
        suite_path: str | Path,
        model_matrix: dict[str, list[str]] | None = None,
    ) -> dict[str, Any]:
        """
        Run evaluation suite against a skill.

        Args:
            skill_name: Name of the skill to evaluate
            suite_path: Path to evaluation suite YAML
            model_matrix: Optional model comparison matrix
                          e.g., {"model": ["opus", "haiku"], "thinking": ["on", "off"]}

        Returns:
            Evaluation report
        """
        import yaml

        suite_path = Path(suite_path)
        if not suite_path.exists():
            raise FileNotFoundError(f"Evaluation suite not found: {suite_path}")

        with open(suite_path) as f:
            suite = yaml.safe_load(f)

        results = []
        test_cases = suite.get("test_cases", [])

        for case in test_cases:
            context = case.get("context", {})
            expected = case.get("expected", {})

            trace = await self.execute(skill_name, context=context)

            # Simple evaluation - check if output contains expected keys
            passed = all(
                k in trace.output for k in expected.keys()
            )

            results.append({
                "case": case.get("name", "unnamed"),
                "passed": passed,
                "trace_id": trace.trace_id,
                "duration_ms": trace.duration_ms,
                "tokens": trace.total_tokens,
            })

        # Aggregate results
        total = len(results)
        passed = sum(1 for r in results if r["passed"])

        return {
            "skill": skill_name,
            "suite": str(suite_path),
            "total_cases": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": passed / total if total > 0 else 0.0,
            "results": results,
        }

    async def get_recent_traces(
        self,
        skill_name: str,
        limit: int = 10,
    ) -> list[ExecutionTrace]:
        """Get recent traces for a skill."""
        from agent_framework.backends.base import TraceQuery

        return await self.trace_backend.query(
            TraceQuery(skill_name=skill_name, limit=limit)
        )
```

**Step 2: Commit**

```bash
git add platform/agent-framework/src/agent_framework/skill_executor.py
git commit -m "feat(framework): add SkillExecutor

Execute and evaluate skills in isolation:
- Load skills from filesystem
- Execute with context and trace recording
- Run evaluation suites with test cases
- Query recent traces

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Create AgentRunner

**Files:**
- Create: `platform/agent-framework/src/agent_framework/runner.py`

**Step 1: Create runner.py**

```python
"""AgentRunner - Run agents in local or cluster mode."""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import TYPE_CHECKING, Any

from agent_framework.config import AgentConfig, RunMode
from agent_framework.trace import ExecutionTrace, SpanKind, TraceSpan

if TYPE_CHECKING:
    from agent_framework.base import AgentBase

logger = logging.getLogger(__name__)


class AgentRunner:
    """
    Run agents in local or cluster mode.

    Provides a unified entry point for agent execution, handling:
    - Lifecycle management (initialize, run, shutdown)
    - Signal handling for graceful shutdown
    - Mode-specific behavior (local vs cluster)

    Example:
        # Local mode
        runner = AgentRunner(MyAgent, AgentConfig(name="my-agent"))
        await runner.run_local()

        # Single event
        result = await runner.handle_event({"type": "pod_crash", ...})

        # Cluster mode (Temporal worker)
        await runner.run_cluster()
    """

    def __init__(
        self,
        agent_class: type["AgentBase"],
        config: AgentConfig,
    ):
        """
        Initialize AgentRunner.

        Args:
            agent_class: The agent class to instantiate
            config: Agent configuration
        """
        self.agent_class = agent_class
        self.config = config
        self._agent: AgentBase | None = None
        self._shutdown_event: asyncio.Event | None = None

    @property
    def agent(self) -> "AgentBase":
        """Get the agent instance (creates if needed)."""
        if self._agent is None:
            self._agent = self.agent_class(self.config)
        return self._agent

    async def run_local(self) -> None:
        """
        Run agent in local mode (single process).

        Sets up signal handlers for graceful shutdown.
        """
        self._shutdown_event = asyncio.Event()

        # Set up signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(
                sig,
                lambda: asyncio.create_task(self._handle_shutdown()),
            )

        try:
            logger.info(f"Starting agent {self.config.name} in local mode")

            # Initialize
            await self.agent.initialize()
            self.agent._running = True

            # Run until shutdown
            run_task = asyncio.create_task(self.agent.run())
            shutdown_task = asyncio.create_task(self._shutdown_event.wait())

            done, pending = await asyncio.wait(
                [run_task, shutdown_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Cancel pending tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        finally:
            await self.agent.shutdown()
            logger.info(f"Agent {self.config.name} stopped")

    async def _handle_shutdown(self) -> None:
        """Handle shutdown signal."""
        logger.info("Shutdown signal received")
        if self._shutdown_event:
            self._shutdown_event.set()

    async def handle_event(
        self,
        event: dict[str, Any],
        trace: bool = True,
    ) -> ExecutionTrace:
        """
        Handle a single event and return trace.

        Useful for testing and one-off executions.

        Args:
            event: Event data to handle
            trace: Whether to record trace

        Returns:
            Execution trace with results
        """
        # Create trace
        exec_trace = ExecutionTrace(
            execution_type="agent",
            name=self.config.name,
            version=self.config.version,
            input=event,
        )

        # Create span
        span = TraceSpan(
            name=f"agent.{self.config.name}.handle_event",
            kind=SpanKind.AGENT,
            attributes={
                "event.type": event.get("type", "unknown"),
            },
        )
        exec_trace.add_span(span)

        try:
            # Ensure initialized
            if not self.agent._initialized:
                await self.agent.initialize()

            # Handle event
            result = await self.agent.handle_event(event)

            span.end()
            exec_trace.end(output=result)

        except Exception as e:
            logger.exception(f"Event handling failed: {e}")
            span.end(status="error", error=str(e))
            exec_trace.end(output={"error": str(e)})

        return exec_trace

    async def run_cluster(self) -> None:
        """
        Run agent in cluster mode (Temporal worker).

        Requires temporalio to be installed.
        """
        try:
            from temporalio.client import Client
            from temporalio.worker import Worker
        except ImportError:
            raise ImportError(
                "Temporal support requires 'temporalio' package. "
                "Install with: pip install agent-framework[temporal]"
            )

        # Get Temporal configuration
        from core_agents.config_unified import get_config

        kubani_config = get_config()

        # Connect to Temporal
        client = await Client.connect(
            kubani_config.temporal.host,
            namespace=kubani_config.temporal.namespace,
        )

        logger.info(
            f"Starting agent {self.config.name} in cluster mode "
            f"(Temporal: {kubani_config.temporal.host})"
        )

        # Initialize agent
        await self.agent.initialize()

        # Create worker
        # Note: Actual workflows/activities would be registered by the agent
        worker = Worker(
            client,
            task_queue=self.config.name,
            workflows=[],  # Agent provides these
            activities=[],  # Agent provides these
        )

        try:
            await worker.run()
        finally:
            await self.agent.shutdown()


def run_agent(
    agent_class: type["AgentBase"],
    config: AgentConfig | None = None,
    **config_kwargs: Any,
) -> None:
    """
    Convenience function to run an agent.

    Parses command-line arguments and runs in appropriate mode.

    Example:
        if __name__ == "__main__":
            run_agent(MyAgent, name="my-agent")
    """
    import argparse

    parser = argparse.ArgumentParser(description=f"Run agent")
    parser.add_argument(
        "--mode",
        choices=["local", "local-cluster", "cluster"],
        default="local",
        help="Execution mode",
    )
    parser.add_argument(
        "--event",
        type=str,
        help="JSON event to handle (single execution)",
    )

    args = parser.parse_args()

    # Build config
    mode_map = {
        "local": RunMode.LOCAL,
        "local-cluster": RunMode.LOCAL_CLUSTER,
        "cluster": RunMode.CLUSTER,
    }

    if config is None:
        config = AgentConfig(mode=mode_map[args.mode], **config_kwargs)
    else:
        config.mode = mode_map[args.mode]

    runner = AgentRunner(agent_class, config)

    async def main() -> None:
        if args.event:
            import json
            event = json.loads(args.event)
            trace = await runner.handle_event(event)
            print(trace.model_dump_json(indent=2))
        elif config.mode == RunMode.CLUSTER:
            await runner.run_cluster()
        else:
            await runner.run_local()

    asyncio.run(main())
```

**Step 2: Commit**

```bash
git add platform/agent-framework/src/agent_framework/runner.py
git commit -m "feat(framework): add AgentRunner

Run agents in local or cluster mode:
- run_local() with signal handling
- run_cluster() with Temporal worker
- handle_event() for single event execution
- run_agent() convenience function with CLI parsing

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Create Mixins

**Files:**
- Create: `platform/agent-framework/src/agent_framework/mixins/__init__.py`
- Create: `platform/agent-framework/src/agent_framework/mixins/mcp.py`
- Create: `platform/agent-framework/src/agent_framework/mixins/skills.py`
- Create: `platform/agent-framework/src/agent_framework/mixins/observability.py`

**Step 1: Create mixins directory**

```bash
mkdir -p platform/agent-framework/src/agent_framework/mixins
```

**Step 2: Create mixins/__init__.py**

```python
"""Composable agent mixins."""

from agent_framework.mixins.mcp import MCPClientMixin
from agent_framework.mixins.observability import ObservabilityMixin
from agent_framework.mixins.skills import SkillLoaderMixin

__all__ = [
    "MCPClientMixin",
    "ObservabilityMixin",
    "SkillLoaderMixin",
]
```

**Step 3: Create mixins/mcp.py**

```python
"""MCP Client Mixin - Connect to MCP servers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_framework.base import AgentBase

logger = logging.getLogger(__name__)


class MCPClientMixin:
    """
    Mixin for MCP server connectivity.

    Provides access to MCP servers (Temporal, Qdrant, Memory, Discord).
    Auto-discovers endpoints based on run mode (local vs cluster).

    Usage:
        class MyAgent(AgentBase, MCPClientMixin):
            async def initialize(self) -> None:
                await super().initialize()
                await self.init_mcp()

            async def run(self) -> None:
                workflows = await self.mcp.temporal.list_workflows()
    """

    async def init_mcp(self: "AgentBase") -> None:
        """Initialize MCP client connections."""
        from core_agents.mcp import get_mcp_client

        self._mcp_client = get_mcp_client()
        logger.info(f"MCP client initialized for {self.name}")

    @property
    def mcp(self: "AgentBase") -> Any:
        """Get the MCP client."""
        if self._mcp_client is None:
            raise RuntimeError(
                "MCP client not initialized. "
                "Call await self.init_mcp() in initialize()."
            )
        return self._mcp_client

    async def call_mcp_tool(
        self: "AgentBase",
        server: str,
        tool: str,
        **kwargs: Any,
    ) -> Any:
        """
        Call an MCP tool directly.

        Args:
            server: MCP server name (temporal, qdrant, memory, discord)
            tool: Tool name
            **kwargs: Tool arguments

        Returns:
            Tool result
        """
        server_client = getattr(self.mcp, server, None)
        if server_client is None:
            raise ValueError(f"Unknown MCP server: {server}")

        return await server_client.call_tool(tool, **kwargs)
```

**Step 4: Create mixins/skills.py**

```python
"""Skill Loader Mixin - Load and execute skills."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_framework.base import AgentBase
    from agent_framework.trace import ExecutionTrace

logger = logging.getLogger(__name__)


class SkillLoaderMixin:
    """
    Mixin for skill loading and execution.

    Provides access to skills from the skills directory.

    Usage:
        class MyAgent(AgentBase, SkillLoaderMixin):
            async def initialize(self) -> None:
                await super().initialize()
                await self.init_skills()

            async def run(self) -> None:
                trace = await self.execute_skill(
                    "investigate-pod-failure",
                    context={"pod": "nginx-abc"},
                )
    """

    async def init_skills(
        self: "AgentBase",
        skills_dir: str | Path | None = None,
    ) -> None:
        """
        Initialize skill loader.

        Args:
            skills_dir: Directory containing skills (default: agents/skills/)
        """
        from agent_framework.skill_executor import SkillExecutor

        if skills_dir is None:
            # Default to agents/skills/ relative to repo root
            skills_dir = Path(__file__).parents[5] / "agents" / "skills"

        self._skill_loader = SkillExecutor(
            skills_dir=skills_dir,
            llm_client=getattr(self, "_llm_client", None),
            mcp_client=getattr(self, "_mcp_client", None),
        )

        logger.info(f"Skills initialized from {skills_dir}")

    @property
    def skills(self: "AgentBase") -> Any:
        """Get the skill executor."""
        if self._skill_loader is None:
            raise RuntimeError(
                "Skills not initialized. "
                "Call await self.init_skills() in initialize()."
            )
        return self._skill_loader

    async def execute_skill(
        self: "AgentBase",
        skill_name: str,
        context: dict[str, Any] | None = None,
    ) -> "ExecutionTrace":
        """
        Execute a skill by name.

        Args:
            skill_name: Name of the skill
            context: Context data for the skill

        Returns:
            Execution trace
        """
        return await self.skills.execute(skill_name, context or {})

    async def list_skills(self: "AgentBase") -> list[str]:
        """List available skills."""
        skills_dir = self.skills.skills_dir
        skill_names = []

        for skill_file in skills_dir.rglob("SKILL.md"):
            # Extract skill name from path
            rel_path = skill_file.relative_to(skills_dir)
            skill_name = str(rel_path.parent)
            skill_names.append(skill_name)

        return sorted(skill_names)
```

**Step 5: Create mixins/observability.py**

```python
"""Observability Mixin - Structured logging, metrics, tracing."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from agent_framework.base import AgentBase

logger = logging.getLogger(__name__)


class ObservabilityMixin:
    """
    Mixin for observability (logging, metrics, tracing).

    Provides structured logging and trace context propagation.

    Usage:
        class MyAgent(AgentBase, ObservabilityMixin):
            async def initialize(self) -> None:
                await super().initialize()
                self.init_observability()

            async def run(self) -> None:
                self.log.info("Starting processing", event_count=10)
    """

    def init_observability(self: "AgentBase") -> None:
        """Initialize observability (structured logging)."""
        # Configure structlog
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )

        # Create bound logger for this agent
        self._log = structlog.get_logger(self.name)
        self._log = self._log.bind(
            agent_name=self.name,
            agent_version=self.version,
        )

        logger.info(f"Observability initialized for {self.name}")

    @property
    def log(self: "AgentBase") -> Any:
        """Get the structured logger."""
        if not hasattr(self, "_log") or self._log is None:
            # Fallback to standard logger
            return logging.getLogger(self.name)
        return self._log

    def log_event(
        self: "AgentBase",
        event: str,
        level: str = "info",
        **kwargs: Any,
    ) -> None:
        """
        Log a structured event.

        Args:
            event: Event name
            level: Log level (debug, info, warning, error)
            **kwargs: Additional context
        """
        log_method = getattr(self.log, level, self.log.info)
        log_method(event, **kwargs)
```

**Step 6: Commit**

```bash
git add platform/agent-framework/src/agent_framework/mixins/
git commit -m "feat(framework): add agent mixins

Composable capabilities for agents:
- MCPClientMixin: MCP server connectivity
- SkillLoaderMixin: Skill loading and execution
- ObservabilityMixin: Structured logging

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Create Example Agent

**Files:**
- Create: `platform/agent-framework/examples/simple_agent.py`

**Step 1: Create examples directory**

```bash
mkdir -p platform/agent-framework/examples
```

**Step 2: Create simple_agent.py**

```python
"""
Example: Simple Agent using the Agent Framework.

Demonstrates:
- AgentBase usage
- Mixin composition
- Local execution with AgentRunner

Run with:
    python examples/simple_agent.py --mode local
    python examples/simple_agent.py --event '{"type": "test"}'
"""

import asyncio
from typing import Any

from agent_framework import AgentBase, AgentRunner
from agent_framework.config import AgentConfig
from agent_framework.mixins import MCPClientMixin, ObservabilityMixin, SkillLoaderMixin


class SimpleAgent(AgentBase, ObservabilityMixin, SkillLoaderMixin):
    """
    A simple example agent demonstrating the framework.

    This agent:
    - Initializes observability and skills
    - Handles events by logging them
    - Can execute skills on demand
    """

    async def initialize(self) -> None:
        """Initialize the agent."""
        await super().initialize()

        # Initialize mixins
        self.init_observability()
        await self.init_skills()

        self.log.info("SimpleAgent initialized")

    async def run(self) -> None:
        """Main run loop - waits for shutdown."""
        self.log.info("SimpleAgent running, waiting for events...")

        # Simple example: just wait
        # In a real agent, this would poll for events or run workflows
        while self.running:
            await asyncio.sleep(1)

    async def handle_event(self, event: dict[str, Any]) -> dict[str, Any]:
        """Handle an incoming event."""
        event_type = event.get("type", "unknown")
        self.log.info("Handling event", event_type=event_type)

        # Example: execute a skill based on event type
        if event_type == "pod_crash":
            pod = event.get("pod", "unknown")
            namespace = event.get("namespace", "default")

            # Check if skill exists, execute if so
            available_skills = await self.list_skills()
            if "k8s/investigate-pod-failure" in available_skills:
                trace = await self.execute_skill(
                    "k8s/investigate-pod-failure",
                    context={"pod": pod, "namespace": namespace},
                )
                return {"handled": True, "trace_id": trace.trace_id}

        return {"handled": True, "event_type": event_type}

    async def shutdown(self) -> None:
        """Cleanup on shutdown."""
        self.log.info("SimpleAgent shutting down")
        await super().shutdown()


if __name__ == "__main__":
    from agent_framework.runner import run_agent

    run_agent(
        SimpleAgent,
        name="simple-agent",
        version="0.1.0",
        description="Example agent demonstrating the framework",
    )
```

**Step 3: Commit**

```bash
git add platform/agent-framework/examples/
git commit -m "feat(framework): add example agent

Simple example demonstrating:
- AgentBase usage
- Mixin composition (Observability, Skills)
- Event handling
- Local execution with AgentRunner

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 9: Create Framework Tests

**Files:**
- Create: `platform/agent-framework/tests/test_base.py`
- Create: `platform/agent-framework/tests/test_skill_executor.py`
- Create: `platform/agent-framework/tests/conftest.py`

**Step 1: Create conftest.py**

```python
"""Test fixtures for agent framework."""

import pytest
from pathlib import Path
import tempfile


@pytest.fixture
def temp_skills_dir():
    """Create a temporary skills directory with a test skill."""
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir)

        # Create a test skill
        test_skill_dir = skills_dir / "test" / "example-skill"
        test_skill_dir.mkdir(parents=True)

        skill_content = """---
name: example-skill
version: "1.0.0"
description: A test skill for unit tests
category: test
---

# Example Skill

This is a test skill used for unit testing.

## Steps

1. Log the input context
2. Return a success message
"""
        (test_skill_dir / "SKILL.md").write_text(skill_content)

        yield skills_dir


@pytest.fixture
def temp_trace_dir():
    """Create a temporary trace directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)
```

**Step 2: Create test_base.py**

```python
"""Tests for AgentBase."""

import pytest
from agent_framework import AgentBase
from agent_framework.config import AgentConfig, RunMode


class TestAgent(AgentBase):
    """Test agent implementation."""

    def __init__(self, config: AgentConfig):
        super().__init__(config)
        self.events_handled = []

    async def run(self) -> None:
        """Simple run that exits immediately."""
        pass

    async def handle_event(self, event: dict) -> dict:
        """Track handled events."""
        self.events_handled.append(event)
        return {"handled": True}


class TestAgentBase:
    """Tests for AgentBase class."""

    def test_agent_creation(self):
        """Test agent can be created with config."""
        config = AgentConfig(name="test-agent", version="1.0.0")
        agent = TestAgent(config)

        assert agent.name == "test-agent"
        assert agent.version == "1.0.0"
        assert agent.mode == RunMode.LOCAL
        assert not agent.running

    @pytest.mark.asyncio
    async def test_agent_lifecycle(self):
        """Test agent initialize/run/shutdown cycle."""
        config = AgentConfig(name="test-agent")
        agent = TestAgent(config)

        # Initialize
        await agent.initialize()
        assert agent._initialized

        # Run
        await agent.run()

        # Shutdown
        await agent.shutdown()
        assert not agent.running

    @pytest.mark.asyncio
    async def test_handle_event(self):
        """Test event handling."""
        config = AgentConfig(name="test-agent")
        agent = TestAgent(config)
        await agent.initialize()

        event = {"type": "test", "data": "hello"}
        result = await agent.handle_event(event)

        assert result == {"handled": True}
        assert event in agent.events_handled
```

**Step 3: Create test_skill_executor.py**

```python
"""Tests for SkillExecutor."""

import pytest
from agent_framework.skill_executor import SkillExecutor


class TestSkillExecutor:
    """Tests for SkillExecutor class."""

    def test_executor_creation(self, temp_skills_dir):
        """Test executor can be created."""
        executor = SkillExecutor(skills_dir=temp_skills_dir)
        assert executor.skills_dir == temp_skills_dir

    @pytest.mark.asyncio
    async def test_load_skill(self, temp_skills_dir):
        """Test skill loading."""
        executor = SkillExecutor(skills_dir=temp_skills_dir)

        skill = await executor.load_skill("test/example-skill")

        assert skill["name"] == "test/example-skill"
        assert "metadata" in skill
        assert skill["metadata"]["version"] == "1.0.0"

    @pytest.mark.asyncio
    async def test_execute_skill(self, temp_skills_dir):
        """Test skill execution."""
        executor = SkillExecutor(skills_dir=temp_skills_dir)

        trace = await executor.execute(
            "test/example-skill",
            context={"key": "value"},
        )

        assert trace.name == "test/example-skill"
        assert trace.input == {"key": "value"}
        assert trace.trace_id is not None
        assert len(trace.spans) > 0

    @pytest.mark.asyncio
    async def test_skill_not_found(self, temp_skills_dir):
        """Test error when skill not found."""
        executor = SkillExecutor(skills_dir=temp_skills_dir)

        with pytest.raises(ValueError, match="Skill not found"):
            await executor.load_skill("nonexistent-skill")
```

**Step 4: Commit**

```bash
git add platform/agent-framework/tests/
git commit -m "test(framework): add framework tests

Tests for core framework components:
- AgentBase lifecycle and event handling
- SkillExecutor loading and execution
- Test fixtures for temp directories

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 10: Update Package Exports

**Files:**
- Modify: `platform/agent-framework/src/agent_framework/__init__.py`

**Step 1: Update __init__.py with all exports**

```python
"""
Agent Framework - Local-first, cluster-ready agent development.

Core abstractions:
- AgentBase: Base class for all agents
- SkillExecutor: Run and evaluate skills in isolation
- AgentRunner: Run agents in local or cluster mode
- Mixins: Composable capabilities (MCP, Skills, Memory, etc.)

Example:
    from agent_framework import AgentBase, AgentRunner
    from agent_framework.config import AgentConfig
    from agent_framework.mixins import SkillLoaderMixin, ObservabilityMixin

    class MyAgent(AgentBase, SkillLoaderMixin, ObservabilityMixin):
        async def initialize(self) -> None:
            await super().initialize()
            await self.init_skills()
            self.init_observability()

        async def run(self) -> None:
            while self.running:
                await self.process_next()

    if __name__ == "__main__":
        from agent_framework.runner import run_agent
        run_agent(MyAgent, name="my-agent")
"""

from agent_framework.base import AgentBase
from agent_framework.config import AgentConfig, RunMode, SkillConfig
from agent_framework.runner import AgentRunner, run_agent
from agent_framework.skill_executor import SkillExecutor
from agent_framework.trace import ExecutionTrace, SpanKind, TraceSpan

__all__ = [
    # Core classes
    "AgentBase",
    "AgentRunner",
    "SkillExecutor",
    # Config
    "AgentConfig",
    "RunMode",
    "SkillConfig",
    # Trace
    "ExecutionTrace",
    "TraceSpan",
    "SpanKind",
    # Convenience
    "run_agent",
]

__version__ = "0.1.0"
```

**Step 2: Commit**

```bash
git add platform/agent-framework/src/agent_framework/__init__.py
git commit -m "feat(framework): update package exports

Export all core classes and utilities from package root.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 11: Run Framework Tests

**Step 1: Install framework in development mode**

```bash
cd platform/agent-framework
pip install -e ".[dev]"
```

**Step 2: Run tests**

```bash
cd platform/agent-framework
pytest tests/ -v
```

Expected: All tests pass

**Step 3: Fix any failures and commit**

```bash
# If tests pass:
git status
# Commit any fixes if needed
```

---

## Task 12: Final Verification

**Step 1: Verify package structure**

```bash
ls -la platform/agent-framework/src/agent_framework/
```

Expected:
```
__init__.py
backends/
base.py
config.py
mixins/
runner.py
skill_executor.py
trace.py
```

**Step 2: Verify imports work**

```bash
python -c "from agent_framework import AgentBase, AgentRunner, SkillExecutor; print('OK')"
```

**Step 3: Run example agent**

```bash
cd platform/agent-framework
python examples/simple_agent.py --event '{"type": "test"}'
```

Expected: JSON output with trace

**Step 4: Review commits**

```bash
git log --oneline feature/restructure ^main | head -15
```

---

## Post-Phase 2 Checklist

- [ ] Package structure complete (`platform/agent-framework/`)
- [ ] Core classes implemented (AgentBase, AgentRunner, SkillExecutor)
- [ ] Trace models with OTEL compatibility
- [ ] Trace backends (JsonlBackend)
- [ ] Mixins implemented (MCP, Skills, Observability)
- [ ] Example agent works
- [ ] Tests pass
- [ ] Package importable

---

## Notes

- The framework is designed to be **additive** - existing agents can continue using current patterns
- Migration to the framework will happen in Phase 5 (Agent Consolidation)
- LLM integration in SkillExecutor is placeholder - will be connected to actual LLM client
- Temporal integration requires `temporalio` optional dependency
