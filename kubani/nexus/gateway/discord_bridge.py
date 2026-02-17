"""Nexus Discord Bridge.

Bridges Discord messages to the Nexus Temporal workflow and routes
agent responses back to Discord channels.

This module runs as a background task alongside the Gateway. It:
1. Listens for Discord messages via the Discord MCP server.
2. Normalizes them into UserMessage format.
3. Signals the Nexus workflow.
4. Subscribes to Redis pub/sub for responses.
5. Sends responses back to Discord via the Discord MCP server.

Usage:
    from kubani.nexus.gateway.discord_bridge import DiscordBridge

    bridge = DiscordBridge(temporal_client, pubsub)
    await bridge.start()
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class DiscordBridge:
    """Bridges Discord messages to/from the Nexus agent.

    Attributes:
        temporal_client: Temporal client for signaling workflows.
        pubsub: NexusPubSub instance for subscribing to responses.
        discord_mcp_url: URL of the Discord MCP server.
        monitored_channels: Set of Discord channel IDs to monitor.
    """

    def __init__(
        self,
        temporal_client: Any,
        pubsub: Any,
        discord_mcp_url: str | None = None,
        monitored_channels: list[str] | None = None,
    ) -> None:
        self.temporal_client = temporal_client
        self.pubsub = pubsub
        self.discord_mcp_url = discord_mcp_url or os.environ.get(
            "MCP_DISCORD_URL", "http://localhost:8084"
        )
        self.monitored_channels = set(monitored_channels or [])
        self._running = False
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        """Start the Discord bridge.

        Launches background tasks for:
        - Polling Discord for new messages
        - Subscribing to agent responses for Discord conversations
        """
        self._running = True
        logger.info("Starting Discord bridge")

        # Start the message polling task
        self._tasks.append(
            asyncio.create_task(self._poll_discord_messages())
        )

        logger.info("Discord bridge started")

    async def stop(self) -> None:
        """Stop the Discord bridge."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
        logger.info("Discord bridge stopped")

    async def _poll_discord_messages(self) -> None:
        """Poll the Discord MCP server for new messages.

        This is a simple polling approach. In production, the Discord
        MCP server would push events via WebSocket or webhook.
        """
        import httpx

        last_message_id: str | None = None

        while self._running:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self.discord_mcp_url}/tools/get_recent_messages",
                        json={
                            "channel_ids": list(self.monitored_channels),
                            "after": last_message_id,
                            "limit": 10,
                        },
                        timeout=10.0,
                    )

                    if response.status_code == 200:
                        messages = response.json().get("messages", [])
                        for msg in messages:
                            await self._handle_discord_message(msg)
                            last_message_id = msg.get("id", last_message_id)

            except Exception as e:
                logger.warning(f"Discord polling error: {e}")

            await asyncio.sleep(2.0)  # Poll every 2 seconds

    async def _handle_discord_message(self, msg: dict[str, Any]) -> None:
        """Handle a single Discord message.

        Normalizes the Discord message into a UserMessage and signals
        the Nexus workflow.

        Args:
            msg: Discord message dict from the MCP server.
        """
        # Skip bot messages
        if msg.get("author", {}).get("bot", False):
            return

        from kubani.nexus.models.messages import MessageSource, UserMessage

        user_id = msg.get("author", {}).get("id", "discord-user")
        channel_id = msg.get("channel_id", "")
        content = msg.get("content", "")

        if not content:
            return

        # Use channel_id as conversation_id for Discord
        conversation_id = f"discord-{channel_id}"

        user_message = UserMessage(
            source=MessageSource.DISCORD,
            user_id=f"discord-{user_id}",
            conversation_id=conversation_id,
            text=content,
            metadata={
                "discord_channel_id": channel_id,
                "discord_message_id": msg.get("id", ""),
                "discord_guild_id": msg.get("guild_id", ""),
            },
        )

        try:
            workflow_id = f"nexus-discord-{user_id}"
            handle = self.temporal_client.get_workflow_handle(workflow_id)
            await handle.signal("user_message", user_message.to_dict())
            logger.debug(f"Forwarded Discord message to workflow {workflow_id}")
        except Exception as e:
            logger.error(f"Failed to forward Discord message: {e}")

        # Start a response listener for this conversation
        asyncio.create_task(
            self._listen_for_response(conversation_id, channel_id)
        )

    async def _listen_for_response(
        self, conversation_id: str, channel_id: str
    ) -> None:
        """Listen for the agent's response and send it back to Discord.

        Args:
            conversation_id: The Nexus conversation ID.
            channel_id: The Discord channel to send the response to.
        """
        import httpx

        try:
            async for message in self.pubsub.subscribe_responses(conversation_id):
                text = message.get("text", "")
                if text:
                    async with httpx.AsyncClient() as client:
                        await client.post(
                            f"{self.discord_mcp_url}/tools/send_message",
                            json={
                                "channel_id": channel_id,
                                "content": text,
                            },
                            timeout=10.0,
                        )
                    # Only listen for one response per message
                    break
        except Exception as e:
            logger.error(f"Discord response listener error: {e}")
