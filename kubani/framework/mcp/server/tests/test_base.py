"""Tests for MCPServerBase class."""

import pytest

from kubani.framework.mcp.server.base import MCPServerBase
from kubani.framework.mcp.server.health import HealthStatus


class MockBackendServer(MCPServerBase):
    """Mock server for testing."""

    name = "mock-server"
    description = "A mock MCP server for testing"

    def __init__(self):
        super().__init__()
        self.connected = False
        self.tools_registered = False

    async def connect_backend(self) -> None:
        self.connected = True

    async def disconnect_backend(self) -> None:
        self.connected = False

    def register_tools(self, mcp) -> None:
        self.tools_registered = True

        @mcp.tool()
        async def echo(message: str) -> dict:
            """Echo back the message."""
            return {"echo": message}


class FailingServer(MCPServerBase):
    """Server that fails to connect."""

    name = "failing-server"
    description = "Always fails to connect"

    async def connect_backend(self) -> None:
        raise ConnectionError("Backend unavailable")

    async def disconnect_backend(self) -> None:
        pass

    def register_tools(self, mcp) -> None:
        pass


class TestMCPServerBase:
    """Tests for MCPServerBase."""

    def test_create_server(self):
        server = MockBackendServer()
        mcp = server.create_server()

        assert mcp.name == "mock-server"
        assert server.tools_registered

    @pytest.mark.asyncio
    async def test_startup_shutdown(self):
        server = MockBackendServer()
        server.create_server()

        # Simulate lifespan startup
        await server.startup()
        assert server.connected
        assert server.connection.is_connected

        # Simulate lifespan shutdown
        await server.shutdown()
        assert not server.connected

    @pytest.mark.asyncio
    async def test_health_check(self):
        server = MockBackendServer()
        await server.startup()

        result = await server.health_check()
        assert result.status == HealthStatus.HEALTHY
        assert result.name == "mock-server"

        await server.shutdown()

    @pytest.mark.asyncio
    async def test_health_check_not_connected(self):
        server = MockBackendServer()
        # Don't call startup

        result = await server.health_check()
        assert result.status == HealthStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_connection_failure(self):
        server = FailingServer()

        with pytest.raises(ConnectionError, match="Backend unavailable"):
            await server.startup()

    def test_get_client_before_connect(self):
        from kubani.framework.mcp.server.errors import MCPConnectionError

        server = MockBackendServer()

        with pytest.raises(MCPConnectionError):
            server.ensure_connected()

    @pytest.mark.asyncio
    async def test_ensure_connected_after_connect(self):
        server = MockBackendServer()
        await server.startup()

        # Should not raise
        server.ensure_connected()

        await server.shutdown()
