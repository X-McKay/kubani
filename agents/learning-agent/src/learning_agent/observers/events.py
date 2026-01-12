"""
Event Collector.

Subscribes to the Redis event bus and collects agent events
for the learning pipeline.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AgentEvent:
    """An event from an agent."""

    event_id: str
    event_type: str
    source: str
    timestamp: datetime
    payload: dict[str, Any]
    correlation_id: str | None = None

    @property
    def agent_name(self) -> str:
        """Extract agent name from source."""
        # Source is typically "agent-name" or "agent-name:component"
        return self.source.split(":")[0].replace("-", "_")


@dataclass
class ExecutionChain:
    """A chain of correlated events representing one execution."""

    correlation_id: str
    events: list[AgentEvent] = field(default_factory=list)
    agent_name: str = ""
    start_time: datetime | None = None
    end_time: datetime | None = None

    @property
    def is_complete(self) -> bool:
        """Check if the chain has start and end events."""
        if not self.events:
            return False

        event_types = {e.event_type for e in self.events}

        # Check for completion patterns
        completion_patterns = [
            ("K8S_ISSUE_DETECTED", "K8S_REMEDIATION_COMPLETED"),
            ("K8S_ISSUE_DETECTED", "K8S_REMEDIATION_FAILED"),
            ("NEWS_ARTICLE_INGESTED", "NEWS_DIGEST_PUBLISHED"),
        ]

        for start, end in completion_patterns:
            if start in event_types and end in event_types:
                return True

        # Check for single-event completions
        single_complete = {"NEWS_DIGEST_PUBLISHED", "NEWS_BREAKING_DETECTED"}
        if event_types & single_complete:
            return True

        return False

    @property
    def is_success(self) -> bool:
        """Determine if the execution chain was successful."""
        event_types = {e.event_type for e in self.events}

        failure_types = {"K8S_REMEDIATION_FAILED", "SYSTEM_ERROR"}
        if event_types & failure_types:
            return False

        success_types = {
            "K8S_REMEDIATION_COMPLETED",
            "NEWS_DIGEST_PUBLISHED",
            "NEWS_BREAKING_DETECTED",
            "SYSTEM_SKILL_APPROVED",
        }
        return bool(event_types & success_types)

    def add_event(self, event: AgentEvent) -> None:
        """Add an event to the chain."""
        self.events.append(event)
        self.events.sort(key=lambda e: e.timestamp)

        if not self.agent_name and event.agent_name:
            self.agent_name = event.agent_name

        if not self.start_time or event.timestamp < self.start_time:
            self.start_time = event.timestamp

        if not self.end_time or event.timestamp > self.end_time:
            self.end_time = event.timestamp


class EventCollector:
    """
    Collects events from the Redis event bus.

    Buffers events and correlates them into execution chains.
    """

    # Event types we care about for learning
    MONITORED_EVENTS = {
        # K8s events
        "K8S_ISSUE_DETECTED",
        "K8S_REMEDIATION_STARTED",
        "K8S_REMEDIATION_COMPLETED",
        "K8S_REMEDIATION_FAILED",
        # News events
        "NEWS_ARTICLE_INGESTED",
        "NEWS_BREAKING_DETECTED",
        "NEWS_DIGEST_PUBLISHED",
        "NEWS_TREND_DETECTED",
        # System events
        "SYSTEM_SKILL_PROPOSED",
        "SYSTEM_SKILL_APPROVED",
        "SYSTEM_SKILL_REJECTED",
        "SYSTEM_APPROVAL_REQUESTED",
    }

    def __init__(
        self,
        redis_url: str = "redis://redis.ai-agents.svc:6379",
        consumer_group: str = "learning-agent",
        chain_timeout_seconds: int = 300,
    ):
        """
        Initialize the event collector.

        Args:
            redis_url: Redis connection URL
            consumer_group: Consumer group name for reliable delivery
            chain_timeout_seconds: Time to wait before considering a chain complete
        """
        self.redis_url = redis_url
        self.consumer_group = consumer_group
        self.chain_timeout = timedelta(seconds=chain_timeout_seconds)

        self._redis = None
        self._running = False
        self._event_buffer: list[AgentEvent] = []
        self._chains: dict[str, ExecutionChain] = {}
        self._completed_chains: list[ExecutionChain] = []

    async def _get_redis(self):
        """Get or create Redis connection."""
        if self._redis is None:
            try:
                import redis.asyncio as redis

                self._redis = redis.from_url(self.redis_url)
            except ImportError:
                logger.warning("redis package not available, event collection disabled")
                return None
        return self._redis

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis is not None:
            await self._redis.close()
            self._redis = None

    async def collect_recent_events(
        self,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[AgentEvent]:
        """
        Collect recent events from Redis streams.

        Args:
            since: Only return events after this time
            limit: Maximum events to return

        Returns:
            List of agent events
        """
        redis = await self._get_redis()
        if redis is None:
            return []

        if since is None:
            since = datetime.now(UTC) - timedelta(minutes=5)

        events = []

        try:
            # Query each monitored event stream
            for event_type in self.MONITORED_EVENTS:
                stream_name = f"events:{event_type.lower()}"

                try:
                    # Read from stream
                    messages = await redis.xread(
                        {stream_name: "0"},
                        count=limit,
                    )

                    for stream, stream_messages in messages:
                        for msg_id, msg_data in stream_messages:
                            event = self._parse_event(msg_id, event_type, msg_data)
                            if event and event.timestamp >= since:
                                events.append(event)

                except Exception as e:
                    # Stream may not exist yet
                    logger.debug(f"Could not read stream {stream_name}: {e}")

            events.sort(key=lambda e: e.timestamp)
            return events[:limit]

        except Exception as e:
            logger.warning(f"Failed to collect events: {e}")
            return []

    def correlate_events(self, events: list[AgentEvent]) -> list[ExecutionChain]:
        """
        Correlate events into execution chains.

        Args:
            events: List of events to correlate

        Returns:
            List of complete execution chains
        """
        # Add events to chains
        for event in events:
            if event.correlation_id:
                if event.correlation_id not in self._chains:
                    self._chains[event.correlation_id] = ExecutionChain(
                        correlation_id=event.correlation_id
                    )
                self._chains[event.correlation_id].add_event(event)
            else:
                # Events without correlation_id are standalone
                chain = ExecutionChain(correlation_id=event.event_id)
                chain.add_event(event)
                if chain.is_complete:
                    self._completed_chains.append(chain)

        # Check for complete chains
        now = datetime.now(UTC)
        completed = []
        expired_ids = []

        for corr_id, chain in self._chains.items():
            if chain.is_complete:
                completed.append(chain)
                expired_ids.append(corr_id)
            elif chain.end_time and (now - chain.end_time) > self.chain_timeout:
                # Chain timed out, consider it complete
                completed.append(chain)
                expired_ids.append(corr_id)

        # Remove completed chains from active tracking
        for corr_id in expired_ids:
            del self._chains[corr_id]

        # Add to completed list
        self._completed_chains.extend(completed)

        return completed

    def get_completed_chains(self, clear: bool = True) -> list[ExecutionChain]:
        """
        Get completed execution chains.

        Args:
            clear: If True, clear the completed chains list

        Returns:
            List of completed execution chains
        """
        chains = list(self._completed_chains)
        if clear:
            self._completed_chains.clear()
        return chains

    def _parse_event(
        self,
        msg_id: str | bytes,
        event_type: str,
        msg_data: dict,
    ) -> AgentEvent | None:
        """Parse a Redis message into an AgentEvent."""
        try:
            import json

            # Decode bytes if needed
            if isinstance(msg_id, bytes):
                msg_id = msg_id.decode()

            data = {}
            for key, value in msg_data.items():
                if isinstance(key, bytes):
                    key = key.decode()
                if isinstance(value, bytes):
                    value = value.decode()
                data[key] = value

            # Parse timestamp from message ID (format: timestamp-sequence)
            timestamp_ms = int(msg_id.split("-")[0])
            timestamp = datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)

            # Parse payload
            payload = {}
            if "payload" in data:
                try:
                    payload = json.loads(data["payload"])
                except (json.JSONDecodeError, TypeError):
                    payload = {"raw": data["payload"]}

            return AgentEvent(
                event_id=msg_id,
                event_type=event_type,
                source=data.get("source", "unknown"),
                timestamp=timestamp,
                payload=payload,
                correlation_id=data.get("correlation_id"),
            )

        except Exception as e:
            logger.debug(f"Failed to parse event: {e}")
            return None

    async def subscribe_loop(self) -> None:
        """
        Run a subscription loop for real-time event collection.

        This is a long-running task that continuously collects events.
        """
        self._running = True
        last_poll = datetime.now(UTC) - timedelta(minutes=1)

        while self._running:
            try:
                events = await self.collect_recent_events(since=last_poll)
                if events:
                    self.correlate_events(events)
                    last_poll = events[-1].timestamp

                await asyncio.sleep(10)  # Poll every 10 seconds

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Event subscription error: {e}")
                await asyncio.sleep(30)

    def stop(self) -> None:
        """Stop the subscription loop."""
        self._running = False
