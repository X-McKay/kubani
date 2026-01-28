"""Tests for Critic agent models."""

from datetime import UTC, datetime

from kubani.agents.critic.models import (
    DEFAULT_WEIGHTS,
    CriticEvaluation,
    EvaluationCriteria,
    ExecutionRecord,
)


class TestEvaluationCriteria:
    """Tests for EvaluationCriteria enum."""

    def test_all_criteria_exist(self):
        """Test that all expected criteria exist."""
        assert EvaluationCriteria.TASK_COMPLETION.value == "task_completion"
        assert EvaluationCriteria.EFFICIENCY.value == "efficiency"
        assert EvaluationCriteria.SAFETY.value == "safety"
        assert EvaluationCriteria.QUALITY.value == "quality"

    def test_default_weights_sum_to_one(self):
        """Test that default weights sum to 1.0."""
        total = sum(DEFAULT_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001


class TestExecutionRecord:
    """Tests for ExecutionRecord dataclass."""

    def test_create_record(self):
        """Test creating an execution record."""
        now = datetime.now(UTC)
        record = ExecutionRecord(
            execution_id="exec-123",
            agent_id="test-agent",
            task_description="Test task",
            start_time=now,
        )
        assert record.execution_id == "exec-123"
        assert record.agent_id == "test-agent"
        assert record.task_description == "Test task"
        assert record.start_time == now
        assert record.end_time is None
        assert record.success is False

    def test_duration_ms_with_end_time(self):
        """Test duration calculation when end_time is set."""
        start = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        end = datetime(2024, 1, 1, 0, 0, 5, tzinfo=UTC)  # 5 seconds later
        record = ExecutionRecord(
            execution_id="exec-123",
            agent_id="test-agent",
            task_description="Test",
            start_time=start,
            end_time=end,
        )
        assert record.duration_ms == 5000

    def test_duration_ms_without_end_time(self):
        """Test duration is 0 when end_time is not set."""
        record = ExecutionRecord(
            execution_id="exec-123",
            agent_id="test-agent",
            task_description="Test",
            start_time=datetime.now(UTC),
        )
        assert record.duration_ms == 0


class TestCriticEvaluation:
    """Tests for CriticEvaluation dataclass."""

    def test_default_evaluation(self):
        """Test default evaluation values."""
        evaluation = CriticEvaluation()
        assert evaluation.execution_id == ""
        assert evaluation.agent_id == ""
        assert evaluation.task_completion_score == 0.0
        assert evaluation.efficiency_score == 0.0
        assert evaluation.safety_score == 0.0
        assert evaluation.quality_score == 0.0
        assert evaluation.overall_score == 0.0
        assert evaluation.success is False
        assert evaluation.improvement_suggestions == []
        assert evaluation.strengths == []

    def test_compute_overall_score(self):
        """Test weighted overall score computation."""
        evaluation = CriticEvaluation(
            task_completion_score=1.0,
            efficiency_score=1.0,
            safety_score=1.0,
            quality_score=1.0,
        )
        score = evaluation.compute_overall_score()
        # All 1.0 with default weights should equal 1.0
        assert abs(score - 1.0) < 0.001
        assert evaluation.overall_score == score

    def test_compute_overall_score_partial(self):
        """Test weighted overall score with partial scores."""
        evaluation = CriticEvaluation(
            task_completion_score=0.8,
            efficiency_score=0.6,
            safety_score=1.0,
            quality_score=0.7,
        )
        score = evaluation.compute_overall_score()
        # 0.8*0.35 + 0.6*0.20 + 1.0*0.25 + 0.7*0.20 = 0.28 + 0.12 + 0.25 + 0.14 = 0.79
        assert abs(score - 0.79) < 0.001

    def test_has_improvement_opportunity_with_suggestions(self):
        """Test improvement opportunity detection with suggestions."""
        evaluation = CriticEvaluation(
            improvement_suggestions=["Try faster approach"],
            success=True,
        )
        assert evaluation.has_improvement_opportunity is True

    def test_has_improvement_opportunity_low_score(self):
        """Test improvement opportunity detection with low score."""
        evaluation = CriticEvaluation(
            overall_score=0.5,
            success=False,
        )
        assert evaluation.has_improvement_opportunity is True

    def test_no_improvement_opportunity(self):
        """Test when there's no improvement opportunity."""
        evaluation = CriticEvaluation(
            overall_score=0.9,
            success=True,
        )
        assert evaluation.has_improvement_opportunity is False

    def test_to_dict(self):
        """Test conversion to dictionary."""
        evaluation = CriticEvaluation(
            evaluation_id="eval-123",
            execution_id="exec-456",
            agent_id="test-agent",
            task_description="Test task",
            task_completion_score=0.9,
            efficiency_score=0.8,
            safety_score=1.0,
            quality_score=0.85,
            overall_score=0.89,
            success=True,
            improvement_suggestions=["suggestion1"],
            strengths=["strength1"],
        )
        data = evaluation.to_dict()
        assert data["evaluation_id"] == "eval-123"
        assert data["execution_id"] == "exec-456"
        assert data["agent_id"] == "test-agent"
        assert data["scores"]["task_completion"] == 0.9
        assert data["scores"]["efficiency"] == 0.8
        assert data["scores"]["overall"] == 0.89
        assert data["success"] is True
        assert data["improvement_suggestions"] == ["suggestion1"]
        assert data["strengths"] == ["strength1"]
