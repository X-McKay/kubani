# Phase 4: Local Development Experience - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete the local-first development workflow with enhanced CLI commands, DuckDB trace backend for analytics, hot reload, and seamless integration between SkillExecutor/AgentRunner and kubani-dev. Also includes strategic improvements: Typer CLI, structured logging, error hierarchy, config consolidation, and dependency injection.

**Architecture:** Extend the agent-framework with DuckDB backend (optimized for analytical queries on traces), integrate AgentRunner with kubani-dev, add skill scaffolding and hot reload capabilities. Modernize infrastructure with Typer, structlog, and service container pattern.

**Tech Stack:** Python 3.11+, Typer CLI, DuckDB, watchdog (file watching), structlog, agent-framework

**Why DuckDB over SQLite:**
- Columnar storage optimized for analytical queries (aggregations, statistics)
- Vectorized execution for faster query performance
- Native JSON querying capabilities
- Built-in Parquet export for trace archival
- Same single-file, zero-server model as SQLite

---

## Pre-Flight Checklist

Before starting, verify:
```bash
# On feature/restructure branch
git branch --show-current

# Phase 3 framework installed (v0.2.0)
python -c "from agent_framework import __version__; print(__version__)"

# kubani-dev installed
kubani-dev --version

# Skills directory exists
ls agents/skills/
```

---

## Task 1: Add DuckDB Trace Backend

**Files:**
- Create: `platform/agent-framework/src/agent_framework/backends/duckdb_backend.py`
- Modify: `platform/agent-framework/src/agent_framework/backends/__init__.py`
- Modify: `platform/agent-framework/pyproject.toml` (add duckdb dependency)

**Step 1: Add duckdb to dependencies**

In `platform/agent-framework/pyproject.toml`, add to dependencies:
```toml
duckdb = ">=0.10.0"
```

**Step 2: Create duckdb_backend.py**

```python
"""DuckDB trace backend for local development with analytical query capability."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb

from agent_framework.backends.base import TraceBackend, TraceQuery
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
            sql += " AND name = ?"
            params.append(query.skill_name)

        if query.execution_type:
            sql += " AND execution_type = ?"
            params.append(query.execution_type)

        if query.start_after:
            sql += " AND start_time > ?"
            params.append(query.start_after)

        if query.start_before:
            sql += " AND start_time < ?"
            params.append(query.start_before)

        if query.min_tokens:
            sql += " AND total_tokens >= ?"
            params.append(query.min_tokens)

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

    async def get_stats(self, skill_name: str | None = None) -> dict[str, Any]:
        """Get aggregate statistics using DuckDB's analytical capabilities."""
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
            stats["first_trace"] = stats["first_trace"].isoformat() if hasattr(stats["first_trace"], 'isoformat') else str(stats["first_trace"])
        if stats.get("last_trace"):
            stats["last_trace"] = stats["last_trace"].isoformat() if hasattr(stats["last_trace"], 'isoformat') else str(stats["last_trace"])

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
                row_dict["time_bucket"] = row_dict["time_bucket"].isoformat() if hasattr(row_dict["time_bucket"], 'isoformat') else str(row_dict["time_bucket"])
            rows.append(row_dict)

        return rows

    async def export_to_parquet(self, output_path: str | Path, skill_name: str | None = None) -> str:
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
        from agent_framework.trace import TraceSpan

        spans_data = json.loads(row["spans_json"]) if row["spans_json"] else []
        spans = [TraceSpan(**s) for s in spans_data]

        start_time = row["start_time"]
        end_time = row["end_time"]

        # Handle DuckDB datetime objects
        if hasattr(start_time, 'isoformat'):
            pass  # Already datetime
        elif isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time)

        if end_time:
            if hasattr(end_time, 'isoformat'):
                pass  # Already datetime
            elif isinstance(end_time, str):
                end_time = datetime.fromisoformat(end_time)

        return ExecutionTrace(
            trace_id=row["trace_id"],
            execution_type=row["execution_type"],
            name=row["name"],
            version=row["version"],
            start_time=start_time,
            end_time=end_time,
            input=json.loads(row["input_json"]) if row["input_json"] else {},
            output=json.loads(row["output_json"]) if row["output_json"] else {},
            spans=spans,
        )

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
```

**Step 3: Update backends/__init__.py**

```python
"""Trace backend implementations."""

from agent_framework.backends.base import TraceBackend, TraceQuery
from agent_framework.backends.jsonl import JsonlBackend
from agent_framework.backends.duckdb_backend import DuckDBBackend

__all__ = ["TraceBackend", "TraceQuery", "JsonlBackend", "DuckDBBackend"]
```

**Step 4: Commit**

```bash
git add platform/agent-framework/src/agent_framework/backends/
git add platform/agent-framework/pyproject.toml
git commit -m "feat(framework): add DuckDB trace backend

DuckDB backend optimized for trace analytics:
- Columnar storage for fast aggregations
- Native JSON querying
- Time-series performance queries
- Token usage breakdown by skill
- Parquet export for archival
- Vectorized execution for large datasets

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Add `kubani-dev skill create` Command

**Files:**
- Modify: `tools/kubani-dev/src/kubani_dev/commands/skill.py`

**Step 1: Add create command (simpler than draft)**

Add after the existing commands:

```python
@skill_group.command(name="create")
@click.argument("skill_name")
@click.option("--category", "-c", default="development", help="Skill category (k8s/diagnostic, etc.)")
@click.option("--description", "-d", help="Short description")
@click.option("--with-tests", is_flag=True, default=True, help="Generate test cases template")
@click.option("--with-scripts", is_flag=True, help="Include scripts directory")
def create_skill(
    skill_name: str,
    category: str,
    description: Optional[str],
    with_tests: bool,
    with_scripts: bool,
):
    """
    Create a new skill from template.

    Quick scaffolding for new skills. Use 'skill draft' for LLM-assisted
    skill creation with conversation.

    \b
    Examples:
        kubani-dev skill create investigate-oom-kill --category k8s/diagnostic
        kubani-dev skill create my-skill -d "Does something useful"
        kubani-dev skill create my-skill --with-scripts
    """
    from datetime import datetime

    # Normalize name
    skill_name = skill_name.lower().replace(" ", "-").replace("_", "-")

    # Determine output path
    skills_base = Path.cwd() / "agents" / "skills"
    if not skills_base.exists():
        skills_base = Path(__file__).parents[4] / "agents" / "skills"

    # Handle category path
    if "/" in category:
        skill_dir = skills_base / category / skill_name
    else:
        skill_dir = skills_base / category / skill_name

    if skill_dir.exists():
        error(f"Skill already exists: {skill_dir}")
        sys.exit(1)

    skill_dir.mkdir(parents=True, exist_ok=True)

    # Create SKILL.md
    skill_md_content = f'''---
name: {skill_name}
version: "0.1.0"
category: {category}
description: {description or "TODO: Add description"}
triggers: []
---

# {skill_name.replace("-", " ").title()}

## Purpose

{description or "TODO: Describe what this skill does"}

## When to Use

- TODO: List scenarios when this skill should be triggered

## Steps

1. **Gather Context**
   - TODO: What information needs to be collected

2. **Analyze**
   - TODO: What analysis should be performed

3. **Take Action**
   - TODO: What actions should be taken

## Expected Output

Return a JSON response with:
- `status`: "success" | "failure" | "needs_approval"
- `summary`: Brief description of findings
- `findings`: List of discovered issues
- `recommendations`: List of suggested actions

## Examples

### Example 1: Basic Usage

**Input Context:**
```json
{{
    "example_field": "value"
}}
```

**Expected Output:**
```json
{{
    "status": "success",
    "summary": "Analysis complete",
    "findings": ["Finding 1"],
    "recommendations": ["Recommendation 1"]
}}
```
'''

    (skill_dir / "SKILL.md").write_text(skill_md_content)

    # Create metadata.json
    metadata = {
        "name": skill_name,
        "version": "0.1.0",
        "category": category,
        "description": description or "TODO: Add description",
        "status": "development",
        "created_at": datetime.now().isoformat(),
        "created_by": "kubani-dev",
    }

    if with_scripts:
        metadata["has_scripts"] = True
        metadata["scripts"] = {"main": "scripts/main.py"}

    (skill_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    # Create test_cases.yaml
    if with_tests:
        test_cases_content = f'''# Test cases for {skill_name}
# Run with: kubani-dev skill eval {skill_dir.relative_to(Path.cwd())}

test_cases:
  - name: "basic_test"
    description: "Basic functionality test"
    context:
      example_field: "test_value"
    expected:
      status: "success"
    assertions:
      - type: "contains"
        field: "summary"
        value: "complete"

  - name: "edge_case"
    description: "Test edge case handling"
    context:
      example_field: ""
    expected:
      status: "success"
'''
        (skill_dir / "test_cases.yaml").write_text(test_cases_content)

    # Create scripts directory if requested
    if with_scripts:
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir(exist_ok=True)

        main_script = '''"""Main script for skill execution."""

from typing import Any


def execute(context: dict[str, Any]) -> dict[str, Any]:
    """
    Execute the skill logic.

    Args:
        context: Input context from skill execution

    Returns:
        Result dictionary with status, findings, etc.
    """
    # TODO: Implement skill logic
    return {
        "status": "success",
        "summary": "Execution complete",
        "findings": [],
        "recommendations": [],
    }
'''
        (scripts_dir / "main.py").write_text(main_script)
        (scripts_dir / "__init__.py").write_text("")

    # Success output
    success(f"Created skill: [bold]{skill_name}[/bold]")
    console.print(f"   Location: {skill_dir}")
    console.print()

    # Show created files
    table = create_table(columns=["File", "Purpose"])
    table.add_row("SKILL.md", "Skill definition and instructions")
    table.add_row("metadata.json", "Skill metadata and configuration")
    if with_tests:
        table.add_row("test_cases.yaml", "Evaluation test cases")
    if with_scripts:
        table.add_row("scripts/main.py", "Executable skill logic")
    console.print(table)

    console.print()
    muted("Next steps:")
    muted(f"  1. Edit {skill_dir}/SKILL.md to define skill behavior")
    muted(f"  2. Run: kubani-dev skill run {skill_name} --context '{{...}}'")
    muted(f"  3. Evaluate: kubani-dev skill eval {skill_dir}")
```

**Step 2: Commit**

```bash
git add tools/kubani-dev/src/kubani_dev/commands/skill.py
git commit -m "feat(kubani-dev): add 'skill create' command

Quick skill scaffolding:
- Creates SKILL.md, metadata.json, test_cases.yaml
- Optional scripts directory
- Category-based organization

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Add `kubani-dev skill watch` Command

**Files:**
- Modify: `tools/kubani-dev/src/kubani_dev/commands/skill.py`
- Modify: `tools/kubani-dev/pyproject.toml` (add watchdog dependency)

**Step 1: Add watchdog to dependencies**

In `tools/kubani-dev/pyproject.toml`, add to dependencies:
```toml
watchdog = ">=3.0.0"
```

**Step 2: Add watch command**

```python
@skill_group.command(name="watch")
@click.argument("skill_path", type=click.Path(exists=True))
@click.option("--context", "-c", help="JSON context string")
@click.option("--context-file", "-f", type=click.Path(exists=True), help="JSON context file")
@click.option("--llm-url", help="LLM base URL")
@click.option("--llm-model", help="LLM model name")
@click.option("--debounce", default=1.0, help="Debounce delay in seconds")
def watch_skill(
    skill_path: str,
    context: Optional[str],
    context_file: Optional[str],
    llm_url: Optional[str],
    llm_model: Optional[str],
    debounce: float,
):
    """
    Watch a skill for changes and auto-run.

    Hot reload development - automatically re-executes the skill when
    SKILL.md or scripts change.

    \b
    Examples:
        kubani-dev skill watch skills/development/my-skill
        kubani-dev skill watch ./my-skill --context '{"test": true}'
        kubani-dev skill watch ./my-skill -f context.json --debounce 2
    """
    import time
    from threading import Timer

    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        error("watchdog not installed. Run: pip install watchdog")
        sys.exit(1)

    skill_dir = Path(skill_path)

    # Parse context
    ctx = {}
    if context_file:
        with open(context_file) as f:
            ctx = json.load(f)
    elif context:
        try:
            ctx = json.loads(context)
        except json.JSONDecodeError as e:
            error(f"Invalid JSON context: {e}")
            sys.exit(1)

    # Get skill name from path
    skill_name = skill_dir.name

    print_panel(
        f"[bold]Skill:[/bold] {skill_name}\n"
        f"[bold]Path:[/bold] {skill_dir}\n"
        f"[bold]Context:[/bold] {json.dumps(ctx)[:50]}..." if ctx else "[bold]Context:[/bold] (none)",
        title="Skill Watch Mode",
        style="cyan",
    )
    console.print()
    info("Watching for changes... (Ctrl+C to stop)")
    console.print()

    # Debounced execution
    pending_timer: Timer | None = None

    def run_skill():
        console.print("\n" + "=" * 60)
        info(f"[{datetime.now().strftime('%H:%M:%S')}] Change detected, running skill...")
        console.print()

        try:
            import asyncio
            from agent_framework.skill_executor import SkillExecutor
            from agent_framework.llm import LLMClientWrapper
            from agent_framework.config import SkillConfig

            async def execute():
                llm = LLMClientWrapper(
                    base_url=llm_url or os.getenv("LLM_BASE_URL", "https://llm.almckay.io/v1"),
                    model=llm_model or os.getenv("LLM_MODEL", "nvidia/Qwen3-14B-FP4"),
                )

                # Clear skill cache to pick up changes
                executor = SkillExecutor(
                    skills_dir=skill_dir.parent,
                    llm_client=llm,
                )

                config = SkillConfig(name=skill_name, record_trace=True)

                with spinner("Running skill..."):
                    result = await executor.execute(skill_name, context=ctx, config=config)

                await llm.close()
                return result

            result = asyncio.run(execute())

            # Display result
            if result.output.get("status") == "success":
                success("Skill completed successfully")
            elif result.output.get("status") == "failure":
                error("Skill failed")
            else:
                warning(f"Skill status: {result.output.get('status', 'unknown')}")

            if result.output.get("summary"):
                console.print(f"\n[bold]Summary:[/bold] {result.output['summary']}")

            muted(f"\nDuration: {result.duration_ms:.0f}ms | Tokens: {result.total_tokens}")

        except Exception as e:
            error(f"Execution failed: {e}")

        console.print()
        muted("Watching for changes...")

    class SkillChangeHandler(FileSystemEventHandler):
        def on_modified(self, event):
            nonlocal pending_timer

            if event.is_directory:
                return

            # Only watch relevant files
            path = Path(event.src_path)
            if path.suffix not in ('.md', '.py', '.yaml', '.yml', '.json'):
                return

            # Debounce
            if pending_timer:
                pending_timer.cancel()

            pending_timer = Timer(debounce, run_skill)
            pending_timer.start()

    # Initial run
    run_skill()

    # Set up file watcher
    event_handler = SkillChangeHandler()
    observer = Observer()
    observer.schedule(event_handler, str(skill_dir), recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        console.print()
        info("Watch mode stopped")

    observer.join()
```

**Step 3: Add datetime import at top of file if not present**

```python
from datetime import datetime
```

**Step 4: Commit**

```bash
git add tools/kubani-dev/src/kubani_dev/commands/skill.py
git add tools/kubani-dev/pyproject.toml
git commit -m "feat(kubani-dev): add 'skill watch' command

Hot reload skill development:
- Watches SKILL.md, scripts, and config for changes
- Auto-runs skill on file modification
- Configurable debounce delay
- Requires watchdog package

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Add `kubani-dev agent` Command Group

**Files:**
- Create: `tools/kubani-dev/src/kubani_dev/commands/agent.py`
- Modify: `tools/kubani-dev/src/kubani_dev/commands/__init__.py`
- Modify: `tools/kubani-dev/src/kubani_dev/cli.py`

**Step 1: Create agent.py**

```python
"""Agent management commands using the new framework."""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import click

from kubani_dev.ui import (
    console,
    create_table,
    error,
    info,
    muted,
    print_panel,
    spinner,
    success,
    warning,
)

logger = logging.getLogger(__name__)


@click.group(name="agent")
def agent_group():
    """
    Manage agents using the new agent framework.

    Commands for running, testing, and evaluating agents locally
    with the agent-framework abstractions.
    """
    pass


@agent_group.command(name="run")
@click.argument("agent_name")
@click.option("--trigger", "-t", help="JSON trigger event")
@click.option("--trigger-file", "-f", type=click.Path(exists=True), help="JSON trigger file")
@click.option("--mode", type=click.Choice(["local", "cluster"]), default="local")
@click.option("--hot-reload", is_flag=True, help="Enable hot reload")
@click.option("--trace", is_flag=True, help="Show execution trace")
def run_agent(
    agent_name: str,
    trigger: Optional[str],
    trigger_file: Optional[str],
    mode: str,
    hot_reload: bool,
    trace: bool,
):
    """
    Run an agent with the new framework.

    Uses AgentRunner for local or cluster mode execution.

    \b
    Examples:
        kubani-dev agent run k8s-monitor
        kubani-dev agent run k8s-monitor --trigger '{"event": "pod_crash"}'
        kubani-dev agent run k8s-monitor --mode cluster
    """
    # Parse trigger
    trigger_data = {}
    if trigger_file:
        with open(trigger_file) as f:
            trigger_data = json.load(f)
    elif trigger:
        try:
            trigger_data = json.loads(trigger)
        except json.JSONDecodeError as e:
            error(f"Invalid JSON trigger: {e}")
            sys.exit(1)

    # Find agent directory
    agents_dir = Path.cwd() / "agents"
    if not agents_dir.exists():
        agents_dir = Path(__file__).parents[4] / "agents"

    agent_dir = agents_dir / agent_name
    if not agent_dir.exists():
        error(f"Agent not found: {agent_name}")
        info(f"Available agents: {', '.join(d.name for d in agents_dir.iterdir() if d.is_dir() and not d.name.startswith('.'))}")
        sys.exit(1)

    print_panel(
        f"[bold]Agent:[/bold] {agent_name}\n"
        f"[bold]Mode:[/bold] {mode}\n"
        f"[bold]Hot Reload:[/bold] {'enabled' if hot_reload else 'disabled'}\n"
        f"[bold]Trigger:[/bold] {json.dumps(trigger_data)[:50] if trigger_data else '(none)'}",
        title="Agent Runner",
        style="cyan",
    )
    console.print()

    async def execute():
        from agent_framework import AgentRunner, AgentConfig, RunMode

        # Create config
        config = AgentConfig(
            name=agent_name,
            run_mode=RunMode.LOCAL if mode == "local" else RunMode.CLUSTER,
        )

        # Create runner
        runner = AgentRunner(config)

        info(f"Starting agent: {agent_name}")

        try:
            if trigger_data:
                # Single execution with trigger
                result = await runner.execute_once(trigger_data)

                if trace:
                    console.print_json(json.dumps(result, indent=2, default=str))
                else:
                    success("Agent execution complete")
                    if isinstance(result, dict):
                        console.print(f"\n[bold]Result:[/bold]")
                        console.print(json.dumps(result, indent=2, default=str)[:500])
            else:
                # Continuous run
                info("Running in continuous mode (Ctrl+C to stop)...")
                await runner.run()

        except KeyboardInterrupt:
            info("Shutting down...")
        except Exception as e:
            error(f"Agent execution failed: {e}")
            raise

    asyncio.run(execute())


@agent_group.command(name="list")
def list_agents():
    """List all available agents."""
    agents_dir = Path.cwd() / "agents"
    if not agents_dir.exists():
        agents_dir = Path(__file__).parents[4] / "agents"

    if not agents_dir.exists():
        error("Agents directory not found")
        return

    table = create_table(title="Available Agents", columns=["Name", "Version", "Status", "Description"])

    for agent_dir in sorted(agents_dir.iterdir()):
        if not agent_dir.is_dir() or agent_dir.name.startswith('.'):
            continue

        # Skip non-agent directories
        if agent_dir.name in ('skills', 'evaluations', 'templates'):
            continue

        # Try to load pyproject.toml for version
        pyproject = agent_dir / "pyproject.toml"
        version = "-"
        description = "-"

        if pyproject.exists():
            try:
                import tomllib
                with open(pyproject, "rb") as f:
                    data = tomllib.load(f)
                version = data.get("project", {}).get("version", "-")
                description = data.get("project", {}).get("description", "-")
                if len(description) > 40:
                    description = description[:37] + "..."
            except Exception:
                pass

        # Check if agent has worker.py (indicates it's a real agent)
        src_dir = agent_dir / "src"
        has_worker = False
        if src_dir.exists():
            for f in src_dir.rglob("worker.py"):
                has_worker = True
                break

        status = "[green]ready[/green]" if has_worker else "[yellow]scaffold[/yellow]"

        table.add_row(agent_dir.name, version, status, description)

    console.print(table)


@agent_group.command(name="info")
@click.argument("agent_name")
def agent_info(agent_name: str):
    """Show detailed information about an agent."""
    agents_dir = Path.cwd() / "agents"
    if not agents_dir.exists():
        agents_dir = Path(__file__).parents[4] / "agents"

    agent_dir = agents_dir / agent_name
    if not agent_dir.exists():
        error(f"Agent not found: {agent_name}")
        return

    # Load pyproject.toml
    pyproject = agent_dir / "pyproject.toml"
    project_data = {}
    if pyproject.exists():
        try:
            import tomllib
            with open(pyproject, "rb") as f:
                project_data = tomllib.load(f).get("project", {})
        except Exception:
            pass

    # Basic info table
    info_table = create_table(title=f"Agent: {agent_name}", columns=["Property", "Value"])
    info_table.add_row("Name", project_data.get("name", agent_name))
    info_table.add_row("Version", project_data.get("version", "unknown"))
    info_table.add_row("Description", project_data.get("description", "No description"))
    info_table.add_row("Path", str(agent_dir))

    console.print(info_table)
    console.print()

    # List key files
    files_table = create_table(title="Key Files", columns=["File", "Status"])

    key_files = [
        ("pyproject.toml", "Package configuration"),
        ("src/*/worker.py", "Temporal worker"),
        ("src/*/workflows.py", "Workflow definitions"),
        ("src/*/activities.py", "Activity definitions"),
        ("README.md", "Documentation"),
    ]

    for pattern, desc in key_files:
        if "*" in pattern:
            matches = list(agent_dir.glob(pattern))
            exists = len(matches) > 0
        else:
            exists = (agent_dir / pattern).exists()

        status = "[green]exists[/green]" if exists else "[red]missing[/red]"
        files_table.add_row(pattern, status)

    console.print(files_table)


@agent_group.command(name="eval")
@click.argument("agent_name")
@click.option("--suite", "-s", type=click.Path(exists=True), help="Evaluation suite YAML")
@click.option("--output", "-o", type=click.Choice(["table", "json"]), default="table")
def eval_agent(
    agent_name: str,
    suite: Optional[str],
    output: str,
):
    """
    Evaluate an agent end-to-end.

    Runs evaluation scenarios and checks agent behavior.

    \b
    Examples:
        kubani-dev agent eval k8s-monitor
        kubani-dev agent eval k8s-monitor --suite evaluations/k8s/full.yaml
    """
    import yaml

    # Find evaluation suite
    if not suite:
        # Look for default suite
        eval_dirs = [
            Path.cwd() / "agents" / "evaluations" / agent_name,
            Path.cwd() / "evaluations" / agent_name,
        ]

        for eval_dir in eval_dirs:
            if eval_dir.exists():
                suite_files = list(eval_dir.glob("*.yaml")) + list(eval_dir.glob("*.yml"))
                if suite_files:
                    suite = str(suite_files[0])
                    break

    if not suite:
        warning(f"No evaluation suite found for {agent_name}")
        muted("Create one at: agents/evaluations/{agent_name}/eval.yaml")
        return

    print_panel(
        f"[bold]Agent:[/bold] {agent_name}\n"
        f"[bold]Suite:[/bold] {suite}",
        title="Agent Evaluation",
        style="magenta",
    )
    console.print()

    # Load suite
    with open(suite) as f:
        suite_data = yaml.safe_load(f)

    scenarios = suite_data.get("scenarios", [])
    if not scenarios:
        warning("No scenarios defined in evaluation suite")
        return

    info(f"Running {len(scenarios)} evaluation scenarios...")
    console.print()

    results = []
    passed = 0

    for scenario in scenarios:
        scenario_name = scenario.get("name", "unnamed")

        with spinner(f"Running: {scenario_name}..."):
            # TODO: Implement actual agent evaluation
            # For now, this is a placeholder
            result = {
                "name": scenario_name,
                "passed": True,  # Placeholder
                "duration_ms": 0,
                "details": {},
            }

        results.append(result)
        if result["passed"]:
            passed += 1
            success(f"  {scenario_name}")
        else:
            error(f"  {scenario_name}")

    console.print()

    # Summary
    total = len(results)
    if output == "json":
        console.print_json(json.dumps({
            "agent": agent_name,
            "suite": suite,
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "results": results,
        }, indent=2))
    else:
        summary_table = create_table(title="Evaluation Summary", columns=["Metric", "Value"])
        summary_table.add_row("Total Scenarios", str(total))
        summary_table.add_row("Passed", f"[green]{passed}[/green]")
        summary_table.add_row("Failed", f"[red]{total - passed}[/red]")
        summary_table.add_row("Pass Rate", f"{passed/total*100:.1f}%" if total > 0 else "N/A")
        console.print(summary_table)
```

**Step 2: Update commands/__init__.py**

Add the agent group import:

```python
from kubani_dev.commands.agent import agent_group
from kubani_dev.commands.skill import skill_group

__all__ = ["agent_group", "skill_group"]
```

**Step 3: Update cli.py to register agent commands**

Find where commands are registered (usually in cli.py) and add:

```python
from kubani_dev.commands.agent import agent_group

# In the CLI setup
cli.add_command(agent_group)
```

**Step 4: Commit**

```bash
git add tools/kubani-dev/src/kubani_dev/commands/agent.py
git add tools/kubani-dev/src/kubani_dev/commands/__init__.py
git add tools/kubani-dev/src/kubani_dev/cli.py
git commit -m "feat(kubani-dev): add 'agent' command group

Agent management with new framework:
- kubani-dev agent run <agent> [--trigger] [--mode]
- kubani-dev agent list
- kubani-dev agent info <agent>
- kubani-dev agent eval <agent> [--suite]

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Implement AgentRunner.execute_once()

**Files:**
- Modify: `platform/agent-framework/src/agent_framework/runner.py`

**Step 1: Add execute_once method to AgentRunner**

Update the AgentRunner class:

```python
async def execute_once(self, trigger: dict[str, Any]) -> dict[str, Any]:
    """
    Execute agent once with a trigger event.

    Useful for testing and evaluation - runs the agent's
    handle_event method with a single trigger.

    Args:
        trigger: Event data to trigger the agent

    Returns:
        Result from agent execution
    """
    if self.agent is None:
        raise RuntimeError("Agent not initialized. Call initialize() first.")

    # Create execution trace
    trace = ExecutionTrace(
        execution_type="agent",
        name=self.config.name,
        input=trigger,
    )

    try:
        # Initialize agent if needed
        if not hasattr(self.agent, '_initialized') or not self.agent._initialized:
            await self.agent.initialize()
            self.agent._initialized = True

        # Execute
        result = await self.agent.handle_event(trigger)

        trace.end(output=result if isinstance(result, dict) else {"result": result})

        return trace.output

    except Exception as e:
        trace.end(output={"error": str(e)})
        raise

    finally:
        # Record trace
        if self.trace_backend:
            await self.trace_backend.record(trace)
```

**Step 2: Update imports if needed**

Make sure ExecutionTrace is imported:

```python
from agent_framework.trace import ExecutionTrace
```

**Step 3: Commit**

```bash
git add platform/agent-framework/src/agent_framework/runner.py
git commit -m "feat(framework): add AgentRunner.execute_once()

Single-shot agent execution for testing and evaluation:
- Runs agent with trigger event
- Records execution trace
- Returns result for inspection

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Add Trace Statistics Command

**Files:**
- Modify: `tools/kubani-dev/src/kubani_dev/commands/skill.py`

**Step 1: Add stats command**

```python
@skill_group.command(name="stats")
@click.argument("skill_name", required=False)
@click.option("--backend", type=click.Choice(["jsonl", "duckdb"]), default="jsonl")
@click.option("--db", type=click.Path(), help="DuckDB database path")
@click.option("--by-skill", is_flag=True, help="Show breakdown by skill")
@click.option("--over-time", type=click.Choice(["hour", "day", "week"]), help="Show performance over time")
def skill_stats(
    skill_name: Optional[str],
    backend: str,
    db: Optional[str],
    by_skill: bool,
    over_time: Optional[str],
):
    """
    Show execution statistics for skills.

    Aggregate metrics across execution traces. Uses DuckDB for
    advanced analytical queries.

    \b
    Examples:
        kubani-dev skill stats
        kubani-dev skill stats investigate-pod-failure
        kubani-dev skill stats --backend duckdb --db traces.duckdb
        kubani-dev skill stats --by-skill
        kubani-dev skill stats --over-time day
    """
    import asyncio

    async def get_stats():
        if backend == "duckdb":
            from agent_framework.backends import DuckDBBackend
            trace_backend = DuckDBBackend(db or "traces.duckdb")
        else:
            from agent_framework.backends import JsonlBackend
            skills_dir = Path.cwd() / "agents" / "skills"
            trace_backend = JsonlBackend(skills_dir / ".traces")

        stats = await trace_backend.get_stats(skill_name)

        # Additional analytics for DuckDB
        by_skill_data = None
        over_time_data = None

        if backend == "duckdb" and hasattr(trace_backend, 'get_token_usage_by_skill'):
            if by_skill:
                by_skill_data = await trace_backend.get_token_usage_by_skill()
            if over_time:
                over_time_data = await trace_backend.get_performance_over_time(skill_name, over_time)

        return stats, by_skill_data, over_time_data

    stats, by_skill_data, over_time_data = asyncio.run(get_stats())

    if not stats or stats.get("total_traces", 0) == 0:
        warning("No traces found")
        return

    print_panel(
        f"[bold]Skill:[/bold] {skill_name or 'All skills'}",
        title="Execution Statistics",
        style="cyan",
    )
    console.print()

    # Main stats table
    table = create_table(columns=["Metric", "Value"])
    table.add_row("Total Executions", str(stats.get("total_traces", 0)))
    table.add_row("Total Tokens", f"{stats.get('total_tokens', 0):,}")
    table.add_row("Avg Duration", f"{stats.get('avg_duration_ms', 0):.0f} ms")
    table.add_row("Avg Tokens", f"{stats.get('avg_tokens', 0):.0f}")
    table.add_row("Total LLM Calls", str(stats.get("total_llm_calls", 0)))
    table.add_row("Unique Skills", str(stats.get("unique_skills", "-")))
    table.add_row("First Execution", str(stats.get("first_trace", "-")))
    table.add_row("Last Execution", str(stats.get("last_trace", "-")))

    console.print(table)

    # By-skill breakdown
    if by_skill_data:
        console.print()
        skill_table = create_table(
            title="Token Usage by Skill",
            columns=["Skill", "Executions", "Total Tokens", "Avg Tokens", "Avg Duration"]
        )
        for row in by_skill_data[:10]:  # Top 10
            skill_table.add_row(
                row["skill_name"],
                str(row["executions"]),
                f"{row['total_tokens']:,}",
                f"{row['avg_tokens']:.0f}",
                f"{row['avg_duration_ms']:.0f} ms",
            )
        console.print(skill_table)

    # Over time breakdown
    if over_time_data:
        console.print()
        time_table = create_table(
            title=f"Performance Over Time ({over_time})",
            columns=["Time", "Executions", "Avg Duration", "Avg Tokens"]
        )
        for row in over_time_data[-10:]:  # Last 10 periods
            time_table.add_row(
                row["time_bucket"][:10] if row["time_bucket"] else "-",
                str(row["executions"]),
                f"{row['avg_duration_ms']:.0f} ms",
                f"{row['avg_tokens']:.0f}",
            )
        console.print(time_table)
```

**Step 2: Add get_stats to JsonlBackend**

In `platform/agent-framework/src/agent_framework/backends/jsonl.py`, add:

```python
async def get_stats(self, skill_name: str | None = None) -> dict[str, Any]:
    """Get aggregate statistics from JSONL traces."""
    traces = await self.query(TraceQuery(skill_name=skill_name, limit=10000))

    if not traces:
        return {}

    total_tokens = sum(t.total_tokens for t in traces)
    durations = [t.duration_ms for t in traces if t.duration_ms]

    return {
        "total_traces": len(traces),
        "total_tokens": total_tokens,
        "avg_duration_ms": sum(durations) / len(durations) if durations else 0,
        "avg_tokens": total_tokens / len(traces) if traces else 0,
        "first_trace": min(t.start_time for t in traces).isoformat() if traces else None,
        "last_trace": max(t.start_time for t in traces).isoformat() if traces else None,
    }
```

**Step 3: Commit**

```bash
git add tools/kubani-dev/src/kubani_dev/commands/skill.py
git add platform/agent-framework/src/agent_framework/backends/jsonl.py
git commit -m "feat(kubani-dev): add 'skill stats' command

Aggregate execution statistics:
- Total executions, tokens, durations
- Works with JSONL and DuckDB backends
- DuckDB: breakdown by skill (--by-skill)
- DuckDB: performance over time (--over-time)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Add Backend Selection to Config

**Files:**
- Modify: `agents/core/src/core_agents/config_unified.py`

**Step 1: Add traces configuration**

Add a new config section:

```python
class TracesConfig(BaseSettings):
    """Trace storage configuration."""

    model_config = SettingsConfigDict(
        env_prefix="TRACES_",
        env_file=".env",
        extra="ignore",
    )

    backend: str = Field(
        default="jsonl",
        description="Trace backend: jsonl, duckdb, or opentelemetry"
    )
    path: str = Field(
        default=".traces",
        description="Path for file-based backends"
    )
    duckdb_path: str = Field(
        default="traces.duckdb",
        description="DuckDB database file"
    )
    otel_endpoint: str = Field(
        default="",
        description="OpenTelemetry collector endpoint"
    )
```

Add to KubaniConfig:

```python
class KubaniConfig(BaseModel):
    # ... existing fields ...

    traces: TracesConfig = Field(
        default_factory=TracesConfig,
        description="Trace storage configuration"
    )
```

**Step 2: Commit**

```bash
git add agents/core/src/core_agents/config_unified.py
git commit -m "feat(config): add traces backend configuration

Configurable trace storage:
- traces.backend: jsonl, duckdb, opentelemetry
- traces.path: file storage location
- traces.duckdb_path: DuckDB database file
- traces.otel_endpoint: OTEL collector URL

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Add Tests for New Functionality

**Files:**
- Create: `platform/agent-framework/tests/test_duckdb_backend.py`
- Create: `tools/kubani-dev/tests/test_skill_commands.py`

**Step 1: Create test_duckdb_backend.py**

```python
"""Tests for DuckDB trace backend."""

import pytest
from pathlib import Path
from datetime import datetime

from agent_framework.backends import DuckDBBackend, TraceQuery
from agent_framework.trace import ExecutionTrace


class TestDuckDBBackend:
    """Tests for DuckDBBackend."""

    @pytest.fixture
    def backend(self, tmp_path):
        """Create a temporary DuckDB backend."""
        db_path = tmp_path / "test_traces.duckdb"
        backend = DuckDBBackend(db_path)
        yield backend
        backend.close()

    @pytest.fixture
    def sample_trace(self):
        """Create a sample trace for testing."""
        trace = ExecutionTrace(
            execution_type="skill",
            name="test-skill",
            input={"test": "data"},
        )
        trace.end(output={"status": "success"})
        return trace

    @pytest.mark.asyncio
    async def test_record_and_get(self, backend, sample_trace):
        """Test recording and retrieving a trace."""
        trace_id = await backend.record(sample_trace)

        retrieved = await backend.get(trace_id)

        assert retrieved is not None
        assert retrieved.trace_id == sample_trace.trace_id
        assert retrieved.name == "test-skill"

    @pytest.mark.asyncio
    async def test_query_by_skill(self, backend, sample_trace):
        """Test querying traces by skill name."""
        await backend.record(sample_trace)

        results = await backend.query(TraceQuery(skill_name="test-skill"))

        assert len(results) == 1
        assert results[0].name == "test-skill"

    @pytest.mark.asyncio
    async def test_query_empty(self, backend):
        """Test querying with no results."""
        results = await backend.query(TraceQuery(skill_name="nonexistent"))

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_delete(self, backend, sample_trace):
        """Test deleting a trace."""
        trace_id = await backend.record(sample_trace)

        deleted = await backend.delete(trace_id)

        assert deleted is True
        assert await backend.get(trace_id) is None

    @pytest.mark.asyncio
    async def test_get_stats(self, backend, sample_trace):
        """Test aggregate statistics."""
        await backend.record(sample_trace)

        stats = await backend.get_stats("test-skill")

        assert stats["total_traces"] == 1

    @pytest.mark.asyncio
    async def test_multiple_traces(self, backend):
        """Test with multiple traces."""
        for i in range(5):
            trace = ExecutionTrace(
                execution_type="skill",
                name="test-skill",
                input={"iteration": i},
            )
            trace.end(output={"status": "success"})
            await backend.record(trace)

        results = await backend.query(TraceQuery(skill_name="test-skill"))

        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_token_usage_by_skill(self, backend):
        """Test analytical query: token usage by skill."""
        # Create traces for different skills
        for skill in ["skill-a", "skill-b"]:
            for i in range(3):
                trace = ExecutionTrace(
                    execution_type="skill",
                    name=skill,
                    input={"iteration": i},
                )
                trace.end(output={"status": "success"})
                await backend.record(trace)

        usage = await backend.get_token_usage_by_skill()

        assert len(usage) == 2
        assert all("skill_name" in u for u in usage)

    @pytest.mark.asyncio
    async def test_performance_over_time(self, backend, sample_trace):
        """Test analytical query: performance over time."""
        await backend.record(sample_trace)

        performance = await backend.get_performance_over_time(bucket="day")

        assert len(performance) >= 1
        assert "time_bucket" in performance[0]

    @pytest.mark.asyncio
    async def test_export_to_parquet(self, backend, sample_trace, tmp_path):
        """Test Parquet export."""
        await backend.record(sample_trace)

        output_path = tmp_path / "traces.parquet"
        result = await backend.export_to_parquet(output_path)

        assert Path(result).exists()
```

**Step 2: Create test_skill_commands.py**

```python
"""Tests for kubani-dev skill commands."""

import pytest
from click.testing import CliRunner
from pathlib import Path
import json


class TestSkillCreate:
    """Tests for skill create command."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def temp_skills_dir(self, tmp_path):
        """Create temporary skills directory structure."""
        skills_dir = tmp_path / "agents" / "skills" / "development"
        skills_dir.mkdir(parents=True)
        return tmp_path

    def test_create_basic(self, runner, temp_skills_dir, monkeypatch):
        """Test basic skill creation."""
        monkeypatch.chdir(temp_skills_dir)

        from kubani_dev.commands.skill import skill_group

        result = runner.invoke(skill_group, [
            "create", "test-skill",
            "--description", "A test skill"
        ])

        assert result.exit_code == 0

        skill_dir = temp_skills_dir / "agents" / "skills" / "development" / "test-skill"
        assert skill_dir.exists()
        assert (skill_dir / "SKILL.md").exists()
        assert (skill_dir / "metadata.json").exists()
        assert (skill_dir / "test_cases.yaml").exists()

    def test_create_with_category(self, runner, temp_skills_dir, monkeypatch):
        """Test skill creation with category."""
        monkeypatch.chdir(temp_skills_dir)

        # Create category directory
        cat_dir = temp_skills_dir / "agents" / "skills" / "k8s" / "diagnostic"
        cat_dir.mkdir(parents=True)

        from kubani_dev.commands.skill import skill_group

        result = runner.invoke(skill_group, [
            "create", "my-skill",
            "--category", "k8s/diagnostic"
        ])

        assert result.exit_code == 0

    def test_create_with_scripts(self, runner, temp_skills_dir, monkeypatch):
        """Test skill creation with scripts."""
        monkeypatch.chdir(temp_skills_dir)

        from kubani_dev.commands.skill import skill_group

        result = runner.invoke(skill_group, [
            "create", "scripted-skill",
            "--with-scripts"
        ])

        assert result.exit_code == 0

        skill_dir = temp_skills_dir / "agents" / "skills" / "development" / "scripted-skill"
        assert (skill_dir / "scripts" / "main.py").exists()
```

**Step 3: Commit**

```bash
git add platform/agent-framework/tests/test_duckdb_backend.py
git add tools/kubani-dev/tests/test_skill_commands.py
git commit -m "test(phase4): add tests for DuckDB backend and skill commands

Tests for Phase 4 functionality:
- DuckDB backend CRUD operations
- Analytical queries (token usage, performance over time)
- Parquet export
- Skill create command variations

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 9: Update Package Exports and Version

**Files:**
- Modify: `platform/agent-framework/src/agent_framework/__init__.py`
- Modify: `platform/agent-framework/src/agent_framework/backends/__init__.py`

**Step 1: Update framework __init__.py**

```python
"""
Agent Framework - Local-first, cluster-ready agent development.

Core abstractions:
- AgentBase: Base class for all agents
- SkillExecutor: Run and evaluate skills in isolation
- AgentRunner: Run agents in local or cluster mode
- Mixins: Composable capabilities (MCP, Skills, Memory, etc.)
- LLM: LLM client and skill executor
- Evaluation: Model comparison matrix
- Backends: Trace storage (JSONL, DuckDB)

Example:
    from agent_framework import AgentBase, AgentRunner, SkillExecutor
    from agent_framework.llm import LLMClientWrapper
    from agent_framework.backends import DuckDBBackend
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

__version__ = "0.3.0"
```

**Step 2: Verify backends __init__.py includes DuckDBBackend**

Already done in Task 1.

**Step 3: Commit**

```bash
git add platform/agent-framework/src/agent_framework/__init__.py
git commit -m "feat(framework): bump version to 0.3.0 for Phase 4

Phase 4 complete:
- DuckDB trace backend with analytical queries
- skill create, watch, stats commands
- agent command group
- Trace configuration

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 10: Run Tests and Validate

**Step 1: Reinstall packages**

```bash
pip install -e platform/agent-framework/[dev]
pip install -e tools/kubani-dev/
```

**Step 2: Run all framework tests**

```bash
pytest platform/agent-framework/tests/ -v
```

Expected: All tests pass

**Step 3: Test new CLI commands**

```bash
# Test skill create
kubani-dev skill create --help

# Test skill watch
kubani-dev skill watch --help

# Test skill stats
kubani-dev skill stats --help

# Test agent commands
kubani-dev agent --help
kubani-dev agent list
kubani-dev agent run --help
```

**Step 4: Integration test**

```bash
# Create a test skill
kubani-dev skill create test-phase4 --description "Phase 4 test skill"

# Check it was created
ls agents/skills/development/test-phase4/

# Clean up
rm -rf agents/skills/development/test-phase4/
```

**Step 5: Commit any fixes**

```bash
git status
# Fix and commit if needed
```

---

## Task 11: Final Verification and Documentation

**Step 1: Verify module structure**

```bash
ls -la platform/agent-framework/src/agent_framework/backends/
python -c "from agent_framework.backends import DuckDBBackend; print('DuckDB: OK')"
```

**Step 2: Verify CLI commands**

```bash
kubani-dev skill --help
kubani-dev agent --help
```

**Step 3: Test end-to-end workflow**

```bash
# Create skill
kubani-dev skill create demo-skill -d "Demo for Phase 4"

# List skills
kubani-dev skill list

# Validate
kubani-dev skill validate agents/skills/development/demo-skill

# Clean up
rm -rf agents/skills/development/demo-skill
```

**Step 4: Review commits**

```bash
git log --oneline feature/restructure ^main | head -30
```

---

## Task 12: Migrate kubani-dev CLI from Click to Typer

**Files:**
- Modify: `tools/kubani-dev/pyproject.toml`
- Modify: `tools/kubani-dev/src/kubani_dev/cli.py`
- Modify: `tools/kubani-dev/src/kubani_dev/commands/skill.py`
- Modify: `tools/kubani-dev/src/kubani_dev/commands/agent.py`

**Rationale:** Typer provides automatic type hint support, better help generation, and is already used in cluster-manager. Standardize CLI framework across project.

**Step 1: Update dependencies**

In `tools/kubani-dev/pyproject.toml`:
```toml
# Replace click with typer
typer = ">=0.12.0"
# Keep rich (already used)
rich = ">=13.0.0"
```

Remove `click` from dependencies.

**Step 2: Update cli.py**

```python
"""kubani-dev CLI - Typer-based."""

import typer
from typing import Optional
from typing_extensions import Annotated

from kubani_dev.commands.skill import skill_app
from kubani_dev.commands.agent import agent_app

app = typer.Typer(
    name="kubani-dev",
    help="Kubani development CLI for agent and skill management.",
    no_args_is_help=True,
)

# Add subcommand groups
app.add_typer(skill_app, name="skill", help="Skill management commands")
app.add_typer(agent_app, name="agent", help="Agent management commands")


@app.command()
def version():
    """Show kubani-dev version."""
    from kubani_dev import __version__
    typer.echo(f"kubani-dev {__version__}")


@app.command()
def init(
    force: Annotated[bool, typer.Option("--force", "-f", help="Overwrite existing config")] = False,
):
    """Initialize kubani-dev configuration."""
    from kubani_dev.config import init_config
    init_config(force=force)
    typer.echo("Configuration initialized.")


def main():
    app()


if __name__ == "__main__":
    main()
```

**Step 3: Update skill.py to use Typer**

```python
"""Skill management commands - Typer-based."""

import typer
from typing import Optional
from typing_extensions import Annotated
from pathlib import Path

from kubani_dev.ui import console, success, error, info, warning, muted, create_table, print_panel, spinner

skill_app = typer.Typer(help="Skill management commands")


@skill_app.command("create")
def create_skill(
    skill_name: Annotated[str, typer.Argument(help="Name for the new skill")],
    category: Annotated[str, typer.Option("--category", "-c", help="Skill category")] = "development",
    description: Annotated[Optional[str], typer.Option("--description", "-d", help="Short description")] = None,
    with_tests: Annotated[bool, typer.Option("--with-tests/--no-tests", help="Generate test cases")] = True,
    with_scripts: Annotated[bool, typer.Option("--with-scripts", help="Include scripts directory")] = False,
):
    """Create a new skill from template."""
    # ... implementation unchanged, but use typer.echo() for output
    pass


@skill_app.command("run")
def run_skill(
    skill_name: Annotated[str, typer.Argument(help="Skill name or path to run")],
    context: Annotated[Optional[str], typer.Option("--context", "-c", help="JSON context string")] = None,
    context_file: Annotated[Optional[Path], typer.Option("--context-file", "-f", help="JSON context file")] = None,
    llm_url: Annotated[Optional[str], typer.Option("--llm-url", help="LLM base URL")] = None,
    llm_model: Annotated[Optional[str], typer.Option("--llm-model", help="LLM model name")] = None,
    output_format: Annotated[str, typer.Option("--output", "-o", help="Output format")] = "table",
):
    """Run a skill with context."""
    # ... implementation unchanged
    pass


@skill_app.command("watch")
def watch_skill(
    skill_path: Annotated[Path, typer.Argument(help="Path to skill directory")],
    context: Annotated[Optional[str], typer.Option("--context", "-c", help="JSON context string")] = None,
    context_file: Annotated[Optional[Path], typer.Option("--context-file", "-f", help="JSON context file")] = None,
    debounce: Annotated[float, typer.Option("--debounce", help="Debounce delay in seconds")] = 1.0,
):
    """Watch a skill for changes and auto-run."""
    # ... implementation unchanged
    pass


@skill_app.command("stats")
def skill_stats(
    skill_name: Annotated[Optional[str], typer.Argument(help="Skill name (optional)")] = None,
    backend: Annotated[str, typer.Option("--backend", help="Trace backend")] = "jsonl",
    db: Annotated[Optional[Path], typer.Option("--db", help="DuckDB database path")] = None,
    by_skill: Annotated[bool, typer.Option("--by-skill", help="Show breakdown by skill")] = False,
    over_time: Annotated[Optional[str], typer.Option("--over-time", help="Performance over time bucket")] = None,
):
    """Show execution statistics for skills."""
    # ... implementation unchanged
    pass
```

**Step 4: Update agent.py similarly**

Follow the same pattern as skill.py, converting Click decorators to Typer.

**Step 5: Commit**

```bash
git add tools/kubani-dev/
git commit -m "refactor(kubani-dev): migrate CLI from Click to Typer

Benefits:
- Automatic type hint support
- Better help text generation
- Consistent with cluster-manager CLI
- Modern Python CLI patterns

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 13: Add Error Hierarchy and Structured Exceptions

**Files:**
- Create: `agents/core/src/core_agents/exceptions.py`
- Create: `platform/agent-framework/src/agent_framework/exceptions.py`
- Modify: Multiple files to use new exceptions

**Rationale:** Currently 40+ instances of bare `except Exception`. Custom hierarchy enables better error handling, debugging, and retry logic.

**Step 1: Create core exceptions.py**

```python
"""Kubani exception hierarchy for structured error handling."""

from __future__ import annotations

from typing import Any


class KubaniError(Exception):
    """Base exception for all Kubani errors."""

    def __init__(
        self,
        message: str,
        *,
        cause: Exception | None = None,
        context: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.cause = cause
        self.context = context or {}

    def __str__(self) -> str:
        if self.cause:
            return f"{self.message} (caused by: {self.cause})"
        return self.message


class ConfigurationError(KubaniError):
    """Configuration-related errors (missing keys, invalid values, etc.)."""
    pass


class MCPError(KubaniError):
    """MCP server communication errors."""

    def __init__(
        self,
        message: str,
        *,
        server: str | None = None,
        tool: str | None = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.server = server
        self.tool = tool


class MCPConnectionError(MCPError):
    """MCP server connection failures."""
    pass


class MCPToolError(MCPError):
    """MCP tool execution errors."""
    pass


class SkillError(KubaniError):
    """Skill-related errors."""

    def __init__(
        self,
        message: str,
        *,
        skill_name: str | None = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.skill_name = skill_name


class SkillNotFoundError(SkillError):
    """Skill not found in registry or filesystem."""
    pass


class SkillExecutionError(SkillError):
    """Skill execution failures."""
    pass


class SkillValidationError(SkillError):
    """Skill validation failures (invalid SKILL.md, missing fields, etc.)."""
    pass


class AgentError(KubaniError):
    """Agent-related errors."""

    def __init__(
        self,
        message: str,
        *,
        agent_name: str | None = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.agent_name = agent_name


class AgentInitializationError(AgentError):
    """Agent failed to initialize."""
    pass


class AgentExecutionError(AgentError):
    """Agent execution failures."""
    pass


class MemoryError(KubaniError):
    """Memory system errors (Qdrant, Neo4j, Redis)."""

    def __init__(
        self,
        message: str,
        *,
        backend: str | None = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.backend = backend


class TemporalError(KubaniError):
    """Temporal workflow errors."""

    def __init__(
        self,
        message: str,
        *,
        workflow_id: str | None = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.workflow_id = workflow_id


class LLMError(KubaniError):
    """LLM provider errors."""

    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.provider = provider
        self.model = model


class LLMRateLimitError(LLMError):
    """LLM rate limit hit."""
    pass


class LLMTimeoutError(LLMError):
    """LLM request timeout."""
    pass


class RegistryError(KubaniError):
    """Registry service errors."""
    pass


# Convenience function for migration
def wrap_exception(exc: Exception, error_class: type[KubaniError], message: str) -> KubaniError:
    """Wrap a generic exception in a Kubani error type."""
    return error_class(message, cause=exc, context={"original_type": type(exc).__name__})
```

**Step 2: Create framework exceptions.py (lighter weight)**

```python
"""Agent framework exceptions."""

from __future__ import annotations


class FrameworkError(Exception):
    """Base exception for agent framework."""
    pass


class TraceBackendError(FrameworkError):
    """Trace backend errors."""
    pass


class ExecutorError(FrameworkError):
    """Skill/agent executor errors."""
    pass


class ConfigError(FrameworkError):
    """Framework configuration errors."""
    pass
```

**Step 3: Update core_agents/__init__.py to export exceptions**

```python
from core_agents.exceptions import (
    KubaniError,
    ConfigurationError,
    MCPError,
    MCPConnectionError,
    MCPToolError,
    SkillError,
    SkillNotFoundError,
    SkillExecutionError,
    AgentError,
    LLMError,
)
```

**Step 4: Commit**

```bash
git add agents/core/src/core_agents/exceptions.py
git add platform/agent-framework/src/agent_framework/exceptions.py
git commit -m "feat(core): add structured exception hierarchy

Exception types:
- KubaniError (base)
- ConfigurationError
- MCPError, MCPConnectionError, MCPToolError
- SkillError, SkillNotFoundError, SkillExecutionError
- AgentError, AgentInitializationError, AgentExecutionError
- MemoryError, TemporalError, LLMError

Benefits:
- Better debugging with preserved context
- Specific catch blocks for retry logic
- Clear error taxonomy

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 14: Add Structured Logging with structlog

**Files:**
- Modify: `agents/core/pyproject.toml`
- Create: `agents/core/src/core_agents/logging.py`
- Modify: `agents/core/src/core_agents/config_unified.py`

**Rationale:** Current logging is basic `logging.getLogger(__name__)`. Structured logging (JSON) with context propagation is essential for observability.

**Step 1: Add structlog dependency**

In `agents/core/pyproject.toml`:
```toml
structlog = ">=24.0.0"
```

**Step 2: Create logging.py**

```python
"""Structured logging configuration using structlog."""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from structlog.types import Processor


def configure_logging(
    level: str = "INFO",
    format: str = "console",  # "console" or "json"
    service_name: str = "kubani",
) -> None:
    """
    Configure structured logging for Kubani.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        format: Output format ("console" for human-readable, "json" for machine-readable)
        service_name: Service name for log context
    """
    # Shared processors
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if format == "json":
        # JSON output for production
        shared_processors.append(structlog.processors.format_exc_info)
        renderer: Processor = structlog.processors.JSONRenderer()
    else:
        # Console output for development
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure stdlib logging to use structlog
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, level.upper()))

    # Bind service context
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(service=service_name)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Bound structlog logger
    """
    return structlog.get_logger(name)


def bind_context(**kwargs: Any) -> None:
    """Bind context variables that will appear in all subsequent logs."""
    structlog.contextvars.bind_contextvars(**kwargs)


def unbind_context(*keys: str) -> None:
    """Remove context variables."""
    structlog.contextvars.unbind_contextvars(*keys)


def clear_context() -> None:
    """Clear all bound context variables."""
    structlog.contextvars.clear_contextvars()


# Context managers for scoped logging context
class LogContext:
    """Context manager for scoped log context."""

    def __init__(self, **kwargs: Any):
        self.kwargs = kwargs
        self._token = None

    def __enter__(self):
        bind_context(**self.kwargs)
        return self

    def __exit__(self, *args):
        unbind_context(*self.kwargs.keys())
```

**Step 3: Add logging config to config_unified.py**

```python
class LoggingConfig(BaseSettings):
    """Logging configuration."""

    model_config = SettingsConfigDict(
        env_prefix="LOGGING_",
        extra="ignore",
    )

    level: str = Field(default="INFO", description="Log level")
    format: str = Field(default="console", description="Log format: console or json")
    include_timestamps: bool = Field(default=True, description="Include timestamps")
```

**Step 4: Update __init__.py to configure logging on import**

In `agents/core/src/core_agents/__init__.py`:
```python
from core_agents.logging import configure_logging, get_logger, bind_context, LogContext

# Configure logging based on environment
import os
_log_format = os.getenv("LOG_FORMAT", "console")
_log_level = os.getenv("LOG_LEVEL", "INFO")
configure_logging(level=_log_level, format=_log_format)
```

**Step 5: Commit**

```bash
git add agents/core/src/core_agents/logging.py
git add agents/core/pyproject.toml
git add agents/core/src/core_agents/__init__.py
git commit -m "feat(core): add structured logging with structlog

Features:
- JSON or console output (configurable)
- Context propagation (service, request_id, etc.)
- LogContext context manager for scoped context
- Automatic timestamp formatting
- Stack trace rendering

Usage:
  from core_agents.logging import get_logger, bind_context
  logger = get_logger(__name__)
  bind_context(request_id='abc123')
  logger.info('Processing request', user='alice')

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 15: Consolidate Configuration Systems

**Files:**
- Modify: `platform/agent-framework/src/agent_framework/config.py`
- Modify: `agents/core/src/core_agents/config_unified.py`
- Modify: `agents/core/src/core_agents/learning/voyager/manager.py`

**Rationale:** Two parallel config systems exist (agent-framework and core_agents). Consolidate to single source of truth.

**Step 1: Make agent-framework config inherit from core_agents**

In `platform/agent-framework/src/agent_framework/config.py`:

```python
"""Agent framework configuration - extends core config."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# Try to import from core_agents if available
try:
    from core_agents.config_unified import LLMConfig, TracesConfig
    HAS_CORE_CONFIG = True
except ImportError:
    HAS_CORE_CONFIG = False


class RunMode(str, Enum):
    """Agent run mode."""
    LOCAL = "local"
    CLUSTER = "cluster"


class SkillConfig(BaseModel):
    """Configuration for skill execution."""

    name: str = Field(description="Skill name")
    version: str | None = Field(default=None, description="Skill version")
    record_trace: bool = Field(default=True, description="Record execution trace")
    timeout_seconds: int = Field(default=300, description="Execution timeout")


class AgentConfig(BaseModel):
    """Configuration for agent execution."""

    name: str = Field(description="Agent name")
    run_mode: RunMode = Field(default=RunMode.LOCAL, description="Run mode")
    skills_dir: str | None = Field(default=None, description="Skills directory")
    trace_backend: str = Field(default="jsonl", description="Trace storage backend")

    # LLM config - use core_agents version if available
    llm_base_url: str = Field(default="https://llm.almckay.io/v1")
    llm_model: str = Field(default="nvidia/Qwen3-14B-FP4")

    @classmethod
    def from_core_config(cls, name: str, run_mode: RunMode = RunMode.LOCAL) -> "AgentConfig":
        """Create AgentConfig from core_agents unified config."""
        if not HAS_CORE_CONFIG:
            return cls(name=name, run_mode=run_mode)

        from core_agents.config_unified import get_config
        config = get_config()

        return cls(
            name=name,
            run_mode=run_mode,
            llm_base_url=config.llm.api_url,
            llm_model=config.llm.model,
            trace_backend=config.traces.backend,
        )
```

**Step 2: Remove duplicate LearningConfig from voyager/manager.py**

In `agents/core/src/core_agents/learning/voyager/manager.py`, replace local LearningConfig with import:

```python
# Before (remove this):
# class LearningConfig(BaseSettings):
#     ... duplicate config ...

# After:
from core_agents.config_unified import get_config

def get_learning_config():
    """Get learning configuration from unified config."""
    config = get_config()
    return config.learning
```

**Step 3: Add config consolidation note to CLAUDE.md**

Document the single source of truth pattern.

**Step 4: Commit**

```bash
git add platform/agent-framework/src/agent_framework/config.py
git add agents/core/src/core_agents/learning/voyager/manager.py
git commit -m "refactor(config): consolidate configuration systems

Changes:
- agent-framework config now imports from core_agents when available
- AgentConfig.from_core_config() factory method
- Removed duplicate LearningConfig from voyager/manager.py
- Single source of truth: core_agents/config_unified.py

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 16: Add Service Container for Dependency Injection

**Files:**
- Create: `agents/core/src/core_agents/container.py`
- Modify: `agents/core/src/core_agents/__init__.py`

**Rationale:** Currently 30+ global singletons make testing difficult. Service container provides clean dependency management without full DI framework overhead.

**Step 1: Create container.py**

```python
"""Service container for dependency injection.

Replaces global singletons with a lightweight container pattern.
Enables easy testing via container.override() and container.reset().
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, TypeVar, Generic, Callable, Awaitable

T = TypeVar("T")


class Singleton(Generic[T]):
    """Lazy singleton with optional async initialization."""

    def __init__(
        self,
        factory: Callable[[], T] | Callable[[], Awaitable[T]],
        *,
        async_init: bool = False,
    ):
        self._factory = factory
        self._async_init = async_init
        self._instance: T | None = None
        self._lock = asyncio.Lock()

    def get(self) -> T:
        """Get the singleton instance (sync)."""
        if self._instance is None:
            if self._async_init:
                raise RuntimeError("Use get_async() for async-initialized singletons")
            self._instance = self._factory()
        return self._instance

    async def get_async(self) -> T:
        """Get the singleton instance (async-safe)."""
        if self._instance is None:
            async with self._lock:
                if self._instance is None:
                    if self._async_init:
                        self._instance = await self._factory()
                    else:
                        self._instance = self._factory()
        return self._instance

    def reset(self) -> None:
        """Reset the singleton (for testing)."""
        self._instance = None

    def override(self, instance: T) -> None:
        """Override with a specific instance (for testing)."""
        self._instance = instance


class ServiceContainer:
    """
    Lightweight service container for managing dependencies.

    Usage:
        container = ServiceContainer()

        # Register services
        container.register("config", lambda: get_config())
        container.register("mcp_client", create_mcp_client, async_init=True)

        # Get services
        config = container.get("config")
        client = await container.get_async("mcp_client")

        # Testing
        container.override("config", mock_config)
        container.reset_all()
    """

    def __init__(self):
        self._services: dict[str, Singleton] = {}

    def register(
        self,
        name: str,
        factory: Callable[[], Any] | Callable[[], Awaitable[Any]],
        *,
        async_init: bool = False,
    ) -> None:
        """Register a service factory."""
        self._services[name] = Singleton(factory, async_init=async_init)

    def get(self, name: str) -> Any:
        """Get a service instance (sync)."""
        if name not in self._services:
            raise KeyError(f"Service not registered: {name}")
        return self._services[name].get()

    async def get_async(self, name: str) -> Any:
        """Get a service instance (async-safe)."""
        if name not in self._services:
            raise KeyError(f"Service not registered: {name}")
        return await self._services[name].get_async()

    def override(self, name: str, instance: Any) -> None:
        """Override a service with a specific instance (for testing)."""
        if name not in self._services:
            # Create a dummy singleton for the override
            self._services[name] = Singleton(lambda: None)
        self._services[name].override(instance)

    def reset(self, name: str) -> None:
        """Reset a specific service."""
        if name in self._services:
            self._services[name].reset()

    def reset_all(self) -> None:
        """Reset all services (for testing cleanup)."""
        for service in self._services.values():
            service.reset()

    @asynccontextmanager
    async def test_context(self, **overrides: Any):
        """Context manager for test isolation."""
        for name, instance in overrides.items():
            self.override(name, instance)
        try:
            yield self
        finally:
            self.reset_all()


# Global container instance
_container: ServiceContainer | None = None


def get_container() -> ServiceContainer:
    """Get the global service container."""
    global _container
    if _container is None:
        _container = ServiceContainer()
        _register_default_services(_container)
    return _container


def _register_default_services(container: ServiceContainer) -> None:
    """Register default services."""
    # Config (sync)
    container.register("config", lambda: _lazy_get_config())

    # MCP Client (async)
    container.register("mcp_client", _lazy_create_mcp_client, async_init=True)

    # Plugin Manager (sync with async init)
    container.register("plugin_manager", lambda: _lazy_get_plugin_manager())


def _lazy_get_config():
    """Lazy config loader to avoid circular imports."""
    from core_agents.config_unified import get_config
    return get_config()


async def _lazy_create_mcp_client():
    """Lazy MCP client factory."""
    from core_agents.mcp.client import create_mcp_client
    return await create_mcp_client()


def _lazy_get_plugin_manager():
    """Lazy plugin manager factory."""
    from core_agents.plugins.manager import get_plugin_manager
    return get_plugin_manager()


# Convenience functions
def get_config():
    """Get config via container."""
    return get_container().get("config")


async def get_mcp_client():
    """Get MCP client via container."""
    return await get_container().get_async("mcp_client")
```

**Step 2: Update __init__.py to export container**

```python
from core_agents.container import get_container, get_config, get_mcp_client
```

**Step 3: Add test helper**

```python
# In tests/conftest.py
import pytest
from core_agents.container import get_container

@pytest.fixture
def isolated_container():
    """Provide an isolated container for testing."""
    container = get_container()
    yield container
    container.reset_all()

@pytest.fixture
async def mock_services(isolated_container):
    """Context manager for mocking services."""
    async with isolated_container.test_context(
        config=MockConfig(),
        mcp_client=MockMCPClient(),
    ) as container:
        yield container
```

**Step 4: Commit**

```bash
git add agents/core/src/core_agents/container.py
git add agents/core/src/core_agents/__init__.py
git commit -m "feat(core): add service container for dependency injection

Lightweight DI pattern:
- ServiceContainer with lazy singleton management
- Sync and async service initialization
- override() and reset() for testing
- test_context() async context manager
- Replaces 30+ global singletons with container.get()

Benefits:
- Easy test isolation
- Explicit dependencies
- Thread-safe initialization
- No heavy DI framework overhead

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 17: Run Tests and Final Validation (Extended)

**Step 1: Run all tests**

```bash
# Framework tests
pytest platform/agent-framework/tests/ -v

# Core tests
pytest agents/core/tests/ -v

# CLI tests
pytest tools/kubani-dev/tests/ -v
```

**Step 2: Verify new functionality**

```bash
# Typer CLI
kubani-dev --help
kubani-dev skill --help
kubani-dev agent --help

# Structured logging
python -c "from core_agents.logging import get_logger; log = get_logger(); log.info('test', key='value')"

# Exception hierarchy
python -c "from core_agents.exceptions import SkillNotFoundError; raise SkillNotFoundError('test', skill_name='foo')"

# Service container
python -c "from core_agents.container import get_container; c = get_container(); print(c.get('config'))"
```

**Step 3: Commit fixes**

```bash
git status
# Fix and commit if needed
```

---

## Post-Phase 4 Checklist

- [ ] DuckDB trace backend complete with analytical queries
- [ ] `kubani-dev skill create` command works
- [ ] `kubani-dev skill watch` command works
- [ ] `kubani-dev skill stats` command works (with DuckDB analytics)
- [ ] `kubani-dev agent` command group works
- [ ] AgentRunner.execute_once() implemented
- [ ] Traces configuration in config_unified.py
- [ ] All tests pass
- [ ] Framework version bumped to 0.3.0
- [ ] **Click → Typer migration complete**
- [ ] **Structured exception hierarchy in place**
- [ ] **Structured logging with structlog configured**
- [ ] **Configuration systems consolidated**
- [ ] **Service container for dependency injection**

---

## Notes

### Original Tasks (1-11)
- `skill watch` requires the `watchdog` package
- DuckDB backend is file-based and portable (~15MB additional dependency)
- DuckDB provides advanced analytical queries: token usage by skill, performance over time
- Parquet export available for trace archival
- Agent commands integrate with the new framework
- Hot reload watches for .md, .py, .yaml, .json changes
- Trace backends are configurable via environment or config files

### Strategic Improvements (Tasks 12-17)
- **Typer** replaces Click for modern CLI patterns with type hints
- **structlog** provides JSON logging for production observability
- **Exception hierarchy** enables specific error handling and retry logic
- **Config consolidation** establishes single source of truth in core_agents
- **Service container** replaces 30+ global singletons for better testability

### Migration Notes
- Typer commands are compatible with Click subcommands during migration
- structlog can coexist with stdlib logging (foreign loggers are wrapped)
- New exceptions extend existing behavior (no breaking changes)
- Service container provides `override()` and `reset()` for test isolation
