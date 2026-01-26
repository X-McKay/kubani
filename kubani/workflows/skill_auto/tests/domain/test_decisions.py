"""Unit tests for the domain decision functions.

These tests verify the pure business logic for iteration control
without any Temporal or external service dependencies.
"""

import pytest

from kubani.workflows.skill_auto.domain.decisions import (
    make_continue_decision,
    should_continue_iteration,
)
from kubani.workflows.skill_auto.domain.models import (
    ContinueDecision,
    EvalMetrics,
    IterationContext,
    IterationResult,
)


def create_metrics(accuracy: float = 0.8) -> EvalMetrics:
    """Helper to create EvalMetrics with sensible defaults."""
    return EvalMetrics(
        accuracy=accuracy,
        latency_ms=100.0,
        tests_passed=8,
        tests_total=10,
        critic_confidence=0.9,
    )


def create_history(scores: list[float]) -> list[IterationResult]:
    """Helper to create a dummy history from a list of scores."""
    return [
        IterationResult(
            iteration=i + 1,
            metrics=create_metrics(s),
            score=s,
            improved=i == 0 or s > scores[i - 1],
            action="continue",
        )
        for i, s in enumerate(scores)
    ]


def create_context(**overrides) -> IterationContext:
    """Helper to create an IterationContext with sensible defaults."""
    defaults = {
        "current_iteration": 5,
        "max_iterations": 10,
        "best_score": 0.8,
        "target_accuracy": 0.9,
        "history": create_history([0.5, 0.6, 0.7, 0.75, 0.8]),
        "is_cancelled": False,
    }
    defaults.update(overrides)
    return IterationContext(**defaults)


class TestShouldContinueIteration:
    """Tests for the should_continue_iteration function."""

    def test_happy_path_continue(self):
        """Should continue when no stopping conditions are met."""
        ctx = create_context()

        should_continue, reason = should_continue_iteration(ctx)

        assert should_continue is True
        assert reason == "continue_improving"

    def test_stops_when_cancelled(self):
        """Should stop immediately when workflow is cancelled."""
        ctx = create_context(is_cancelled=True)

        should_continue, reason = should_continue_iteration(ctx)

        assert should_continue is False
        assert reason == "cancelled"

    def test_stops_when_max_iterations_reached(self):
        """Should stop when current iteration equals max iterations."""
        ctx = create_context(current_iteration=10, max_iterations=10)

        should_continue, reason = should_continue_iteration(ctx)

        assert should_continue is False
        assert reason == "max_iterations_reached"

    def test_stops_when_max_iterations_exceeded(self):
        """Should stop when current iteration exceeds max iterations."""
        ctx = create_context(current_iteration=11, max_iterations=10)

        should_continue, reason = should_continue_iteration(ctx)

        assert should_continue is False
        assert reason == "max_iterations_reached"

    def test_stops_when_target_accuracy_met(self):
        """Should stop when best score meets target accuracy."""
        ctx = create_context(best_score=0.9, target_accuracy=0.9)

        should_continue, reason = should_continue_iteration(ctx)

        assert should_continue is False
        assert reason == "target_accuracy_met"

    def test_stops_when_target_accuracy_exceeded(self):
        """Should stop when best score exceeds target accuracy."""
        ctx = create_context(best_score=0.95, target_accuracy=0.9)

        should_continue, reason = should_continue_iteration(ctx)

        assert should_continue is False
        assert reason == "target_accuracy_met"

    def test_stops_when_score_plateaued(self):
        """Should stop when score has plateaued over recent iterations."""
        # Create history with plateau (same score for last 3+ iterations)
        plateau_history = create_history([0.5, 0.6, 0.7, 0.7, 0.7])
        ctx = create_context(history=plateau_history)

        should_continue, reason = should_continue_iteration(ctx)

        assert should_continue is False
        assert reason == "score_plateaued"

    def test_continues_when_plateau_window_not_met(self):
        """Should continue when history is too short for plateau detection."""
        short_history = create_history([0.7, 0.7])
        ctx = create_context(history=short_history)

        should_continue, reason = should_continue_iteration(ctx)

        assert should_continue is True
        assert reason == "continue_improving"

    def test_continues_with_empty_history(self):
        """Should continue when there's no history yet."""
        ctx = create_context(history=[])

        should_continue, reason = should_continue_iteration(ctx)

        assert should_continue is True
        assert reason == "continue_improving"

    def test_cancelled_takes_priority_over_max_iterations(self):
        """Cancellation should be checked before max iterations."""
        ctx = create_context(
            is_cancelled=True,
            current_iteration=10,
            max_iterations=10,
        )

        should_continue, reason = should_continue_iteration(ctx)

        assert should_continue is False
        assert reason == "cancelled"

    def test_max_iterations_takes_priority_over_target_accuracy(self):
        """Max iterations should be checked before target accuracy."""
        ctx = create_context(
            current_iteration=10,
            max_iterations=10,
            best_score=0.95,
            target_accuracy=0.9,
        )

        should_continue, reason = should_continue_iteration(ctx)

        assert should_continue is False
        assert reason == "max_iterations_reached"


class TestMakeContinueDecision:
    """Tests for the make_continue_decision function."""

    def test_returns_continue_decision_object(self):
        """Should return a ContinueDecision dataclass."""
        ctx = create_context()

        decision = make_continue_decision(ctx)

        assert isinstance(decision, ContinueDecision)
        assert decision.should_continue is True
        assert decision.reason == "continue_improving"

    def test_matches_should_continue_iteration(self):
        """Should return the same result as should_continue_iteration."""
        ctx = create_context(is_cancelled=True)

        decision = make_continue_decision(ctx)
        should_continue, reason = should_continue_iteration(ctx)

        assert decision.should_continue == should_continue
        assert decision.reason == reason


@pytest.mark.parametrize(
    "ctx_overrides,expected_continue,expected_reason",
    [
        # Test Case 1: Happy path, continue
        ({}, True, "continue_improving"),
        # Test Case 2: Max iterations reached
        ({"current_iteration": 10, "max_iterations": 10}, False, "max_iterations_reached"),
        # Test Case 3: Target accuracy met
        ({"best_score": 0.95, "target_accuracy": 0.9}, False, "target_accuracy_met"),
        # Test Case 4: Workflow cancelled
        ({"is_cancelled": True}, False, "cancelled"),
        # Test Case 5: Score has plateaued
        ({"history": create_history([0.5, 0.6, 0.7, 0.7, 0.7])}, False, "score_plateaued"),
        # Test Case 6: Plateau window not met yet
        ({"history": create_history([0.7, 0.7])}, True, "continue_improving"),
        # Test Case 7: First iteration (no history)
        ({"current_iteration": 1, "history": []}, True, "continue_improving"),
        # Test Case 8: Just below target
        ({"best_score": 0.89, "target_accuracy": 0.9}, True, "continue_improving"),
    ],
)
def test_should_continue_iteration_parametrized(ctx_overrides, expected_continue, expected_reason):
    """Parametrized tests for all scenarios."""
    base_context = {
        "current_iteration": 5,
        "max_iterations": 10,
        "best_score": 0.8,
        "target_accuracy": 0.9,
        "history": create_history([0.5, 0.6, 0.7, 0.75, 0.8]),
        "is_cancelled": False,
    }

    # Apply test-specific overrides
    test_ctx_dict = {**base_context, **ctx_overrides}
    ctx = IterationContext(**test_ctx_dict)

    should_continue, reason = should_continue_iteration(ctx)

    assert should_continue == expected_continue
    assert reason == expected_reason
