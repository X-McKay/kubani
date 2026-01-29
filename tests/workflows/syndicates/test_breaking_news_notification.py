"""Tests for breaking news Discord notification."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestSendBreakingNewsActivity:
    """Tests for send_breaking_news_activity."""

    @pytest.mark.asyncio
    async def test_sends_embed_to_discord(self):
        """Test that breaking news sends an embed to Discord."""
        from kubani.framework.temporal.discord import send_breaking_news_activity

        mock_client = MagicMock()
        mock_discord = AsyncMock()
        mock_discord.send_message_to_channel_name.return_value = MagicMock(
            success=True,
            data={"message_id": "123456", "channel_id": "789"},
        )
        mock_client.discord = mock_discord

        with patch(
            "kubani.framework.temporal.discord._get_mcp_client",
            return_value=mock_client,
        ):
            result = await send_breaking_news_activity(
                channel_name="ai-news-breaking",
                articles=[
                    {
                        "title": "OpenAI Releases GPT-5",
                        "url": "https://example.com/gpt5",
                        "reason": "Major model release",
                        "urgency": 9,
                    }
                ],
            )

        assert result["success"] is True
        assert result["message_id"] == "123456"
        mock_discord.send_message_to_channel_name.assert_called_once()

        # Verify embed format is correct for Discord MCP
        call_kwargs = mock_discord.send_message_to_channel_name.call_args[1]
        embed = call_kwargs["embed"]
        assert isinstance(embed.get("footer"), str), "Footer should be a string, not a dict"

    @pytest.mark.asyncio
    async def test_formats_multiple_articles(self):
        """Test that multiple breaking articles are formatted correctly."""
        from kubani.framework.temporal.discord import send_breaking_news_activity

        mock_client = MagicMock()
        mock_discord = AsyncMock()
        mock_discord.send_message_to_channel_name.return_value = MagicMock(
            success=True,
            data={"message_id": "123456"},
        )
        mock_client.discord = mock_discord

        with patch(
            "kubani.framework.temporal.discord._get_mcp_client",
            return_value=mock_client,
        ):
            result = await send_breaking_news_activity(
                channel_name="ai-news-breaking",
                articles=[
                    {"title": "Article 1", "url": "https://a.com", "reason": "R1", "urgency": 9},
                    {"title": "Article 2", "url": "https://b.com", "reason": "R2", "urgency": 8},
                ],
            )

        assert result["success"] is True
        assert result["articles_notified"] == 2

    @pytest.mark.asyncio
    async def test_returns_failure_on_discord_error(self):
        """Test that Discord errors are handled gracefully."""
        from kubani.framework.temporal.discord import send_breaking_news_activity

        mock_client = MagicMock()
        mock_discord = AsyncMock()
        mock_discord.send_message_to_channel_name.return_value = MagicMock(
            success=False,
            error="Channel not found",
        )
        mock_client.discord = mock_discord

        with patch(
            "kubani.framework.temporal.discord._get_mcp_client",
            return_value=mock_client,
        ):
            result = await send_breaking_news_activity(
                channel_name="nonexistent-channel",
                articles=[
                    {"title": "Test", "url": "https://test.com", "reason": "Test", "urgency": 8}
                ],
            )

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_skips_empty_articles_list(self):
        """Test that empty articles list returns early without calling Discord."""
        from kubani.framework.temporal.discord import send_breaking_news_activity

        mock_client = MagicMock()
        mock_discord = AsyncMock()
        mock_client.discord = mock_discord

        with patch(
            "kubani.framework.temporal.discord._get_mcp_client",
            return_value=mock_client,
        ):
            result = await send_breaking_news_activity(
                channel_name="ai-news-breaking",
                articles=[],
            )

        assert result["success"] is True
        assert result["articles_notified"] == 0
        mock_discord.send_message_to_channel_name.assert_not_called()


class TestNewsCollectionWorkflowBreakingIntegration:
    """Tests for breaking news integration in NewsCollectionWorkflow."""

    def test_notify_method_exists(self):
        """Test that _notify_breaking_news method exists."""
        from kubani.syndicates.news_digest.workflows.collection import NewsCollectionWorkflow

        workflow = NewsCollectionWorkflow()
        assert hasattr(workflow, "_notify_breaking_news")
        assert callable(workflow._notify_breaking_news)

    def test_breaking_articles_list_stored(self):
        """Test that workflow stores breaking articles list, not just count."""
        from kubani.syndicates.news_digest.workflows.collection import NewsCollectionWorkflow

        workflow = NewsCollectionWorkflow()
        # After initialization, should have a place to store breaking articles
        assert hasattr(workflow, "_breaking_articles")
