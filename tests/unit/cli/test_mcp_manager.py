"""Tests for MCP server subprocess manager."""

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestMCPServerManager:
    """Tests for MCPServerManager."""

    def test_manager_initialization(self):
        """Test manager initializes with empty server list."""
        from kubani.cli.mcp_manager import MCPServerManager

        manager = MCPServerManager()

        assert manager.servers == {}
        assert manager.processes == []

    def test_get_server_path(self):
        """Test server path resolution."""
        from kubani.cli.mcp_manager import MCPServerManager

        manager = MCPServerManager()
        path = manager._get_server_path("memory")

        assert "kubani/mcp/servers/memory" in str(path)

    def test_get_server_command(self):
        """Test server command generation."""
        from kubani.cli.mcp_manager import MCPServerManager

        manager = MCPServerManager()
        cmd = manager._get_server_command("memory")

        assert cmd == ["uv", "run", "memory-mcp"]

    def test_get_server_command_discord(self):
        """Test server command for discord (different naming)."""
        from kubani.cli.mcp_manager import MCPServerManager

        manager = MCPServerManager()
        cmd = manager._get_server_command("discord")

        assert cmd == ["uv", "run", "discord-mcp-server"]

    def test_get_server_command_temporal(self):
        """Test server command for temporal."""
        from kubani.cli.mcp_manager import MCPServerManager

        manager = MCPServerManager()
        cmd = manager._get_server_command("temporal")

        assert cmd == ["uv", "run", "temporal-mcp"]

    def test_get_server_command_qdrant(self):
        """Test server command for qdrant."""
        from kubani.cli.mcp_manager import MCPServerManager

        manager = MCPServerManager()
        cmd = manager._get_server_command("qdrant")

        assert cmd == ["uv", "run", "qdrant-mcp"]

    def test_get_server_command_unknown_fallback(self):
        """Test server command falls back for unknown servers."""
        from kubani.cli.mcp_manager import MCPServerManager

        manager = MCPServerManager()
        cmd = manager._get_server_command("unknown")

        assert cmd == ["uv", "run", "unknown-mcp"]

    def test_default_ports(self):
        """Test default ports are defined correctly."""
        from kubani.cli.mcp_manager import DEFAULT_PORTS

        assert DEFAULT_PORTS["memory"] == 8083
        assert DEFAULT_PORTS["discord"] == 8084
        assert DEFAULT_PORTS["temporal"] == 8081
        assert DEFAULT_PORTS["qdrant"] == 8082

    def test_build_server_env_none_config(self):
        """Test build_server_env with None config returns base environment."""
        from kubani.cli.mcp_manager import MCPServerManager

        manager = MCPServerManager()
        env = manager._build_server_env(None)

        # Should return a copy of os.environ
        assert isinstance(env, dict)
        assert "PATH" in env  # Common env var should be present

    def test_build_server_env_with_services(self):
        """Test build_server_env extracts service URLs from config."""
        from kubani.cli.mcp_manager import MCPServerManager

        @dataclass
        class Services:
            qdrant_url: str = "http://qdrant.example:6333"
            redis_url: str = "redis://redis.example:6379"

        @dataclass
        class Config:
            services: Services = None

        config = Config(services=Services())
        manager = MCPServerManager()
        env = manager._build_server_env(config)

        assert env["QDRANT_URL"] == "http://qdrant.example:6333"
        assert env["REDIS_URL"] == "redis://redis.example:6379"

    def test_build_server_env_with_discord(self):
        """Test build_server_env extracts Discord config."""
        from kubani.cli.mcp_manager import MCPServerManager

        @dataclass
        class Discord:
            bot_token: str = "test-token"
            guild_id: int = 12345

        @dataclass
        class Config:
            services: None = None
            discord: Discord = None

        config = Config(discord=Discord())
        manager = MCPServerManager()
        env = manager._build_server_env(config)

        assert env["DISCORD_BOT_TOKEN"] == "test-token"
        assert env["DISCORD_GUILD_ID"] == "12345"

    def test_get_server_urls_empty(self):
        """Test get_server_urls returns empty dict when no servers."""
        from kubani.cli.mcp_manager import MCPServerManager

        manager = MCPServerManager()
        urls = manager.get_server_urls()

        assert urls == {}

    def test_get_server_urls_with_servers(self):
        """Test get_server_urls returns correct URLs."""
        from kubani.cli.mcp_manager import MCPServerManager, MCPServerProcess

        manager = MCPServerManager()
        # Manually add a server process for testing
        manager.servers["memory"] = MCPServerProcess(
            name="memory",
            port=8083,
            process=MagicMock(),
            url="http://localhost:8083",
        )

        urls = manager.get_server_urls()

        assert urls == {"memory": "http://localhost:8083"}

    def test_stop_server_not_found(self):
        """Test stop_server handles missing server gracefully."""
        from kubani.cli.mcp_manager import MCPServerManager

        manager = MCPServerManager()
        # Should not raise
        manager.stop_server("nonexistent")

    def test_stop_server_terminates_process(self):
        """Test stop_server terminates the process."""
        from kubani.cli.mcp_manager import MCPServerManager, MCPServerProcess

        mock_process = MagicMock()
        mock_process.wait.return_value = 0

        manager = MCPServerManager()
        manager.servers["memory"] = MCPServerProcess(
            name="memory",
            port=8083,
            process=mock_process,
            url="http://localhost:8083",
        )
        manager.processes.append(mock_process)

        manager.stop_server("memory")

        mock_process.terminate.assert_called_once()
        assert "memory" not in manager.servers
        assert mock_process not in manager.processes

    def test_stop_server_kills_on_timeout(self):
        """Test stop_server kills process if terminate times out."""
        import subprocess

        from kubani.cli.mcp_manager import MCPServerManager, MCPServerProcess

        mock_process = MagicMock()
        mock_process.wait.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=5)

        manager = MCPServerManager()
        manager.servers["memory"] = MCPServerProcess(
            name="memory",
            port=8083,
            process=mock_process,
            url="http://localhost:8083",
        )
        manager.processes.append(mock_process)

        manager.stop_server("memory")

        mock_process.terminate.assert_called_once()
        mock_process.kill.assert_called_once()

    def test_stop_all_stops_all_servers(self):
        """Test stop_all stops all running servers."""
        from kubani.cli.mcp_manager import MCPServerManager, MCPServerProcess

        mock_process1 = MagicMock()
        mock_process1.wait.return_value = 0
        mock_process2 = MagicMock()
        mock_process2.wait.return_value = 0

        manager = MCPServerManager()
        manager.servers["memory"] = MCPServerProcess(
            name="memory",
            port=8083,
            process=mock_process1,
            url="http://localhost:8083",
        )
        manager.servers["discord"] = MCPServerProcess(
            name="discord",
            port=8084,
            process=mock_process2,
            url="http://localhost:8084",
        )
        manager.processes.extend([mock_process1, mock_process2])

        manager.stop_all()

        assert manager.servers == {}
        mock_process1.terminate.assert_called_once()
        mock_process2.terminate.assert_called_once()


class TestMCPServerConfig:
    """Tests for MCPServerConfig dataclass."""

    def test_server_config_creation(self):
        """Test MCPServerConfig can be created with required fields."""
        from kubani.cli.mcp_manager import MCPServerConfig

        config = MCPServerConfig(name="memory", port=8083)

        assert config.name == "memory"
        assert config.port == 8083
        assert config.env == {}

    def test_server_config_with_env(self):
        """Test MCPServerConfig can include custom env vars."""
        from kubani.cli.mcp_manager import MCPServerConfig

        config = MCPServerConfig(
            name="memory",
            port=8083,
            env={"CUSTOM_VAR": "value"},
        )

        assert config.env == {"CUSTOM_VAR": "value"}


class TestMCPServerProcess:
    """Tests for MCPServerProcess dataclass."""

    def test_server_process_creation(self):
        """Test MCPServerProcess can be created."""
        from kubani.cli.mcp_manager import MCPServerProcess

        mock_process = MagicMock()
        process = MCPServerProcess(
            name="memory",
            port=8083,
            process=mock_process,
            url="http://localhost:8083",
        )

        assert process.name == "memory"
        assert process.port == 8083
        assert process.process is mock_process
        assert process.url == "http://localhost:8083"


class TestAsyncMethods:
    """Tests for async methods using mocks."""

    @pytest.mark.asyncio
    async def test_wait_for_health_success(self):
        """Test _wait_for_health returns when server is healthy."""
        from kubani.cli.mcp_manager import MCPServerManager

        manager = MCPServerManager()

        with patch("kubani.cli.mcp_manager.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Should complete without raising
            await manager._wait_for_health("http://localhost:8083", timeout=5.0)

            mock_client.get.assert_called_with("http://localhost:8083/health", timeout=2.0)

    @pytest.mark.asyncio
    async def test_wait_for_health_timeout(self):
        """Test _wait_for_health raises TimeoutError on timeout."""
        import httpx

        from kubani.cli.mcp_manager import MCPServerManager

        manager = MCPServerManager()

        with patch("kubani.cli.mcp_manager.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.ConnectError("Connection refused")
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with pytest.raises(TimeoutError):
                await manager._wait_for_health("http://localhost:8083", timeout=0.5)

    @pytest.mark.asyncio
    async def test_start_server_path_not_found(self):
        """Test start_server raises error if server path doesn't exist."""
        from kubani.cli.mcp_manager import MCPServerManager

        manager = MCPServerManager()

        # Mock _get_server_path to return non-existent path
        with patch.object(
            manager,
            "_get_server_path",
            return_value=MagicMock(exists=lambda: False),
        ), pytest.raises(RuntimeError, match="MCP server not found"):
            await manager.start_server("nonexistent")

    @pytest.mark.asyncio
    async def test_start_servers_multiple(self):
        """Test start_servers starts multiple servers."""
        from kubani.cli.mcp_manager import MCPServerManager, MCPServerProcess

        manager = MCPServerManager()

        mock_process = MCPServerProcess(
            name="test", port=8080, process=MagicMock(), url="http://localhost:8080"
        )

        with patch.object(manager, "start_server", new_callable=AsyncMock) as mock_start:
            mock_start.return_value = mock_process

            await manager.start_servers(["memory", "discord"])

            assert mock_start.call_count == 2
