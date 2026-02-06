"""Tests for the Nexus Gateway REST API.

Uses FastAPI's TestClient for synchronous testing of the REST endpoints.
Mocks the Temporal and Redis dependencies to test the Gateway logic
in isolation.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient


@pytest.fixture
def mock_state():
    """Create a mock GatewayState for testing."""
    from kubani.nexus.gateway.app import _state

    # Save original state
    original_temporal = _state.temporal_client
    original_pubsub = _state.pubsub
    original_db = _state.db_pool

    # Set up mocks
    _state.temporal_client = MagicMock()
    _state.pubsub = MagicMock()
    _state.db_pool = MagicMock()

    # Mock the signal_workflow method
    _state.signal_workflow = AsyncMock()
    _state.query_workflow = AsyncMock(return_value={
        "status": "idle",
        "user_id": "test-user",
        "conversation_id": "test-conv",
        "current_goal": None,
        "actions_count": 0,
        "current_plan": None,
    })

    yield _state

    # Restore original state
    _state.temporal_client = original_temporal
    _state.pubsub = original_pubsub
    _state.db_pool = original_db


@pytest.fixture
def client(mock_state):
    """Create a FastAPI test client."""
    from kubani.nexus.gateway.app import create_app

    app = create_app()

    # Override the lifespan to skip real connections
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def test_lifespan(app):
        yield

    app.router.lifespan_context = test_lifespan

    return TestClient(app)


class TestHealthEndpoint:
    """Test the health check endpoint."""

    def test_health_check(self, client):
        response = client.get("/api/nexus/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "nexus-gateway"


class TestChatEndpoint:
    """Test the chat message endpoint."""

    def test_send_message(self, client, mock_state):
        response = client.post(
            "/api/nexus/chat",
            json={
                "text": "Hello Nexus!",
                "user_id": "test-user",
                "source": "kubani-ui",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"
        assert "conversation_id" in data

    def test_send_message_with_conversation_id(self, client, mock_state):
        response = client.post(
            "/api/nexus/chat",
            json={
                "text": "Follow-up message",
                "conversation_id": "existing-conv-123",
                "user_id": "test-user",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["conversation_id"] == "existing-conv-123"

    def test_send_message_signals_workflow(self, client, mock_state):
        client.post(
            "/api/nexus/chat",
            json={"text": "Test", "user_id": "test-user"},
        )
        mock_state.signal_workflow.assert_called_once()

    def test_send_message_workflow_unavailable(self, client, mock_state):
        mock_state.signal_workflow = AsyncMock(
            side_effect=Exception("Workflow not found")
        )
        response = client.post(
            "/api/nexus/chat",
            json={"text": "Test", "user_id": "test-user"},
        )
        assert response.status_code == 503


class TestStatusEndpoint:
    """Test the status query endpoint."""

    def test_get_status(self, client, mock_state):
        response = client.get("/api/nexus/status/test-user")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "idle"
        assert data["user_id"] == "test-user"

    def test_get_status_offline(self, client, mock_state):
        mock_state.query_workflow = AsyncMock(
            side_effect=Exception("Workflow not found")
        )
        response = client.get("/api/nexus/status/unknown-user")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "offline"


class TestActionsEndpoint:
    """Test the actions query endpoint."""

    def test_get_recent_actions(self, client, mock_state):
        # Mock the database query
        with patch("kubani.nexus.db.get_recent_actions", new_callable=AsyncMock) as mock_actions:
            mock_actions.return_value = [
                {
                    "id": 1,
                    "action_type": "planning",
                    "description": "Planning response",
                    "status": "completed",
                    "duration_ms": 500,
                    "started_at": "2025-01-01T00:00:00Z",
                    "completed_at": "2025-01-01T00:00:01Z",
                }
            ]
            response = client.get("/api/nexus/actions?limit=10")
            assert response.status_code == 200


class TestApprovalsEndpoint:
    """Test the approvals endpoint."""

    def test_get_pending_approvals(self, client, mock_state):
        with patch("kubani.nexus.db.get_pending_approvals", new_callable=AsyncMock) as mock_approvals:
            mock_approvals.return_value = [
                {
                    "id": 1,
                    "request_type": "skill_approval",
                    "subject": "web/new-skill@0.1.0",
                    "description": "New skill needs review",
                    "risk_level": "medium",
                    "status": "pending",
                }
            ]
            response = client.get("/api/nexus/approvals")
            assert response.status_code == 200

    def test_approve_request(self, client, mock_state):
        with patch("kubani.nexus.db.resolve_approval", new_callable=AsyncMock):
            response = client.post(
                "/api/nexus/approvals/1/decide",
                json={
                    "approval_id": 1,
                    "approved": True,
                    "reason": "Looks good",
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "approved"
