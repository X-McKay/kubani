"""Unit tests for Nexus memory activities.

This module tests the memory activities that handle memory storage and retrieval
for the Nexus orchestrator.

Tests include:
- recall_memories_activity: Querying the memory system for relevant context
- store_memory_activity: Storing new memories from conversations
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from kubani.nexus.orchestrator.activities import (
    recall_memories_activity,
    store_memory_activity,
)


class TestRecallMemoriesActivity:
    """Tests for recall_memories_activity."""

    @pytest.mark.asyncio
    async def test_recall_memories_returns_empty_list_on_failure(self):
        """
        Test that recall_memories_activity returns empty list when memory client fails.
        
        When the memory client raises an exception, the activity should:
        1. Catch the exception
        2. Log a warning (non-fatal)
        3. Return an empty list of memories
        4. Not crash or propagate the exception
        
        This ensures the orchestrator can continue processing even when the
        memory system is unavailable.
        
        Validates: Requirements 4.8
        """
        # Prepare input data
        input_data = {
            "query": "What are the user's preferences?",
            "user_id": "user-123",
            "limit": 5
        }
        
        # Mock MemoryClient that raises an exception
        mock_memory_client = MagicMock()
        mock_memory_client.search = AsyncMock(side_effect=Exception("Qdrant connection failed"))
        
        # Mock the MemoryClient class and activity context
        with patch('kubani.nexus.memory.client.MemoryClient', return_value=mock_memory_client), \
             patch('temporalio.activity.heartbeat') as mock_heartbeat:
            
            # Execute the activity
            result = await recall_memories_activity(input_data)
            
            # Verify the result
            assert result is not None
            assert isinstance(result, dict)
            assert "memories" in result
            
            # Verify empty list is returned (not None, not error)
            assert result["memories"] == []
            assert isinstance(result["memories"], list)
            
            # Verify search was attempted
            mock_memory_client.search.assert_called_once_with(
                query="What are the user's preferences?",
                user_id="user-123",
                limit=5
            )
            
            # Verify heartbeat was called
            mock_heartbeat.assert_called()

    @pytest.mark.asyncio
    async def test_recall_memories_handles_connection_timeout(self):
        """
        Test that recall_memories_activity handles connection timeouts gracefully.
        
        Validates: Requirements 4.8
        """
        # Prepare input data
        input_data = {
            "query": "user preferences",
            "user_id": "user-456",
            "limit": 3
        }
        
        # Mock MemoryClient that times out
        mock_memory_client = MagicMock()
        mock_memory_client.search = AsyncMock(side_effect=TimeoutError("Memory search timed out"))
        
        # Mock the MemoryClient class and activity context
        with patch('kubani.nexus.memory.client.MemoryClient', return_value=mock_memory_client), \
             patch('temporalio.activity.heartbeat'):
            
            # Execute the activity
            result = await recall_memories_activity(input_data)
            
            # Verify empty list is returned without crashing
            assert result["memories"] == []

    @pytest.mark.asyncio
    async def test_recall_memories_handles_network_error(self):
        """
        Test that recall_memories_activity handles network errors gracefully.
        
        Validates: Requirements 4.8
        """
        # Prepare input data
        input_data = {
            "query": "test query",
            "user_id": "user-789",
            "limit": 10
        }
        
        # Mock MemoryClient that raises network error
        mock_memory_client = MagicMock()
        mock_memory_client.search = AsyncMock(
            side_effect=ConnectionError("Network unreachable")
        )
        
        # Mock the MemoryClient class and activity context
        with patch('kubani.nexus.memory.client.MemoryClient', return_value=mock_memory_client), \
             patch('temporalio.activity.heartbeat'):
            
            # Execute the activity
            result = await recall_memories_activity(input_data)
            
            # Verify empty list is returned
            assert result["memories"] == []
            
            # Verify search was attempted with correct parameters
            mock_memory_client.search.assert_called_once_with(
                query="test query",
                user_id="user-789",
                limit=10
            )

    @pytest.mark.asyncio
    async def test_recall_memories_with_default_values(self):
        """
        Test that recall_memories_activity uses default values when optional fields are missing.
        
        Validates: Requirements 4.8
        """
        # Prepare minimal input data (missing user_id and limit)
        input_data = {
            "query": "minimal query"
        }
        
        # Mock MemoryClient that raises an error
        mock_memory_client = MagicMock()
        mock_memory_client.search = AsyncMock(side_effect=Exception("Test error"))
        
        # Mock the MemoryClient class and activity context
        with patch('kubani.nexus.memory.client.MemoryClient', return_value=mock_memory_client), \
             patch('temporalio.activity.heartbeat'):
            
            # Execute the activity
            result = await recall_memories_activity(input_data)
            
            # Verify empty list is returned
            assert result["memories"] == []
            
            # Verify default values were used
            mock_memory_client.search.assert_called_once_with(
                query="minimal query",
                user_id="default",  # default value
                limit=5  # default value
            )

    @pytest.mark.asyncio
    async def test_recall_memories_successful_case(self):
        """
        Test that recall_memories_activity returns memories when successful.
        
        This test verifies the happy path to ensure the activity works correctly
        when the memory system is available.
        
        Validates: Requirements 4.8
        """
        # Prepare input data
        input_data = {
            "query": "user preferences",
            "user_id": "user-success",
            "limit": 3
        }
        
        # Mock MemoryClient that returns memories
        mock_memory_client = MagicMock()
        mock_memory_client.search = AsyncMock(return_value=[
            "User prefers dark mode",
            "User likes Python programming",
            "User is interested in AI"
        ])
        
        # Mock the MemoryClient class and activity context
        with patch('kubani.nexus.memory.client.MemoryClient', return_value=mock_memory_client), \
             patch('temporalio.activity.heartbeat'):
            
            # Execute the activity
            result = await recall_memories_activity(input_data)
            
            # Verify memories are returned
            assert result["memories"] == [
                "User prefers dark mode",
                "User likes Python programming",
                "User is interested in AI"
            ]
            
            # Verify search was called correctly
            mock_memory_client.search.assert_called_once_with(
                query="user preferences",
                user_id="user-success",
                limit=3
            )


class TestStoreMemoryActivity:
    """Tests for store_memory_activity."""

    @pytest.mark.asyncio
    async def test_store_memory_returns_false_on_failure(self):
        """
        Test that store_memory_activity returns stored=False when memory client fails.
        
        When the memory client raises an exception, the activity should:
        1. Catch the exception
        2. Log a warning (non-fatal)
        3. Return stored=False with error message
        4. Not crash or propagate the exception
        
        This ensures the orchestrator can continue processing even when the
        memory system is unavailable.
        
        Validates: Requirements 4.9
        """
        # Prepare input data
        input_data = {
            "content": "User prefers dark mode",
            "user_id": "user-123",
            "metadata": {"source": "conversation", "importance": "high"}
        }
        
        # Mock MemoryClient that raises an exception
        mock_memory_client = MagicMock()
        mock_memory_client.add = AsyncMock(side_effect=Exception("Qdrant write failed"))
        
        # Mock the MemoryClient class
        with patch('kubani.nexus.memory.client.MemoryClient', return_value=mock_memory_client):
            # Execute the activity
            result = await store_memory_activity(input_data)
            
            # Verify the result
            assert result is not None
            assert isinstance(result, dict)
            assert "stored" in result
            
            # Verify stored=False is returned
            assert result["stored"] is False
            
            # Verify error message is included
            assert "error" in result
            assert "Qdrant write failed" in result["error"]
            
            # Verify add was attempted
            mock_memory_client.add.assert_called_once_with(
                content="User prefers dark mode",
                user_id="user-123",
                metadata={"source": "conversation", "importance": "high"}
            )

    @pytest.mark.asyncio
    async def test_store_memory_handles_connection_timeout(self):
        """
        Test that store_memory_activity handles connection timeouts gracefully.
        
        Validates: Requirements 4.9
        """
        # Prepare input data
        input_data = {
            "content": "Important memory",
            "user_id": "user-456",
            "metadata": {}
        }
        
        # Mock MemoryClient that times out
        mock_memory_client = MagicMock()
        mock_memory_client.add = AsyncMock(side_effect=TimeoutError("Memory storage timed out"))
        
        # Mock the MemoryClient class
        with patch('kubani.nexus.memory.client.MemoryClient', return_value=mock_memory_client):
            # Execute the activity
            result = await store_memory_activity(input_data)
            
            # Verify stored=False is returned without crashing
            assert result["stored"] is False
            assert "error" in result
            assert "Memory storage timed out" in result["error"]

    @pytest.mark.asyncio
    async def test_store_memory_handles_network_error(self):
        """
        Test that store_memory_activity handles network errors gracefully.
        
        Validates: Requirements 4.9
        """
        # Prepare input data
        input_data = {
            "content": "Test memory content",
            "user_id": "user-789",
            "metadata": {"key": "value"}
        }
        
        # Mock MemoryClient that raises network error
        mock_memory_client = MagicMock()
        mock_memory_client.add = AsyncMock(
            side_effect=ConnectionError("Network unreachable")
        )
        
        # Mock the MemoryClient class
        with patch('kubani.nexus.memory.client.MemoryClient', return_value=mock_memory_client):
            # Execute the activity
            result = await store_memory_activity(input_data)
            
            # Verify stored=False is returned
            assert result["stored"] is False
            assert "error" in result
            
            # Verify add was attempted with correct parameters
            mock_memory_client.add.assert_called_once_with(
                content="Test memory content",
                user_id="user-789",
                metadata={"key": "value"}
            )

    @pytest.mark.asyncio
    async def test_store_memory_with_default_values(self):
        """
        Test that store_memory_activity uses default values when optional fields are missing.
        
        Validates: Requirements 4.9
        """
        # Prepare minimal input data (missing user_id and metadata)
        input_data = {
            "content": "Minimal memory"
        }
        
        # Mock MemoryClient that raises an error
        mock_memory_client = MagicMock()
        mock_memory_client.add = AsyncMock(side_effect=Exception("Test error"))
        
        # Mock the MemoryClient class
        with patch('kubani.nexus.memory.client.MemoryClient', return_value=mock_memory_client):
            # Execute the activity
            result = await store_memory_activity(input_data)
            
            # Verify stored=False is returned
            assert result["stored"] is False
            
            # Verify default values were used
            mock_memory_client.add.assert_called_once_with(
                content="Minimal memory",
                user_id="default",  # default value
                metadata={}  # default value
            )

    @pytest.mark.asyncio
    async def test_store_memory_successful_case(self):
        """
        Test that store_memory_activity returns stored=True when successful.
        
        This test verifies the happy path to ensure the activity works correctly
        when the memory system is available.
        
        Validates: Requirements 4.9
        """
        # Prepare input data
        input_data = {
            "content": "User completed Python tutorial",
            "user_id": "user-success",
            "metadata": {"category": "learning", "timestamp": "2024-01-15"}
        }
        
        # Mock MemoryClient that succeeds
        mock_memory_client = MagicMock()
        mock_memory_client.add = AsyncMock(return_value="memory-id-123")
        
        # Mock the MemoryClient class
        with patch('kubani.nexus.memory.client.MemoryClient', return_value=mock_memory_client):
            # Execute the activity
            result = await store_memory_activity(input_data)
            
            # Verify stored=True is returned
            assert result["stored"] is True
            
            # Verify no error field is present
            assert "error" not in result
            
            # Verify add was called correctly
            mock_memory_client.add.assert_called_once_with(
                content="User completed Python tutorial",
                user_id="user-success",
                metadata={"category": "learning", "timestamp": "2024-01-15"}
            )

    @pytest.mark.asyncio
    async def test_store_memory_with_empty_metadata(self):
        """
        Test that store_memory_activity handles empty metadata correctly.
        
        Validates: Requirements 4.9
        """
        # Prepare input data with explicit empty metadata
        input_data = {
            "content": "Simple memory",
            "user_id": "user-empty-meta",
            "metadata": {}
        }
        
        # Mock MemoryClient that raises an error
        mock_memory_client = MagicMock()
        mock_memory_client.add = AsyncMock(side_effect=Exception("Storage error"))
        
        # Mock the MemoryClient class
        with patch('kubani.nexus.memory.client.MemoryClient', return_value=mock_memory_client):
            # Execute the activity
            result = await store_memory_activity(input_data)
            
            # Verify stored=False is returned
            assert result["stored"] is False
            
            # Verify empty metadata was passed
            mock_memory_client.add.assert_called_once_with(
                content="Simple memory",
                user_id="user-empty-meta",
                metadata={}
            )
