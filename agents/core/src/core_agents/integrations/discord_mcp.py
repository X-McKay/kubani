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
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Default channel names for each agent type
DEFAULT_CHANNELS = {
    "k8s-monitor": "kubani-alerts",
    "news-monitor": "ai-news",
    "default": "kubani-alerts",
}

DEFAULT_MCP_URL = "https://discord-mcp.almckay.io/mcp"


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
    if not url.endswith("/mcp"):
        url = f"{url}/mcp"
    return url


def _create_mcp_client():
    """Create an MCP client for the Discord server."""
    from mcp.client.streamable_http import streamablehttp_client
    from strands.tools.mcp import MCPClient

    return MCPClient(lambda: streamablehttp_client(_get_mcp_url()))


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
            tools = client.list_tools_sync()
            send_tool = next(
                (t for t in tools if getattr(t, "tool_name", "") == "send_message_to_channel_name"),
                None,
            )

            if not send_tool:
                logger.error("send_message_to_channel_name tool not found in Discord MCP server")
                return None

            # Build tool input
            tool_input: dict[str, Any] = {"channel_name": channel}
            if content:
                tool_input["content"] = content
            if embed:
                tool_input["embed"] = embed

            # Execute the tool
            tool_use = {
                "toolUseId": "discord_send",
                "name": "send_message_to_channel_name",
                "input": tool_input,
            }

            result = None
            for event in send_tool.stream(tool_use, {}):
                if hasattr(event, "result"):
                    result = event.result

            if result and isinstance(result, dict):
                message_id = result.get("message_id")
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
            tools = client.list_tools_sync()

            # First, get channel ID from channel name
            list_channels_tool = next(
                (t for t in tools if getattr(t, "tool_name", "") == "list_channels"),
                None,
            )
            if not list_channels_tool:
                logger.error("list_channels tool not found")
                return False

            tool_use = {
                "toolUseId": "list_channels",
                "name": "list_channels",
                "input": {},
            }
            channels_result = None
            for event in list_channels_tool.stream(tool_use, {}):
                if hasattr(event, "result"):
                    channels_result = event.result

            if not channels_result:
                return False

            channel_id = None
            for ch in channels_result.get("channels", []):
                if ch.get("name") == channel_name:
                    channel_id = ch.get("channel_id")
                    break

            if not channel_id:
                logger.error(f"Channel '{channel_name}' not found")
                return False

            # Now add the reaction
            add_reaction_tool = next(
                (t for t in tools if getattr(t, "tool_name", "") == "add_reaction"),
                None,
            )
            if not add_reaction_tool:
                logger.error("add_reaction tool not found")
                return False

            tool_use = {
                "toolUseId": "add_reaction",
                "name": "add_reaction",
                "input": {
                    "channel_id": channel_id,
                    "message_id": message_id,
                    "emoji": emoji,
                },
            }

            return any(hasattr(event, "result") for event in add_reaction_tool.stream(tool_use, {}))

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
            tools = client.list_tools_sync()

            # Get channel ID
            list_channels_tool = next(
                (t for t in tools if getattr(t, "tool_name", "") == "list_channels"),
                None,
            )
            if not list_channels_tool:
                return None

            tool_use = {
                "toolUseId": "list_channels",
                "name": "list_channels",
                "input": {},
            }
            channels_result = None
            for event in list_channels_tool.stream(tool_use, {}):
                if hasattr(event, "result"):
                    channels_result = event.result

            if not channels_result:
                return None

            channel_id = None
            for ch in channels_result.get("channels", []):
                if ch.get("name") == channel_name:
                    channel_id = ch.get("channel_id")
                    break

            if not channel_id:
                logger.error(f"Channel '{channel_name}' not found")
                return None

            # Wait for reaction
            await_reaction_tool = next(
                (t for t in tools if getattr(t, "tool_name", "") == "await_reaction"),
                None,
            )
            if not await_reaction_tool:
                logger.error("await_reaction tool not found")
                return None

            tool_input: dict[str, Any] = {
                "channel_id": channel_id,
                "message_id": message_id,
                "timeout_seconds": timeout_seconds,
            }
            if valid_emojis:
                tool_input["valid_emojis"] = valid_emojis

            tool_use = {
                "toolUseId": "await_reaction",
                "name": "await_reaction",
                "input": tool_input,
            }

            result = None
            for event in await_reaction_tool.stream(tool_use, {}):
                if hasattr(event, "result"):
                    result = event.result

            if result and isinstance(result, dict):
                emoji = result.get("emoji")
                user = result.get("user")
                if emoji and user:
                    return (emoji, user)

            return None

    except Exception as e:
        logger.error(f"Failed to await reaction: {e}")
        return None


def is_mcp_discord_configured() -> bool:
    """Check if Discord MCP is configured."""
    return os.environ.get("DISCORD_MCP_URL") is not None


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
