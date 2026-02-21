"""Unit tests for Nexus skill execution activity.

This module tests the execute_skill_activity which delegates skill execution
to the sandbox executor and returns the result.

Tests include:
- Successful skill execution with valid inputs
- Delegation to sandbox executor
- Result transformation and return
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from kubani.nexus.orchestrator.activities import execute_skill_activity
from kubani.nexus.models.skills import SkillExecutionResult


class TestExecuteSkillActivity:
    """Tests for execute_skill_activity."""

    @pytest.mark.asyncio
    async def test_execute_skill_activity_success(self):
        """
        Test that execute_skill_activity delegates to sandbox and returns result.
        
        When a skill is executed successfully, the activity should:
        1. Delegate to execute_skill_in_sandbox
        2. Return the result with success=True
        3. Include output, duration, and other metadata
        
        Validates: Requirements 4.4
        """
        # Prepare input data
        input_data = {
            "skill_name": "web/fetch-url",
            "skill_version": "1.0.0",
            "inputs": {
                "url": "https://example.com"
            },
            "timeout_seconds": 30,
            "conversation_id": "conv-123"
        }
        
        # Mock successful sandbox execution result
        mock_sandbox_result = SkillExecutionResult(
            skill_name="web/fetch-url",
            success=True,
            output='{"status": "success", "content": "Example Domain"}',
            error=None,
            exit_code=0,
            duration_ms=0,  # Will be set by activity
            logs="Fetching URL...\nDone."
        )
        
        # Mock the sandbox executor and activity context
        with patch('kubani.nexus.sandbox.executor.execute_skill_in_sandbox') as mock_execute, \
             patch('temporalio.activity.heartbeat') as mock_heartbeat:
            mock_execute.return_value = mock_sandbox_result
            
            # Execute the activity
            result = await execute_skill_activity(input_data)
            
            # Verify the result structure
            assert result is not None
            assert isinstance(result, dict)
            
            # Verify success status
            assert result["success"] is True
            
            # Verify output is present
            assert "output" in result
            assert result["output"] == '{"status": "success", "content": "Example Domain"}'
            
            # Verify no error
            assert result["error"] is None
            
            # Verify exit code
            assert result["exit_code"] == 0
            
            # Verify duration is present and positive
            assert "duration_ms" in result
            assert result["duration_ms"] >= 0
            
            # Verify logs are captured
            assert "logs" in result
            assert result["logs"] == "Fetching URL...\nDone."
            
            # Verify sandbox executor was called with correct parameters
            mock_execute.assert_called_once()
            call_kwargs = mock_execute.call_args[1]
            assert call_kwargs["skill_name"] == "web/fetch-url"
            assert call_kwargs["inputs"] == {"url": "https://example.com"}
            assert call_kwargs["timeout_seconds"] == 30
            
            # Verify heartbeat was called
            mock_heartbeat.assert_called_once_with("Executing skill: web/fetch-url")

    @pytest.mark.asyncio
    async def test_execute_skill_activity_failure(self):
        """
        Test that execute_skill_activity handles skill execution failures.
        
        When a skill fails to execute, the activity should:
        1. Return success=False
        2. Include error message
        3. Include exit code and logs
        
        Validates: Requirements 4.4
        """
        # Prepare input data
        input_data = {
            "skill_name": "code/analyze",
            "skill_version": "1.0.0",
            "inputs": {
                "code": "invalid python code {"
            },
            "timeout_seconds": 10,
            "conversation_id": "conv-456"
        }
        
        # Mock failed sandbox execution result
        mock_sandbox_result = SkillExecutionResult(
            skill_name="code/analyze",
            success=False,
            output="",
            error="SyntaxError: invalid syntax",
            exit_code=1,
            duration_ms=0,
            logs="Traceback (most recent call last):\n  File...\nSyntaxError: invalid syntax"
        )
        
        # Mock the sandbox executor and activity context
        with patch('kubani.nexus.sandbox.executor.execute_skill_in_sandbox') as mock_execute, \
             patch('temporalio.activity.heartbeat') as mock_heartbeat:
            mock_execute.return_value = mock_sandbox_result
            
            # Execute the activity
            result = await execute_skill_activity(input_data)
            
            # Verify failure status
            assert result["success"] is False
            
            # Verify error message is present
            assert result["error"] is not None
            assert "SyntaxError" in result["error"]
            
            # Verify exit code indicates failure
            assert result["exit_code"] == 1
            
            # Verify logs contain error details
            assert "Traceback" in result["logs"]
            
            # Verify output is empty
            assert result["output"] == ""

    @pytest.mark.asyncio
    async def test_execute_skill_activity_timeout(self):
        """
        Test that execute_skill_activity handles timeout errors.
        
        When a skill times out, the activity should:
        1. Return success=False
        2. Include timeout error message
        3. Set exit code to -1
        
        Validates: Requirements 4.4
        """
        # Prepare input data with short timeout
        input_data = {
            "skill_name": "compute/long-task",
            "skill_version": "1.0.0",
            "inputs": {
                "iterations": 1000000
            },
            "timeout_seconds": 1,
            "conversation_id": "conv-789"
        }
        
        # Mock timeout result
        mock_sandbox_result = SkillExecutionResult(
            skill_name="compute/long-task",
            success=False,
            output="",
            error="Execution timed out after 1s",
            exit_code=-1,
            duration_ms=1000,
            logs=""
        )
        
        # Mock the sandbox executor and activity context
        with patch('kubani.nexus.sandbox.executor.execute_skill_in_sandbox') as mock_execute, \
             patch('temporalio.activity.heartbeat') as mock_heartbeat:
            mock_execute.return_value = mock_sandbox_result
            
            # Execute the activity
            result = await execute_skill_activity(input_data)
            
            # Verify timeout handling
            assert result["success"] is False
            assert "timed out" in result["error"].lower()
            assert result["exit_code"] == -1

    @pytest.mark.asyncio
    async def test_execute_skill_activity_exception_handling(self):
        """
        Test that execute_skill_activity handles unexpected exceptions.
        
        When the sandbox executor raises an exception, the activity should:
        1. Catch the exception
        2. Return success=False
        3. Include error message
        4. Set exit code to -1
        
        Validates: Requirements 4.4
        """
        # Prepare input data
        input_data = {
            "skill_name": "test/skill",
            "skill_version": "1.0.0",
            "inputs": {},
            "timeout_seconds": 30,
            "conversation_id": "conv-999"
        }
        
        # Mock the sandbox executor to raise an exception
        with patch('kubani.nexus.sandbox.executor.execute_skill_in_sandbox') as mock_execute, \
             patch('temporalio.activity.heartbeat') as mock_heartbeat:
            mock_execute.side_effect = RuntimeError("Sandbox initialization failed")
            
            # Execute the activity
            result = await execute_skill_activity(input_data)
            
            # Verify exception handling
            assert result["success"] is False
            assert result["error"] is not None
            assert "Sandbox initialization failed" in result["error"]
            assert result["exit_code"] == -1
            assert result["output"] == ""

    @pytest.mark.asyncio
    async def test_execute_skill_activity_with_default_timeout(self):
        """
        Test that execute_skill_activity uses default timeout when not specified.
        
        When timeout_seconds is not provided in input_data, the activity should
        use a default value (60 seconds).
        
        Validates: Requirements 4.4
        """
        # Prepare input data without timeout
        input_data = {
            "skill_name": "test/skill",
            "inputs": {},
            "conversation_id": "conv-default"
        }
        
        # Mock successful execution
        mock_sandbox_result = SkillExecutionResult(
            skill_name="test/skill",
            success=True,
            output="success",
            error=None,
            exit_code=0,
            duration_ms=100,
            logs=""
        )
        
        # Mock the sandbox executor and activity context
        with patch('kubani.nexus.sandbox.executor.execute_skill_in_sandbox') as mock_execute, \
             patch('temporalio.activity.heartbeat') as mock_heartbeat:
            mock_execute.return_value = mock_sandbox_result
            
            # Execute the activity
            result = await execute_skill_activity(input_data)
            
            # Verify default timeout was used
            call_kwargs = mock_execute.call_args[1]
            assert call_kwargs["timeout_seconds"] == 60  # Default value

    @pytest.mark.asyncio
    async def test_execute_skill_activity_duration_measurement(self):
        """
        Test that execute_skill_activity measures execution duration.
        
        The activity should measure the total time taken for skill execution
        and include it in the result.
        
        Validates: Requirements 4.4
        """
        # Prepare input data
        input_data = {
            "skill_name": "test/skill",
            "inputs": {},
            "timeout_seconds": 30,
            "conversation_id": "conv-duration"
        }
        
        # Mock execution result (duration_ms will be overwritten by activity)
        mock_sandbox_result = SkillExecutionResult(
            skill_name="test/skill",
            success=True,
            output="result",
            error=None,
            exit_code=0,
            duration_ms=0,  # This will be set by the activity
            logs=""
        )
        
        # Mock the sandbox executor with a delay
        async def mock_execute_with_delay(**kwargs):
            import asyncio
            await asyncio.sleep(0.01)  # 10ms delay
            return mock_sandbox_result
        
        # Mock the sandbox executor and activity context
        with patch('kubani.nexus.sandbox.executor.execute_skill_in_sandbox') as mock_execute, \
             patch('temporalio.activity.heartbeat') as mock_heartbeat:
            mock_execute.side_effect = mock_execute_with_delay
            
            # Execute the activity
            result = await execute_skill_activity(input_data)
            
            # Verify duration was measured
            assert result["duration_ms"] > 0
            # Should be at least 10ms (our delay)
            assert result["duration_ms"] >= 10
