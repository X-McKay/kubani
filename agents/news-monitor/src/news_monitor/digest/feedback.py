"""
Emoji Feedback Handler for News Learning.

Captures and processes emoji reactions on news posts to learn:
- Which topics users find valuable
- Which sources are trusted
- What format/style works best
- What to prioritize in future digests

Emoji meanings:
- 👍/🔥 = Valuable/Important
- 📖/💡 = Want to learn more
- 🎯/⭐ = Actionable/Useful
- 🤔/❓ = Confusing/Need clarification
- 👎 = Not relevant/Not interested
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, UTC
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class FeedbackType(Enum):
    """Types of feedback from emoji reactions."""

    POSITIVE = "positive"  # 👍, 🔥, ⭐
    INTERESTED = "interested"  # 📖, 💡, 🔜
    ACTIONABLE = "actionable"  # 🎯, ✅, 📌
    CONFUSED = "confused"  # 🤔, ❓
    NEGATIVE = "negative"  # 👎
    SECURITY = "security"  # 🚨, 🔍
    FOLLOW_UP = "follow_up"  # 👀, 📝


# Emoji to feedback type mapping
EMOJI_MAPPING: dict[str, FeedbackType] = {
    "👍": FeedbackType.POSITIVE,
    "🔥": FeedbackType.POSITIVE,
    "⭐": FeedbackType.POSITIVE,
    "📖": FeedbackType.INTERESTED,
    "💡": FeedbackType.INTERESTED,
    "🔜": FeedbackType.INTERESTED,
    "🎯": FeedbackType.ACTIONABLE,
    "✅": FeedbackType.ACTIONABLE,
    "📌": FeedbackType.ACTIONABLE,
    "🤔": FeedbackType.CONFUSED,
    "❓": FeedbackType.CONFUSED,
    "👎": FeedbackType.NEGATIVE,
    "🚨": FeedbackType.SECURITY,
    "🔍": FeedbackType.SECURITY,
    "👀": FeedbackType.FOLLOW_UP,
    "📝": FeedbackType.FOLLOW_UP,
    "🔄": FeedbackType.FOLLOW_UP,
    "📊": FeedbackType.INTERESTED,
    "🔮": FeedbackType.INTERESTED,
    "🛠️": FeedbackType.ACTIONABLE,
}


@dataclass
class FeedbackEvent:
    """A single feedback event from an emoji reaction."""

    message_id: str
    channel_id: str
    user_id: str
    emoji: str
    feedback_type: FeedbackType
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    # Context about the message
    message_category: str = ""  # topline, research, tools, etc.
    article_url: str = ""
    article_source: str = ""
    article_topic: str = ""


@dataclass
class FeedbackAggregation:
    """Aggregated feedback for an item."""

    item_id: str  # message_id or article_url
    total_reactions: int = 0
    positive_count: int = 0
    interested_count: int = 0
    actionable_count: int = 0
    confused_count: int = 0
    negative_count: int = 0

    @property
    def engagement_score(self) -> float:
        """Calculate overall engagement score (0-1)."""
        if self.total_reactions == 0:
            return 0.0

        # Weighted score
        weighted = (
            self.positive_count * 1.0
            + self.interested_count * 0.8
            + self.actionable_count * 1.2
            + self.confused_count * 0.3  # Some engagement
            - self.negative_count * 0.5
        )

        # Normalize
        return max(0.0, min(1.0, weighted / self.total_reactions))

    @property
    def sentiment(self) -> str:
        """Get overall sentiment."""
        if self.total_reactions == 0:
            return "neutral"

        positive_ratio = (self.positive_count + self.actionable_count) / self.total_reactions
        negative_ratio = self.negative_count / self.total_reactions

        if positive_ratio > 0.6:
            return "positive"
        elif negative_ratio > 0.3:
            return "negative"
        elif self.confused_count / self.total_reactions > 0.3:
            return "confused"
        else:
            return "neutral"


@dataclass
class TopicPreference:
    """Learned preference for a topic."""

    topic: str
    engagement_score: float
    reaction_count: int
    last_updated: datetime


@dataclass
class SourcePreference:
    """Learned preference for a source."""

    source: str
    engagement_score: float
    reaction_count: int
    last_updated: datetime


class FeedbackCollector:
    """
    Collects and stores feedback events.

    Integrates with:
    - Discord reactions via MCP
    - Shared memory for persistence
    - Learning system for skill improvement
    """

    def __init__(
        self,
        redis_client: Any = None,
        shared_memory: Any = None,
    ):
        """Initialize the collector."""
        self.redis_client = redis_client
        self.shared_memory = shared_memory
        self._events: list[FeedbackEvent] = []
        self._aggregations: dict[str, FeedbackAggregation] = {}

    async def record_reaction(
        self,
        message_id: str,
        channel_id: str,
        user_id: str,
        emoji: str,
        message_metadata: dict[str, Any] | None = None,
    ) -> FeedbackEvent | None:
        """
        Record a reaction as feedback.

        Args:
            message_id: Discord message ID
            channel_id: Discord channel ID
            user_id: User who reacted
            emoji: The emoji used
            message_metadata: Optional metadata about the message

        Returns:
            FeedbackEvent if recorded, None if emoji not recognized
        """
        feedback_type = EMOJI_MAPPING.get(emoji)
        if not feedback_type:
            logger.debug(f"Unrecognized emoji: {emoji}")
            return None

        metadata = message_metadata or {}

        event = FeedbackEvent(
            message_id=message_id,
            channel_id=channel_id,
            user_id=user_id,
            emoji=emoji,
            feedback_type=feedback_type,
            message_category=metadata.get("category", ""),
            article_url=metadata.get("url", ""),
            article_source=metadata.get("source", ""),
            article_topic=metadata.get("topic", ""),
        )

        self._events.append(event)

        # Update aggregation
        await self._update_aggregation(event)

        # Persist to Redis if available
        if self.redis_client:
            await self._persist_event(event)

        logger.debug(f"Recorded feedback: {emoji} on {message_id}")
        return event

    async def _update_aggregation(self, event: FeedbackEvent) -> None:
        """Update aggregation for an item."""
        item_id = event.message_id

        if item_id not in self._aggregations:
            self._aggregations[item_id] = FeedbackAggregation(item_id=item_id)

        agg = self._aggregations[item_id]
        agg.total_reactions += 1

        if event.feedback_type == FeedbackType.POSITIVE:
            agg.positive_count += 1
        elif event.feedback_type == FeedbackType.INTERESTED:
            agg.interested_count += 1
        elif event.feedback_type == FeedbackType.ACTIONABLE:
            agg.actionable_count += 1
        elif event.feedback_type == FeedbackType.CONFUSED:
            agg.confused_count += 1
        elif event.feedback_type == FeedbackType.NEGATIVE:
            agg.negative_count += 1

    async def _persist_event(self, event: FeedbackEvent) -> None:
        """Persist event to Redis."""
        try:
            import json

            key = f"feedback:{event.message_id}:{event.user_id}:{event.emoji}"
            data = {
                "message_id": event.message_id,
                "channel_id": event.channel_id,
                "user_id": event.user_id,
                "emoji": event.emoji,
                "feedback_type": event.feedback_type.value,
                "timestamp": event.timestamp.isoformat(),
                "category": event.message_category,
                "source": event.article_source,
                "topic": event.article_topic,
            }
            await self.redis_client.set(key, json.dumps(data), ex=86400 * 30)  # 30 days
        except Exception as e:
            logger.warning(f"Failed to persist feedback: {e}")

    def get_aggregation(self, item_id: str) -> FeedbackAggregation | None:
        """Get aggregation for an item."""
        return self._aggregations.get(item_id)

    def get_recent_events(
        self,
        hours: int = 24,
        feedback_type: FeedbackType | None = None,
    ) -> list[FeedbackEvent]:
        """Get recent feedback events."""
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        events = [e for e in self._events if e.timestamp >= cutoff]

        if feedback_type:
            events = [e for e in events if e.feedback_type == feedback_type]

        return events


class PreferenceLearner:
    """
    Learns user preferences from feedback.

    Tracks:
    - Topic preferences
    - Source preferences
    - Content type preferences
    - Time-of-day preferences
    """

    def __init__(self, feedback_collector: FeedbackCollector):
        """Initialize the learner."""
        self.collector = feedback_collector
        self._topic_preferences: dict[str, TopicPreference] = {}
        self._source_preferences: dict[str, SourcePreference] = {}

    async def update_preferences(self) -> None:
        """Update preferences from recent feedback."""
        events = self.collector.get_recent_events(hours=168)  # Last week

        # Group by topic
        topic_events: dict[str, list[FeedbackEvent]] = {}
        source_events: dict[str, list[FeedbackEvent]] = {}

        for event in events:
            if event.article_topic:
                if event.article_topic not in topic_events:
                    topic_events[event.article_topic] = []
                topic_events[event.article_topic].append(event)

            if event.article_source:
                if event.article_source not in source_events:
                    source_events[event.article_source] = []
                source_events[event.article_source].append(event)

        # Calculate topic preferences
        for topic, events_list in topic_events.items():
            score = self._calculate_engagement_score(events_list)
            self._topic_preferences[topic] = TopicPreference(
                topic=topic,
                engagement_score=score,
                reaction_count=len(events_list),
                last_updated=datetime.now(UTC),
            )

        # Calculate source preferences
        for source, events_list in source_events.items():
            score = self._calculate_engagement_score(events_list)
            self._source_preferences[source] = SourcePreference(
                source=source,
                engagement_score=score,
                reaction_count=len(events_list),
                last_updated=datetime.now(UTC),
            )

    def _calculate_engagement_score(self, events: list[FeedbackEvent]) -> float:
        """Calculate engagement score from events."""
        if not events:
            return 0.5

        positive = sum(
            1 for e in events
            if e.feedback_type in (FeedbackType.POSITIVE, FeedbackType.ACTIONABLE)
        )
        negative = sum(1 for e in events if e.feedback_type == FeedbackType.NEGATIVE)

        total = len(events)
        score = (positive - negative * 0.5) / total
        return max(0.0, min(1.0, 0.5 + score * 0.5))

    def get_topic_boost(self, topic: str) -> float:
        """Get boost factor for a topic based on preferences."""
        pref = self._topic_preferences.get(topic)
        if not pref:
            return 1.0

        # Convert engagement score to boost (0.5 to 1.5)
        return 0.5 + pref.engagement_score

    def get_source_boost(self, source: str) -> float:
        """Get boost factor for a source based on preferences."""
        pref = self._source_preferences.get(source)
        if not pref:
            return 1.0

        return 0.5 + pref.engagement_score

    def get_top_topics(self, n: int = 10) -> list[TopicPreference]:
        """Get top N preferred topics."""
        topics = list(self._topic_preferences.values())
        topics.sort(key=lambda t: t.engagement_score, reverse=True)
        return topics[:n]

    def get_top_sources(self, n: int = 10) -> list[SourcePreference]:
        """Get top N preferred sources."""
        sources = list(self._source_preferences.values())
        sources.sort(key=lambda s: s.engagement_score, reverse=True)
        return sources[:n]

    def to_learning_report(self) -> dict[str, Any]:
        """Generate a report for the learning system."""
        return {
            "top_topics": [
                {"topic": t.topic, "score": t.engagement_score, "count": t.reaction_count}
                for t in self.get_top_topics(10)
            ],
            "top_sources": [
                {"source": s.source, "score": s.engagement_score, "count": s.reaction_count}
                for s in self.get_top_sources(10)
            ],
            "total_feedback_events": len(self.collector._events),
            "generated_at": datetime.now(UTC).isoformat(),
        }
