"""
Discord Publisher Agent - Publishes digests and alerts to Discord.

Responsible for:
- Publishing regular digests to the #ai-news channel
- Sending breaking news alerts immediately
- Formatting messages with Discord embeds

Uses Discord MCP server for channel-based routing.
"""

import logging

from core_agents.integrations.discord_mcp import (
    is_mcp_discord_configured,
    send_discord_message_sync,
)
from news_monitor.models import NewsDigest, ProcessedArticle

logger = logging.getLogger(__name__)


class DiscordPublisherAgent:
    """Agent for publishing to Discord via MCP server."""

    def __init__(self):
        """Initialize Discord publisher."""
        if not is_mcp_discord_configured():
            logger.warning("Discord MCP not configured - publishing will be disabled")

    def publish_digest(self, digest: NewsDigest, formatted_content: str) -> str | None:
        """
        Publish a news digest to Discord.

        Args:
            digest: The news digest to publish
            formatted_content: Pre-formatted markdown content

        Returns:
            Discord message ID if successful, None otherwise
        """
        if not is_mcp_discord_configured():
            logger.warning("Cannot publish digest - Discord MCP not configured")
            return None

        try:
            # Split content if too long (Discord 2000 char limit)
            chunks = self._split_message(formatted_content, max_length=1900)

            message_id = None
            for i, chunk in enumerate(chunks):
                result = send_discord_message_sync(
                    content=chunk,
                    agent_name="news-monitor",
                )

                # Get message ID from first chunk
                if i == 0:
                    message_id = result

            logger.info(f"Published digest {digest.digest_id} to Discord")
            return message_id

        except Exception as e:
            logger.error(f"Failed to publish digest to Discord: {e}")
            return None

    def publish_breaking_alert(
        self,
        article: ProcessedArticle,
        formatted_content: str,
    ) -> str | None:
        """
        Publish a breaking news alert to Discord.

        Args:
            article: The breaking news article
            formatted_content: Pre-formatted alert content

        Returns:
            Discord message ID if successful, None otherwise
        """
        if not is_mcp_discord_configured():
            logger.warning("Cannot publish alert - Discord MCP not configured")
            return None

        try:
            # Use embed for breaking alerts to make them stand out
            embed = {
                "title": f"BREAKING: {article.title}",
                "description": article.ai_summary or article.original_summary,
                "url": article.url,
                "color": 15158332,  # Red color for breaking news
                "fields": [
                    {"name": "Source", "value": article.source, "inline": True},
                    {"name": "Category", "value": article.category.value.title(), "inline": True},
                ],
                "footer": {"text": "AI News Monitor - Breaking Alert"},
            }

            message_id = send_discord_message_sync(
                content="@here **Breaking AI News**",  # Mention for alerts
                embed=embed,
                agent_name="news-monitor",
            )

            logger.info(f"Published breaking alert for: {article.title[:50]}...")
            return message_id

        except Exception as e:
            logger.error(f"Failed to publish breaking alert: {e}")
            return None

    def _split_message(self, content: str, max_length: int = 1900) -> list[str]:
        """
        Split a message into chunks that fit Discord's limit.

        Args:
            content: The content to split
            max_length: Maximum length per chunk

        Returns:
            List of message chunks
        """
        if len(content) <= max_length:
            return [content]

        chunks = []
        current_chunk = ""

        # Split by paragraphs first
        paragraphs = content.split("\n\n")

        for para in paragraphs:
            if len(current_chunk) + len(para) + 2 <= max_length:
                if current_chunk:
                    current_chunk += "\n\n"
                current_chunk += para
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                # If single paragraph is too long, split by lines
                if len(para) > max_length:
                    lines = para.split("\n")
                    current_chunk = ""
                    for line in lines:
                        if len(current_chunk) + len(line) + 1 <= max_length:
                            if current_chunk:
                                current_chunk += "\n"
                            current_chunk += line
                        else:
                            if current_chunk:
                                chunks.append(current_chunk)
                            current_chunk = line
                else:
                    current_chunk = para

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    def close(self):
        """No-op for compatibility. MCP client handles its own resources."""
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
