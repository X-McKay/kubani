"""
Trend Analyzer Agent - Identifies patterns and emerging themes.

Responsible for:
- Detecting hot topics (multiple sources covering same story)
- Tracking topic momentum over time
- Identifying emerging vs fading themes
- Using graph memory to track entity relationships across articles
- Finding related topics via shared entity mentions
"""

import logging
from collections import Counter
from typing import Any

from news_monitor.memory import (
    _extract_search_results,
    calculate_trend_status,
    get_memory,
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
            topic: articles for topic, articles in entity_articles.items() if len(articles) >= 2
        }

        return topics

    def detect_hot_topics(self, articles: list[ProcessedArticle]) -> list[TrendingTopic]:
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
            sources = list({a.source for a in topic_articles})

            if len(sources) >= self.hot_threshold:
                # This is a hot topic
                hot_topic = TrendingTopic(
                    topic=topic_name.title(),
                    status=TrendStatus.HOT,
                    article_count=len(topic_articles),
                    first_seen=min(a.published_at or a.processed_at for a in topic_articles),
                    last_seen=max(a.published_at or a.processed_at for a in topic_articles),
                    sources=sources,
                    related_articles=[a.url for a in topic_articles],
                    momentum=len(sources) / self.hot_threshold,  # Simple momentum
                )
                hot_topics.append(hot_topic)

        # Sort by source count (most covered first)
        hot_topics.sort(key=lambda t: len(t.sources), reverse=True)

        return hot_topics

    def analyze_trends(self, articles: list[ProcessedArticle]) -> list[TrendingTopic]:
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
            sources = list({a.source for a in topic_articles})

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
        emerging = [t for t in trends if t.status in (TrendStatus.BREAKING, TrendStatus.RISING)]
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

    # --- Graph-Enhanced Methods ---

    def get_entity_clusters(self, articles: list[ProcessedArticle]) -> list[dict[str, Any]]:
        """
        Find entity clusters across articles using graph relationships.

        Uses the graph memory to identify entities that frequently appear
        together, indicating related concepts or stories.

        Args:
            articles: List of processed articles

        Returns:
            List of entity clusters with their article counts
        """
        # Build entity co-occurrence from current batch
        entity_cooccurrence: dict[tuple[str, str], int] = {}
        entity_counts: dict[str, int] = Counter()

        for article in articles:
            entities = [e.lower().strip() for e in article.entities if len(e) >= 3]
            entity_counts.update(entities)

            # Track which entities appear together
            for i, e1 in enumerate(entities):
                for e2 in entities[i + 1 :]:
                    pair = tuple(sorted([e1, e2]))
                    entity_cooccurrence[pair] = entity_cooccurrence.get(pair, 0) + 1

        # Find strongly co-occurring entities (clusters)
        clusters = []
        seen_entities: set[str] = set()

        for (e1, e2), count in sorted(
            entity_cooccurrence.items(), key=lambda x: x[1], reverse=True
        ):
            if count >= 2 and e1 not in seen_entities and e2 not in seen_entities:
                cluster = {
                    "entities": [e1.title(), e2.title()],
                    "cooccurrence_count": count,
                    "total_mentions": entity_counts[e1] + entity_counts[e2],
                }
                clusters.append(cluster)
                seen_entities.add(e1)
                seen_entities.add(e2)

        logger.debug(f"Found {len(clusters)} entity clusters")
        return clusters[:10]  # Top 10 clusters

    def find_related_topics(self, topic: str, limit: int = 5) -> list[str]:
        """
        Find topics related to the given topic via shared entities.

        Uses graph memory to find other topics that share entity mentions,
        indicating thematic connections.

        Args:
            topic: The topic to find relations for
            limit: Maximum number of related topics to return

        Returns:
            List of related topic names
        """
        try:
            memory = get_memory()

            # Search for articles mentioning this topic
            raw_results = memory.search(
                topic,
                user_id="news-monitor-articles",
                limit=20,
            )

            # Collect entities from related articles
            related_entities: Counter = Counter()
            for result in _extract_search_results(raw_results):
                # Look for entities in the stored content
                content = result.get("memory", "")
                if "Entities:" in content:
                    entities_part = content.split("Entities:")[-1].strip()
                    for entity in entities_part.split(","):
                        entity = entity.strip().lower()
                        if entity and entity != topic.lower() and len(entity) >= 3:
                            related_entities[entity] += 1

            # The most common related entities become related topics
            related_topics = [entity.title() for entity, _ in related_entities.most_common(limit)]

            logger.debug(f"Found {len(related_topics)} topics related to '{topic}'")
            return related_topics

        except Exception as e:
            logger.error(f"Failed to find related topics: {e}")
            return []

    def get_topic_evolution(self, topic: str, days: int = 7) -> list[dict[str, Any]]:
        """
        Trace how a topic has evolved over time using graph history.

        Args:
            topic: The topic to trace
            days: Number of days to look back

        Returns:
            List of historical snapshots showing topic evolution
        """
        try:
            # Get historical themes for this topic
            all_themes = get_recent_themes(days=days)

            topic_history = [
                {
                    "date": h.get("metadata", {}).get("last_seen", ""),
                    "status": h.get("metadata", {}).get("status", ""),
                    "article_count": h.get("metadata", {}).get("article_count", 0),
                    "momentum": h.get("metadata", {}).get("momentum", 0),
                }
                for h in all_themes
                if h.get("metadata", {}).get("topic", "").lower() == topic.lower()
            ]

            # Sort by date
            topic_history.sort(key=lambda x: x["date"])

            logger.debug(f"Found {len(topic_history)} historical snapshots for '{topic}'")
            return topic_history

        except Exception as e:
            logger.error(f"Failed to get topic evolution: {e}")
            return []

    def detect_cross_topic_themes(self, trends: list[TrendingTopic]) -> list[dict[str, Any]]:
        """
        Identify broader themes that span multiple trending topics.

        Uses entity overlap to find meta-themes connecting different topics.

        Args:
            trends: List of identified trends

        Returns:
            List of cross-topic themes with their constituent topics
        """
        # Group topics by shared high-level entities
        # (companies, technologies, etc.)
        topic_entities: dict[str, set[str]] = {}

        for trend in trends:
            # Collect related articles' entities
            topic_entities[trend.topic] = set()
            for _url in trend.related_articles[:5]:  # Sample first 5
                # The entities would come from the articles
                # For now, use the topic itself as a proxy
                topic_entities[trend.topic].add(trend.topic.lower())

        # Find topics with overlapping entities
        cross_themes = []
        seen_pairs: set[tuple[str, str]] = set()

        for t1 in trends:
            for t2 in trends:
                if t1.topic >= t2.topic:
                    continue
                pair = (t1.topic, t2.topic)
                if pair in seen_pairs:
                    continue

                # Check for entity overlap (simplified - use topics themselves)
                overlap = topic_entities[t1.topic] & topic_entities[t2.topic]
                if len(overlap) > 0:
                    cross_themes.append(
                        {
                            "theme": f"{t1.topic} + {t2.topic}",
                            "topics": [t1.topic, t2.topic],
                            "shared_entities": list(overlap),
                            "combined_articles": t1.article_count + t2.article_count,
                        }
                    )
                    seen_pairs.add(pair)

        logger.debug(f"Found {len(cross_themes)} cross-topic themes")
        return cross_themes[:5]  # Top 5 cross-themes
