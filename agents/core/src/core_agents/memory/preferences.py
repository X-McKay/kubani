"""
User preferences memory for personalization.

Tracks user interests and preferences based on feedback and engagement,
enabling agents to personalize their responses and recommendations.

Features:
- Topic interest tracking with decay
- Engagement history (likes, dislikes, bookmarks)
- Automatic interest scoring based on behavior
- Preference search for content ranking

Usage:
    from core_agents.user_preferences import UserPreferences

    # Initialize preferences for a user
    prefs = UserPreferences(user_id="user123", agent_id="news-monitor")

    # Record user engagement
    prefs.record_like("machine learning", content_id="article-456")
    prefs.record_dislike("celebrity gossip", content_id="article-789")
    prefs.record_bookmark("kubernetes", content_id="article-101")

    # Get interest scores for content ranking
    scores = prefs.get_interest_scores(["AI", "kubernetes", "sports"])
    # Returns: {"AI": 0.8, "kubernetes": 0.9, "sports": 0.1}

    # Check if user is interested in a topic
    if prefs.is_interested("kubernetes"):
        # Show K8s-related content more prominently
        pass
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class EngagementType(Enum):
    """Types of user engagement."""

    LIKE = "like"
    DISLIKE = "dislike"
    BOOKMARK = "bookmark"
    VIEW = "view"
    SHARE = "share"
    DISMISS = "dismiss"


# Weights for different engagement types
ENGAGEMENT_WEIGHTS = {
    EngagementType.LIKE: 1.0,
    EngagementType.BOOKMARK: 1.5,
    EngagementType.SHARE: 2.0,
    EngagementType.VIEW: 0.1,
    EngagementType.DISLIKE: -1.0,
    EngagementType.DISMISS: -0.5,
}


@dataclass
class EngagementRecord:
    """A single engagement event."""

    topic: str
    engagement_type: EngagementType
    timestamp: float = field(default_factory=time.time)
    content_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TopicPreference:
    """Aggregated preference for a topic."""

    topic: str
    score: float  # Positive = interested, negative = not interested
    engagement_count: int
    last_engagement: float
    positive_count: int = 0
    negative_count: int = 0


@dataclass
class UserPreferencesConfig:
    """Configuration for user preferences tracking."""

    # Score decay settings
    decay_half_life_days: float = 30.0  # Score halves every 30 days
    min_score_threshold: float = 0.1  # Ignore topics below this score

    # Memory settings
    max_topics: int = 100  # Maximum topics to track
    collection_name: str = "user_preferences"

    # Interest classification thresholds
    high_interest_threshold: float = 0.7
    low_interest_threshold: float = -0.3


class UserPreferences:
    """
    User preferences memory for personalization.

    Tracks user interests based on engagement and provides
    personalized scoring for content ranking.
    """

    def __init__(
        self,
        user_id: str,
        agent_id: str,
        mem0_config: dict[str, Any] | None = None,
        config: UserPreferencesConfig | None = None,
    ):
        """
        Initialize user preferences.

        Args:
            user_id: Unique identifier for the user
            agent_id: Agent using this preferences system
            mem0_config: Configuration for mem0 memory storage
            config: User preferences configuration
        """
        self.user_id = user_id
        self.agent_id = agent_id
        self.config = config or UserPreferencesConfig()
        self._mem0_config = mem0_config

        # In-memory cache for fast access
        self._topic_scores: dict[str, TopicPreference] = {}
        self._loaded = False

        # Lazy mem0 initialization
        self._memory: Any = None

        logger.info(f"UserPreferences initialized for user={user_id}, agent={agent_id}")

    def _get_memory(self) -> Any:
        """Get or create the mem0 memory instance."""
        if self._memory is None:
            from mem0 import Memory

            if self._mem0_config is None:
                from core_agents.memory.config import get_mem0_config

                self._mem0_config = get_mem0_config(
                    collection_name=f"{self.config.collection_name}_{self.agent_id}"
                )

            self._memory = Memory.from_config(self._mem0_config)
            logger.debug(f"Initialized mem0 for user preferences: {self.agent_id}")

        return self._memory

    def _calculate_decay(self, timestamp: float) -> float:
        """Calculate decay factor based on age."""
        age_seconds = time.time() - timestamp
        age_days = age_seconds / 86400
        half_life = self.config.decay_half_life_days
        return 0.5 ** (age_days / half_life)

    def _load_preferences(self) -> None:
        """Load preferences from memory into cache."""
        if self._loaded:
            return

        try:
            memory = self._get_memory()
            results = memory.get_all(user_id=f"{self.agent_id}:{self.user_id}")

            for result in results:
                metadata = result.get("metadata", {})
                if metadata.get("type") != "topic_preference":
                    continue

                topic = metadata.get("topic")
                if not topic:
                    continue

                pref = TopicPreference(
                    topic=topic,
                    score=metadata.get("score", 0.0),
                    engagement_count=metadata.get("engagement_count", 0),
                    last_engagement=metadata.get("last_engagement", time.time()),
                    positive_count=metadata.get("positive_count", 0),
                    negative_count=metadata.get("negative_count", 0),
                )
                self._topic_scores[topic.lower()] = pref

            self._loaded = True
            logger.debug(f"Loaded {len(self._topic_scores)} topic preferences for {self.user_id}")

        except Exception as e:
            logger.error(f"Failed to load preferences: {e}")
            self._loaded = True  # Mark as loaded to prevent retries

    def _save_preference(self, pref: TopicPreference) -> None:
        """Save a topic preference to memory."""
        try:
            memory = self._get_memory()

            content = f"User preference for topic: {pref.topic}, score: {pref.score:.2f}"

            metadata = {
                "type": "topic_preference",
                "topic": pref.topic,
                "score": pref.score,
                "engagement_count": pref.engagement_count,
                "last_engagement": pref.last_engagement,
                "positive_count": pref.positive_count,
                "negative_count": pref.negative_count,
                "updated_at": datetime.now(UTC).isoformat(),
            }

            memory.add(
                content,
                user_id=f"{self.agent_id}:{self.user_id}",
                metadata=metadata,
            )

            logger.debug(f"Saved preference for {pref.topic}: {pref.score:.2f}")

        except Exception as e:
            logger.error(f"Failed to save preference: {e}")

    def _update_topic_score(
        self,
        topic: str,
        engagement_type: EngagementType,
        content_id: str | None = None,
    ) -> TopicPreference:
        """Update score for a topic based on engagement."""
        self._load_preferences()

        topic_key = topic.lower()
        weight = ENGAGEMENT_WEIGHTS.get(engagement_type, 0)
        now = time.time()

        if topic_key in self._topic_scores:
            pref = self._topic_scores[topic_key]
            # Apply decay to existing score
            decay = self._calculate_decay(pref.last_engagement)
            decayed_score = pref.score * decay
            # Add new engagement
            new_score = max(-1.0, min(1.0, decayed_score + weight * 0.2))
            pref.score = new_score
            pref.engagement_count += 1
            pref.last_engagement = now
            if weight > 0:
                pref.positive_count += 1
            elif weight < 0:
                pref.negative_count += 1
        else:
            pref = TopicPreference(
                topic=topic,
                score=max(-1.0, min(1.0, weight * 0.3)),
                engagement_count=1,
                last_engagement=now,
                positive_count=1 if weight > 0 else 0,
                negative_count=1 if weight < 0 else 0,
            )
            self._topic_scores[topic_key] = pref

        # Save to persistent storage
        self._save_preference(pref)

        return pref

    # -------------------------------------------------------------------------
    # Public API - Record Engagement
    # -------------------------------------------------------------------------

    def record_engagement(
        self,
        topic: str,
        engagement_type: EngagementType,
        content_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TopicPreference:
        """
        Record a user engagement event.

        Args:
            topic: The topic the user engaged with
            engagement_type: Type of engagement
            content_id: Optional ID of the content
            metadata: Optional additional metadata

        Returns:
            Updated topic preference
        """
        return self._update_topic_score(topic, engagement_type, content_id)

    def record_like(self, topic: str, content_id: str | None = None) -> TopicPreference:
        """Record a like for a topic."""
        return self.record_engagement(topic, EngagementType.LIKE, content_id)

    def record_dislike(self, topic: str, content_id: str | None = None) -> TopicPreference:
        """Record a dislike for a topic."""
        return self.record_engagement(topic, EngagementType.DISLIKE, content_id)

    def record_bookmark(self, topic: str, content_id: str | None = None) -> TopicPreference:
        """Record a bookmark for a topic."""
        return self.record_engagement(topic, EngagementType.BOOKMARK, content_id)

    def record_view(self, topic: str, content_id: str | None = None) -> TopicPreference:
        """Record a view for a topic."""
        return self.record_engagement(topic, EngagementType.VIEW, content_id)

    def record_share(self, topic: str, content_id: str | None = None) -> TopicPreference:
        """Record a share for a topic."""
        return self.record_engagement(topic, EngagementType.SHARE, content_id)

    def record_dismiss(self, topic: str, content_id: str | None = None) -> TopicPreference:
        """Record a dismiss for a topic."""
        return self.record_engagement(topic, EngagementType.DISMISS, content_id)

    # -------------------------------------------------------------------------
    # Public API - Query Preferences
    # -------------------------------------------------------------------------

    def get_preference(self, topic: str) -> TopicPreference | None:
        """
        Get preference for a specific topic.

        Args:
            topic: The topic to look up

        Returns:
            TopicPreference if found, None otherwise
        """
        self._load_preferences()
        return self._topic_scores.get(topic.lower())

    def get_interest_score(self, topic: str) -> float:
        """
        Get interest score for a topic (0.0 to 1.0).

        Args:
            topic: The topic to score

        Returns:
            Interest score between 0.0 (no interest) and 1.0 (high interest)
        """
        pref = self.get_preference(topic)
        if pref is None:
            return 0.5  # Neutral for unknown topics

        # Apply decay and normalize to 0-1 range
        decay = self._calculate_decay(pref.last_engagement)
        decayed_score = pref.score * decay

        # Convert from [-1, 1] to [0, 1]
        return (decayed_score + 1) / 2

    def get_interest_scores(self, topics: list[str]) -> dict[str, float]:
        """
        Get interest scores for multiple topics.

        Args:
            topics: List of topics to score

        Returns:
            Dict mapping topic to interest score
        """
        return {topic: self.get_interest_score(topic) for topic in topics}

    def is_interested(self, topic: str) -> bool:
        """
        Check if user is interested in a topic.

        Args:
            topic: The topic to check

        Returns:
            True if user shows interest in this topic
        """
        score = self.get_interest_score(topic)
        return score >= (self.config.high_interest_threshold + 1) / 2

    def is_not_interested(self, topic: str) -> bool:
        """
        Check if user has shown disinterest in a topic.

        Args:
            topic: The topic to check

        Returns:
            True if user has actively avoided this topic
        """
        score = self.get_interest_score(topic)
        return score <= (self.config.low_interest_threshold + 1) / 2

    def get_top_interests(self, limit: int = 10) -> list[TopicPreference]:
        """
        Get the user's top interests.

        Args:
            limit: Maximum number of topics to return

        Returns:
            List of TopicPreference sorted by score (highest first)
        """
        self._load_preferences()

        # Apply decay and sort
        scored = []
        for pref in self._topic_scores.values():
            decay = self._calculate_decay(pref.last_engagement)
            decayed_score = pref.score * decay
            if decayed_score >= self.config.min_score_threshold:
                scored.append((decayed_score, pref))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [pref for _, pref in scored[:limit]]

    def get_avoided_topics(self, limit: int = 10) -> list[TopicPreference]:
        """
        Get topics the user actively avoids.

        Args:
            limit: Maximum number of topics to return

        Returns:
            List of TopicPreference sorted by score (lowest first)
        """
        self._load_preferences()

        scored = []
        for pref in self._topic_scores.values():
            decay = self._calculate_decay(pref.last_engagement)
            decayed_score = pref.score * decay
            if decayed_score <= -self.config.min_score_threshold:
                scored.append((decayed_score, pref))

        scored.sort(key=lambda x: x[0])
        return [pref for _, pref in scored[:limit]]

    def rank_content(
        self,
        items: list[dict[str, Any]],
        topic_key: str = "topics",
        score_key: str = "preference_score",
    ) -> list[dict[str, Any]]:
        """
        Rank content items by user preference.

        Args:
            items: List of content items (each must have a topics field)
            topic_key: Key in item dict containing list of topics
            score_key: Key to add with preference score

        Returns:
            Items with preference_score added, sorted by score
        """
        for item in items:
            topics = item.get(topic_key, [])
            if not topics:
                item[score_key] = 0.5
                continue

            # Average score across all topics
            scores = self.get_interest_scores(topics)
            avg_score = sum(scores.values()) / len(scores) if scores else 0.5
            item[score_key] = avg_score

        # Sort by preference score (highest first)
        return sorted(items, key=lambda x: x.get(score_key, 0), reverse=True)
