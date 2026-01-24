"""
Shared fixtures for testing MCP clients.
"""

from collections.abc import Callable
from typing import Any

import pytest
from httpx import Response

from framework.mcp.client import MCPResponse


@pytest.fixture
def mock_mcp_response() -> Callable[..., MCPResponse]:
    """
    Factory for creating mock MCP responses.

    Usage:
        def test_success(mock_mcp_response):
            response = mock_mcp_response(data={"result": "ok"})
            assert response.success is True

        def test_error(mock_mcp_response):
            response = mock_mcp_response(success=False, error="Connection failed")
            assert response.success is False
    """

    def _create(
        success: bool = True,
        data: Any = None,
        error: str | None = None,
    ) -> MCPResponse:
        return MCPResponse(success=success, data=data, error=error)

    return _create


@pytest.fixture
def mock_mcp_server(respx_mock):
    """
    Fully mocked MCP server with common endpoints.

    Uses respx to mock HTTP responses. Default endpoints:
    - GET /health -> 200 OK
    - GET /tools/list -> 200 with empty tools list
    - POST /tools/call -> 200 with content

    Usage:
        @pytest.mark.asyncio
        async def test_health_check(mock_mcp_server):
            client = MCPServerClient("test", "http://test-mcp:8081")
            healthy = await client.health_check()
            assert healthy is True
    """
    # Health endpoint
    respx_mock.get("http://test-mcp:8081/health").mock(
        return_value=Response(200, json={"status": "ok"})
    )

    # List tools endpoint
    respx_mock.get("http://test-mcp:8081/tools/list").mock(
        return_value=Response(200, json={"tools": []})
    )

    # Call tool endpoint (generic success)
    respx_mock.post("http://test-mcp:8081/tools/call").mock(
        return_value=Response(200, json={"content": {"result": "success"}})
    )

    return respx_mock


@pytest.fixture
def mock_temporal_mcp(respx_mock):
    """
    Mocked Temporal MCP server with workflow endpoints.

    Usage:
        @pytest.mark.asyncio
        async def test_list_workflows(mock_temporal_mcp):
            client = TemporalMCPClient("temporal", "http://localhost:8081")
            response = await client.list_workflows()
            assert response.success is True
    """
    base_url = "http://localhost:8081"

    # Health check
    respx_mock.get(f"{base_url}/health").mock(return_value=Response(200, json={"status": "ok"}))

    # List workflows
    respx_mock.post(f"{base_url}/tools/call").mock(
        return_value=Response(
            200,
            json={
                "content": {
                    "workflows": [
                        {"id": "wf-1", "status": "running"},
                        {"id": "wf-2", "status": "completed"},
                    ]
                }
            },
        )
    )

    return respx_mock
