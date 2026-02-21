"""Tests for skill execution crash error handling.

This module tests that the system properly handles skill execution crashes
and marks steps as failed with appropriate error messages.

Requirements: 12.5
"""

from unittest.mock import patch

import pytest
from temporalio.testing import ActivityEnvironment


@pytest.mark.asyncio
async def test_execute_skill_with_exception():
    """Test that skill execution exceptions are captured properly.

    Validates: Requirements 12.5
    - Creates skill that raises exception
    - Verifies error is captured and step marked as failed
    """
    from kubani.nexus.orchestrator.activities import execute_skill_activity

    # Mock skill execution that raises exception
    async def crashing_skill(*args, **kwargs):
        raise RuntimeError("Skill crashed unexpectedly")

    with patch(
        "kubani.nexus.sandbox.executor.execute_skill_in_sandbox", side_effect=crashing_skill
    ):
        env = ActivityEnvironment()

        input_data = {
            "skill_name": "crashing-skill",
            "inputs": {"param": "value"},
            "timeout_seconds": 10,
            "conversation_id": "conv-crash",
        }

        # Execute activity - should capture exception
        result = await env.run(execute_skill_activity, input_data)

        # Verify error was captured
        assert result["success"] is False
        assert result["error"] is not None
        assert "crashed unexpectedly" in result["error"]
        assert result["exit_code"] == -1


@pytest.mark.asyncio
async def test_execute_skill_with_syntax_error():
    """Test that skill syntax errors are captured.

    Validates: Requirements 12.5
    - Creates skill with syntax error
    - Verifies error is captured with details
    """
    from kubani.nexus.models import SkillExecutionResult
    from kubani.nexus.orchestrator.activities import execute_skill_activity

    # Mock skill execution that returns syntax error
    async def syntax_error_skill(*args, **kwargs):
        return SkillExecutionResult(
            success=False,
            output="",
            error="SyntaxError: invalid syntax at line 5",
            duration_ms=10,
            exit_code=1,
            logs="Traceback...",
            skill_name="test-skill",
        )

    with patch(
        "kubani.nexus.sandbox.executor.execute_skill_in_sandbox", side_effect=syntax_error_skill
    ):
        env = ActivityEnvironment()

        input_data = {
            "skill_name": "syntax-error-skill",
            "inputs": {},
            "timeout_seconds": 10,
            "conversation_id": "conv-syntax",
        }

        # Execute activity
        result = await env.run(execute_skill_activity, input_data)

        # Verify syntax error was captured
        assert result["success"] is False
        assert "SyntaxError" in result["error"]
        assert "invalid syntax" in result["error"]
        assert result["exit_code"] == 1


@pytest.mark.asyncio
async def test_execute_skill_with_import_error():
    """Test that skill import errors are captured.

    Validates: Requirements 12.5
    - Creates skill with missing import
    - Verifies error is captured
    """
    from kubani.nexus.models import SkillExecutionResult
    from kubani.nexus.orchestrator.activities import execute_skill_activity

    # Mock skill execution that returns import error
    async def import_error_skill(*args, **kwargs):
        return SkillExecutionResult(
            success=False,
            output="",
            error="ImportError: No module named 'nonexistent_module'",
            duration_ms=50,
            exit_code=1,
            logs="",
            skill_name="test-skill",
        )

    with patch(
        "kubani.nexus.sandbox.executor.execute_skill_in_sandbox", side_effect=import_error_skill
    ):
        env = ActivityEnvironment()

        input_data = {
            "skill_name": "import-error-skill",
            "inputs": {},
            "timeout_seconds": 10,
            "conversation_id": "conv-import",
        }

        # Execute activity
        result = await env.run(execute_skill_activity, input_data)

        # Verify import error was captured
        assert result["success"] is False
        assert "ImportError" in result["error"]
        assert "nonexistent_module" in result["error"]


@pytest.mark.asyncio
async def test_execute_skill_with_runtime_error():
    """Test that skill runtime errors are captured.

    Validates: Requirements 12.5
    - Creates skill that fails during execution
    - Verifies error details are preserved
    """
    from kubani.nexus.models import SkillExecutionResult
    from kubani.nexus.orchestrator.activities import execute_skill_activity

    # Mock skill execution that returns runtime error
    async def runtime_error_skill(*args, **kwargs):
        return SkillExecutionResult(
            success=False,
            output="Partial output before crash",
            error="ZeroDivisionError: division by zero",
            duration_ms=200,
            exit_code=1,
            logs="Traceback (most recent call last):\n  File...",
            skill_name="test-skill",
        )

    with patch(
        "kubani.nexus.sandbox.executor.execute_skill_in_sandbox", side_effect=runtime_error_skill
    ):
        env = ActivityEnvironment()

        input_data = {
            "skill_name": "runtime-error-skill",
            "inputs": {"divisor": 0},
            "timeout_seconds": 10,
            "conversation_id": "conv-runtime",
        }

        # Execute activity
        result = await env.run(execute_skill_activity, input_data)

        # Verify runtime error was captured
        assert result["success"] is False
        assert "ZeroDivisionError" in result["error"]
        assert result["output"] == "Partial output before crash"
        assert len(result["logs"]) > 0


@pytest.mark.asyncio
async def test_execute_skill_with_segfault():
    """Test that skill segmentation faults are captured.

    Validates: Requirements 12.5
    - Simulates skill that causes segfault
    - Verifies error is captured
    """
    from kubani.nexus.models import SkillExecutionResult
    from kubani.nexus.orchestrator.activities import execute_skill_activity

    # Mock skill execution that returns segfault
    async def segfault_skill(*args, **kwargs):
        return SkillExecutionResult(
            success=False,
            output="",
            error="Segmentation fault (core dumped)",
            duration_ms=100,
            exit_code=139,  # Standard segfault exit code
            logs="",
            skill_name="test-skill",
        )

    with patch(
        "kubani.nexus.sandbox.executor.execute_skill_in_sandbox", side_effect=segfault_skill
    ):
        env = ActivityEnvironment()

        input_data = {
            "skill_name": "segfault-skill",
            "inputs": {},
            "timeout_seconds": 10,
            "conversation_id": "conv-segfault",
        }

        # Execute activity
        result = await env.run(execute_skill_activity, input_data)

        # Verify segfault was captured
        assert result["success"] is False
        assert "Segmentation fault" in result["error"]
        assert result["exit_code"] == 139


@pytest.mark.asyncio
async def test_execute_skill_with_memory_error():
    """Test that skill memory errors are captured.

    Validates: Requirements 12.5
    - Simulates skill that runs out of memory
    - Verifies error is captured
    """
    from kubani.nexus.models import SkillExecutionResult
    from kubani.nexus.orchestrator.activities import execute_skill_activity

    # Mock skill execution that returns memory error
    async def memory_error_skill(*args, **kwargs):
        return SkillExecutionResult(
            success=False,
            output="",
            error="MemoryError: Unable to allocate memory",
            duration_ms=5000,
            exit_code=1,
            logs="",
            skill_name="test-skill",
        )

    with patch(
        "kubani.nexus.sandbox.executor.execute_skill_in_sandbox", side_effect=memory_error_skill
    ):
        env = ActivityEnvironment()

        input_data = {
            "skill_name": "memory-error-skill",
            "inputs": {},
            "timeout_seconds": 10,
            "conversation_id": "conv-memory",
        }

        # Execute activity
        result = await env.run(execute_skill_activity, input_data)

        # Verify memory error was captured
        assert result["success"] is False
        assert "MemoryError" in result["error"]


@pytest.mark.asyncio
async def test_execute_skill_crash_preserves_duration():
    """Test that execution duration is preserved even on crash.

    Validates: Requirements 12.5
    - Verifies duration_ms is captured for failed executions
    """
    from kubani.nexus.orchestrator.activities import execute_skill_activity

    # Mock skill that crashes but records duration
    async def crashing_skill_with_duration(*args, **kwargs):
        raise Exception("Crash after some time")

    with patch(
        "kubani.nexus.sandbox.executor.execute_skill_in_sandbox",
        side_effect=crashing_skill_with_duration,
    ):
        env = ActivityEnvironment()

        input_data = {
            "skill_name": "duration-crash-skill",
            "inputs": {},
            "timeout_seconds": 10,
            "conversation_id": "conv-duration",
        }

        # Execute activity
        result = await env.run(execute_skill_activity, input_data)

        # Verify duration was captured
        assert result["success"] is False
        assert result["duration_ms"] >= 0
        assert result["error"] is not None


@pytest.mark.asyncio
async def test_multiple_skill_crashes_handled_independently():
    """Test that multiple skill crashes are handled independently.

    Validates: Requirements 12.5
    - Executes multiple skills that crash
    - Verifies each error is captured separately
    """
    from kubani.nexus.orchestrator.activities import execute_skill_activity

    crash_count = 0

    async def different_crashes(*args, **kwargs):
        nonlocal crash_count
        crash_count += 1

        if crash_count == 1:
            raise ValueError("First crash")
        elif crash_count == 2:
            raise TypeError("Second crash")
        else:
            raise RuntimeError("Third crash")

    with patch(
        "kubani.nexus.sandbox.executor.execute_skill_in_sandbox", side_effect=different_crashes
    ):
        env = ActivityEnvironment()

        # Execute first skill
        result1 = await env.run(
            execute_skill_activity,
            {
                "skill_name": "skill-1",
                "inputs": {},
                "timeout_seconds": 10,
                "conversation_id": "conv-1",
            },
        )

        assert result1["success"] is False
        assert "First crash" in result1["error"]

        # Execute second skill
        result2 = await env.run(
            execute_skill_activity,
            {
                "skill_name": "skill-2",
                "inputs": {},
                "timeout_seconds": 10,
                "conversation_id": "conv-2",
            },
        )

        assert result2["success"] is False
        assert "Second crash" in result2["error"]

        # Execute third skill
        result3 = await env.run(
            execute_skill_activity,
            {
                "skill_name": "skill-3",
                "inputs": {},
                "timeout_seconds": 10,
                "conversation_id": "conv-3",
            },
        )

        assert result3["success"] is False
        assert "Third crash" in result3["error"]

        # Verify all three crashes were handled
        assert crash_count == 3


@pytest.mark.asyncio
async def test_skill_crash_logs_error():
    """Test that skill crashes are logged for debugging.

    Validates: Requirements 12.5
    - Verifies errors are logged when skills crash
    """
    from kubani.nexus.orchestrator.activities import execute_skill_activity

    async def crashing_skill(*args, **kwargs):
        raise Exception("Logged crash")

    with (
        patch("kubani.nexus.sandbox.executor.execute_skill_in_sandbox", side_effect=crashing_skill),
        patch("kubani.nexus.orchestrator.activities.logger") as mock_logger,
    ):
        env = ActivityEnvironment()

        input_data = {
            "skill_name": "logged-crash-skill",
            "inputs": {},
            "timeout_seconds": 10,
            "conversation_id": "conv-logged",
        }

        # Execute activity
        result = await env.run(execute_skill_activity, input_data)

        # Verify error was logged
        assert mock_logger.error.called
        error_message = mock_logger.error.call_args[0][0]
        assert "Skill execution failed" in error_message

        # Verify result indicates failure
        assert result["success"] is False
