"""
Discord Monitor.

Watches Discord channels for agent messages and reactions
to track outputs and gather feedback signals.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ReactionSummary:
    """Summary of reactions on a message."""

    message_id: str
    total_reactions: int = 0
    positive_count: int = 0  # thumbsup, fire, star
    negative_count: int = 0  # thumbsdown
    interested_count: int = 0  # eyes, bookmark
    reactions: dict[str, int] = field(default_factory=dict)

    @property
    def engagement_score(self) -> float:
        """Calculate engagement score from reactions."""
        if self.total_reactions == 0:
            return 0.0

        weighted = (
            self.positive_count * 1.0 + self.interested_count * 0.5 - self.negative_count * 0.5
        )
        return max(0.0, min(1.0, 0.5 + weighted / max(self.total_reactions, 1) * 0.5))


@dataclass
class AgentMessage:
    """A message posted by an agent to Discord."""

    message_id: str
    channel_id: str
    channel_name: str
    content: str
    author_id: str
    author_name: str
    created_at: datetime
    reactions: ReactionSummary | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_bot_message(self) -> bool:
        """Check if message is from a bot."""
        return "bot" in self.author_name.lower() or self.metadata.get("is_bot", False)

    @property
    def agent_name(self) -> str:
        """Extract agent name from author or content."""
        # Try to identify agent from author name
        if "k8s" in self.author_name.lower() or "kubernetes" in self.content.lower()[:100]:
            return "k8s_monitor"
        if "news" in self.author_name.lower() or "digest" in self.content.lower()[:100]:
            return "news_monitor"
        return "unknown_agent"

    @property
    def content_preview(self) -> str:
        """Get a preview of the content."""
        if len(self.content) <= 100:
            return self.content
        return self.content[:100] + "..."


class DiscordMonitor:
    """
    Monitors Discord channels for agent outputs.

    Uses the Discord MCP server to query messages and reactions.
    """

    # Channels to monitor for agent output
    MONITORED_CHANNELS = [
        "ai-news",
        "kubani-alerts",
        "ai-breaking-news",
        "kubani-learning",
        "kubani-approvals",
    ]

    # Emoji to sentiment mapping
    POSITIVE_EMOJIS = {"thumbsup", "fire", "star", "heart", "100", "tada"}
    NEGATIVE_EMOJIS = {"thumbsdown", "-1"}
    INTERESTED_EMOJIS = {"eyes", "bookmark", "pushpin", "memo"}

    DEFAULT_MCP_URL = "http://discord-mcp-server.ai-agents.svc:8080"

    def __init__(
        self,
        discord_mcp_url: str | None = None,
    ):
        """
        Initialize the Discord monitor.

        Args:
            discord_mcp_url: URL of the Discord MCP server
        """
        import os

        self.discord_mcp_url = discord_mcp_url or os.environ.get(
            "DISCORD_MCP_URL", self.DEFAULT_MCP_URL
        )
        self._seen_messages: set[str] = set()
        self._channel_cache: dict[str, str] = {}  # name -> id

    def _get_mcp_url(self) -> str:
        """Get the Discord MCP URL with SSE endpoint."""
        url = self.discord_mcp_url
        # Ensure URL ends with /sse for SSE transport
        if not url.endswith("/sse"):
            if url.endswith("/mcp"):
                url = url[:-4]
            url = f"{url.rstrip('/')}/sse"
        return url

    def _create_mcp_client(self):
        """Create an MCP client for the Discord server using SSE transport."""
        from mcp.client.sse import sse_client
        from strands.tools.mcp import MCPClient

        return MCPClient(lambda: sse_client(self._get_mcp_url()))

    async def close(self) -> None:
        """Close resources (no-op, MCP client is created per-call)."""
        pass

    def _call_mcp_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Call an MCP tool on the Discord server."""
        import uuid

        try:
            with self._create_mcp_client() as client:
                tool_use_id = f"discord_{uuid.uuid4().hex[:12]}"
                result = client.call_tool_sync(
                    tool_use_id=tool_use_id,
                    name=tool_name,
                    arguments=arguments,
                )

                if result and isinstance(result, dict):
                    # Extract from structuredContent (MCP result format)
                    return result.get("structuredContent", {})
                return {}

        except Exception as e:
            logger.debug(f"MCP tool call failed ({tool_name}): {type(e).__name__}: {e}")
            raise

    async def poll_agent_messages(
        self,
        since: datetime | None = None,
        channels: list[str] | None = None,
        limit: int = 20,
    ) -> list[AgentMessage]:
        """
        Poll for recent agent messages.

        Args:
            since: Only return messages after this time
            channels: Channels to monitor (defaults to MONITORED_CHANNELS)
            limit: Maximum messages per channel

        Returns:
            List of agent messages
        """
        if since is None:
            since = datetime.now(UTC) - timedelta(minutes=30)

        if channels is None:
            channels = self.MONITORED_CHANNELS

        messages = []

        for channel_name in channels:
            try:
                channel_messages = await self._get_channel_messages(
                    channel_name=channel_name,
                    limit=limit,
                )

                for msg in channel_messages:
                    # Skip if already seen
                    if msg.message_id in self._seen_messages:
                        continue

                    # Filter by time
                    if msg.created_at < since:
                        continue

                    # Only include bot messages
                    if msg.is_bot_message:
                        messages.append(msg)
                        self._seen_messages.add(msg.message_id)

            except Exception as e:
                logger.debug(f"Failed to poll channel {channel_name}: {e}")

        # Sort by time
        messages.sort(key=lambda m: m.created_at)
        return messages

    async def _get_channel_messages(
        self,
        channel_name: str,
        limit: int = 20,
    ) -> list[AgentMessage]:
        """Get messages from a specific channel."""
        try:
            result = self._call_mcp_tool(
                "get_messages_by_channel_name",
                {
                    "channel_name": channel_name,
                    "limit": limit,
                },
            )

            messages_data = result.get("messages", [])

            messages = []
            for msg_data in messages_data:
                msg = self._parse_message(msg_data, channel_name)
                if msg:
                    messages.append(msg)

            return messages

        except Exception as e:
            logger.debug(f"Failed to get messages from {channel_name}: {e}")
            return []

    async def get_message_reactions(self, message_id: str, channel_id: str) -> ReactionSummary:
        """
        Get reactions on a specific message.

        Args:
            message_id: The message ID
            channel_id: The channel ID

        Returns:
            Reaction summary
        """
        summary = ReactionSummary(message_id=message_id)

        try:
            result = self._call_mcp_tool(
                "get_reactions",
                {
                    "channel_id": channel_id,
                    "message_id": message_id,
                },
            )

            reactions = result.get("reactions", [])

            for reaction in reactions:
                emoji = reaction.get("emoji", "")
                count = reaction.get("count", 1)

                summary.reactions[emoji] = count
                summary.total_reactions += count

                emoji_name = emoji.lower().replace(":", "")
                if emoji_name in self.POSITIVE_EMOJIS:
                    summary.positive_count += count
                elif emoji_name in self.NEGATIVE_EMOJIS:
                    summary.negative_count += count
                elif emoji_name in self.INTERESTED_EMOJIS:
                    summary.interested_count += count

        except Exception as e:
            logger.debug(f"Failed to get reactions for {message_id}: {e}")

        return summary

    async def enrich_with_reactions(self, messages: list[AgentMessage]) -> list[AgentMessage]:
        """
        Enrich messages with their reactions.

        Args:
            messages: Messages to enrich

        Returns:
            Messages with reactions populated
        """
        for msg in messages:
            if msg.reactions is None:
                msg.reactions = await self.get_message_reactions(
                    msg.message_id,
                    msg.channel_id,
                )
        return messages

    def _parse_message(self, data: dict[str, Any], channel_name: str) -> AgentMessage | None:
        """Parse a Discord message from MCP response."""
        try:
            created_at = datetime.now(UTC)
            if data.get("created_at"):
                try:
                    created_at = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            return AgentMessage(
                message_id=data.get("message_id", ""),
                channel_id=data.get("channel_id", ""),
                channel_name=channel_name,
                content=data.get("content", ""),
                author_id=data.get("author_id", ""),
                author_name=data.get("author", ""),
                created_at=created_at,
                metadata={
                    "is_bot": data.get("is_bot", False),
                    "has_embeds": data.get("has_embeds", False),
                    "reply_to": data.get("reply_to"),
                },
            )

        except Exception as e:
            logger.debug(f"Failed to parse message: {e}")
            return None

    def reset_seen(self) -> None:
        """Reset the seen messages cache."""
        self._seen_messages.clear()
