"""
Discord client wrapper for MCP server.

Provides a managed Discord client that connects via the Gateway API
for full bidirectional communication.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import discord
from discord import (
    CategoryChannel,
    Embed,
    Guild,
    Message,
    TextChannel,
    Webhook,
)

logger = logging.getLogger(__name__)


@dataclass
class DiscordConfig:
    """Configuration for the Discord client."""

    bot_token: str
    guild_id: int | None = None  # Default guild for operations
    command_prefix: str = "!"
    intents: discord.Intents | None = None

    def get_intents(self) -> discord.Intents:
        """Get Discord intents, using provided or sensible defaults."""
        if self.intents:
            return self.intents
        # Default intents for MCP operations
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guild_messages = True
        intents.guild_reactions = True
        intents.guilds = True
        return intents


class DiscordClient:
    """
    Managed Discord client for MCP operations.

    Handles connection lifecycle and provides high-level methods
    for Discord operations used by MCP tools.
    """

    def __init__(self, config: DiscordConfig):
        self.config = config
        self._client: discord.Client | None = None
        self._ready = asyncio.Event()
        self._guild: Guild | None = None

    @property
    def client(self) -> discord.Client:
        """Get the underlying Discord client."""
        if not self._client:
            raise RuntimeError("Discord client not initialized. Call connect() first.")
        return self._client

    @property
    def guild(self) -> Guild | None:
        """Get the default guild."""
        return self._guild

    async def connect(self) -> None:
        """Connect to Discord Gateway."""
        if self._client:
            return  # Already connected

        intents = self.config.get_intents()
        self._client = discord.Client(intents=intents)

        @self._client.event
        async def on_ready():
            logger.info(f"Discord client connected as {self._client.user}")
            if self.config.guild_id:
                self._guild = self._client.get_guild(self.config.guild_id)
                if self._guild:
                    logger.info(f"Default guild: {self._guild.name}")
                else:
                    logger.warning(f"Guild {self.config.guild_id} not found")
            self._ready.set()

        # Start client in background
        asyncio.create_task(self._client.start(self.config.bot_token))

        # Wait for ready
        await asyncio.wait_for(self._ready.wait(), timeout=30.0)

    async def disconnect(self) -> None:
        """Disconnect from Discord Gateway."""
        if self._client:
            await self._client.close()
            self._client = None
            self._ready.clear()

    async def ensure_connected(self) -> None:
        """Ensure client is connected, connecting if needed."""
        if not self._client or not self._ready.is_set():
            await self.connect()

    # =========================================================================
    # Channel Operations
    # =========================================================================

    def get_channel(self, channel_id: int) -> TextChannel | None:
        """Get a channel by ID."""
        channel = self.client.get_channel(channel_id)
        if isinstance(channel, TextChannel):
            return channel
        return None

    def get_channel_by_name(self, name: str, guild: Guild | None = None) -> TextChannel | None:
        """Get a channel by name in the specified or default guild."""
        target_guild = guild or self._guild
        if not target_guild:
            return None
        for channel in target_guild.text_channels:
            if channel.name == name:
                return channel
        return None

    async def create_channel(
        self,
        name: str,
        guild: Guild | None = None,
        category: CategoryChannel | None = None,
        topic: str | None = None,
        slowmode_delay: int = 0,
    ) -> TextChannel:
        """Create a new text channel."""
        target_guild = guild or self._guild
        if not target_guild:
            raise ValueError("No guild specified and no default guild configured")

        return await target_guild.create_text_channel(
            name=name,
            category=category,
            topic=topic,
            slowmode_delay=slowmode_delay,
        )

    async def delete_channel(self, channel: TextChannel, reason: str | None = None) -> None:
        """Delete a channel."""
        await channel.delete(reason=reason)

    async def list_channels(self, guild: Guild | None = None) -> list[TextChannel]:
        """List all text channels in a guild."""
        target_guild = guild or self._guild
        if not target_guild:
            return []
        return target_guild.text_channels

    # =========================================================================
    # Message Operations
    # =========================================================================

    async def send_message(
        self,
        channel: TextChannel,
        content: str | None = None,
        embed: Embed | None = None,
        embeds: list[Embed] | None = None,
    ) -> Message:
        """Send a message to a channel."""
        return await channel.send(content=content, embed=embed, embeds=embeds)

    async def get_message(self, channel: TextChannel, message_id: int) -> Message | None:
        """Get a specific message by ID."""
        try:
            return await channel.fetch_message(message_id)
        except discord.NotFound:
            return None

    async def get_messages(
        self,
        channel: TextChannel,
        limit: int = 10,
        before: Message | None = None,
        after: Message | None = None,
    ) -> list[Message]:
        """Get recent messages from a channel."""
        messages = []
        async for msg in channel.history(limit=limit, before=before, after=after):
            messages.append(msg)
        return messages

    async def delete_message(self, message: Message, reason: str | None = None) -> None:
        """Delete a message."""
        await message.delete()

    async def edit_message(
        self,
        message: Message,
        content: str | None = None,
        embed: Embed | None = None,
    ) -> Message:
        """Edit a message."""
        return await message.edit(content=content, embed=embed)

    async def await_reply(
        self,
        channel: TextChannel,
        reference_message: Message | None = None,
        timeout: float = 300.0,
        check: Any | None = None,
    ) -> Message | None:
        """
        Wait for a reply in a channel.

        Args:
            channel: Channel to watch
            reference_message: If provided, only consider replies to this message
            timeout: How long to wait in seconds
            check: Optional custom check function

        Returns:
            The reply message, or None if timeout
        """

        def default_check(msg: Message) -> bool:
            if msg.channel.id != channel.id:
                return False
            if msg.author.bot:
                return False
            if reference_message and msg.reference:
                return msg.reference.message_id == reference_message.id
            return True

        try:
            return await self.client.wait_for(
                "message",
                check=check or default_check,
                timeout=timeout,
            )
        except TimeoutError:
            return None

    # =========================================================================
    # Reaction Operations
    # =========================================================================

    async def add_reaction(self, message: Message, emoji: str) -> None:
        """Add a reaction to a message."""
        await message.add_reaction(emoji)

    async def remove_reaction(self, message: Message, emoji: str) -> None:
        """Remove the bot's reaction from a message."""
        await message.remove_reaction(emoji, self.client.user)

    async def get_reactions(self, message: Message) -> dict[str, list[str]]:
        """
        Get all reactions on a message.

        Returns:
            Dict mapping emoji to list of user names
        """
        reactions: dict[str, list[str]] = {}
        for reaction in message.reactions:
            emoji_str = str(reaction.emoji)
            users = []
            async for user in reaction.users():
                if not user.bot:
                    users.append(user.display_name)
            reactions[emoji_str] = users
        return reactions

    async def await_reaction(
        self,
        message: Message,
        emojis: list[str] | None = None,
        timeout: float = 300.0,
    ) -> tuple[str, str] | None:
        """
        Wait for a reaction on a message.

        Args:
            message: Message to watch
            emojis: List of valid emojis (None = any)
            timeout: How long to wait

        Returns:
            Tuple of (emoji, user_name) or None if timeout
        """

        def check(reaction, user):
            if reaction.message.id != message.id:
                return False
            if user.bot:
                return False
            return not (emojis and str(reaction.emoji) not in emojis)

        try:
            reaction, user = await self.client.wait_for(
                "reaction_add",
                check=check,
                timeout=timeout,
            )
            return (str(reaction.emoji), user.display_name)
        except TimeoutError:
            return None

    # =========================================================================
    # Webhook Operations
    # =========================================================================

    async def create_webhook(
        self,
        channel: TextChannel,
        name: str,
        avatar: bytes | None = None,
        reason: str | None = None,
    ) -> Webhook:
        """Create a webhook for a channel."""
        return await channel.create_webhook(name=name, avatar=avatar, reason=reason)

    async def get_webhooks(self, channel: TextChannel) -> list[Webhook]:
        """Get all webhooks for a channel."""
        return await channel.webhooks()

    async def delete_webhook(self, webhook: Webhook, reason: str | None = None) -> None:
        """Delete a webhook."""
        await webhook.delete(reason=reason)

    async def send_webhook_message(
        self,
        webhook: Webhook,
        content: str | None = None,
        embed: Embed | None = None,
        username: str | None = None,
        avatar_url: str | None = None,
    ) -> Message:
        """Send a message via webhook."""
        return await webhook.send(
            content=content,
            embed=embed,
            username=username,
            avatar_url=avatar_url,
            wait=True,
        )


# Singleton client instance
_client: DiscordClient | None = None


def get_client() -> DiscordClient | None:
    """Get the singleton Discord client instance."""
    return _client


def set_client(client: DiscordClient) -> None:
    """Set the singleton Discord client instance."""
    global _client
    _client = client
