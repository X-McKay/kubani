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
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from agents._base import KubaniAgent
from agents.feed_collector.feeds import (
    FeedConfig,
    get_enabled_feeds,
    is_ai_relevant,
)

logger = logging.getLogger(__name__)


@dataclass
class RawArticle:
    """Raw article from RSS feed."""

    title: str
    url: str
    source: str
    published_date: str
    summary: str = ""
    author: str | None = None
    tags: list[str] = field(default_factory=list)
    source_category: str = ""


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

        # HTTP client will be created lazily
        self._http_client = None

    def _get_http_client(self):
        """Get or create HTTP client."""
        if self._http_client is None:
            import httpx

            self._http_client = httpx.Client(timeout=30.0, follow_redirects=True)
        return self._http_client

    def _collect_from_feed(self, feed: FeedConfig) -> list[RawArticle]:
        """
        Collect articles from a single RSS feed.

        Args:
            feed: The feed configuration

        Returns:
            List of raw articles from this feed
        """
        import feedparser

        articles = []
        cutoff = datetime.now(UTC) - timedelta(hours=self.max_age_hours)

        try:
            logger.debug(f"Fetching feed: {feed.name}")
            client = self._get_http_client()
            response = client.get(feed.url)
            response.raise_for_status()

            parsed = feedparser.parse(response.text)

            if parsed.bozo and parsed.bozo_exception:
                logger.warning(f"Feed parse warning for {feed.name}: {parsed.bozo_exception}")

            for entry in parsed.entries:
                try:
                    # Parse published date
                    published_at = None
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        published_at = datetime(*entry.published_parsed[:6], tzinfo=UTC)
                    elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                        published_at = datetime(*entry.updated_parsed[:6], tzinfo=UTC)

                    # Skip old articles
                    if published_at and published_at < cutoff:
                        continue

                    # Get URL
                    url = entry.get("link", "")
                    if not url:
                        continue

                    # Get title and summary
                    title = entry.get("title", "").strip()
                    summary = entry.get("summary", entry.get("description", "")).strip()

                    # Skip if no title
                    if not title:
                        continue

                    # Get author
                    author = entry.get("author", None)

                    # Get tags
                    tags = []
                    if hasattr(entry, "tags"):
                        tags = [tag.get("term", "") for tag in entry.tags if tag.get("term")]

                    # Format published date as ISO string
                    published_date_str = published_at.isoformat() if published_at else ""

                    article = RawArticle(
                        url=url,
                        title=title,
                        source=feed.name,
                        source_category=feed.category.value,
                        published_date=published_date_str,
                        summary=summary,
                        author=author,
                        tags=tags,
                    )
                    articles.append(article)

                except Exception as e:
                    logger.warning(f"Failed to parse entry from {feed.name}: {e}")
                    continue

            logger.info(f"Collected {len(articles)} articles from {feed.name}")

        except Exception as e:
            logger.error(f"Error fetching {feed.name}: {e}")

        return articles

    async def collect(self) -> CollectionResult:
        """
        Execute the full collection pipeline.

        Steps:
        1. Load feed configuration
        2. Fetch each feed
        3. Filter by age
        4. Filter AI relevance
        5. Deduplicate by URL

        Returns:
            CollectionResult with articles and stats
        """
        result = CollectionResult()

        logger.info(f"Collecting articles (max_age={self.max_age_hours}h)")

        feeds = get_enabled_feeds()
        all_articles = []
        failed_feeds = 0

        logger.info(f"Collecting from {len(feeds)} feeds")

        for feed in feeds:
            try:
                articles = self._collect_from_feed(feed)
                result.sources_fetched += 1

                # Filter general tech feeds for AI relevance
                if self.filter_ai_relevant and feed.category.value == "general_tech":
                    original_count = len(articles)
                    articles = [
                        a for a in articles if is_ai_relevant(a.title) or is_ai_relevant(a.summary)
                    ]
                    filtered_count = original_count - len(articles)
                    if filtered_count > 0:
                        logger.debug(f"Filtered {filtered_count} non-AI articles from {feed.name}")

                all_articles.extend(articles)
            except Exception as e:
                logger.error(f"Failed to collect from {feed.name}: {e}")
                failed_feeds += 1

        # Deduplicate by URL (same article from multiple feeds)
        seen_urls: set[str] = set()
        unique_articles = []
        for article in all_articles:
            if article.url not in seen_urls:
                seen_urls.add(article.url)
                unique_articles.append(article)

        result.articles = unique_articles
        result.total_collected = len(unique_articles)
        result.seen_filtered = len(all_articles) - len(unique_articles)
        result.failed_feeds = failed_feeds

        logger.info(
            f"Collected {result.total_collected} unique articles "
            f"(from {len(all_articles)} total, {result.sources_fetched} feeds)"
        )

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
                "author": a.author,
                "tags": a.tags,
                "source_category": a.source_category,
            }
            for a in result.articles
        ]

    async def on_skill_complete(self, skill_name: str, result: dict[str, Any]) -> None:
        """Record skill outcomes for learning."""
        success = result.get("total_collected", 0) > 0
        await self.record_outcome(skill_name, result, success=success)

    def close(self):
        """Close HTTP client."""
        if self._http_client:
            self._http_client.close()
            self._http_client = None

    def __del__(self):
        """Cleanup on deletion."""
        self.close()
