# tests/workflows/agent_auto/domain/test_analysis.py
"""Unit tests for the analysis functions."""

from kubani.workflows.agent_auto.domain.analysis import analyze_evaluation_failures
from kubani.workflows.agent_auto.domain.models import AgentEvaluationResult


def test_analyze_failures_suggests_skill_addition_for_missing_skills():
    """Tests that missing skills in an eval result lead to skill addition suggestions."""
    # Arrange
    eval_result = AgentEvaluationResult(
        objective_accuracy=0.5,
        skill_precision=1.0,
        skill_recall=0.5,
        invoked_skills=["skill/a"],
        missing_skills=["skill/b"],
        extraneous_skills=[],
        failures=["Test Case 2"],
    )

    # Act
    suggestions = analyze_evaluation_failures(eval_result)

    # Assert
    assert suggestions.skill_additions == ["skill/b"]
    assert "missing skills: ['skill/b']" in suggestions.prompt_clarifications[0]


def test_analyze_failures_suggests_clarification_for_extraneous_skills():
    """Tests that extraneous skills lead to prompt clarification suggestions."""
    # Arrange
    eval_result = AgentEvaluationResult(
        objective_accuracy=0.75,
        skill_precision=0.5,
        skill_recall=1.0,
        invoked_skills=["skill/a", "skill/c"],
        missing_skills=[],
        extraneous_skills=["skill/c"],
        failures=["Test Case 3"],
    )

    # Act
    suggestions = analyze_evaluation_failures(eval_result)

    # Assert
    assert suggestions.skill_additions == []
    assert "ambiguous" in suggestions.prompt_clarifications[0].lower()
    assert "skill/c" in suggestions.prompt_clarifications[0]


def test_analyze_failures_no_suggestions_for_perfect_result():
    """Tests that a perfect evaluation result produces no suggestions."""
    # Arrange
    eval_result = AgentEvaluationResult(
        objective_accuracy=1.0,
        skill_precision=1.0,
        skill_recall=1.0,
        invoked_skills=["skill/a", "skill/b"],
        missing_skills=[],
        extraneous_skills=[],
        failures=[],
    )

    # Act
    suggestions = analyze_evaluation_failures(eval_result)

    # Assert
    assert suggestions.skill_additions == []
    assert suggestions.skill_removals == []
    assert suggestions.prompt_clarifications == []
