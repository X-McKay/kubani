"""Nexus Redis Pub/Sub utility.

Provides a thin, testable wrapper around Redis pub/sub for routing
agent responses back to the correct client (Discord, Kubani UI).

The Gateway subscribes to conversation-specific channels. The Orchestrator
publishes agent responses to those channels. This decouples the agent
from the delivery mechanism.

Channel naming convention:
    nexus:response:{conversation_id}

Usage:
    from kubani.nexus.pubsub import NexusPubSub

    pubsub = NexusPubSub(redis_url="redis://localhost:6379")
    await pubsub.connect()

    # Publisher side (Orchestrator activity)
    await pubsub.publish_response(conversation_id, agent_message.to_dict())

    # Subscriber side (Gateway)
    async for message in pubsub.subscribe_responses(conversation_id):
        await websocket.send_json(message)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Protocol

logger = logging.getLogger(__name__)

RESPONSE_CHANNEL_PREFIX = "nexus:response:"
NOTIFICATION_CHANNEL = "nexus:notifications"


class RedisClient(Protocol):
    """Protocol for Redis client to enable testing with fakes."""

    async def publish(self, channel: str, message: str) -> int: ...
    def pubsub(self) -> Any: ...
    async def close(self) -> None: ...


class NexusPubSub:
    """Redis Pub/Sub wrapper for Nexus response routing.

    Attributes:
        redis_url: Redis connection URL.
        _redis: The underlying Redis client instance.
    """

    def __init__(self, redis_url: str = "redis://localhost:6379") -> None:
        self.redis_url = redis_url
        self._redis: Any = None

    async def connect(self) -> None:
        """Connect to Redis."""
        import redis.asyncio as aioredis

        self._redis = aioredis.from_url(self.redis_url, decode_responses=True)
        logger.info(f"Connected to Redis at {self.redis_url}")

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._redis:
            await self._redis.aclose()
            logger.info("Redis connection closed")

    @classmethod
    def from_client(cls, client: RedisClient) -> NexusPubSub:
        """Create a NexusPubSub with a pre-existing Redis client (for testing).

        Args:
            client: A Redis client instance or mock.

        Returns:
            NexusPubSub instance with the client already set.
        """
        instance = cls.__new__(cls)
        instance.redis_url = ""
        instance._redis = client
        return instance

    # =====================================================================
    # Publishing
    # =====================================================================

    async def publish_response(
        self, conversation_id: str, message: dict[str, Any]
    ) -> None:
        """Publish an agent response to the conversation channel.

        Args:
            conversation_id: The conversation to publish to.
            message: The AgentMessage dict to publish.
        """
        channel = f"{RESPONSE_CHANNEL_PREFIX}{conversation_id}"
        payload = json.dumps(message)
        await self._redis.publish(channel, payload)
        logger.debug(f"Published response to {channel}")

    async def publish_notification(self, notification: dict[str, Any]) -> None:
        """Publish a system notification (e.g., skill approved, error).

        Args:
            notification: Notification payload dict.
        """
        payload = json.dumps(notification)
        await self._redis.publish(NOTIFICATION_CHANNEL, payload)
        logger.debug("Published notification")

    # =====================================================================
    # Subscribing
    # =====================================================================

    async def subscribe_responses(
        self, conversation_id: str
    ) -> AsyncIterator[dict[str, Any]]:
        """Subscribe to agent responses for a specific conversation.

        This is an async generator that yields messages as they arrive.
        It is designed to be consumed by a WebSocket handler in the Gateway.

        Args:
            conversation_id: The conversation to subscribe to.

        Yields:
            AgentMessage dicts as they are published.
        """
        channel = f"{RESPONSE_CHANNEL_PREFIX}{conversation_id}"
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(channel)
        logger.info(f"Subscribed to {channel}")

        try:
            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )
                if message and message["type"] == "message":
                    data = json.loads(message["data"])
                    yield data
                else:
                    # Yield control to the event loop
                    await asyncio.sleep(0.01)
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
            logger.info(f"Unsubscribed from {channel}")

    async def subscribe_notifications(self) -> AsyncIterator[dict[str, Any]]:
        """Subscribe to system notifications.

        Yields:
            Notification dicts as they are published.
        """
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(NOTIFICATION_CHANNEL)
        logger.info(f"Subscribed to {NOTIFICATION_CHANNEL}")

        try:
            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )
                if message and message["type"] == "message":
                    data = json.loads(message["data"])
                    yield data
                else:
                    await asyncio.sleep(0.01)
        finally:
            await pubsub.unsubscribe(NOTIFICATION_CHANNEL)
            await pubsub.aclose()
