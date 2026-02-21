"""Integration tests for Nexus Gateway WebSocket.

Tests the WebSocket endpoint of the Gateway with real services (Redis, Temporal).
These tests verify that the Gateway correctly handles WebSocket connections,
forwards messages to workflows, and publishes responses back to clients.

Requirements tested:
- 5.7: WebSocket connection and Redis subscription
- 5.8: WebSocket message sending to workflow
- 5.9: WebSocket message receiving from Redis
"""

import asyncio
import json
import time
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

from kubani.nexus.gateway.app import GatewayState, create_app


@pytest.fixture
def mock_gateway_state() -> GatewayState:
    """Create a mock gateway state with mocked dependencies."""
    state = GatewayState()
    
    # Mock Temporal client
    workflow_handle = AsyncMock()
    workflow_handle.workflow_id = "nexus-test-user"
    workflow_handle.signal = AsyncMock()
    workflow_handle.query = AsyncMock(return_value={
        "status": "IDLE",
        "user_id": "test-user",
        "conversation_id": "test-conv-123",
    })
    
    temporal_client = AsyncMock()
    temporal_client.get_workflow_handle = MagicMock(return_value=workflow_handle)
    state.temporal_client = temporal_client
    
    # Mock database pool
    db_pool = AsyncMock()
    db_pool.fetch = AsyncMock(return_value=[])
    db_pool.fetchrow = AsyncMock(return_value=None)
    db_pool.fetchval = AsyncMock(return_value=1)
    db_pool.execute = AsyncMock()
    state.db_pool = db_pool
    
    # Mock Redis pub/sub with a real-ish implementation
    pubsub = AsyncMock()
    pubsub._subscriptions = {}  # Track subscriptions
    pubsub._message_queues = {}  # Store messages for each channel
    
    async def mock_subscribe_responses(conversation_id: str):
        """Mock subscribe_responses that yields messages from a queue."""
        channel = f"nexus:response:{conversation_id}"
        queue = asyncio.Queue()
        pubsub._subscriptions[channel] = queue
        pubsub._message_queues[channel] = queue
        
        try:
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=0.1)
                    yield message
                except asyncio.TimeoutError:
                    # Allow other tasks to run
                    await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            # Clean up subscription
            if channel in pubsub._subscriptions:
                del pubsub._subscriptions[channel]
            if channel in pubsub._message_queues:
                del pubsub._message_queues[channel]
            raise
    
    async def mock_publish_response(conversation_id: str, message: dict[str, Any]):
        """Mock publish_response that puts messages in the subscription queue."""
        channel = f"nexus:response:{conversation_id}"
        if channel in pubsub._message_queues:
            await pubsub._message_queues[channel].put(message)
    
    pubsub.subscribe_responses = mock_subscribe_responses
    pubsub.publish_response = mock_publish_response
    pubsub.close = AsyncMock()
    state.pubsub = pubsub
    
    return state


@pytest.fixture
def test_client(mock_gateway_state: GatewayState) -> TestClient:
    """Create a test client for the Gateway app."""
    app = create_app()
    
    # Patch the global state before creating the client
    import kubani.nexus.gateway.app as gateway_app
    gateway_app._state = mock_gateway_state
    
    client = TestClient(app)
    
    # Return the client (cleanup happens automatically)
    return client


# =========================================================================
# Test 18.1: WebSocket connection
# =========================================================================


@pytest.mark.integration
def test_websocket_connection_accepted(
    test_client: TestClient,
    mock_gateway_state: GatewayState,
) -> None:
    """Test WebSocket connection is accepted and tracked.
    
    Requirements: 5.7
    """
    # Arrange
    conversation_id = str(uuid.uuid4())
    
    # Act & Assert
    with test_client.websocket_connect(f"/ws/nexus/{conversation_id}") as websocket:
        # Verify connection was accepted (no exception raised)
        assert websocket is not None
        
        # Give time for connection tracking
        time.sleep(0.1)
        
        # Verify the connection is tracked in active_websockets
        assert conversation_id in mock_gateway_state.active_websockets
        assert len(mock_gateway_state.active_websockets[conversation_id]) >= 1
    
    # After context exit, give cleanup time to run
    time.sleep(0.2)
    
    # Verify cleanup (connection should be removed)
    assert conversation_id not in mock_gateway_state.active_websockets


@pytest.mark.integration
def test_websocket_redis_subscription_created(
    test_client: TestClient,
    mock_gateway_state: GatewayState,
) -> None:
    """Test WebSocket connection creates Redis subscription.
    
    Requirements: 5.7
    """
    # Arrange
    conversation_id = str(uuid.uuid4())
    expected_channel = f"nexus:response:{conversation_id}"
    
    # Act
    with test_client.websocket_connect(f"/ws/nexus/{conversation_id}") as websocket:
        # Give the subscription task time to start
        time.sleep(0.3)
        
        # Assert - verify Redis subscription was created
        assert expected_channel in mock_gateway_state.pubsub._subscriptions
    
    # After disconnect, give cleanup time
    time.sleep(0.2)
    
    # Subscription should be cleaned up
    assert expected_channel not in mock_gateway_state.pubsub._subscriptions


@pytest.mark.integration
def test_websocket_multiple_connections_same_conversation(
    test_client: TestClient,
    mock_gateway_state: GatewayState,
) -> None:
    """Test multiple WebSocket connections to the same conversation.
    
    Requirements: 5.7
    """
    # Arrange
    conversation_id = str(uuid.uuid4())
    
    # Act - test sequential connections (TestClient limitation)
    with test_client.websocket_connect(f"/ws/nexus/{conversation_id}") as ws1:
        time.sleep(0.1)
        # Verify first connection is tracked
        assert conversation_id in mock_gateway_state.active_websockets
        assert len(mock_gateway_state.active_websockets[conversation_id]) >= 1
    
    # After first disconnect, verify cleanup
    time.sleep(0.2)
    
    # Second connection
    with test_client.websocket_connect(f"/ws/nexus/{conversation_id}") as ws2:
        time.sleep(0.1)
        # Verify second connection is tracked
        assert conversation_id in mock_gateway_state.active_websockets
        assert len(mock_gateway_state.active_websockets[conversation_id]) >= 1
    
    # After both disconnect, verify cleanup
    time.sleep(0.2)
    assert conversation_id not in mock_gateway_state.active_websockets


# =========================================================================
# Test 18.2: WebSocket message sending
# =========================================================================


@pytest.mark.integration
def test_websocket_send_message_signals_workflow(
    test_client: TestClient,
    mock_gateway_state: GatewayState,
) -> None:
    """Test sending message via WebSocket signals the workflow.
    
    Requirements: 5.8
    """
    # Arrange
    conversation_id = str(uuid.uuid4())
    user_id = "test-user"
    message_text = "Hello from WebSocket!"
    
    # Act
    with test_client.websocket_connect(f"/ws/nexus/{conversation_id}") as websocket:
        # Send a message
        websocket.send_json({
            "text": message_text,
            "user_id": user_id,
        })
        
        # Give the receive loop time to process
        time.sleep(0.3)
    
    # Assert - verify workflow was signaled
    workflow_handle = mock_gateway_state.temporal_client.get_workflow_handle.return_value
    workflow_handle.signal.assert_called()
    
    # Verify signal details
    signal_calls = workflow_handle.signal.call_args_list
    assert len(signal_calls) >= 1
    
    # Find the user_message signal
    user_message_call = None
    for call in signal_calls:
        if call[0][0] == "user_message":
            user_message_call = call
            break
    
    assert user_message_call is not None
    signal_name, signal_data = user_message_call[0]
    assert signal_name == "user_message"
    assert signal_data["text"] == message_text
    assert signal_data["user_id"] == user_id
    assert signal_data["conversation_id"] == conversation_id
    assert signal_data["source"] == "kubani-ui"


@pytest.mark.integration
def test_websocket_send_multiple_messages(
    test_client: TestClient,
    mock_gateway_state: GatewayState,
) -> None:
    """Test sending multiple messages via WebSocket.
    
    Requirements: 5.8
    """
    # Arrange
    conversation_id = str(uuid.uuid4())
    messages = [
        {"text": "First message", "user_id": "user1"},
        {"text": "Second message", "user_id": "user1"},
        {"text": "Third message", "user_id": "user1"},
    ]
    
    # Act
    with test_client.websocket_connect(f"/ws/nexus/{conversation_id}") as websocket:
        for msg in messages:
            websocket.send_json(msg)
            time.sleep(0.1)  # Small delay between messages
        
        # Give time for processing
        time.sleep(0.3)
    
    # Assert - verify all messages were signaled
    workflow_handle = mock_gateway_state.temporal_client.get_workflow_handle.return_value
    signal_calls = workflow_handle.signal.call_args_list
    
    # Count user_message signals
    user_message_signals = [
        call for call in signal_calls if call[0][0] == "user_message"
    ]
    assert len(user_message_signals) >= 3


@pytest.mark.integration
def test_websocket_send_empty_message_ignored(
    test_client: TestClient,
    mock_gateway_state: GatewayState,
) -> None:
    """Test sending empty message via WebSocket is ignored.
    
    Requirements: 5.8
    """
    # Arrange
    conversation_id = str(uuid.uuid4())
    
    # Act
    with test_client.websocket_connect(f"/ws/nexus/{conversation_id}") as websocket:
        # Send empty message
        websocket.send_json({"text": "", "user_id": "test-user"})
        time.sleep(0.1)
        
        # Send valid message
        websocket.send_json({"text": "Valid message", "user_id": "test-user"})
        time.sleep(0.3)
    
    # Assert - only the valid message should be signaled
    workflow_handle = mock_gateway_state.temporal_client.get_workflow_handle.return_value
    signal_calls = workflow_handle.signal.call_args_list
    
    user_message_signals = [
        call for call in signal_calls if call[0][0] == "user_message"
    ]
    
    # Should only have one signal (the valid message)
    assert len(user_message_signals) == 1
    assert user_message_signals[0][0][1]["text"] == "Valid message"


# =========================================================================
# Test 18.3: WebSocket message receiving
# =========================================================================


@pytest.mark.integration
def test_websocket_receive_message_from_redis(
    test_client: TestClient,
    mock_gateway_state: GatewayState,
) -> None:
    """Test WebSocket receives messages published to Redis.
    
    Requirements: 5.9
    """
    # Arrange
    conversation_id = str(uuid.uuid4())
    agent_message = {
        "role": "assistant",
        "content": "Hello from the agent!",
        "source": "system",
        "timestamp": "2024-01-01T10:00:00Z",
    }
    
    # Act
    with test_client.websocket_connect(f"/ws/nexus/{conversation_id}") as websocket:
        # Give subscription time to set up
        time.sleep(0.3)
        
        # Publish a message to Redis (need to run in event loop)
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(
            mock_gateway_state.pubsub.publish_response(conversation_id, agent_message)
        )
        loop.close()
        
        # Give time for message to propagate
        time.sleep(0.2)
        
        # Receive the message from WebSocket
        received = websocket.receive_json()
    
    # Assert
    assert received == agent_message
    assert received["content"] == "Hello from the agent!"
    assert received["role"] == "assistant"


@pytest.mark.integration
def test_websocket_receive_multiple_messages(
    test_client: TestClient,
    mock_gateway_state: GatewayState,
) -> None:
    """Test WebSocket receives multiple messages from Redis.
    
    Requirements: 5.9
    """
    # Arrange
    conversation_id = str(uuid.uuid4())
    messages = [
        {"role": "assistant", "content": "Message 1", "timestamp": "2024-01-01T10:00:00Z"},
        {"role": "assistant", "content": "Message 2", "timestamp": "2024-01-01T10:00:01Z"},
        {"role": "assistant", "content": "Message 3", "timestamp": "2024-01-01T10:00:02Z"},
    ]
    
    # Act
    with test_client.websocket_connect(f"/ws/nexus/{conversation_id}") as websocket:
        # Give subscription time to set up
        time.sleep(0.3)
        
        # Publish messages to Redis
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        for msg in messages:
            loop.run_until_complete(
                mock_gateway_state.pubsub.publish_response(conversation_id, msg)
            )
            time.sleep(0.05)
        loop.close()
        
        # Give time for messages to propagate
        time.sleep(0.2)
        
        # Receive all messages
        received_messages = []
        for _ in range(3):
            received = websocket.receive_json()
            received_messages.append(received)
    
    # Assert
    assert len(received_messages) == 3
    assert received_messages[0]["content"] == "Message 1"
    assert received_messages[1]["content"] == "Message 2"
    assert received_messages[2]["content"] == "Message 3"


@pytest.mark.integration
def test_websocket_bidirectional_communication(
    test_client: TestClient,
    mock_gateway_state: GatewayState,
) -> None:
    """Test bidirectional communication: send and receive messages.
    
    Requirements: 5.8, 5.9
    """
    # Arrange
    conversation_id = str(uuid.uuid4())
    user_message = {"text": "What's the weather?", "user_id": "test-user"}
    agent_response = {
        "role": "assistant",
        "content": "It's sunny today!",
        "timestamp": "2024-01-01T10:00:00Z",
    }
    
    # Act
    with test_client.websocket_connect(f"/ws/nexus/{conversation_id}") as websocket:
        # Give subscription time to set up
        time.sleep(0.3)
        
        # Send user message
        websocket.send_json(user_message)
        time.sleep(0.2)
        
        # Simulate agent response via Redis
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(
            mock_gateway_state.pubsub.publish_response(conversation_id, agent_response)
        )
        loop.close()
        
        time.sleep(0.2)
        
        # Receive agent response
        received = websocket.receive_json()
    
    # Assert - verify workflow was signaled
    workflow_handle = mock_gateway_state.temporal_client.get_workflow_handle.return_value
    workflow_handle.signal.assert_called()
    
    # Assert - verify response was received
    assert received == agent_response
    assert received["content"] == "It's sunny today!"


@pytest.mark.integration
def test_websocket_graceful_disconnect(
    test_client: TestClient,
    mock_gateway_state: GatewayState,
) -> None:
    """Test WebSocket handles graceful disconnect and cleanup.
    
    Requirements: 5.7
    """
    # Arrange
    conversation_id = str(uuid.uuid4())
    
    # Act
    with test_client.websocket_connect(f"/ws/nexus/{conversation_id}") as websocket:
        time.sleep(0.2)
        # Verify connection is active
        assert conversation_id in mock_gateway_state.active_websockets
        
        # Send a message to verify it's working
        websocket.send_json({"text": "Test", "user_id": "test-user"})
        time.sleep(0.2)
    
    # Assert - after disconnect, verify cleanup
    time.sleep(0.2)
    assert conversation_id not in mock_gateway_state.active_websockets
    
    # Verify Redis subscription was cleaned up
    expected_channel = f"nexus:response:{conversation_id}"
    assert expected_channel not in mock_gateway_state.pubsub._subscriptions
