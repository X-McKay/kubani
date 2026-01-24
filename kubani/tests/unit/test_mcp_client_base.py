"""Tests for MCPServerClient base class."""

import httpx
import pytest

from framework.mcp.client import MCPServerClient


class TestMCPServerClientHealth:
    """Test health check functionality"""

    @pytest.mark.asyncio
    async def test_health_check_returns_true_when_server_healthy(self, respx_mock):
        """Health check should return True when server responds with 200"""
        respx_mock.get("http://test-server:8080/health").mock(return_value=httpx.Response(200))

        client = MCPServerClient("test", "http://test-server:8080")
        result = await client.health_check()

        assert result is True
        await client.close()

    @pytest.mark.asyncio
    async def test_health_check_returns_false_when_server_unavailable(self, respx_mock):
        """Health check should return False when server is down"""
        respx_mock.get("http://test-server:8080/health").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        client = MCPServerClient("test", "http://test-server:8080")
        result = await client.health_check()

        assert result is False
        await client.close()


class TestMCPServerClientListTools:
    """Test list_tools functionality"""

    @pytest.mark.asyncio
    async def test_list_tools_returns_tools_array(self, respx_mock):
        """list_tools should return tools from server response"""
        respx_mock.get("http://test-server:8080/tools/list").mock(
            return_value=httpx.Response(200, json={"tools": [{"name": "tool1"}, {"name": "tool2"}]})
        )

        client = MCPServerClient("test", "http://test-server:8080")
        tools = await client.list_tools()

        assert len(tools) == 2
        assert tools[0]["name"] == "tool1"
        assert tools[1]["name"] == "tool2"
        await client.close()

    @pytest.mark.asyncio
    async def test_list_tools_returns_empty_on_error(self, respx_mock):
        """list_tools should return empty array on error"""
        respx_mock.get("http://test-server:8080/tools/list").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        client = MCPServerClient("test", "http://test-server:8080")
        tools = await client.list_tools()

        assert tools == []
        await client.close()


class TestMCPServerClientCallTool:
    """Test call_tool functionality"""

    @pytest.mark.asyncio
    async def test_call_tool_returns_success_response(self, respx_mock):
        """call_tool should return MCPResponse with success=True on successful call"""
        respx_mock.post("http://test-server:8080/tools/call").mock(
            return_value=httpx.Response(
                200, json={"content": {"result": "success", "data": [1, 2, 3]}}
            )
        )

        client = MCPServerClient("test", "http://test-server:8080")
        response = await client.call_tool("test_tool", arg1="value1", arg2=42)

        assert response.success is True
        assert response.data == {"result": "success", "data": [1, 2, 3]}
        assert response.error is None
        await client.close()

    @pytest.mark.asyncio
    async def test_call_tool_returns_error_response_on_http_error(self, respx_mock):
        """call_tool should return MCPResponse with success=False on HTTP error"""
        respx_mock.post("http://test-server:8080/tools/call").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        client = MCPServerClient("test", "http://test-server:8080")
        response = await client.call_tool("test_tool")

        assert response.success is False
        assert response.data is None
        assert response.error is not None
        assert "500" in response.error
        await client.close()

    @pytest.mark.asyncio
    async def test_call_tool_returns_error_response_on_connection_error(self, respx_mock):
        """call_tool should return MCPResponse with success=False on connection error"""
        respx_mock.post("http://test-server:8080/tools/call").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        client = MCPServerClient("test", "http://test-server:8080")
        response = await client.call_tool("test_tool")

        assert response.success is False
        assert response.data is None
        assert "Connection refused" in response.error
        await client.close()


class TestMCPServerClientInitialization:
    """Test client initialization and cleanup"""

    @pytest.mark.asyncio
    async def test_http_client_created_lazily(self):
        """HTTP client should be created on first use, not in __init__"""
        client = MCPServerClient("test", "http://test-server:8080")

        assert client._client is None  # Not created yet

        # Trigger client creation
        await client._get_client()

        assert client._client is not None
        await client.close()

    @pytest.mark.asyncio
    async def test_close_cleans_up_client(self):
        """close() should clean up HTTP client"""
        client = MCPServerClient("test", "http://test-server:8080")
        await client._get_client()

        assert client._client is not None

        await client.close()

        assert client._client is None
