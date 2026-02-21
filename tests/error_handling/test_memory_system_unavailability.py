"""Tests for memory system unavailability error handling.

This module tests that the system continues processing when the memory
system is unavailable, without crashing.

Requirements: 12.6
"""

from unittest.mock import AsyncMock, patch

import pytest
from temporalio.testing import ActivityEnvironment


@pytest.mark.asyncio
async def test_recall_memories_unavailable():
    """Test that recall_memories handles memory system unavailability.

    Validates: Requirements 12.6
    - Simulates memory system failure
    - Verifies processing continues without memories
    """
    from kubani.nexus.orchestrator.activities import recall_memories_activity

    # Mock memory client that fails
    async def failing_search(*args, **kwargs):
        raise ConnectionError("Memory system unavailable")

    mock_client = AsyncMock()
    mock_client.search = AsyncMock(side_effect=failing_search)

    with patch("kubani.nexus.memory.client.MemoryClient", return_value=mock_client):
        with patch("kubani.nexus.orchestrator.activities.logger") as mock_logger:
            env = ActivityEnvironment()

            input_data = {
                "query": "test query",
                "user_id": "user-123",
                "limit": 5,
            }

            # Execute activity - should handle error gracefully
            result = await env.run(recall_memories_activity, input_data)

            # Verify warning was logged
            assert mock_logger.warning.called
            warning_message = mock_logger.warning.call_args[0][0]
            assert "Memory recall failed" in warning_message
            assert "non-fatal" in warning_message

            # Verify empty memories returned (not crash)
            assert result["memories"] == []


@pytest.mark.asyncio
async def test_store_memory_unavailable():
    """Test that store_memory handles memory system unavailability.

    Validates: Requirements 12.6
    - Simulates memory system failure during storage
    - Verifies processing continues
    """
    from kubani.nexus.orchestrator.activities import store_memory_activity

    # Mock memory client that fails
    async def failing_add(*args, **kwargs):
        raise TimeoutError("Memory system timeout")

    mock_client = AsyncMock()
    mock_client.add = AsyncMock(side_effect=failing_add)

    with patch("kubani.nexus.memory.client.MemoryClient", return_value=mock_client):
        with patch("kubani.nexus.orchestrator.activities.logger") as mock_logger:
            env = ActivityEnvironment()

            input_data = {
                "content": "Important memory",
                "user_id": "user-456",
                "metadata": {"key": "value"},
            }

            # Execute activity - should handle error gracefully
            result = await env.run(store_memory_activity, input_data)

            # Verify warning was logged
            assert mock_logger.warning.called
            warning_message = mock_logger.warning.call_args[0][0]
            assert "Memory storage failed" in warning_message
            assert "non-fatal" in warning_message

            # Verify stored=False returned (not crash)
            assert result["stored"] is False
            assert "error" in result


@pytest.mark.asyncio
async def test_recall_memories_qdrant_unavailable():
    """Test handling of Qdrant vector database unavailability.

    Validates: Requirements 12.6
    - Simulates Qdrant connection failure
    - Verifies graceful degradation
    """
    from kubani.nexus.orchestrator.activities import recall_memories_activity

    # Mock Qdrant connection error
    async def qdrant_connection_error(*args, **kwargs):
        raise Exception("Qdrant: Connection refused")

    mock_client = AsyncMock()
    mock_client.search = AsyncMock(side_effect=qdrant_connection_error)

    with patch("kubani.nexus.memory.client.MemoryClient", return_value=mock_client):
        with patch("kubani.nexus.orchestrator.activities.logger"):
            env = ActivityEnvironment()

            input_data = {
                "query": "search query",
                "user_id": "user-789",
                "limit": 10,
            }

            # Execute activity - should not crash
            result = await env.run(recall_memories_activity, input_data)

            # Verify empty result
            assert result["memories"] == []


@pytest.mark.asyncio
async def test_store_memory_neo4j_unavailable():
    """Test handling of Neo4j graph database unavailability.

    Validates: Requirements 12.6
    - Simulates Neo4j connection failure
    - Verifies graceful degradation
    """
    from kubani.nexus.orchestrator.activities import store_memory_activity

    # Mock Neo4j connection error
    async def neo4j_connection_error(*args, **kwargs):
        raise Exception("Neo4j: ServiceUnavailable")

    mock_client = AsyncMock()
    mock_client.add = AsyncMock(side_effect=neo4j_connection_error)

    with patch("kubani.nexus.memory.client.MemoryClient", return_value=mock_client):
        with patch("kubani.nexus.orchestrator.activities.logger"):
            env = ActivityEnvironment()

            input_data = {
                "content": "Graph memory",
                "user_id": "user-graph",
                "metadata": {},
            }

            # Execute activity - should not crash
            result = await env.run(store_memory_activity, input_data)

            # Verify failure is indicated
            assert result["stored"] is False


@pytest.mark.asyncio
async def test_memory_system_intermittent_failure():
    """Test handling of intermittent memory system failures.

    Validates: Requirements 12.6
    - Simulates intermittent failures
    - Verifies system continues despite failures
    """
    from kubani.nexus.orchestrator.activities import recall_memories_activity

    call_count = 0

    async def intermittent_search(*args, **kwargs):
        nonlocal call_count
        call_count += 1

        # Fail on odd calls, succeed on even calls
        if call_count % 2 == 1:
            raise ConnectionError("Intermittent failure")

        return ["memory1", "memory2"]

    mock_client = AsyncMock()
    mock_client.search = AsyncMock(side_effect=intermittent_search)

    with patch("kubani.nexus.memory.client.MemoryClient", return_value=mock_client):
        with patch("kubani.nexus.orchestrator.activities.logger"):
            env = ActivityEnvironment()

            # First call should fail
            result1 = await env.run(
                recall_memories_activity,
                {
                    "query": "query1",
                    "user_id": "user-1",
                    "limit": 5,
                },
            )
            assert result1["memories"] == []

            # Second call should succeed
            result2 = await env.run(
                recall_memories_activity,
                {
                    "query": "query2",
                    "user_id": "user-2",
                    "limit": 5,
                },
            )
            assert result2["memories"] == ["memory1", "memory2"]


@pytest.mark.asyncio
async def test_plan_response_without_memories():
    """Test that plan_response works without memory system.

    Validates: Requirements 12.6
    - Simulates memory recall failure
    - Verifies planning continues without memories
    """
    from kubani.nexus.orchestrator.activities import plan_response

    # Mock LLM to return valid plan
    async def mock_llm_chat(*args, **kwargs):
        return '{"needs_plan": false, "direct_response": "Hello without memories"}'

    with patch("kubani.framework.llm.get_llm") as mock_get_llm:
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(side_effect=mock_llm_chat)
        mock_get_llm.return_value = mock_llm

        env = ActivityEnvironment()

        input_data = {
            "user_message": "Hello",
            "conversation_history": [],
            "available_skills": [],
            "memories": [],  # Empty memories due to system failure
        }

        # Execute activity - should work without memories
        result = await env.run(plan_response, input_data)

        # Verify planning succeeded
        assert result["needs_plan"] is False
        assert "Hello without memories" in result["direct_response"]


@pytest.mark.asyncio
async def test_memory_client_initialization_failure():
    """Test handling of memory client initialization failure.

    Validates: Requirements 12.6
    - Simulates failure during client initialization
    - Verifies graceful handling
    """
    from kubani.nexus.orchestrator.activities import recall_memories_activity

    # Mock MemoryClient constructor that fails
    def failing_init(*args, **kwargs):
        raise RuntimeError("Failed to initialize memory client")

    with patch("kubani.nexus.memory.client.MemoryClient", side_effect=failing_init):
        with patch("kubani.nexus.orchestrator.activities.logger"):
            env = ActivityEnvironment()

            input_data = {
                "query": "test",
                "user_id": "user-init",
                "limit": 5,
            }

            # Execute activity - should handle init failure
            result = await env.run(recall_memories_activity, input_data)

            # Verify empty result
            assert result["memories"] == []


@pytest.mark.asyncio
async def test_memory_system_partial_failure():
    """Test handling of partial memory system failures.

    Validates: Requirements 12.6
    - Simulates partial results from memory system
    - Verifies system uses what's available
    """
    from kubani.nexus.orchestrator.activities import recall_memories_activity

    # Mock memory client that returns partial results
    async def partial_search(*args, **kwargs):
        # Return some results but log warning about partial failure
        return ["memory1"]  # Only 1 instead of requested 5

    mock_client = AsyncMock()
    mock_client.search = AsyncMock(side_effect=partial_search)

    with patch("kubani.nexus.memory.client.MemoryClient", return_value=mock_client):
        env = ActivityEnvironment()

        input_data = {
            "query": "test query",
            "user_id": "user-partial",
            "limit": 5,
        }

        # Execute activity
        result = await env.run(recall_memories_activity, input_data)

        # Verify partial results are returned
        assert len(result["memories"]) == 1
        assert result["memories"][0] == "memory1"


@pytest.mark.asyncio
async def test_memory_operations_dont_block_workflow():
    """Test that memory operations don't block workflow execution.

    Validates: Requirements 12.6
    - Simulates slow memory operations
    - Verifies they don't block other activities
    """
    import asyncio

    from kubani.nexus.orchestrator.activities import recall_memories_activity

    # Mock slow memory search
    async def slow_search(*args, **kwargs):
        await asyncio.sleep(0.5)
        return ["slow_memory"]

    mock_client = AsyncMock()
    mock_client.search = AsyncMock(side_effect=slow_search)

    with patch("kubani.nexus.memory.client.MemoryClient", return_value=mock_client):
        env = ActivityEnvironment()

        input_data = {
            "query": "slow query",
            "user_id": "user-slow",
            "limit": 5,
        }

        # Execute with timeout to ensure it doesn't hang
        result = await asyncio.wait_for(env.run(recall_memories_activity, input_data), timeout=2.0)

        # Verify it completed
        assert result["memories"] == ["slow_memory"]
