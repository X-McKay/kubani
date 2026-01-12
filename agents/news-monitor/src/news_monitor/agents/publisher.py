"""
Discord Publisher Agent - Publishes digests and alerts to Discord.

Responsible for:
- Publishing regular digests to the #ai-news channel
- Sending breaking news alerts immediately
- Formatting messages with Discord embeds
- Publishing granular messages with reactions for feedback

Uses Discord MCP server for channel-based routing.
"""

import logging
from typing import Any

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

    def publish_granular_messages(
        self,
        messages: list[dict[str, Any]],
        channel_name: str = "ai-news",
    ) -> list[dict[str, Any]]:
        """
        Publish multiple messages and add suggested reactions.

        Each message dict should have:
        - 'category': str (e.g., 'topline', 'research', 'tools')
        - 'content': str (the message text)
        - 'reactions': list[str] (suggested emoji reactions)

        Args:
            messages: List of message dicts from ExecutiveBrief.to_granular_messages()
            channel_name: Discord channel name to publish to

        Returns:
            List of dicts with message_id, category, and channel_name for tracking
        """
        if not is_mcp_discord_configured():
            logger.warning("Cannot publish - Discord MCP not configured")
            return []

        results = []

        for msg in messages:
            try:
                content = msg.get("content", "")
                category = msg.get("category", "unknown")
                reactions = msg.get("reactions", [])

                # Send the message
                message_id = send_discord_message_sync(
                    content=content,
                    agent_name="news-monitor",
                )

                if message_id:
                    # Add suggested reactions for feedback collection
                    for emoji in reactions:
                        try:
                            # Use asyncio.run for the async add_reaction function
                            import asyncio

                            from core_agents.integrations.discord_mcp import add_reaction

                            asyncio.get_event_loop().run_until_complete(
                                add_reaction(channel_name, message_id, emoji)
                            )
                        except RuntimeError:
                            # If there's no event loop, create one
                            asyncio.run(add_reaction(channel_name, message_id, emoji))
                        except Exception as e:
                            logger.debug(f"Failed to add reaction {emoji}: {e}")

                    results.append(
                        {
                            "message_id": message_id,
                            "category": category,
                            "channel_name": channel_name,
                        }
                    )
                    logger.info(f"Published {category} message to Discord")

            except Exception as e:
                logger.error(f"Failed to publish {msg.get('category', 'unknown')}: {e}")

        return results

    def close(self):
        """No-op for compatibility. MCP client handles its own resources."""
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
