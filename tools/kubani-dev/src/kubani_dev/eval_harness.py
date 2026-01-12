"""
Evaluation Harness for Kubani Agents.

Executes evaluation suites against agents and records results:
- Runs tasks with environment setup/teardown
- Executes multiple trials for statistical significance
- Applies code and model-based graders
- Persists results to registry for tracking
- Supports CI/CD integration

Based on Anthropic's agent evaluation best practices.
"""

import asyncio
import json
import logging
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import httpx

from kubani_dev.eval_suite import (
    EvalSuite,
    EvalSuiteLoader,
    EvalTask,
    Grader,
    GraderType,
    SuiteResult,
    TaskResult,
    TaskStatus,
    TrialResult,
)

logger = logging.getLogger(__name__)


@dataclass
class HarnessConfig:
    """Configuration for the evaluation harness."""

    project_root: Path
    evals_dir: Path
    output_dir: Path
    registry_url: str = "http://localhost:8000"
    llm_api_url: str = "http://localhost:8000/v1"
    llm_model: str = "Qwen/Qwen3-14B"
    parallel_trials: int = 1
    save_transcripts: bool = True
    post_to_registry: bool = True


class CodeGrader:
    """Executes code-based graders (assertions)."""

    def __init__(self):
        pass

    def evaluate(
        self,
        grader: Grader,
        outcome: dict[str, Any],
        transcript: list[dict[str, Any]],
    ) -> tuple[bool, float, str]:
        """
        Evaluate using a code assertion.

        Returns: (passed, score, message)
        """
        if not grader.assertion:
            return True, 1.0, "No assertion defined"

        try:
            # Create evaluation context
            context = {
                "outcome": type("Outcome", (), outcome)(),
                "transcript": transcript,
                "len": len,
                "str": str,
                "any": any,
                "all": all,
            }

            # Evaluate the assertion
            result = eval(grader.assertion, {"__builtins__": {}}, context)

            if result:
                return True, 1.0, "Assertion passed"
            else:
                return False, 0.0, f"Assertion failed: {grader.assertion}"

        except Exception as e:
            return False, 0.0, f"Assertion error: {e}"


class ModelGrader:
    """Executes model-based graders (LLM-as-judge)."""

    JUDGE_PROMPT = """You are an expert evaluator assessing an AI agent's performance.

Task: {task_name}
Prompt given to agent: {prompt}

Agent's response/outcome:
{outcome}

Evaluation rubric:
{rubric}

{criteria_section}

Provide your evaluation as JSON:
{{
    "score": <number 0-10>,
    "passed": <true if score >= 7>,
    "reasoning": "<detailed explanation>",
    "strengths": ["<strength 1>", ...],
    "weaknesses": ["<weakness 1>", ...]
}}

Respond ONLY with valid JSON."""

    def __init__(self, api_url: str, model: str):
        self.api_url = api_url
        self.model = model

    async def evaluate(
        self,
        grader: Grader,
        task: EvalTask,
        outcome: dict[str, Any],
        transcript: list[dict[str, Any]],
    ) -> tuple[bool, float, str]:
        """
        Evaluate using LLM-as-judge.

        Returns: (passed, score, message)
        """
        criteria_section = ""
        if grader.criteria:
            criteria_section = "Specific criteria to check:\n" + "\n".join(
                f"- {c}" for c in grader.criteria
            )

        prompt = self.JUDGE_PROMPT.format(
            task_name=task.name,
            prompt=task.prompt,
            outcome=json.dumps(outcome, indent=2),
            rubric=grader.rubric,
            criteria_section=criteria_section,
        )

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}/chat/completions",
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.1,
                        "max_tokens": 1024,
                    },
                    timeout=60.0,
                )

                if response.status_code != 200:
                    return False, 0.0, f"LLM API error: {response.status_code}"

                data = response.json()
                content = data["choices"][0]["message"]["content"]

                # Parse JSON response
                json_start = content.find("{")
                json_end = content.rfind("}") + 1
                if json_start >= 0 and json_end > json_start:
                    result = json.loads(content[json_start:json_end])
                    score = result.get("score", 0) / 10.0
                    passed = result.get("passed", score >= 0.7)
                    reasoning = result.get("reasoning", "")
                    return passed, score, reasoning

                return False, 0.0, "Failed to parse LLM response"

        except Exception as e:
            logger.error(f"Model grader error: {e}")
            return False, 0.0, f"Model grader error: {e}"


class EnvironmentManager:
    """Manages test environment setup and teardown."""

    def __init__(self, project_root: Path):
        self.project_root = project_root

    async def setup(self, task: EvalTask) -> bool:
        """Set up the test environment."""
        env = task.environment

        # Write fixture files
        for filename, content in env.fixtures.items():
            fixture_path = self.project_root / "eval-fixtures" / filename
            fixture_path.parent.mkdir(parents=True, exist_ok=True)
            fixture_path.write_text(content)

        # Run setup commands
        for cmd in env.setup_commands:
            try:
                # Replace fixture references
                cmd = cmd.replace("fixtures/", str(self.project_root / "eval-fixtures") + "/")
                result = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=env.timeout_seconds,
                )
                if result.returncode != 0:
                    logger.warning(f"Setup command failed: {cmd}\n{result.stderr}")
            except subprocess.TimeoutExpired:
                logger.warning(f"Setup command timed out: {cmd}")
            except Exception as e:
                logger.warning(f"Setup error: {e}")

        return True

    async def teardown(self, task: EvalTask) -> None:
        """Tear down the test environment."""
        env = task.environment

        for cmd in env.teardown_commands:
            try:
                subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            except Exception as e:
                logger.warning(f"Teardown error: {e}")


class AgentExecutor:
    """Executes agent tasks and captures results."""

    def __init__(self, agent_name: str, project_root: Path):
        self.agent_name = agent_name
        self.project_root = project_root

    async def execute(
        self,
        task: EvalTask,
        trial_number: int,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, int]]:
        """
        Execute a task against the agent.

        Returns: (outcome, transcript, token_usage)
        """
        # This is a placeholder - in practice, this would:
        # 1. Start the agent or connect to a running instance
        # 2. Send the task prompt
        # 3. Capture the agent's tool calls and responses
        # 4. Return the final outcome

        # For now, return mock data for testing the harness
        logger.info(f"Executing task '{task.name}' trial {trial_number}")

        # Simulate agent execution
        await asyncio.sleep(1)

        outcome = {
            "diagnosis": "Pod is in CrashLoopBackOff state due to exit code 1",
            "remediation": "Fix the container command or increase memory limits",
            "tools_used": task.expected_tools,
        }

        transcript = [
            {"role": "user", "content": task.prompt},
            {"role": "assistant", "content": "Let me investigate...", "tool_calls": []},
        ]

        token_usage = {"prompt_tokens": 500, "completion_tokens": 200}

        return outcome, transcript, token_usage


class EvalHarness:
    """Main evaluation harness that orchestrates suite execution."""

    def __init__(self, config: HarnessConfig):
        self.config = config
        self.loader = EvalSuiteLoader(config.evals_dir)
        self.code_grader = CodeGrader()
        self.model_grader = ModelGrader(config.llm_api_url, config.llm_model)
        self.env_manager = EnvironmentManager(config.project_root)

    async def run_suite(self, suite: EvalSuite) -> SuiteResult:
        """Run an evaluation suite and return results."""
        logger.info(f"Running evaluation suite: {suite.name}")

        result = SuiteResult(suite=suite)
        result.started_at = datetime.now(UTC)

        for task in suite.tasks:
            task_result = await self.run_task(task, suite.agent)
            result.task_results.append(task_result)

        result.completed_at = datetime.now(UTC)
        result.compute_metrics()

        # Save results
        output_path = (
            self.config.output_dir
            / suite.agent
            / f"{suite.name}_{result.started_at.strftime('%Y%m%d_%H%M%S')}.json"
        )
        result.save(output_path)
        logger.info(f"Results saved to {output_path}")

        # Post to registry if enabled
        if self.config.post_to_registry:
            await self.post_results_to_registry(result)

        return result

    async def run_task(self, task: EvalTask, agent_name: str) -> TaskResult:
        """Run a single task with multiple trials."""
        logger.info(f"Running task: {task.name} ({task.trials} trials)")

        task_result = TaskResult(task=task)
        executor = AgentExecutor(agent_name, self.config.project_root)

        for trial_num in range(1, task.trials + 1):
            trial_result = await self.run_trial(task, executor, trial_num)
            task_result.trials.append(trial_result)

        task_result.compute_metrics()
        return task_result

    async def run_trial(
        self,
        task: EvalTask,
        executor: AgentExecutor,
        trial_number: int,
    ) -> TrialResult:
        """Run a single trial of a task."""
        trial = TrialResult(trial_number=trial_number)
        start_time = time.time()

        try:
            # Setup environment
            await self.env_manager.setup(task)

            # Execute the task
            outcome, transcript, token_usage = await executor.execute(task, trial_number)

            trial.outcome = outcome
            trial.transcript = transcript
            trial.token_usage = token_usage

            # Run graders
            grader_results = {}
            all_passed = True
            total_score = 0.0
            total_weight = 0.0

            for grader in task.graders:
                if grader.type == GraderType.CODE:
                    passed, score, message = self.code_grader.evaluate(
                        grader, outcome, transcript
                    )
                elif grader.type == GraderType.MODEL:
                    passed, score, message = await self.model_grader.evaluate(
                        grader, task, outcome, transcript
                    )
                else:
                    # Human graders are skipped in automated runs
                    passed, score, message = True, 1.0, "Human review required"

                grader_name = grader.name or f"{grader.type.value}_grader"
                grader_results[grader_name] = {
                    "passed": passed,
                    "score": score,
                    "message": message,
                }

                if grader.required and not passed:
                    all_passed = False

                total_score += score * grader.weight
                total_weight += grader.weight

            trial.grader_results = grader_results
            trial.score = total_score / total_weight if total_weight > 0 else 0.0
            trial.status = TaskStatus.PASSED if all_passed else TaskStatus.FAILED

        except asyncio.TimeoutError:
            trial.status = TaskStatus.ERROR
            trial.error = "Task timed out"
        except Exception as e:
            trial.status = TaskStatus.ERROR
            trial.error = str(e)
            logger.error(f"Trial error: {e}")
        finally:
            # Teardown environment
            await self.env_manager.teardown(task)
            trial.duration_seconds = time.time() - start_time

        return trial

    async def post_results_to_registry(self, result: SuiteResult) -> None:
        """Post evaluation results to the registry."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.config.registry_url}/api/v1/evaluations",
                    json=result.to_dict(),
                    timeout=30.0,
                )
                if response.status_code in (200, 201):
                    logger.info("Results posted to registry")
                else:
                    logger.warning(f"Failed to post results: {response.status_code}")
        except Exception as e:
            logger.warning(f"Failed to post results to registry: {e}")

    async def run_all(self, agent: str | None = None) -> list[SuiteResult]:
        """Run all evaluation suites for an agent."""
        suites = self.loader.load_all(agent)
        results = []

        for suite in suites:
            result = await self.run_suite(suite)
            results.append(result)

        return results


def print_results(result: SuiteResult) -> None:
    """Print evaluation results to console."""
    print(f"\n{'='*60}")
    print(f"Evaluation Suite: {result.suite.name}")
    print(f"{'='*60}")
    print(f"Overall Pass Rate: {result.overall_pass_rate:.1%}")
    print(f"Overall Score: {result.overall_score:.2f}")
    print(f"Total Duration: {result.total_duration:.1f}s")
    print()

    for task_result in result.task_results:
        status_icon = "✓" if task_result.pass_at_k > 0 else "✗"
        print(f"{status_icon} {task_result.task.name}")
        print(f"  Pass@k: {task_result.pass_at_k:.1%} | Score: {task_result.mean_score:.2f} ± {task_result.std_score:.2f}")

        for trial in task_result.trials:
            trial_icon = "✓" if trial.status == TaskStatus.PASSED else "✗"
            print(f"    Trial {trial.trial_number}: {trial_icon} ({trial.score:.2f})")

    print(f"\n{'='*60}\n")
