"""
Sentinel Agent - Real-time Kubernetes event watcher.

The Sentinel watches Kubernetes events via watch streams or MCP polling,
classifies them based on known patterns, and publishes actionable issues
to the event bus for the Healer to process.

This is a continuously running agent that:
1. Watches K8s events via watch streams (or polls via MCP as fallback)
2. Classifies events against known issue patterns
3. Emits structured events to Redis Streams
4. Uses Redis for persistent deduplication (survives pod restarts)
"""

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import redis.asyncio as aioredis
from pydantic import BaseModel, Field

from core_agents.events import EventBus, EventType, get_event_bus
from core_agents.observability import record_event_published

logger = logging.getLogger(__name__)


class WatchMode(str, Enum):
    """Mode for watching Kubernetes events."""

    WATCH = "watch"  # Real-time watch streams (preferred)
    POLL = "poll"  # Polling via MCP (fallback)
    AUTO = "auto"  # Try watch, fall back to poll


class EventClassification(BaseModel):
    """Classification of a Kubernetes event."""

    severity: str = Field(description="low, medium, high, critical")
    is_actionable: bool = Field(description="Whether this needs remediation")
    category: str = Field(description="warning, error, normal, or issue type")
    reason: str = Field(description="Why this classification was made")


@dataclass
class K8sEvent:
    """Kubernetes event from the cluster."""

    type: str  # Normal, Warning
    reason: str  # e.g., "CrashLoopBackOff", "BackOff", "ImagePullBackOff"
    message: str
    namespace: str
    name: str  # Resource name
    kind: str  # Pod, Deployment, etc.
    first_timestamp: str | None = None
    last_timestamp: str | None = None
    count: int = 1

    @classmethod
    def from_mcp_event(cls, event_data: dict[str, Any]) -> "K8sEvent":
        """Create from MCP kubernetes events_list response."""
        involved_object = event_data.get("involvedObject", {})

        return cls(
            type=event_data.get("type", "Normal"),
            reason=event_data.get("reason", "Unknown"),
            message=event_data.get("message", ""),
            namespace=involved_object.get("namespace", "default"),
            name=involved_object.get("name", "unknown"),
            kind=involved_object.get("kind", "Unknown"),
            first_timestamp=event_data.get("firstTimestamp"),
            last_timestamp=event_data.get("lastTimestamp"),
            count=event_data.get("count", 1),
        )


# Issue patterns that match known problems (used for severity classification)
ISSUE_PATTERNS = {
    "CrashLoopBackOff": {"severity": "high", "category": "pod_health"},
    "ImagePullBackOff": {"severity": "high", "category": "pod_health"},
    "ErrImagePull": {"severity": "high", "category": "pod_health"},
    "OOMKilled": {"severity": "critical", "category": "resource"},
    "FailedScheduling": {"severity": "high", "category": "scheduling"},
    "Unhealthy": {"severity": "medium", "category": "pod_health"},
    "FailedMount": {"severity": "high", "category": "storage"},
    "NodeNotReady": {"severity": "critical", "category": "node_health"},
    "BackOff": {"severity": "medium", "category": "pod_health"},
}

# Default cooldown in seconds (60 minutes) - can be overridden via SENTINEL_COOLDOWN_SECONDS
DEFAULT_COOLDOWN_SECONDS = 3600


class SentinelAgent:
    """
    Watches Kubernetes events and publishes actionable issues.

    The Sentinel classifies events using known issue patterns and
    publishes them to the event bus for the Healer to process.

    Uses Redis for persistent deduplication that survives pod restarts.
    Redis is required - the agent will fail to start if Redis is unavailable.
    """

    DEDUP_KEY_PREFIX = "sentinel:seen:"

    def __init__(
        self,
        event_bus: EventBus | None = None,
        poll_interval: float = 30.0,
        source_name: str = "k8s-sentinel",
        watch_mode: WatchMode = WatchMode.AUTO,
    ):
        self._event_bus = event_bus
        self.poll_interval = poll_interval
        self.source_name = source_name
        self.watch_mode = watch_mode
        self._running = False
        self._redis: aioredis.Redis | None = None
        self._cooldown_seconds = int(
            os.getenv("SENTINEL_COOLDOWN_SECONDS", str(DEFAULT_COOLDOWN_SECONDS))
        )
        self._watch_stream = None

    async def _ensure_initialized(self) -> None:
        """Initialize required dependencies. Raises if Redis unavailable."""
        if self._event_bus is None:
            self._event_bus = await get_event_bus()

        if self._redis is None:
            redis_url = os.getenv("REDIS_URL", "redis://redis.almckay.io:6379")
            self._redis = aioredis.from_url(redis_url, decode_responses=True)
            await self._redis.ping()
            logger.info(
                f"Connected to Redis for deduplication (cooldown={self._cooldown_seconds}s)"
            )

    async def _is_recently_seen(self, event_key: str) -> bool:
        """Check if event was recently seen using Redis.

        Uses Redis SET with NX (only if not exists) and EX (expiry).
        Returns True if event was seen recently (should be skipped).
        Returns False if this is a new event (should be processed).
        """
        was_set = await self._redis.set(
            f"{self.DEDUP_KEY_PREFIX}{event_key}",
            datetime.now(UTC).isoformat(),
            nx=True,
            ex=self._cooldown_seconds,
        )
        # was_set is True if key was set (new event), None if already exists
        return was_set is None

    async def start(self) -> None:
        """Start the continuous event watching loop."""
        await self._ensure_initialized()
        self._running = True

        mode = self.watch_mode
        if mode == WatchMode.AUTO:
            mode = WatchMode.WATCH

        logger.info(f"Sentinel starting in {mode.value} mode")

        if mode == WatchMode.WATCH:
            try:
                await self._run_watch_mode()
            except Exception as e:
                if self.watch_mode == WatchMode.AUTO:
                    logger.warning(f"Watch mode failed ({e}), falling back to poll mode")
                    await self._run_poll_mode()
                else:
                    raise
        else:
            await self._run_poll_mode()

    async def _run_watch_mode(self) -> None:
        """Run using Kubernetes watch streams for real-time events."""
        from k8s_monitor.watch import K8sWatchStream

        self._watch_stream = K8sWatchStream(initial_backoff=1.0, max_backoff=60.0)
        logger.info("Starting real-time Kubernetes event watch")

        async for watch_event in self._watch_stream.watch():
            if not self._running:
                break

            try:
                event = K8sEvent.from_mcp_event(watch_event.k8s_event)
                await self._process_event(event)
            except Exception as e:
                logger.error(f"Error processing watch event: {e}")

    async def _run_poll_mode(self) -> None:
        """Run using MCP polling (fallback mode)."""
        logger.info(f"Starting poll mode with {self.poll_interval}s interval")

        while self._running:
            try:
                events = await self._get_events_via_mcp()
                for event in events:
                    await self._process_event(event)
            except Exception as e:
                logger.error(f"Error polling events: {e}")

            await asyncio.sleep(self.poll_interval)

    async def _get_events_via_mcp(self) -> list[K8sEvent]:
        """Get Kubernetes events via MCP."""
        try:
            from k8s_monitor.mcp_tools import call_mcp_tool_async

            result = await call_mcp_tool_async("events_list", {})
            if not result.get("success"):
                logger.warning(f"MCP events_list failed: {result.get('error')}")
                return []

            raw = result.get("result", "")
            if isinstance(raw, str):
                import json

                try:
                    events_data = json.loads(raw)
                except json.JSONDecodeError:
                    return []
            else:
                events_data = raw

            if isinstance(events_data, list):
                return [K8sEvent.from_mcp_event(e) for e in events_data]
            return []

        except Exception as e:
            logger.error(f"Failed to get events via MCP: {e}")
            return []

    async def _process_event(self, event: K8sEvent) -> None:
        """Process a single Kubernetes event."""
        # Skip normal events - only process Warning events
        if event.type == "Normal":
            return

        # Deduplicate using Redis with configurable cooldown
        event_key = f"{event.namespace}/{event.kind}/{event.name}/{event.reason}"
        if await self._is_recently_seen(event_key):
            return

        # Classify and publish
        classification = self._classify_event(event)

        if classification.is_actionable:
            await self._publish_issue(event, classification)

    def _classify_event(self, event: K8sEvent) -> EventClassification:
        """Classify a Kubernetes event based on known patterns."""
        pattern = ISSUE_PATTERNS.get(event.reason)

        if pattern:
            severity = pattern["severity"]
            return EventClassification(
                severity=severity,
                is_actionable=severity in ("high", "critical", "medium"),
                category=pattern["category"],
                reason=f"Matched known pattern: {event.reason}",
            )

        # Unknown pattern - Warning events are actionable (let Healer investigate)
        if event.type == "Warning":
            return EventClassification(
                severity="medium",
                is_actionable=True,
                category="warning",
                reason=f"Warning event: {event.reason}",
            )

        # Normal event, not actionable
        return EventClassification(
            severity="low",
            is_actionable=False,
            category="normal",
            reason="Normal event, no action needed",
        )

    async def _publish_issue(self, event: K8sEvent, classification: EventClassification) -> None:
        """Publish a detected issue to the event bus."""
        payload = {
            "event": {
                "type": event.type,
                "reason": event.reason,
                "message": event.message,
                "namespace": event.namespace,
                "name": event.name,
                "kind": event.kind,
            },
            "classification": {
                "severity": classification.severity,
                "category": classification.category,
                "reason": classification.reason,
            },
            "detected_at": datetime.now(UTC).isoformat(),
        }

        await self._event_bus.publish(
            event_type=EventType.K8S_ISSUE_DETECTED,
            payload=payload,
            source=self.source_name,
        )

        record_event_published(
            event_type=EventType.K8S_ISSUE_DETECTED.value,
            source=self.source_name,
        )

        logger.info(
            f"Published issue: {event.reason} on {event.kind}/{event.name} "
            f"(severity={classification.severity})"
        )

    def stop(self) -> None:
        """Stop the event watching loop."""
        self._running = False
        if self._watch_stream:
            self._watch_stream.stop()
        logger.info("Sentinel stopping")


async def run_sentinel(
    poll_interval: float = 30.0,
    stop_after: float | None = None,
    watch_mode: WatchMode = WatchMode.AUTO,
) -> None:
    """Run the Sentinel agent."""
    sentinel = SentinelAgent(poll_interval=poll_interval, watch_mode=watch_mode)

    if stop_after:

        async def stop_timer():
            await asyncio.sleep(stop_after)
            sentinel.stop()

        asyncio.create_task(stop_timer())

    await sentinel.start()
