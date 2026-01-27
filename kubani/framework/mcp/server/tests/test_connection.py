# kubani/framework/mcp/server/tests/test_connection.py
"""Tests for connection management utilities."""

import pytest

from kubani.framework.mcp.server.connection import ConnectionManager, ConnectionState


class TestConnectionState:
    """Tests for ConnectionState enum."""

    def test_states_exist(self):
        assert ConnectionState.DISCONNECTED.value == "disconnected"
        assert ConnectionState.CONNECTING.value == "connecting"
        assert ConnectionState.CONNECTED.value == "connected"
        assert ConnectionState.FAILED.value == "failed"


class TestConnectionManager:
    """Tests for ConnectionManager."""

    @pytest.mark.asyncio
    async def test_initial_state(self):
        manager = ConnectionManager(name="test")
        assert manager.state == ConnectionState.DISCONNECTED
        assert manager.name == "test"

    @pytest.mark.asyncio
    async def test_connect_success(self):
        manager = ConnectionManager(name="test")

        async def connect_fn():
            return {"client": "connected"}

        result = await manager.connect(connect_fn)
        assert result == {"client": "connected"}
        assert manager.state == ConnectionState.CONNECTED

    @pytest.mark.asyncio
    async def test_connect_failure(self):
        manager = ConnectionManager(name="test")

        async def failing_connect():
            raise ValueError("Connection refused")

        with pytest.raises(ValueError, match="Connection refused"):
            await manager.connect(failing_connect)

        assert manager.state == ConnectionState.FAILED

    @pytest.mark.asyncio
    async def test_disconnect(self):
        manager = ConnectionManager(name="test")

        async def connect_fn():
            return "client"

        async def disconnect_fn():
            pass

        await manager.connect(connect_fn)
        assert manager.state == ConnectionState.CONNECTED

        await manager.disconnect(disconnect_fn)
        assert manager.state == ConnectionState.DISCONNECTED

    @pytest.mark.asyncio
    async def test_is_connected(self):
        manager = ConnectionManager(name="test")
        assert not manager.is_connected

        async def connect_fn():
            return "client"

        await manager.connect(connect_fn)
        assert manager.is_connected

    @pytest.mark.asyncio
    async def test_ensure_connected_raises(self):
        from kubani.framework.mcp.server.errors import MCPConnectionError

        manager = ConnectionManager(name="test-server")

        with pytest.raises(MCPConnectionError) as exc_info:
            manager.ensure_connected()

        assert exc_info.value.server == "test-server"

    @pytest.mark.asyncio
    async def test_ensure_connected_passes(self):
        manager = ConnectionManager(name="test")

        async def connect_fn():
            return "client"

        await manager.connect(connect_fn)
        # Should not raise
        manager.ensure_connected()
