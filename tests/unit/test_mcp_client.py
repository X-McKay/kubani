"""
Tests for the MCP client module.

Tests cover:
- MCP client initialization
- Individual MCP server clients
- Health checks
- Tool calls (mocked)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestMCPServerClient:
    """Tests for the base MCP server client."""

    @pytest.mark.asyncio
    async def test_client_initialization(self):
        """Test MCP server client initialization."""
        from core_agents.mcp.client import MCPServerClient
        
        client = MCPServerClient("test", "http://localhost:8080")
        
        assert client.name == "test"
        assert client.url == "http://localhost:8080"
        assert client.timeout == 30.0

    @pytest.mark.asyncio
    async def test_client_url_trailing_slash_removed(self):
        """Test that trailing slashes are removed from URL."""
        from core_agents.mcp.client import MCPServerClient
        
        client = MCPServerClient("test", "http://localhost:8080/")
        
        assert client.url == "http://localhost:8080"

    @pytest.mark.asyncio
    async def test_call_tool_success(self):
        """Test successful tool call."""
        from core_agents.mcp.client import MCPServerClient
        
        client = MCPServerClient("test", "http://localhost:8080")
        
        # Mock the HTTP client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"content": {"result": "success"}}
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post.return_value = mock_response
            mock_get_client.return_value = mock_http_client
            
            result = await client.call_tool("test_tool", param="value")
            
            assert result.success is True
            assert result.data == {"result": "success"}
            assert result.error is None

    @pytest.mark.asyncio
    async def test_call_tool_failure(self):
        """Test failed tool call."""
        from core_agents.mcp.client import MCPServerClient
        import httpx
        
        client = MCPServerClient("test", "http://localhost:8080")
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post.side_effect = httpx.HTTPStatusError(
                "Error", request=MagicMock(), response=MagicMock()
            )
            mock_get_client.return_value = mock_http_client
            
            result = await client.call_tool("test_tool", param="value")
            
            assert result.success is False
            assert result.data is None
            assert result.error is not None

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """Test successful health check."""
        from core_agents.mcp.client import MCPServerClient
        
        client = MCPServerClient("test", "http://localhost:8080")
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.get.return_value = mock_response
            mock_get_client.return_value = mock_http_client
            
            result = await client.health_check()
            
            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        """Test failed health check."""
        from core_agents.mcp.client import MCPServerClient
        
        client = MCPServerClient("test", "http://localhost:8080")
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.get.side_effect = Exception("Connection failed")
            mock_get_client.return_value = mock_http_client
            
            result = await client.health_check()
            
            assert result is False


class TestTemporalMCPClient:
    """Tests for the Temporal MCP client."""

    @pytest.mark.asyncio
    async def test_list_workflows(self):
        """Test list_workflows method."""
        from core_agents.mcp.client import TemporalMCPClient
        
        client = TemporalMCPClient("temporal", "http://localhost:8081")
        
        with patch.object(client, "call_tool") as mock_call:
            mock_call.return_value = MagicMock(success=True, data=[])
            
            result = await client.list_workflows(status="running")
            
            mock_call.assert_called_once_with(
                "list_workflows",
                status="running",
                workflow_type=None,
                limit=100,
            )

    @pytest.mark.asyncio
    async def test_start_workflow(self):
        """Test start_workflow method."""
        from core_agents.mcp.client import TemporalMCPClient
        
        client = TemporalMCPClient("temporal", "http://localhost:8081")
        
        with patch.object(client, "call_tool") as mock_call:
            mock_call.return_value = MagicMock(success=True, data={})
            
            result = await client.start_workflow(
                workflow_type="TestWorkflow",
                workflow_id="test-123",
                task_queue="test-queue",
            )
            
            mock_call.assert_called_once()
            call_args = mock_call.call_args
            assert call_args[0][0] == "start_workflow"
            assert call_args[1]["workflow_type"] == "TestWorkflow"
            assert call_args[1]["workflow_id"] == "test-123"


class TestQdrantMCPClient:
    """Tests for the Qdrant MCP client."""

    @pytest.mark.asyncio
    async def test_search_vectors(self):
        """Test search_vectors method."""
        from core_agents.mcp.client import QdrantMCPClient
        
        client = QdrantMCPClient("qdrant", "http://localhost:8082")
        
        with patch.object(client, "call_tool") as mock_call:
            mock_call.return_value = MagicMock(success=True, data=[])
            
            result = await client.search_vectors(
                collection="test",
                query_vector=[0.1, 0.2, 0.3],
                limit=5,
            )
            
            mock_call.assert_called_once()
            call_args = mock_call.call_args
            assert call_args[0][0] == "search_vectors"
            assert call_args[1]["collection"] == "test"
            assert call_args[1]["limit"] == 5

    @pytest.mark.asyncio
    async def test_upsert_vectors(self):
        """Test upsert_vectors method."""
        from core_agents.mcp.client import QdrantMCPClient
        
        client = QdrantMCPClient("qdrant", "http://localhost:8082")
        
        with patch.object(client, "call_tool") as mock_call:
            mock_call.return_value = MagicMock(success=True, data={})
            
            points = [{"id": 1, "vector": [0.1, 0.2], "payload": {}}]
            result = await client.upsert_vectors(
                collection="test",
                points=points,
            )
            
            mock_call.assert_called_once()


class TestMemoryMCPClient:
    """Tests for the Memory MCP client."""

    @pytest.mark.asyncio
    async def test_store_learning(self):
        """Test store_learning method."""
        from core_agents.mcp.client import MemoryMCPClient
        
        client = MemoryMCPClient("memory", "http://localhost:8083")
        
        with patch.object(client, "call_tool") as mock_call:
            mock_call.return_value = MagicMock(success=True, data={})
            
            result = await client.store_learning(
                agent_id="test-agent",
                learning_type="pattern",
                content="Test learning",
                confidence=0.85,
            )
            
            mock_call.assert_called_once()
            call_args = mock_call.call_args
            assert call_args[0][0] == "store_learning"
            assert call_args[1]["agent_id"] == "test-agent"
            assert call_args[1]["confidence"] == 0.85

    @pytest.mark.asyncio
    async def test_query_learnings(self):
        """Test query_learnings method."""
        from core_agents.mcp.client import MemoryMCPClient
        
        client = MemoryMCPClient("memory", "http://localhost:8083")
        
        with patch.object(client, "call_tool") as mock_call:
            mock_call.return_value = MagicMock(success=True, data=[])
            
            result = await client.query_learnings(
                query="test query",
                min_confidence=0.7,
            )
            
            mock_call.assert_called_once()


class TestDiscordMCPClient:
    """Tests for the Discord MCP client."""

    @pytest.mark.asyncio
    async def test_send_message(self):
        """Test send_message method."""
        from core_agents.mcp.client import DiscordMCPClient
        
        client = DiscordMCPClient("discord", "http://localhost:8084")
        
        with patch.object(client, "call_tool") as mock_call:
            mock_call.return_value = MagicMock(success=True, data={})
            
            result = await client.send_message(
                channel_id="123456",
                content="Test message",
            )
            
            mock_call.assert_called_once()
            call_args = mock_call.call_args
            assert call_args[0][0] == "send_message"
            assert call_args[1]["channel_id"] == "123456"

    @pytest.mark.asyncio
    async def test_send_embed(self):
        """Test send_embed method."""
        from core_agents.mcp.client import DiscordMCPClient
        
        client = DiscordMCPClient("discord", "http://localhost:8084")
        
        with patch.object(client, "call_tool") as mock_call:
            mock_call.return_value = MagicMock(success=True, data={})
            
            result = await client.send_embed(
                channel_id="123456",
                title="Test",
                description="Test embed",
            )
            
            mock_call.assert_called_once()


class TestMCPClient:
    """Tests for the unified MCP client."""

    def test_client_initialization(self):
        """Test MCP client initialization."""
        from core_agents.mcp.client import MCPClient
        
        client = MCPClient()
        
        assert client._temporal is None  # Lazy initialization
        assert client._qdrant is None
        assert client._memory is None
        assert client._discord is None

    def test_temporal_property(self):
        """Test temporal property returns TemporalMCPClient."""
        from core_agents.mcp.client import MCPClient, TemporalMCPClient
        
        client = MCPClient()
        
        temporal = client.temporal
        
        assert isinstance(temporal, TemporalMCPClient)
        assert client._temporal is temporal  # Cached

    def test_qdrant_property(self):
        """Test qdrant property returns QdrantMCPClient."""
        from core_agents.mcp.client import MCPClient, QdrantMCPClient
        
        client = MCPClient()
        
        qdrant = client.qdrant
        
        assert isinstance(qdrant, QdrantMCPClient)

    def test_memory_property(self):
        """Test memory property returns MemoryMCPClient."""
        from core_agents.mcp.client import MCPClient, MemoryMCPClient
        
        client = MCPClient()
        
        memory = client.memory
        
        assert isinstance(memory, MemoryMCPClient)

    def test_discord_property(self):
        """Test discord property returns DiscordMCPClient."""
        from core_agents.mcp.client import MCPClient, DiscordMCPClient
        
        client = MCPClient()
        
        discord = client.discord
        
        assert isinstance(discord, DiscordMCPClient)

    @pytest.mark.asyncio
    async def test_health_check_all(self):
        """Test health_check_all method."""
        from core_agents.mcp.client import MCPClient
        
        client = MCPClient()
        
        # Mock all health checks
        with patch.object(client.temporal, "health_check", return_value=True), \
             patch.object(client.qdrant, "health_check", return_value=True), \
             patch.object(client.memory, "health_check", return_value=True), \
             patch.object(client.discord, "health_check", return_value=False), \
             patch.object(client.registry, "health_check", return_value=True):
            
            results = await client.health_check_all()
            
            assert results["temporal"] is True
            assert results["qdrant"] is True
            assert results["memory"] is True
            assert results["discord"] is False
            assert results["registry"] is True


class TestMCPClientSingleton:
    """Tests for the MCP client singleton functions."""

    def test_get_mcp_client_singleton(self):
        """Test that get_mcp_client returns a singleton."""
        from core_agents.mcp.client import get_mcp_client, close_mcp_client
        import core_agents.mcp.client as client_module
        
        # Reset the singleton
        client_module._mcp_client = None
        
        client1 = get_mcp_client()
        client2 = get_mcp_client()
        
        assert client1 is client2

    @pytest.mark.asyncio
    async def test_close_mcp_client(self):
        """Test close_mcp_client clears the singleton."""
        from core_agents.mcp.client import get_mcp_client, close_mcp_client
        import core_agents.mcp.client as client_module
        
        # Reset the singleton
        client_module._mcp_client = None
        
        client1 = get_mcp_client()
        await close_mcp_client()
        
        assert client_module._mcp_client is None
