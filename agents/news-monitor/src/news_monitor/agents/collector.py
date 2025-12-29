"""
RSS Collector Agent - Fetches articles from configured RSS feeds.

Uses feedparser to collect articles from multiple sources and performs
initial filtering for AI relevance.
"""

import logging
from datetime import UTC, datetime, timedelta

import feedparser
import httpx

from news_monitor.feeds import FeedConfig, get_enabled_feeds, is_ai_relevant
from news_monitor.models import RawArticle

logger = logging.getLogger(__name__)


class RSSCollectorAgent:
    """Agent for collecting articles from RSS feeds."""

    def __init__(self, max_age_hours: int = 24):
        """
        Initialize the collector.

        Args:
            max_age_hours: Maximum age of articles to collect (default: 24 hours)
        """
        self.max_age_hours = max_age_hours
        self.http_client = httpx.Client(timeout=30.0, follow_redirects=True)

    def collect_from_feed(self, feed: FeedConfig) -> list[RawArticle]:
        """
        Collect articles from a single RSS feed.

        Args:
            feed: The feed configuration

        Returns:
            List of raw articles from this feed
        """
        articles = []
        cutoff = datetime.now(UTC) - timedelta(hours=self.max_age_hours)

        try:
            logger.debug(f"Fetching feed: {feed.name}")
            response = self.http_client.get(feed.url)
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

                    article = RawArticle(
                        url=url,
                        title=title,
                        source=feed.name,
                        source_category=feed.category.value,
                        published_at=published_at,
                        summary=summary,
                        author=author,
                        tags=tags,
                    )
                    articles.append(article)

                except Exception as e:
                    logger.warning(f"Failed to parse entry from {feed.name}: {e}")
                    continue

            logger.info(f"Collected {len(articles)} articles from {feed.name}")

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching {feed.name}: {e}")
        except Exception as e:
            logger.error(f"Error fetching {feed.name}: {e}")

        return articles

    def collect_all(self, filter_ai_relevant: bool = True) -> list[RawArticle]:
        """
        Collect articles from all enabled feeds.

        Args:
            filter_ai_relevant: If True, filter general feeds for AI relevance

        Returns:
            List of all collected raw articles
        """
        all_articles = []
        feeds = get_enabled_feeds()

        logger.info(f"Collecting from {len(feeds)} feeds")

        for feed in feeds:
            articles = self.collect_from_feed(feed)

            # Filter general tech feeds for AI relevance
            if filter_ai_relevant and feed.category.value == "general_tech":
                original_count = len(articles)
                articles = [
                    a for a in articles if is_ai_relevant(a.title) or is_ai_relevant(a.summary)
                ]
                filtered_count = original_count - len(articles)
                if filtered_count > 0:
                    logger.debug(f"Filtered {filtered_count} non-AI articles from {feed.name}")

            all_articles.extend(articles)

        # Deduplicate by URL (same article from multiple feeds)
        seen_urls = set()
        unique_articles = []
        for article in all_articles:
            if article.url not in seen_urls:
                seen_urls.add(article.url)
                unique_articles.append(article)

        logger.info(
            f"Collected {len(unique_articles)} unique articles (from {len(all_articles)} total)"
        )

        return unique_articles

    def close(self):
        """Close the HTTP client."""
        self.http_client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
