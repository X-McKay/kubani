"""
Event bus implementation using Redis Streams.
"""

import asyncio
import os
import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from core_agents.events.schemas import Event, EventType


class EventBus(ABC):
    """
    Abstract interface for the event bus.

    The event bus enables cross-agent communication through
    publish/subscribe patterns.
    """

    @abstractmethod
    async def publish(
        self,
        event_type: EventType,
        payload: dict[str, Any],
        source: str = "unknown",
        correlation_id: str | None = None,
    ) -> str:
        """
        Publish an event to the bus.

        Args:
            event_type: Type of event
            payload: Event-specific data
            source: Agent/component publishing the event
            correlation_id: Optional ID linking related events

        Returns:
            Event ID
        """
        ...

    @abstractmethod
    async def subscribe(
        self,
        *event_types: EventType,
        consumer_group: str | None = None,
        consumer_name: str | None = None,
    ) -> AsyncIterator[Event]:
        """
        Subscribe to events of specified types.

        Args:
            event_types: Event types to subscribe to (empty = all)
            consumer_group: Consumer group for load balancing
            consumer_name: Name of this consumer within the group

        Yields:
            Events as they arrive
        """
        ...

    @abstractmethod
    async def get_recent(
        self,
        event_type: EventType | None = None,
        count: int = 100,
        since_id: str | None = None,
    ) -> list[Event]:
        """
        Get recent events from the bus.

        Args:
            event_type: Filter by type (None = all)
            count: Maximum events to return
            since_id: Only return events after this ID

        Returns:
            List of recent events
        """
        ...


class RedisEventBus(EventBus):
    """
    Redis Streams-based event bus implementation.

    Uses Redis Streams for durable, ordered event storage with
    consumer group support for load balancing.
    """

    # Stream name for all events
    STREAM_KEY = "kubani:events"

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        password: str | None = None,
        db: int = 0,
        max_stream_length: int = 10000,
    ):
        self.host = host or os.getenv("REDIS_HOST", "localhost")
        self.port = port or int(os.getenv("REDIS_PORT", "6379"))
        self.password = password or os.getenv("REDIS_PASSWORD") or None
        self.db = db
        self.max_stream_length = max_stream_length

        self._client: Any = None
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        """Lazy initialization of Redis client."""
        if self._initialized:
            return

        try:
            import redis.asyncio as redis

            self._client = redis.Redis(
                host=self.host,
                port=self.port,
                password=self.password,
                db=self.db,
                decode_responses=False,  # We handle decoding ourselves
            )

            # Ping to verify connection
            await self._client.ping()
            self._initialized = True

        except ImportError as err:
            raise ImportError(
                "redis is required for RedisEventBus. Install with: pip install redis"
            ) from err

    async def publish(
        self,
        event_type: EventType,
        payload: dict[str, Any],
        source: str = "unknown",
        correlation_id: str | None = None,
    ) -> str:
        """Publish an event to the stream."""
        await self._ensure_initialized()

        event_id = str(uuid.uuid4())

        event = Event(
            id=event_id,
            type=event_type,
            source=source,
            payload=payload,
            correlation_id=correlation_id,
        )

        # Add to stream with automatic trimming
        await self._client.xadd(
            self.STREAM_KEY,
            event.to_stream_data(),
            maxlen=self.max_stream_length,
        )

        return event_id

    async def subscribe(
        self,
        *event_types: EventType,
        consumer_group: str | None = None,
        consumer_name: str | None = None,
    ) -> AsyncIterator[Event]:
        """Subscribe to events using Redis Streams."""
        await self._ensure_initialized()

        # Use consumer groups if specified, otherwise simple read
        if consumer_group:
            async for event in self._subscribe_with_group(
                event_types, consumer_group, consumer_name or str(uuid.uuid4())
            ):
                yield event
        else:
            async for event in self._subscribe_simple(event_types):
                yield event

    async def _subscribe_simple(self, event_types: tuple[EventType, ...]) -> AsyncIterator[Event]:
        """Simple subscription without consumer groups."""
        last_id = "$"  # Start from new messages

        type_values = {et.value for et in event_types} if event_types else None

        while True:
            try:
                # Block for up to 5 seconds waiting for new messages
                results = await self._client.xread(
                    {self.STREAM_KEY: last_id},
                    count=10,
                    block=5000,
                )

                if not results:
                    continue

                for _stream_name, messages in results:
                    for message_id, data in messages:
                        last_id = message_id.decode()
                        event = Event.from_stream_data(data)

                        # Filter by type if specified
                        if type_values is None or event.type.value in type_values:
                            yield event

            except asyncio.CancelledError:
                break

    async def _subscribe_with_group(
        self,
        event_types: tuple[EventType, ...],
        group: str,
        consumer: str,
    ) -> AsyncIterator[Event]:
        """Subscription with consumer groups for load balancing."""
        # Create consumer group if it doesn't exist
        import contextlib

        with contextlib.suppress(Exception):
            await self._client.xgroup_create(
                self.STREAM_KEY,
                group,
                id="0",
                mkstream=True,
            )

        type_values = {et.value for et in event_types} if event_types else None

        while True:
            try:
                # Read from consumer group
                results = await self._client.xreadgroup(
                    group,
                    consumer,
                    {self.STREAM_KEY: ">"},  # Only new messages
                    count=10,
                    block=5000,
                )

                if not results:
                    continue

                for _stream_name, messages in results:
                    for message_id, data in messages:
                        event = Event.from_stream_data(data)

                        # Filter by type if specified
                        if type_values is None or event.type.value in type_values:
                            yield event

                        # Acknowledge the message
                        await self._client.xack(self.STREAM_KEY, group, message_id)

            except asyncio.CancelledError:
                break

    async def get_recent(
        self,
        event_type: EventType | None = None,
        count: int = 100,
        since_id: str | None = None,
    ) -> list[Event]:
        """Get recent events from the stream."""
        await self._ensure_initialized()

        # Read from stream
        start = since_id.encode() if since_id else b"-"

        results = await self._client.xrange(
            self.STREAM_KEY,
            min=start,
            count=count * 2 if event_type else count,  # Over-fetch if filtering
        )

        events = []
        for _message_id, data in results:
            event = Event.from_stream_data(data)

            # Filter by type if specified
            if event_type is None or event.type == event_type:
                events.append(event)

            if len(events) >= count:
                break

        return events

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._client:
            await self._client.close()
            self._initialized = False


# Singleton instance
_event_bus: EventBus | None = None


async def get_event_bus() -> EventBus:
    """Get the singleton event bus instance."""
    global _event_bus

    if _event_bus is None:
        _event_bus = RedisEventBus()

    return _event_bus
