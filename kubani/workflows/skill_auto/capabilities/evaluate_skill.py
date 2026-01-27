"""Evaluate a skill against its test cases using LLM-based evaluation.

This module provides functions for:
- Running skill evaluation using Strands sub-agent pattern
- Supporting quick (single config) and full (4-config matrix) modes
- Converting raw evaluation results to EvalMetrics
- Extracting failing test information
- Formatting evaluation feedback for improvement prompts
"""

import asyncio
from pathlib import Path
from typing import Any

from ..eval_config import (
    ComparisonReport,
    ConfigurationResult,
)
from ..models import EvalMetrics
from .eval_orchestrator import EvalOrchestrator
from .eval_reporter import EvalReporter

# =============================================================================
# Evaluation Functions
# =============================================================================


async def evaluate_skill(
    skill_path: str,
    mode: str = "quick",
    parallel: bool = True,
    enable_critic: bool = True,
) -> tuple[EvalMetrics, str]:
    """
    Evaluate a skill and return metrics and formatted feedback.

    Uses LLM-based evaluation with Strands sub-agent pattern to execute
    SKILL.md prompts against test cases.

    Args:
        skill_path: Path to the skill directory containing SKILL.md and test_cases.yaml
        mode: Evaluation mode - "quick" (single config) or "full" (4-config matrix)
        parallel: Whether to run full mode configurations in parallel
        enable_critic: Whether to enable critic evaluation for semantic verification

    Returns:
        Tuple of (EvalMetrics, formatted_feedback_string)

    Raises:
        FileNotFoundError: If skill path doesn't exist
        ValueError: If skill is invalid or no test cases found
    """
    orchestrator = EvalOrchestrator(enable_critic=enable_critic)
    reporter = EvalReporter()

    skill_path_obj = Path(skill_path)

    if mode == "quick":
        result = await orchestrator.run_quick(skill_path_obj)
        metrics = config_result_to_metrics(result)
        feedback = reporter.format_quick_report(result)
    elif mode == "full":
        report = await orchestrator.run_full(skill_path_obj, parallel=parallel)
        # For metrics, use the best performing config by accuracy
        best_config = _get_best_config(report)
        if best_config:
            metrics = config_result_to_metrics(best_config)
        else:
            metrics = EvalMetrics(
                accuracy=0.0,
                latency_ms=0.0,
                tests_passed=0,
                tests_total=0,
                critic_confidence=0.0,
            )
        feedback = reporter.format_comparison_table(report)
    else:
        raise ValueError(f"Unknown evaluation mode: '{mode}'. Valid modes: quick, full")

    return metrics, feedback


def evaluate_skill_sync(
    skill_path: str,
    mode: str = "quick",
    parallel: bool = True,
    enable_critic: bool = True,
) -> tuple[EvalMetrics, str]:
    """
    Synchronous wrapper for evaluate_skill.

    Useful for non-async contexts like CLI commands.

    Args:
        skill_path: Path to the skill directory
        mode: Evaluation mode ("quick" or "full")
        parallel: Whether to run full mode in parallel
        enable_critic: Whether to enable critic evaluation

    Returns:
        Tuple of (EvalMetrics, formatted_feedback_string)
    """
    return asyncio.run(
        evaluate_skill(skill_path, mode=mode, parallel=parallel, enable_critic=enable_critic)
    )


# =============================================================================
# Result Conversion
# =============================================================================


def config_result_to_metrics(result: ConfigurationResult) -> EvalMetrics:
    """
    Convert ConfigurationResult to EvalMetrics.

    Args:
        result: ConfigurationResult from evaluation

    Returns:
        EvalMetrics instance with normalized values
    """
    if result.error:
        return EvalMetrics(
            accuracy=0.0,
            latency_ms=0.0,
            tests_passed=0,
            tests_total=0,
            critic_confidence=0.0,
        )

    return EvalMetrics(
        accuracy=result.accuracy,
        latency_ms=result.avg_latency_ms,
        tests_passed=result.tests_passed,
        tests_total=result.tests_total,
        critic_confidence=_get_avg_critic_confidence(result),
        tokens_prompt=result.total_tokens.get("prompt", 0)
        if isinstance(result.total_tokens, dict)
        else 0,
        tokens_completion=result.total_tokens.get("completion", 0)
        if isinstance(result.total_tokens, dict)
        else 0,
    )


def results_to_metrics(raw_result: dict[str, Any]) -> EvalMetrics:
    """
    Convert raw evaluation results dict to EvalMetrics.

    Supports both old sandbox evaluator format and new LLM evaluator format.

    Args:
        raw_result: Raw evaluation results dictionary

    Returns:
        EvalMetrics instance with normalized values
    """
    accuracy = raw_result.get("accuracy", 0.0)

    # Convert accuracy from percentage to fraction if needed
    if accuracy > 1.0:
        accuracy = accuracy / 100.0

    return EvalMetrics(
        accuracy=accuracy,
        latency_ms=raw_result.get("avg_latency_ms", 0.0),
        tests_passed=raw_result.get("tests_passed", 0),
        tests_total=raw_result.get("tests_total", 0),
        critic_confidence=raw_result.get("critic_confidence", 0.0),
        tokens_prompt=raw_result.get("tokens_prompt", 0),
        tokens_completion=raw_result.get("tokens_completion", 0),
    )


def _get_best_config(report: ComparisonReport) -> ConfigurationResult | None:
    """
    Get the best performing configuration from a comparison report.

    Ranks by accuracy, then by latency for ties.

    Args:
        report: ComparisonReport with multiple configurations

    Returns:
        Best ConfigurationResult or None if no successful configs
    """
    rankings = report.get_rankings()
    if not rankings.get("accuracy"):
        return None

    best_config_name = rankings["accuracy"][0]
    return report.get_result(best_config_name)


def _get_avg_critic_confidence(result: ConfigurationResult) -> float:
    """
    Calculate average critic confidence from test results.

    Args:
        result: ConfigurationResult with test results

    Returns:
        Average critic confidence (0.0 if no critic evaluations)
    """
    confidences = []
    for test in result.test_results:
        critic_eval = test.get("critic_evaluation")
        if critic_eval and "confidence" in critic_eval:
            confidences.append(critic_eval["confidence"])

    return sum(confidences) / len(confidences) if confidences else 0.0


# =============================================================================
# Feedback Extraction
# =============================================================================


def extract_failing_tests(raw_result: dict[str, Any]) -> list[dict[str, str]]:
    """
    Extract failing test information from evaluation results.

    Args:
        raw_result: Raw evaluation results (dict with test_results key)

    Returns:
        List of dicts with 'name' and 'reason' keys for each failing test
    """
    failing = []
    test_results = raw_result.get("test_results", [])

    for test in test_results:
        if not test.get("passed", True):
            reason = test.get("error") or "Assertions failed"

            # Check for failed assertions
            failed_assertions = test.get("assertions_failed", [])
            if failed_assertions:
                details = []
                for a in failed_assertions[:2]:  # Limit to first 2
                    msg = a.get("message", "")
                    if not msg and a.get("expected") is not None:
                        msg = f"expected {a['expected']}, got {a.get('actual')}"
                    details.append(msg)
                if details:
                    reason = "; ".join(details)

            # Check for critic feedback
            critic_eval = test.get("critic_evaluation")
            if critic_eval and not critic_eval.get("success", True):
                critique = critic_eval.get("critique", "")
                if critique:
                    reason = f"{reason}. Critic: {critique[:100]}"

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
    - Critic feedback if available

    Args:
        raw_result: Raw evaluation results dictionary

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

    if metrics.critic_confidence > 0:
        lines.append(f"Critic confidence: {metrics.critic_confidence:.1%}")

    if failing:
        lines.append("\nFailing tests:")
        for test in failing:
            lines.append(f"  - {test['name']}: {test['reason']}")

    return "\n".join(lines)


__all__ = [
    "evaluate_skill",
    "evaluate_skill_sync",
    "config_result_to_metrics",
    "results_to_metrics",
    "extract_failing_tests",
    "format_evaluation_feedback",
]
