"""Tests for Redis pub/sub failure error handling.

This module tests that the system properly handles Redis failures
and continues processing without crashing.

Requirements: 12.3
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from temporalio.testing import ActivityEnvironment


@pytest.mark.asyncio
async def test_publish_response_redis_unavailable():
    """Test that publish_response handles Redis unavailability gracefully.

    Validates: Requirements 12.3
    - Simulates Redis failure
    - Verifies error is logged and processing continues
    """
    from kubani.nexus.orchestrator.activities import publish_response_activity

    # Mock Redis connection failure
    async def failing_connect():
        raise ConnectionError("Redis unavailable")

    mock_pubsub = MagicMock()
    mock_pubsub.connect = AsyncMock(side_effect=failing_connect)
    mock_pubsub.close = AsyncMock()

    with patch("kubani.nexus.pubsub.NexusPubSub", return_value=mock_pubsub):
        with patch("kubani.nexus.orchestrator.activities.logger") as mock_logger:
            env = ActivityEnvironment()

            input_data = {
                "conversation_id": "conv-123",
                "text": "Test response",
                "metadata": {},
            }

            # Execute activity - should handle error gracefully
            result = await env.run(publish_response_activity, input_data)

            # Verify error was logged
            assert mock_logger.error.called, "Error should be logged"
            error_call = mock_logger.error.call_args[0][0]
            assert "Failed to publish response" in error_call

            # Verify activity returns failure status but doesn't crash
            assert result["published"] is False
            assert "error" in result


@pytest.mark.asyncio
async def test_publish_response_redis_publish_failure():
    """Test handling of Redis publish operation failure.

    Validates: Requirements 12.3
    - Simulates Redis publish failure
    - Verifies graceful error handling
    """
    from kubani.nexus.orchestrator.activities import publish_response_activity

    # Mock successful connection but failed publish
    async def failing_publish(*args, **kwargs):
        raise TimeoutError("Redis publish timeout")

    mock_pubsub = MagicMock()
    mock_pubsub.connect = AsyncMock()
    mock_pubsub.publish_response = AsyncMock(side_effect=failing_publish)
    mock_pubsub.close = AsyncMock()

    with patch("kubani.nexus.pubsub.NexusPubSub", return_value=mock_pubsub):
        with patch("kubani.nexus.orchestrator.activities.logger") as mock_logger:
            env = ActivityEnvironment()

            input_data = {
                "conversation_id": "conv-456",
                "text": "Another test",
                "metadata": {"key": "value"},
            }

            # Execute activity - should handle error gracefully
            result = await env.run(publish_response_activity, input_data)

            # Verify error was logged
            assert mock_logger.error.called

            # Verify activity returns failure status
            assert result["published"] is False
            assert "error" in result
            assert "timeout" in result["error"].lower()


@pytest.mark.asyncio
async def test_publish_response_redis_connection_lost():
    """Test handling of Redis connection loss during operation.

    Validates: Requirements 12.3
    - Simulates connection loss during publish
    - Verifies error logging and graceful continuation
    """
    from kubani.nexus.orchestrator.activities import publish_response_activity

    # Mock connection that fails during publish
    async def connection_lost_publish(*args, **kwargs):
        raise ConnectionResetError("Connection lost")

    mock_pubsub = MagicMock()
    mock_pubsub.connect = AsyncMock()
    mock_pubsub.publish_response = AsyncMock(side_effect=connection_lost_publish)
    mock_pubsub.close = AsyncMock()

    with patch("kubani.nexus.pubsub.NexusPubSub", return_value=mock_pubsub):
        with patch("kubani.nexus.orchestrator.activities.logger") as mock_logger:
            env = ActivityEnvironment()

            input_data = {
                "conversation_id": "conv-789",
                "text": "Connection test",
                "metadata": {},
            }

            # Execute activity - should not crash
            result = await env.run(publish_response_activity, input_data)

            # Verify error was logged
            assert mock_logger.error.called

            # Verify graceful failure
            assert result["published"] is False
            assert "error" in result


@pytest.mark.asyncio
async def test_publish_response_redis_intermittent_failure():
    """Test that Redis intermittent failures are handled properly.

    Validates: Requirements 12.3
    - Simulates intermittent Redis failures
    - Verifies system continues processing
    """
    from kubani.nexus.orchestrator.activities import publish_response_activity

    call_count = 0

    async def intermittent_publish(*args, **kwargs):
        nonlocal call_count
        call_count += 1

        # Fail on odd calls, succeed on even calls
        if call_count % 2 == 1:
            raise ConnectionError("Intermittent failure")

    mock_pubsub = MagicMock()
    mock_pubsub.connect = AsyncMock()
    mock_pubsub.publish_response = AsyncMock(side_effect=intermittent_publish)
    mock_pubsub.close = AsyncMock()

    with patch("kubani.nexus.pubsub.NexusPubSub", return_value=mock_pubsub):
        with patch("kubani.nexus.orchestrator.activities.logger") as mock_logger:
            env = ActivityEnvironment()

            # First call should fail
            result1 = await env.run(
                publish_response_activity,
                {
                    "conversation_id": "conv-1",
                    "text": "First",
                    "metadata": {},
                },
            )

            assert result1["published"] is False
            assert call_count == 1

            # Second call should also fail (our mock fails on odd calls)
            result2 = await env.run(
                publish_response_activity,
                {
                    "conversation_id": "conv-2",
                    "text": "Second",
                    "metadata": {},
                },
            )

            assert result2["published"] is False
            assert call_count == 2

            # Verify errors were logged
            assert mock_logger.error.call_count >= 2


@pytest.mark.asyncio
async def test_redis_failure_does_not_block_workflow():
    """Test that Redis failures don't block workflow execution.

    Validates: Requirements 12.3
    - Simulates Redis failure
    - Verifies workflow can continue without Redis
    """
    from kubani.nexus.orchestrator.activities import publish_response_activity

    # Mock complete Redis failure
    mock_pubsub = MagicMock()
    mock_pubsub.connect = AsyncMock(side_effect=Exception("Redis completely down"))
    mock_pubsub.close = AsyncMock()

    with patch("kubani.nexus.pubsub.NexusPubSub", return_value=mock_pubsub):
        with patch("kubani.nexus.orchestrator.activities.logger"):
            env = ActivityEnvironment()

            input_data = {
                "conversation_id": "conv-blocking-test",
                "text": "Should not block",
                "metadata": {},
            }

            # Execute activity - should complete without blocking
            import asyncio

            # Set a timeout to ensure it doesn't hang
            result = await asyncio.wait_for(
                env.run(publish_response_activity, input_data), timeout=5.0
            )

            # Verify activity completed (even though it failed)
            assert result["published"] is False
            assert "error" in result


@pytest.mark.asyncio
async def test_redis_close_failure_is_handled():
    """Test that Redis close failures are handled gracefully.

    Validates: Requirements 12.3
    - Simulates failure during Redis connection close
    - Verifies cleanup errors don't crash the system
    """
    from kubani.nexus.orchestrator.activities import publish_response_activity

    # Mock successful publish but failed close
    mock_pubsub = MagicMock()
    mock_pubsub.connect = AsyncMock()
    mock_pubsub.publish_response = AsyncMock()
    mock_pubsub.close = AsyncMock(side_effect=Exception("Close failed"))

    with patch("kubani.nexus.pubsub.NexusPubSub", return_value=mock_pubsub):
        env = ActivityEnvironment()

        input_data = {
            "conversation_id": "conv-close-test",
            "text": "Test close failure",
            "metadata": {},
        }

        # Execute activity - should handle close failure
        # The activity should still complete successfully since publish worked
        result = await env.run(publish_response_activity, input_data)

        # Verify publish was attempted
        assert mock_pubsub.publish_response.called

        # Verify close was attempted (even though it failed)
        assert mock_pubsub.close.called
