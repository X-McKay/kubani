"""Tests for models.py - data models and scoring functions.

Tests cover:
- Scoring functions (compute_score, is_plateau, detect_regression)
- Decision functions (should_continue_iteration, make_continue_decision)
- Helper functions (create_no_overlap_result)
"""

import pytest

from kubani.workflows.skill_auto.models import (
    ACCURACY_WEIGHT,
    LATENCY_WEIGHT,
    ContinueDecision,
    EvalMetrics,
    IterationContext,
    OverlapResult,
    SkillSpec,
    compute_score,
    create_no_overlap_result,
    detect_regression,
    is_plateau,
    make_continue_decision,
    should_continue_iteration,
)

# =============================================================================
# Scoring Function Tests
# =============================================================================


class TestComputeScore:
    """Tests for compute_score function."""

    def test_perfect_accuracy_fast_latency(self, perfect_metrics):
        """Perfect accuracy and fast latency gives score close to 1.0."""
        score = compute_score(perfect_metrics)
        assert score == pytest.approx(1.0, rel=0.01)

    def test_zero_accuracy(self):
        """Zero accuracy gives only latency component."""
        metrics = EvalMetrics(
            accuracy=0.0,
            latency_ms=1000.0,
            tests_passed=0,
            tests_total=5,
            critic_confidence=0.0,
        )
        score = compute_score(metrics)
        # Only latency component: 0.3 * min(3000/1000, 1.0) = 0.3 * 1.0 = 0.3
        assert score == pytest.approx(0.3, rel=0.01)

    def test_slow_latency(self, poor_metrics):
        """Slow latency reduces score."""
        score = compute_score(poor_metrics)
        # accuracy: 0.2 * 0.7 = 0.14
        # latency: 3000/5000 = 0.6 * 0.3 = 0.18
        # total: 0.32
        assert score == pytest.approx(0.32, rel=0.01)

    def test_score_between_zero_and_one(self, sample_metrics):
        """Score is always between 0 and 1."""
        score = compute_score(sample_metrics)
        assert 0.0 <= score <= 1.0

    def test_very_fast_latency_capped(self):
        """Very fast latency is capped at baseline."""
        metrics = EvalMetrics(
            accuracy=0.8,
            latency_ms=10.0,  # Very fast
            tests_passed=4,
            tests_total=5,
            critic_confidence=0.8,
        )
        score = compute_score(metrics)
        # accuracy: 0.8 * 0.7 = 0.56
        # latency: min(3000/10, 1.0) * 0.3 = 1.0 * 0.3 = 0.3
        # total: 0.86
        assert score == pytest.approx(0.86, rel=0.01)

    def test_weights_add_up_correctly(self):
        """Verify ACCURACY_WEIGHT + LATENCY_WEIGHT equals 1.0."""
        assert pytest.approx(1.0) == ACCURACY_WEIGHT + LATENCY_WEIGHT


class TestIsPlateau:
    """Tests for is_plateau function."""

    def test_not_enough_history(self, iteration_history):
        """Not enough history returns False."""
        short_history = iteration_history[:1]
        assert is_plateau(short_history) is False

    def test_improving_not_plateau(self, iteration_history):
        """Clear improvement is not a plateau."""
        assert is_plateau(iteration_history) is False

    def test_plateau_detected(self, plateau_history):
        """Detect plateau when improvement is minimal."""
        assert is_plateau(plateau_history) is True

    def test_empty_history(self):
        """Empty history is not a plateau."""
        assert is_plateau([]) is False

    def test_custom_threshold(self, plateau_history):
        """Custom threshold changes detection."""
        # With very low threshold, even small improvements count
        assert is_plateau(plateau_history, threshold=0.001) is False


class TestDetectRegression:
    """Tests for detect_regression function."""

    def test_no_history(self):
        """No history means no regression."""
        result = detect_regression([], 0.5)
        assert result["is_regression"] is False
        assert result["best_score"] == 0.5

    def test_improvement_not_regression(self, iteration_history):
        """Higher score than history is not regression."""
        result = detect_regression(iteration_history, 0.9)
        assert result["is_regression"] is False

    def test_small_drop_not_regression(self, iteration_history):
        """Small drop (< 20%) is not regression."""
        # Best score in history is 0.75
        result = detect_regression(iteration_history, 0.65)  # ~13% drop
        assert result["is_regression"] is False

    def test_large_drop_is_regression(self, iteration_history):
        """Large drop (> 20%) is regression."""
        # Best score in history is 0.75
        result = detect_regression(iteration_history, 0.5)  # ~33% drop
        assert result["is_regression"] is True
        assert result["drop_percentage"] == pytest.approx(33.3, rel=0.1)
        assert result["best_score"] == 0.75
        assert result["best_iteration"] == 3

    def test_custom_threshold(self, iteration_history):
        """Custom threshold changes detection."""
        # 13% drop with 10% threshold should be regression
        result = detect_regression(iteration_history, 0.65, threshold=0.10)
        assert result["is_regression"] is True


# =============================================================================
# Decision Function Tests
# =============================================================================


class TestShouldContinueIteration:
    """Tests for should_continue_iteration function."""

    def test_stops_when_cancelled(self):
        """Cancellation stops iteration immediately."""
        ctx = IterationContext(
            current_iteration=1,
            max_iterations=10,
            best_score=0.5,
            target_accuracy=0.9,
            is_cancelled=True,
        )
        should_continue, reason = should_continue_iteration(ctx)
        assert should_continue is False
        assert reason == "cancelled"

    def test_stops_at_max_iterations(self):
        """Stops when max iterations reached."""
        ctx = IterationContext(
            current_iteration=10,
            max_iterations=10,
            best_score=0.5,
            target_accuracy=0.9,
        )
        should_continue, reason = should_continue_iteration(ctx)
        assert should_continue is False
        assert reason == "max_iterations_reached"

    def test_stops_when_target_met(self):
        """Stops when target accuracy is met."""
        ctx = IterationContext(
            current_iteration=3,
            max_iterations=10,
            best_score=0.95,
            target_accuracy=0.9,
        )
        should_continue, reason = should_continue_iteration(ctx)
        assert should_continue is False
        assert reason == "target_accuracy_met"

    def test_continues_when_improving(self):
        """Continues when still improving."""
        ctx = IterationContext(
            current_iteration=3,
            max_iterations=10,
            best_score=0.6,
            target_accuracy=0.9,
            history=[],
        )
        should_continue, reason = should_continue_iteration(ctx)
        assert should_continue is True
        assert reason == "continue_improving"

    def test_stops_on_plateau(self, plateau_history):
        """Stops when plateau detected."""
        ctx = IterationContext(
            current_iteration=4,
            max_iterations=10,
            best_score=0.808,
            target_accuracy=0.9,
            history=plateau_history,
        )
        should_continue, reason = should_continue_iteration(ctx)
        assert should_continue is False
        assert reason == "score_plateaued"


class TestMakeContinueDecision:
    """Tests for make_continue_decision function."""

    def test_returns_decision_object(self):
        """Returns a ContinueDecision dataclass."""
        ctx = IterationContext(
            current_iteration=3,
            max_iterations=10,
            best_score=0.6,
            target_accuracy=0.9,
        )
        decision = make_continue_decision(ctx)
        assert isinstance(decision, ContinueDecision)
        assert decision.should_continue is True
        assert decision.reason == "continue_improving"

    def test_decision_matches_function(self):
        """Decision object matches tuple function result."""
        ctx = IterationContext(
            current_iteration=10,
            max_iterations=10,
            best_score=0.5,
            target_accuracy=0.9,
        )
        should_continue, reason = should_continue_iteration(ctx)
        decision = make_continue_decision(ctx)

        assert decision.should_continue == should_continue
        assert decision.reason == reason


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestCreateNoOverlapResult:
    """Tests for create_no_overlap_result helper."""

    def test_default_result(self):
        """Creates default no-overlap result."""
        result = create_no_overlap_result()
        assert result.has_overlap is False
        assert result.confidence == 1.0
        assert result.overlapping_skills == []
        assert result.recommendation == "proceed"

    def test_custom_reason(self):
        """Creates result with custom reason."""
        result = create_no_overlap_result("Custom reason here")
        assert result.reasoning == "Custom reason here"

    def test_returns_overlap_result(self):
        """Returns an OverlapResult instance."""
        result = create_no_overlap_result()
        assert isinstance(result, OverlapResult)


# =============================================================================
# Pydantic Model Tests
# =============================================================================


class TestSkillSpec:
    """Tests for SkillSpec Pydantic model."""

    def test_valid_skill_spec(self):
        """Create valid SkillSpec from dict."""
        data = {
            "name": "test-skill",
            "description": "A test skill",
            "inputs": {"query": {"type": "string", "description": "Input query", "required": True}},
            "outputs": {"result": {"type": "string", "description": "Output result"}},
            "steps": ["Step 1", "Step 2"],
            "error_handling": ["Handle errors gracefully"],
            "examples": [
                {
                    "name": "example1",
                    "description": "Example description",
                    "input": {"query": "test"},
                    "expected_output": {"result": "test result"},
                }
            ],
        }
        spec = SkillSpec.model_validate(data)
        assert spec.name == "test-skill"
        assert len(spec.inputs) == 1
        assert spec.inputs["query"].type == "string"

    def test_model_dump(self):
        """SkillSpec can be serialized back to dict."""
        data = {
            "name": "test-skill",
            "description": "A test skill",
            "inputs": {},
            "outputs": {},
            "steps": [],
            "error_handling": [],
            "examples": [],
        }
        spec = SkillSpec.model_validate(data)
        dumped = spec.model_dump()
        assert dumped["name"] == "test-skill"
