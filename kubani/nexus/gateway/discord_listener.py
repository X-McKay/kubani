"""Discord Message Listener for Nexus.

A simple Discord bot that listens for messages mentioning the bot
and forwards them to the Nexus Gateway REST API, then listens for
responses and sends them back to Discord.

This runs as a standalone service alongside the Gateway.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

import discord
import httpx
import redis.asyncio as aioredis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Must match RESPONSE_CHANNEL_PREFIX in kubani/nexus/pubsub.py
RESPONSE_CHANNEL_PREFIX = "nexus:response:"


class NexusDiscordListener(discord.Client):
    """Discord bot that forwards messages to Nexus Gateway and handles responses."""

    def __init__(self, gateway_url: str, redis_url: str, bot_user_id: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.gateway_url = gateway_url
        self.redis_url = redis_url
        self.bot_user_id = bot_user_id
        self.http_client = httpx.AsyncClient(timeout=30.0)
        self.redis_client = None

    async def setup_redis(self):
        """Set up Redis connection for pub/sub."""
        self.redis_client = aioredis.from_url(self.redis_url, decode_responses=True)
        logger.info(f"Connected to Redis at {self.redis_url}")

    async def on_ready(self):
        """Called when the bot is ready."""
        logger.info(f"Discord listener ready as {self.user} (ID: {self.user.id})")
        logger.info(f"Forwarding messages to: {self.gateway_url}")
        await self.setup_redis()

    async def on_message(self, message: discord.Message):
        """Handle incoming Discord messages."""
        logger.info(
            f"Received message: author={message.author.id}, bot={message.author.bot}, "
            f"content={message.content[:100]}, mentions={[m.id for m in message.mentions]}"
        )

        # Ignore messages from the bot itself
        if message.author.id == self.user.id:
            logger.info("Ignoring message from self")
            return

        # Only process messages that mention the bot or are DMs
        if not (self.user.mentioned_in(message) or isinstance(message.channel, discord.DMChannel)):
            return

        logger.info(f"Processing message from {message.author}: {message.content[:50]}...")

        # Remove the bot mention from the message
        content = message.content
        for mention in message.mentions:
            if mention.id == self.user.id:
                content = content.replace(f"<@{mention.id}>", "").strip()
                content = content.replace(f"<@!{mention.id}>", "").strip()

        if not content:
            return

        conversation_id = f"discord-{message.channel.id}"

        # Forward to Nexus Gateway
        try:
            response = await self.http_client.post(
                f"{self.gateway_url}/api/nexus/chat",
                json={
                    "text": content,
                    "user_id": f"discord-{message.author.id}",
                    "conversation_id": conversation_id,
                    "source": "discord",
                },
            )

            if response.status_code == 200:
                logger.info(f"Forwarded message to Nexus: {response.json()}")
                await message.add_reaction("\u2705")

                # Start listening for the response
                asyncio.create_task(
                    self._listen_for_response(conversation_id, message.channel)
                )
            else:
                logger.error(
                    f"Failed to forward message: {response.status_code} {response.text}"
                )
                await message.add_reaction("\u274c")

        except Exception as e:
            logger.error(f"Error forwarding message to Nexus: {e}")
            await message.add_reaction("\u274c")

    async def _listen_for_response(
        self, conversation_id: str, channel: discord.TextChannel
    ):
        """Listen for Nexus response via Redis pub/sub and send to Discord."""
        if not self.redis_client:
            logger.error("Redis client not initialized")
            return

        try:
            pubsub = self.redis_client.pubsub()
            channel_name = f"{RESPONSE_CHANNEL_PREFIX}{conversation_id}"
            await pubsub.subscribe(channel_name)

            logger.info(f"Listening for responses on {channel_name}")

            timeout = 120  # 2 minutes
            start_time = asyncio.get_event_loop().time()

            async for message in pubsub.listen():
                if asyncio.get_event_loop().time() - start_time > timeout:
                    logger.warning(f"Timeout waiting for response on {channel_name}")
                    break

                if message["type"] == "message":
                    response_data = json.loads(message["data"])
                    response_text = response_data.get("text", "")

                    if response_text:
                        logger.info(
                            f"Received response from Nexus: {response_text[:50]}..."
                        )

                        # Send response to Discord (split if too long)
                        if len(response_text) > 2000:
                            chunks = [
                                response_text[i : i + 2000]
                                for i in range(0, len(response_text), 2000)
                            ]
                            for chunk in chunks:
                                await channel.send(chunk)
                        else:
                            await channel.send(response_text)

                        break

            await pubsub.unsubscribe(channel_name)
            await pubsub.aclose()

        except Exception as e:
            logger.error(f"Error listening for response: {e}")

    async def close(self):
        """Clean up resources."""
        if self.redis_client:
            await self.redis_client.aclose()
        await self.http_client.aclose()
        await super().close()


async def main():
    """Run the Discord listener."""
    bot_token = os.environ.get("DISCORD_BOT_TOKEN")
    if not bot_token:
        raise ValueError("DISCORD_BOT_TOKEN environment variable is required")

    gateway_url = os.environ.get(
        "NEXUS_GATEWAY_URL", "http://nexus-gateway.nexus.svc.cluster.local:8000"
    )
    redis_url = os.environ.get("REDIS_URL", "redis://redis.database.svc.cluster.local:6379")
    bot_user_id = os.environ.get("DISCORD_BOT_USER_ID", "")

    intents = discord.Intents.default()
    intents.message_content = True
    intents.messages = True
    intents.guilds = True

    client = NexusDiscordListener(
        gateway_url=gateway_url,
        redis_url=redis_url,
        bot_user_id=bot_user_id,
        intents=intents,
    )

    try:
        await client.start(bot_token)
    except KeyboardInterrupt:
        logger.info("Shutting down Discord listener...")
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
