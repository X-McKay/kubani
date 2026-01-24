"""
Shared fixtures for testing event bus and event types.
"""

import uuid
from collections.abc import AsyncGenerator, Callable
from typing import Any

import pytest

from framework.events.bus import RedisEventBus
from framework.events.types import Event, EventType


@pytest.fixture
def event_factory() -> Callable[..., Event]:
    """
    Factory for creating test events with sensible defaults.

    Usage:
        def test_event(event_factory):
            event = event_factory(
                event_type=EventType.K8S_ISSUE_DETECTED,
                payload={"pod": "test-pod"}
            )
    """

    def _create(
        event_type: EventType = EventType.K8S_ISSUE_DETECTED,
        source: str = "test-agent",
        payload: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        **kwargs: Any,
    ) -> Event:
        return Event(
            id=str(uuid.uuid4()),
            type=event_type,
            source=source,
            payload=payload or {},
            correlation_id=correlation_id,
            **kwargs,
        )

    return _create


@pytest.fixture
async def fake_redis_event_bus() -> AsyncGenerator[RedisEventBus, None]:
    """
    Event bus using fakeredis for fast unit tests.

    Provides a fully functional RedisEventBus backed by fakeredis
    instead of a real Redis instance.

    Usage:
        @pytest.mark.asyncio
        async def test_publish(fake_redis_event_bus):
            event_id = await fake_redis_event_bus.publish(
                EventType.K8S_ISSUE_DETECTED,
                {"pod": "test-pod"},
                source="test-agent"
            )
    """
    import fakeredis.aioredis

    bus = RedisEventBus(host="fake", port=6379)
    # Replace real Redis client with fakeredis
    bus._client = fakeredis.aioredis.FakeRedis(decode_responses=False)
    bus._initialized = True

    yield bus

    # Cleanup
    await bus.close()


@pytest.fixture
def sample_event_data():
    """
    Returns sample event data for testing serialization.

    Usage:
        def test_serialization(sample_event_data):
            event = Event(**sample_event_data)
    """
    return {
        "id": "test-event-123",
        "type": EventType.K8S_ISSUE_DETECTED,
        "source": "test-agent",
        "payload": {
            "pod": "test-pod",
            "namespace": "test-ns",
            "issue": "CrashLoopBackOff",
        },
        "correlation_id": "corr-123",
    }
