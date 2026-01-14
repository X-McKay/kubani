"""
Discord MCP integration utilities.

Provides helper functions for interacting with Discord via the Discord MCP server.
These utilities are used by non-agent code (activities, hooks, etc.) that needs
to send Discord notifications. For agent-based Discord interaction, agents should
use skills or call MCP tools directly.

Environment Variables:
    DISCORD_MCP_URL: MCP server URL (default: https://discord-mcp.almckay.io/mcp)
    DISCORD_CHANNEL: Default channel name for notifications
"""

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


def _gen_tool_use_id() -> str:
    """Generate a unique tool use ID."""
    return f"discord_{uuid.uuid4().hex[:12]}"


# Default channel names for each agent type
DEFAULT_CHANNELS = {
    "k8s-monitor": "kubani-alerts",
    "news-monitor": "ai-news",
    "default": "kubani-alerts",
}

DEFAULT_MCP_URL = "https://discord-mcp.almckay.io/sse"


@dataclass
class DiscordMCPConfig:
    """Configuration for Discord MCP client."""

    mcp_url: str
    default_channel: str

    @classmethod
    def from_env(cls, agent_name: str = "default") -> "DiscordMCPConfig":
        """Create config from environment variables."""
        mcp_url = os.environ.get("DISCORD_MCP_URL", DEFAULT_MCP_URL)
        channel = os.environ.get(
            "DISCORD_CHANNEL",
            DEFAULT_CHANNELS.get(agent_name, DEFAULT_CHANNELS["default"]),
        )
        return cls(mcp_url=mcp_url, default_channel=channel)


def _get_mcp_url() -> str:
    """Get the Discord MCP server URL."""
    url = os.environ.get("DISCORD_MCP_URL", DEFAULT_MCP_URL)
    # Ensure URL ends with /sse for SSE transport
    if not url.endswith("/sse"):
        # Remove /mcp suffix if present and add /sse
        if url.endswith("/mcp"):
            url = url[:-4]
        url = f"{url.rstrip('/')}/sse"
    return url


def _create_mcp_client():
    """Create an MCP client for the Discord server using SSE transport."""
    from mcp.client.sse import sse_client
    from strands.tools.mcp import MCPClient

    return MCPClient(lambda: sse_client(_get_mcp_url()))


async def send_discord_message(
    content: str | None = None,
    embed: dict[str, Any] | None = None,
    channel_name: str | None = None,
    agent_name: str = "default",
) -> str | None:
    """
    Send a message to Discord via MCP (async).

    Args:
        content: Plain text message content.
        embed: Discord embed dict for rich messages.
        channel_name: Target channel name. Defaults to agent's default channel.
        agent_name: Agent identifier for default channel lookup.

    Returns:
        Message ID if successful, None otherwise.

    Example:
        >>> message_id = await send_discord_message(
        ...     content="Hello from Kubani!",
        ...     channel_name="kubani-alerts",
        ... )

        >>> message_id = await send_discord_message(
        ...     embed={
        ...         "title": "Alert",
        ...         "description": "Something happened",
        ...         "color": 0xED4245,
        ...     },
        ...     agent_name="k8s-monitor",
        ... )
    """
    config = DiscordMCPConfig.from_env(agent_name)
    channel = channel_name or config.default_channel

    if not content and not embed:
        logger.warning("No content or embed provided for Discord message")
        return None

    try:
        with _create_mcp_client() as client:
            # Build tool input
            tool_input: dict[str, Any] = {"channel_name": channel}
            if content:
                tool_input["content"] = content
            if embed:
                tool_input["embed"] = embed

            # Use call_tool_sync which properly handles the MCP protocol
            result = client.call_tool_sync(
                tool_use_id=_gen_tool_use_id(),
                name="send_message_to_channel_name",
                arguments=tool_input,
            )

            if result and isinstance(result, dict):
                # Extract from structuredContent (MCP result format)
                structured = result.get("structuredContent", {})
                message_id = structured.get("message_id") if structured else None
                logger.info(f"Sent Discord message to #{channel}: {message_id}")
                return message_id

            return None

    except Exception as e:
        logger.error(f"Failed to send Discord message via MCP: {e}")
        return None


def send_discord_message_sync(
    content: str | None = None,
    embed: dict[str, Any] | None = None,
    channel_name: str | None = None,
    agent_name: str = "default",
) -> str | None:
    """
    Send a message to Discord via MCP (synchronous).

    This is a convenience wrapper for sync contexts. See send_discord_message
    for full documentation.

    Args:
        content: Plain text message content.
        embed: Discord embed dict for rich messages.
        channel_name: Target channel name.
        agent_name: Agent identifier for default channel lookup.

    Returns:
        Message ID if successful, None otherwise.
    """
    try:
        # Check if we're in an async context
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None:
            # We're in an async context, need to run in a thread
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run,
                    send_discord_message(content, embed, channel_name, agent_name),
                )
                return future.result(timeout=30)
        else:
            # No running loop, we can use asyncio.run directly
            return asyncio.run(send_discord_message(content, embed, channel_name, agent_name))
    except Exception as e:
        logger.error(f"Failed to send Discord message sync: {e}")
        return None


async def add_reaction(
    channel_name: str,
    message_id: str,
    emoji: str,
) -> bool:
    """
    Add a reaction to a Discord message.

    Args:
        channel_name: Channel containing the message.
        message_id: Message ID to react to.
        emoji: Emoji to add (unicode or custom emoji string).

    Returns:
        True if successful, False otherwise.
    """
    try:
        with _create_mcp_client() as client:
            # First, get channel ID from channel name
            channels_result = client.call_tool_sync(
                tool_use_id=_gen_tool_use_id(),
                name="list_channels",
                arguments={},
            )

            if not channels_result:
                logger.error("Failed to list channels")
                return False

            # Extract from structuredContent (MCP result format)
            channels_data = channels_result.get("structuredContent", {})
            channel_id = None
            for ch in channels_data.get("channels", []):
                if ch.get("name") == channel_name:
                    channel_id = ch.get("channel_id")
                    break

            if not channel_id:
                logger.error(f"Channel '{channel_name}' not found")
                return False

            # Now add the reaction
            result = client.call_tool_sync(
                tool_use_id=_gen_tool_use_id(),
                name="add_reaction",
                arguments={
                    "channel_id": channel_id,
                    "message_id": message_id,
                    "emoji": emoji,
                },
            )

            # Extract success from structuredContent
            reaction_result = result.get("structuredContent", {}) if result else {}
            return reaction_result.get("success", False)

    except Exception as e:
        logger.error(f"Failed to add reaction: {e}")
        return False


async def await_reaction(
    channel_name: str,
    message_id: str,
    valid_emojis: list[str] | None = None,
    timeout_seconds: float = 300.0,
) -> tuple[str, str] | None:
    """
    Wait for a reaction on a Discord message.

    Args:
        channel_name: Channel containing the message.
        message_id: Message ID to watch.
        valid_emojis: Only accept these emojis (None = any).
        timeout_seconds: How long to wait (default: 5 minutes).

    Returns:
        Tuple of (emoji, username) if reaction received, None on timeout.
    """
    try:
        with _create_mcp_client() as client:
            # Get channel ID
            channels_result = client.call_tool_sync(
                tool_use_id=_gen_tool_use_id(),
                name="list_channels",
                arguments={},
            )

            if not channels_result:
                logger.error("Failed to list channels")
                return None

            # Extract from structuredContent (MCP result format)
            channels_data = channels_result.get("structuredContent", {})
            channel_id = None
            for ch in channels_data.get("channels", []):
                if ch.get("name") == channel_name:
                    channel_id = ch.get("channel_id")
                    break

            if not channel_id:
                logger.error(f"Channel '{channel_name}' not found")
                return None

            # Wait for reaction - use call_tool_sync with longer timeout
            tool_input: dict[str, Any] = {
                "channel_id": channel_id,
                "message_id": message_id,
                "timeout_seconds": timeout_seconds,
            }
            if valid_emojis:
                tool_input["valid_emojis"] = valid_emojis

            result = client.call_tool_sync(
                tool_use_id=_gen_tool_use_id(),
                name="await_reaction",
                arguments=tool_input,
            )

            if result and isinstance(result, dict):
                # Extract from structuredContent (MCP result format)
                structured = result.get("structuredContent", {})
                # Handle wrapped result (await_reaction returns {result: {...}})
                inner_result = structured.get("result", structured) if structured else None
                if inner_result:
                    emoji = inner_result.get("emoji")
                    user = inner_result.get("user")
                    if emoji and user:
                        return (emoji, user)

            return None

    except Exception as e:
        logger.error(f"Failed to await reaction: {e}")
        return None


def is_mcp_discord_configured() -> bool:
    """Check if Discord MCP is configured."""
    return os.environ.get("DISCORD_MCP_URL") is not None


def add_reaction_sync(
    channel_name: str,
    message_id: str,
    emoji: str,
) -> bool:
    """
    Add a reaction to a Discord message (synchronous).

    This is a convenience wrapper for sync contexts.

    Args:
        channel_name: Channel containing the message.
        message_id: Message ID to react to.
        emoji: Emoji to add (unicode or custom emoji string).

    Returns:
        True if successful, False otherwise.
    """
    try:
        # Check if we're in an async context
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None:
            # We're in an async context, need to run in a thread
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run,
                    add_reaction(channel_name, message_id, emoji),
                )
                return future.result(timeout=30)
        else:
            # No running loop, we can use asyncio.run directly
            return asyncio.run(add_reaction(channel_name, message_id, emoji))
    except Exception as e:
        logger.error(f"Failed to add reaction sync: {e}")
        return False


# Convenience function for backward compatibility
async def post_discord_message(
    content: str | None = None,
    embed: dict[str, Any] | None = None,
    channel_name: str | None = None,
) -> bool:
    """
    Post a message to Discord (backward-compatible wrapper).

    Returns True if successful, False otherwise.
    """
    result = await send_discord_message(content, embed, channel_name)
    return result is not None
