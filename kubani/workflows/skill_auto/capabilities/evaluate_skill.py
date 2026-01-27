"""Evaluate a skill against its test cases.

This module provides functions for:
- Running skill evaluation and returning metrics
- Converting raw evaluation results to EvalMetrics
- Extracting failing test information
- Formatting evaluation feedback for improvement prompts
"""

from pathlib import Path
from typing import Any

from ..models import EvalMetrics

# =============================================================================
# Evaluation Functions
# =============================================================================


def evaluate_skill(
    skill_path: str,
    sandbox_type: str = "auto",
) -> tuple[EvalMetrics, str]:
    """
    Evaluate a skill and return metrics and formatted feedback.

    Uses the sandbox-based SkillEvaluator to run test cases against
    the skill in an isolated environment.

    Args:
        skill_path: Path to the skill directory containing SKILL.md and test_cases.yaml
        sandbox_type: Sandbox backend to use (auto, microsandbox, docker)

    Returns:
        Tuple of (EvalMetrics, formatted_feedback_string)

    Raises:
        FileNotFoundError: If skill path doesn't exist
        ValueError: If skill is invalid or no test cases found
    """
    from kubani_dev.sandbox.evaluator import SkillEvaluator

    evaluator = SkillEvaluator(Path(skill_path), sandbox_type=sandbox_type)
    raw_result = evaluator.evaluate()

    metrics = results_to_metrics(raw_result)
    feedback = format_evaluation_feedback(raw_result)

    return metrics, feedback


# =============================================================================
# Result Conversion
# =============================================================================


def results_to_metrics(raw_result: dict[str, Any]) -> EvalMetrics:
    """
    Convert SkillEvaluator output to EvalMetrics.

    The sandbox evaluator returns accuracy as a fraction (0.0-1.0).

    Args:
        raw_result: Raw evaluation results from SkillEvaluator

    Returns:
        EvalMetrics instance with normalized values
    """
    # Sandbox evaluator puts metrics at top level
    accuracy = raw_result.get("accuracy", 0.0)

    # Convert accuracy from percentage to fraction if needed
    if accuracy > 1.0:
        accuracy = accuracy / 100.0

    return EvalMetrics(
        accuracy=accuracy,
        latency_ms=raw_result.get("avg_latency_ms", 0.0),
        tests_passed=raw_result.get("tests_passed", 0),
        tests_total=raw_result.get("tests_total", 0),
        # Sandbox evaluator doesn't have critic confidence or token counts
        critic_confidence=0.0,
        tokens_prompt=0,
        tokens_completion=0,
    )


def extract_failing_tests(raw_result: dict[str, Any]) -> list[dict[str, str]]:
    """
    Extract failing test information from evaluation results.

    Args:
        raw_result: Raw evaluation results from SkillEvaluator

    Returns:
        List of dicts with 'name' and 'reason' keys for each failing test
    """
    failing = []
    test_results = raw_result.get("test_results", [])

    for test in test_results:
        if not test.get("passed", True):
            reason = test.get("error") or "Assertions failed"

            # Sandbox evaluator uses assertions_failed list directly
            failed_assertions = test.get("assertions_failed", [])
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

    Args:
        raw_result: Raw evaluation results from SkillEvaluator

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

    return "\n".join(lines)


__all__ = [
    "evaluate_skill",
    "results_to_metrics",
    "extract_failing_tests",
    "format_evaluation_feedback",
]
