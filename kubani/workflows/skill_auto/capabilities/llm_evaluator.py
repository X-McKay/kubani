"""LLM-based skill evaluator using Strands sub-agent pattern.

This module provides skill evaluation by creating isolated Strands sub-agents
that execute SKILL.md prompts against test cases. Each test case is run by
a fresh sub-agent with the skill's SOP as its system prompt.

The Strands sub-agent pattern provides:
- Isolated context per skill execution
- Native streaming support
- Consistent architecture with rest of Kubani

Usage:
    from kubani.workflows.skill_auto.capabilities.llm_evaluator import SkillEvaluator
    from kubani.workflows.skill_auto.eval_config import get_quick_configuration

    evaluator = SkillEvaluator()
    config = get_quick_configuration()
    results = await evaluator.evaluate_skill(skill_dir, config)
"""

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from strands import Agent
from strands.models.openai import OpenAIModel

from kubani.workflows.skill_auto.eval_config import EvalConfiguration

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class AssertionResult:
    """Result of a single assertion check."""

    type: str
    passed: bool
    message: str
    expected: Any = None
    actual: Any = None


@dataclass
class TestResult:
    """Result of a single test case execution."""

    name: str
    passed: bool
    latency_ms: float
    assertions_passed: list[AssertionResult] = field(default_factory=list)
    assertions_failed: list[AssertionResult] = field(default_factory=list)
    output: dict = field(default_factory=dict)
    error: str | None = None
    critic_evaluation: dict | None = None


@dataclass
class EvaluationResult:
    """Complete evaluation result for a skill."""

    skill_name: str
    config_name: str
    accuracy: float
    tests_passed: int
    tests_total: int
    avg_latency_ms: float
    total_duration_ms: float
    test_results: list[TestResult] = field(default_factory=list)
    tokens: dict = field(default_factory=lambda: {"prompt": 0, "completion": 0, "total": 0})
    error: str | None = None


# =============================================================================
# Assertion Checking
# =============================================================================


def check_assertions(output: dict, assertions: list[dict]) -> list[AssertionResult]:
    """
    Check all assertions against the output.

    Supports assertion types:
    - exists: Check if a key exists in output
    - type: Check if a value has the expected type
    - equals: Check if a value equals the expected value
    - contains: Check if a value contains the expected substring
    - range: Check if a number is within a range

    Args:
        output: The actual output from skill execution
        assertions: List of assertion definitions from test case

    Returns:
        List of AssertionResult objects
    """
    results = []

    for assertion in assertions:
        assertion_type = assertion.get("type", "exists")
        key = assertion.get("key", "")
        expected = assertion.get("expected")
        description = assertion.get("description", f"{assertion_type} check on {key}")

        # Get nested value from output using dot notation
        actual = _get_nested_value(output, key)

        result = _check_single_assertion(assertion_type, actual, expected, key)
        result_obj = AssertionResult(
            type=assertion_type,
            passed=result["passed"],
            message=result.get("message", description),
            expected=expected,
            actual=actual,
        )
        results.append(result_obj)

    return results


def _get_nested_value(data: dict, key: str) -> Any:
    """
    Get a nested value from a dictionary using dot notation.

    Args:
        data: Dictionary to search
        key: Dot-separated key path (e.g., "result.items.0")

    Returns:
        The value at the path, or None if not found
    """
    if not key:
        return data

    parts = key.split(".")
    value = data

    for part in parts:
        if value is None:
            return None

        if isinstance(value, dict):
            value = value.get(part)
        elif isinstance(value, list):
            try:
                index = int(part)
                value = value[index] if 0 <= index < len(value) else None
            except ValueError:
                return None
        else:
            return None

    return value


def _check_single_assertion(
    assertion_type: str, actual: Any, expected: Any, key: str
) -> dict[str, Any]:
    """
    Check a single assertion.

    Args:
        assertion_type: Type of assertion to check
        actual: Actual value from output
        expected: Expected value from assertion
        key: The key being checked (for error messages)

    Returns:
        Dict with 'passed' bool and optional 'message'
    """
    if assertion_type == "exists":
        if actual is not None:
            return {"passed": True}
        return {"passed": False, "message": f"Key '{key}' does not exist in output"}

    elif assertion_type == "type":
        type_map = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "float": float,
            "boolean": bool,
            "array": list,
            "object": dict,
            "null": type(None),
        }
        expected_type = type_map.get(expected, str)

        if isinstance(actual, expected_type):
            return {"passed": True}
        return {
            "passed": False,
            "message": f"Expected type '{expected}', got '{type(actual).__name__}'",
        }

    elif assertion_type == "equals":
        if actual == expected:
            return {"passed": True}
        return {
            "passed": False,
            "message": f"Expected '{expected}', got '{actual}'",
        }

    elif assertion_type == "contains":
        if expected is None:
            return {"passed": False, "message": "No expected value for contains check"}

        if isinstance(actual, str) and isinstance(expected, str):
            if expected in actual:
                return {"passed": True}
            return {
                "passed": False,
                "message": f"String does not contain '{expected}'",
            }
        elif isinstance(actual, list):
            if expected in actual:
                return {"passed": True}
            return {
                "passed": False,
                "message": f"List does not contain '{expected}'",
            }
        return {
            "passed": False,
            "message": f"Cannot check 'contains' on type {type(actual).__name__}",
        }

    elif assertion_type == "range":
        if not isinstance(expected, dict):
            return {"passed": False, "message": "Range assertion requires min/max dict"}

        if actual is None or not isinstance(actual, (int, float)):
            return {"passed": False, "message": f"Value '{actual}' is not a number"}

        min_val = expected.get("min", float("-inf"))
        max_val = expected.get("max", float("inf"))

        if min_val <= actual <= max_val:
            return {"passed": True}
        return {
            "passed": False,
            "message": f"Value {actual} not in range [{min_val}, {max_val}]",
        }

    else:
        return {"passed": False, "message": f"Unknown assertion type: {assertion_type}"}


# =============================================================================
# Skill Evaluator
# =============================================================================


class SkillEvaluator:
    """
    Evaluate skills using Strands sub-agents.

    Each test case is executed by a fresh Strands Agent with the skill's
    SKILL.md content as the system prompt. This provides isolation and
    consistent behavior across evaluations.
    """

    def __init__(self, enable_critic: bool = True):
        """
        Initialize the evaluator.

        Args:
            enable_critic: Whether to use LLM critic for semantic verification
        """
        self.enable_critic = enable_critic

    async def evaluate_skill(
        self,
        skill_dir: Path,
        config: EvalConfiguration,
    ) -> EvaluationResult:
        """
        Evaluate a skill against all its test cases.

        Args:
            skill_dir: Path to the skill directory containing SKILL.md and test_cases.yaml
            config: Evaluation configuration (model, endpoint, etc.)

        Returns:
            EvaluationResult with all metrics and test results

        Raises:
            FileNotFoundError: If skill files don't exist
            ValueError: If skill files are invalid
        """
        start_time = time.time()
        skill_name = skill_dir.name

        logger.info(f"Evaluating skill '{skill_name}' with config '{config.name}'")

        # Load skill content and test cases
        try:
            skill_sop = self._load_skill_sop(skill_dir)
            test_cases = self._load_test_cases(skill_dir)
        except Exception as e:
            logger.error(f"Failed to load skill files: {e}")
            return EvaluationResult(
                skill_name=skill_name,
                config_name=config.name,
                accuracy=0.0,
                tests_passed=0,
                tests_total=0,
                avg_latency_ms=0.0,
                total_duration_ms=0.0,
                error=str(e),
            )

        # Run each test case
        test_results: list[TestResult] = []
        total_latency = 0.0
        total_tokens = {"prompt": 0, "completion": 0, "total": 0}

        for test_case in test_cases:
            result = await self._run_test_case(skill_sop, test_case, config)
            test_results.append(result)
            total_latency += result.latency_ms

        # Calculate metrics
        tests_passed = sum(1 for r in test_results if r.passed)
        tests_total = len(test_results)
        accuracy = tests_passed / tests_total if tests_total > 0 else 0.0
        avg_latency = total_latency / tests_total if tests_total > 0 else 0.0
        total_duration = (time.time() - start_time) * 1000

        logger.info(
            f"Evaluation complete: {tests_passed}/{tests_total} passed, "
            f"accuracy={accuracy:.1%}, avg_latency={avg_latency:.0f}ms"
        )

        return EvaluationResult(
            skill_name=skill_name,
            config_name=config.name,
            accuracy=accuracy,
            tests_passed=tests_passed,
            tests_total=tests_total,
            avg_latency_ms=avg_latency,
            total_duration_ms=total_duration,
            test_results=test_results,
            tokens=total_tokens,
        )

    def _load_skill_sop(self, skill_dir: Path) -> str:
        """Load SKILL.md content from skill directory."""
        skill_path = skill_dir / "SKILL.md"
        if not skill_path.exists():
            raise FileNotFoundError(f"SKILL.md not found in {skill_dir}")
        return skill_path.read_text()

    def _load_test_cases(self, skill_dir: Path) -> list[dict]:
        """Load test cases from test_cases.yaml."""
        test_path = skill_dir / "test_cases.yaml"
        if not test_path.exists():
            raise FileNotFoundError(f"test_cases.yaml not found in {skill_dir}")

        with open(test_path) as f:
            data = yaml.safe_load(f)

        test_cases = data.get("test_cases", [])
        if not test_cases:
            raise ValueError("No test cases found in test_cases.yaml")

        return test_cases

    async def _run_test_case(
        self,
        skill_sop: str,
        test_case: dict,
        config: EvalConfiguration,
    ) -> TestResult:
        """
        Run a single test case using a Strands sub-agent.

        Creates an isolated agent with the skill SOP as system prompt,
        executes the test input, and validates the output.

        Args:
            skill_sop: The SKILL.md content
            test_case: Test case definition with inputs, expected_output, assertions
            config: Evaluation configuration

        Returns:
            TestResult with execution details
        """
        test_name = test_case.get("name", "unnamed")
        inputs = test_case.get("inputs", {})
        expected_output = test_case.get("expected_output", {})
        assertions = test_case.get("assertions", [])

        logger.debug(f"Running test case: {test_name}")
        start_time = time.time()

        try:
            # Build system prompt with execution instructions
            system_prompt = self._build_execution_prompt(skill_sop)

            # Create isolated sub-agent for this test case
            model = OpenAIModel(
                client_args={
                    "api_key": "not-needed",  # vLLM doesn't require API key
                    "base_url": config.base_url,
                },
                model_id=config.model,
            )

            agent = Agent(
                model=model,
                system_prompt=system_prompt,
            )

            # Execute with test inputs
            user_prompt = f"Execute the skill with these inputs:\n\n{json.dumps(inputs, indent=2)}\n\nReturn the result as JSON."
            result = await agent.invoke_async(user_prompt)

            latency_ms = (time.time() - start_time) * 1000

            # Parse the output
            output = self._parse_agent_output(result)

            # Run assertions
            assertion_results = check_assertions(output, assertions)
            assertions_passed = [a for a in assertion_results if a.passed]
            assertions_failed = [a for a in assertion_results if not a.passed]

            # Determine if test passed (all assertions pass)
            test_passed = len(assertions_failed) == 0

            # Optionally run critic evaluation
            critic_eval = None
            if self.enable_critic and not test_passed:
                critic_eval = await self._run_critic_evaluation(
                    skill_sop, test_case, output, assertion_results, config
                )
                # Critic can override test_passed for semantic correctness
                if critic_eval and critic_eval.get("success"):
                    test_passed = True
                    logger.info(f"Test '{test_name}' passed by critic override")

            return TestResult(
                name=test_name,
                passed=test_passed,
                latency_ms=latency_ms,
                assertions_passed=[
                    AssertionResult(
                        type=a.type,
                        passed=True,
                        message=a.message,
                        expected=a.expected,
                        actual=a.actual,
                    )
                    for a in assertions_passed
                ],
                assertions_failed=[
                    AssertionResult(
                        type=a.type,
                        passed=False,
                        message=a.message,
                        expected=a.expected,
                        actual=a.actual,
                    )
                    for a in assertions_failed
                ],
                output=output,
                critic_evaluation=critic_eval,
            )

        except Exception as e:
            logger.error(f"Test case '{test_name}' failed with error: {e}")
            latency_ms = (time.time() - start_time) * 1000
            return TestResult(
                name=test_name,
                passed=False,
                latency_ms=latency_ms,
                error=str(e),
            )

    def _build_execution_prompt(self, skill_sop: str) -> str:
        """Build the system prompt for skill execution."""
        return f"""You are an AI agent executing a skill. Follow the instructions in the skill SOP exactly.

SKILL SOP:
{skill_sop}

CRITICAL INSTRUCTIONS:
1. Read the "Output Format" section carefully
2. Return ONLY a JSON object with the EXACT field names specified
3. Do NOT add wrapper fields like "output", "result", or "response"
4. Do NOT add explanatory text before or after the JSON
5. The JSON must be parseable and match the schema exactly

Example: If the SOP says return {{"sum": number}}, return {{"sum": 8}}, NOT {{"output": {{"sum": 8}}}}"""

    def _parse_agent_output(self, result: Any) -> dict:
        """
        Parse the Strands Agent output into a dictionary.

        Handles various response formats from Strands agents.
        """
        import re

        # Extract text content from result
        if hasattr(result, "message"):
            message = result.message
            if isinstance(message, dict):
                content = message.get("content", [])
                if isinstance(content, list) and content:
                    text_block = content[0]
                    if isinstance(text_block, dict):
                        text = text_block.get("text", str(message))
                    else:
                        text = str(text_block)
                else:
                    text = str(content)
            else:
                text = str(message)
        else:
            text = str(result)

        # Strip thinking tags
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        text = re.sub(r"<reasoning>.*?</reasoning>", "", text, flags=re.DOTALL)
        text = re.sub(r"<thought>.*?</thought>", "", text, flags=re.DOTALL)
        text = text.strip()

        # Extract JSON from markdown code blocks
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # If not valid JSON, wrap in result dict
            return {"result": text}

    async def _run_critic_evaluation(
        self,
        skill_sop: str,
        test_case: dict,
        actual_output: dict,
        assertion_results: list[AssertionResult],
        config: EvalConfiguration,
    ) -> dict | None:
        """
        Run LLM critic evaluation for semantic verification.

        This goes beyond assertion checking to understand if the skill
        truly achieved its goal. Inspired by Voyager's self-verification.

        Args:
            skill_sop: The skill's SOP content
            test_case: The test case definition
            actual_output: The actual output from execution
            assertion_results: Results from assertion checking
            config: Evaluation configuration

        Returns:
            Dict with 'success', 'confidence', 'critique', 'suggestions'
            or None if critic evaluation fails
        """
        try:
            # Build assertion summary
            passed = sum(1 for a in assertion_results if a.passed)
            total = len(assertion_results)
            assertion_summary = []
            for i, assertion in enumerate(assertion_results, 1):
                status = "PASSED" if assertion.passed else "FAILED"
                assertion_summary.append(f"{i}. {assertion.type}: {status}")
                if not assertion.passed:
                    assertion_summary.append(f"   Reason: {assertion.message}")

            system_prompt = """You are an expert evaluator for AI agent skills. Your job is to determine if a skill execution truly achieved its intended goal.

You will be given:
1. What the skill is supposed to do
2. What this test case is testing
3. The inputs provided
4. The expected output
5. The actual output
6. Results from automated assertion checks

Your task is to provide a semantic evaluation that goes beyond simple assertion checking. Consider:
- Did the skill achieve its core objective?
- Are there subtle failures the assertions might have missed?
- Is the output semantically correct even if format differs slightly?

Respond with a JSON object:
{
    "success": true/false,
    "confidence": 0.0-1.0,
    "critique": "Detailed analysis of what happened",
    "suggestions": "Specific suggestions for improvement (if failed)"
}"""

            user_prompt = f"""Evaluate this skill execution:

**Skill SOP:**
{skill_sop[:2000]}...

**Test Case:**
{test_case.get("name", "unknown")}: {test_case.get("description", "No description")}

**Inputs:**
{json.dumps(test_case.get("inputs", {}), indent=2)}

**Expected Output:**
{json.dumps(test_case.get("expected_output", {}), indent=2)}

**Actual Output:**
{json.dumps(actual_output, indent=2)}

**Assertion Results ({passed}/{total} passed):**
{chr(10).join(assertion_summary) if assertion_summary else "No assertions defined"}

Provide your evaluation as JSON."""

            # Create critic sub-agent
            model = OpenAIModel(
                client_args={
                    "api_key": "not-needed",
                    "base_url": config.base_url,
                },
                model_id=config.model,
            )

            critic_agent = Agent(
                model=model,
                system_prompt=system_prompt,
            )

            result = await critic_agent.invoke_async(user_prompt)
            critic_output = self._parse_agent_output(result)

            # Validate required fields
            if all(k in critic_output for k in ["success", "confidence", "critique"]):
                if "suggestions" not in critic_output:
                    critic_output["suggestions"] = ""
                return critic_output

            logger.warning("Critic response missing required fields")
            return None

        except Exception as e:
            logger.error(f"Critic evaluation failed: {e}")
            return None


# =============================================================================
# Convenience Functions
# =============================================================================


async def evaluate_skill_with_config(
    skill_dir: Path | str,
    config: EvalConfiguration,
    enable_critic: bool = True,
) -> EvaluationResult:
    """
    Convenience function to evaluate a skill with a configuration.

    Args:
        skill_dir: Path to the skill directory
        config: Evaluation configuration
        enable_critic: Whether to enable critic evaluation

    Returns:
        EvaluationResult with metrics and test results
    """
    if isinstance(skill_dir, str):
        skill_dir = Path(skill_dir)

    evaluator = SkillEvaluator(enable_critic=enable_critic)
    return await evaluator.evaluate_skill(skill_dir, config)


__all__ = [
    "AssertionResult",
    "TestResult",
    "EvaluationResult",
    "SkillEvaluator",
    "check_assertions",
    "evaluate_skill_with_config",
]
