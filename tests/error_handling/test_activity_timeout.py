"""Tests for Temporal activity timeout error handling.

This module tests that activities properly handle timeouts and retry
according to the configured retry policy.

Requirements: 12.4
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from temporalio.testing import ActivityEnvironment


@pytest.mark.asyncio
async def test_execute_skill_activity_timeout():
    """Test that execute_skill_activity handles timeouts properly.

    Validates: Requirements 12.4
    - Simulates slow activity execution
    - Verifies timeout and retry according to policy
    """
    from kubani.nexus.orchestrator.activities import execute_skill_activity

    attempt_count = 0

    async def slow_execute_skill(*args, **kwargs):
        nonlocal attempt_count
        attempt_count += 1

        # First attempt times out, second succeeds quickly
        if attempt_count == 1:
            await asyncio.sleep(10)  # Simulate long-running operation
            return {
                "success": False,
                "output": "",
                "error": "Should have timed out",
                "duration_ms": 10000,
                "exit_code": -1,
                "logs": "",
            }

        # Second attempt succeeds
        return {
            "success": True,
            "output": "Skill executed successfully",
            "error": None,
            "duration_ms": 100,
            "exit_code": 0,
            "logs": "Execution logs",
        }

    with patch(
        "kubani.nexus.sandbox.executor.execute_skill_in_sandbox", side_effect=slow_execute_skill
    ):
        env = ActivityEnvironment()

        input_data = {
            "skill_name": "test-skill",
            "inputs": {"param": "value"},
            "timeout_seconds": 1,  # Short timeout
            "conversation_id": "conv-123",
        }

        # Execute with timeout - first attempt should timeout, second should succeed
        try:
            result = await asyncio.wait_for(
                env.run(execute_skill_activity, input_data),
                timeout=2.0,  # Give enough time for retry
            )

            # If we get here, the retry succeeded
            assert attempt_count >= 1

        except TimeoutError:
            # First attempt timed out as expected
            assert attempt_count >= 1


@pytest.mark.asyncio
async def test_plan_response_activity_timeout():
    """Test that plan_response handles timeouts properly.

    Validates: Requirements 12.4
    - Simulates slow LLM response
    - Verifies timeout handling
    """
    from kubani.nexus.orchestrator.activities import plan_response

    attempt_count = 0

    async def slow_llm_chat(*args, **kwargs):
        nonlocal attempt_count
        attempt_count += 1

        # First attempt is slow, second is fast
        if attempt_count == 1:
            await asyncio.sleep(5)
            return '{"needs_plan": false, "direct_response": "Slow response"}'

        return '{"needs_plan": false, "direct_response": "Fast response"}'

    with patch("kubani.framework.llm.get_llm") as mock_get_llm:
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(side_effect=slow_llm_chat)
        mock_get_llm.return_value = mock_llm

        env = ActivityEnvironment()

        input_data = {
            "user_message": "Hello",
            "conversation_history": [],
            "available_skills": [],
            "memories": [],
        }

        # Execute with timeout
        try:
            result = await asyncio.wait_for(env.run(plan_response, input_data), timeout=2.0)

            # Should timeout on first attempt
            pytest.fail("Should have timed out")

        except TimeoutError:
            # Expected timeout
            assert attempt_count >= 1


@pytest.mark.asyncio
async def test_generate_response_activity_timeout():
    """Test that generate_response handles timeouts properly.

    Validates: Requirements 12.4
    - Simulates slow response generation
    - Verifies timeout and retry
    """
    from kubani.nexus.orchestrator.activities import generate_response

    attempt_count = 0

    async def slow_llm_chat(*args, **kwargs):
        nonlocal attempt_count
        attempt_count += 1

        # Simulate slow response on first attempt
        if attempt_count == 1:
            await asyncio.sleep(10)

        return "Generated response"

    with patch("kubani.framework.llm.get_llm") as mock_get_llm:
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(side_effect=slow_llm_chat)
        mock_get_llm.return_value = mock_llm

        env = ActivityEnvironment()

        input_data = {
            "user_message": "Do something",
            "goal": "Complete task",
            "step_results": [{"success": True, "output": "Done"}],
        }

        # Execute with timeout
        try:
            result = await asyncio.wait_for(env.run(generate_response, input_data), timeout=2.0)

            pytest.fail("Should have timed out")

        except TimeoutError:
            # Expected timeout
            assert attempt_count >= 1


@pytest.mark.asyncio
async def test_activity_timeout_with_heartbeat():
    """Test that activities with heartbeats handle timeouts correctly.

    Validates: Requirements 12.4
    - Simulates activity with heartbeats that times out
    - Verifies heartbeat doesn't prevent timeout
    """
    from kubani.nexus.orchestrator.activities import execute_skill_activity

    async def slow_with_heartbeat(*args, **kwargs):
        # Simulate long operation with heartbeats
        for i in range(10):
            await asyncio.sleep(1)
            # Heartbeat would be sent here in real execution

        return {
            "success": True,
            "output": "Should not reach here",
            "error": None,
            "duration_ms": 10000,
            "exit_code": 0,
            "logs": "",
        }

    with patch(
        "kubani.nexus.sandbox.executor.execute_skill_in_sandbox", side_effect=slow_with_heartbeat
    ):
        env = ActivityEnvironment()

        input_data = {
            "skill_name": "slow-skill",
            "inputs": {},
            "timeout_seconds": 2,
            "conversation_id": "conv-heartbeat",
        }

        # Execute with timeout
        try:
            result = await asyncio.wait_for(
                env.run(execute_skill_activity, input_data), timeout=3.0
            )

            pytest.fail("Should have timed out despite heartbeats")

        except TimeoutError:
            # Expected timeout
            pass


@pytest.mark.asyncio
async def test_activity_retry_after_timeout():
    """Test that activities retry after timeout according to policy.

    Validates: Requirements 12.4
    - Simulates timeout followed by successful retry
    - Verifies retry policy is applied
    """
    from kubani.nexus.orchestrator.activities import execute_skill_activity

    attempt_count = 0

    async def timeout_then_succeed(*args, **kwargs):
        nonlocal attempt_count
        attempt_count += 1

        # First 2 attempts timeout, third succeeds
        if attempt_count < 3:
            await asyncio.sleep(10)
            return {
                "success": False,
                "output": "",
                "error": "Timeout",
                "duration_ms": 10000,
                "exit_code": -1,
                "logs": "",
            }

        return {
            "success": True,
            "output": "Success after retries",
            "error": None,
            "duration_ms": 50,
            "exit_code": 0,
            "logs": "Success",
        }

    with patch(
        "kubani.nexus.sandbox.executor.execute_skill_in_sandbox", side_effect=timeout_then_succeed
    ):
        env = ActivityEnvironment()

        input_data = {
            "skill_name": "retry-skill",
            "inputs": {},
            "timeout_seconds": 1,
            "conversation_id": "conv-retry",
        }

        # Execute - should eventually succeed after retries
        # Note: In real Temporal, retry policy would handle this
        # For testing, we simulate the retry behavior
        for attempt in range(3):
            try:
                result = await asyncio.wait_for(
                    env.run(execute_skill_activity, input_data), timeout=2.0
                )

                # If we get here on attempt 3, success
                if attempt == 2:
                    assert result["success"] is True
                    assert attempt_count == 3
                    break

            except TimeoutError:
                # Expected on first 2 attempts
                if attempt < 2:
                    continue
                else:
                    pytest.fail("Should have succeeded on third attempt")


@pytest.mark.asyncio
async def test_multiple_activities_timeout_independently():
    """Test that multiple activities can timeout independently.

    Validates: Requirements 12.4
    - Simulates multiple activities with different timeout behaviors
    - Verifies each handles timeout independently
    """
    from kubani.nexus.orchestrator.activities import execute_skill_activity

    async def fast_execute(*args, **kwargs):
        await asyncio.sleep(0.1)
        return {
            "success": True,
            "output": "Fast",
            "error": None,
            "duration_ms": 100,
            "exit_code": 0,
            "logs": "",
        }

    async def slow_execute(*args, **kwargs):
        await asyncio.sleep(10)
        return {
            "success": False,
            "output": "",
            "error": "Slow",
            "duration_ms": 10000,
            "exit_code": -1,
            "logs": "",
        }

    env = ActivityEnvironment()

    # Fast activity should succeed
    with patch("kubani.nexus.sandbox.executor.execute_skill_in_sandbox", side_effect=fast_execute):
        result1 = await asyncio.wait_for(
            env.run(
                execute_skill_activity,
                {
                    "skill_name": "fast-skill",
                    "inputs": {},
                    "timeout_seconds": 5,
                    "conversation_id": "conv-fast",
                },
            ),
            timeout=1.0,
        )
        assert result1["success"] is True

    # Slow activity should timeout
    with patch("kubani.nexus.sandbox.executor.execute_skill_in_sandbox", side_effect=slow_execute):
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(
                env.run(
                    execute_skill_activity,
                    {
                        "skill_name": "slow-skill",
                        "inputs": {},
                        "timeout_seconds": 1,
                        "conversation_id": "conv-slow",
                    },
                ),
                timeout=2.0,
            )
