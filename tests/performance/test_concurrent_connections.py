"""Performance tests for concurrent WebSocket connections.

Tests the Gateway's ability to handle multiple concurrent WebSocket connections
without errors or performance degradation.

Requirements tested:
- 10.1: Handle 10 concurrent WebSocket connections
"""

import asyncio
import time
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

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
    
    # Mock Redis pub/sub
    pubsub = AsyncMock()
    pubsub._subscriptions = {}
    pubsub._message_queues = {}
    
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
                    await asyncio.sleep(0.01)
        except asyncio.CancelledError:
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
    
    # Patch the global state
    import kubani.nexus.gateway.app as gateway_app
    gateway_app._state = mock_gateway_state
    
    return TestClient(app)


# =========================================================================
# Test 27.1: Concurrent WebSocket connections
# =========================================================================


@pytest.mark.performance
def test_concurrent_websocket_connections(
    test_client: TestClient,
    mock_gateway_state: GatewayState,
) -> None:
    """Test handling 10 concurrent WebSocket connections.
    
    Requirements: 10.1
    
    This test verifies that the Gateway can handle multiple concurrent
    WebSocket connections without errors or resource exhaustion.
    """
    # Arrange
    num_connections = 10
    conversation_ids = [str(uuid.uuid4()) for _ in range(num_connections)]
    connections = []
    
    start_time = time.time()
    
    try:
        # Act - establish all connections
        for conv_id in conversation_ids:
            ws = test_client.websocket_connect(f"/ws/nexus/{conv_id}")
            connections.append((conv_id, ws.__enter__()))
            time.sleep(0.05)  # Small delay to avoid overwhelming the system
        
        # Give time for all connections to be established
        time.sleep(0.5)
        
        # Assert - verify all connections are tracked
        for conv_id, _ in connections:
            assert conv_id in mock_gateway_state.active_websockets
            assert len(mock_gateway_state.active_websockets[conv_id]) >= 1
        
        # Verify total number of active connections
        total_connections = sum(
            len(ws_list) for ws_list in mock_gateway_state.active_websockets.values()
        )
        assert total_connections >= num_connections
        
        # Send a message through each connection to verify they're working
        for conv_id, ws in connections:
            ws.send_json({
                "text": f"Test message from {conv_id}",
                "user_id": "test-user",
            })
        
        # Give time for messages to be processed
        time.sleep(0.5)
        
        # Verify all messages were signaled to workflows
        workflow_handle = mock_gateway_state.temporal_client.get_workflow_handle.return_value
        signal_calls = workflow_handle.signal.call_args_list
        user_message_signals = [
            call for call in signal_calls if call[0][0] == "user_message"
        ]
        assert len(user_message_signals) >= num_connections
        
    finally:
        # Cleanup - close all connections
        for _, ws in connections:
            try:
                ws.__exit__(None, None, None)
            except Exception:
                pass  # Ignore cleanup errors
        
        # Give time for cleanup
        time.sleep(0.5)
    
    end_time = time.time()
    duration = end_time - start_time
    
    # Performance assertion - should complete within reasonable time
    assert duration < 10.0, f"Test took too long: {duration:.2f}s"
    
    # Verify cleanup - all connections should be removed
    # (Some may still be cleaning up, so we check that most are gone)
    remaining_connections = sum(
        len(ws_list) for ws_list in mock_gateway_state.active_websockets.values()
    )
    assert remaining_connections < num_connections // 2


@pytest.mark.performance
def test_concurrent_connections_with_messages(
    test_client: TestClient,
    mock_gateway_state: GatewayState,
) -> None:
    """Test concurrent connections can send and receive messages simultaneously.
    
    Requirements: 10.1
    
    This test verifies that multiple concurrent connections can exchange
    messages without interference or dropped messages.
    """
    # Arrange
    num_connections = 10
    messages_per_connection = 5
    conversation_ids = [str(uuid.uuid4()) for _ in range(num_connections)]
    connections = []
    
    try:
        # Establish all connections
        for conv_id in conversation_ids:
            ws = test_client.websocket_connect(f"/ws/nexus/{conv_id}")
            connections.append((conv_id, ws.__enter__()))
            time.sleep(0.05)
        
        time.sleep(0.5)
        
        # Send multiple messages through each connection
        for conv_id, ws in connections:
            for i in range(messages_per_connection):
                ws.send_json({
                    "text": f"Message {i} from {conv_id}",
                    "user_id": "test-user",
                })
                time.sleep(0.02)
        
        # Give time for all messages to be processed
        time.sleep(1.0)
        
        # Verify all messages were signaled
        workflow_handle = mock_gateway_state.temporal_client.get_workflow_handle.return_value
        signal_calls = workflow_handle.signal.call_args_list
        user_message_signals = [
            call for call in signal_calls if call[0][0] == "user_message"
        ]
        
        expected_total = num_connections * messages_per_connection
        assert len(user_message_signals) >= expected_total
        
    finally:
        # Cleanup
        for _, ws in connections:
            try:
                ws.__exit__(None, None, None)
            except Exception:
                pass
        
        time.sleep(0.5)


@pytest.mark.performance
def test_connection_stability_under_load(
    test_client: TestClient,
    mock_gateway_state: GatewayState,
) -> None:
    """Test connection stability when rapidly connecting and disconnecting.
    
    Requirements: 10.1
    
    This test verifies that the Gateway handles rapid connection churn
    without resource leaks or errors.
    """
    # Arrange
    num_iterations = 10
    connections_per_iteration = 5
    
    for iteration in range(num_iterations):
        connections = []
        conversation_ids = [str(uuid.uuid4()) for _ in range(connections_per_iteration)]
        
        try:
            # Establish connections
            for conv_id in conversation_ids:
                ws = test_client.websocket_connect(f"/ws/nexus/{conv_id}")
                connections.append((conv_id, ws.__enter__()))
            
            time.sleep(0.2)
            
            # Verify connections are active
            for conv_id, _ in connections:
                assert conv_id in mock_gateway_state.active_websockets
            
            # Send a message through each
            for conv_id, ws in connections:
                ws.send_json({
                    "text": f"Test message iteration {iteration}",
                    "user_id": "test-user",
                })
            
            time.sleep(0.2)
            
        finally:
            # Disconnect all
            for _, ws in connections:
                try:
                    ws.__exit__(None, None, None)
                except Exception:
                    pass
            
            time.sleep(0.2)
    
    # Verify no resource leaks - all connections should be cleaned up
    time.sleep(0.5)
    total_remaining = sum(
        len(ws_list) for ws_list in mock_gateway_state.active_websockets.values()
    )
    assert total_remaining == 0, f"Resource leak: {total_remaining} connections remaining"
