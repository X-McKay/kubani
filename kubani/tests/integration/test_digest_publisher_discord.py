"""Integration tests for DigestPublisher Discord functionality.

These tests verify the Discord integration works correctly with mocked MCP client.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kubani.agents.digest_publisher import DigestPublisherAgent
from kubani.framework.mcp.client import MCPResponse


@pytest.fixture
def mock_mcp_client():
    """Create a mock MCP client with Discord support."""
    client = MagicMock()
    client.discord = MagicMock()
    client.discord.health_check = AsyncMock(return_value=True)
    client.discord.send_message_to_channel_name = AsyncMock(
        return_value=MCPResponse(
            success=True,
            data={"message_id": "123456789"},
            error=None,
        )
    )
    return client


@pytest.fixture
def mock_config():
    """Create a mock config with Discord enabled."""
    config = MagicMock()
    config.mcp.discord_enabled = True
    config.mcp.discord_url = "http://localhost:8084"
    config.discord.digest_channel = "ai-news"
    config.discord.breaking_news_channel = "ai-breaking-news"
    config.discord.alerts_channel = "alerts"
    return config


class TestDigestPublisherDiscordIntegration:
    """Test DigestPublisher Discord integration."""

    @pytest.mark.asyncio
    async def test_publish_digest_success(self, mock_mcp_client, mock_config):
        """Test publishing a digest successfully."""
        with patch(
            "kubani.agents.digest_publisher.agent.get_mcp_client", return_value=mock_mcp_client
        ), patch("kubani.agents.digest_publisher.agent.get_config", return_value=mock_config):
            agent = DigestPublisherAgent()

            result = await agent._publish_digest_async(
                content="Test digest content",
                channel_name="ai-news",
            )

            assert result.success is True
            assert result.message_id == "123456789"
            assert result.channel == "ai-news"

            # Verify MCP client was called correctly
            mock_mcp_client.discord.send_message_to_channel_name.assert_called_once_with(
                channel_name="ai-news",
                content="Test digest content",
            )

    @pytest.mark.asyncio
    async def test_publish_digest_uses_config_channel(self, mock_mcp_client, mock_config):
        """Test that publishing uses channel from config when not specified."""
        with patch(
            "kubani.agents.digest_publisher.agent.get_mcp_client", return_value=mock_mcp_client
        ), patch("kubani.agents.digest_publisher.agent.get_config", return_value=mock_config):
            agent = DigestPublisherAgent()

            result = await agent._publish_digest_async(
                content="Test content",
                channel_name=None,  # Should use config
            )

            assert result.success is True
            # Should use config.discord.digest_channel
            mock_mcp_client.discord.send_message_to_channel_name.assert_called_once_with(
                channel_name="ai-news",
                content="Test content",
            )

    @pytest.mark.asyncio
    async def test_publish_digest_chunking(self, mock_mcp_client, mock_config):
        """Test that long content is chunked properly."""
        with patch(
            "kubani.agents.digest_publisher.agent.get_mcp_client", return_value=mock_mcp_client
        ), patch("kubani.agents.digest_publisher.agent.get_config", return_value=mock_config):
            agent = DigestPublisherAgent()

            # Create content that will be split into multiple chunks
            long_content = "A" * 2000 + "\n\n" + "B" * 2000

            result = await agent._publish_digest_async(
                content=long_content,
                channel_name="ai-news",
            )

            assert result.success is True
            # Should have called send_message multiple times for chunks
            assert mock_mcp_client.discord.send_message_to_channel_name.call_count >= 2

    @pytest.mark.asyncio
    async def test_publish_digest_discord_disabled(self, mock_mcp_client, mock_config):
        """Test that publishing fails gracefully when Discord is disabled."""
        mock_config.mcp.discord_enabled = False

        with patch(
            "kubani.agents.digest_publisher.agent.get_mcp_client", return_value=mock_mcp_client
        ), patch("kubani.agents.digest_publisher.agent.get_config", return_value=mock_config):
            agent = DigestPublisherAgent()

            result = await agent._publish_digest_async(
                content="Test content",
                channel_name="ai-news",
            )

            assert result.success is False
            assert "not configured" in result.error.lower()
            # MCP client should not have been called
            mock_mcp_client.discord.send_message_to_channel_name.assert_not_called()

    @pytest.mark.asyncio
    async def test_publish_digest_mcp_unhealthy(self, mock_mcp_client, mock_config):
        """Test that publishing fails gracefully when MCP is unhealthy."""
        mock_mcp_client.discord.health_check = AsyncMock(return_value=False)

        with patch(
            "kubani.agents.digest_publisher.agent.get_mcp_client", return_value=mock_mcp_client
        ), patch("kubani.agents.digest_publisher.agent.get_config", return_value=mock_config):
            agent = DigestPublisherAgent()

            result = await agent._publish_digest_async(
                content="Test content",
                channel_name="ai-news",
            )

            assert result.success is False
            assert "unavailable" in result.error.lower()

    @pytest.mark.asyncio
    async def test_publish_breaking_alert_with_embed(self, mock_mcp_client, mock_config):
        """Test publishing a breaking news alert with embed."""
        with patch(
            "kubani.agents.digest_publisher.agent.get_mcp_client", return_value=mock_mcp_client
        ), patch("kubani.agents.digest_publisher.agent.get_config", return_value=mock_config):
            agent = DigestPublisherAgent()

            article = {
                "title": "Major AI Breakthrough",
                "ai_summary": "Scientists achieved a major breakthrough in AI research.",
                "url": "https://example.com/news",
                "source": "TechNews",
                "category": "research",
            }

            result = await agent._publish_breaking_alert_async(
                article=article,
                channel_name="ai-breaking-news",
            )

            assert result.success is True

            # Verify embed was included
            call_kwargs = mock_mcp_client.discord.send_message_to_channel_name.call_args.kwargs
            assert "embed" in call_kwargs
            assert "BREAKING" in call_kwargs["embed"]["title"]
            assert call_kwargs["embed"]["color"] == 15158332  # Red

    @pytest.mark.asyncio
    async def test_compose_and_publish_integration(self, mock_mcp_client, mock_config):
        """Test the full compose_and_publish flow."""
        with patch(
            "kubani.agents.digest_publisher.agent.get_mcp_client", return_value=mock_mcp_client
        ), patch("kubani.agents.digest_publisher.agent.get_config", return_value=mock_config):
            agent = DigestPublisherAgent()

            articles = [
                {
                    "title": "AI News Article 1",
                    "ai_summary": "Summary of article 1",
                    "url": "https://example.com/1",
                    "source": "Source1",
                    "importance_score": 8,
                },
                {
                    "title": "AI News Article 2",
                    "ai_summary": "Summary of article 2",
                    "url": "https://example.com/2",
                    "source": "Source2",
                    "importance_score": 7,
                },
            ]

            trends = [
                {"topic": "LLM", "status": "rising"},
                {"topic": "RAG", "status": "stable"},
            ]

            result = await agent.compose_and_publish(
                articles=articles,
                trends=trends,
                channel_name="ai-news",
            )

            assert result.success is True
            assert mock_mcp_client.discord.send_message_to_channel_name.called
