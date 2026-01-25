"""
Event bus for cross-agent communication.

Provides a Redis Streams-based event bus for publishing and subscribing
to events across agents and domains.

Example:
    from framework.events import EventBus, EventType, get_event_bus

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

from .bus import (
    EventBus,
    RedisEventBus,
    get_event_bus,
)
from .types import (
    ApprovalRequest,
    ApprovalResponse,
    DeploymentEvent,
    Event,
    EventType,
    ImagePushedEvent,
    MCPServerRequest,
)

__all__ = [
    # Event types and schemas
    "Event",
    "EventType",
    "ApprovalRequest",
    "ApprovalResponse",
    "ImagePushedEvent",
    "DeploymentEvent",
    "MCPServerRequest",
    # Bus
    "EventBus",
    "RedisEventBus",
    "get_event_bus",
]
