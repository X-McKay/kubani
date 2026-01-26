# tests/workflows/agent_auto/services/test_evaluation_service.py
"""Integration tests for the EvaluationService."""

import pytest

from kubani.workflows.agent_auto.domain.models import AgentTestCase
from kubani.workflows.agent_auto.services.evaluation import EvaluationService

from .mocks import MockAgentRunner


@pytest.mark.asyncio
async def test_evaluate_agent_perfect_score():
    """Tests evaluation with all test cases passing."""
    # Arrange
    mock_runner = MockAgentRunner()
    mock_runner.set_result_for_prompt(
        "What is 2+2?",
        output="4",
        invoked_skills=["math/add"],
    )
    mock_runner.set_result_for_prompt(
        "What is 3*3?",
        output="9",
        invoked_skills=["math/multiply"],
    )

    service = EvaluationService(agent_runner=mock_runner)

    test_cases = [
        AgentTestCase(
            name="addition",
            prompt="What is 2+2?",
            expected_skills=["math/add"],
            expected_output="4",
        ),
        AgentTestCase(
            name="multiplication",
            prompt="What is 3*3?",
            expected_skills=["math/multiply"],
            expected_output="9",
        ),
    ]

    # Act
    result = await service.evaluate_agent("agents/math", test_cases)

    # Assert
    assert result.objective_accuracy == 1.0
    assert result.skill_precision == 1.0
    assert result.skill_recall == 1.0
    assert result.failures == []


@pytest.mark.asyncio
async def test_evaluate_agent_partial_failures():
    """Tests evaluation with some test cases failing."""
    # Arrange
    mock_runner = MockAgentRunner()
    mock_runner.set_result_for_prompt(
        "What is 2+2?",
        output="4",
        invoked_skills=["math/add"],
    )
    mock_runner.set_result_for_prompt(
        "What is 3*3?",
        output="6",  # Wrong answer
        invoked_skills=["math/add"],  # Wrong skill
    )

    service = EvaluationService(agent_runner=mock_runner)

    test_cases = [
        AgentTestCase(
            name="addition",
            prompt="What is 2+2?",
            expected_skills=["math/add"],
            expected_output="4",
        ),
        AgentTestCase(
            name="multiplication",
            prompt="What is 3*3?",
            expected_skills=["math/multiply"],
            expected_output="9",
        ),
    ]

    # Act
    result = await service.evaluate_agent("agents/math", test_cases)

    # Assert
    assert result.objective_accuracy == 0.5  # 1 of 2 passed
    assert result.failures == ["multiplication"]
    assert "math/multiply" in result.missing_skills


@pytest.mark.asyncio
async def test_evaluate_agent_empty_test_cases():
    """Tests evaluation with no test cases returns perfect scores."""
    # Arrange
    mock_runner = MockAgentRunner()
    service = EvaluationService(agent_runner=mock_runner)

    # Act
    result = await service.evaluate_agent("agents/empty", [])

    # Assert
    assert result.objective_accuracy == 1.0
    assert result.skill_precision == 1.0
    assert result.skill_recall == 1.0
    assert result.failures == []
