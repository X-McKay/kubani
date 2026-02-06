"""Nexus Conversational Gateway.

A FastAPI application that serves as the unified entry point for all
user interactions with the Nexus agent. It handles:

1. WebSocket connections from the Kubani UI for real-time chat.
2. REST endpoints for the UI to query agent status, actions, and history.
3. Discord message ingestion (via webhook or polling).
4. Routing agent responses back to the correct client via Redis pub/sub.

Architecture:
    User (UI/Discord) → Gateway → Temporal Signal → Orchestrator Workflow
    Orchestrator Workflow → Redis Pub/Sub → Gateway → User (UI/Discord)

Usage:
    uvicorn kubani.nexus.gateway.app:create_app --factory --host 0.0.0.0 --port 8090
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# =========================================================================
# Request/Response Models
# =========================================================================


class ChatRequest(BaseModel):
    """REST endpoint request for sending a message."""

    text: str
    conversation_id: str | None = None
    user_id: str = "default"
    source: str = "kubani-ui"


class ChatResponse(BaseModel):
    """REST endpoint response after queuing a message."""

    conversation_id: str
    status: str = "queued"
    message: str = "Message sent to Nexus agent"


class StatusResponse(BaseModel):
    """Agent status response."""

    status: str
    user_id: str
    conversation_id: str
    current_goal: str | None = None
    actions_count: int = 0
    current_plan: dict[str, Any] | None = None


class ActionRecord(BaseModel):
    """A single agent action for the UI."""

    id: int
    action_type: str
    description: str
    status: str
    duration_ms: int | None = None
    started_at: str
    completed_at: str | None = None


class ApprovalRequest(BaseModel):
    """Request to approve or reject a pending item."""

    approval_id: int
    approved: bool
    reason: str = ""


# =========================================================================
# Application State
# =========================================================================


class GatewayState:
    """Shared application state for the Gateway.

    Holds connections to Temporal, Redis, and PostgreSQL.
    Initialized during app startup and cleaned up on shutdown.
    """

    def __init__(self) -> None:
        self.temporal_client: Any = None
        self.pubsub: Any = None
        self.db_pool: Any = None
        self.active_websockets: dict[str, list[WebSocket]] = {}

    async def initialize(self) -> None:
        """Initialize all connections."""
        from temporalio.client import Client

        from kubani.nexus.pubsub import NexusPubSub

        temporal_host = os.environ.get("TEMPORAL_HOST", "localhost:7233")
        temporal_namespace = os.environ.get("TEMPORAL_NAMESPACE", "nexus")
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        db_url = os.environ.get(
            "NEXUS_DATABASE_URL",
            "postgresql://kubani:kubani@localhost:5432/kubani_nexus",
        )

        logger.info(f"Connecting to Temporal at {temporal_host}")
        self.temporal_client = await Client.connect(
            temporal_host, namespace=temporal_namespace
        )

        logger.info(f"Connecting to Redis at {redis_url}")
        self.pubsub = NexusPubSub(redis_url=redis_url)
        await self.pubsub.connect()

        logger.info(f"Connecting to PostgreSQL")
        from kubani.nexus.db import create_pool

        self.db_pool = await create_pool(db_url)

        logger.info("Gateway state initialized")

    async def cleanup(self) -> None:
        """Clean up all connections."""
        if self.pubsub:
            await self.pubsub.close()
        if self.db_pool:
            await self.db_pool.close()
        logger.info("Gateway state cleaned up")

    async def signal_workflow(
        self, user_id: str, signal_name: str, data: dict[str, Any]
    ) -> None:
        """Send a signal to the Nexus workflow for a user.

        Args:
            user_id: The user whose workflow to signal.
            signal_name: The signal name (e.g., 'user_message').
            data: The signal payload.
        """
        workflow_id = f"nexus-{user_id}"
        handle = self.temporal_client.get_workflow_handle(workflow_id)
        await handle.signal(signal_name, data)

    async def query_workflow(
        self, user_id: str, query_name: str
    ) -> dict[str, Any]:
        """Query the Nexus workflow state.

        Args:
            user_id: The user whose workflow to query.
            query_name: The query name (e.g., 'get_state').

        Returns:
            The query result.
        """
        workflow_id = f"nexus-{user_id}"
        handle = self.temporal_client.get_workflow_handle(workflow_id)
        return await handle.query(query_name)


# Global state instance
_state = GatewayState()


# =========================================================================
# Application Factory
# =========================================================================


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan handler for startup/shutdown."""
    await _state.initialize()
    yield
    await _state.cleanup()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI app instance.
    """
    app = FastAPI(
        title="Kubani Nexus Gateway",
        description="Conversational gateway for the Kubani Nexus agent",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configured per-environment in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routes
    app.include_router(_create_chat_router())
    app.include_router(_create_status_router())
    app.include_router(_create_actions_router())
    app.include_router(_create_approvals_router())
    app.include_router(_create_ws_router())

    return app


# =========================================================================
# Chat Routes
# =========================================================================


def _create_chat_router():
    from fastapi import APIRouter

    router = APIRouter(prefix="/api/nexus", tags=["chat"])

    @router.post("/chat", response_model=ChatResponse)
    async def send_message(request: ChatRequest) -> ChatResponse:
        """Send a message to the Nexus agent.

        This endpoint normalizes the message, signals the Temporal workflow,
        and returns immediately. The actual response will arrive via WebSocket
        or can be polled from the conversation history endpoint.
        """
        conversation_id = request.conversation_id or str(uuid.uuid4())

        from kubani.nexus.models.messages import MessageSource, UserMessage

        user_message = UserMessage(
            source=MessageSource(request.source),
            user_id=request.user_id,
            conversation_id=conversation_id,
            text=request.text,
        )

        try:
            await _state.signal_workflow(
                request.user_id, "user_message", user_message.to_dict()
            )
        except Exception as e:
            logger.error(f"Failed to signal workflow: {e}")
            raise HTTPException(
                status_code=503,
                detail=f"Agent workflow not available: {e}",
            )

        return ChatResponse(
            conversation_id=conversation_id,
            status="queued",
            message="Message sent to Nexus agent",
        )

    @router.get("/conversations/{conversation_id}/history")
    async def get_history(
        conversation_id: str,
        limit: int = Query(default=50, le=200),
    ) -> list[dict[str, Any]]:
        """Get conversation history from the database."""
        from kubani.nexus.db import get_conversation_history

        return await get_conversation_history(
            _state.db_pool, conversation_id, limit
        )

    return router


# =========================================================================
# Status Routes
# =========================================================================


def _create_status_router():
    from fastapi import APIRouter

    router = APIRouter(prefix="/api/nexus", tags=["status"])

    @router.get("/status/{user_id}", response_model=StatusResponse)
    async def get_status(user_id: str) -> StatusResponse:
        """Get the current status of the Nexus agent for a user."""
        try:
            state = await _state.query_workflow(user_id, "get_state")
            return StatusResponse(
                status=state.get("status", "unknown"),
                user_id=state.get("user_id", user_id),
                conversation_id=state.get("conversation_id", ""),
                current_goal=state.get("current_goal"),
                actions_count=state.get("actions_count", 0),
                current_plan=state.get("current_plan"),
            )
        except Exception as e:
            logger.warning(f"Failed to query workflow state: {e}")
            return StatusResponse(
                status="offline",
                user_id=user_id,
                conversation_id="",
            )

    @router.get("/health")
    async def health_check() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "healthy", "service": "nexus-gateway"}

    return router


# =========================================================================
# Actions Routes
# =========================================================================


def _create_actions_router():
    from fastapi import APIRouter

    router = APIRouter(prefix="/api/nexus", tags=["actions"])

    @router.get("/actions")
    async def get_recent_actions(
        limit: int = Query(default=20, le=100),
        conversation_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get recent agent actions for the UI monitoring panel."""
        from kubani.nexus.db import get_recent_actions

        return await get_recent_actions(
            _state.db_pool, limit, conversation_id
        )

    return router


# =========================================================================
# Approvals Routes
# =========================================================================


def _create_approvals_router():
    from fastapi import APIRouter

    router = APIRouter(prefix="/api/nexus", tags=["approvals"])

    @router.get("/approvals")
    async def get_pending_approvals() -> list[dict[str, Any]]:
        """Get all pending approval requests."""
        from kubani.nexus.db import get_pending_approvals

        return await get_pending_approvals(_state.db_pool)

    @router.post("/approvals/{approval_id}/decide")
    async def decide_approval(
        approval_id: int, request: ApprovalRequest
    ) -> dict[str, str]:
        """Approve or reject a pending approval request."""
        from kubani.nexus.db import resolve_approval

        await resolve_approval(
            _state.db_pool,
            approval_id,
            request.approved,
            decided_by="ui-user",
            reason=request.reason,
        )

        # Signal the workflow about the decision
        try:
            await _state.signal_workflow(
                "default",
                "approval_decision",
                {
                    "approval_id": approval_id,
                    "approved": request.approved,
                    "reason": request.reason,
                },
            )
        except Exception as e:
            logger.warning(f"Failed to signal approval decision: {e}")

        status = "approved" if request.approved else "rejected"
        return {"status": status, "approval_id": str(approval_id)}

    return router


# =========================================================================
# WebSocket Routes
# =========================================================================


def _create_ws_router():
    from fastapi import APIRouter

    router = APIRouter(tags=["websocket"])

    @router.websocket("/ws/nexus/{conversation_id}")
    async def websocket_endpoint(
        websocket: WebSocket, conversation_id: str
    ) -> None:
        """WebSocket endpoint for real-time chat.

        This endpoint:
        1. Accepts the WebSocket connection.
        2. Subscribes to Redis pub/sub for agent responses.
        3. Listens for user messages from the WebSocket.
        4. Forwards user messages to the Temporal workflow via signal.
        5. Forwards agent responses from Redis to the WebSocket.
        """
        await websocket.accept()

        # Track the connection
        if conversation_id not in _state.active_websockets:
            _state.active_websockets[conversation_id] = []
        _state.active_websockets[conversation_id].append(websocket)

        logger.info(f"WebSocket connected for conversation {conversation_id}")

        # Create tasks for bidirectional communication
        receive_task = asyncio.create_task(
            _ws_receive_loop(websocket, conversation_id)
        )
        publish_task = asyncio.create_task(
            _ws_publish_loop(websocket, conversation_id)
        )

        try:
            # Wait for either task to complete (usually due to disconnect)
            done, pending = await asyncio.wait(
                [receive_task, publish_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            # Clean up
            if conversation_id in _state.active_websockets:
                _state.active_websockets[conversation_id].remove(websocket)
                if not _state.active_websockets[conversation_id]:
                    del _state.active_websockets[conversation_id]
            logger.info(
                f"WebSocket disconnected for conversation {conversation_id}"
            )

    return router


async def _ws_receive_loop(
    websocket: WebSocket, conversation_id: str
) -> None:
    """Receive messages from the WebSocket and forward to the workflow.

    Args:
        websocket: The WebSocket connection.
        conversation_id: The conversation ID.
    """
    try:
        while True:
            data = await websocket.receive_json()
            text = data.get("text", "")
            user_id = data.get("user_id", "default")

            if not text:
                continue

            from kubani.nexus.models.messages import MessageSource, UserMessage

            user_message = UserMessage(
                source=MessageSource.KUBANI_UI,
                user_id=user_id,
                conversation_id=conversation_id,
                text=text,
            )

            await _state.signal_workflow(
                user_id, "user_message", user_message.to_dict()
            )
    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected: {conversation_id}")
    except Exception as e:
        logger.error(f"WebSocket receive error: {e}")


async def _ws_publish_loop(
    websocket: WebSocket, conversation_id: str
) -> None:
    """Subscribe to Redis pub/sub and forward responses to the WebSocket.

    Args:
        websocket: The WebSocket connection.
        conversation_id: The conversation ID.
    """
    try:
        async for message in _state.pubsub.subscribe_responses(conversation_id):
            await websocket.send_json(message)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket publish error: {e}")
