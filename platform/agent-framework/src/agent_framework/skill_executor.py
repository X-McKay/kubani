"""SkillExecutor - Run and evaluate skills in isolation."""

from __future__ import annotations

import logging
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
        self.trace_backend = trace_backend or JsonlBackend(self.skills_dir / ".traces")
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
            passed = all(k in trace.output for k in expected.keys())

            results.append(
                {
                    "case": case.get("name", "unnamed"),
                    "passed": passed,
                    "trace_id": trace.trace_id,
                    "duration_ms": trace.duration_ms,
                    "tokens": trace.total_tokens,
                }
            )

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

        return await self.trace_backend.query(TraceQuery(skill_name=skill_name, limit=limit))
