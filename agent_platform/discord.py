"""
Discord webhook integration for agent notifications.

Provides simple helpers for posting messages to Discord channels
via webhooks.
"""

import os
from dataclasses import dataclass
from typing import Any

import httpx


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


# Color constants for different message types
class Colors:
    SUCCESS = 0x57F287  # Green
    WARNING = 0xFEE75C  # Yellow
    ERROR = 0xED4245  # Red
    INFO = 0x5865F2  # Blurple
    NEUTRAL = 0x99AAB5  # Gray


async def send_discord_message(
    content: str | None = None,
    embeds: list[DiscordEmbed] | None = None,
    webhook_url: str | None = None,
    username: str = "Kubani Agent",
    avatar_url: str | None = None,
) -> bool:
    """
    Send a message to Discord via webhook.

    Args:
        content: Plain text message content.
        embeds: List of DiscordEmbed objects for rich messages.
        webhook_url: Discord webhook URL. Defaults to DISCORD_WEBHOOK_URL env var.
        username: Bot username to display.
        avatar_url: Bot avatar URL.

    Returns:
        True if message was sent successfully.

    Raises:
        ValueError: If no webhook URL is provided.
        httpx.HTTPError: If the request fails.

    Example:
        >>> await send_discord_message(
        ...     embeds=[DiscordEmbed(
        ...         title="Cluster Health",
        ...         description="All systems operational",
        ...         color=Colors.SUCCESS,
        ...     )]
        ... )
    """
    url = webhook_url or os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        raise ValueError("Discord webhook URL must be provided or set via DISCORD_WEBHOOK_URL")

    payload: dict[str, Any] = {
        "username": username,
    }

    if content:
        payload["content"] = content

    if embeds:
        payload["embeds"] = [e.to_dict() for e in embeds]

    if avatar_url:
        payload["avatar_url"] = avatar_url

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()

    return True


def send_discord_message_sync(
    content: str | None = None,
    embeds: list[DiscordEmbed] | None = None,
    webhook_url: str | None = None,
    username: str = "Kubani Agent",
    avatar_url: str | None = None,
) -> bool:
    """Synchronous version of send_discord_message."""
    url = webhook_url or os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        raise ValueError("Discord webhook URL must be provided or set via DISCORD_WEBHOOK_URL")

    payload: dict[str, Any] = {
        "username": username,
    }

    if content:
        payload["content"] = content

    if embeds:
        payload["embeds"] = [e.to_dict() for e in embeds]

    if avatar_url:
        payload["avatar_url"] = avatar_url

    with httpx.Client() as client:
        response = client.post(url, json=payload)
        response.raise_for_status()

    return True
