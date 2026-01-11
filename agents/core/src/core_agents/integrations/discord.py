"""
Discord formatting utilities.

Provides embed structures and color constants for Discord messages.
For sending messages, use the discord_mcp module which uses the Discord MCP server.

Example:
    from core_agents.integrations.discord import DiscordEmbed, Colors
    from core_agents.integrations.discord_mcp import send_discord_message_sync

    embed = DiscordEmbed(
        title="Alert",
        description="Something happened",
        color=Colors.WARNING,
    )
    send_discord_message_sync(embed=embed.to_dict(), agent_name="my-agent")
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class DiscordEmbed:
    """Discord embed structure for rich messages."""

    title: str
    description: str
    color: int = 0x5865F2  # Discord blurple
    fields: list[dict[str, Any]] | None = None
    footer: str | None = None
    timestamp: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to Discord API format."""
        embed: dict[str, Any] = {
            "title": self.title,
            "description": self.description,
            "color": self.color,
        }
        if self.fields:
            embed["fields"] = self.fields
        if self.footer:
            embed["footer"] = {"text": self.footer}
        if self.timestamp:
            embed["timestamp"] = self.timestamp
        return embed


class Colors:
    """Color constants for different message types."""

    SUCCESS = 0x57F287  # Green
    WARNING = 0xFEE75C  # Yellow
    ERROR = 0xED4245  # Red
    INFO = 0x5865F2  # Blurple
    NEUTRAL = 0x99AAB5  # Gray
