"""
Sentinel Agent - Real-time Kubernetes event watcher.

The Sentinel watches Kubernetes events via watch streams or MCP polling,
classifies them based on known patterns, and publishes actionable issues
to the event bus for the Healer to process.

This is a continuously running agent that:
1. Watches K8s events via watch streams (or polls via MCP as fallback)
2. Classifies events against known issue patterns
3. Uses LLM for intelligent classification of unknown patterns
4. Emits structured events to Redis Streams
5. Uses Redis for persistent deduplication (survives pod restarts)

Enhanced with:
- LLM-based classification for unknown event patterns
- Learning from classification outcomes
- Dynamic pattern discovery
"""

import asyncio
import json
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


class ClassificationMethod(str, Enum):
    """Method used to classify an event."""

    PATTERN = "pattern"  # Matched known pattern
    LLM = "llm"  # Classified by LLM
    DEFAULT = "default"  # Default classification


class EventClassification(BaseModel):
    """Classification of a Kubernetes event."""

    severity: str = Field(description="low, medium, high, critical")
    is_actionable: bool = Field(description="Whether this needs remediation")
    category: str = Field(description="warning, error, normal, or issue type")
    reason: str = Field(description="Why this classification was made")
    method: ClassificationMethod = Field(
        default=ClassificationMethod.PATTERN,
        description="How this classification was determined",
    )
    confidence: float = Field(
        default=1.0,
        description="Confidence in this classification (0.0-1.0)",
    )
    suggested_action: str = Field(
        default="",
        description="Suggested remediation action",
    )


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

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "type": self.type,
            "reason": self.reason,
            "message": self.message,
            "namespace": self.namespace,
            "name": self.name,
            "kind": self.kind,
            "first_timestamp": self.first_timestamp,
            "last_timestamp": self.last_timestamp,
            "count": self.count,
        }


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
    "FailedCreate": {"severity": "high", "category": "resource"},
    "FailedKillPod": {"severity": "medium", "category": "pod_health"},
    "NetworkNotReady": {"severity": "high", "category": "network"},
    "FreeDiskSpaceFailed": {"severity": "high", "category": "storage"},
    "EvictionThresholdMet": {"severity": "high", "category": "resource"},
    "NodeHasDiskPressure": {"severity": "high", "category": "node_health"},
    "NodeHasMemoryPressure": {"severity": "high", "category": "node_health"},
}

# Default cooldown in seconds (60 minutes) - can be overridden via SENTINEL_COOLDOWN_SECONDS
DEFAULT_COOLDOWN_SECONDS = 3600

# LLM classification prompt template
LLM_CLASSIFICATION_PROMPT = """You are a Kubernetes expert. Analyze this Kubernetes event and classify it.

Event Details:
- Type: {type}
- Reason: {reason}
- Message: {message}
- Resource: {kind}/{name} in namespace {namespace}
- Occurrence Count: {count}

Based on your knowledge of Kubernetes, classify this event:

1. Severity: Choose one of: low, medium, high, critical
   - low: Informational, no action needed
   - medium: Should be monitored, may need attention
   - high: Requires attention soon, impacts service
   - critical: Immediate action required, service down or at risk

2. Category: Choose the most appropriate:
   - pod_health: Issues with pod lifecycle or health
   - resource: Resource limits, quotas, or capacity issues
   - scheduling: Pod scheduling problems
   - storage: Volume or storage issues
   - network: Network connectivity issues
   - node_health: Node-level problems
   - security: Security-related events
   - configuration: Misconfiguration issues
   - other: Doesn't fit other categories

3. Is Actionable: true if this requires remediation, false otherwise

4. Suggested Action: Brief description of recommended remediation

Respond in JSON format:
{{
    "severity": "...",
    "category": "...",
    "is_actionable": true/false,
    "suggested_action": "...",
    "reasoning": "..."
}}"""


@dataclass
class LLMClassifierConfig:
    """Configuration for LLM-based classification."""

    enabled: bool = True
    cache_classifications: bool = True
    cache_ttl_seconds: int = 86400  # 24 hours
    model_id: str | None = None  # Use default if None
    max_retries: int = 2
    timeout_seconds: float = 30.0


class LLMEventClassifier:
    """
    LLM-based event classifier for unknown Kubernetes events.

    Uses an LLM to intelligently classify events that don't match
    known patterns, enabling the system to handle novel issues.
    """

    CACHE_KEY_PREFIX = "sentinel:llm_class:"

    def __init__(
        self,
        redis_client: aioredis.Redis | None = None,
        config: LLMClassifierConfig | None = None,
    ):
        """
        Initialize the LLM classifier.

        Args:
            redis_client: Redis client for caching
            config: Classifier configuration
        """
        self.config = config or LLMClassifierConfig()
        self._redis = redis_client
        self._agent = None

    async def _get_agent(self):
        """Get or create the classification agent."""
        if self._agent is None:
            try:
                from core_agents.factory import AgentConfig, AgentFactory, ModelConfig

                factory = AgentFactory()
                model_config = None
                if self.config.model_id:
                    model_config = ModelConfig(model_id=self.config.model_id)

                self._agent = factory.create_agent(
                    AgentConfig(
                        name="event-classifier",
                        description="Classifies Kubernetes events",
                        system_prompt=(
                            "You are a Kubernetes expert specializing in event analysis "
                            "and incident classification. Respond only with valid JSON."
                        ),
                        tools=[],
                        model_config=model_config,
                        enable_observability=False,
                    )
                )
            except Exception as e:
                logger.error(f"Failed to create LLM classifier agent: {e}")
                return None

        return self._agent

    def _get_cache_key(self, event: K8sEvent) -> str:
        """Generate cache key for an event classification."""
        # Cache by reason and message pattern (not specific resource)
        return f"{self.CACHE_KEY_PREFIX}{event.reason}:{hash(event.message[:100])}"

    async def _get_cached_classification(self, event: K8sEvent) -> EventClassification | None:
        """Get cached classification if available."""
        if not self.config.cache_classifications or not self._redis:
            return None

        try:
            cache_key = self._get_cache_key(event)
            cached = await self._redis.get(cache_key)
            if cached:
                data = json.loads(cached)
                return EventClassification(**data)
        except Exception as e:
            logger.debug(f"Cache lookup failed: {e}")

        return None

    async def _cache_classification(
        self, event: K8sEvent, classification: EventClassification
    ) -> None:
        """Cache a classification result."""
        if not self.config.cache_classifications or not self._redis:
            return

        try:
            cache_key = self._get_cache_key(event)
            await self._redis.set(
                cache_key,
                classification.model_dump_json(),
                ex=self.config.cache_ttl_seconds,
            )
        except Exception as e:
            logger.debug(f"Cache store failed: {e}")

    async def classify(self, event: K8sEvent) -> EventClassification | None:
        """
        Classify an event using LLM.

        Args:
            event: The Kubernetes event to classify

        Returns:
            EventClassification or None if classification failed
        """
        if not self.config.enabled:
            return None

        # Check cache first
        cached = await self._get_cached_classification(event)
        if cached:
            logger.debug(f"Using cached LLM classification for {event.reason}")
            return cached

        # Get agent
        agent = await self._get_agent()
        if not agent:
            return None

        # Build prompt
        prompt = LLM_CLASSIFICATION_PROMPT.format(
            type=event.type,
            reason=event.reason,
            message=event.message,
            kind=event.kind,
            name=event.name,
            namespace=event.namespace,
            count=event.count,
        )

        # Call LLM
        for attempt in range(self.config.max_retries):
            try:
                result = agent(prompt)
                response_text = result.message if hasattr(result, "message") else str(result)

                # Parse JSON response
                # Try to extract JSON from response
                json_start = response_text.find("{")
                json_end = response_text.rfind("}") + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = response_text[json_start:json_end]
                    data = json.loads(json_str)

                    classification = EventClassification(
                        severity=data.get("severity", "medium"),
                        is_actionable=data.get("is_actionable", True),
                        category=data.get("category", "other"),
                        reason=data.get("reasoning", f"LLM classified: {event.reason}"),
                        method=ClassificationMethod.LLM,
                        confidence=0.8,  # LLM classifications have slightly lower confidence
                        suggested_action=data.get("suggested_action", ""),
                    )

                    # Cache the result
                    await self._cache_classification(event, classification)

                    logger.info(
                        f"LLM classified {event.reason} as {classification.severity}/{classification.category}"
                    )
                    return classification

            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse LLM response (attempt {attempt + 1}): {e}")
            except Exception as e:
                logger.error(f"LLM classification failed (attempt {attempt + 1}): {e}")

        return None


class SentinelAgent:
    """
    Watches Kubernetes events and publishes actionable issues.

    The Sentinel classifies events using known issue patterns and
    publishes them to the event bus for the Healer to process.

    Enhanced with LLM-based classification for unknown patterns.

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
        enable_llm_classification: bool = True,
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

        # LLM classifier
        self._enable_llm = enable_llm_classification
        self._llm_classifier: LLMEventClassifier | None = None

        # Classification statistics
        self._classification_stats = {
            "pattern_matches": 0,
            "llm_classifications": 0,
            "default_classifications": 0,
        }

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

        # Initialize LLM classifier
        if self._enable_llm and self._llm_classifier is None:
            self._llm_classifier = LLMEventClassifier(redis_client=self._redis)
            logger.info("LLM event classifier enabled")

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
        classification = await self._classify_event(event)

        if classification.is_actionable:
            await self._publish_issue(event, classification)

    async def _classify_event(self, event: K8sEvent) -> EventClassification:
        """
        Classify a Kubernetes event.

        Uses a tiered approach:
        1. First, check known patterns (fast, high confidence)
        2. If unknown, use LLM classification (slower, intelligent)
        3. Fall back to default classification if LLM unavailable
        """
        # Try known patterns first
        pattern = ISSUE_PATTERNS.get(event.reason)

        if pattern:
            self._classification_stats["pattern_matches"] += 1
            severity = pattern["severity"]
            return EventClassification(
                severity=severity,
                is_actionable=severity in ("high", "critical", "medium"),
                category=pattern["category"],
                reason=f"Matched known pattern: {event.reason}",
                method=ClassificationMethod.PATTERN,
                confidence=1.0,
            )

        # Try LLM classification for unknown patterns
        if self._llm_classifier:
            llm_result = await self._llm_classifier.classify(event)
            if llm_result:
                self._classification_stats["llm_classifications"] += 1
                return llm_result

        # Default classification for unknown Warning events
        self._classification_stats["default_classifications"] += 1

        if event.type == "Warning":
            return EventClassification(
                severity="medium",
                is_actionable=True,
                category="warning",
                reason=f"Warning event: {event.reason}",
                method=ClassificationMethod.DEFAULT,
                confidence=0.5,
            )

        # Normal event, not actionable
        return EventClassification(
            severity="low",
            is_actionable=False,
            category="normal",
            reason="Normal event, no action needed",
            method=ClassificationMethod.DEFAULT,
            confidence=1.0,
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
                "method": classification.method.value,
                "confidence": classification.confidence,
                "suggested_action": classification.suggested_action,
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
            f"(severity={classification.severity}, method={classification.method.value})"
        )

    def get_classification_stats(self) -> dict[str, int]:
        """Get classification statistics."""
        return dict(self._classification_stats)

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
    enable_llm_classification: bool = True,
) -> None:
    """Run the Sentinel agent."""
    sentinel = SentinelAgent(
        poll_interval=poll_interval,
        watch_mode=watch_mode,
        enable_llm_classification=enable_llm_classification,
    )

    if stop_after:

        async def stop_timer():
            await asyncio.sleep(stop_after)
            sentinel.stop()

        asyncio.create_task(stop_timer())

    await sentinel.start()
