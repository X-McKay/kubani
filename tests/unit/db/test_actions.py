"""Unit tests for Nexus database action logging operations.

These tests use mocked database pools to validate the action logging
operations without requiring a live database connection.

Tests cover:
- log_action_start: Logging the start of an agent action
- log_action_complete: Logging the completion of an agent action
"""

import pytest
from unittest.mock import AsyncMock

# Import the db_pool_mock fixture
pytest_plugins = ['tests.fixtures.mocks']

from kubani.nexus.db import (
    log_action_start,
    log_action_complete,
)


# =========================================================================
# Test: log_action_start
# =========================================================================


@pytest.mark.asyncio
async def test_log_action_start_returns_action_id(db_pool_mock):
    """Test that log_action_start inserts an action and returns the action ID.
    
    **Validates: Requirements 2.4**
    
    This test verifies:
    1. The correct SQL INSERT is executed
    2. The action_id is returned from the database
    3. The status is set to 'started'
    4. All parameters are passed correctly
    """
    # Arrange
    conversation_id = "conv-123"
    action_type = "skill_execution"
    description = "Fetching URL"
    input_summary = "web/fetch-url"
    expected_action_id = 42
    
    # Mock the database to return an action ID
    db_pool_mock.fetchval = AsyncMock(return_value=expected_action_id)
    
    # Act
    action_id = await log_action_start(
        db_pool_mock,
        conversation_id,
        action_type,
        description,
        input_summary
    )
    
    # Assert
    assert action_id == expected_action_id
    
    # Verify the SQL was executed with correct parameters
    db_pool_mock.fetchval.assert_called_once()
    call_args = db_pool_mock.fetchval.call_args
    
    # Check the SQL query
    sql = call_args[0][0]
    assert "INSERT INTO agent_actions" in sql
    assert "RETURNING id" in sql
    assert "'started'" in sql or "status" in sql  # Status should be 'started'
    
    # Check the parameters
    params = call_args[0][1:]
    assert params[0] == conversation_id
    assert params[1] == action_type
    assert params[2] == description
    assert params[3] == input_summary


@pytest.mark.asyncio
async def test_log_action_start_with_empty_input_summary(db_pool_mock):
    """Test that log_action_start handles empty input_summary correctly."""
    # Arrange
    conversation_id = "conv-456"
    action_type = "planning"
    description = "Creating execution plan"
    input_summary = ""  # Empty string
    expected_action_id = 99
    
    db_pool_mock.fetchval = AsyncMock(return_value=expected_action_id)
    
    # Act
    action_id = await log_action_start(
        db_pool_mock,
        conversation_id,
        action_type,
        description,
        input_summary
    )
    
    # Assert
    assert action_id == expected_action_id
    
    # Verify input_summary parameter is empty string
    call_args = db_pool_mock.fetchval.call_args
    params = call_args[0][1:]
    assert params[3] == ""


@pytest.mark.asyncio
async def test_log_action_start_with_default_input_summary(db_pool_mock):
    """Test that log_action_start uses default empty string for input_summary."""
    # Arrange
    conversation_id = "conv-789"
    action_type = "response_generation"
    description = "Generating response"
    expected_action_id = 123
    
    db_pool_mock.fetchval = AsyncMock(return_value=expected_action_id)
    
    # Act - Don't pass input_summary, use default
    action_id = await log_action_start(
        db_pool_mock,
        conversation_id,
        action_type,
        description
    )
    
    # Assert
    assert action_id == expected_action_id
    
    # Verify default input_summary is empty string
    call_args = db_pool_mock.fetchval.call_args
    params = call_args[0][1:]
    assert params[3] == ""


# =========================================================================
# Test: log_action_complete
# =========================================================================


@pytest.mark.asyncio
async def test_log_action_complete_with_error(db_pool_mock):
    """Test that log_action_complete sets status to 'failed' when error_message is provided.
    
    **Validates: Requirements 2.5**
    
    This test verifies:
    1. The correct SQL UPDATE is executed
    2. The status is set to 'failed' when error_message is provided
    3. All parameters are passed correctly
    """
    # Arrange
    action_id = 42
    output_summary = ""
    error_message = "Connection timeout"
    duration_ms = 5000
    
    # Mock the database execute
    db_pool_mock.execute = AsyncMock(return_value="UPDATE 1")
    
    # Act
    await log_action_complete(
        db_pool_mock,
        action_id,
        output_summary,
        error_message,
        duration_ms
    )
    
    # Assert
    db_pool_mock.execute.assert_called_once()
    call_args = db_pool_mock.execute.call_args
    
    # Check the SQL query
    sql = call_args[0][0]
    assert "UPDATE agent_actions" in sql
    assert "status" in sql
    assert "completed_at" in sql
    assert "NOW()" in sql
    
    # Check the parameters
    params = call_args[0][1:]
    assert params[0] == "failed"  # Status should be 'failed'
    assert params[1] == output_summary
    assert params[2] == error_message
    assert params[3] == duration_ms
    assert params[4] == action_id


@pytest.mark.asyncio
async def test_log_action_complete_without_error(db_pool_mock):
    """Test that log_action_complete sets status to 'completed' when no error."""
    # Arrange
    action_id = 99
    output_summary = "Successfully fetched data"
    error_message = None
    duration_ms = 1500
    
    db_pool_mock.execute = AsyncMock(return_value="UPDATE 1")
    
    # Act
    await log_action_complete(
        db_pool_mock,
        action_id,
        output_summary,
        error_message,
        duration_ms
    )
    
    # Assert
    call_args = db_pool_mock.execute.call_args
    params = call_args[0][1:]
    assert params[0] == "completed"  # Status should be 'completed'
    assert params[1] == output_summary
    assert params[2] is None  # No error message
    assert params[3] == duration_ms


@pytest.mark.asyncio
async def test_log_action_complete_with_default_values(db_pool_mock):
    """Test that log_action_complete handles default parameter values."""
    # Arrange
    action_id = 123
    
    db_pool_mock.execute = AsyncMock(return_value="UPDATE 1")
    
    # Act - Use all default values
    await log_action_complete(db_pool_mock, action_id)
    
    # Assert
    call_args = db_pool_mock.execute.call_args
    params = call_args[0][1:]
    assert params[0] == "completed"  # Status should be 'completed' (no error)
    assert params[1] == ""  # Default output_summary
    assert params[2] is None  # Default error_message
    assert params[3] == 0  # Default duration_ms


@pytest.mark.asyncio
async def test_log_action_complete_with_empty_error_message(db_pool_mock):
    """Test that log_action_complete treats empty string as no error."""
    # Arrange
    action_id = 456
    output_summary = "Done"
    error_message = ""  # Empty string, not None
    duration_ms = 2000
    
    db_pool_mock.execute = AsyncMock(return_value="UPDATE 1")
    
    # Act
    await log_action_complete(
        db_pool_mock,
        action_id,
        output_summary,
        error_message,
        duration_ms
    )
    
    # Assert
    call_args = db_pool_mock.execute.call_args
    params = call_args[0][1:]
    # Empty string is falsy, so status should be 'completed'
    assert params[0] == "completed"
    assert params[2] == ""
