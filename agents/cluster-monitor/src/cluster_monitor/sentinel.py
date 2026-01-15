"""
Sentinel Service - Watches Kubernetes events and publishes issues.

The Sentinel watches Kubernetes events via MCP polling,
classifies them based on known patterns, and publishes actionable
issues to the event bus for the Correlator to process.

Simplified version for cluster-monitor that:
1. Polls Kubernetes events via MCP
2. Classifies events using known patterns
3. Publishes K8S_ISSUE_DETECTED events to Redis
4. Uses Redis for persistent deduplication
"""

import asyncio
import hashlib
import logging
import os
import re
from datetime import UTC, datetime

import redis.asyncio as aioredis

from cluster_monitor.models import K8sEvent, Severity
from core_agents.events import EventBus, EventType, get_event_bus

# MCP server URL for Kubernetes operations
KUBERNETES_MCP_URL = os.getenv("KUBERNETES_MCP_SERVER_URL", "http://localhost:8080/mcp")

logger = logging.getLogger(__name__)

# Poll interval for checking Kubernetes events
POLL_INTERVAL_SECONDS = int(os.getenv("SENTINEL_POLL_INTERVAL", "30"))

# Cooldown for deduplication (1 hour by default)
COOLDOWN_SECONDS = int(os.getenv("SENTINEL_COOLDOWN_SECONDS", "3600"))

# Maximum age for events to be considered (5 minutes)
MAX_EVENT_AGE_SECONDS = int(os.getenv("SENTINEL_MAX_EVENT_AGE", "300"))

# Issue patterns for classification
ISSUE_PATTERNS = {
    "CrashLoopBackOff": {"severity": Severity.HIGH, "category": "pod_health"},
    "ImagePullBackOff": {"severity": Severity.HIGH, "category": "pod_health"},
    "ErrImagePull": {"severity": Severity.HIGH, "category": "pod_health"},
    "OOMKilled": {"severity": Severity.CRITICAL, "category": "resource"},
    "FailedScheduling": {"severity": Severity.HIGH, "category": "scheduling"},
    "Unhealthy": {"severity": Severity.MEDIUM, "category": "pod_health"},
    "FailedMount": {"severity": Severity.HIGH, "category": "storage"},
    "NodeNotReady": {"severity": Severity.CRITICAL, "category": "node_health"},
    "BackOff": {"severity": Severity.MEDIUM, "category": "pod_health"},
    "FailedCreate": {"severity": Severity.HIGH, "category": "resource"},
    "FailedKillPod": {"severity": Severity.MEDIUM, "category": "pod_health"},
    "NetworkNotReady": {"severity": Severity.HIGH, "category": "network"},
    "FreeDiskSpaceFailed": {"severity": Severity.HIGH, "category": "storage"},
    "EvictionThresholdMet": {"severity": Severity.CRITICAL, "category": "resource"},
    "NodeHasDiskPressure": {"severity": Severity.HIGH, "category": "node_health"},
    "NodeHasMemoryPressure": {"severity": Severity.HIGH, "category": "node_health"},
}

# Benign patterns to ignore
BENIGN_PATTERNS = {
    "DNSConfigForming",
    "Killing",
    "Preempting",
    "ProbeWarning",
    "ReconciliationSucceeded",
    "Progressing",
    "Pulled",
    "Created",
    "Started",
    "Scheduled",
    "SuccessfulCreate",
}

# Resource patterns to ignore (prevent self-monitoring loops)
IGNORED_RESOURCE_PATTERNS = [
    r"cluster-monitor",
    r"cluster-swarm",
    r"k8s-monitor",
]


class SentinelService:
    """
    Watches Kubernetes events and publishes issues to the event bus.

    Uses MCP polling to fetch events and Redis for deduplication.
    """

    DEDUP_KEY_PREFIX = "cluster-monitor:sentinel:"

    def __init__(
        self,
        event_bus: EventBus | None = None,
        redis_client: aioredis.Redis | None = None,
        poll_interval: float = POLL_INTERVAL_SECONDS,
    ):
        self._event_bus = event_bus
        self._redis = redis_client
        self.poll_interval = poll_interval
        self._running = False

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
            await self._redis.ping()
            logger.info(f"Connected to Redis for deduplication (cooldown={COOLDOWN_SECONDS}s)")
        return self._redis

    async def _is_recently_seen(self, event_key: str) -> bool:
        """Check if event was recently seen using Redis."""
        redis = await self._ensure_redis()
        full_key = f"{self.DEDUP_KEY_PREFIX}{event_key}"

        try:
            was_set = await redis.set(
                full_key,
                datetime.now(UTC).isoformat(),
                nx=True,
                ex=COOLDOWN_SECONDS,
            )
            # was_set is True if key was set (new event), None if already exists
            return was_set is None

        except Exception as e:
            logger.error(f"Redis dedup error for {event_key}: {e}. Treating as duplicate.")
            return True

    def _should_ignore_resource(self, resource_name: str) -> bool:
        """Check if resource should be ignored (self-monitoring prevention)."""
        for pattern in IGNORED_RESOURCE_PATTERNS:
            if re.search(pattern, resource_name, re.IGNORECASE):
                return True
        return False

    def _is_event_stale(self, timestamp: str | None) -> bool:
        """Check if event is too old to process."""
        if not timestamp:
            return False

        try:
            event_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            age = (datetime.now(UTC) - event_time).total_seconds()
            return age > MAX_EVENT_AGE_SECONDS
        except (ValueError, TypeError):
            return False

    def _classify_event(self, reason: str, event_type: str) -> tuple[Severity, bool]:
        """
        Classify an event by reason.

        Returns:
            Tuple of (severity, is_actionable)
        """
        pattern = ISSUE_PATTERNS.get(reason)

        if pattern:
            severity = pattern["severity"]
            is_actionable = severity in (Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL)
            return severity, is_actionable

        # Default for unknown Warning events
        if event_type == "Warning":
            return Severity.MEDIUM, True

        return Severity.LOW, False

    def _parse_k8s_event(self, raw_event: dict) -> K8sEvent | None:
        """Parse a raw Kubernetes event into our K8sEvent model."""
        try:
            involved_object = raw_event.get("involvedObject", {})
            event_type = raw_event.get("type", "Normal")
            reason = raw_event.get("reason", "Unknown")
            message = raw_event.get("message", "")
            namespace = involved_object.get("namespace", "default")
            resource_name = involved_object.get("name", "unknown")
            resource_kind = involved_object.get("kind", "Unknown")
            last_timestamp = raw_event.get("lastTimestamp")
            count = raw_event.get("count", 1)

            # Generate unique event ID
            event_id = hashlib.sha256(
                f"{namespace}/{resource_kind}/{resource_name}/{reason}/{last_timestamp}".encode()
            ).hexdigest()[:16]

            # Classify
            severity, _ = self._classify_event(reason, event_type)

            return K8sEvent(
                event_id=event_id,
                event_type=event_type,
                reason=reason,
                message=message,
                namespace=namespace,
                resource_name=resource_name,
                resource_kind=resource_kind,
                severity=severity,
                timestamp=last_timestamp or datetime.now(UTC).isoformat(),
                count=count,
            )

        except Exception as e:
            logger.error(f"Failed to parse K8s event: {e}")
            return None

    async def _fetch_events(self) -> list[dict]:
        """Fetch Kubernetes events via MCP using direct ClientSession."""
        try:
            # Import here to avoid circular imports and allow linter to pass
            import yaml
            from mcp import ClientSession
            from mcp.client.streamable_http import streamablehttp_client

            async with streamablehttp_client(KUBERNETES_MCP_URL) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    # Call events_list tool
                    result = await session.call_tool("events_list", {})

                    # Parse the YAML content from the response
                    events = []
                    for content in result.content:
                        if hasattr(content, "text"):
                            text = content.text
                            # The response is YAML prefixed with a comment
                            if text.startswith("# The following events"):
                                # Skip the comment line
                                yaml_text = "\n".join(text.split("\n")[1:])
                            else:
                                yaml_text = text

                            try:
                                parsed = yaml.safe_load(yaml_text)
                                if isinstance(parsed, list):
                                    # Convert from MCP format to K8s event format
                                    for item in parsed:
                                        event = self._convert_mcp_event(item)
                                        if event:
                                            events.append(event)
                            except yaml.YAMLError as e:
                                logger.warning(f"Failed to parse YAML events: {e}")

                    logger.debug(f"Fetched {len(events)} events from Kubernetes")
                    return events

        except Exception as e:
            logger.error(f"Failed to fetch events via MCP: {e}")
            return []

    def _convert_mcp_event(self, mcp_event: dict) -> dict | None:
        """Convert MCP event format to standard K8s event format."""
        try:
            involved_object = mcp_event.get("InvolvedObject", {})
            return {
                "type": mcp_event.get("Type", "Normal"),
                "reason": mcp_event.get("Reason", "Unknown"),
                "message": mcp_event.get("Message", ""),
                "involvedObject": {
                    "kind": involved_object.get("Kind", "Unknown"),
                    "name": involved_object.get("Name", "unknown"),
                    "namespace": mcp_event.get("Namespace", "default"),
                },
                "lastTimestamp": mcp_event.get("Timestamp"),
                "count": 1,
            }
        except Exception as e:
            logger.debug(f"Failed to convert MCP event: {e}")
            return None

    async def _process_event(self, raw_event: dict) -> None:
        """Process a single Kubernetes event."""
        event_type = raw_event.get("type", "Normal")
        reason = raw_event.get("reason", "Unknown")
        involved_object = raw_event.get("involvedObject", {})
        resource_name = involved_object.get("name", "unknown")
        last_timestamp = raw_event.get("lastTimestamp")

        # Skip Normal events
        if event_type == "Normal":
            return

        # Skip benign patterns
        if reason in BENIGN_PATTERNS:
            return

        # Skip ignored resources (self-monitoring prevention)
        if self._should_ignore_resource(resource_name):
            logger.debug(f"Ignoring event from {resource_name} (self-monitoring prevention)")
            return

        # Skip stale events
        if self._is_event_stale(last_timestamp):
            return

        # Classify
        severity, is_actionable = self._classify_event(reason, event_type)

        if not is_actionable:
            return

        # Deduplicate
        namespace = involved_object.get("namespace", "default")
        resource_kind = involved_object.get("kind", "Unknown")
        event_key = f"{namespace}/{resource_kind}/{resource_name}/{reason}"

        if await self._is_recently_seen(event_key):
            logger.debug(f"Skipping duplicate: {reason} on {resource_name}")
            return

        # Parse into K8sEvent
        k8s_event = self._parse_k8s_event(raw_event)
        if not k8s_event:
            return

        # Publish to event bus
        await self._publish_issue(k8s_event)

    async def _publish_issue(self, event: K8sEvent) -> None:
        """Publish a K8S_ISSUE_DETECTED event."""
        logger.info(
            f"Publishing issue: {event.reason} on {event.resource_kind}/{event.resource_name} "
            f"(severity={event.severity.value})"
        )

        await self.event_bus.publish(
            event_type=EventType.K8S_ISSUE_DETECTED,
            payload=event.model_dump(),
            source="cluster-monitor-sentinel",
        )

    async def _poll_loop(self) -> None:
        """Main polling loop."""
        while self._running:
            try:
                raw_events = await self._fetch_events()
                logger.debug(f"Fetched {len(raw_events)} events from Kubernetes")

                for raw_event in raw_events:
                    try:
                        await self._process_event(raw_event)
                    except Exception as e:
                        logger.error(f"Error processing event: {e}")

            except Exception as e:
                logger.error(f"Error in poll loop: {e}")

            await asyncio.sleep(self.poll_interval)

    async def run(self) -> None:
        """Run the Sentinel service."""
        # Initialize event bus if not provided
        if self._event_bus is None:
            self._event_bus = await get_event_bus()

        # Ensure Redis is connected
        await self._ensure_redis()

        logger.info(
            f"Starting Sentinel service (poll_interval={self.poll_interval}s, "
            f"cooldown={COOLDOWN_SECONDS}s, max_age={MAX_EVENT_AGE_SECONDS}s)"
        )

        self._running = True
        await self._poll_loop()

    def stop(self) -> None:
        """Stop the Sentinel service."""
        self._running = False
        logger.info("Sentinel service stopping")


async def main():
    """Main entry point for the sentinel service."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    sentinel = SentinelService()
    await sentinel.run()


if __name__ == "__main__":
    asyncio.run(main())
