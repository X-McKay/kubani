# Phase 3: Unified Skills System - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Connect the Agent Framework's SkillExecutor to real LLM execution, add `kubani-dev skill run` command, and enable model comparison matrix for evaluations.

**Architecture:** Integrate the new `agent_framework.SkillExecutor` with the existing `kubani_dev.LLMClient` and evaluation infrastructure. Skills remain in `agents/skills/` as the single source of truth.

**Tech Stack:** Python 3.11+, Click CLI, existing LLMClient, agent-framework SkillExecutor

---

## Pre-Flight Checklist

Before starting, verify:
```bash
# On feature/restructure branch
git branch --show-current

# Phase 2 framework installed
python -c "from agent_framework import SkillExecutor; print('OK')"

# kubani-dev installed
kubani-dev --version

# Skills directory exists
ls agents/skills/
```

---

## Task 1: Create LLM Integration for SkillExecutor

**Files:**
- Create: `platform/agent-framework/src/agent_framework/llm/__init__.py`
- Create: `platform/agent-framework/src/agent_framework/llm/client.py`
- Create: `platform/agent-framework/src/agent_framework/llm/executor.py`

**Step 1: Create llm directory**

```bash
mkdir -p platform/agent-framework/src/agent_framework/llm
```

**Step 2: Create llm/__init__.py**

```python
"""LLM integration for skill execution."""

from agent_framework.llm.client import LLMClientWrapper
from agent_framework.llm.executor import LLMSkillExecutor

__all__ = ["LLMClientWrapper", "LLMSkillExecutor"]
```

**Step 3: Create llm/client.py**

```python
"""LLM client wrapper for skill execution."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Response from LLM call."""

    content: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    model: str
    raw_response: dict[str, Any] | None = None


class LLMClientWrapper:
    """
    Wrapper for LLM API calls with tracing support.

    Supports OpenAI-compatible endpoints (vLLM, Ollama, etc.)
    """

    def __init__(
        self,
        base_url: str = "https://llm.almckay.io/v1",
        model: str = "nvidia/Qwen3-14B-FP4",
        api_key: str = "not-needed",
        timeout: float = 120.0,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        enable_thinking: bool = True,
    ):
        """
        Initialize LLM client.

        Args:
            base_url: OpenAI-compatible API base URL
            model: Model name/ID
            api_key: API key (often not needed for local deployments)
            timeout: Request timeout in seconds
            temperature: Sampling temperature
            max_tokens: Max tokens to generate
            enable_thinking: Enable thinking mode for reasoning models
        """
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.enable_thinking = enable_thinking

        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """
        Send chat completion request.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Override temperature
            max_tokens: Override max tokens

        Returns:
            LLMResponse with content and metrics
        """
        client = await self._get_client()

        # Build request
        request_body = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "stream": False,
        }

        if max_tokens or self.max_tokens:
            request_body["max_tokens"] = max_tokens or self.max_tokens

        # Add thinking control for Qwen models
        if not self.enable_thinking and "qwen" in self.model.lower():
            # Add instruction to skip thinking
            if messages and messages[-1]["role"] == "user":
                messages[-1]["content"] += "\n\nRespond directly without <think> tags."

        start_time = time.time()

        try:
            response = await client.post("/chat/completions", json=request_body)
            response.raise_for_status()
            data = response.json()

            latency_ms = (time.time() - start_time) * 1000

            # Extract response
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})

            return LLMResponse(
                content=content,
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                latency_ms=latency_ms,
                model=self.model,
                raw_response=data,
            )

        except httpx.HTTPStatusError as e:
            logger.error(f"LLM request failed: {e}")
            raise
        except Exception as e:
            logger.error(f"LLM request error: {e}")
            raise

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
```

**Step 4: Create llm/executor.py**

```python
"""LLM-powered skill executor."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from agent_framework.llm.client import LLMClientWrapper, LLMResponse
from agent_framework.trace import ExecutionTrace, SpanKind, TraceSpan

logger = logging.getLogger(__name__)


class LLMSkillExecutor:
    """
    Execute skills using LLM.

    Takes a skill definition (markdown) and context, executes via LLM,
    and returns structured output with full trace.
    """

    SYSTEM_PROMPT = """You are an AI agent executing a skill. Follow the skill instructions precisely.

Given:
1. A skill definition (SKILL.md) with steps and expected behavior
2. Input context with relevant data

Your task:
1. Follow the skill steps exactly
2. Use the provided context
3. Return a JSON response with your findings/actions

IMPORTANT: Your response MUST be valid JSON. Use this format:
{
    "status": "success" | "failure" | "needs_approval",
    "summary": "Brief summary of what was done",
    "findings": ["Finding 1", "Finding 2"],
    "actions_taken": ["Action 1", "Action 2"],
    "recommendations": ["Recommendation 1"],
    "confidence": 0.0-1.0,
    "details": { ... any additional structured data ... }
}
"""

    def __init__(self, llm_client: LLMClientWrapper):
        """
        Initialize executor.

        Args:
            llm_client: LLM client for making calls
        """
        self.llm = llm_client

    async def execute(
        self,
        skill_content: str,
        skill_name: str,
        context: dict[str, Any],
        trace: ExecutionTrace,
    ) -> dict[str, Any]:
        """
        Execute a skill with LLM.

        Args:
            skill_content: Full skill markdown content
            skill_name: Name of the skill
            context: Input context for the skill
            trace: Execution trace to record to

        Returns:
            Structured output from skill execution
        """
        # Build the prompt
        user_message = self._build_prompt(skill_content, context)

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        # Create LLM call span
        llm_span = TraceSpan(
            name=f"llm.execute_skill.{skill_name}",
            kind=SpanKind.LLM_CALL,
            attributes={
                "llm.model": self.llm.model,
                "llm.temperature": self.llm.temperature,
                "skill.name": skill_name,
            },
        )
        trace.add_span(llm_span)

        try:
            # Make LLM call
            response = await self.llm.chat(messages)

            # Update span with token counts
            llm_span.input_tokens = response.input_tokens
            llm_span.output_tokens = response.output_tokens
            llm_span.attributes["llm.latency_ms"] = response.latency_ms

            # Parse response
            output = self._parse_response(response.content)

            llm_span.end()

            return output

        except Exception as e:
            llm_span.end(status="error", error=str(e))
            raise

    def _build_prompt(
        self,
        skill_content: str,
        context: dict[str, Any],
    ) -> str:
        """Build the user prompt for skill execution."""
        context_str = json.dumps(context, indent=2, default=str)

        return f"""# Skill Definition

{skill_content}

---

# Input Context

```json
{context_str}
```

---

Execute this skill with the given context. Return your response as JSON."""

    def _parse_response(self, content: str) -> dict[str, Any]:
        """Parse LLM response to extract JSON output."""
        # Try to find JSON in the response
        # First, try direct JSON parse
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try to extract JSON from markdown code block
        json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find JSON object in the text
        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        # Fallback: return raw content
        logger.warning("Could not parse JSON from LLM response, returning raw")
        return {
            "status": "unknown",
            "summary": "Could not parse structured response",
            "raw_response": content,
        }
```

**Step 5: Commit**

```bash
git add platform/agent-framework/src/agent_framework/llm/
git commit -m "feat(framework): add LLM integration for skill execution

LLM client wrapper and executor:
- LLMClientWrapper with async HTTP, token tracking
- LLMSkillExecutor for running skills via LLM
- Full trace recording with spans

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Update SkillExecutor to Use LLM

**Files:**
- Modify: `platform/agent-framework/src/agent_framework/skill_executor.py`

**Step 1: Update skill_executor.py to integrate LLM execution**

Add LLM execution to the `_execute_skill_logic` method:

```python
async def _execute_skill_logic(
    self,
    skill: dict[str, Any],
    context: dict[str, Any],
    trace: ExecutionTrace,
) -> dict[str, Any]:
    """
    Execute the actual skill logic via LLM.
    """
    # Check if we have an LLM client
    if self.llm_client is None:
        # Try to create default client
        try:
            from agent_framework.llm import LLMClientWrapper
            self.llm_client = LLMClientWrapper()
        except Exception as e:
            logger.warning(f"No LLM client available: {e}")
            return {
                "status": "skipped",
                "reason": "No LLM client configured",
                "skill": skill["name"],
            }

    # Create LLM executor
    from agent_framework.llm import LLMSkillExecutor
    executor = LLMSkillExecutor(self.llm_client)

    # Execute skill
    return await executor.execute(
        skill_content=skill["content"],
        skill_name=skill["name"],
        context=context,
        trace=trace,
    )
```

Also update the constructor to accept LLMClientWrapper:

```python
def __init__(
    self,
    skills_dir: str | Path,
    trace_backend: TraceBackend | None = None,
    llm_client: Any = None,  # LLMClientWrapper or compatible
    mcp_client: Any = None,
):
```

**Step 2: Commit**

```bash
git add platform/agent-framework/src/agent_framework/skill_executor.py
git commit -m "feat(framework): integrate LLM execution in SkillExecutor

SkillExecutor now executes skills via LLM:
- Uses LLMSkillExecutor for actual execution
- Falls back gracefully if no LLM client
- Full trace recording with LLM spans

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Add `kubani-dev skill run` Command

**Files:**
- Modify: `tools/kubani-dev/src/kubani_dev/commands/skill.py`

**Step 1: Add the `run` command to skill.py**

Add after the existing commands:

```python
@skill_group.command(name="run")
@click.argument("skill_name")
@click.option("--context", "-c", help="JSON context string")
@click.option("--context-file", "-f", type=click.Path(exists=True), help="JSON context file")
@click.option("--llm-url", help="LLM base URL")
@click.option("--llm-model", help="LLM model name")
@click.option("--trace", is_flag=True, help="Show full execution trace")
@click.option("--no-record", is_flag=True, help="Don't record trace to backend")
@click.option("--output", "-o", type=click.Choice(["json", "summary"]), default="summary")
def run_skill(
    skill_name: str,
    context: Optional[str],
    context_file: Optional[str],
    llm_url: Optional[str],
    llm_model: Optional[str],
    trace: bool,
    no_record: bool,
    output: str,
):
    """
    Execute a skill with given context.

    \b
    Examples:
        kubani-dev skill run k8s/diagnostic/investigate-pod-failure \\
            --context '{"pod": "nginx-abc", "namespace": "default"}'

        kubani-dev skill run investigate-pod-failure -f context.json --trace
    """
    import asyncio
    import json as json_module
    from pathlib import Path

    # Parse context
    ctx = {}
    if context_file:
        with open(context_file) as f:
            ctx = json_module.load(f)
    elif context:
        try:
            ctx = json_module.loads(context)
        except json_module.JSONDecodeError as e:
            error(f"Invalid JSON context: {e}")
            sys.exit(1)

    # Get skills directory
    skills_dir = Path.cwd() / "agents" / "skills"
    if not skills_dir.exists():
        # Try relative to script
        skills_dir = Path(__file__).parents[4] / "agents" / "skills"

    if not skills_dir.exists():
        error(f"Skills directory not found: {skills_dir}")
        sys.exit(1)

    async def execute():
        from agent_framework.skill_executor import SkillExecutor
        from agent_framework.llm import LLMClientWrapper
        from agent_framework.config import SkillConfig

        # Create LLM client
        llm = LLMClientWrapper(
            base_url=llm_url or os.getenv("LLM_BASE_URL", "https://llm.almckay.io/v1"),
            model=llm_model or os.getenv("LLM_MODEL", "nvidia/Qwen3-14B-FP4"),
        )

        # Create executor
        executor = SkillExecutor(
            skills_dir=skills_dir,
            llm_client=llm,
        )

        # Execute skill
        config = SkillConfig(
            name=skill_name,
            record_trace=not no_record,
        )

        info(f"Executing skill: [bold]{skill_name}[/bold]")
        if ctx:
            muted(f"Context: {json_module.dumps(ctx, indent=2)[:200]}...")

        with spinner("Running skill..."):
            result = await executor.execute(skill_name, context=ctx, config=config)

        await llm.close()
        return result

    # Run async execution
    result = asyncio.run(execute())

    # Output results
    if output == "json" or trace:
        console.print_json(result.model_dump_json(indent=2))
    else:
        # Summary output
        if result.output.get("status") == "success":
            success(f"Skill completed successfully")
        elif result.output.get("status") == "failure":
            error(f"Skill failed")
        else:
            warning(f"Skill status: {result.output.get('status', 'unknown')}")

        console.print()

        if result.output.get("summary"):
            info(f"Summary: {result.output['summary']}")

        if result.output.get("findings"):
            console.print("\n[bold]Findings:[/bold]")
            for finding in result.output["findings"]:
                console.print(f"  • {finding}")

        if result.output.get("recommendations"):
            console.print("\n[bold]Recommendations:[/bold]")
            for rec in result.output["recommendations"]:
                console.print(f"  • {rec}")

        # Metrics
        console.print()
        muted(f"Duration: {result.duration_ms:.0f}ms | Tokens: {result.total_tokens} | LLM calls: {result.llm_calls}")

        if not no_record:
            muted(f"Trace ID: {result.trace_id}")
```

**Step 2: Add required imports at top of file**

```python
import os
```

**Step 3: Commit**

```bash
git add tools/kubani-dev/src/kubani_dev/commands/skill.py
git commit -m "feat(kubani-dev): add 'skill run' command

Execute skills with context and full tracing:
- kubani-dev skill run <skill> --context '{...}'
- Support for JSON context file
- Full trace output with --trace flag
- Summary or JSON output modes

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Add Model Comparison Matrix to Evaluations

**Files:**
- Create: `platform/agent-framework/src/agent_framework/evaluation/__init__.py`
- Create: `platform/agent-framework/src/agent_framework/evaluation/matrix.py`

**Step 1: Create evaluation directory**

```bash
mkdir -p platform/agent-framework/src/agent_framework/evaluation
```

**Step 2: Create evaluation/__init__.py**

```python
"""Evaluation framework for skills and agents."""

from agent_framework.evaluation.matrix import ModelMatrix, MatrixResult

__all__ = ["ModelMatrix", "MatrixResult"]
```

**Step 3: Create evaluation/matrix.py**

```python
"""Model comparison matrix for skill evaluation."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from agent_framework.llm import LLMClientWrapper
from agent_framework.skill_executor import SkillExecutor
from agent_framework.trace import ExecutionTrace

logger = logging.getLogger(__name__)


@dataclass
class MatrixConfig:
    """Configuration for a matrix dimension."""

    name: str
    values: list[Any]


@dataclass
class MatrixResult:
    """Result from a single matrix cell."""

    config: dict[str, Any]  # e.g., {"model": "opus", "thinking": True}
    trace: ExecutionTrace
    metrics: dict[str, Any]  # accuracy, latency, tokens


@dataclass
class MatrixReport:
    """Complete matrix evaluation report."""

    skill_name: str
    dimensions: list[str]
    results: list[MatrixResult]
    summary: dict[str, Any] = field(default_factory=dict)

    def to_table(self) -> list[list[str]]:
        """Convert to table format for display."""
        if not self.results:
            return []

        # Build header
        headers = list(self.results[0].config.keys()) + [
            "Accuracy", "Latency (ms)", "Tokens"
        ]

        rows = [headers]
        for r in self.results:
            row = list(str(v) for v in r.config.values())
            row.extend([
                f"{r.metrics.get('accuracy', 0):.1%}",
                f"{r.metrics.get('latency_ms', 0):.0f}",
                str(r.metrics.get('tokens', 0)),
            ])
            rows.append(row)

        return rows


class ModelMatrix:
    """
    Run skill evaluations across a matrix of configurations.

    Enables comparison across:
    - Models (opus, haiku, local)
    - Settings (thinking on/off, temperature)
    - Any other configurable dimension

    Example:
        matrix = ModelMatrix(
            dimensions=[
                MatrixConfig("model", ["opus", "haiku"]),
                MatrixConfig("thinking", [True, False]),
            ]
        )
        report = await matrix.evaluate(executor, skill_name, suite)
    """

    # Known model configurations
    MODEL_CONFIGS = {
        "opus": {
            "base_url": "https://api.anthropic.com/v1",
            "model": "claude-opus-4-5-20251101",
        },
        "sonnet": {
            "base_url": "https://api.anthropic.com/v1",
            "model": "claude-sonnet-4-20250514",
        },
        "haiku": {
            "base_url": "https://api.anthropic.com/v1",
            "model": "claude-3-5-haiku-20241022",
        },
        "local": {
            "base_url": "https://llm.almckay.io/v1",
            "model": "nvidia/Qwen3-14B-FP4",
        },
    }

    def __init__(self, dimensions: list[MatrixConfig]):
        """
        Initialize matrix evaluator.

        Args:
            dimensions: List of matrix dimensions to evaluate
        """
        self.dimensions = dimensions

    @classmethod
    def from_string(cls, matrix_str: str) -> "ModelMatrix":
        """
        Parse matrix from string format.

        Format: "dim1:val1,val2 dim2:val1,val2"
        Example: "model:opus,haiku thinking:on,off"
        """
        dimensions = []

        for part in matrix_str.split():
            if ":" not in part:
                continue

            name, values_str = part.split(":", 1)
            values = []

            for v in values_str.split(","):
                # Convert special values
                if v.lower() in ("on", "true", "yes"):
                    values.append(True)
                elif v.lower() in ("off", "false", "no"):
                    values.append(False)
                else:
                    values.append(v)

            dimensions.append(MatrixConfig(name, values))

        return cls(dimensions)

    def _generate_configs(self) -> list[dict[str, Any]]:
        """Generate all configuration combinations."""
        if not self.dimensions:
            return [{}]

        configs = [{}]
        for dim in self.dimensions:
            new_configs = []
            for config in configs:
                for value in dim.values:
                    new_config = config.copy()
                    new_config[dim.name] = value
                    new_configs.append(new_config)
            configs = new_configs

        return configs

    async def evaluate(
        self,
        skill_executor: SkillExecutor,
        skill_name: str,
        test_cases: list[dict[str, Any]],
    ) -> MatrixReport:
        """
        Run evaluation across all matrix configurations.

        Args:
            skill_executor: Base skill executor
            skill_name: Name of skill to evaluate
            test_cases: Test cases to run

        Returns:
            MatrixReport with all results
        """
        configs = self._generate_configs()
        results = []

        for config in configs:
            logger.info(f"Evaluating with config: {config}")

            # Create LLM client for this config
            llm_client = self._create_llm_client(config)

            # Create executor with this client
            executor = SkillExecutor(
                skills_dir=skill_executor.skills_dir,
                llm_client=llm_client,
            )

            # Run test cases
            case_results = []
            total_tokens = 0
            total_latency = 0
            passed = 0

            for case in test_cases:
                try:
                    trace = await executor.execute(
                        skill_name,
                        context=case.get("context", {}),
                    )

                    # Check assertions if present
                    case_passed = self._check_assertions(
                        trace.output,
                        case.get("expected", {}),
                    )

                    if case_passed:
                        passed += 1

                    total_tokens += trace.total_tokens
                    total_latency += trace.duration_ms or 0

                    case_results.append(trace)

                except Exception as e:
                    logger.error(f"Test case failed: {e}")

            # Close client
            if hasattr(llm_client, "close"):
                await llm_client.close()

            # Aggregate metrics
            metrics = {
                "accuracy": passed / len(test_cases) if test_cases else 0,
                "latency_ms": total_latency / len(test_cases) if test_cases else 0,
                "tokens": total_tokens,
                "passed": passed,
                "total": len(test_cases),
            }

            results.append(MatrixResult(
                config=config,
                trace=case_results[-1] if case_results else None,
                metrics=metrics,
            ))

        return MatrixReport(
            skill_name=skill_name,
            dimensions=[d.name for d in self.dimensions],
            results=results,
        )

    def _create_llm_client(self, config: dict[str, Any]) -> LLMClientWrapper:
        """Create LLM client for a configuration."""
        # Get model config
        model_name = config.get("model", "local")
        model_config = self.MODEL_CONFIGS.get(model_name, self.MODEL_CONFIGS["local"])

        # Apply thinking setting
        enable_thinking = config.get("thinking", True)

        return LLMClientWrapper(
            base_url=model_config["base_url"],
            model=model_config["model"],
            enable_thinking=enable_thinking,
        )

    def _check_assertions(
        self,
        output: dict[str, Any],
        expected: dict[str, Any],
    ) -> bool:
        """Check if output matches expected assertions."""
        if not expected:
            return True

        for key, expected_value in expected.items():
            actual_value = output.get(key)

            if isinstance(expected_value, str) and expected_value.startswith("contains:"):
                # Check if value contains substring
                search = expected_value[9:]
                if search not in str(actual_value):
                    return False
            elif actual_value != expected_value:
                return False

        return True
```

**Step 4: Commit**

```bash
git add platform/agent-framework/src/agent_framework/evaluation/
git commit -m "feat(framework): add model comparison matrix

Evaluate skills across configuration matrix:
- ModelMatrix with configurable dimensions
- Support for model, thinking, temperature dimensions
- Parse from string: 'model:opus,haiku thinking:on,off'
- MatrixReport with table output

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Add Matrix Evaluation to CLI

**Files:**
- Modify: `tools/kubani-dev/src/kubani_dev/commands/skill.py`

**Step 1: Update the eval command to support matrix**

Modify the existing `eval` command or add `eval-matrix` command:

```python
@skill_group.command(name="eval-matrix")
@click.argument("skill_name")
@click.option("--suite", "-s", type=click.Path(exists=True), help="Evaluation suite YAML")
@click.option("--matrix", "-m", default="model:local", help="Matrix config (e.g., 'model:opus,haiku thinking:on,off')")
@click.option("--llm-url", help="Default LLM base URL")
@click.option("--output", "-o", type=click.Choice(["table", "json"]), default="table")
def eval_matrix(
    skill_name: str,
    suite: Optional[str],
    matrix: str,
    llm_url: Optional[str],
    output: str,
):
    """
    Evaluate skill across model/config matrix.

    \b
    Examples:
        kubani-dev skill eval-matrix investigate-pod-failure \\
            --matrix "model:opus,haiku thinking:on,off"

        kubani-dev skill eval-matrix my-skill \\
            --suite test_cases.yaml \\
            --matrix "model:local,opus"
    """
    import asyncio
    import yaml
    from pathlib import Path

    # Get skills directory
    skills_dir = Path.cwd() / "agents" / "skills"
    if not skills_dir.exists():
        skills_dir = Path(__file__).parents[4] / "agents" / "skills"

    # Load test cases
    test_cases = []
    if suite:
        with open(suite) as f:
            suite_data = yaml.safe_load(f)
            test_cases = suite_data.get("test_cases", [])
    else:
        # Try to find test_cases.yaml in skill directory
        skill_path = skills_dir / skill_name.replace("/", os.sep)
        test_file = skill_path / "test_cases.yaml"
        if test_file.exists():
            with open(test_file) as f:
                suite_data = yaml.safe_load(f)
                test_cases = suite_data.get("test_cases", [])

    if not test_cases:
        warning("No test cases found. Running with empty context.")
        test_cases = [{"name": "default", "context": {}}]

    async def run_matrix():
        from agent_framework.skill_executor import SkillExecutor
        from agent_framework.evaluation import ModelMatrix
        from agent_framework.llm import LLMClientWrapper

        # Create base executor
        llm = LLMClientWrapper(
            base_url=llm_url or os.getenv("LLM_BASE_URL", "https://llm.almckay.io/v1"),
        )
        executor = SkillExecutor(skills_dir=skills_dir, llm_client=llm)

        # Create matrix
        model_matrix = ModelMatrix.from_string(matrix)

        info(f"Running matrix evaluation for [bold]{skill_name}[/bold]")
        info(f"Matrix: {matrix}")
        info(f"Test cases: {len(test_cases)}")
        console.print()

        with spinner("Running matrix evaluation..."):
            report = await model_matrix.evaluate(executor, skill_name, test_cases)

        await llm.close()
        return report

    report = asyncio.run(run_matrix())

    # Output results
    if output == "json":
        import json
        console.print_json(json.dumps({
            "skill": report.skill_name,
            "dimensions": report.dimensions,
            "results": [
                {
                    "config": r.config,
                    "metrics": r.metrics,
                }
                for r in report.results
            ],
        }, indent=2))
    else:
        # Table output
        table = create_table(title=f"Matrix Evaluation: {report.skill_name}")

        rows = report.to_table()
        if rows:
            for header in rows[0]:
                table.add_column(header)
            for row in rows[1:]:
                # Color code accuracy
                colored_row = list(row)
                acc_idx = len(row) - 3  # Accuracy column
                acc_val = float(row[acc_idx].rstrip('%')) / 100
                if acc_val >= 0.9:
                    colored_row[acc_idx] = f"[green]{row[acc_idx]}[/green]"
                elif acc_val >= 0.7:
                    colored_row[acc_idx] = f"[yellow]{row[acc_idx]}[/yellow]"
                else:
                    colored_row[acc_idx] = f"[red]{row[acc_idx]}[/red]"
                table.add_row(*colored_row)

        console.print(table)
```

**Step 2: Commit**

```bash
git add tools/kubani-dev/src/kubani_dev/commands/skill.py
git commit -m "feat(kubani-dev): add 'skill eval-matrix' command

Evaluate skills across configuration matrix:
- kubani-dev skill eval-matrix <skill> --matrix 'model:opus,haiku'
- Table and JSON output formats
- Color-coded accuracy results

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Add `kubani-dev skill traces` Command

**Files:**
- Modify: `tools/kubani-dev/src/kubani_dev/commands/skill.py`

**Step 1: Add traces command**

```python
@skill_group.command(name="traces")
@click.argument("skill_name")
@click.option("--last", "-n", default=10, help="Number of traces to show")
@click.option("--output", "-o", type=click.Choice(["table", "json"]), default="table")
def show_traces(
    skill_name: str,
    last: int,
    output: str,
):
    """
    Show recent execution traces for a skill.

    \b
    Examples:
        kubani-dev skill traces investigate-pod-failure
        kubani-dev skill traces my-skill --last 5 --output json
    """
    import asyncio
    from pathlib import Path

    skills_dir = Path.cwd() / "agents" / "skills"
    if not skills_dir.exists():
        skills_dir = Path(__file__).parents[4] / "agents" / "skills"

    async def get_traces():
        from agent_framework.skill_executor import SkillExecutor

        executor = SkillExecutor(skills_dir=skills_dir)
        return await executor.get_recent_traces(skill_name, limit=last)

    traces = asyncio.run(get_traces())

    if not traces:
        warning(f"No traces found for skill: {skill_name}")
        return

    if output == "json":
        import json
        console.print_json(json.dumps([t.model_dump() for t in traces], indent=2, default=str))
    else:
        # Table output
        table = create_table(title=f"Recent Traces: {skill_name}")
        table.add_column("Trace ID", style="cyan")
        table.add_column("Time")
        table.add_column("Status")
        table.add_column("Duration")
        table.add_column("Tokens")

        for t in traces:
            status = t.output.get("status", "unknown")
            status_color = "green" if status == "success" else "red" if status == "failure" else "yellow"

            table.add_row(
                t.trace_id[:12],
                t.start_time.strftime("%Y-%m-%d %H:%M"),
                f"[{status_color}]{status}[/{status_color}]",
                f"{t.duration_ms:.0f}ms" if t.duration_ms else "—",
                str(t.total_tokens),
            )

        console.print(table)
```

**Step 2: Commit**

```bash
git add tools/kubani-dev/src/kubani_dev/commands/skill.py
git commit -m "feat(kubani-dev): add 'skill traces' command

View recent execution traces:
- kubani-dev skill traces <skill> --last 10
- Table and JSON output formats

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Add Feature Flag for Skills V2

**Files:**
- Modify: `agents/core/src/core_agents/config_unified.py`

**Step 1: Add feature flag to config**

Add to the config model:

```python
class FeatureFlags(BaseModel):
    """Feature flags for gradual rollout."""

    skills_v2: bool = Field(
        default=False,
        description="Use new skill loading from agent-framework"
    )
    trace_recording: bool = Field(
        default=True,
        description="Record execution traces"
    )
```

Add to main config:

```python
class KubaniConfig(BaseModel):
    # ... existing fields ...

    features: FeatureFlags = Field(
        default_factory=FeatureFlags,
        description="Feature flags"
    )
```

**Step 2: Commit**

```bash
git add agents/core/src/core_agents/config_unified.py
git commit -m "feat(config): add feature flags for skills v2

Feature flags for gradual rollout:
- features.skills_v2: Use new agent-framework skill loading
- features.trace_recording: Enable trace recording

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Update Package Exports

**Files:**
- Modify: `platform/agent-framework/src/agent_framework/__init__.py`

**Step 1: Update __init__.py to include new modules**

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

Example:
    from agent_framework import AgentBase, AgentRunner, SkillExecutor
    from agent_framework.llm import LLMClientWrapper
    from agent_framework.evaluation import ModelMatrix
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

__version__ = "0.2.0"
```

**Step 2: Commit**

```bash
git add platform/agent-framework/src/agent_framework/__init__.py
git commit -m "feat(framework): update exports, bump to 0.2.0

Added LLM and evaluation modules to framework.
Version bump for Phase 3 features.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 9: Add Tests for New Functionality

**Files:**
- Create: `platform/agent-framework/tests/test_llm_executor.py`
- Create: `platform/agent-framework/tests/test_matrix.py`

**Step 1: Create test_llm_executor.py**

```python
"""Tests for LLM skill executor."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from agent_framework.llm import LLMClientWrapper, LLMSkillExecutor
from agent_framework.trace import ExecutionTrace


class TestLLMClientWrapper:
    """Tests for LLMClientWrapper."""

    def test_client_creation(self):
        """Test client can be created with defaults."""
        client = LLMClientWrapper()
        assert client.base_url == "https://llm.almckay.io/v1"
        assert client.model == "nvidia/Qwen3-14B-FP4"

    def test_client_custom_config(self):
        """Test client with custom config."""
        client = LLMClientWrapper(
            base_url="http://localhost:11434/v1",
            model="llama2",
            temperature=0.5,
        )
        assert client.base_url == "http://localhost:11434/v1"
        assert client.model == "llama2"
        assert client.temperature == 0.5


class TestLLMSkillExecutor:
    """Tests for LLMSkillExecutor."""

    def test_parse_json_response(self):
        """Test JSON parsing from LLM response."""
        client = MagicMock()
        executor = LLMSkillExecutor(client)

        # Direct JSON
        result = executor._parse_response('{"status": "success"}')
        assert result["status"] == "success"

        # JSON in code block
        result = executor._parse_response('```json\n{"status": "success"}\n```')
        assert result["status"] == "success"

        # JSON embedded in text
        result = executor._parse_response('Here is the result: {"status": "success"}')
        assert result["status"] == "success"

    def test_parse_invalid_response(self):
        """Test fallback for unparseable response."""
        client = MagicMock()
        executor = LLMSkillExecutor(client)

        result = executor._parse_response("This is not JSON at all")
        assert result["status"] == "unknown"
        assert "raw_response" in result
```

**Step 2: Create test_matrix.py**

```python
"""Tests for model comparison matrix."""

import pytest

from agent_framework.evaluation import ModelMatrix, MatrixResult
from agent_framework.evaluation.matrix import MatrixConfig


class TestModelMatrix:
    """Tests for ModelMatrix."""

    def test_parse_from_string(self):
        """Test matrix parsing from string."""
        matrix = ModelMatrix.from_string("model:opus,haiku thinking:on,off")

        assert len(matrix.dimensions) == 2
        assert matrix.dimensions[0].name == "model"
        assert matrix.dimensions[0].values == ["opus", "haiku"]
        assert matrix.dimensions[1].name == "thinking"
        assert matrix.dimensions[1].values == [True, False]

    def test_generate_configs(self):
        """Test configuration generation."""
        matrix = ModelMatrix([
            MatrixConfig("model", ["a", "b"]),
            MatrixConfig("thinking", [True, False]),
        ])

        configs = matrix._generate_configs()

        assert len(configs) == 4
        assert {"model": "a", "thinking": True} in configs
        assert {"model": "a", "thinking": False} in configs
        assert {"model": "b", "thinking": True} in configs
        assert {"model": "b", "thinking": False} in configs

    def test_check_assertions(self):
        """Test assertion checking."""
        matrix = ModelMatrix([])

        # Exact match
        assert matrix._check_assertions(
            {"status": "success"},
            {"status": "success"},
        )

        # Contains check
        assert matrix._check_assertions(
            {"summary": "Found OOM kill in logs"},
            {"summary": "contains:OOM"},
        )

        # Mismatch
        assert not matrix._check_assertions(
            {"status": "failure"},
            {"status": "success"},
        )
```

**Step 3: Commit**

```bash
git add platform/agent-framework/tests/test_llm_executor.py
git add platform/agent-framework/tests/test_matrix.py
git commit -m "test(framework): add tests for LLM executor and matrix

Tests for Phase 3 functionality:
- LLMClientWrapper configuration
- LLMSkillExecutor JSON parsing
- ModelMatrix string parsing
- Configuration generation
- Assertion checking

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 10: Run Tests and Validate

**Step 1: Reinstall framework**

```bash
cd platform/agent-framework
pip install -e ".[dev]"
```

**Step 2: Run all tests**

```bash
cd platform/agent-framework
pytest tests/ -v
```

Expected: All tests pass

**Step 3: Test CLI commands**

```bash
# Test skill run (may need real LLM)
kubani-dev skill run --help

# Test eval-matrix
kubani-dev skill eval-matrix --help

# Test traces
kubani-dev skill traces --help
```

**Step 4: Commit any fixes**

```bash
git status
# Fix and commit if needed
```

---

## Task 11: Final Verification

**Step 1: Verify module structure**

```bash
ls -la platform/agent-framework/src/agent_framework/
ls -la platform/agent-framework/src/agent_framework/llm/
ls -la platform/agent-framework/src/agent_framework/evaluation/
```

**Step 2: Test imports**

```bash
python -c "from agent_framework.llm import LLMClientWrapper, LLMSkillExecutor; print('LLM: OK')"
python -c "from agent_framework.evaluation import ModelMatrix; print('Evaluation: OK')"
```

**Step 3: Test end-to-end skill execution (optional, requires LLM)**

```bash
# If LLM is available
kubani-dev skill run k8s/diagnostic/investigate-pod-failure \
    --context '{"pod": "test-pod", "namespace": "default"}' \
    --trace
```

**Step 4: Review commits**

```bash
git log --oneline feature/restructure ^main | head -20
```

---

## Post-Phase 3 Checklist

- [ ] LLM integration complete (`agent_framework.llm`)
- [ ] SkillExecutor uses LLM for execution
- [ ] `kubani-dev skill run` command works
- [ ] `kubani-dev skill eval-matrix` command works
- [ ] `kubani-dev skill traces` command works
- [ ] Feature flags added to config
- [ ] All tests pass
- [ ] Framework version bumped to 0.2.0

---

## Notes

- LLM execution requires network access to LLM endpoint
- Model matrix with Anthropic models requires API key in environment
- Traces are stored in `skills/<skill-name>/.traces/` by default (gitignored)
- Feature flag `features.skills_v2` enables new skill loading in agents
