"""Tests for unified MCPClient wrapper."""

import httpx
import pytest

from kubani.framework.mcp.client import (
    MCPClient,
    MemoryMCPClient,
    QdrantMCPClient,
    TemporalMCPClient,
)


class TestMCPClientProperties:
    """Test lazy property initialization"""

    def test_temporal_property_creates_client(self):
        """temporal property should lazily create TemporalMCPClient"""
        client = MCPClient()

        assert client._temporal is None
        temporal = client.temporal

        assert isinstance(temporal, TemporalMCPClient)
        assert client._temporal is temporal  # Same instance on second access

    def test_qdrant_property_creates_client(self):
        """qdrant property should lazily create QdrantMCPClient"""
        client = MCPClient()

        assert client._qdrant is None
        qdrant = client.qdrant

        assert isinstance(qdrant, QdrantMCPClient)
        assert client._qdrant is qdrant

    def test_memory_property_creates_client(self):
        """memory property should lazily create MemoryMCPClient"""
        client = MCPClient()

        assert client._memory is None
        memory = client.memory

        assert isinstance(memory, MemoryMCPClient)
        assert client._memory is memory


class TestMCPClientHealthCheckAll:
    """Test health_check_all functionality"""

    @pytest.mark.asyncio
    async def test_health_check_all_checks_enabled_servers(
        self, respx_mock, isolated_config_dir, create_yaml_config
    ):
        """health_check_all should check all enabled MCP servers"""
        # Configure enabled servers
        create_yaml_config(
            "default.yaml",
            {
                "mcp": {
                    "temporal_enabled": True,
                    "temporal_url": "http://localhost:8081",
                    "qdrant_enabled": True,
                    "qdrant_url": "http://localhost:8082",
                    "memory_enabled": False,
                    "discord_enabled": False,
                }
            },
        )

        # Mock health endpoints
        respx_mock.get("http://localhost:8081/health").mock(return_value=httpx.Response(200))
        respx_mock.get("http://localhost:8082/health").mock(return_value=httpx.Response(200))

        from framework.config import reload_config

        reload_config()

        client = MCPClient()
        results = await client.health_check_all()

        assert "temporal" in results
        assert "qdrant" in results
        assert results["temporal"] is True
        assert results["qdrant"] is True
        assert "memory" not in results  # Disabled

        await client.close()


class TestMCPClientSingleton:
    """Test global singleton pattern"""

    def test_get_mcp_client_returns_same_instance(self):
        """get_mcp_client should return same instance"""
        from framework.mcp.client import get_mcp_client

        client1 = get_mcp_client()
        client2 = get_mcp_client()

        assert client1 is client2

    @pytest.mark.asyncio
    async def test_close_mcp_client_clears_singleton(self):
        """close_mcp_client should clear global instance"""
        from framework.mcp.client import close_mcp_client, get_mcp_client

        client1 = get_mcp_client()
        await close_mcp_client()
        client2 = get_mcp_client()

        assert client1 is not client2  # New instance created
