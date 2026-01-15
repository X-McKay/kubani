"""
Correlator Service - Groups related Kubernetes events before investigation.

The Correlator subscribes to K8S_ISSUE_DETECTED events from the Sentinel,
buffers them for a configurable time window, and groups related events
into correlated issues for investigation.
"""

import asyncio
import hashlib
import logging
import os
from collections import defaultdict
from datetime import UTC, datetime

import redis.asyncio as aioredis

from cluster_monitor.models import CorrelatedIssue, K8sEvent, Severity
from core_agents.events import Event, EventBus, EventType

logger = logging.getLogger(__name__)

# Configuration
CORRELATION_WINDOW_SECONDS = int(os.getenv("CORRELATION_WINDOW_SECONDS", "30"))
CRITICAL_IMMEDIATE_REASONS = {"OOMKilled", "NodeNotReady", "EvictionThresholdMet"}

# Resources to ignore (prevent self-referential investigation loops)
IGNORED_RESOURCE_PATTERNS = {"cluster-monitor", "cluster-swarm"}


class EventCorrelator:
    """
    Correlates related Kubernetes events before triggering investigations.

    Groups events by:
    - Similar error patterns (e.g., connection timeouts)
    - Same namespace
    - Time proximity (within correlation window)
    """

    def __init__(
        self,
        event_bus: EventBus | None = None,
        redis_client: aioredis.Redis | None = None,
        window_seconds: int = CORRELATION_WINDOW_SECONDS,
    ):
        self._event_bus = event_bus
        self._redis = redis_client
        self.window_seconds = window_seconds
        self._buffer: dict[str, list[K8sEvent]] = defaultdict(list)
        self._timers: dict[str, asyncio.Task] = {}

    @property
    def event_bus(self) -> EventBus:
        """Get the event bus (must be initialized via run() first)."""
        if self._event_bus is None:
            raise RuntimeError("Event bus not initialized. Call run() first.")
        return self._event_bus

    async def _ensure_redis(self) -> aioredis.Redis:
        """Lazy initialization of Redis client."""
        if self._redis is None:
            self._redis = aioredis.Redis(
                host=os.getenv("REDIS_HOST", "localhost"),
                port=int(os.getenv("REDIS_PORT", "6379")),
                password=os.getenv("REDIS_PASSWORD") or None,
                decode_responses=True,
            )
        return self._redis

    def _extract_error_pattern(self, message: str) -> str:
        """
        Extract the core error pattern from a message.

        Examples:
        - "context deadline exceeded" -> "timeout"
        - "connection refused" -> "connection_error"
        - "OOMKilled" -> "oom"
        """
        message_lower = message.lower()

        # Timeout patterns
        if any(
            pattern in message_lower for pattern in ["timeout", "deadline exceeded", "timed out"]
        ):
            return "timeout"

        # Connection patterns
        if any(
            pattern in message_lower
            for pattern in ["connection refused", "connection reset", "no route to host"]
        ):
            return "connection_error"

        # Resource patterns
        if "oom" in message_lower or "out of memory" in message_lower:
            return "oom"

        if "disk" in message_lower or "storage" in message_lower:
            return "storage"

        # Image patterns
        if "image" in message_lower and ("pull" in message_lower or "not found" in message_lower):
            return "image_pull"

        # Default to the reason
        return "other"

    def _generate_correlation_key(self, event: K8sEvent) -> str:
        """
        Generate a correlation key for grouping related events.

        Events are grouped by:
        - Error pattern (timeout, connection_error, etc.)
        - Namespace (issues in the same namespace are often related)
        """
        pattern = self._extract_error_pattern(event.message)
        return f"{pattern}:{event.namespace}"

    def _should_process_immediately(self, event: K8sEvent) -> bool:
        """Check if an event should bypass correlation and be processed immediately."""
        return event.reason in CRITICAL_IMMEDIATE_REASONS or event.severity == Severity.CRITICAL

    async def _flush_correlation_group(self, correlation_key: str) -> None:
        """
        Flush a correlation group and publish an INVESTIGATION_REQUESTED event.
        """
        events = self._buffer.pop(correlation_key, [])
        if not events:
            return

        # Clean up timer
        if correlation_key in self._timers:
            self._timers[correlation_key].cancel()
            del self._timers[correlation_key]

        # Determine overall severity (highest among events)
        severity_order = [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]
        max_severity = max(events, key=lambda e: severity_order.index(e.severity)).severity

        # Extract pattern type from correlation key
        pattern_type = correlation_key.split(":")[0]

        # Generate correlation ID
        correlation_id = hashlib.sha256(
            f"{correlation_key}:{datetime.now(UTC).isoformat()}".encode()
        ).hexdigest()[:16]

        # Create correlated issue
        correlated_issue = CorrelatedIssue(
            correlation_id=correlation_id,
            events=events,
            pattern_type=pattern_type,
            affected_namespaces=list({e.namespace for e in events}),
            affected_resources=[f"{e.resource_kind}/{e.resource_name}" for e in events],
            severity=max_severity,
        )

        logger.info(
            f"Flushing correlation group {correlation_key}: "
            f"{len(events)} events, pattern={pattern_type}, severity={max_severity.value}"
        )

        # Publish K8S_INVESTIGATION_REQUESTED event
        await self.event_bus.publish(
            event_type=EventType.K8S_INVESTIGATION_REQUESTED,
            payload=correlated_issue.model_dump(),
            source="correlator",
            correlation_id=correlation_id,
        )

    def _should_ignore_event(self, event: K8sEvent) -> bool:
        """
        Check if an event should be ignored to prevent self-referential loops.

        Ignores events from cluster-monitor itself and related agents.
        """
        resource_name_lower = event.resource_name.lower()
        for pattern in IGNORED_RESOURCE_PATTERNS:
            if pattern in resource_name_lower:
                return True
        return False

    def _parse_event_payload(self, payload: dict) -> K8sEvent | None:
        """
        Parse event payload into K8sEvent.

        Handles two formats:
        1. Flat format (from cluster-monitor Sentinel): direct K8sEvent fields
        2. Nested format (from k8s-monitor Sentinel): {"event": {...}, "classification": {...}}
        """
        try:
            # Try flat format first (cluster-monitor Sentinel)
            if "event_id" in payload:
                return K8sEvent(**payload)

            # Try nested format (k8s-monitor Sentinel)
            if "event" in payload and "classification" in payload:
                event_data = payload["event"]
                classification = payload["classification"]

                # Generate event_id from the data
                event_id = hashlib.sha256(
                    f"{event_data.get('namespace', 'default')}/"
                    f"{event_data.get('kind', 'Unknown')}/"
                    f"{event_data.get('name', 'unknown')}/"
                    f"{event_data.get('reason', 'Unknown')}".encode()
                ).hexdigest()[:16]

                # Map severity from classification
                severity_map = {
                    "critical": Severity.CRITICAL,
                    "high": Severity.HIGH,
                    "medium": Severity.MEDIUM,
                    "low": Severity.LOW,
                }
                severity = severity_map.get(
                    classification.get("severity", "medium"), Severity.MEDIUM
                )

                return K8sEvent(
                    event_id=event_id,
                    event_type=event_data.get("type", "Warning"),
                    reason=event_data.get("reason", "Unknown"),
                    message=event_data.get("message", ""),
                    namespace=event_data.get("namespace", "default"),
                    resource_name=event_data.get("name", "unknown"),
                    resource_kind=event_data.get("kind", "Unknown"),
                    severity=severity,
                    timestamp=payload.get("detected_at", ""),
                )

            logger.warning(f"Unknown event payload format: {list(payload.keys())}")
            return None

        except Exception as e:
            logger.error(f"Failed to parse K8S event: {e}")
            return None

    async def process_event(self, event: Event) -> None:
        """
        Process a K8S_ISSUE_DETECTED event.

        Either buffers it for correlation or processes it immediately.
        """
        k8s_event = self._parse_event_payload(event.payload)
        if k8s_event is None:
            return

        # Ignore events from ourselves to prevent investigation loops
        if self._should_ignore_event(k8s_event):
            logger.debug(
                f"Ignoring self-referential event: {k8s_event.resource_kind}/{k8s_event.resource_name}"
            )
            return

        # Check if this should be processed immediately
        if self._should_process_immediately(k8s_event):
            logger.info(
                f"Processing critical event immediately: {k8s_event.reason} "
                f"({k8s_event.resource_kind}/{k8s_event.resource_name})"
            )
            # Create single-event correlation
            correlation_id = hashlib.sha256(f"immediate:{k8s_event.event_id}".encode()).hexdigest()[
                :16
            ]
            correlated_issue = CorrelatedIssue(
                correlation_id=correlation_id,
                events=[k8s_event],
                pattern_type=k8s_event.reason.lower(),
                affected_namespaces=[k8s_event.namespace],
                affected_resources=[f"{k8s_event.resource_kind}/{k8s_event.resource_name}"],
                severity=k8s_event.severity,
            )
            await self.event_bus.publish(
                event_type=EventType.K8S_INVESTIGATION_REQUESTED,
                payload=correlated_issue.model_dump(),
                source="correlator",
                correlation_id=correlation_id,
            )
            return

        # Buffer for correlation
        correlation_key = self._generate_correlation_key(k8s_event)
        self._buffer[correlation_key].append(k8s_event)

        logger.debug(
            f"Buffered event for correlation: {correlation_key} "
            f"(now {len(self._buffer[correlation_key])} events)"
        )

        # Set up timer to flush this group if not already set
        if correlation_key not in self._timers:

            async def flush_after_window():
                await asyncio.sleep(self.window_seconds)
                await self._flush_correlation_group(correlation_key)

            self._timers[correlation_key] = asyncio.create_task(flush_after_window())

    async def run(self) -> None:
        """
        Run the correlator service.

        Subscribes to K8S_ISSUE_DETECTED events and processes them.
        """
        # Initialize event bus if not provided
        if self._event_bus is None:
            from core_agents.events import get_event_bus

            self._event_bus = await get_event_bus()

        logger.info(
            f"Starting Correlator service (window={self.window_seconds}s, "
            f"critical_immediate={CRITICAL_IMMEDIATE_REASONS})"
        )

        async for event in self.event_bus.subscribe(
            EventType.K8S_ISSUE_DETECTED,
            consumer_group="correlator",
            consumer_name="correlator-1",
        ):
            try:
                await self.process_event(event)
            except Exception as e:
                logger.error(f"Error processing event: {e}", exc_info=True)


async def main():
    """Main entry point for the correlator service."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    correlator = EventCorrelator()
    await correlator.run()


if __name__ == "__main__":
    asyncio.run(main())
