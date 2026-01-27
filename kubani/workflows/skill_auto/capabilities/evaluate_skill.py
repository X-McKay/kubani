"""Evaluate a skill against its test cases.

This module provides functions for:
- Running skill evaluation and returning metrics
- Converting raw evaluation results to EvalMetrics
- Extracting failing test information
- Formatting evaluation feedback for improvement prompts
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..models import EvalMetrics

if TYPE_CHECKING:
    from ..protocols import LLMClient


# =============================================================================
# Evaluation Functions
# =============================================================================


def evaluate_skill(
    skill_path: str,
    llm_client: "LLMClient",
) -> tuple[EvalMetrics, str]:
    """
    Evaluate a skill and return metrics and formatted feedback.

    This function wraps the SkillEvaluatorLLM from kubani_dev to provide
    a clean interface for the capability layer.

    Args:
        skill_path: Path to the skill directory containing SKILL.md and test_cases.yaml
        llm_client: LLM client for running evaluations

    Returns:
        Tuple of (EvalMetrics, formatted_feedback_string)

    Raises:
        FileNotFoundError: If skill path doesn't exist
        ValueError: If skill is invalid
    """
    from kubani_dev.skill_evaluator_llm import SkillEvaluatorLLM

    evaluator = SkillEvaluatorLLM(llm_client=llm_client)
    raw_result = evaluator.evaluate_skill(Path(skill_path))

    metrics = results_to_metrics(raw_result)
    feedback = format_evaluation_feedback(raw_result)

    return metrics, feedback


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
        EvalMetrics instance with normalized values
    """
    metrics = raw_result.get("metrics", {})
    tokens = metrics.get("total_tokens", {})

    # Convert accuracy from percentage to fraction if needed
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
        List of dicts with 'name' and 'reason' keys for each failing test
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
                    for a in failed_assertions[:2]  # Limit to first 2
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

    Creates a human-readable summary including:
    - Accuracy, tests passed, latency
    - List of failing tests with reasons
    - Critic feedback (if available)

    Args:
        raw_result: Raw evaluation results from SkillEvaluatorLLM

    Returns:
        Formatted feedback string suitable for LLM improvement prompts
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


__all__ = [
    "evaluate_skill",
    "results_to_metrics",
    "extract_failing_tests",
    "format_evaluation_feedback",
]
