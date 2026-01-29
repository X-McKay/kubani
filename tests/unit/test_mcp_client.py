"""
Tests for the MCP client module.

Tests cover:
- MCP client initialization
- Individual MCP server clients
- Health checks
- Tool calls (mocked)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestMCPServerClient:
    """Tests for the base MCP server client."""

    @pytest.mark.asyncio
    async def test_client_initialization(self):
        """Test MCP server client initialization."""
        from kubani.framework.mcp.client import MCPServerClient

        client = MCPServerClient("test", "http://localhost:8080")

        assert client.name == "test"
        # URL should have /sse appended for SSE transport
        assert client.url == "http://localhost:8080/sse"
        assert client.timeout == 30.0

    @pytest.mark.asyncio
    async def test_client_url_trailing_slash_removed(self):
        """Test that trailing slashes are removed from URL."""
        from kubani.framework.mcp.client import MCPServerClient

        client = MCPServerClient("test", "http://localhost:8080/")

        # Trailing slash removed, /sse appended
        assert client.url == "http://localhost:8080/sse"

    @pytest.mark.asyncio
    async def test_client_url_with_sse_not_duplicated(self):
        """Test that /sse is not duplicated if already present."""
        from kubani.framework.mcp.client import MCPServerClient

        client = MCPServerClient("test", "http://localhost:8080/sse")

        assert client.url == "http://localhost:8080/sse"

    @pytest.mark.asyncio
    async def test_call_tool_success(self):
        """Test successful tool call."""
        from kubani.framework.mcp.client import MCPServerClient

        client = MCPServerClient("test", "http://localhost:8080")

        # Mock the SSE connection context manager
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.isError = False
        mock_content = MagicMock()
        mock_content.text = '{"result": "success"}'
        mock_result.content = [mock_content]
        mock_session.call_tool.return_value = mock_result

        with patch.object(client, "_connect") as mock_connect:
            mock_connect.return_value.__aenter__.return_value = mock_session
            mock_connect.return_value.__aexit__.return_value = None

            result = await client.call_tool("test_tool", param="value")

            assert result.success is True
            assert result.data == {"result": "success"}
            assert result.error is None

    @pytest.mark.asyncio
    async def test_call_tool_error_response(self):
        """Test tool call that returns an error."""
        from kubani.framework.mcp.client import MCPServerClient

        client = MCPServerClient("test", "http://localhost:8080")

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.isError = True
        mock_content = MagicMock()
        mock_content.text = "Tool failed: invalid params"
        mock_result.content = [mock_content]
        mock_session.call_tool.return_value = mock_result

        with patch.object(client, "_connect") as mock_connect:
            mock_connect.return_value.__aenter__.return_value = mock_session
            mock_connect.return_value.__aexit__.return_value = None

            result = await client.call_tool("test_tool", param="value")

            assert result.success is False
            assert result.data is None
            assert "Tool failed" in result.error

    @pytest.mark.asyncio
    async def test_call_tool_connection_failure(self):
        """Test tool call when connection fails."""
        from kubani.framework.mcp.client import MCPServerClient

        client = MCPServerClient("test", "http://localhost:8080")

        with patch.object(client, "_connect") as mock_connect:
            mock_connect.return_value.__aenter__.side_effect = Exception("Connection refused")

            result = await client.call_tool("test_tool", param="value")

            assert result.success is False
            assert result.data is None
            assert "Connection refused" in result.error

    @pytest.mark.asyncio
    async def test_list_tools_success(self):
        """Test successful list_tools call."""
        from kubani.framework.mcp.client import MCPServerClient

        client = MCPServerClient("test", "http://localhost:8080")

        mock_session = AsyncMock()
        mock_tool1 = MagicMock()
        mock_tool1.name = "tool1"
        mock_tool1.description = "First tool"
        mock_tool2 = MagicMock()
        mock_tool2.name = "tool2"
        mock_tool2.description = "Second tool"
        mock_result = MagicMock()
        mock_result.tools = [mock_tool1, mock_tool2]
        mock_session.list_tools.return_value = mock_result

        with patch.object(client, "_connect") as mock_connect:
            mock_connect.return_value.__aenter__.return_value = mock_session
            mock_connect.return_value.__aexit__.return_value = None

            result = await client.list_tools()

            assert len(result) == 2
            assert result[0]["name"] == "tool1"
            assert result[1]["name"] == "tool2"

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """Test successful health check."""
        from kubani.framework.mcp.client import MCPServerClient

        client = MCPServerClient("test", "http://localhost:8080")

        # Health check now works by listing tools
        with patch.object(client, "list_tools", return_value=[{"name": "test"}]):
            result = await client.health_check()
            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        """Test failed health check."""
        from kubani.framework.mcp.client import MCPServerClient

        client = MCPServerClient("test", "http://localhost:8080")

        with patch.object(client, "list_tools", side_effect=Exception("Connection failed")):
            result = await client.health_check()
            assert result is False

    @pytest.mark.asyncio
    async def test_health_check_empty_tools(self):
        """Test health check when server returns no tools."""
        from kubani.framework.mcp.client import MCPServerClient

        client = MCPServerClient("test", "http://localhost:8080")

        with patch.object(client, "list_tools", return_value=[]):
            result = await client.health_check()
            assert result is False


class TestTemporalMCPClient:
    """Tests for the Temporal MCP client."""

    @pytest.mark.asyncio
    async def test_list_workflows(self):
        """Test list_workflows method."""
        from kubani.framework.mcp.client import TemporalMCPClient

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
        from kubani.framework.mcp.client import TemporalMCPClient

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
        from kubani.framework.mcp.client import QdrantMCPClient

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
        from kubani.framework.mcp.client import QdrantMCPClient

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
        from kubani.framework.mcp.client import MemoryMCPClient

        client = MemoryMCPClient("memory", "http://localhost:8083")

        with patch.object(client, "call_tool") as mock_call:
            mock_call.return_value = MagicMock(success=True, data={"learning_id": "123"})

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
        from kubani.framework.mcp.client import MemoryMCPClient

        client = MemoryMCPClient("memory", "http://localhost:8083")

        with patch.object(client, "call_tool") as mock_call:
            mock_call.return_value = MagicMock(success=True, data={"learnings": []})

            result = await client.query_learnings(
                query="test query",
                min_confidence=0.7,
            )

            mock_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_knowledge(self):
        """Test store_knowledge method."""
        from kubani.framework.mcp.client import MemoryMCPClient

        client = MemoryMCPClient("memory", "http://localhost:8083")

        with patch.object(client, "call_tool") as mock_call:
            mock_call.return_value = MagicMock(success=True, data={"knowledge_id": "456"})

            result = await client.store_knowledge(
                topic="test-topic",
                content="Test knowledge content",
                source="unit-test",
            )

            mock_call.assert_called_once()
            call_args = mock_call.call_args
            assert call_args[0][0] == "store_knowledge"
            assert call_args[1]["topic"] == "test-topic"

    @pytest.mark.asyncio
    async def test_query_knowledge(self):
        """Test query_knowledge method."""
        from kubani.framework.mcp.client import MemoryMCPClient

        client = MemoryMCPClient("memory", "http://localhost:8083")

        with patch.object(client, "call_tool") as mock_call:
            mock_call.return_value = MagicMock(success=True, data=[])

            result = await client.query_knowledge(query="test query", limit=5)

            mock_call.assert_called_once()
            call_args = mock_call.call_args
            assert call_args[0][0] == "query_knowledge"
            assert call_args[1]["query"] == "test query"
            assert call_args[1]["limit"] == 5

    @pytest.mark.asyncio
    async def test_cache_get(self):
        """Test cache_get method."""
        from kubani.framework.mcp.client import MemoryMCPClient

        client = MemoryMCPClient("memory", "http://localhost:8083")

        with patch.object(client, "call_tool") as mock_call:
            mock_call.return_value = MagicMock(success=True, data={"found": True, "value": "test"})

            result = await client.cache_get(key="test-key")

            mock_call.assert_called_once()
            call_args = mock_call.call_args
            assert call_args[0][0] == "cache_get"
            assert call_args[1]["key"] == "test-key"

    @pytest.mark.asyncio
    async def test_cache_set(self):
        """Test cache_set method."""
        from kubani.framework.mcp.client import MemoryMCPClient

        client = MemoryMCPClient("memory", "http://localhost:8083")

        with patch.object(client, "call_tool") as mock_call:
            mock_call.return_value = MagicMock(success=True, data={"success": True})

            result = await client.cache_set(key="test-key", value={"data": 123}, ttl_seconds=3600)

            mock_call.assert_called_once()
            call_args = mock_call.call_args
            assert call_args[0][0] == "cache_set"
            assert call_args[1]["key"] == "test-key"
            assert call_args[1]["ttl_seconds"] == 3600


class TestDiscordMCPClient:
    """Tests for the Discord MCP client."""

    @pytest.mark.asyncio
    async def test_send_message(self):
        """Test send_message method."""
        from kubani.framework.mcp.client import DiscordMCPClient

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
        from kubani.framework.mcp.client import DiscordMCPClient

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
        from kubani.framework.mcp.client import MCPClient

        client = MCPClient()

        assert client._temporal is None  # Lazy initialization
        assert client._qdrant is None
        assert client._memory is None
        assert client._discord is None

    def test_temporal_property(self):
        """Test temporal property returns TemporalMCPClient."""
        from kubani.framework.mcp.client import MCPClient, TemporalMCPClient

        client = MCPClient()

        temporal = client.temporal

        assert isinstance(temporal, TemporalMCPClient)
        assert client._temporal is temporal  # Cached

    def test_qdrant_property(self):
        """Test qdrant property returns QdrantMCPClient."""
        from kubani.framework.mcp.client import MCPClient, QdrantMCPClient

        client = MCPClient()

        qdrant = client.qdrant

        assert isinstance(qdrant, QdrantMCPClient)

    def test_memory_property(self):
        """Test memory property returns MemoryMCPClient."""
        from kubani.framework.mcp.client import MCPClient, MemoryMCPClient

        client = MCPClient()

        memory = client.memory

        assert isinstance(memory, MemoryMCPClient)

    def test_discord_property(self):
        """Test discord property returns DiscordMCPClient."""
        from kubani.framework.mcp.client import DiscordMCPClient, MCPClient

        client = MCPClient()

        discord = client.discord

        assert isinstance(discord, DiscordMCPClient)

    @pytest.mark.asyncio
    async def test_health_check_all(self):
        """Test health_check_all method."""
        from kubani.framework.mcp.client import MCPClient

        # Create a mock config with all services enabled
        mock_config = MagicMock()
        mock_config.temporal_enabled = True
        mock_config.qdrant_enabled = True
        mock_config.memory_enabled = True
        mock_config.discord_enabled = True
        mock_config.registry_enabled = True
        mock_config.skills_enabled = False
        mock_config.temporal_url = "http://localhost:8081"
        mock_config.qdrant_url = "http://localhost:8082"
        mock_config.memory_url = "http://localhost:8083"
        mock_config.discord_url = "http://localhost:8084"
        mock_config.registry_url = "http://localhost:8085"
        mock_config.skills_url = "http://localhost:8086"

        client = MCPClient(config=mock_config)

        # Mock all health checks
        with (
            patch.object(client.temporal, "health_check", return_value=True),
            patch.object(client.qdrant, "health_check", return_value=True),
            patch.object(client.memory, "health_check", return_value=True),
            patch.object(client.discord, "health_check", return_value=False),
            patch.object(client.registry, "health_check", return_value=True),
        ):
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
        import kubani.framework.mcp.client as client_module
        from kubani.framework.mcp.client import get_mcp_client

        # Reset the singleton
        client_module._mcp_client = None

        client1 = get_mcp_client()
        client2 = get_mcp_client()

        assert client1 is client2

    @pytest.mark.asyncio
    async def test_close_mcp_client(self):
        """Test close_mcp_client clears the singleton."""
        import kubani.framework.mcp.client as client_module
        from kubani.framework.mcp.client import close_mcp_client, get_mcp_client

        # Reset the singleton
        client_module._mcp_client = None

        client1 = get_mcp_client()
        await close_mcp_client()

        assert client_module._mcp_client is None
