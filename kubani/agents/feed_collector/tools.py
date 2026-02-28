"""Feed collection tools for the FeedCollectorAgent.

Provides RSS feed fetching via feedparser + httpx. The core logic lives in
``fetch_feeds()`` which can be called directly (used by collect_feeds_activity)
or via the Strands @tool wrapper (used by FeedCollectorAgent).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

import feedparser
import httpx
from strands import tool

from kubani.agents.feed_collector.feeds import FeedConfig

logger = logging.getLogger(__name__)

# Timeout per feed in seconds
FEED_TIMEOUT = 15.0
# Max entries per feed (no cap on total — callers decide)
MAX_ENTRIES_PER_FEED = 50
MAX_SUMMARY_LENGTH = 200


def _parse_entry_date(entry: Any) -> str:
    """Extract an ISO-8601 date string from a feedparser entry."""
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            return datetime(*entry.published_parsed[:6], tzinfo=UTC).isoformat()
        except Exception:
            return entry.get("published", "")
    if hasattr(entry, "updated_parsed") and entry.updated_parsed:
        try:
            return datetime(*entry.updated_parsed[:6], tzinfo=UTC).isoformat()
        except Exception:
            return entry.get("updated", "")
    return ""


async def fetch_feeds(
    feeds: list[FeedConfig],
    max_entries_per_feed: int = MAX_ENTRIES_PER_FEED,
) -> tuple[list[dict[str, Any]], int, int]:
    """Fetch and parse RSS/Atom feeds.

    This is the core fetch function used by both the Temporal activity
    (directly) and the Strands tool wrapper.

    Args:
        feeds: List of FeedConfig objects to fetch.
        max_entries_per_feed: Cap entries per individual feed.

    Returns:
        Tuple of (entries, sources_fetched, failed_feeds).
    """
    all_entries: list[dict[str, Any]] = []
    sources_fetched = 0
    failed_feeds = 0

    async with httpx.AsyncClient(
        timeout=FEED_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": "Kubani-NewsMonitor/1.0 (+https://github.com/X-McKay/kubani)"},
    ) as client:
        for feed in feeds:
            if not feed.url:
                failed_feeds += 1
                continue

            try:
                response = await client.get(feed.url)
                response.raise_for_status()

                parsed = feedparser.parse(response.text)

                if parsed.bozo and not parsed.entries:
                    logger.warning(f"Feed parse error for {feed.name}: {parsed.bozo_exception}")
                    failed_feeds += 1
                    continue

                for entry in parsed.entries[:max_entries_per_feed]:
                    all_entries.append(
                        {
                            "title": entry.get("title", "").strip(),
                            "url": entry.get("link", "").strip(),
                            "source": feed.name,
                            "published_date": _parse_entry_date(entry),
                            "summary": (entry.get("summary", "") or "").strip()[
                                :MAX_SUMMARY_LENGTH
                            ],
                            "author": entry.get("author"),
                            "source_category": feed.category.value
                            if hasattr(feed.category, "value")
                            else str(feed.category),
                        }
                    )

                sources_fetched += 1
                logger.info(
                    f"Fetched {min(len(parsed.entries), max_entries_per_feed)} entries from {feed.name}"
                )

            except httpx.HTTPStatusError as e:
                logger.warning(f"HTTP {e.response.status_code} fetching {feed.name}: {feed.url}")
                failed_feeds += 1
            except httpx.TimeoutException:
                logger.warning(f"Timeout fetching {feed.name}: {feed.url}")
                failed_feeds += 1
            except Exception as e:
                logger.warning(f"Error fetching {feed.name}: {e}")
                failed_feeds += 1

    return all_entries, sources_fetched, failed_feeds


def create_feed_tools() -> list:
    """Create feed collection tools for the Strands agent.

    Returns:
        List of Strands @tool instances.
    """

    @tool
    async def fetch_all_feeds(feeds_json: str) -> str:
        """Fetch and parse multiple RSS/Atom feeds concurrently.

        Args:
            feeds_json: JSON array of feed objects, each with "name", "url", "category".

        Returns:
            JSON with "entries" array and "stats" object.
        """
        try:
            raw_feeds = json.loads(feeds_json)
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid feeds JSON: {e}", "entries": [], "stats": {}})

        # Convert dicts to FeedConfig for the shared function
        configs = [
            FeedConfig(
                name=f.get("name", "Unknown"),
                url=f.get("url", ""),
                category=f.get("category", "general"),
            )
            for f in raw_feeds
        ]

        entries, sources_fetched, failed = await fetch_feeds(configs, max_entries_per_feed=5)

        # Cap for LLM context
        entries = entries[:75]

        result = {
            "entries": entries,
            "stats": {
                "total_entries": len(entries),
                "sources_fetched": sources_fetched,
                "failed_feeds": failed,
            },
        }
        return json.dumps(result, default=str)

    return [fetch_all_feeds]
