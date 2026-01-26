"""Pure functions for score calculation and improvement detection.

These functions contain no side effects and can be tested
without any Temporal or external service dependencies.
"""

from ..models import EvalMetrics, IterationResult

# Constants for score calculation
ACCURACY_WEIGHT = 0.7
LATENCY_WEIGHT = 0.3
LATENCY_BASELINE_MS = 3000.0  # Normalize latency against this baseline
PLATEAU_THRESHOLD = 0.02  # 2% improvement threshold
PLATEAU_WINDOW = 2  # Check last N iterations
REGRESSION_THRESHOLD = 0.20  # 20% drop triggers regression


def compute_score(metrics: EvalMetrics) -> float:
    """
    Compute composite score from metrics.

    Score = accuracy * 0.7 + normalized_latency_score * 0.3

    Where normalized_latency_score = baseline / actual (capped at 1.0)
    Faster execution gets higher latency score.

    Args:
        metrics: Evaluation metrics containing accuracy and latency

    Returns:
        Composite score between 0.0 and 1.0

    Examples:
        >>> metrics = EvalMetrics(accuracy=0.9, latency_ms=1500, tests_passed=9, tests_total=10, critic_confidence=0.9)
        >>> score = compute_score(metrics)
        >>> score
        0.93
    """
    # Accuracy component (0.0 - 1.0)
    accuracy_score = metrics.accuracy * ACCURACY_WEIGHT

    # Latency component - faster is better
    # Cap at 1.0 (can't score higher than baseline)
    latency_ratio = min(LATENCY_BASELINE_MS / max(metrics.latency_ms, 1.0), 1.0)
    latency_score = latency_ratio * LATENCY_WEIGHT

    return accuracy_score + latency_score


def is_plateau(
    history: list[IterationResult],
    window: int = PLATEAU_WINDOW,
    threshold: float = PLATEAU_THRESHOLD,
) -> bool:
    """
    Detect if improvement has plateaued.

    Returns True if score improvement is < threshold for the last `window` iterations.

    Args:
        history: List of iteration results
        window: Number of recent iterations to check
        threshold: Minimum improvement percentage to not be considered a plateau

    Returns:
        True if plateaued, False otherwise

    Examples:
        >>> from kubani.workflows.skill_auto.models import IterationResult, EvalMetrics
        >>> history = [
        ...     IterationResult(iteration=1, metrics=EvalMetrics(accuracy=0.8, latency_ms=100, tests_passed=8, tests_total=10, critic_confidence=0.9), score=0.8, improved=True, action="continue"),
        ...     IterationResult(iteration=2, metrics=EvalMetrics(accuracy=0.81, latency_ms=100, tests_passed=8, tests_total=10, critic_confidence=0.9), score=0.81, improved=True, action="continue"),
        ...     IterationResult(iteration=3, metrics=EvalMetrics(accuracy=0.811, latency_ms=100, tests_passed=8, tests_total=10, critic_confidence=0.9), score=0.811, improved=True, action="continue"),
        ... ]
        >>> is_plateau(history)
        True
    """
    if len(history) < window + 1:
        return False

    recent = history[-(window + 1) :]

    for i in range(1, len(recent)):
        prev_score = recent[i - 1].score
        curr_score = recent[i].score

        if prev_score > 0:
            improvement = (curr_score - prev_score) / prev_score
            if improvement >= threshold:
                return False  # Found significant improvement

    return True  # All recent improvements below threshold


def detect_regression(
    history: list[IterationResult],
    current_score: float,
    threshold: float = REGRESSION_THRESHOLD,
) -> dict[str, any]:
    """
    Detect if current score represents a significant regression.

    A regression is detected when the current score drops more than
    threshold (default 20%) below the best historical score.

    Args:
        history: List of previous iteration results
        current_score: Score from the current iteration
        threshold: Percentage drop that triggers regression (0.0-1.0)

    Returns:
        Dict with:
            - is_regression: bool
            - drop_percentage: float (how much score dropped)
            - best_score: float (best score from history)
            - best_iteration: int (which iteration had best score)

    Examples:
        >>> from kubani.workflows.skill_auto.models import IterationResult, EvalMetrics
        >>> history = [
        ...     IterationResult(iteration=1, metrics=EvalMetrics(accuracy=0.9, latency_ms=100, tests_passed=9, tests_total=10, critic_confidence=0.9), score=0.9, improved=True, action="continue"),
        ... ]
        >>> result = detect_regression(history, 0.7)
        >>> result['is_regression']
        True
        >>> result['drop_percentage'] > 0.2
        True
    """
    if not history:
        return {
            "is_regression": False,
            "drop_percentage": 0.0,
            "best_score": current_score,
            "best_iteration": 0,
        }

    # Find best score in history
    best_result = max(history, key=lambda r: r.score)
    best_score = best_result.score
    best_iteration = best_result.iteration

    if best_score <= 0:
        return {
            "is_regression": False,
            "drop_percentage": 0.0,
            "best_score": best_score,
            "best_iteration": best_iteration,
        }

    # Calculate drop percentage
    drop = (best_score - current_score) / best_score

    return {
        "is_regression": drop >= threshold,
        "drop_percentage": drop,
        "best_score": best_score,
        "best_iteration": best_iteration,
    }


__all__ = [
    "compute_score",
    "is_plateau",
    "detect_regression",
    "ACCURACY_WEIGHT",
    "LATENCY_WEIGHT",
    "LATENCY_BASELINE_MS",
    "PLATEAU_THRESHOLD",
    "PLATEAU_WINDOW",
    "REGRESSION_THRESHOLD",
]
