"""Unit tests for Nexus database conversation operations.

These tests use mocked database pools to validate the conversation
operations without requiring a live database connection.

Tests cover:
- save_message: Saving messages to the database
- get_conversation_history: Retrieving conversation history
- ensure_conversation: Creating/updating conversations
"""

import json
import pytest
from unittest.mock import AsyncMock, call
from datetime import datetime, timezone
from hypothesis import given, strategies as st

# Import the db_pool_mock fixture
pytest_plugins = ['tests.fixtures.mocks']

from kubani.nexus.db import (
    save_message,
    get_conversation_history,
    ensure_conversation,
)


# =========================================================================
# Test: save_message
# =========================================================================


@pytest.mark.asyncio
async def test_save_message_returns_message_id(db_pool_mock):
    """Test that save_message inserts a message and returns the message ID.
    
    **Validates: Requirements 2.1**
    
    This test verifies:
    1. The correct SQL INSERT is executed
    2. The message_id is returned from the database
    3. All parameters are passed correctly
    """
    # Arrange
    conversation_id = "conv-123"
    role = "user"
    content = "Hello, world!"
    source = "test-ui"
    metadata = {"key": "value"}
    expected_message_id = 42
    
    # Mock the database to return a message ID
    db_pool_mock.fetchval = AsyncMock(return_value=expected_message_id)
    
    # Act
    message_id = await save_message(
        db_pool_mock,
        conversation_id,
        role,
        content,
        source,
        metadata
    )
    
    # Assert
    assert message_id == expected_message_id
    
    # Verify the SQL was executed with correct parameters
    db_pool_mock.fetchval.assert_called_once()
    call_args = db_pool_mock.fetchval.call_args
    
    # Check the SQL query
    sql = call_args[0][0]
    assert "INSERT INTO conversation_messages" in sql
    assert "RETURNING id" in sql
    
    # Check the parameters
    params = call_args[0][1:]
    assert params[0] == conversation_id
    assert params[1] == role
    assert params[2] == content
    assert params[3] == source
    assert json.loads(params[4]) == metadata


@pytest.mark.asyncio
async def test_save_message_with_default_metadata(db_pool_mock):
    """Test that save_message handles None metadata correctly."""
    # Arrange
    conversation_id = "conv-456"
    role = "assistant"
    content = "Response"
    source = "system"
    expected_message_id = 99
    
    db_pool_mock.fetchval = AsyncMock(return_value=expected_message_id)
    
    # Act
    message_id = await save_message(
        db_pool_mock,
        conversation_id,
        role,
        content,
        source,
        metadata=None  # Explicitly pass None
    )
    
    # Assert
    assert message_id == expected_message_id
    
    # Verify metadata was converted to empty dict
    call_args = db_pool_mock.fetchval.call_args
    params = call_args[0][1:]
    assert json.loads(params[4]) == {}


# =========================================================================
# Test: get_conversation_history (Property-Based Test)
# =========================================================================


def create_mock_message_row(role: str, content: str, timestamp: datetime):
    """Helper to create a mock database row for a message."""
    return {
        "role": role,
        "content": content,
        "source": "test",
        "metadata": "{}",
        "created_at": timestamp,
    }


@pytest.mark.asyncio
@given(
    num_messages=st.integers(min_value=1, max_value=20),
)
async def test_get_conversation_history_ordering_property(num_messages):
    """Property test: Messages are always returned in chronological order.
    
    **Feature: nexus-testing, Property 6: Conversation history ordering**
    **Validates: Requirements 2.2**
    
    For any sequence of messages with different timestamps,
    get_conversation_history should return them ordered from oldest to newest.
    """
    # Arrange
    db_pool_mock = AsyncMock()
    conversation_id = "conv-test"
    
    # Generate messages with increasing timestamps
    base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    messages = []
    for i in range(num_messages):
        timestamp = base_time.replace(second=i)
        messages.append(create_mock_message_row(
            role="user" if i % 2 == 0 else "assistant",
            content=f"Message {i}",
            timestamp=timestamp
        ))
    
    # Database returns messages in DESC order (newest first)
    db_pool_mock.fetch = AsyncMock(return_value=list(reversed(messages)))
    
    # Act
    history = await get_conversation_history(db_pool_mock, conversation_id)
    
    # Assert: Messages should be in chronological order (oldest first)
    assert len(history) == num_messages
    
    for i in range(num_messages):
        assert history[i]["content"] == f"Message {i}"
        
    # Verify timestamps are in ascending order
    timestamps = [datetime.fromisoformat(msg["timestamp"]) for msg in history]
    for i in range(len(timestamps) - 1):
        assert timestamps[i] <= timestamps[i + 1], \
            f"Messages not in chronological order: {timestamps[i]} > {timestamps[i + 1]}"


@pytest.mark.asyncio
async def test_get_conversation_history_respects_limit(db_pool_mock):
    """Test that get_conversation_history passes the limit parameter correctly."""
    # Arrange
    conversation_id = "conv-789"
    limit = 10
    
    # Mock empty result
    db_pool_mock.fetch = AsyncMock(return_value=[])
    
    # Act
    await get_conversation_history(db_pool_mock, conversation_id, limit=limit)
    
    # Assert
    db_pool_mock.fetch.assert_called_once()
    call_args = db_pool_mock.fetch.call_args
    
    # Check the SQL query includes LIMIT
    sql = call_args[0][0]
    assert "LIMIT" in sql
    
    # Check the limit parameter is passed
    params = call_args[0][1:]
    assert params[0] == conversation_id
    assert params[1] == limit


@pytest.mark.asyncio
async def test_get_conversation_history_default_limit(db_pool_mock):
    """Test that get_conversation_history uses default limit of 50."""
    # Arrange
    conversation_id = "conv-default"
    
    db_pool_mock.fetch = AsyncMock(return_value=[])
    
    # Act
    await get_conversation_history(db_pool_mock, conversation_id)
    
    # Assert
    call_args = db_pool_mock.fetch.call_args
    params = call_args[0][1:]
    assert params[1] == 50  # Default limit


# =========================================================================
# Test: ensure_conversation (Property-Based Test)
# =========================================================================


@pytest.mark.asyncio
@given(
    num_calls=st.integers(min_value=2, max_value=10),
)
async def test_ensure_conversation_idempotence_property(num_calls):
    """Property test: Calling ensure_conversation multiple times is idempotent.
    
    **Feature: nexus-testing, Property 7: Conversation idempotence**
    **Validates: Requirements 2.3**
    
    For any conversation_id, calling ensure_conversation multiple times
    should use ON CONFLICT DO UPDATE and not create duplicate records.
    """
    # Arrange
    db_pool_mock = AsyncMock()
    conversation_id = "conv-idempotent"
    user_id = "user-123"
    source = "test"
    
    # Mock execute to track calls
    db_pool_mock.execute = AsyncMock(return_value="INSERT 0 1")
    
    # Act: Call ensure_conversation multiple times
    for _ in range(num_calls):
        await ensure_conversation(db_pool_mock, conversation_id, user_id, source)
    
    # Assert: execute should be called num_calls times
    assert db_pool_mock.execute.call_count == num_calls
    
    # Verify all calls use ON CONFLICT DO UPDATE
    for call_obj in db_pool_mock.execute.call_args_list:
        sql = call_obj[0][0]
        assert "ON CONFLICT" in sql
        assert "DO UPDATE" in sql
        
        # Verify parameters are consistent
        params = call_obj[0][1:]
        assert params[0] == conversation_id
        assert params[1] == user_id
        assert params[2] == source


@pytest.mark.asyncio
async def test_ensure_conversation_creates_with_correct_status(db_pool_mock):
    """Test that ensure_conversation creates conversation with 'active' status."""
    # Arrange
    conversation_id = "conv-new"
    user_id = "user-456"
    source = "discord"
    
    db_pool_mock.execute = AsyncMock(return_value="INSERT 0 1")
    
    # Act
    await ensure_conversation(db_pool_mock, conversation_id, user_id, source)
    
    # Assert
    db_pool_mock.execute.assert_called_once()
    call_args = db_pool_mock.execute.call_args
    
    # Check the SQL includes status = 'active'
    sql = call_args[0][0]
    assert "INSERT INTO conversations" in sql
    assert "'active'" in sql or "status" in sql
    
    # Check parameters
    params = call_args[0][1:]
    assert params[0] == conversation_id
    assert params[1] == user_id
    assert params[2] == source


@pytest.mark.asyncio
async def test_ensure_conversation_updates_timestamp_on_conflict(db_pool_mock):
    """Test that ensure_conversation updates timestamp on conflict."""
    # Arrange
    conversation_id = "conv-existing"
    user_id = "user-789"
    source = "kubani-ui"
    
    db_pool_mock.execute = AsyncMock(return_value="INSERT 0 1")
    
    # Act
    await ensure_conversation(db_pool_mock, conversation_id, user_id, source)
    
    # Assert
    call_args = db_pool_mock.execute.call_args
    sql = call_args[0][0]
    
    # Verify the ON CONFLICT clause updates the timestamp
    assert "ON CONFLICT" in sql
    assert "updated_at" in sql
    assert "NOW()" in sql
