"""Tests for database connection loss error handling.

This module tests that the system properly handles database disconnections
and attempts to reconnect.

Requirements: 12.2
"""

from unittest.mock import AsyncMock, patch

import asyncpg
import pytest
from temporalio.testing import ActivityEnvironment


@pytest.mark.asyncio
async def test_persist_message_database_reconnect():
    """Test that persist_message reconnects on database failure.

    Validates: Requirements 12.2
    - Simulates database disconnection
    - Verifies reconnection attempt
    """
    from kubani.nexus.orchestrator.activities import persist_message

    attempt_count = 0

    async def create_pool_with_retry(db_url):
        nonlocal attempt_count
        attempt_count += 1

        # Fail first attempt, succeed on second
        if attempt_count == 1:
            raise asyncpg.exceptions.CannotConnectNowError("Database unavailable")

        # Return mock pool on second attempt
        pool = AsyncMock()
        pool.close = AsyncMock()

        # Mock ensure_conversation
        with patch("kubani.nexus.db.ensure_conversation", AsyncMock()):
            # Mock save_message
            with patch(
                "kubani.nexus.db.save_message",
                AsyncMock(return_value="msg-123"),
            ):
                return pool

    with patch("kubani.nexus.db.create_pool", side_effect=create_pool_with_retry):
        env = ActivityEnvironment()

        input_data = {
            "conversation_id": "conv-123",
            "user_id": "user-456",
            "role": "user",
            "content": "Hello",
            "source": "test",
        }

        # Execute activity - should retry and succeed
        result = await env.run(persist_message, input_data)

        # Verify reconnection occurred
        assert attempt_count == 2, f"Expected 2 connection attempts, got {attempt_count}"

        # Verify message was saved
        assert result["message_id"] == "msg-123"


@pytest.mark.asyncio
async def test_persist_message_connection_pool_exhausted():
    """Test handling of connection pool exhaustion.

    Validates: Requirements 12.2
    - Simulates connection pool exhaustion
    - Verifies retry behavior
    """
    from kubani.nexus.orchestrator.activities import persist_message

    attempt_count = 0

    async def create_pool_with_exhaustion(db_url):
        nonlocal attempt_count
        attempt_count += 1

        # Fail first 2 attempts with pool exhaustion
        if attempt_count < 3:
            raise asyncpg.exceptions.TooManyConnectionsError("Connection pool exhausted")

        # Return mock pool on third attempt
        pool = AsyncMock()
        pool.close = AsyncMock()

        with (
            patch("kubani.nexus.db.ensure_conversation", AsyncMock()),
            patch(
                "kubani.nexus.db.save_message",
                AsyncMock(return_value="msg-456"),
            ),
        ):
            return pool

    with patch("kubani.nexus.db.create_pool", side_effect=create_pool_with_exhaustion):
        env = ActivityEnvironment()

        input_data = {
            "conversation_id": "conv-789",
            "user_id": "user-101",
            "role": "assistant",
            "content": "Response",
            "source": "test",
        }

        # Execute activity - should retry and succeed
        result = await env.run(persist_message, input_data)

        # Verify retries occurred
        assert attempt_count == 3, f"Expected 3 connection attempts, got {attempt_count}"

        # Verify message was saved
        assert result["message_id"] == "msg-456"


@pytest.mark.asyncio
async def test_log_action_database_connection_loss():
    """Test that log_action_activity handles database connection loss.

    Validates: Requirements 12.2
    - Simulates database connection loss during action logging
    - Verifies reconnection and retry
    """
    from kubani.nexus.orchestrator.activities import log_action_activity

    attempt_count = 0

    async def create_pool_with_intermittent_failure(db_url):
        nonlocal attempt_count
        attempt_count += 1

        # Fail first attempt
        if attempt_count == 1:
            raise asyncpg.exceptions.ConnectionDoesNotExistError("Connection lost")

        # Return mock pool on second attempt
        pool = AsyncMock()
        pool.close = AsyncMock()

        with patch("kubani.nexus.db.log_action_start", AsyncMock(return_value=42)):
            return pool

    with patch("kubani.nexus.db.create_pool", side_effect=create_pool_with_intermittent_failure):
        env = ActivityEnvironment()

        input_data = {
            "conversation_id": "conv-999",
            "action_type": "skill_execution",
            "description": "Test action",
            "input_summary": "Test input",
        }

        # Execute activity - should retry and succeed
        result = await env.run(log_action_activity, input_data)

        # Verify reconnection occurred
        assert attempt_count == 2, f"Expected 2 connection attempts, got {attempt_count}"

        # Verify action was logged
        assert result["action_id"] == 42


@pytest.mark.asyncio
async def test_database_query_timeout_retry():
    """Test that database query timeouts trigger retry.

    Validates: Requirements 12.2
    - Simulates query timeout
    - Verifies retry with new connection
    """
    from kubani.nexus.orchestrator.activities import persist_message

    call_count = 0

    async def mock_save_message(pool, *args, **kwargs):
        nonlocal call_count
        call_count += 1

        # Timeout on first call, succeed on second
        if call_count == 1:
            raise asyncpg.exceptions.QueryCanceledError("Query timeout")

        return "msg-timeout-test"

    # Create a mock pool that doesn't fail on creation
    mock_pool = AsyncMock()
    mock_pool.close = AsyncMock()

    with patch("kubani.nexus.db.create_pool", AsyncMock(return_value=mock_pool)):
        with patch("kubani.nexus.db.ensure_conversation", AsyncMock()):
            with patch("kubani.nexus.db.save_message", side_effect=mock_save_message):
                env = ActivityEnvironment()

                input_data = {
                    "conversation_id": "conv-timeout",
                    "user_id": "user-timeout",
                    "role": "user",
                    "content": "Test timeout",
                    "source": "test",
                }

                # Execute activity - should retry and succeed
                result = await env.run(persist_message, input_data)

                # Verify retry occurred
                assert call_count == 2, f"Expected 2 query attempts, got {call_count}"

                # Verify message was saved
                assert result["message_id"] == "msg-timeout-test"


@pytest.mark.asyncio
async def test_database_permanent_failure():
    """Test graceful failure when database is permanently unavailable.

    Validates: Requirements 12.2
    - Simulates permanent database failure
    - Verifies graceful error handling after max retries
    """
    from kubani.nexus.orchestrator.activities import persist_message

    attempt_count = 0

    async def always_failing_create_pool(db_url):
        nonlocal attempt_count
        attempt_count += 1
        raise asyncpg.exceptions.CannotConnectNowError("Database permanently down")

    with patch("kubani.nexus.db.create_pool", side_effect=always_failing_create_pool):
        env = ActivityEnvironment()

        input_data = {
            "conversation_id": "conv-fail",
            "user_id": "user-fail",
            "role": "user",
            "content": "This will fail",
            "source": "test",
        }

        # Execute activity - should fail after retries
        with pytest.raises(asyncpg.exceptions.CannotConnectNowError):
            await env.run(persist_message, input_data)

        # Verify multiple attempts were made
        assert attempt_count >= 2, f"Expected at least 2 attempts, got {attempt_count}"
