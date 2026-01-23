"""
Feed Collector Agent - Collects content from data feeds.

Fetches content from feeds (RSS, APIs, webhooks), filters by age
and relevance, and deduplicates. Can be used for any feed-based collection.

Usage:
    from agents.feed_collector import FeedCollectorAgent

    agent = FeedCollectorAgent()
    result = await agent.collect()
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agents._base import KubaniAgent

logger = logging.getLogger(__name__)


@dataclass
class RawArticle:
    """Raw article from RSS feed."""

    title: str
    url: str
    source: str
    published_date: str
    summary: str = ""


@dataclass
class CollectionResult:
    """Result from running collection."""

    articles: list[RawArticle] = field(default_factory=list)
    total_collected: int = 0
    seen_filtered: int = 0
    sources_fetched: int = 0
    failed_feeds: int = 0


class FeedCollectorAgent(KubaniAgent):
    """
    Collects content from data feeds.

    Fetches content, filters by age and relevance, and deduplicates.
    """

    AGENT_DIR = Path(__file__).parent

    def __init__(self, agent_dir: Path | None = None):
        """Initialize the Feed Collector agent."""
        super().__init__(agent_dir)

        # Collector-specific configuration
        collector_config = self.config.get("collector", {})
        self.max_age_hours = collector_config.get("max_age_hours", 24)
        self.filter_ai_relevant = collector_config.get("filter_ai_relevant", True)

    async def collect(self) -> CollectionResult:
        """
        Execute the full collection pipeline.

        Steps:
        1. Load feed configuration
        2. Fetch each feed in parallel
        3. Filter by age
        4. Filter AI relevance
        5. Deduplicate by URL

        Returns:
            CollectionResult with articles and stats
        """
        result = CollectionResult()

        logger.info(f"Collecting articles (max_age={self.max_age_hours}h)")

        # This would use the actual RSS collection implementation
        # For now, return empty result - actual implementation would
        # call the news/collection/fetch-rss-feeds skill

        return result

    async def collect_as_dicts(self) -> list[dict[str, Any]]:
        """
        Collect articles and return as serializable dicts.

        Convenience method for Temporal activities.
        """
        result = await self.collect()
        return [
            {
                "title": a.title,
                "url": a.url,
                "source": a.source,
                "published_date": a.published_date,
                "summary": a.summary,
            }
            for a in result.articles
        ]

    async def on_skill_complete(self, skill_name: str, result: dict[str, Any]) -> None:
        """Record skill outcomes for learning."""
        success = result.get("total_collected", 0) > 0
        await self.record_outcome(skill_name, result, success=success)
