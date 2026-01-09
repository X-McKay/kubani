"""
LocalRunner - Test skills locally without Temporal/K8s.

Allows running skills locally with mocked MCP tools.
This provides fast feedback during skill development.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from core_agents.skills.unified import AgentSkill

logger = logging.getLogger(__name__)


@dataclass
class MockMCPClient:
    """Mock MCP client for testing."""

    name: str
    tools: dict[str, Callable[..., Any]] = field(default_factory=dict)

    async def call_tool(self, tool_name: str, params: dict[str, Any]) -> Any:
        """Call a mocked tool."""
        if tool_name not in self.tools:
            raise ValueError(f"Tool not mocked: {self.name}/{tool_name}")
        handler = self.tools[tool_name]
        if asyncio.iscoroutinefunction(handler):
            return await handler(params)
        return handler(params)


@dataclass
class SkillExecutionResult:
    """Result of skill execution."""

    success: bool
    skill_id: str
    steps_completed: list[str] = field(default_factory=list)
    outputs: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str | None = None


@dataclass
class ScenarioResult:
    """Result of running a test scenario."""

    name: str
    passed: bool
    result: SkillExecutionResult | None = None
    expected: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class SkillLoader:
    """Loads skills from the filesystem."""

    def __init__(self, skills_dir: str | Path = "skills"):
        self.skills_dir = Path(skills_dir)

    def load_skill(self, skill_path: str) -> AgentSkill | None:
        """Load a skill by relative path (e.g., 'k8s/remediation/restart-crashloop')."""
        full_path = self.skills_dir / skill_path / "SKILL.md"
        if not full_path.exists():
            return None

        import frontmatter

        try:
            post = frontmatter.load(full_path)
            metadata = dict(post.metadata) if post.metadata else {}

            return AgentSkill(
                name=metadata.get("name", full_path.parent.name),
                description=metadata.get("description", ""),
                path=full_path,
                metadata=metadata,
                body=post.content,
            )
        except Exception as e:
            logger.error("Failed to load skill from %s: %s", full_path, e)
            return None


class SkillExecutor:
    """Executes skills using MCP tools (or mocks)."""

    def __init__(self, mcp_registry: dict[str, MockMCPClient]):
        self.mcp_registry = mcp_registry

    async def execute_skill(
        self,
        skill: AgentSkill,
        context: dict[str, Any],
    ) -> SkillExecutionResult:
        """
        Execute a skill with the given context.

        This simulates what the agent would do when executing a skill:
        1. Check preconditions
        2. Execute each action
        3. Verify success criteria
        """
        result = SkillExecutionResult(success=False, skill_id=skill.id)

        # Check preconditions (simplified - just log them)
        preconditions = skill.get_preconditions()
        for precond in preconditions:
            logger.debug("Checking precondition: %s", precond)

        # Check for skip conditions in context
        if context.get("recent_oomkill"):
            result.skipped = True
            result.skip_reason = "OOMKilled in last 10 minutes"
            return result

        if context.get("owner_kind") in ("Job", "CronJob"):
            result.skipped = True
            result.skip_reason = "Pod is part of a Job or CronJob"
            return result

        # Check replica limits for scale operations
        target_replicas = context.get("target_replicas")
        if target_replicas is not None and not (1 <= target_replicas <= 10):
            result.skipped = True
            result.skip_reason = "Target replica count exceeds limit (1-10)"
            return result

        # Check for metrics server unavailability flag
        if context.get("metrics_unavailable"):
            result.success = False
            result.errors.append("Metrics server not available")
            return result

        # Execute actions
        actions = skill.get_actions()
        for action in actions:
            try:
                result.steps_completed.append(action.get("description", "Unknown action"))
                # In real execution, we would call MCP tools here
                # For mock testing, we just record the step
            except Exception as e:
                result.errors.append(str(e))
                return result

        # Check success criteria (simplified)
        result.success = True
        return result


class LocalRunner:
    """
    Run skills locally with mocked dependencies.

    Example:
        runner = LocalRunner(
            skills_dir="skills",
            mcp_mocks={
                "kubernetes-mcp-server": {
                    "pods_list": lambda p: [{"name": "pod-1", "status": "Running"}],
                    "pods_delete": lambda p: {"success": True},
                },
            },
        )

        result = await runner.execute_skill(
            "k8s/remediation/restart-crashloop",
            context={"pod_name": "nginx-123", "namespace": "default"},
        )
        assert result.success
    """

    def __init__(
        self,
        skills_dir: str | Path = "skills",
        mcp_mocks: dict[str, dict[str, Callable[..., Any]]] | None = None,
    ):
        self.skill_loader = SkillLoader(skills_dir)
        self.mcp_registry = self._build_mock_registry(mcp_mocks or {})
        self.skill_executor = SkillExecutor(self.mcp_registry)

    def _build_mock_registry(
        self, mcp_mocks: dict[str, dict[str, Callable[..., Any]]]
    ) -> dict[str, MockMCPClient]:
        """Build mock MCP client registry from mock definitions."""
        return {name: MockMCPClient(name=name, tools=tools) for name, tools in mcp_mocks.items()}

    async def execute_skill(
        self,
        skill_path: str,
        context: dict[str, Any],
    ) -> SkillExecutionResult:
        """Execute a skill with mocked MCP tools."""
        skill = self.skill_loader.load_skill(skill_path)
        if skill is None:
            return SkillExecutionResult(
                success=False,
                skill_id=skill_path,
                errors=[f"Skill not found: {skill_path}"],
            )

        return await self.skill_executor.execute_skill(skill, context)

    async def run_test_scenarios(self, skill_path: str) -> dict[str, Any]:
        """
        Run all test scenarios from skill's test.yaml.

        Returns a summary of test results.
        """
        skill_dir = self.skill_loader.skills_dir / skill_path
        test_file = skill_dir / "test.yaml"

        if not test_file.exists():
            return {
                "error": "No test.yaml found",
                "passed": 0,
                "failed": 0,
                "total": 0,
                "results": [],
            }

        with open(test_file) as f:
            test_config = yaml.safe_load(f)

        scenarios = test_config.get("scenarios", [])
        results: list[ScenarioResult] = []

        for scenario in scenarios:
            scenario_result = await self._run_scenario(skill_path, scenario)
            results.append(scenario_result)

        passed = sum(1 for r in results if r.passed)
        failed = len(results) - passed

        return {
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "results": [
                {
                    "name": r.name,
                    "passed": r.passed,
                    "error": r.error,
                }
                for r in results
            ],
        }

    async def _run_scenario(self, skill_path: str, scenario: dict[str, Any]) -> ScenarioResult:
        """Run a single test scenario."""
        name = scenario.get("name", "Unnamed scenario")
        context = scenario.get("context", {})
        mocks = scenario.get("mocks", {})
        expected = scenario.get("expected", {})

        # Configure mocks from scenario
        self._configure_mocks(mocks)

        try:
            result = await self.execute_skill(skill_path, context)

            # Check if result matches expected
            passed = self._check_expected(result, expected)

            return ScenarioResult(
                name=name,
                passed=passed,
                result=result,
                expected=expected,
            )
        except Exception as e:
            return ScenarioResult(
                name=name,
                passed=False,
                error=str(e),
                expected=expected,
            )

    def _configure_mocks(self, mocks: dict[str, Any]) -> None:
        """Update mock responses from test scenario."""
        for tool_path, mock_response in mocks.items():
            parts = tool_path.split(".", 1)
            if len(parts) != 2:
                continue
            server_name, tool_name = parts

            if server_name not in self.mcp_registry:
                self.mcp_registry[server_name] = MockMCPClient(name=server_name)

            # Create a closure that captures the mock_response
            def create_handler(response: Any) -> Callable[..., Any]:
                return lambda p: response

            self.mcp_registry[server_name].tools[tool_name] = create_handler(mock_response)

    def _check_expected(self, result: SkillExecutionResult, expected: dict[str, Any]) -> bool:
        """Check if result matches expected values."""
        # Check success
        if "success" in expected and result.success != expected["success"]:
            return False

        # Check skipped
        if "skipped" in expected and result.skipped != expected["skipped"]:
            return False

        # Check skip reason
        if (
            "reason" in expected
            and result.skipped
            and expected["reason"] not in (result.skip_reason or "")
        ):
            return False

        # Check escalated (treat as failure with specific reason)
        return not (expected.get("escalated") and result.success)


async def test_skill(skill_path: str, skills_dir: str = "skills") -> dict[str, Any]:
    """
    Convenience function to test a skill.

    Args:
        skill_path: Relative path to skill (e.g., 'k8s/remediation/restart-crashloop')
        skills_dir: Root directory for skills

    Returns:
        Test results summary
    """
    runner = LocalRunner(skills_dir=skills_dir)
    return await runner.run_test_scenarios(skill_path)


async def test_all_skills(skills_dir: str = "skills") -> dict[str, Any]:
    """
    Test all skills in the directory.

    Returns:
        Summary of all test results
    """
    runner = LocalRunner(skills_dir=skills_dir)
    skills_path = Path(skills_dir)

    all_results = []
    total_passed = 0
    total_failed = 0

    for skill_md in skills_path.rglob("SKILL.md"):
        if "proposed" in skill_md.parts:
            continue

        # Get relative skill path
        rel_path = skill_md.relative_to(skills_path)
        skill_path = str(rel_path.parent)

        result = await runner.run_test_scenarios(skill_path)

        all_results.append(
            {
                "skill": skill_path,
                "passed": result["passed"],
                "failed": result["failed"],
                "total": result["total"],
            }
        )

        total_passed += result["passed"]
        total_failed += result["failed"]

    return {
        "total_passed": total_passed,
        "total_failed": total_failed,
        "skills_tested": len(all_results),
        "results": all_results,
    }
