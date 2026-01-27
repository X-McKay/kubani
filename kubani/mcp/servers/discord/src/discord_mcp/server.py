"""
Discord MCP Server implementation.

Provides MCP tools for bidirectional Discord communication.
"""

import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Any

import discord
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from discord_mcp.client import DiscordClient, DiscordConfig, get_client, set_client
from discord_mcp.models import (
    ChannelResult,
    ChannelsResult,
    EmbedModel,
    MessageResult,
    MessagesResult,
    ReactionInfo,
    ReactionsResult,
    ReactionWaitResult,
    SuccessResult,
    WebhookResult,
    WebhooksResult,
)

logger = logging.getLogger(__name__)

# Global Discord client - connected once at server startup
_discord_client: DiscordClient | None = None


async def connect_discord() -> DiscordClient:
    """Connect to Discord at server startup (called once)."""
    global _discord_client

    if _discord_client is not None:
        return _discord_client

    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        logger.error("DISCORD_BOT_TOKEN environment variable not set")
        raise ValueError("DISCORD_BOT_TOKEN is required")

    guild_id = os.environ.get("DISCORD_GUILD_ID")

    config = DiscordConfig(
        bot_token=token,
        guild_id=int(guild_id) if guild_id else None,
    )

    _discord_client = DiscordClient(config)
    set_client(_discord_client)

    logger.info("Connecting to Discord (server startup)...")
    await _discord_client.connect()
    logger.info("Discord client ready - connection will persist for server lifetime")

    return _discord_client


async def disconnect_discord() -> None:
    """Disconnect from Discord at server shutdown."""
    global _discord_client

    if _discord_client is not None:
        logger.info("Disconnecting from Discord (server shutdown)...")
        await _discord_client.disconnect()
        _discord_client = None


def _message_to_result(msg: discord.Message) -> MessageResult:
    """Convert a Discord message to a MessageResult."""
    return MessageResult(
        message_id=str(msg.id),
        channel_id=str(msg.channel.id),
        content=msg.content,
        author=msg.author.display_name,
        author_id=str(msg.author.id),
        created_at=msg.created_at,
        is_bot=msg.author.bot,
        has_embeds=len(msg.embeds) > 0,
        reply_to=str(msg.reference.message_id) if msg.reference else None,
    )


def _channel_to_result(channel: discord.TextChannel) -> ChannelResult:
    """Convert a Discord channel to a ChannelResult."""
    return ChannelResult(
        channel_id=str(channel.id),
        name=channel.name,
        topic=channel.topic,
        category=channel.category.name if channel.category else None,
        category_id=str(channel.category.id) if channel.category else None,
        position=channel.position,
    )


def _embed_model_to_discord(embed_model: EmbedModel) -> discord.Embed:
    """Convert an EmbedModel to a Discord Embed."""
    embed = discord.Embed(
        title=embed_model.title,
        description=embed_model.description,
        color=embed_model.color,
        url=embed_model.url,
        timestamp=embed_model.timestamp,
    )
    if embed_model.footer:
        embed.set_footer(text=embed_model.footer)
    if embed_model.thumbnail_url:
        embed.set_thumbnail(url=embed_model.thumbnail_url)
    if embed_model.image_url:
        embed.set_image(url=embed_model.image_url)
    if embed_model.author_name:
        embed.set_author(
            name=embed_model.author_name,
            url=embed_model.author_url,
            icon_url=embed_model.author_icon_url,
        )
    if embed_model.fields:
        for field in embed_model.fields:
            embed.add_field(name=field.name, value=field.value, inline=field.inline)
    return embed


def _get_client_or_error() -> DiscordClient:
    """Get the Discord client or raise an error."""
    client = get_client()
    if not client:
        raise RuntimeError(
            "Discord client not initialized. Ensure connect_discord() was called at server startup."
        )
    return client


@asynccontextmanager
async def lifespan(server: FastMCP):
    """
    MCP session lifespan - no-op since Discord is managed at server level.

    Discord connection is established before the MCP server starts accepting
    connections (in main()), so we don't need to manage it per-session.
    """
    yield


def create_server() -> FastMCP:
    """Create and configure the Discord MCP server."""
    # Get allowed hosts from environment or use defaults
    allowed_hosts_env = os.environ.get("MCP_ALLOWED_HOSTS", "")
    allowed_hosts = ["localhost:*", "127.0.0.1:*"]
    if allowed_hosts_env:
        allowed_hosts.extend(h.strip() for h in allowed_hosts_env.split(",") if h.strip())

    mcp = FastMCP(
        name="Discord MCP Server",
        instructions=(
            "Bidirectional Discord integration for AI agents. "
            "Use these tools to send messages, read replies, manage reactions, "
            "channels, and webhooks in Discord."
        ),
        lifespan=lifespan,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=allowed_hosts,
        ),
    )

    # =========================================================================
    # Message Tools
    # =========================================================================

    @mcp.tool()
    async def send_message(
        channel_id: str,
        content: str | None = None,
        embed: dict[str, Any] | None = None,
    ) -> MessageResult:
        """
        Send a message to a Discord channel.

        Args:
            channel_id: The Discord channel ID to send to
            content: Text content of the message
            embed: Optional embed object for rich formatting

        Returns:
            Information about the sent message
        """
        client = _get_client_or_error()
        channel = client.get_channel(int(channel_id))
        if not channel:
            raise ValueError(f"Channel {channel_id} not found")

        discord_embed = None
        if embed:
            embed_model = EmbedModel.model_validate(embed)
            discord_embed = _embed_model_to_discord(embed_model)

        msg = await client.send_message(channel, content=content, embed=discord_embed)
        return _message_to_result(msg)

    @mcp.tool()
    async def send_message_to_channel_name(
        channel_name: str,
        content: str | None = None,
        embed: dict[str, Any] | None = None,
    ) -> MessageResult:
        """
        Send a message to a Discord channel by name.

        Args:
            channel_name: Name of the channel (without #)
            content: Text content of the message
            embed: Optional embed object for rich formatting

        Returns:
            Information about the sent message
        """
        client = _get_client_or_error()
        channel = client.get_channel_by_name(channel_name)
        if not channel:
            raise ValueError(f"Channel '{channel_name}' not found")

        discord_embed = None
        if embed:
            embed_model = EmbedModel.model_validate(embed)
            discord_embed = _embed_model_to_discord(embed_model)

        msg = await client.send_message(channel, content=content, embed=discord_embed)
        return _message_to_result(msg)

    @mcp.tool()
    async def get_messages(
        channel_id: str,
        limit: int = 10,
    ) -> MessagesResult:
        """
        Get recent messages from a Discord channel.

        Args:
            channel_id: The Discord channel ID
            limit: Maximum number of messages to retrieve (default: 10, max: 100)

        Returns:
            List of recent messages
        """
        client = _get_client_or_error()
        channel = client.get_channel(int(channel_id))
        if not channel:
            raise ValueError(f"Channel {channel_id} not found")

        limit = min(limit, 100)
        messages = await client.get_messages(channel, limit=limit)

        return MessagesResult(
            messages=[_message_to_result(m) for m in messages],
            channel_id=channel_id,
            count=len(messages),
        )

    @mcp.tool()
    async def get_messages_by_channel_name(
        channel_name: str,
        limit: int = 10,
    ) -> MessagesResult:
        """
        Get recent messages from a Discord channel by name.

        Args:
            channel_name: Name of the channel (without #)
            limit: Maximum number of messages to retrieve (default: 10, max: 100)

        Returns:
            List of recent messages
        """
        client = _get_client_or_error()
        channel = client.get_channel_by_name(channel_name)
        if not channel:
            raise ValueError(f"Channel '{channel_name}' not found")

        limit = min(limit, 100)
        messages = await client.get_messages(channel, limit=limit)

        return MessagesResult(
            messages=[_message_to_result(m) for m in messages],
            channel_id=str(channel.id),
            count=len(messages),
        )

    @mcp.tool()
    async def get_message(
        channel_id: str,
        message_id: str,
    ) -> MessageResult:
        """
        Get a specific message by ID.

        Args:
            channel_id: The Discord channel ID
            message_id: The message ID to retrieve

        Returns:
            The message details
        """
        client = _get_client_or_error()
        channel = client.get_channel(int(channel_id))
        if not channel:
            raise ValueError(f"Channel {channel_id} not found")

        msg = await client.get_message(channel, int(message_id))
        if not msg:
            raise ValueError(f"Message {message_id} not found")

        return _message_to_result(msg)

    @mcp.tool()
    async def delete_message(
        channel_id: str,
        message_id: str,
    ) -> SuccessResult:
        """
        Delete a message from a Discord channel.

        Args:
            channel_id: The Discord channel ID
            message_id: The message ID to delete

        Returns:
            Success confirmation
        """
        client = _get_client_or_error()
        channel = client.get_channel(int(channel_id))
        if not channel:
            raise ValueError(f"Channel {channel_id} not found")

        msg = await client.get_message(channel, int(message_id))
        if not msg:
            raise ValueError(f"Message {message_id} not found")

        await client.delete_message(msg)
        return SuccessResult(message=f"Deleted message {message_id}")

    @mcp.tool()
    async def await_reply(
        channel_id: str,
        timeout_seconds: float = 300.0,
        to_message_id: str | None = None,
    ) -> MessageResult | None:
        """
        Wait for a reply in a Discord channel.

        Args:
            channel_id: The Discord channel ID to watch
            timeout_seconds: How long to wait (default: 300s / 5 minutes)
            to_message_id: Only consider replies to this specific message

        Returns:
            The reply message, or None if timeout
        """
        client = _get_client_or_error()
        channel = client.get_channel(int(channel_id))
        if not channel:
            raise ValueError(f"Channel {channel_id} not found")

        reference_msg = None
        if to_message_id:
            reference_msg = await client.get_message(channel, int(to_message_id))

        reply = await client.await_reply(
            channel,
            reference_message=reference_msg,
            timeout=timeout_seconds,
        )

        if reply:
            return _message_to_result(reply)
        return None

    # =========================================================================
    # Reaction Tools
    # =========================================================================

    @mcp.tool()
    async def add_reaction(
        channel_id: str,
        message_id: str,
        emoji: str,
    ) -> SuccessResult:
        """
        Add a reaction to a message.

        Args:
            channel_id: The Discord channel ID
            message_id: The message ID to react to
            emoji: The emoji to add (unicode or custom emoji string)

        Returns:
            Success confirmation
        """
        client = _get_client_or_error()
        channel = client.get_channel(int(channel_id))
        if not channel:
            raise ValueError(f"Channel {channel_id} not found")

        msg = await client.get_message(channel, int(message_id))
        if not msg:
            raise ValueError(f"Message {message_id} not found")

        await client.add_reaction(msg, emoji)
        return SuccessResult(message=f"Added reaction {emoji} to message {message_id}")

    @mcp.tool()
    async def remove_reaction(
        channel_id: str,
        message_id: str,
        emoji: str,
    ) -> SuccessResult:
        """
        Remove the bot's reaction from a message.

        Args:
            channel_id: The Discord channel ID
            message_id: The message ID
            emoji: The emoji to remove

        Returns:
            Success confirmation
        """
        client = _get_client_or_error()
        channel = client.get_channel(int(channel_id))
        if not channel:
            raise ValueError(f"Channel {channel_id} not found")

        msg = await client.get_message(channel, int(message_id))
        if not msg:
            raise ValueError(f"Message {message_id} not found")

        await client.remove_reaction(msg, emoji)
        return SuccessResult(message=f"Removed reaction {emoji} from message {message_id}")

    @mcp.tool()
    async def get_reactions(
        channel_id: str,
        message_id: str,
    ) -> ReactionsResult:
        """
        Get all reactions on a message.

        Args:
            channel_id: The Discord channel ID
            message_id: The message ID

        Returns:
            All reactions with user information
        """
        client = _get_client_or_error()
        channel = client.get_channel(int(channel_id))
        if not channel:
            raise ValueError(f"Channel {channel_id} not found")

        msg = await client.get_message(channel, int(message_id))
        if not msg:
            raise ValueError(f"Message {message_id} not found")

        reactions_dict = await client.get_reactions(msg)

        reactions = [
            ReactionInfo(emoji=emoji, count=len(users), users=users)
            for emoji, users in reactions_dict.items()
        ]

        return ReactionsResult(message_id=message_id, reactions=reactions)

    @mcp.tool()
    async def await_reaction(
        channel_id: str,
        message_id: str,
        valid_emojis: list[str] | None = None,
        timeout_seconds: float = 300.0,
    ) -> ReactionWaitResult | None:
        """
        Wait for a reaction on a message.

        Args:
            channel_id: The Discord channel ID
            message_id: The message ID to watch
            valid_emojis: Only accept these emojis (None = any)
            timeout_seconds: How long to wait (default: 300s / 5 minutes)

        Returns:
            The reaction details, or None if timeout
        """
        client = _get_client_or_error()
        channel = client.get_channel(int(channel_id))
        if not channel:
            raise ValueError(f"Channel {channel_id} not found")

        msg = await client.get_message(channel, int(message_id))
        if not msg:
            raise ValueError(f"Message {message_id} not found")

        result = await client.await_reaction(
            msg,
            emojis=valid_emojis,
            timeout=timeout_seconds,
        )

        if result:
            emoji, user = result
            return ReactionWaitResult(emoji=emoji, user=user, message_id=message_id)
        return None

    # =========================================================================
    # Channel Tools
    # =========================================================================

    @mcp.tool()
    async def list_channels() -> ChannelsResult:
        """
        List all text channels in the configured guild.

        Returns:
            List of channels with their details
        """
        client = _get_client_or_error()
        if not client.guild:
            raise ValueError("No default guild configured. Set DISCORD_GUILD_ID.")

        channels = await client.list_channels()

        return ChannelsResult(
            channels=[_channel_to_result(c) for c in channels],
            guild_id=str(client.guild.id),
            guild_name=client.guild.name,
            count=len(channels),
        )

    @mcp.tool()
    async def create_channel(
        name: str,
        topic: str | None = None,
        category_id: str | None = None,
    ) -> ChannelResult:
        """
        Create a new text channel.

        Args:
            name: Channel name (will be lowercased, spaces become hyphens)
            topic: Optional channel topic/description
            category_id: Optional category to create the channel in

        Returns:
            The created channel details
        """
        client = _get_client_or_error()
        if not client.guild:
            raise ValueError("No default guild configured. Set DISCORD_GUILD_ID.")

        category = None
        if category_id:
            cat = client.client.get_channel(int(category_id))
            if isinstance(cat, discord.CategoryChannel):
                category = cat

        channel = await client.create_channel(
            name=name,
            topic=topic,
            category=category,
        )

        return _channel_to_result(channel)

    @mcp.tool()
    async def delete_channel(
        channel_id: str,
        reason: str | None = None,
    ) -> SuccessResult:
        """
        Delete a text channel.

        Args:
            channel_id: The channel ID to delete
            reason: Optional reason for audit log

        Returns:
            Success confirmation
        """
        client = _get_client_or_error()
        channel = client.get_channel(int(channel_id))
        if not channel:
            raise ValueError(f"Channel {channel_id} not found")

        channel_name = channel.name
        await client.delete_channel(channel, reason=reason)
        return SuccessResult(message=f"Deleted channel #{channel_name} ({channel_id})")

    # =========================================================================
    # Webhook Tools
    # =========================================================================

    @mcp.tool()
    async def list_webhooks(
        channel_id: str,
    ) -> WebhooksResult:
        """
        List all webhooks for a channel.

        Args:
            channel_id: The Discord channel ID

        Returns:
            List of webhooks
        """
        client = _get_client_or_error()
        channel = client.get_channel(int(channel_id))
        if not channel:
            raise ValueError(f"Channel {channel_id} not found")

        webhooks = await client.get_webhooks(channel)

        return WebhooksResult(
            webhooks=[
                WebhookResult(
                    webhook_id=str(w.id),
                    name=w.name or "Unnamed",
                    channel_id=channel_id,
                    url=w.url,
                    token=w.token,
                )
                for w in webhooks
            ],
            channel_id=channel_id,
            count=len(webhooks),
        )

    @mcp.tool()
    async def create_webhook(
        channel_id: str,
        name: str,
        reason: str | None = None,
    ) -> WebhookResult:
        """
        Create a webhook for a channel.

        Args:
            channel_id: The Discord channel ID
            name: Name for the webhook
            reason: Optional reason for audit log

        Returns:
            The created webhook details (including URL)
        """
        client = _get_client_or_error()
        channel = client.get_channel(int(channel_id))
        if not channel:
            raise ValueError(f"Channel {channel_id} not found")

        webhook = await client.create_webhook(channel, name=name, reason=reason)

        return WebhookResult(
            webhook_id=str(webhook.id),
            name=webhook.name or name,
            channel_id=channel_id,
            url=webhook.url,
            token=webhook.token,
        )

    @mcp.tool()
    async def delete_webhook(
        channel_id: str,
        webhook_id: str,
        reason: str | None = None,
    ) -> SuccessResult:
        """
        Delete a webhook.

        Args:
            channel_id: The Discord channel ID
            webhook_id: The webhook ID to delete
            reason: Optional reason for audit log

        Returns:
            Success confirmation
        """
        client = _get_client_or_error()
        channel = client.get_channel(int(channel_id))
        if not channel:
            raise ValueError(f"Channel {channel_id} not found")

        webhooks = await client.get_webhooks(channel)
        webhook = next((w for w in webhooks if w.id == int(webhook_id)), None)
        if not webhook:
            raise ValueError(f"Webhook {webhook_id} not found in channel {channel_id}")

        await client.delete_webhook(webhook, reason=reason)
        return SuccessResult(message=f"Deleted webhook {webhook_id}")

    return mcp


def main():
    """Entry point for the Discord MCP server."""
    import anyio
    from kubani.framework.mcp.server.transport import TransportConfig, run_server_async

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr,
    )

    # Parse transport config from args
    config = TransportConfig.from_args()

    # Create the server
    mcp = create_server()

    # Run with connection management
    async def run_with_discord():
        try:
            await connect_discord()
            await run_server_async(mcp, config)
        finally:
            await disconnect_discord()

    anyio.run(run_with_discord)


if __name__ == "__main__":
    main()
