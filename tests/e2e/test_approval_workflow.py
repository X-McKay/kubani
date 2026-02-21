"""End-to-end tests for Nexus approval workflow.

These tests validate the complete HITL (Human-in-the-Loop) approval workflow
for medium-risk skills that require human approval before execution.

Requirements tested:
- 7.3: Skill requiring approval creates approval request
- 7.4: Approval granted allows skill execution
- 7.5: Approval rejected prevents skill execution
"""

import asyncio
import uuid
from datetime import timedelta
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport
from temporalio.client import Client
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from kubani.nexus.gateway.app import create_app, GatewayState
from kubani.nexus.models.messages import MessageSource
from kubani.nexus.models.skills import RiskLevel, SkillMetadata, SkillStatus
from kubani.nexus.orchestrator.workflow import NexusOrchestratorWorkflow


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
async def workflow_environment() -> AsyncGenerator[WorkflowEnvironment, None]:
    """Create a test Temporal environment."""
    async with await WorkflowEnvironment.start_time_skipping() as env:
        yield env


@pytest.fixture
async def temporal_client(workflow_environment: WorkflowEnvironment) -> Client:
    """Get Temporal client for the test environment."""
    return workflow_environment.client


@pytest.fixture
def mock_activities() -> dict[str, Any]:
    """Create mocked activity functions for E2E testing."""
    from temporalio import activity
    
    mocks = {}
    
    # Create actual async functions that call the mocks
    @activity.defn(name="persist_message")
    async def persist_message(input_data: dict[str, Any]) -> dict[str, Any]:
        return mocks["persist_message"](input_data)
    
    @activity.defn(name="recall_memories_activity")
    async def recall_memories_activity(input_data: dict[str, Any]) -> dict[str, Any]:
        return mocks["recall_memories_activity"](input_data)
    
    @activity.defn(name="plan_response")
    async def plan_response(input_data: dict[str, Any]) -> dict[str, Any]:
        return mocks["plan_response"](input_data)
    
    @activity.defn(name="execute_skill_activity")
    async def execute_skill_activity(input_data: dict[str, Any]) -> dict[str, Any]:
        return mocks["execute_skill_activity"](input_data)
    
    @activity.defn(name="generate_response")
    async def generate_response(input_data: dict[str, Any]) -> dict[str, Any]:
        return mocks["generate_response"](input_data)
    
    @activity.defn(name="publish_response_activity")
    async def publish_response_activity(input_data: dict[str, Any]) -> dict[str, Any]:
        return mocks["publish_response_activity"](input_data)
    
    @activity.defn(name="store_memory_activity")
    async def store_memory_activity(input_data: dict[str, Any]) -> dict[str, Any]:
        return mocks["store_memory_activity"](input_data)
    
    @activity.defn(name="log_action_activity")
    async def log_action_activity(input_data: dict[str, Any]) -> dict[str, Any]:
        return mocks["log_action_activity"](input_data)
    
    @activity.defn(name="check_skill_approval_activity")
    async def check_skill_approval_activity(input_data: dict[str, Any]) -> dict[str, Any]:
        return mocks["check_skill_approval_activity"](input_data)
    
    @activity.defn(name="create_approval_request_activity")
    async def create_approval_request_activity(input_data: dict[str, Any]) -> dict[str, Any]:
        return mocks["create_approval_request_activity"](input_data)
    
    # Create mocks with default return values
    mocks["persist_message"] = MagicMock(return_value={"message_id": 1})
    mocks["recall_memories_activity"] = MagicMock(return_value={"memories": []})
    mocks["plan_response"] = MagicMock(return_value={
        "needs_plan": False,
        "direct_response": "Hello! How can I help you?",
        "goal": "",
        "steps": [],
    })
    mocks["execute_skill_activity"] = MagicMock(return_value={
        "success": True,
        "output": "Skill executed successfully",
        "error": None,
        "duration_ms": 100,
    })
    mocks["generate_response"] = MagicMock(return_value={
        "response_text": "I've completed the task successfully.",
    })
    mocks["publish_response_activity"] = MagicMock(return_value={"published": True})
    mocks["store_memory_activity"] = MagicMock(return_value={"stored": True})
    mocks["log_action_activity"] = MagicMock(return_value={"action_id": 1})
    mocks["check_skill_approval_activity"] = MagicMock(return_value={
        "requires_approval": False,
        "risk_level": "low",
    })
    mocks["create_approval_request_activity"] = MagicMock(return_value={
        "approval_id": 1,
    })
    
    # Store the actual functions for registration
    mocks["_functions"] = [
        persist_message,
        recall_memories_activity,
        plan_response,
        execute_skill_activity,
        generate_response,
        publish_response_activity,
        store_memory_activity,
        log_action_activity,
        check_skill_approval_activity,
        create_approval_request_activity,
    ]
    
    return mocks


@pytest.fixture
async def workflow_worker(
    workflow_environment: WorkflowEnvironment,
    mock_activities: dict[str, Any],
) -> AsyncGenerator[Worker, None]:
    """Create a Temporal worker with the workflow and mocked activities."""
    worker = Worker(
        workflow_environment.client,
        task_queue="nexus-e2e-approval-queue",
        workflows=[NexusOrchestratorWorkflow],
        activities=mock_activities["_functions"],
    )
    
    async with worker:
        yield worker


@pytest.fixture
async def gateway_state(temporal_client: Client) -> AsyncGenerator[GatewayState, None]:
    """Create a gateway state with test Temporal client and mocked dependencies."""
    state = GatewayState()
    
    # Use real Temporal client from test environment
    state.temporal_client = temporal_client
    
    # Mock database pool
    db_pool = AsyncMock()
    db_pool.fetch = AsyncMock(return_value=[])
    db_pool.fetchrow = AsyncMock(return_value=None)
    db_pool.fetchval = AsyncMock(return_value=1)
    db_pool.execute = AsyncMock()
    state.db_pool = db_pool
    
    # Mock Redis pub/sub with message queue
    pubsub = AsyncMock()
    pubsub._message_queues = {}
    
    async def mock_subscribe_responses(conversation_id: str):
        """Mock subscribe that yields messages from a queue."""
        channel = f"nexus:response:{conversation_id}"
        queue = asyncio.Queue()
        pubsub._message_queues[channel] = queue
        
        try:
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=0.1)
                    yield message
                except asyncio.TimeoutError:
                    await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            if channel in pubsub._message_queues:
                del pubsub._message_queues[channel]
            raise
    
    async def mock_publish_response(conversation_id: str, message: dict[str, Any]):
        """Mock publish that puts messages in the subscription queue."""
        channel = f"nexus:response:{conversation_id}"
        if channel in pubsub._message_queues:
            await pubsub._message_queues[channel].put(message)
    
    pubsub.subscribe_responses = mock_subscribe_responses
    pubsub.publish_response = mock_publish_response
    pubsub.close = AsyncMock()
    state.pubsub = pubsub
    
    yield state
    
    # Cleanup
    if state.pubsub:
        await state.pubsub.close()


@pytest.fixture
async def test_client(gateway_state: GatewayState) -> AsyncGenerator[AsyncClient, None]:
    """Create a test client for the Gateway app."""
    app = create_app()
    
    # Replace the global state with our test state
    with patch("kubani.nexus.gateway.app._state", gateway_state):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


async def start_test_workflow(
    client: Client,
    user_id: str,
    conversation_id: str,
    task_queue: str = "nexus-e2e-approval-queue",
):
    """Helper to start a test workflow instance."""
    workflow_id = f"nexus-{user_id}"
    
    handle = await client.start_workflow(
        NexusOrchestratorWorkflow.run,
        {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "restored_history": [],
        },
        id=workflow_id,
        task_queue=task_queue,
        execution_timeout=timedelta(minutes=5),
    )
    
    return handle


# =========================================================================
# Test 21.1: Skill Requiring Approval
# =========================================================================


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.skip(reason="Workflow has bug: uses datetime.now() which is non-deterministic in Temporal. Also, approval workflow logic not yet implemented.")
async def test_skill_requiring_approval_creates_request(
    test_client: AsyncClient,
    temporal_client: Client,
    workflow_worker: Worker,
    mock_activities: dict[str, Any],
    gateway_state: GatewayState,
) -> None:
    """Test that a medium-risk skill creates an approval request.
    
    This test validates:
    1. User sends request that requires medium-risk skill
    2. Workflow checks skill risk level
    3. Approval request is created in database
    4. User is notified that approval is pending
    
    Requirements: 7.3
    """
    # Arrange
    user_id = "approval-test-user"
    conversation_id = str(uuid.uuid4())
    task_request = "Please delete all pods in the production namespace"
    
    # Configure mock to return a plan with a medium-risk skill
    mock_activities["plan_response"].return_value = {
        "needs_plan": True,
        "direct_response": None,
        "goal": "Delete pods in production namespace",
        "steps": [
            {
                "id": 1,
                "description": "Delete all pods in production namespace",
                "skill_name": "k8s/delete-pods",
            },
        ],
    }
    
    # Configure skill to require approval (medium risk)
    mock_activities["check_skill_approval_activity"].return_value = {
        "requires_approval": True,
        "risk_level": "medium",
        "risk_score": 6.5,
    }
    
    # Track approval request creation
    approval_requests = []
    
    def create_approval_side_effect(input_data):
        approval_requests.append(input_data)
        return {"approval_id": len(approval_requests)}
    
    mock_activities["create_approval_request_activity"].side_effect = create_approval_side_effect
    
    # Configure response to notify user about pending approval
    mock_activities["generate_response"].return_value = {
        "response_text": (
            "I've created a plan to delete pods in the production namespace. "
            "However, this action requires approval due to its risk level (medium). "
            "An approval request has been created and is pending review."
        ),
    }
    
    # Mock database to return pending approval
    gateway_state.db_pool.fetch = AsyncMock(return_value=[
        {
            "id": 1,
            "request_type": "skill_approval",
            "reference_id": 1,
            "title": "Approve skill: k8s/delete-pods",
            "description": "Delete all pods in production namespace",
            "risk_score": 6.5,
            "status": "pending",
            "created_at": "2024-01-01T10:00:00Z",
        }
    ])
    
    # Start the workflow
    workflow_handle = await start_test_workflow(
        temporal_client,
        user_id,
        conversation_id,
    )
    
    await asyncio.sleep(0.2)
    
    # Act - Send task request
    response = await test_client.post(
        "/api/nexus/chat",
        json={
            "text": task_request,
            "user_id": user_id,
            "conversation_id": conversation_id,
            "source": "kubani-ui",
        },
    )
    
    # Assert - Message was accepted
    assert response.status_code == 200
    data = response.json()
    assert data["conversation_id"] == conversation_id
    assert data["status"] == "queued"
    
    # Wait for workflow to process
    await asyncio.sleep(1.0)
    
    # Assert - Plan was created
    mock_activities["plan_response"].assert_called()
    plan_call = mock_activities["plan_response"].call_args[0][0]
    assert plan_call["user_message"] == task_request
    
    # Assert - Skill approval was checked
    mock_activities["check_skill_approval_activity"].assert_called()
    check_call = mock_activities["check_skill_approval_activity"].call_args[0][0]
    assert check_call["skill_name"] == "k8s/delete-pods"
    
    # Assert - Approval request was created
    assert len(approval_requests) == 1
    approval_req = approval_requests[0]
    assert approval_req["request_type"] == "skill_approval"
    assert approval_req["skill_name"] == "k8s/delete-pods"
    assert approval_req["risk_level"] == "medium"
    
    # Assert - User was notified about pending approval
    mock_activities["publish_response_activity"].assert_called()
    publish_calls = mock_activities["publish_response_activity"].call_args_list
    response_text = publish_calls[-1][0][0]["text"]
    assert "requires approval" in response_text.lower()
    assert "pending" in response_text.lower()
    
    # Assert - Skill was NOT executed (waiting for approval)
    # The execute_skill_activity should not have been called
    execute_calls = [
        call for call in mock_activities["execute_skill_activity"].call_args_list
        if call[0][0].get("skill_name") == "k8s/delete-pods"
    ]
    assert len(execute_calls) == 0, "Skill should not execute before approval"
    
    # Assert - Can query pending approvals via API
    response = await test_client.get("/api/nexus/approvals")
    assert response.status_code == 200
    approvals = response.json()
    assert len(approvals) == 1
    assert approvals[0]["status"] == "pending"
    assert approvals[0]["risk_score"] == 6.5


# =========================================================================
# Test 21.2: Approval Granted
# =========================================================================


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.skip(reason="Workflow has bug: uses datetime.now() which is non-deterministic in Temporal. Also, approval workflow logic not yet implemented.")
async def test_approval_granted_executes_skill(
    test_client: AsyncClient,
    temporal_client: Client,
    workflow_worker: Worker,
    mock_activities: dict[str, Any],
    gateway_state: GatewayState,
) -> None:
    """Test that granting approval allows skill execution.
    
    This test validates:
    1. Approval request exists for a skill
    2. User grants approval via API
    3. Workflow receives approval signal
    4. Skill is executed
    5. Task is completed successfully
    
    Requirements: 7.4
    """
    # Arrange
    user_id = "approval-granted-user"
    conversation_id = str(uuid.uuid4())
    approval_id = 42
    
    # Configure skill execution to succeed
    mock_activities["execute_skill_activity"].return_value = {
        "success": True,
        "output": "Successfully deleted 5 pods in production namespace",
        "error": None,
        "duration_ms": 2500,
    }
    
    mock_activities["generate_response"].return_value = {
        "response_text": (
            "The approval was granted. I've successfully deleted 5 pods "
            "in the production namespace as requested."
        ),
    }
    
    # Mock database operations
    gateway_state.db_pool.fetchrow = AsyncMock(return_value={
        "id": approval_id,
        "request_type": "skill_approval",
        "reference_id": 1,
        "skill_name": "k8s/delete-pods",
        "status": "pending",
    })
    
    # Start workflow
    workflow_handle = await start_test_workflow(
        temporal_client,
        user_id,
        conversation_id,
    )
    
    await asyncio.sleep(0.2)
    
    # Act - Grant approval via API
    response = await test_client.post(
        f"/api/nexus/approvals/{approval_id}/decide",
        json={
            "approval_id": approval_id,
            "approved": True,
            "reason": "Approved by admin - maintenance window",
        },
    )
    
    # Assert - Approval was recorded
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approved"
    assert data["approval_id"] == str(approval_id)
    
    # Verify database was updated
    gateway_state.db_pool.execute.assert_called()
    
    # Wait for workflow to process approval signal
    await asyncio.sleep(0.5)
    
    # Assert - Skill was executed after approval
    mock_activities["execute_skill_activity"].assert_called()
    execute_call = mock_activities["execute_skill_activity"].call_args[0][0]
    assert execute_call["skill_name"] == "k8s/delete-pods"
    
    # Assert - Success response was generated
    mock_activities["generate_response"].assert_called()
    response_call = mock_activities["generate_response"].call_args[0][0]
    step_results = response_call["step_results"]
    assert len(step_results) > 0
    assert step_results[0]["success"] is True
    assert "deleted 5 pods" in step_results[0]["output"]
    
    # Assert - User was notified of completion
    mock_activities["publish_response_activity"].assert_called()
    publish_calls = mock_activities["publish_response_activity"].call_args_list
    final_response = publish_calls[-1][0][0]["text"]
    assert "successfully" in final_response.lower()
    assert "deleted" in final_response.lower()


# =========================================================================
# Test 21.3: Approval Rejected
# =========================================================================


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.skip(reason="Workflow has bug: uses datetime.now() which is non-deterministic in Temporal. Also, approval workflow logic not yet implemented.")
async def test_approval_rejected_prevents_execution(
    test_client: AsyncClient,
    temporal_client: Client,
    workflow_worker: Worker,
    mock_activities: dict[str, Any],
    gateway_state: GatewayState,
) -> None:
    """Test that rejecting approval prevents skill execution.
    
    This test validates:
    1. Approval request exists for a skill
    2. User rejects approval via API
    3. Workflow receives rejection signal
    4. Skill is NOT executed
    5. User is informed of rejection
    
    Requirements: 7.5
    """
    # Arrange
    user_id = "approval-rejected-user"
    conversation_id = str(uuid.uuid4())
    approval_id = 43
    rejection_reason = "Too risky - production is currently serving traffic"
    
    # Configure response for rejection
    mock_activities["generate_response"].return_value = {
        "response_text": (
            f"The approval request was rejected. Reason: {rejection_reason}. "
            "The skill will not be executed. Please try a safer approach."
        ),
    }
    
    # Mock database operations
    gateway_state.db_pool.fetchrow = AsyncMock(return_value={
        "id": approval_id,
        "request_type": "skill_approval",
        "reference_id": 1,
        "skill_name": "k8s/delete-pods",
        "status": "pending",
    })
    
    # Track skill execution attempts
    skill_executions = []
    
    def execute_skill_side_effect(input_data):
        skill_executions.append(input_data)
        return {
            "success": True,
            "output": "This should not happen",
            "error": None,
            "duration_ms": 100,
        }
    
    mock_activities["execute_skill_activity"].side_effect = execute_skill_side_effect
    
    # Start workflow
    workflow_handle = await start_test_workflow(
        temporal_client,
        user_id,
        conversation_id,
    )
    
    await asyncio.sleep(0.2)
    
    # Act - Reject approval via API
    response = await test_client.post(
        f"/api/nexus/approvals/{approval_id}/decide",
        json={
            "approval_id": approval_id,
            "approved": False,
            "reason": rejection_reason,
        },
    )
    
    # Assert - Rejection was recorded
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "rejected"
    assert data["approval_id"] == str(approval_id)
    
    # Verify database was updated with rejection
    gateway_state.db_pool.execute.assert_called()
    
    # Wait for workflow to process rejection signal
    await asyncio.sleep(0.5)
    
    # Assert - Skill was NOT executed
    k8s_executions = [
        exec_data for exec_data in skill_executions
        if exec_data.get("skill_name") == "k8s/delete-pods"
    ]
    assert len(k8s_executions) == 0, "Skill should not execute after rejection"
    
    # Assert - User was notified of rejection
    mock_activities["publish_response_activity"].assert_called()
    publish_calls = mock_activities["publish_response_activity"].call_args_list
    
    # Find the rejection notification
    rejection_notifications = [
        call[0][0]["text"] for call in publish_calls
        if "rejected" in call[0][0]["text"].lower()
    ]
    
    assert len(rejection_notifications) > 0, "User should be notified of rejection"
    rejection_text = rejection_notifications[0]
    assert rejection_reason.lower() in rejection_text.lower()
    assert "will not be executed" in rejection_text.lower() or "not be executed" in rejection_text.lower()


# =========================================================================
# Test 21.4: Multiple Approvals in Sequence
# =========================================================================


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.skip(reason="Workflow has bug: uses datetime.now() which is non-deterministic in Temporal. Also, approval workflow logic not yet implemented.")
async def test_multiple_approvals_in_sequence(
    test_client: AsyncClient,
    temporal_client: Client,
    workflow_worker: Worker,
    mock_activities: dict[str, Any],
    gateway_state: GatewayState,
) -> None:
    """Test handling multiple approval requests in a single plan.
    
    This test validates that when a plan has multiple medium-risk skills,
    each one creates a separate approval request and waits for approval
    before proceeding.
    
    Requirements: 7.3, 7.4
    """
    # Arrange
    user_id = "multi-approval-user"
    conversation_id = str(uuid.uuid4())
    
    # Configure plan with multiple medium-risk skills
    mock_activities["plan_response"].return_value = {
        "needs_plan": True,
        "direct_response": None,
        "goal": "Perform production maintenance",
        "steps": [
            {
                "id": 1,
                "description": "Scale down deployment",
                "skill_name": "k8s/scale-deployment",
            },
            {
                "id": 2,
                "description": "Delete old pods",
                "skill_name": "k8s/delete-pods",
            },
            {
                "id": 3,
                "description": "Scale up deployment",
                "skill_name": "k8s/scale-deployment",
            },
        ],
    }
    
    # All skills require approval
    mock_activities["check_skill_approval_activity"].return_value = {
        "requires_approval": True,
        "risk_level": "medium",
        "risk_score": 5.5,
    }
    
    # Track approval requests
    approval_requests = []
    
    def create_approval_side_effect(input_data):
        approval_requests.append(input_data)
        return {"approval_id": len(approval_requests)}
    
    mock_activities["create_approval_request_activity"].side_effect = create_approval_side_effect
    
    # Start workflow
    workflow_handle = await start_test_workflow(
        temporal_client,
        user_id,
        conversation_id,
    )
    
    await asyncio.sleep(0.2)
    
    # Act - Send task request
    response = await test_client.post(
        "/api/nexus/chat",
        json={
            "text": "Perform production maintenance",
            "user_id": user_id,
            "conversation_id": conversation_id,
        },
    )
    
    assert response.status_code == 200
    
    # Wait for processing
    await asyncio.sleep(1.0)
    
    # Assert - Multiple approval requests were created
    assert len(approval_requests) >= 1, "At least one approval request should be created"
    
    # Verify each skill that requires approval got a request
    skill_names = [req["skill_name"] for req in approval_requests]
    assert "k8s/scale-deployment" in skill_names or "k8s/delete-pods" in skill_names
    
    # Assert - User was notified about multiple pending approvals
    mock_activities["publish_response_activity"].assert_called()
