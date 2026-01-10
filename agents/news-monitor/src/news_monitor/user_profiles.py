"""
User Profiles for Personalized News Digests.

Implements user profile management for personalized news delivery.
Profiles store user preferences, interests, and feedback to enable:

1. Personalized trend analysis based on topics of interest
2. Customized digest generation with relevant sections
3. Feedback-driven profile refinement over time

Usage:
    from news_monitor.user_profiles import UserProfileManager, UserProfile

    # Create manager
    manager = UserProfileManager()

    # Get or create profile
    profile = await manager.get_profile("user123")

    # Update preferences
    profile.topics_of_interest.append("kubernetes")
    await manager.save_profile(profile)

    # Record feedback
    await manager.record_feedback("user123", "article_id", positive=True)
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class UserProfile(BaseModel):
    """
    User profile for personalized news delivery.

    Stores preferences, interests, and feedback history to enable
    personalized content curation.
    """

    user_id: str = Field(description="Unique user identifier")

    # Interest configuration
    topics_of_interest: list[str] = Field(
        default_factory=list,
        description="Topics the user wants to follow (e.g., 'kubernetes', 'AI', 'security')",
    )
    keyword_alerts: list[str] = Field(
        default_factory=list,
        description="Keywords that trigger immediate alerts",
    )
    preferred_sources: list[str] = Field(
        default_factory=list,
        description="Preferred news sources (domains)",
    )

    # Negative preferences (from feedback)
    negative_keywords: list[str] = Field(
        default_factory=list,
        description="Keywords to deprioritize (from thumbs-down feedback)",
    )
    blocked_sources: list[str] = Field(
        default_factory=list,
        description="Sources to exclude",
    )

    # Delivery preferences
    digest_frequency: str = Field(
        default="daily",
        description="How often to receive digests: 'realtime', 'hourly', 'daily', 'weekly'",
    )
    max_articles_per_digest: int = Field(
        default=20,
        description="Maximum articles in a digest",
    )
    include_trends: bool = Field(
        default=True,
        description="Include trend analysis in digests",
    )

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Feedback statistics
    total_thumbs_up: int = Field(default=0)
    total_thumbs_down: int = Field(default=0)

    def model_post_init(self, __context: Any) -> None:
        """Update timestamp on any modification."""
        self.updated_at = datetime.now(UTC)


@dataclass
class ArticleFeedback:
    """Feedback on a specific article."""

    user_id: str
    article_id: str
    positive: bool
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    article_topics: list[str] = field(default_factory=list)
    article_source: str = ""


class UserProfileManager:
    """
    Manages user profiles for personalized news delivery.

    Supports multiple storage backends:
    - Redis (default, for production)
    - In-memory (for testing)
    - PostgreSQL (for persistence)
    """

    PROFILE_KEY_PREFIX = "news:profile:"
    FEEDBACK_KEY_PREFIX = "news:feedback:"

    def __init__(
        self,
        redis_url: Optional[str] = None,
        use_memory: bool = False,
    ):
        """
        Initialize the profile manager.

        Args:
            redis_url: Redis connection URL (uses env var if not provided)
            use_memory: Use in-memory storage (for testing)
        """
        self._redis = None
        self._redis_url = redis_url
        self._use_memory = use_memory
        self._memory_store: dict[str, UserProfile] = {}
        self._feedback_store: dict[str, list[ArticleFeedback]] = {}

    async def _get_redis(self):
        """Get Redis client."""
        if self._use_memory:
            return None

        if self._redis is None:
            import os

            import redis.asyncio as aioredis

            url = self._redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
            self._redis = aioredis.from_url(url, decode_responses=True)

        return self._redis

    async def get_profile(self, user_id: str) -> UserProfile:
        """
        Get a user profile, creating a default one if it doesn't exist.

        Args:
            user_id: User identifier

        Returns:
            UserProfile instance
        """
        if self._use_memory:
            if user_id not in self._memory_store:
                self._memory_store[user_id] = UserProfile(user_id=user_id)
            return self._memory_store[user_id]

        redis = await self._get_redis()
        if redis:
            try:
                key = f"{self.PROFILE_KEY_PREFIX}{user_id}"
                data = await redis.get(key)
                if data:
                    return UserProfile.model_validate_json(data)
            except Exception as e:
                logger.warning(f"Failed to get profile from Redis: {e}")

        # Return default profile
        return UserProfile(user_id=user_id)

    async def save_profile(self, profile: UserProfile) -> bool:
        """
        Save a user profile.

        Args:
            profile: UserProfile to save

        Returns:
            True if saved successfully
        """
        profile.updated_at = datetime.now(UTC)

        if self._use_memory:
            self._memory_store[profile.user_id] = profile
            return True

        redis = await self._get_redis()
        if redis:
            try:
                key = f"{self.PROFILE_KEY_PREFIX}{profile.user_id}"
                await redis.set(key, profile.model_dump_json())
                return True
            except Exception as e:
                logger.error(f"Failed to save profile: {e}")

        return False

    async def record_feedback(
        self,
        user_id: str,
        article_id: str,
        positive: bool,
        article_topics: Optional[list[str]] = None,
        article_source: str = "",
    ) -> None:
        """
        Record user feedback on an article.

        This feedback is used to refine the user's profile over time:
        - Positive feedback reinforces topics/sources
        - Negative feedback adds to negative_keywords/blocked_sources

        Args:
            user_id: User identifier
            article_id: Article identifier
            positive: True for thumbs-up, False for thumbs-down
            article_topics: Topics associated with the article
            article_source: Source domain of the article
        """
        feedback = ArticleFeedback(
            user_id=user_id,
            article_id=article_id,
            positive=positive,
            article_topics=article_topics or [],
            article_source=article_source,
        )

        # Store feedback
        if self._use_memory:
            if user_id not in self._feedback_store:
                self._feedback_store[user_id] = []
            self._feedback_store[user_id].append(feedback)
        else:
            redis = await self._get_redis()
            if redis:
                try:
                    key = f"{self.FEEDBACK_KEY_PREFIX}{user_id}"
                    await redis.lpush(
                        key,
                        json.dumps(
                            {
                                "article_id": article_id,
                                "positive": positive,
                                "topics": article_topics or [],
                                "source": article_source,
                                "timestamp": feedback.timestamp.isoformat(),
                            }
                        ),
                    )
                    # Keep last 1000 feedback items
                    await redis.ltrim(key, 0, 999)
                except Exception as e:
                    logger.warning(f"Failed to store feedback: {e}")

        # Update profile based on feedback
        await self._apply_feedback_to_profile(feedback)

    async def _apply_feedback_to_profile(self, feedback: ArticleFeedback) -> None:
        """
        Apply feedback to update user profile.

        Implements the feedback loop:
        - Positive feedback on topics -> add to topics_of_interest
        - Negative feedback on topics -> add to negative_keywords
        - Multiple negative feedbacks on source -> add to blocked_sources
        """
        profile = await self.get_profile(feedback.user_id)

        if feedback.positive:
            profile.total_thumbs_up += 1

            # Reinforce topics
            for topic in feedback.article_topics:
                if topic not in profile.topics_of_interest:
                    # Add topic after 2+ positive feedbacks
                    # (simplified: add immediately for now)
                    profile.topics_of_interest.append(topic)

                # Remove from negative if previously marked
                if topic in profile.negative_keywords:
                    profile.negative_keywords.remove(topic)

        else:
            profile.total_thumbs_down += 1

            # Add topics to negative keywords
            for topic in feedback.article_topics:
                if topic not in profile.negative_keywords:
                    profile.negative_keywords.append(topic)

            # Block source after multiple negative feedbacks
            # (simplified: track in memory, would need proper counting)
            if feedback.article_source and feedback.article_source not in profile.blocked_sources:
                # In production, would count negative feedbacks per source
                pass

        await self.save_profile(profile)

    async def get_all_profiles(self) -> list[UserProfile]:
        """Get all user profiles (for batch digest generation)."""
        if self._use_memory:
            return list(self._memory_store.values())

        profiles = []
        redis = await self._get_redis()
        if redis:
            try:
                keys = await redis.keys(f"{self.PROFILE_KEY_PREFIX}*")
                for key in keys:
                    data = await redis.get(key)
                    if data:
                        profiles.append(UserProfile.model_validate_json(data))
            except Exception as e:
                logger.error(f"Failed to get all profiles: {e}")

        return profiles


class PersonalizedDigestGenerator:
    """
    Generates personalized digests based on user profiles.

    Takes processed articles and user preferences to create
    customized news digests for each user.
    """

    def __init__(self, profile_manager: UserProfileManager):
        self.profile_manager = profile_manager

    def rank_articles_for_user(
        self,
        articles: list[Any],
        profile: UserProfile,
    ) -> list[Any]:
        """
        Rank and filter articles based on user preferences.

        Args:
            articles: List of ProcessedArticle objects
            profile: User profile

        Returns:
            Ranked and filtered list of articles
        """
        scored_articles = []

        for article in articles:
            score = self._calculate_relevance_score(article, profile)
            if score > 0:  # Filter out negative-scored articles
                scored_articles.append((score, article))

        # Sort by score descending
        scored_articles.sort(key=lambda x: x[0], reverse=True)

        # Limit to user's preference
        max_articles = profile.max_articles_per_digest
        return [article for _, article in scored_articles[:max_articles]]

    def _calculate_relevance_score(
        self,
        article: Any,
        profile: UserProfile,
    ) -> float:
        """
        Calculate relevance score for an article.

        Scoring factors:
        - +10 for each matching topic of interest
        - +5 for preferred source
        - +20 for keyword alert match
        - -10 for negative keyword
        - -100 for blocked source (effectively filters out)
        """
        score = 1.0  # Base score

        # Get article attributes (handle both dict and object)
        if hasattr(article, "topics"):
            topics = article.topics or []
        else:
            topics = article.get("topics", [])

        if hasattr(article, "source"):
            source = article.source or ""
        else:
            source = article.get("source", "")

        if hasattr(article, "title"):
            title = article.title or ""
        else:
            title = article.get("title", "")

        if hasattr(article, "summary"):
            summary = article.summary or ""
        else:
            summary = article.get("summary", "")

        content = f"{title} {summary}".lower()

        # Positive factors
        for topic in profile.topics_of_interest:
            if topic.lower() in [t.lower() for t in topics]:
                score += 10
            elif topic.lower() in content:
                score += 5

        for pref_source in profile.preferred_sources:
            if pref_source.lower() in source.lower():
                score += 5

        for keyword in profile.keyword_alerts:
            if keyword.lower() in content:
                score += 20

        # Negative factors
        for neg_keyword in profile.negative_keywords:
            if neg_keyword.lower() in content:
                score -= 10

        for blocked in profile.blocked_sources:
            if blocked.lower() in source.lower():
                score -= 100

        return score

    async def generate_personalized_digest(
        self,
        user_id: str,
        articles: list[Any],
        trends: list[Any],
    ) -> dict:
        """
        Generate a personalized digest for a user.

        Args:
            user_id: User identifier
            articles: All available processed articles
            trends: Trending topics

        Returns:
            Personalized digest dictionary
        """
        profile = await self.profile_manager.get_profile(user_id)

        # Rank articles for this user
        personalized_articles = self.rank_articles_for_user(articles, profile)

        # Filter trends to user's interests
        personalized_trends = []
        if profile.include_trends:
            for trend in trends:
                trend_topic = trend.topic if hasattr(trend, "topic") else trend.get("topic", "")
                if any(
                    topic.lower() in trend_topic.lower() for topic in profile.topics_of_interest
                ):
                    personalized_trends.append(trend)

        return {
            "user_id": user_id,
            "articles": personalized_articles,
            "trends": personalized_trends,
            "profile_topics": profile.topics_of_interest,
            "generated_at": datetime.now(UTC).isoformat(),
        }
