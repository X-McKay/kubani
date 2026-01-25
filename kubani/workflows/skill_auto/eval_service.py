"""Evaluation service layer for the Skill Auto workflow.

This module wraps the existing SkillEvaluatorLLM and SkillImprover classes
from the CLI package, providing a protocol-based interface for testing.
"""

import logging
from pathlib import Path
from typing import Any, Protocol

from .models import EvalMetrics

logger = logging.getLogger(__name__)


# =============================================================================
# Protocol Definitions
# =============================================================================


class EvaluatorProtocol(Protocol):
    """Protocol for skill evaluation."""

    def evaluate_skill(self, skill_path: str) -> dict[str, Any]:
        """
        Evaluate a skill and return results.

        Args:
            skill_path: Path to skill directory

        Returns:
            Evaluation results dict with metrics and test_results
        """
        ...


class ImproverProtocol(Protocol):
    """Protocol for skill improvement."""

    def improve_skill(
        self,
        skill_path: str,
        feedback: str,
    ) -> dict[str, Any]:
        """
        Improve a skill based on feedback.

        Args:
            skill_path: Path to skill directory
            feedback: Evaluation feedback to address

        Returns:
            Improvement results dict
        """
        ...


# =============================================================================
# Real Implementations
# =============================================================================


class EvalService:
    """
    Wraps SkillEvaluatorLLM for evaluation.

    This class adapts the existing CLI evaluator to our service interface,
    handling the Path/str conversion and result format differences.
    """

    def __init__(self, llm_client: Any):
        """
        Initialize with an LLM client.

        Args:
            llm_client: LLMClient instance from kubani_dev
        """
        from kubani_dev.skill_evaluator_llm import SkillEvaluatorLLM

        self._evaluator = SkillEvaluatorLLM(llm_client=llm_client)

    def evaluate_skill(self, skill_path: str) -> dict[str, Any]:
        """Evaluate skill and return raw results."""
        return self._evaluator.evaluate_skill(Path(skill_path))


class ImproveService:
    """
    Wraps SkillImprover for skill improvement.

    Note: The current SkillImprover has a different interface than what we need.
    This adapter provides the simpler feedback-based interface.
    """

    def __init__(self, llm_client: Any):
        """
        Initialize with an LLM client.

        Args:
            llm_client: LLMClient instance from kubani_dev
        """
        self._llm = llm_client

    def improve_skill(
        self,
        skill_path: str,
        feedback: str,
    ) -> dict[str, Any]:
        """
        Improve skill based on feedback.

        Uses LLM directly since SkillImprover expects evaluation results format.
        """

        skill_dir = Path(skill_path)
        skill_md = skill_dir / "SKILL.md"

        if not skill_md.exists():
            return {"improved": False, "error": "SKILL.md not found"}

        current_content = skill_md.read_text()

        # Use LLM to generate improvement
        prompt = f"""Improve this skill based on the evaluation feedback.

CURRENT SKILL:
{current_content}

EVALUATION FEEDBACK:
{feedback}

Generate an improved version that addresses the feedback.
Maintain the same YAML frontmatter format and section structure.
Return ONLY the improved SKILL.md content."""

        messages = [
            {"role": "system", "content": "You are an expert at improving AI agent skills."},
            {"role": "user", "content": prompt},
        ]

        response = self._llm.chat(messages, temperature=0.5)
        new_content = response["content"]

        # Clean LLM output (removes <think> tags and code block markers)
        from .llm_service import clean_markdown_output

        new_content = clean_markdown_output(new_content)

        return {
            "improved": True,
            "new_content": new_content,
            "tokens_used": response.get("tokens", {}),
        }


# =============================================================================
# Result Conversion
# =============================================================================


def results_to_metrics(raw_result: dict[str, Any]) -> EvalMetrics:
    """
    Convert SkillEvaluatorLLM output to EvalMetrics.

    The evaluator returns metrics with accuracy as percentage (0-100),
    but EvalMetrics expects it as a fraction (0.0-1.0).

    Args:
        raw_result: Raw evaluation results from SkillEvaluatorLLM

    Returns:
        EvalMetrics instance
    """
    metrics = raw_result.get("metrics", {})
    tokens = metrics.get("total_tokens", {})

    # Convert accuracy from percentage to fraction
    accuracy = metrics.get("accuracy", 0.0)
    if accuracy > 1.0:
        accuracy = accuracy / 100.0

    return EvalMetrics(
        accuracy=accuracy,
        latency_ms=metrics.get("avg_latency_ms", 0.0),
        tests_passed=metrics.get("tests_passed", 0),
        tests_total=metrics.get("tests_total", 0),
        critic_confidence=metrics.get("avg_critic_confidence", 0.0),
        tokens_prompt=tokens.get("prompt", 0),
        tokens_completion=tokens.get("completion", 0),
    )


def extract_failing_tests(raw_result: dict[str, Any]) -> list[dict[str, str]]:
    """
    Extract failing test information from evaluation results.

    Args:
        raw_result: Raw evaluation results from SkillEvaluatorLLM

    Returns:
        List of dicts with test name and failure reason
    """
    failing = []
    test_results = raw_result.get("test_results", [])

    for test in test_results:
        if not test.get("passed", True):
            reason = test.get("error") or "Assertions failed"

            # Include failed assertion details if available
            failed_assertions = [a for a in test.get("assertions", []) if not a.get("passed", True)]
            if failed_assertions:
                details = [
                    f"{a.get('description', 'assertion')}: expected {a.get('expected')}, got {a.get('actual')}"
                    for a in failed_assertions[:2]
                ]
                reason = "; ".join(details)

            failing.append(
                {
                    "name": test.get("name", "unknown"),
                    "reason": reason,
                }
            )

    return failing


def format_evaluation_feedback(raw_result: dict[str, Any]) -> str:
    """
    Format evaluation results into feedback string for improvement.

    Args:
        raw_result: Raw evaluation results from SkillEvaluatorLLM

    Returns:
        Formatted feedback string
    """
    metrics = results_to_metrics(raw_result)
    failing = extract_failing_tests(raw_result)

    lines = [
        f"Accuracy: {metrics.accuracy:.1%}",
        f"Tests passed: {metrics.tests_passed}/{metrics.tests_total}",
        f"Average latency: {metrics.latency_ms:.0f}ms",
    ]

    if failing:
        lines.append("\nFailing tests:")
        for test in failing:
            lines.append(f"  - {test['name']}: {test['reason']}")

    # Include critic feedback if available
    test_results = raw_result.get("test_results", [])
    critic_feedback = []
    for test in test_results:
        critic = test.get("critic")
        if critic and not critic.get("success", True):
            critique = critic.get("critique", "")
            if critique:
                critic_feedback.append(f"  - {test.get('name', 'test')}: {critique[:100]}")

    if critic_feedback:
        lines.append("\nCritic feedback:")
        lines.extend(critic_feedback[:3])  # Limit to 3

    return "\n".join(lines)
