"""
Event bus for cross-agent communication.

Provides a Redis Streams-based event bus for publishing and subscribing
to events across agents and domains.

Example:
    from core_agents.events import EventBus, EventType, get_event_bus

    bus = await get_event_bus()

    # Publish an event
    await bus.publish(
        EventType.K8S_ISSUE_DETECTED,
        {"pod": "vllm-xxx", "issue": "CrashLoopBackOff"}
    )

    # Subscribe to events
    async for event in bus.subscribe(EventType.K8S_ISSUE_DETECTED):
        print(f"Got issue: {event.payload}")
"""

from core_agents.events.bus import (
    EventBus,
    RedisEventBus,
    get_event_bus,
)
from core_agents.events.schemas import (
    DeploymentEvent,
    Event,
    EventType,
    ImagePushedEvent,
)

__all__ = [
    # Schemas
    "Event",
    "EventType",
    "ImagePushedEvent",
    "DeploymentEvent",
    # Bus
    "EventBus",
    "RedisEventBus",
    "get_event_bus",
]
