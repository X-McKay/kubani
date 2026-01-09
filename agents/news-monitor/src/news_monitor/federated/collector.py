"""
News Collector Agent - Executes collection skills.

This federated agent handles:
- fetch-rss-feeds: Collect articles from RSS sources
- filter-duplicates: Remove already-processed articles

It uses the skill definitions for configuration and the existing
implementation code for actual execution.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from core_agents.skills import record_skill_outcome_to_registry
from news_monitor.agents.collector import RSSCollectorAgent
from news_monitor.federated.skills import get_news_skill
from news_monitor.memory import is_url_seen
from news_monitor.models import RawArticle

logger = logging.getLogger(__name__)


@dataclass
class CollectionResult:
    """Result from running collection skills."""

    articles: list[RawArticle] = field(default_factory=list)
    total_collected: int = 0
    seen_filtered: int = 0
    sources_fetched: int = 0
    failed_feeds: int = 0


class NewsCollectorAgent:
    """
    Federated agent that executes news collection skills.

    Skills used:
    - news/collection/fetch-rss-feeds
    - news/collection/filter-duplicates
    """

    def __init__(
        self,
        max_age_hours: int = 24,
        filter_ai_relevant: bool = True,
    ):
        """
        Initialize the collector agent.

        Args:
            max_age_hours: Maximum age of articles to collect
            filter_ai_relevant: Only include AI-relevant articles
        """
        self.max_age_hours = max_age_hours
        self.filter_ai_relevant = filter_ai_relevant
        self._skill_fetch = None
        self._skill_filter = None

    async def _load_skills(self) -> None:
        """Load skill definitions for configuration."""
        if self._skill_fetch is None:
            self._skill_fetch = await get_news_skill("news/collection/fetch-rss-feeds")
        if self._skill_filter is None:
            self._skill_filter = await get_news_skill("news/collection/filter-duplicates")

    async def collect(self) -> CollectionResult:
        """
        Execute the full collection pipeline.

        Steps (from fetch-rss-feeds skill):
        1. Load feed configuration
        2. Fetch each feed in parallel
        3. Filter by age
        4. Filter AI relevance
        5. Deduplicate by URL

        Then (from filter-duplicates skill):
        1. Check each URL against Redis
        2. Return only unseen articles
        """
        await self._load_skills()

        result = CollectionResult()

        # Step 1-5: Fetch and filter articles
        logger.info(f"Collecting articles (max_age={self.max_age_hours}h)")

        try:
            with RSSCollectorAgent(max_age_hours=self.max_age_hours) as collector:
                articles = collector.collect_all(filter_ai_relevant=self.filter_ai_relevant)
                result.total_collected = len(articles)
                result.sources_fetched = len(collector.get_successful_feeds())
                result.failed_feeds = len(collector.get_failed_feeds())
        except Exception as e:
            logger.error(f"Collection failed: {e}")
            return result

        logger.info(
            f"Collected {result.total_collected} articles from {result.sources_fetched} feeds"
        )

        # Step 6: Filter already-seen URLs (from filter-duplicates skill)
        unseen_articles = []
        for article in articles:
            if not is_url_seen(article.url):
                unseen_articles.append(article)
            else:
                result.seen_filtered += 1

        result.articles = unseen_articles

        logger.info(
            f"After filtering: {len(unseen_articles)} new, {result.seen_filtered} already seen"
        )

        # Record skill outcome to registry
        success = result.total_collected > 0 and result.failed_feeds == 0
        await record_skill_outcome_to_registry(
            skill_id="news/collection/fetch-rss-feeds",
            success=success,
            skill_name="Fetch RSS Feeds",
            domain="news",
            category="collection",
        )

        return result

    async def collect_as_dicts(self) -> list[dict[str, Any]]:
        """
        Collect articles and return as serializable dicts.

        Convenience method for Temporal activities.
        """
        result = await self.collect()
        return [article.model_dump() for article in result.articles]


async def run_collection(
    max_age_hours: int = 24,
    filter_ai_relevant: bool = True,
) -> CollectionResult:
    """
    Run the collection pipeline.

    Args:
        max_age_hours: Maximum article age
        filter_ai_relevant: Filter for AI-relevant content

    Returns:
        CollectionResult with articles and stats
    """
    collector = NewsCollectorAgent(
        max_age_hours=max_age_hours,
        filter_ai_relevant=filter_ai_relevant,
    )
    return await collector.collect()
