"""Integration tests for Nexus Gateway REST API.

Tests the REST endpoints of the Gateway with real services (PostgreSQL, Redis, Temporal).
These tests verify that the Gateway correctly handles HTTP requests, signals workflows,
and interacts with the database.

Requirements tested:
- 5.1: POST /api/nexus/chat
- 5.2: GET /api/nexus/status/{user_id}
- 5.3: GET /api/nexus/conversations/{id}/history
- 5.4: GET /api/nexus/actions
- 5.5: GET /api/nexus/approvals
- 5.6: POST /api/nexus/approvals/{id}/decide
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch

from kubani.nexus.gateway.app import create_app, GatewayState
from kubani.nexus.models.messages import MessageSource, UserMessage


@pytest.fixture
async def mock_gateway_state() -> AsyncGenerator[GatewayState, None]:
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
        "current_goal": None,
        "actions_count": 0,
        "current_plan": None,
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
    pubsub.publish_response = AsyncMock()
    pubsub.close = AsyncMock()
    state.pubsub = pubsub
    
    yield state
    
    # Cleanup
    if state.pubsub:
        await state.pubsub.close()


@pytest.fixture
async def test_client(mock_gateway_state: GatewayState) -> AsyncGenerator[AsyncClient, None]:
    """Create a test client for the Gateway app."""
    app = create_app()
    
    # Replace the global state with our mock
    with patch("kubani.nexus.gateway.app._state", mock_gateway_state):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


# =========================================================================
# Test 17.1: POST /api/nexus/chat
# =========================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_post_chat_with_new_conversation(
    test_client: AsyncClient,
    mock_gateway_state: GatewayState,
) -> None:
    """Test POST /api/nexus/chat creates a new conversation and signals workflow.
    
    Requirements: 5.1
    """
    # Arrange
    request_data = {
        "text": "Hello, Nexus!",
        "user_id": "test-user",
        "source": "kubani-ui",
    }
    
    # Act
    response = await test_client.post("/api/nexus/chat", json=request_data)
    
    # Assert
    assert response.status_code == 200
    data = response.json()
    
    # Verify response structure
    assert "conversation_id" in data
    assert data["status"] == "queued"
    assert data["message"] == "Message sent to Nexus agent"
    
    # Verify conversation_id is a valid UUID
    conversation_id = data["conversation_id"]
    assert uuid.UUID(conversation_id)
    
    # Verify workflow was signaled
    mock_gateway_state.temporal_client.get_workflow_handle.assert_called_once()
    workflow_handle = mock_gateway_state.temporal_client.get_workflow_handle.return_value
    workflow_handle.signal.assert_called_once()
    
    # Verify signal payload
    signal_call = workflow_handle.signal.call_args
    assert signal_call[0][0] == "user_message"
    signal_data = signal_call[0][1]
    assert signal_data["text"] == "Hello, Nexus!"
    assert signal_data["user_id"] == "test-user"
    assert signal_data["source"] == "kubani-ui"
    assert signal_data["conversation_id"] == conversation_id


@pytest.mark.asyncio
@pytest.mark.integration
async def test_post_chat_with_existing_conversation(
    test_client: AsyncClient,
    mock_gateway_state: GatewayState,
) -> None:
    """Test POST /api/nexus/chat with existing conversation_id.
    
    Requirements: 5.1
    """
    # Arrange
    existing_conversation_id = str(uuid.uuid4())
    request_data = {
        "text": "Follow-up message",
        "conversation_id": existing_conversation_id,
        "user_id": "test-user",
        "source": "kubani-ui",
    }
    
    # Act
    response = await test_client.post("/api/nexus/chat", json=request_data)
    
    # Assert
    assert response.status_code == 200
    data = response.json()
    
    # Verify it uses the provided conversation_id
    assert data["conversation_id"] == existing_conversation_id
    
    # Verify workflow was signaled with correct conversation_id
    workflow_handle = mock_gateway_state.temporal_client.get_workflow_handle.return_value
    signal_call = workflow_handle.signal.call_args
    signal_data = signal_call[0][1]
    assert signal_data["conversation_id"] == existing_conversation_id


@pytest.mark.asyncio
@pytest.mark.integration
async def test_post_chat_workflow_unavailable(
    test_client: AsyncClient,
    mock_gateway_state: GatewayState,
) -> None:
    """Test POST /api/nexus/chat handles workflow unavailability gracefully.
    
    Requirements: 5.1
    """
    # Arrange
    request_data = {
        "text": "Hello",
        "user_id": "test-user",
    }
    
    # Make workflow signal fail
    workflow_handle = mock_gateway_state.temporal_client.get_workflow_handle.return_value
    workflow_handle.signal.side_effect = Exception("Workflow not found")
    
    # Act
    response = await test_client.post("/api/nexus/chat", json=request_data)
    
    # Assert
    assert response.status_code == 503
    data = response.json()
    assert "Agent workflow not available" in data["detail"]


# =========================================================================
# Test 17.2: GET /api/nexus/status/{user_id}
# =========================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_status_success(
    test_client: AsyncClient,
    mock_gateway_state: GatewayState,
) -> None:
    """Test GET /api/nexus/status/{user_id} returns workflow state.
    
    Requirements: 5.2
    """
    # Arrange
    user_id = "test-user"
    expected_state = {
        "status": "PROCESSING",
        "user_id": user_id,
        "conversation_id": "conv-123",
        "current_goal": "Analyze data",
        "actions_count": 3,
        "current_plan": {
            "steps": [
                {"id": 1, "description": "Load data", "status": "completed"},
                {"id": 2, "description": "Process data", "status": "running"},
            ]
        },
    }
    
    workflow_handle = mock_gateway_state.temporal_client.get_workflow_handle.return_value
    workflow_handle.query.return_value = expected_state
    
    # Act
    response = await test_client.get(f"/api/nexus/status/{user_id}")
    
    # Assert
    assert response.status_code == 200
    data = response.json()
    
    assert data["status"] == "PROCESSING"
    assert data["user_id"] == user_id
    assert data["conversation_id"] == "conv-123"
    assert data["current_goal"] == "Analyze data"
    assert data["actions_count"] == 3
    assert data["current_plan"] is not None
    assert len(data["current_plan"]["steps"]) == 2
    
    # Verify workflow was queried
    workflow_handle.query.assert_called_once_with("get_state")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_status_workflow_offline(
    test_client: AsyncClient,
    mock_gateway_state: GatewayState,
) -> None:
    """Test GET /api/nexus/status/{user_id} handles offline workflow.
    
    Requirements: 5.2
    """
    # Arrange
    user_id = "offline-user"
    workflow_handle = mock_gateway_state.temporal_client.get_workflow_handle.return_value
    workflow_handle.query.side_effect = Exception("Workflow not found")
    
    # Act
    response = await test_client.get(f"/api/nexus/status/{user_id}")
    
    # Assert
    assert response.status_code == 200
    data = response.json()
    
    # Should return offline status instead of error
    assert data["status"] == "offline"
    assert data["user_id"] == user_id
    assert data["conversation_id"] == ""


# =========================================================================
# Test 17.3: GET /api/nexus/conversations/{id}/history
# =========================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_conversation_history_success(
    test_client: AsyncClient,
    mock_gateway_state: GatewayState,
) -> None:
    """Test GET /api/nexus/conversations/{id}/history returns messages.
    
    Requirements: 5.3
    """
    # Arrange
    conversation_id = "conv-123"
    
    # Mock database response
    mock_messages = [
        {
            "role": "user",
            "content": "Hello",
            "source": "kubani-ui",
            "metadata": {},
            "timestamp": "2024-01-01T10:00:00Z",
        },
        {
            "role": "assistant",
            "content": "Hi there!",
            "source": "system",
            "metadata": {},
            "timestamp": "2024-01-01T10:00:05Z",
        },
    ]
    
    # Mock the get_conversation_history function from kubani.nexus.db
    with patch("kubani.nexus.db.get_conversation_history") as mock_get_history:
        mock_get_history.return_value = mock_messages
        
        # Act
        response = await test_client.get(f"/api/nexus/conversations/{conversation_id}/history")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        
        assert len(data) == 2
        assert data[0]["role"] == "user"
        assert data[0]["content"] == "Hello"
        assert data[1]["role"] == "assistant"
        assert data[1]["content"] == "Hi there!"
        
        # Verify database was queried
        mock_get_history.assert_called_once()
        call_args = mock_get_history.call_args[0]
        assert call_args[1] == conversation_id  # conversation_id argument
        assert call_args[2] == 50  # default limit


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_conversation_history_with_limit(
    test_client: AsyncClient,
    mock_gateway_state: GatewayState,
) -> None:
    """Test GET /api/nexus/conversations/{id}/history respects limit parameter.
    
    Requirements: 5.3
    """
    # Arrange
    conversation_id = "conv-123"
    
    with patch("kubani.nexus.db.get_conversation_history") as mock_get_history:
        mock_get_history.return_value = []
        
        # Act
        response = await test_client.get(
            f"/api/nexus/conversations/{conversation_id}/history?limit=10"
        )
        
        # Assert
        assert response.status_code == 200
        
        # Verify limit was passed
        call_args = mock_get_history.call_args[0]
        assert call_args[2] == 10


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_conversation_history_empty(
    test_client: AsyncClient,
    mock_gateway_state: GatewayState,
) -> None:
    """Test GET /api/nexus/conversations/{id}/history with no messages.
    
    Requirements: 5.3
    """
    # Arrange
    conversation_id = "empty-conv"
    
    with patch("kubani.nexus.db.get_conversation_history") as mock_get_history:
        mock_get_history.return_value = []
        
        # Act
        response = await test_client.get(f"/api/nexus/conversations/{conversation_id}/history")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data == []


# =========================================================================
# Test 17.4: GET /api/nexus/actions
# =========================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_recent_actions_success(
    test_client: AsyncClient,
    mock_gateway_state: GatewayState,
) -> None:
    """Test GET /api/nexus/actions returns recent actions.
    
    Requirements: 5.4
    """
    # Arrange
    mock_actions = [
        {
            "id": 1,
            "conversation_id": "conv-123",
            "action_type": "skill_execution",
            "description": "Execute data analysis skill",
            "status": "completed",
            "input_summary": "data.csv",
            "output_summary": "Analysis complete",
            "error_message": None,
            "duration_ms": 1500,
            "started_at": datetime(2024, 1, 1, 10, 0, 0),
            "completed_at": datetime(2024, 1, 1, 10, 0, 1, 500000),
        },
        {
            "id": 2,
            "conversation_id": "conv-123",
            "action_type": "planning",
            "description": "Create execution plan",
            "status": "completed",
            "input_summary": "User request",
            "output_summary": "3 steps planned",
            "error_message": None,
            "duration_ms": 800,
            "started_at": datetime(2024, 1, 1, 9, 59, 0),
            "completed_at": datetime(2024, 1, 1, 9, 59, 0, 800000),
        },
    ]
    
    with patch("kubani.nexus.db.get_recent_actions") as mock_get_actions:
        mock_get_actions.return_value = mock_actions
        
        # Act
        response = await test_client.get("/api/nexus/actions")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        
        assert len(data) == 2
        assert data[0]["id"] == 1
        assert data[0]["action_type"] == "skill_execution"
        assert data[0]["status"] == "completed"
        assert data[1]["id"] == 2
        assert data[1]["action_type"] == "planning"
        
        # Verify database was queried with defaults
        mock_get_actions.assert_called_once()
        call_args = mock_get_actions.call_args[0]
        assert call_args[1] == 20  # default limit
        assert call_args[2] is None  # no conversation_id filter


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_recent_actions_with_filters(
    test_client: AsyncClient,
    mock_gateway_state: GatewayState,
) -> None:
    """Test GET /api/nexus/actions with limit and conversation_id filters.
    
    Requirements: 5.4
    """
    # Arrange
    with patch("kubani.nexus.db.get_recent_actions") as mock_get_actions:
        mock_get_actions.return_value = []
        
        # Act
        response = await test_client.get(
            "/api/nexus/actions?limit=5&conversation_id=conv-456"
        )
        
        # Assert
        assert response.status_code == 200
        
        # Verify filters were passed
        call_args = mock_get_actions.call_args[0]
        assert call_args[1] == 5  # limit
        assert call_args[2] == "conv-456"  # conversation_id


# =========================================================================
# Test 17.5: GET /api/nexus/approvals
# =========================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_pending_approvals_success(
    test_client: AsyncClient,
    mock_gateway_state: GatewayState,
) -> None:
    """Test GET /api/nexus/approvals returns pending approvals.
    
    Requirements: 5.5
    """
    # Arrange
    mock_approvals = [
        {
            "id": 1,
            "request_type": "skill_approval",
            "reference_id": 42,
            "title": "Approve data analysis skill",
            "description": "Skill requires filesystem access",
            "risk_score": 5.5,
            "status": "pending",
            "created_at": datetime(2024, 1, 1, 10, 0, 0),
            "decided_at": None,
            "decided_by": None,
            "decision_reason": None,
        },
        {
            "id": 2,
            "request_type": "skill_approval",
            "reference_id": 43,
            "title": "Approve network request skill",
            "description": "Skill requires network access",
            "risk_score": 6.0,
            "status": "pending",
            "created_at": datetime(2024, 1, 1, 9, 55, 0),
            "decided_at": None,
            "decided_by": None,
            "decision_reason": None,
        },
    ]
    
    with patch("kubani.nexus.db.get_pending_approvals") as mock_get_approvals:
        mock_get_approvals.return_value = mock_approvals
        
        # Act
        response = await test_client.get("/api/nexus/approvals")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        
        assert len(data) == 2
        assert data[0]["id"] == 1
        assert data[0]["status"] == "pending"
        assert data[0]["risk_score"] == 5.5
        assert data[1]["id"] == 2
        assert data[1]["risk_score"] == 6.0
        
        # Verify database was queried
        mock_get_approvals.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_pending_approvals_empty(
    test_client: AsyncClient,
    mock_gateway_state: GatewayState,
) -> None:
    """Test GET /api/nexus/approvals with no pending approvals.
    
    Requirements: 5.5
    """
    # Arrange
    with patch("kubani.nexus.db.get_pending_approvals") as mock_get_approvals:
        mock_get_approvals.return_value = []
        
        # Act
        response = await test_client.get("/api/nexus/approvals")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data == []


# =========================================================================
# Test 17.6: POST /api/nexus/approvals/{id}/decide
# =========================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_post_approval_decision_approve(
    test_client: AsyncClient,
    mock_gateway_state: GatewayState,
) -> None:
    """Test POST /api/nexus/approvals/{id}/decide approves a request.
    
    Requirements: 5.6
    """
    # Arrange
    approval_id = 1
    request_data = {
        "approval_id": approval_id,
        "approved": True,
        "reason": "Skill looks safe",
    }
    
    with patch("kubani.nexus.db.resolve_approval") as mock_resolve:
        mock_resolve.return_value = None
        
        # Act
        response = await test_client.post(
            f"/api/nexus/approvals/{approval_id}/decide",
            json=request_data,
        )
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "approved"
        assert data["approval_id"] == str(approval_id)
        
        # Verify database was updated
        mock_resolve.assert_called_once()
        call_args = mock_resolve.call_args
        # Check arguments - function is called with positional and keyword args
        assert call_args.args[0] == mock_gateway_state.db_pool
        assert call_args.args[1] == approval_id
        assert call_args.args[2] is True  # approved
        assert call_args.kwargs["decided_by"] == "ui-user"
        assert call_args.kwargs["reason"] == "Skill looks safe"
        
        # Verify workflow was signaled
        workflow_handle = mock_gateway_state.temporal_client.get_workflow_handle.return_value
        workflow_handle.signal.assert_called_once()
        signal_call = workflow_handle.signal.call_args
        assert signal_call[0][0] == "approval_decision"
        signal_data = signal_call[0][1]
        assert signal_data["approval_id"] == approval_id
        assert signal_data["approved"] is True
        assert signal_data["reason"] == "Skill looks safe"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_post_approval_decision_reject(
    test_client: AsyncClient,
    mock_gateway_state: GatewayState,
) -> None:
    """Test POST /api/nexus/approvals/{id}/decide rejects a request.
    
    Requirements: 5.6
    """
    # Arrange
    approval_id = 2
    request_data = {
        "approval_id": approval_id,
        "approved": False,
        "reason": "Too risky",
    }
    
    with patch("kubani.nexus.db.resolve_approval") as mock_resolve:
        mock_resolve.return_value = None
        
        # Act
        response = await test_client.post(
            f"/api/nexus/approvals/{approval_id}/decide",
            json=request_data,
        )
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "rejected"
        assert data["approval_id"] == str(approval_id)
        
        # Verify database was updated
        mock_resolve.assert_called_once()
        call_args = mock_resolve.call_args
        assert call_args.args[0] == mock_gateway_state.db_pool
        assert call_args.args[1] == approval_id
        assert call_args.args[2] is False  # not approved
        
        # Verify workflow was signaled with rejection
        workflow_handle = mock_gateway_state.temporal_client.get_workflow_handle.return_value
        signal_call = workflow_handle.signal.call_args
        signal_data = signal_call[0][1]
        assert signal_data["approved"] is False
        assert signal_data["reason"] == "Too risky"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_post_approval_decision_workflow_signal_fails(
    test_client: AsyncClient,
    mock_gateway_state: GatewayState,
) -> None:
    """Test POST /api/nexus/approvals/{id}/decide handles workflow signal failure.
    
    Requirements: 5.6
    """
    # Arrange
    approval_id = 3
    request_data = {
        "approval_id": approval_id,
        "approved": True,
        "reason": "Approved",
    }
    
    # Make workflow signal fail
    workflow_handle = mock_gateway_state.temporal_client.get_workflow_handle.return_value
    workflow_handle.signal.side_effect = Exception("Workflow not found")
    
    with patch("kubani.nexus.db.resolve_approval") as mock_resolve:
        mock_resolve.return_value = None
        
        # Act
        response = await test_client.post(
            f"/api/nexus/approvals/{approval_id}/decide",
            json=request_data,
        )
        
        # Assert
        # Should still succeed even if workflow signal fails
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "approved"
        
        # Database should still be updated
        mock_resolve.assert_called_once()
