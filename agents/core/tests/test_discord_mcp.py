"""Tests for Discord MCP integration utilities."""

import os
from unittest.mock import MagicMock, patch

import pytest

from core_agents.integrations.discord_mcp import (
    DEFAULT_CHANNELS,
    DEFAULT_MCP_URL,
    DiscordMCPConfig,
    _get_mcp_url,
    is_mcp_discord_configured,
    send_discord_message,
    send_discord_message_sync,
)


class TestDiscordMCPConfig:
    """Tests for DiscordMCPConfig."""

    def test_default_values(self) -> None:
        """Test default values when no env vars are set."""
        with patch.dict(os.environ, {}, clear=True):
            config = DiscordMCPConfig.from_env()
            assert config.mcp_url == DEFAULT_MCP_URL
            assert config.default_channel == DEFAULT_CHANNELS["default"]

    def test_k8s_monitor_defaults(self) -> None:
        """Test defaults for k8s-monitor agent."""
        with patch.dict(os.environ, {}, clear=True):
            config = DiscordMCPConfig.from_env("k8s-monitor")
            assert config.default_channel == "kubani-alerts"

    def test_news_monitor_defaults(self) -> None:
        """Test defaults for news-monitor agent."""
        with patch.dict(os.environ, {}, clear=True):
            config = DiscordMCPConfig.from_env("news-monitor")
            assert config.default_channel == "ai-news"

    def test_env_override(self) -> None:
        """Test that environment variables override defaults."""
        with patch.dict(
            os.environ,
            {
                "DISCORD_MCP_URL": "http://custom-mcp.example.com/mcp",
                "DISCORD_CHANNEL": "custom-channel",
            },
        ):
            config = DiscordMCPConfig.from_env()
            assert config.mcp_url == "http://custom-mcp.example.com/mcp"
            assert config.default_channel == "custom-channel"


class TestGetMcpUrl:
    """Tests for _get_mcp_url function."""

    def test_default_url(self) -> None:
        """Test default URL when env var not set."""
        with patch.dict(os.environ, {}, clear=True):
            url = _get_mcp_url()
            assert url == DEFAULT_MCP_URL
            assert url.endswith("/mcp")

    def test_custom_url_with_mcp_suffix(self) -> None:
        """Test custom URL that already has /mcp suffix."""
        with patch.dict(os.environ, {"DISCORD_MCP_URL": "http://example.com/mcp"}):
            url = _get_mcp_url()
            assert url == "http://example.com/mcp"

    def test_custom_url_without_mcp_suffix(self) -> None:
        """Test custom URL that needs /mcp suffix added."""
        with patch.dict(os.environ, {"DISCORD_MCP_URL": "http://example.com"}):
            url = _get_mcp_url()
            assert url == "http://example.com/mcp"


class TestIsMcpDiscordConfigured:
    """Tests for is_mcp_discord_configured function."""

    def test_configured_when_env_set(self) -> None:
        """Test that returns True when DISCORD_MCP_URL is set."""
        with patch.dict(os.environ, {"DISCORD_MCP_URL": "http://example.com/mcp"}):
            assert is_mcp_discord_configured() is True

    def test_not_configured_when_env_not_set(self) -> None:
        """Test that returns False when DISCORD_MCP_URL is not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove DISCORD_MCP_URL if it exists
            os.environ.pop("DISCORD_MCP_URL", None)
            assert is_mcp_discord_configured() is False


class TestSendDiscordMessage:
    """Tests for send_discord_message function."""

    @pytest.mark.asyncio
    async def test_no_content_or_embed_returns_none(self) -> None:
        """Test that sending without content or embed returns None."""
        result = await send_discord_message()
        assert result is None

    @pytest.mark.asyncio
    async def test_mcp_client_error_returns_none(self) -> None:
        """Test that MCP client errors return None gracefully."""
        with patch(
            "core_agents.integrations.discord_mcp._create_mcp_client",
            side_effect=Exception("MCP connection failed"),
        ):
            result = await send_discord_message(content="test")
            assert result is None

    @pytest.mark.asyncio
    async def test_send_with_content(self) -> None:
        """Test sending message with content."""
        mock_client = MagicMock()
        mock_tool = MagicMock()
        mock_tool.tool_name = "send_message_to_channel_name"

        # Create mock event with result
        mock_event = MagicMock()
        mock_event.result = {"message_id": "123456789"}
        mock_tool.stream.return_value = [mock_event]

        mock_client.list_tools_sync.return_value = [mock_tool]
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch(
            "core_agents.integrations.discord_mcp._create_mcp_client",
            return_value=mock_client,
        ):
            result = await send_discord_message(
                content="Hello test",
                channel_name="test-channel",
            )

            assert result == "123456789"
            mock_tool.stream.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_with_embed(self) -> None:
        """Test sending message with embed."""
        mock_client = MagicMock()
        mock_tool = MagicMock()
        mock_tool.tool_name = "send_message_to_channel_name"

        mock_event = MagicMock()
        mock_event.result = {"message_id": "987654321"}
        mock_tool.stream.return_value = [mock_event]

        mock_client.list_tools_sync.return_value = [mock_tool]
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch(
            "core_agents.integrations.discord_mcp._create_mcp_client",
            return_value=mock_client,
        ):
            result = await send_discord_message(
                embed={"title": "Test", "description": "A test embed"},
                agent_name="k8s-monitor",
            )

            assert result == "987654321"

    @pytest.mark.asyncio
    async def test_tool_not_found_returns_none(self) -> None:
        """Test that missing tool returns None."""
        mock_client = MagicMock()
        mock_client.list_tools_sync.return_value = []  # No tools
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch(
            "core_agents.integrations.discord_mcp._create_mcp_client",
            return_value=mock_client,
        ):
            result = await send_discord_message(content="test")
            assert result is None


class TestSendDiscordMessageSync:
    """Tests for send_discord_message_sync function."""

    def test_no_content_or_embed_returns_none(self) -> None:
        """Test that sending without content or embed returns None."""
        result = send_discord_message_sync()
        assert result is None

    def test_exception_returns_none(self) -> None:
        """Test that exceptions return None gracefully."""
        with patch(
            "core_agents.integrations.discord_mcp.send_discord_message",
            side_effect=Exception("Test error"),
        ):
            result = send_discord_message_sync(content="test")
            assert result is None


class TestDefaultChannels:
    """Tests for DEFAULT_CHANNELS constant."""

    def test_k8s_monitor_channel(self) -> None:
        """Test k8s-monitor has correct default channel."""
        assert DEFAULT_CHANNELS["k8s-monitor"] == "kubani-alerts"

    def test_news_monitor_channel(self) -> None:
        """Test news-monitor has correct default channel."""
        assert DEFAULT_CHANNELS["news-monitor"] == "ai-news"

    def test_default_channel(self) -> None:
        """Test default fallback channel."""
        assert DEFAULT_CHANNELS["default"] == "kubani-alerts"
