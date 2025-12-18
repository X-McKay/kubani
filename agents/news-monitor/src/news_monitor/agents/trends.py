"""
Trend Analyzer Agent - Identifies patterns and emerging themes.

Responsible for:
- Detecting hot topics (multiple sources covering same story)
- Tracking topic momentum over time
- Identifying emerging vs fading themes
- Using memory to compare current vs historical patterns
"""

import logging
from collections import Counter
from datetime import datetime

from news_monitor.memory import (
    calculate_trend_status,
    get_recent_themes,
    store_theme,
)
from news_monitor.models import ProcessedArticle, TrendingTopic, TrendStatus

logger = logging.getLogger(__name__)


class TrendAnalyzerAgent:
    """Agent for analyzing trends and patterns in news coverage."""

    def __init__(self, hot_threshold: int = 3, lookback_days: int = 7):
        """
        Initialize the trend analyzer.

        Args:
            hot_threshold: Number of sources required for a "hot" topic
            lookback_days: Days to look back for trend history
        """
        self.hot_threshold = hot_threshold
        self.lookback_days = lookback_days

    def extract_topics(self, articles: list[ProcessedArticle]) -> dict[str, list[ProcessedArticle]]:
        """
        Group articles by topic based on shared entities and keywords.

        Args:
            articles: List of processed articles

        Returns:
            Dictionary mapping topic names to related articles
        """
        # Collect all entities
        entity_articles: dict[str, list[ProcessedArticle]] = {}

        for article in articles:
            for entity in article.entities:
                entity_lower = entity.lower().strip()
                if len(entity_lower) < 3:  # Skip very short entities
                    continue
                if entity_lower not in entity_articles:
                    entity_articles[entity_lower] = []
                entity_articles[entity_lower].append(article)

        # Filter to topics with multiple articles
        topics = {
            topic: articles
            for topic, articles in entity_articles.items()
            if len(articles) >= 2
        }

        return topics

    def detect_hot_topics(
        self, articles: list[ProcessedArticle]
    ) -> list[TrendingTopic]:
        """
        Detect topics being covered by multiple sources.

        Args:
            articles: List of processed articles

        Returns:
            List of hot trending topics
        """
        topics = self.extract_topics(articles)
        hot_topics = []

        for topic_name, topic_articles in topics.items():
            # Count unique sources
            sources = list(set(a.source for a in topic_articles))

            if len(sources) >= self.hot_threshold:
                # This is a hot topic
                hot_topic = TrendingTopic(
                    topic=topic_name.title(),
                    status=TrendStatus.HOT,
                    article_count=len(topic_articles),
                    first_seen=min(
                        a.published_at or a.processed_at for a in topic_articles
                    ),
                    last_seen=max(
                        a.published_at or a.processed_at for a in topic_articles
                    ),
                    sources=sources,
                    related_articles=[a.url for a in topic_articles],
                    momentum=len(sources) / self.hot_threshold,  # Simple momentum
                )
                hot_topics.append(hot_topic)

        # Sort by source count (most covered first)
        hot_topics.sort(key=lambda t: len(t.sources), reverse=True)

        return hot_topics

    def analyze_trends(
        self, articles: list[ProcessedArticle]
    ) -> list[TrendingTopic]:
        """
        Full trend analysis comparing current articles to historical patterns.

        Args:
            articles: Current batch of processed articles

        Returns:
            List of all identified trends with status
        """
        # Get historical theme data from memory
        historical_themes = get_recent_themes(days=self.lookback_days)

        # Extract current topics
        topics = self.extract_topics(articles)
        trends = []

        for topic_name, topic_articles in topics.items():
            sources = list(set(a.source for a in topic_articles))

            # Calculate trend status based on history
            status = calculate_trend_status(
                topic_name,
                len(topic_articles),
                historical_themes,
            )

            # Override to HOT if multiple sources
            if len(sources) >= self.hot_threshold:
                status = TrendStatus.HOT

            # Calculate momentum
            momentum = self._calculate_momentum(topic_name, len(topic_articles), historical_themes)

            trend = TrendingTopic(
                topic=topic_name.title(),
                status=status,
                article_count=len(topic_articles),
                first_seen=min(a.published_at or a.processed_at for a in topic_articles),
                last_seen=max(a.published_at or a.processed_at for a in topic_articles),
                sources=sources,
                related_articles=[a.url for a in topic_articles],
                momentum=momentum,
            )
            trends.append(trend)

            # Store theme for future trend tracking
            store_theme(trend)

        # Sort by status priority and momentum
        status_priority = {
            TrendStatus.BREAKING: 0,
            TrendStatus.HOT: 1,
            TrendStatus.RISING: 2,
            TrendStatus.ESTABLISHED: 3,
            TrendStatus.FADING: 4,
        }
        trends.sort(key=lambda t: (status_priority[t.status], -t.momentum))

        logger.info(f"Identified {len(trends)} trending topics")
        return trends

    def _calculate_momentum(
        self,
        topic: str,
        current_count: int,
        history: list[dict],
    ) -> float:
        """
        Calculate momentum (rate of change) for a topic.

        Args:
            topic: Topic name
            current_count: Current article count
            history: Historical theme data

        Returns:
            Momentum value (positive = increasing, negative = decreasing)
        """
        # Find historical counts for this topic
        topic_history = [
            h for h in history if h.get("metadata", {}).get("topic", "").lower() == topic.lower()
        ]

        if not topic_history:
            return 0.0

        historical_counts = [h.get("metadata", {}).get("article_count", 0) for h in topic_history]
        avg_historical = sum(historical_counts) / len(historical_counts) if historical_counts else 0

        if avg_historical == 0:
            return float(current_count)

        # Momentum = (current - historical) / historical
        return (current_count - avg_historical) / avg_historical

    def get_emerging_themes(
        self, trends: list[TrendingTopic], limit: int = 3
    ) -> list[TrendingTopic]:
        """
        Get themes that are emerging (breaking or rising).

        Args:
            trends: List of all trends
            limit: Maximum number to return

        Returns:
            List of emerging trends
        """
        emerging = [
            t for t in trends if t.status in (TrendStatus.BREAKING, TrendStatus.RISING)
        ]
        return emerging[:limit]

    def get_summary_stats(
        self, articles: list[ProcessedArticle], trends: list[TrendingTopic]
    ) -> dict:
        """
        Get summary statistics for the current news cycle.

        Args:
            articles: Processed articles
            trends: Identified trends

        Returns:
            Dictionary of summary stats
        """
        source_counts = Counter(a.source for a in articles)
        category_counts = Counter(a.category.value for a in articles)

        return {
            "total_articles": len(articles),
            "unique_sources": len(source_counts),
            "top_sources": source_counts.most_common(5),
            "category_breakdown": dict(category_counts),
            "total_trends": len(trends),
            "hot_topics": len([t for t in trends if t.status == TrendStatus.HOT]),
            "emerging_topics": len(
                [t for t in trends if t.status in (TrendStatus.BREAKING, TrendStatus.RISING)]
            ),
        }
