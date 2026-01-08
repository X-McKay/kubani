"""
Sentinel Agent - Real-time Kubernetes event watcher.

The Sentinel watches Kubernetes events and logs in real-time,
classifies them using the skill library, and emits structured
events to the event bus for downstream processing.

This is a continuously running agent that:
1. Watches K8s events via watch streams (or polls as fallback)
2. Classifies events against skill preconditions
3. Emits structured events to Redis Streams
4. Maintains minimal state (stateless where possible)
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from core_agents.events import EventBus, EventType, get_event_bus
from core_agents.observability import record_event_published
from core_agents.skills import SkillDomain, SkillLibrary, get_skill_library

logger = logging.getLogger(__name__)


class WatchMode(str, Enum):
    """Mode for watching Kubernetes events."""

    WATCH = "watch"  # Real-time watch streams (preferred)
    POLL = "poll"  # Polling fallback
    AUTO = "auto"  # Try watch, fall back to poll


class EventClassification(BaseModel):
    """Classification of a Kubernetes event."""

    severity: str = Field(description="low, medium, high, critical")
    is_actionable: bool = Field(description="Whether this needs remediation")
    matching_skill_ids: list[str] = Field(default_factory=list)
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
        # Handle different response formats from kubernetes-mcp-server
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


# Issue patterns that match known problems
ISSUE_PATTERNS = {
    "CrashLoopBackOff": {
        "severity": "high",
        "category": "pod_health",
        "skill_query": "pod crashing crashloopbackoff restart",
    },
    "ImagePullBackOff": {
        "severity": "high",
        "category": "pod_health",
        "skill_query": "pod image pull backoff registry",
    },
    "ErrImagePull": {
        "severity": "high",
        "category": "pod_health",
        "skill_query": "pod image pull error",
    },
    "OOMKilled": {
        "severity": "critical",
        "category": "resource",
        "skill_query": "pod memory oom killed",
    },
    "FailedScheduling": {
        "severity": "high",
        "category": "scheduling",
        "skill_query": "pod scheduling failed resources",
    },
    "Unhealthy": {
        "severity": "medium",
        "category": "pod_health",
        "skill_query": "pod unhealthy health check probe",
    },
    "FailedMount": {
        "severity": "high",
        "category": "storage",
        "skill_query": "pod volume mount failed",
    },
    "NodeNotReady": {
        "severity": "critical",
        "category": "node_health",
        "skill_query": "node not ready unavailable",
    },
    "BackOff": {
        "severity": "medium",
        "category": "pod_health",
        "skill_query": "pod backoff restart",
    },
}


class SentinelAgent:
    """
    Watches Kubernetes events and classifies them using skills.

    The Sentinel is designed to run continuously, watching for
    new events (via watch streams or polling) and publishing
    classifications to the event bus.
    """

    def __init__(
        self,
        skill_library: SkillLibrary | None = None,
        event_bus: EventBus | None = None,
        poll_interval: float = 30.0,
        source_name: str = "k8s-sentinel",
        watch_mode: WatchMode = WatchMode.AUTO,
    ):
        """
        Initialize the Sentinel agent.

        Args:
            skill_library: Skill library for classification (default: singleton)
            event_bus: Event bus for publishing (default: singleton)
            poll_interval: Seconds between event polls (only used in poll mode)
            source_name: Source identifier for events
            watch_mode: Mode for watching events (watch, poll, or auto)
        """
        self._skill_library = skill_library
        self._event_bus = event_bus
        self.poll_interval = poll_interval
        self.source_name = source_name
        self.watch_mode = watch_mode
        self._running = False
        self._last_seen_events: set[str] = set()
        self._watch_stream = None

    async def _ensure_initialized(self) -> None:
        """Lazy initialization of dependencies."""
        if self._skill_library is None:
            self._skill_library = await get_skill_library()
        if self._event_bus is None:
            self._event_bus = await get_event_bus()

    async def start(self) -> None:
        """Start the continuous event watching loop."""
        await self._ensure_initialized()
        self._running = True

        # Determine which mode to use
        mode = self.watch_mode
        if mode == WatchMode.AUTO:
            mode = WatchMode.WATCH  # Try watch first

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

        self._watch_stream = K8sWatchStream(
            initial_backoff=1.0,
            max_backoff=60.0,
        )

        logger.info("Starting real-time Kubernetes event watch")

        async for watch_event in self._watch_stream.watch():
            if not self._running:
                break

            try:
                await self._process_watch_event(watch_event)
            except Exception as e:
                logger.error(f"Error processing watch event: {e}")

    async def _process_watch_event(self, watch_event: Any) -> None:
        """Process a single watch event."""
        k8s_event_data = watch_event.k8s_event

        # Convert to K8sEvent
        event = K8sEvent.from_mcp_event(k8s_event_data)

        # Skip normal events
        if event.type == "Normal":
            return

        # Deduplicate
        event_key = f"{event.namespace}/{event.name}/{event.reason}/{event.count}"
        if event_key in self._last_seen_events:
            return

        # Classify and potentially publish
        classification = await self.classify_event(event)

        if classification.is_actionable:
            await self._publish_issue(event, classification)

        # Track seen events (with size limit)
        self._last_seen_events.add(event_key)
        if len(self._last_seen_events) > 1000:
            # Remove oldest entries
            to_remove = list(self._last_seen_events)[:500]
            for key in to_remove:
                self._last_seen_events.discard(key)

    async def _run_poll_mode(self) -> None:
        """Run using traditional polling (fallback mode)."""
        logger.info(f"Starting poll mode with {self.poll_interval}s interval")

        while self._running:
            try:
                await self._poll_events()
            except Exception as e:
                logger.error(f"Error polling events: {e}")

            await asyncio.sleep(self.poll_interval)

    def stop(self) -> None:
        """Stop the event watching loop."""
        self._running = False
        if self._watch_stream:
            self._watch_stream.stop()
        logger.info("Sentinel stopping")

    async def _poll_events(self) -> None:
        """Poll for new Kubernetes events and process them."""
        try:
            # Get events via MCP tool call
            events = await self._get_k8s_events()

            for event in events:
                # Skip normal events and already-processed events
                if event.type == "Normal":
                    continue

                event_key = f"{event.namespace}/{event.name}/{event.reason}/{event.count}"
                if event_key in self._last_seen_events:
                    continue

                # Classify and potentially publish
                classification = await self.classify_event(event)

                if classification.is_actionable:
                    await self._publish_issue(event, classification)

                # Track seen events (with size limit)
                self._last_seen_events.add(event_key)
                if len(self._last_seen_events) > 1000:
                    # Remove oldest entries
                    to_remove = list(self._last_seen_events)[:500]
                    for key in to_remove:
                        self._last_seen_events.discard(key)

        except Exception as e:
            logger.error(f"Failed to poll K8s events: {e}")

    async def _get_k8s_events(self) -> list[K8sEvent]:
        """
        Get Kubernetes events via MCP.

        This uses the kubernetes-mcp-server events_list tool.
        In the actual implementation, this would be called via
        the agent's MCP client.
        """
        # For now, use direct kubectl as fallback
        # This will be replaced with MCP client when integrated
        try:
            from k8s_monitor.tools import get_cluster_events

            raw_events = get_cluster_events()
            return self._parse_events_output(raw_events)
        except ImportError:
            logger.warning("k8s_monitor.tools not available")
            return []

    def _parse_events_output(self, output: str) -> list[K8sEvent]:
        """Parse kubectl events output into K8sEvent objects."""
        events = []

        for line in output.strip().split("\n"):
            if not line or line.startswith("NAMESPACE"):
                continue

            parts = line.split(None, 7)  # Split into at most 8 parts
            if len(parts) >= 7:
                namespace = parts[0]
                _last_seen = parts[1]
                event_type = parts[2]
                reason = parts[3]
                kind_name = parts[4]
                message = parts[7] if len(parts) > 7 else ""

                # Parse kind/name
                if "/" in kind_name:
                    kind, name = kind_name.split("/", 1)
                else:
                    kind, name = "Unknown", kind_name

                events.append(
                    K8sEvent(
                        type=event_type,
                        reason=reason,
                        message=message,
                        namespace=namespace,
                        name=name,
                        kind=kind,
                    )
                )

        return events

    async def classify_event(self, event: K8sEvent) -> EventClassification:
        """
        Classify a Kubernetes event using skill preconditions.

        Args:
            event: The K8s event to classify

        Returns:
            Classification with severity, actionability, and matching skills
        """
        # Check against known issue patterns
        pattern = ISSUE_PATTERNS.get(event.reason)

        if pattern:
            # Search for matching skills
            skill_query = pattern["skill_query"]
            matching_skills = await self._skill_library.search(
                query=skill_query,
                domain=SkillDomain.K8S,
                limit=3,
                min_confidence=0.3,
            )

            skill_ids = [result.skill.id for result in matching_skills]

            return EventClassification(
                severity=pattern["severity"],
                is_actionable=len(skill_ids) > 0,
                matching_skill_ids=skill_ids,
                category=pattern["category"],
                reason=f"Matched known pattern: {event.reason}",
            )

        # Unknown pattern - check if Warning type
        if event.type == "Warning":
            # Try semantic search against all skills
            search_query = f"{event.reason}: {event.message}"
            matching_skills = await self._skill_library.search(
                query=search_query,
                domain=SkillDomain.K8S,
                limit=2,
                min_confidence=0.5,
            )

            skill_ids = [result.skill.id for result in matching_skills]

            return EventClassification(
                severity="medium",
                is_actionable=len(skill_ids) > 0,
                matching_skill_ids=skill_ids,
                category="warning",
                reason=f"Warning event: {event.reason}",
            )

        # Normal event, not actionable
        return EventClassification(
            severity="low",
            is_actionable=False,
            matching_skill_ids=[],
            category="normal",
            reason="Normal event, no action needed",
        )

    async def _publish_issue(
        self,
        event: K8sEvent,
        classification: EventClassification,
    ) -> None:
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
            "matching_skills": classification.matching_skill_ids,
            "detected_at": datetime.now(UTC).isoformat(),
        }

        await self._event_bus.publish(
            event_type=EventType.K8S_ISSUE_DETECTED,
            payload=payload,
            source=self.source_name,
        )

        # Record metric
        record_event_published(
            event_type=EventType.K8S_ISSUE_DETECTED.value,
            source=self.source_name,
        )

        logger.info(
            f"Published issue: {event.reason} on {event.kind}/{event.name} "
            f"(severity={classification.severity}, skills={len(classification.matching_skill_ids)})"
        )


async def run_sentinel(
    poll_interval: float = 30.0,
    stop_after: float | None = None,
    watch_mode: WatchMode = WatchMode.AUTO,
) -> None:
    """
    Run the Sentinel agent.

    Args:
        poll_interval: Seconds between event polls (only used in poll mode)
        stop_after: Optional number of seconds to run before stopping
        watch_mode: Mode for watching events (watch, poll, or auto)
    """
    sentinel = SentinelAgent(
        poll_interval=poll_interval,
        watch_mode=watch_mode,
    )

    if stop_after:
        # Run for a limited time
        async def stop_timer():
            await asyncio.sleep(stop_after)
            sentinel.stop()

        asyncio.create_task(stop_timer())

    await sentinel.start()
