"""
Integration tests for Temporal MCP Server.

These tests require a real Temporal server to be running.
Use docker-compose.integration.yml to start Temporal.

Run with: uv run pytest tests/test_integration.py -v
"""

import os
from uuid import uuid4

import pytest

# Set environment variables for test Temporal server
os.environ["TEMPORAL_HOST"] = "localhost"
os.environ["TEMPORAL_PORT"] = "7233"
os.environ["TEMPORAL_NAMESPACE"] = "default"

from temporal_mcp.server import connect_temporal, create_server, disconnect_temporal


@pytest.fixture(scope="module")
async def temporal_client():
    """Connect to Temporal once for all tests."""
    client = await connect_temporal()
    yield client
    await disconnect_temporal()


@pytest.fixture
async def server(temporal_client):
    """Create a fresh server instance for each test."""
    return create_server()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_workflows_integration(server):
    """
    Test listing workflows with real Temporal server.
    
    Validates: Requirements 2.3 - Integration tests with backend dependencies
    """
    result = await server.call_tool(
        "list_workflows",
        {
            "limit": 10,
        },
    )
    
    assert "workflows" in result
    assert "count" in result
    assert result["count"] >= 0
    assert isinstance(result["workflows"], list)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_workflows_with_status_filter(server):
    """
    Test listing workflows with status filter.
    
    Validates: Requirements 2.3 - Integration tests with backend dependencies
    """
    result = await server.call_tool(
        "list_workflows",
        {
            "status": "running",
            "limit": 10,
        },
    )
    
    assert "workflows" in result
    assert result["count"] >= 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_schedules_integration(server):
    """
    Test listing schedules with real Temporal server.
    
    Validates: Requirements 2.3 - Integration tests with backend dependencies
    """
    result = await server.call_tool(
        "list_schedules",
        {
            "limit": 10,
        },
    )
    
    assert "schedules" in result
    assert "count" in result
    assert result["count"] >= 0
    assert isinstance(result["schedules"], list)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_health_check_integration(server):
    """
    Test health check with real Temporal server.
    
    Validates: Requirements 2.3 - Integration tests with backend dependencies
    """
    result = await server.call_tool("health", {})
    
    assert "status" in result
    # Should be healthy if Temporal is running
    assert result["status"] in ["healthy", "degraded"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_worker_task_queues_integration(server):
    """
    Test getting worker task queues information.
    
    Validates: Requirements 2.3 - Integration tests with backend dependencies
    """
    result = await server.call_tool("get_worker_task_queues", {})
    
    assert "namespace" in result
    assert result["namespace"] == "default"


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires a running workflow to test")
async def test_get_workflow_integration(server):
    """
    Test getting workflow details.
    
    This test is skipped by default as it requires a running workflow.
    To run it, start a workflow first and update the workflow_id.
    
    Validates: Requirements 2.3 - Integration tests with backend dependencies
    """
    workflow_id = "test-workflow-id"
    
    result = await server.call_tool(
        "get_workflow",
        {
            "workflow_id": workflow_id,
        },
    )
    
    assert "workflow_id" in result
    assert result["workflow_id"] == workflow_id


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires a running workflow to test")
async def test_get_workflow_history_integration(server):
    """
    Test getting workflow history.
    
    This test is skipped by default as it requires a running workflow.
    
    Validates: Requirements 2.3 - Integration tests with backend dependencies
    """
    workflow_id = "test-workflow-id"
    
    result = await server.call_tool(
        "get_workflow_history",
        {
            "workflow_id": workflow_id,
            "limit": 20,
        },
    )
    
    assert "workflow_id" in result
    assert "events" in result
    assert isinstance(result["events"], list)


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires workflow definition and worker")
async def test_start_workflow_integration(server):
    """
    Test starting a workflow.
    
    This test is skipped by default as it requires:
    - A workflow definition to be registered
    - A worker running to execute the workflow
    
    Validates: Requirements 2.3 - Integration tests with backend dependencies
    """
    workflow_id = f"test-workflow-{uuid4()}"
    
    result = await server.call_tool(
        "start_workflow",
        {
            "workflow_type": "TestWorkflow",
            "workflow_id": workflow_id,
            "task_queue": "test-queue",
            "args": [],
        },
    )
    
    assert "workflow_id" in result
    assert result["workflow_id"] == workflow_id
    assert "status" in result


@pytest.mark.integration
@pytest.mark.asyncio
async def test_metrics_integration(server):
    """
    Test getting metrics from the server.
    
    Validates: Requirements 2.3 - Integration tests with backend dependencies
    """
    result = await server.call_tool("metrics", {})
    
    # Metrics should return either data or an error message
    assert isinstance(result, dict)
    # If metrics collector is initialized, should have content_type
    # Otherwise, should have error message
    assert "content_type" in result or "error" in result
