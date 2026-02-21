"""Mock fixtures for Kubani Nexus tests.

This module provides reusable mock objects for testing Nexus components
without requiring live database, Temporal, Redis, or LLM connections.
"""

from unittest.mock import AsyncMock, MagicMock, Mock

import pytest


@pytest.fixture
def db_pool_mock():
    """Mock asyncpg connection pool for database operations.

    Provides mocked methods for:
    - execute: Execute SQL without returning results
    - fetch: Fetch multiple rows
    - fetchrow: Fetch a single row
    - fetchval: Fetch a single value
    """
    pool = AsyncMock()

    # Mock execute (INSERT, UPDATE, DELETE)
    pool.execute = AsyncMock(return_value="INSERT 0 1")

    # Mock fetch (SELECT returning multiple rows)
    pool.fetch = AsyncMock(return_value=[])

    # Mock fetchrow (SELECT returning single row)
    pool.fetchrow = AsyncMock(return_value=None)

    # Mock fetchval (SELECT returning single value)
    pool.fetchval = AsyncMock(return_value=None)

    # Mock acquire context manager for transactions
    connection_mock = AsyncMock()
    connection_mock.execute = AsyncMock(return_value="INSERT 0 1")
    connection_mock.fetch = AsyncMock(return_value=[])
    connection_mock.fetchrow = AsyncMock(return_value=None)
    connection_mock.fetchval = AsyncMock(return_value=None)

    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=connection_mock)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

    return pool


@pytest.fixture
def temporal_client_mock():
    """Mock Temporal client for workflow and activity operations.

    Provides mocked methods for:
    - start_workflow: Start a new workflow execution
    - get_workflow_handle: Get handle to existing workflow
    - signal_workflow: Send signal to workflow
    - query_workflow: Query workflow state
    """
    client = AsyncMock()

    # Mock workflow handle
    workflow_handle = AsyncMock()
    workflow_handle.workflow_id = "test-workflow-123"
    workflow_handle.run_id = "test-run-456"
    workflow_handle.signal = AsyncMock()
    workflow_handle.query = AsyncMock(return_value={})
    workflow_handle.result = AsyncMock(return_value={})
    workflow_handle.describe = AsyncMock(
        return_value=MagicMock(status="RUNNING", workflow_type="NexusOrchestratorWorkflow")
    )

    # Mock client methods
    client.start_workflow = AsyncMock(return_value=workflow_handle)
    client.get_workflow_handle = MagicMock(return_value=workflow_handle)
    client.get_workflow_handle_for = MagicMock(return_value=workflow_handle)

    return client


@pytest.fixture
def redis_client_mock():
    """Mock Redis client for pub/sub operations.

    Provides mocked methods for:
    - publish: Publish message to channel
    - subscribe: Subscribe to channel
    - get: Get value by key
    - set: Set value by key
    - delete: Delete key
    """
    client = AsyncMock()

    # Mock pub/sub operations
    client.publish = AsyncMock(return_value=1)  # Number of subscribers

    # Mock pubsub context manager
    pubsub_mock = AsyncMock()
    pubsub_mock.subscribe = AsyncMock()
    pubsub_mock.unsubscribe = AsyncMock()
    pubsub_mock.get_message = AsyncMock(return_value=None)
    pubsub_mock.__aenter__ = AsyncMock(return_value=pubsub_mock)
    pubsub_mock.__aexit__ = AsyncMock(return_value=None)

    client.pubsub = MagicMock(return_value=pubsub_mock)

    # Mock key-value operations
    client.get = AsyncMock(return_value=None)
    client.set = AsyncMock(return_value=True)
    client.delete = AsyncMock(return_value=1)
    client.exists = AsyncMock(return_value=0)
    client.expire = AsyncMock(return_value=True)

    return client


@pytest.fixture
def llm_client_mock():
    """Mock LLM client for chat completions.

    Provides mocked methods for:
    - chat: Generate chat completion
    - embed: Generate embeddings
    """
    client = AsyncMock()

    # Mock chat completion
    # Returns string directly (after bug fix in kubani/framework/llm.py)
    client.chat = AsyncMock(return_value="This is a test response from the LLM.")

    # Mock embeddings
    client.embed = AsyncMock(return_value=[0.1, 0.2, 0.3])

    # Mock model info
    client.model = "test-model"
    client.api_url = "http://localhost:8000/v1"

    return client


@pytest.fixture
def sandbox_executor_mock():
    """Mock sandbox executor for skill execution.

    Provides mocked methods for:
    - execute_skill_in_sandbox: Execute skill code
    - analyze_skill_safety: Perform static analysis
    """
    from kubani.nexus.models import SkillExecutionResult

    executor = Mock()

    # Mock successful execution
    executor.execute_skill_in_sandbox = AsyncMock(
        return_value=SkillExecutionResult(
            success=True,
            output="Skill executed successfully",
            error=None,
            duration_ms=100,
            skill_name="test-skill",
        )
    )

    # Mock safety analysis
    executor.analyze_skill_safety = Mock(
        return_value={
            "is_safe": True,
            "risk_score": 2.0,
            "findings": [],
        }
    )

    return executor


@pytest.fixture
def memory_client_mock():
    """Mock memory client for vector and graph storage.

    Provides mocked methods for:
    - store_memory: Store a memory
    - recall_memories: Recall relevant memories
    - store_knowledge: Store knowledge graph
    """
    client = AsyncMock()

    # Mock memory operations
    client.store_memory = AsyncMock(return_value={"stored": True, "memory_id": "mem-123"})
    client.recall_memories = AsyncMock(return_value=[])
    client.store_knowledge = AsyncMock(return_value={"stored": True, "node_id": "node-123"})

    return client


@pytest.fixture
def discord_client_mock():
    """Mock Discord client for notifications.

    Provides mocked methods for:
    - send_message: Send text message
    - send_embed: Send rich embed
    """
    client = AsyncMock()

    # Mock message sending
    client.send_message = AsyncMock(return_value={"id": "msg-123", "channel_id": "channel-456"})
    client.send_embed = AsyncMock(return_value={"id": "msg-124", "channel_id": "channel-456"})

    return client
