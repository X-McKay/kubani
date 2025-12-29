"""
Discord Publisher Agent - Publishes digests and alerts to Discord.

Responsible for:
- Publishing regular digests to the #ai-news channel
- Sending breaking news alerts immediately
- Formatting messages with Discord embeds
"""

import logging
import os

import httpx

from news_monitor.models import NewsDigest, ProcessedArticle

logger = logging.getLogger(__name__)


class DiscordPublisherAgent:
    """Agent for publishing to Discord."""

    def __init__(self):
        """Initialize with Discord webhook URL from environment."""
        self.webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
        self.http_client = httpx.Client(timeout=30.0)

        if not self.webhook_url:
            logger.warning("DISCORD_WEBHOOK_URL not set - publishing will be disabled")

    def publish_digest(self, digest: NewsDigest, formatted_content: str) -> str | None:
        """
        Publish a news digest to Discord.

        Args:
            digest: The news digest to publish
            formatted_content: Pre-formatted markdown content

        Returns:
            Discord message ID if successful, None otherwise
        """
        if not self.webhook_url:
            logger.warning("Cannot publish digest - no webhook URL configured")
            return None

        try:
            # Split content if too long (Discord 2000 char limit)
            chunks = self._split_message(formatted_content, max_length=1900)

            message_id = None
            for i, chunk in enumerate(chunks):
                payload = {
                    "content": chunk,
                    "username": "AI News Monitor",
                }

                response = self.http_client.post(
                    self.webhook_url + "?wait=true",  # wait=true returns message details
                    json=payload,
                )
                response.raise_for_status()

                # Get message ID from first chunk
                if i == 0:
                    data = response.json()
                    message_id = data.get("id")

            logger.info(f"Published digest {digest.digest_id} to Discord")
            return message_id

        except httpx.HTTPError as e:
            logger.error(f"Failed to publish digest to Discord: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error publishing digest: {e}")
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
        if not self.webhook_url:
            logger.warning("Cannot publish alert - no webhook URL configured")
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

            payload = {
                "content": "@here **Breaking AI News**",  # Mention for alerts
                "embeds": [embed],
                "username": "AI News Monitor",
            }

            response = self.http_client.post(
                self.webhook_url + "?wait=true",
                json=payload,
            )
            response.raise_for_status()

            data = response.json()
            message_id = data.get("id")

            logger.info(f"Published breaking alert for: {article.title[:50]}...")
            return message_id

        except httpx.HTTPError as e:
            logger.error(f"Failed to publish breaking alert: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error publishing alert: {e}")
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
        """Close the HTTP client."""
        self.http_client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
