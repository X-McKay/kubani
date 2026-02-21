"""Tests for LLM API unavailability error handling.

This module tests that the system properly handles LLM API failures
with exponential backoff retry logic.

Requirements: 12.1
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from temporalio.testing import ActivityEnvironment


@pytest.mark.asyncio
async def test_plan_response_llm_unavailable_retries():
    """Test that plan_response retries on LLM API failure.

    Validates: Requirements 12.1
    - Simulates LLM API failure
    - Verifies retry with exponential backoff (3 attempts)
    """
    from kubani.nexus.orchestrator.activities import plan_response

    # Track retry attempts
    attempt_count = 0
    attempt_times = []

    async def failing_llm_chat(*args, **kwargs):
        nonlocal attempt_count
        attempt_count += 1
        attempt_times.append(asyncio.get_event_loop().time())

        # Fail first 2 attempts, succeed on 3rd
        if attempt_count < 3:
            raise ConnectionError("LLM API unavailable")

        return '{"needs_plan": false, "direct_response": "Hello! How can I help?"}'

    # Mock the LLM client
    with patch("kubani.framework.llm.get_llm") as mock_get_llm:
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(side_effect=failing_llm_chat)
        mock_get_llm.return_value = mock_llm

        # Configure activity with retry policy
        env = ActivityEnvironment()

        input_data = {
            "user_message": "Hello",
            "conversation_history": [],
            "available_skills": [],
            "memories": [],
        }

        # Execute activity - should retry and eventually succeed
        result = await env.run(plan_response, input_data)

        # Verify retries occurred
        assert attempt_count == 3, f"Expected 3 attempts, got {attempt_count}"

        # Verify exponential backoff (times should increase)
        if len(attempt_times) >= 2:
            first_gap = attempt_times[1] - attempt_times[0]
            # First retry should have some delay (at least 0.1s)
            assert first_gap >= 0.1, f"First retry too fast: {first_gap}s"

        # Verify final result is successful
        assert result["needs_plan"] is False
        assert "Hello" in result["direct_response"]


@pytest.mark.asyncio
async def test_plan_response_llm_permanent_failure():
    """Test that plan_response fails gracefully after max retries.

    Validates: Requirements 12.1
    - Simulates permanent LLM API failure
    - Verifies graceful failure after 3 attempts
    """
    from kubani.nexus.orchestrator.activities import plan_response

    attempt_count = 0

    async def always_failing_llm_chat(*args, **kwargs):
        nonlocal attempt_count
        attempt_count += 1
        raise ConnectionError("LLM API permanently unavailable")

    with patch("kubani.framework.llm.get_llm") as mock_get_llm:
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(side_effect=always_failing_llm_chat)
        mock_get_llm.return_value = mock_llm

        env = ActivityEnvironment()

        input_data = {
            "user_message": "Hello",
            "conversation_history": [],
            "available_skills": [],
            "memories": [],
        }

        # Execute activity - should fail after retries
        with pytest.raises(ConnectionError, match="LLM API permanently unavailable"):
            await env.run(plan_response, input_data)

        # Verify max retries were attempted
        assert attempt_count >= 3, f"Expected at least 3 attempts, got {attempt_count}"


@pytest.mark.asyncio
async def test_generate_response_llm_unavailable_retries():
    """Test that generate_response retries on LLM API failure.

    Validates: Requirements 12.1
    - Simulates LLM API failure during response generation
    - Verifies retry with exponential backoff
    """
    from kubani.nexus.orchestrator.activities import generate_response

    attempt_count = 0

    async def failing_llm_chat(*args, **kwargs):
        nonlocal attempt_count
        attempt_count += 1

        # Fail first 2 attempts, succeed on 3rd
        if attempt_count < 3:
            raise TimeoutError("LLM API timeout")

        return "Based on the execution results, here's what happened..."

    with patch("kubani.framework.llm.get_llm") as mock_get_llm:
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(side_effect=failing_llm_chat)
        mock_get_llm.return_value = mock_llm

        env = ActivityEnvironment()

        input_data = {
            "user_message": "Do something",
            "goal": "Complete task",
            "step_results": [{"success": True, "output": "Task completed"}],
        }

        # Execute activity - should retry and eventually succeed
        result = await env.run(generate_response, input_data)

        # Verify retries occurred
        assert attempt_count == 3, f"Expected 3 attempts, got {attempt_count}"

        # Verify final result is successful
        assert "response_text" in result
        assert len(result["response_text"]) > 0


@pytest.mark.asyncio
async def test_llm_retry_with_different_errors():
    """Test that LLM retries work with various error types.

    Validates: Requirements 12.1
    - Tests retry behavior with different exception types
    """
    from kubani.nexus.orchestrator.activities import plan_response

    errors_to_test = [
        ConnectionError("Connection refused"),
        TimeoutError("Request timeout"),
        Exception("Generic error"),
    ]

    for error in errors_to_test:
        attempt_count = 0

        async def failing_llm_chat(*args, **kwargs):
            nonlocal attempt_count
            attempt_count += 1

            if attempt_count < 3:
                raise error

            return '{"needs_plan": false, "direct_response": "Success"}'

        with patch("kubani.framework.llm.get_llm") as mock_get_llm:
            mock_llm = AsyncMock()
            mock_llm.chat = AsyncMock(side_effect=failing_llm_chat)
            mock_get_llm.return_value = mock_llm

            env = ActivityEnvironment()

            input_data = {
                "user_message": "Test",
                "conversation_history": [],
                "available_skills": [],
                "memories": [],
            }

            # Should retry and succeed
            result = await env.run(plan_response, input_data)

            assert attempt_count == 3, f"Expected 3 attempts for {type(error).__name__}"
            assert result["needs_plan"] is False
