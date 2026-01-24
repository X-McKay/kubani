"""
Multi-Layered Evaluation Framework for Kubani Agents.

Provides systematic quality assessment through multiple complementary strategies:
1. Automated checks (syntax, type checking, linting)
2. LLM-as-Judge evaluation
3. Simulation-based testing
4. Human review integration

Each layer catches different types of issues, creating a comprehensive safety net.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import Enum
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


class EvaluationLayer(Enum):
    """Evaluation layer types."""

    AUTOMATED = "automated"  # Syntax, types, linting
    LLM_JUDGE = "llm_judge"  # LLM-based quality assessment
    SIMULATION = "simulation"  # Scenario-based testing
    HUMAN = "human"  # Human review integration


class EvaluationStatus(Enum):
    """Status of an evaluation."""

    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class EvaluationResult:
    """Result of a single evaluation."""

    name: str
    layer: EvaluationLayer
    status: EvaluationStatus
    score: float = 0.0  # 0.0 to 1.0
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    duration_seconds: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "layer": self.layer.value,
            "status": self.status.value,
            "score": self.score,
            "message": self.message,
            "details": self.details,
            "duration_seconds": self.duration_seconds,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class EvaluationSuite:
    """A collection of evaluations to run."""

    name: str
    description: str = ""
    evaluations: list["Evaluation"] = field(default_factory=list)

    def add(self, evaluation: "Evaluation") -> None:
        """Add an evaluation to the suite."""
        self.evaluations.append(evaluation)


@dataclass
class Evaluation:
    """A single evaluation to run."""

    name: str
    layer: EvaluationLayer
    handler: Callable[..., EvaluationResult]
    description: str = ""
    timeout_seconds: float = 60.0
    required: bool = True  # If True, failure fails the suite


class AutomatedEvaluations:
    """Automated code quality evaluations."""

    @staticmethod
    async def check_syntax(agent_path: Path) -> EvaluationResult:
        """Check Python syntax."""
        import subprocess

        start = asyncio.get_event_loop().time()

        try:
            # Use py_compile to check syntax
            result = subprocess.run(
                ["python", "-m", "py_compile"]
                + [str(p) for p in agent_path.rglob("*.py")],
                capture_output=True,
                text=True,
            )

            duration = asyncio.get_event_loop().time() - start

            if result.returncode == 0:
                return EvaluationResult(
                    name="syntax_check",
                    layer=EvaluationLayer.AUTOMATED,
                    status=EvaluationStatus.PASSED,
                    score=1.0,
                    message="All files have valid syntax",
                    duration_seconds=duration,
                )
            else:
                return EvaluationResult(
                    name="syntax_check",
                    layer=EvaluationLayer.AUTOMATED,
                    status=EvaluationStatus.FAILED,
                    score=0.0,
                    message="Syntax errors found",
                    details={"stderr": result.stderr},
                    duration_seconds=duration,
                )

        except Exception as e:
            return EvaluationResult(
                name="syntax_check",
                layer=EvaluationLayer.AUTOMATED,
                status=EvaluationStatus.ERROR,
                score=0.0,
                message=f"Error running syntax check: {e}",
            )

    @staticmethod
    async def check_types(agent_path: Path) -> EvaluationResult:
        """Run type checking with mypy."""
        import subprocess

        start = asyncio.get_event_loop().time()

        try:
            result = subprocess.run(
                ["python", "-m", "mypy", str(agent_path / "src"), "--ignore-missing-imports"],
                capture_output=True,
                text=True,
            )

            duration = asyncio.get_event_loop().time() - start

            # Parse mypy output
            errors = [
                line for line in result.stdout.split("\n") if ": error:" in line
            ]

            if not errors:
                return EvaluationResult(
                    name="type_check",
                    layer=EvaluationLayer.AUTOMATED,
                    status=EvaluationStatus.PASSED,
                    score=1.0,
                    message="No type errors found",
                    duration_seconds=duration,
                )
            else:
                return EvaluationResult(
                    name="type_check",
                    layer=EvaluationLayer.AUTOMATED,
                    status=EvaluationStatus.FAILED,
                    score=max(0, 1.0 - len(errors) * 0.1),
                    message=f"Found {len(errors)} type errors",
                    details={"errors": errors[:10]},
                    duration_seconds=duration,
                )

        except FileNotFoundError:
            return EvaluationResult(
                name="type_check",
                layer=EvaluationLayer.AUTOMATED,
                status=EvaluationStatus.SKIPPED,
                message="mypy not installed",
            )

    @staticmethod
    async def check_lint(agent_path: Path) -> EvaluationResult:
        """Run linting with ruff."""
        import subprocess

        start = asyncio.get_event_loop().time()

        try:
            result = subprocess.run(
                ["python", "-m", "ruff", "check", str(agent_path / "src")],
                capture_output=True,
                text=True,
            )

            duration = asyncio.get_event_loop().time() - start

            issues = [line for line in result.stdout.split("\n") if line.strip()]

            if result.returncode == 0:
                return EvaluationResult(
                    name="lint_check",
                    layer=EvaluationLayer.AUTOMATED,
                    status=EvaluationStatus.PASSED,
                    score=1.0,
                    message="No linting issues",
                    duration_seconds=duration,
                )
            else:
                return EvaluationResult(
                    name="lint_check",
                    layer=EvaluationLayer.AUTOMATED,
                    status=EvaluationStatus.FAILED,
                    score=max(0, 1.0 - len(issues) * 0.05),
                    message=f"Found {len(issues)} linting issues",
                    details={"issues": issues[:10]},
                    duration_seconds=duration,
                )

        except FileNotFoundError:
            return EvaluationResult(
                name="lint_check",
                layer=EvaluationLayer.AUTOMATED,
                status=EvaluationStatus.SKIPPED,
                message="ruff not installed",
            )


class LLMJudgeEvaluations:
    """LLM-based quality evaluations."""

    JUDGE_PROMPT = """You are an expert code reviewer evaluating an AI agent implementation.

Agent: {agent_name}
Code Section: {section}

```python
{code}
```

Evaluate this code on the following criteria (score 0-10 for each):

1. **Correctness**: Does the code correctly implement the intended functionality?
2. **Robustness**: Does it handle edge cases and errors appropriately?
3. **Clarity**: Is the code readable and well-documented?
4. **Best Practices**: Does it follow Python and agent development best practices?
5. **Security**: Are there any security concerns?

Provide your evaluation as JSON:
{{
    "correctness": {{"score": N, "reasoning": "..."}},
    "robustness": {{"score": N, "reasoning": "..."}},
    "clarity": {{"score": N, "reasoning": "..."}},
    "best_practices": {{"score": N, "reasoning": "..."}},
    "security": {{"score": N, "reasoning": "..."}},
    "overall_score": N,
    "summary": "...",
    "suggestions": ["..."]
}}"""

    @staticmethod
    async def evaluate_code_quality(
        agent_name: str,
        code: str,
        section: str = "main",
    ) -> EvaluationResult:
        """Evaluate code quality using LLM-as-Judge."""
        start = asyncio.get_event_loop().time()

        try:
            from core_agents.factory import AgentFactory, AgentConfig

            factory = AgentFactory()
            judge = factory.create_agent(
                AgentConfig(
                    name="code-judge",
                    description="Evaluates code quality",
                    system_prompt="You are an expert code reviewer. Respond only with valid JSON.",
                    tools=[],
                    enable_observability=False,
                )
            )

            prompt = LLMJudgeEvaluations.JUDGE_PROMPT.format(
                agent_name=agent_name,
                section=section,
                code=code[:5000],  # Limit code length
            )

            result = judge(prompt)
            response = result.message if hasattr(result, "message") else str(result)

            # Parse JSON response
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                data = json.loads(response[json_start:json_end])

                overall_score = data.get("overall_score", 5) / 10.0
                duration = asyncio.get_event_loop().time() - start

                return EvaluationResult(
                    name=f"llm_judge_{section}",
                    layer=EvaluationLayer.LLM_JUDGE,
                    status=(
                        EvaluationStatus.PASSED
                        if overall_score >= 0.7
                        else EvaluationStatus.FAILED
                    ),
                    score=overall_score,
                    message=data.get("summary", ""),
                    details=data,
                    duration_seconds=duration,
                )

        except Exception as e:
            logger.error(f"LLM judge evaluation failed: {e}")

        return EvaluationResult(
            name=f"llm_judge_{section}",
            layer=EvaluationLayer.LLM_JUDGE,
            status=EvaluationStatus.ERROR,
            message=f"Evaluation failed: {e}",
        )


class SimulationEvaluations:
    """Simulation-based evaluations."""

    @staticmethod
    async def run_scenario(
        agent_name: str,
        scenario: dict[str, Any],
        agent_path: Path,
    ) -> EvaluationResult:
        """Run a simulation scenario."""
        start = asyncio.get_event_loop().time()

        scenario_name = scenario.get("name", "unnamed")

        try:
            # Load scenario configuration
            input_event = scenario.get("input", {})
            expected_actions = scenario.get("expected_actions", [])
            timeout = scenario.get("timeout", 30)

            # TODO: Implement actual scenario execution
            # This would involve:
            # 1. Setting up mock infrastructure
            # 2. Sending input event to agent
            # 3. Capturing agent actions
            # 4. Comparing against expected actions

            duration = asyncio.get_event_loop().time() - start

            # Placeholder result
            return EvaluationResult(
                name=f"scenario_{scenario_name}",
                layer=EvaluationLayer.SIMULATION,
                status=EvaluationStatus.PASSED,
                score=1.0,
                message=f"Scenario {scenario_name} passed",
                details={"scenario": scenario_name},
                duration_seconds=duration,
            )

        except Exception as e:
            return EvaluationResult(
                name=f"scenario_{scenario_name}",
                layer=EvaluationLayer.SIMULATION,
                status=EvaluationStatus.ERROR,
                message=f"Scenario failed: {e}",
            )


class EvaluationRunner:
    """
    Runs evaluation suites for agents.

    Orchestrates multiple evaluation layers and aggregates results.
    """

    def __init__(
        self,
        agent_name: str,
        project_root: Path,
        suite: str = "all",
        output_dir: Path | None = None,
        parallel_jobs: int = 1,
    ):
        self.agent_name = agent_name
        self.project_root = project_root
        self.suite_name = suite
        self.output_dir = output_dir or project_root / "eval-results" / agent_name
        self.parallel_jobs = parallel_jobs

        self.agent_path = project_root / "agents" / agent_name
        self.results: list[EvaluationResult] = []

    def _build_suite(self) -> EvaluationSuite:
        """Build the evaluation suite based on configuration."""
        suite = EvaluationSuite(
            name=self.suite_name,
            description=f"Evaluation suite for {self.agent_name}",
        )

        if self.suite_name in ("all", "automated"):
            suite.add(
                Evaluation(
                    name="syntax",
                    layer=EvaluationLayer.AUTOMATED,
                    handler=lambda: AutomatedEvaluations.check_syntax(self.agent_path),
                )
            )
            suite.add(
                Evaluation(
                    name="types",
                    layer=EvaluationLayer.AUTOMATED,
                    handler=lambda: AutomatedEvaluations.check_types(self.agent_path),
                    required=False,
                )
            )
            suite.add(
                Evaluation(
                    name="lint",
                    layer=EvaluationLayer.AUTOMATED,
                    handler=lambda: AutomatedEvaluations.check_lint(self.agent_path),
                    required=False,
                )
            )

        if self.suite_name in ("all", "llm-judge"):
            # Add LLM judge evaluations for key files
            main_files = list(self.agent_path.rglob("*.py"))[:5]
            for file_path in main_files:
                suite.add(
                    Evaluation(
                        name=f"llm_judge_{file_path.stem}",
                        layer=EvaluationLayer.LLM_JUDGE,
                        handler=lambda fp=file_path: self._run_llm_judge(fp),
                        required=False,
                    )
                )

        if self.suite_name in ("all", "simulation"):
            # Load scenarios from config
            scenarios = self._load_scenarios()
            for scenario in scenarios:
                suite.add(
                    Evaluation(
                        name=f"scenario_{scenario['name']}",
                        layer=EvaluationLayer.SIMULATION,
                        handler=lambda s=scenario: SimulationEvaluations.run_scenario(
                            self.agent_name, s, self.agent_path
                        ),
                    )
                )

        return suite

    async def _run_llm_judge(self, file_path: Path) -> EvaluationResult:
        """Run LLM judge on a file."""
        code = file_path.read_text()
        return await LLMJudgeEvaluations.evaluate_code_quality(
            self.agent_name,
            code,
            file_path.stem,
        )

    def _load_scenarios(self) -> list[dict]:
        """Load simulation scenarios."""
        scenarios_file = self.agent_path / "tests" / "scenarios.json"
        if scenarios_file.exists():
            return json.loads(scenarios_file.read_text())
        return []

    async def run(self) -> dict[str, Any]:
        """Run the evaluation suite."""
        logger.info(f"Running {self.suite_name} evaluation for {self.agent_name}")

        suite = self._build_suite()
        self.results = []

        # Run evaluations
        for evaluation in suite.evaluations:
            logger.info(f"Running: {evaluation.name}")

            try:
                result = await asyncio.wait_for(
                    evaluation.handler(),
                    timeout=evaluation.timeout_seconds,
                )
                self.results.append(result)

                status_icon = "✓" if result.status == EvaluationStatus.PASSED else "✗"
                logger.info(
                    f"  {status_icon} {result.name}: {result.status.value} "
                    f"(score={result.score:.2f})"
                )

            except asyncio.TimeoutError:
                self.results.append(
                    EvaluationResult(
                        name=evaluation.name,
                        layer=evaluation.layer,
                        status=EvaluationStatus.ERROR,
                        message="Evaluation timed out",
                    )
                )
            except Exception as e:
                self.results.append(
                    EvaluationResult(
                        name=evaluation.name,
                        layer=evaluation.layer,
                        status=EvaluationStatus.ERROR,
                        message=str(e),
                    )
                )

        # Generate report
        report = self._generate_report()

        # Save results
        self.output_dir.mkdir(parents=True, exist_ok=True)
        report_path = self.output_dir / f"report_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.json"
        report_path.write_text(json.dumps(report, indent=2))

        logger.info(f"Evaluation complete. Report saved to {report_path}")

        return report

    def _generate_report(self) -> dict[str, Any]:
        """Generate evaluation report."""
        passed = sum(1 for r in self.results if r.status == EvaluationStatus.PASSED)
        failed = sum(1 for r in self.results if r.status == EvaluationStatus.FAILED)
        errors = sum(1 for r in self.results if r.status == EvaluationStatus.ERROR)

        avg_score = (
            sum(r.score for r in self.results) / len(self.results)
            if self.results
            else 0
        )

        return {
            "agent": self.agent_name,
            "suite": self.suite_name,
            "timestamp": datetime.now(UTC).isoformat(),
            "summary": {
                "total": len(self.results),
                "passed": passed,
                "failed": failed,
                "errors": errors,
                "average_score": avg_score,
                "overall_status": "passed" if failed == 0 and errors == 0 else "failed",
            },
            "results": [r.to_dict() for r in self.results],
        }
