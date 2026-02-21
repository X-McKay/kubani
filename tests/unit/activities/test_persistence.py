"""Unit tests for Nexus persistence activities.

This module tests the persistence activities that handle database and pub/sub
operations for the Nexus orchestrator.

Tests include:
- persist_message: Saving messages to PostgreSQL
- publish_response_activity: Publishing responses via Redis pub/sub
"""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from kubani.nexus.orchestrator.activities import (
    persist_message,
    publish_response_activity,
)


class TestPersistMessage:
    """Tests for persist_message activity."""

    @pytest.mark.asyncio
    async def test_persist_message_saves_and_returns_id(self):
        """
        Test that persist_message saves message to database and returns message_id.
        
        When persist_message is called with valid message data, it should:
        1. Ensure the conversation exists
        2. Save the message to the database
        3. Return the message_id
        
        Validates: Requirements 4.6
        """
        # Prepare input data
        input_data = {
            "conversation_id": "conv-123",
            "user_id": "user-456",
            "role": "user",
            "content": "Hello, how can you help me?",
            "source": "kubani-ui"
        }
        
        # Mock database pool
        mock_pool = AsyncMock()
        mock_pool.execute = AsyncMock(return_value="INSERT 0 1")
        mock_pool.fetchval = AsyncMock(return_value=789)  # message_id
        mock_pool.close = AsyncMock()
        
        # Mock create_pool to return our mock pool
        with patch('kubani.nexus.db.create_pool', AsyncMock(return_value=mock_pool)):
            # Execute the activity
            result = await persist_message(input_data)
            
            # Verify the result
            assert result is not None
            assert isinstance(result, dict)
            assert "message_id" in result
            assert result["message_id"] == 789
            
            # Verify ensure_conversation was called
            mock_pool.execute.assert_called_once()
            execute_call = mock_pool.execute.call_args
            assert "INSERT INTO conversations" in execute_call[0][0]
            assert execute_call[0][1] == "conv-123"
            assert execute_call[0][2] == "user-456"
            assert execute_call[0][3] == "kubani-ui"
            
            # Verify save_message was called
            mock_pool.fetchval.assert_called_once()
            fetchval_call = mock_pool.fetchval.call_args
            assert "INSERT INTO conversation_messages" in fetchval_call[0][0]
            assert fetchval_call[0][1] == "conv-123"
            assert fetchval_call[0][2] == "user"
            assert fetchval_call[0][3] == "Hello, how can you help me?"
            assert fetchval_call[0][4] == "kubani-ui"
            
            # Verify pool was closed
            mock_pool.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_persist_message_with_assistant_role(self):
        """
        Test that persist_message correctly handles assistant messages.
        
        Validates: Requirements 4.6
        """
        # Prepare input data for assistant message
        input_data = {
            "conversation_id": "conv-789",
            "user_id": "user-123",
            "role": "assistant",
            "content": "I can help you with various tasks.",
            "source": "nexus-orchestrator"
        }
        
        # Mock database pool
        mock_pool = AsyncMock()
        mock_pool.execute = AsyncMock(return_value="INSERT 0 1")
        mock_pool.fetchval = AsyncMock(return_value=456)
        mock_pool.close = AsyncMock()
        
        # Mock create_pool
        with patch('kubani.nexus.db.create_pool', AsyncMock(return_value=mock_pool)):
            # Execute the activity
            result = await persist_message(input_data)
            
            # Verify message_id is returned
            assert result["message_id"] == 456
            
            # Verify role was set correctly
            fetchval_call = mock_pool.fetchval.call_args
            assert fetchval_call[0][2] == "assistant"

    @pytest.mark.asyncio
    async def test_persist_message_with_default_values(self):
        """
        Test that persist_message uses default values when optional fields are missing.
        
        Validates: Requirements 4.6
        """
        # Prepare minimal input data (missing user_id and source)
        input_data = {
            "conversation_id": "conv-minimal",
            "role": "user",
            "content": "Test message"
        }
        
        # Mock database pool
        mock_pool = AsyncMock()
        mock_pool.execute = AsyncMock(return_value="INSERT 0 1")
        mock_pool.fetchval = AsyncMock(return_value=999)
        mock_pool.close = AsyncMock()
        
        # Mock create_pool
        with patch('kubani.nexus.db.create_pool', AsyncMock(return_value=mock_pool)):
            # Execute the activity
            result = await persist_message(input_data)
            
            # Verify message_id is returned
            assert result["message_id"] == 999
            
            # Verify default values were used
            execute_call = mock_pool.execute.call_args
            assert execute_call[0][2] == "system"  # default user_id
            assert execute_call[0][3] == "kubani-ui"  # default source
            
            fetchval_call = mock_pool.fetchval.call_args
            assert fetchval_call[0][4] == "kubani-ui"  # default source

    @pytest.mark.asyncio
    async def test_persist_message_uses_environment_db_url(self):
        """
        Test that persist_message reads database URL from environment.
        
        Validates: Requirements 4.6
        """
        # Prepare input data
        input_data = {
            "conversation_id": "conv-env",
            "role": "user",
            "content": "Test",
            "user_id": "user-1"
        }
        
        # Mock database pool
        mock_pool = AsyncMock()
        mock_pool.execute = AsyncMock(return_value="INSERT 0 1")
        mock_pool.fetchval = AsyncMock(return_value=111)
        mock_pool.close = AsyncMock()
        
        # Mock create_pool and environment
        with patch('kubani.nexus.db.create_pool', AsyncMock(return_value=mock_pool)) as mock_create_pool, \
             patch.dict('os.environ', {'NEXUS_DATABASE_URL': 'postgresql://test:test@testhost:5432/testdb'}):
            
            # Execute the activity
            result = await persist_message(input_data)
            
            # Verify create_pool was called with the environment URL
            mock_create_pool.assert_called_once_with('postgresql://test:test@testhost:5432/testdb')
            
            # Verify message was saved
            assert result["message_id"] == 111


class TestPublishResponseActivity:
    """Tests for publish_response_activity."""

    @pytest.mark.asyncio
    async def test_publish_response_publishes_to_correct_channel(self):
        """
        Test that publish_response_activity publishes message to correct Redis channel.
        
        When publish_response_activity is called, it should:
        1. Connect to Redis
        2. Create an AgentMessage
        3. Publish to the conversation-specific channel
        4. Return published: True
        
        Validates: Requirements 4.7
        """
        # Prepare input data
        input_data = {
            "conversation_id": "conv-abc",
            "text": "Here is your response!",
            "metadata": {"source": "nexus", "version": "1.0"}
        }
        
        # Mock Redis client
        mock_redis = AsyncMock()
        mock_redis.publish = AsyncMock(return_value=1)  # 1 subscriber
        mock_redis.aclose = AsyncMock()
        
        # Mock NexusPubSub
        mock_pubsub = MagicMock()
        mock_pubsub.connect = AsyncMock()
        mock_pubsub.publish_response = AsyncMock()
        mock_pubsub.close = AsyncMock()
        
        # Mock the NexusPubSub class
        with patch('kubani.nexus.pubsub.NexusPubSub', return_value=mock_pubsub):
            # Execute the activity
            result = await publish_response_activity(input_data)
            
            # Verify the result
            assert result is not None
            assert isinstance(result, dict)
            assert "published" in result
            assert result["published"] is True
            
            # Verify NexusPubSub was created with correct Redis URL
            # (default or from environment)
            
            # Verify connect was called
            mock_pubsub.connect.assert_called_once()
            
            # Verify publish_response was called with correct parameters
            mock_pubsub.publish_response.assert_called_once()
            call_args = mock_pubsub.publish_response.call_args
            assert call_args[0][0] == "conv-abc"  # conversation_id
            
            # Verify the message dict was passed
            message_dict = call_args[0][1]
            assert isinstance(message_dict, dict)
            assert message_dict["conversation_id"] == "conv-abc"
            assert message_dict["text"] == "Here is your response!"
            assert message_dict["metadata"] == {"source": "nexus", "version": "1.0"}
            
            # Verify close was called
            mock_pubsub.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_response_with_minimal_data(self):
        """
        Test that publish_response_activity works with minimal input data.
        
        Validates: Requirements 4.7
        """
        # Prepare minimal input data (no metadata)
        input_data = {
            "conversation_id": "conv-minimal",
            "text": "Simple response"
        }
        
        # Mock NexusPubSub
        mock_pubsub = MagicMock()
        mock_pubsub.connect = AsyncMock()
        mock_pubsub.publish_response = AsyncMock()
        mock_pubsub.close = AsyncMock()
        
        # Mock the NexusPubSub class
        with patch('kubani.nexus.pubsub.NexusPubSub', return_value=mock_pubsub):
            # Execute the activity
            result = await publish_response_activity(input_data)
            
            # Verify published successfully
            assert result["published"] is True
            
            # Verify message was published with empty metadata
            call_args = mock_pubsub.publish_response.call_args
            message_dict = call_args[0][1]
            assert message_dict["metadata"] == {}

    @pytest.mark.asyncio
    async def test_publish_response_handles_redis_error(self):
        """
        Test that publish_response_activity handles Redis errors gracefully.
        
        When Redis publish fails, the activity should:
        1. Log the error
        2. Return published: False with error message
        
        Validates: Requirements 4.7
        """
        # Prepare input data
        input_data = {
            "conversation_id": "conv-error",
            "text": "This will fail"
        }
        
        # Mock NexusPubSub that raises an error
        mock_pubsub = MagicMock()
        mock_pubsub.connect = AsyncMock()
        mock_pubsub.publish_response = AsyncMock(side_effect=Exception("Redis connection failed"))
        mock_pubsub.close = AsyncMock()
        
        # Mock the NexusPubSub class
        with patch('kubani.nexus.pubsub.NexusPubSub', return_value=mock_pubsub):
            # Execute the activity
            result = await publish_response_activity(input_data)
            
            # Verify error was handled gracefully
            assert result is not None
            assert isinstance(result, dict)
            assert "published" in result
            assert result["published"] is False
            
            # Verify error message is included
            assert "error" in result
            assert "Redis connection failed" in result["error"]
            
            # Verify close was still called
            mock_pubsub.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_response_uses_environment_redis_url(self):
        """
        Test that publish_response_activity reads Redis URL from environment.
        
        Validates: Requirements 4.7
        """
        # Prepare input data
        input_data = {
            "conversation_id": "conv-env",
            "text": "Test message"
        }
        
        # Mock NexusPubSub
        mock_pubsub = MagicMock()
        mock_pubsub.connect = AsyncMock()
        mock_pubsub.publish_response = AsyncMock()
        mock_pubsub.close = AsyncMock()
        
        # Mock the NexusPubSub class
        with patch('kubani.nexus.pubsub.NexusPubSub') as MockNexusPubSub, \
             patch.dict('os.environ', {'REDIS_URL': 'redis://testhost:6379/1'}):
            
            MockNexusPubSub.return_value = mock_pubsub
            
            # Execute the activity
            result = await publish_response_activity(input_data)
            
            # Verify NexusPubSub was created with the environment URL
            MockNexusPubSub.assert_called_once_with(redis_url='redis://testhost:6379/1')
            
            # Verify message was published
            assert result["published"] is True

    @pytest.mark.asyncio
    async def test_publish_response_creates_agent_message(self):
        """
        Test that publish_response_activity creates proper AgentMessage.
        
        The activity should create an AgentMessage with:
        - conversation_id
        - text
        - metadata
        - auto-generated timestamp
        
        Validates: Requirements 4.7
        """
        # Prepare input data
        input_data = {
            "conversation_id": "conv-msg",
            "text": "Agent response text",
            "metadata": {"key": "value"}
        }
        
        # Mock NexusPubSub
        mock_pubsub = MagicMock()
        mock_pubsub.connect = AsyncMock()
        mock_pubsub.publish_response = AsyncMock()
        mock_pubsub.close = AsyncMock()
        
        # Mock the NexusPubSub class
        with patch('kubani.nexus.pubsub.NexusPubSub', return_value=mock_pubsub):
            # Execute the activity
            result = await publish_response_activity(input_data)
            
            # Verify message was published
            assert result["published"] is True
            
            # Verify AgentMessage was created correctly
            call_args = mock_pubsub.publish_response.call_args
            message_dict = call_args[0][1]
            
            # Verify required fields
            assert "conversation_id" in message_dict
            assert "text" in message_dict
            assert "metadata" in message_dict
            assert "timestamp" in message_dict  # Auto-generated by AgentMessage
            
            # Verify values
            assert message_dict["conversation_id"] == "conv-msg"
            assert message_dict["text"] == "Agent response text"
            assert message_dict["metadata"] == {"key": "value"}
