"""Feed collection tools for the FeedCollectorAgent.

Provides @tool functions that use feedparser + httpx to fetch real RSS feeds.
These are passed to the Strands Agent so the LLM can actually fetch data.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import feedparser
import httpx
from strands import tool

logger = logging.getLogger(__name__)

# Timeout per feed in seconds
FEED_TIMEOUT = 15.0
# Limits to keep tool output within LLM context window (~32k tokens)
MAX_ENTRIES_PER_FEED = 5
MAX_SUMMARY_LENGTH = 200
MAX_TOTAL_ENTRIES = 75


def create_feed_tools() -> list:
    """Create feed collection tools for the agent.

    Returns:
        List of Strands @tool instances.
    """

    @tool
    async def fetch_all_feeds(feeds_json: str) -> str:
        """Fetch and parse multiple RSS/Atom feeds concurrently.

        Fetches all feeds in parallel using httpx, parses them with feedparser,
        and returns structured entries. Handles individual feed failures gracefully.

        Args:
            feeds_json: JSON array of feed objects, each with "name", "url", "category".

        Returns:
            JSON with "entries" array and "stats" object.
        """
        try:
            feeds = json.loads(feeds_json)
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid feeds JSON: {e}", "entries": [], "stats": {}})

        all_entries = []
        sources_fetched = 0
        failed_feeds = 0

        async with httpx.AsyncClient(
            timeout=FEED_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "Kubani-NewsMonitor/0.9 (+https://github.com/X-McKay/kubani)"},
        ) as client:
            for feed_info in feeds:
                name = feed_info.get("name", "Unknown")
                url = feed_info.get("url", "")
                category = feed_info.get("category", "general")

                if not url:
                    failed_feeds += 1
                    continue

                try:
                    response = await client.get(url)
                    response.raise_for_status()

                    parsed = feedparser.parse(response.text)

                    if parsed.bozo and not parsed.entries:
                        logger.warning(f"Feed parse error for {name}: {parsed.bozo_exception}")
                        failed_feeds += 1
                        continue

                    for entry in parsed.entries[:MAX_ENTRIES_PER_FEED]:
                        # Parse published date
                        published = ""
                        if hasattr(entry, "published_parsed") and entry.published_parsed:
                            try:
                                dt = datetime(*entry.published_parsed[:6], tzinfo=UTC)
                                published = dt.isoformat()
                            except Exception:
                                published = entry.get("published", "")
                        elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                            try:
                                dt = datetime(*entry.updated_parsed[:6], tzinfo=UTC)
                                published = dt.isoformat()
                            except Exception:
                                published = entry.get("updated", "")

                        all_entries.append(
                            {
                                "title": entry.get("title", "").strip(),
                                "url": entry.get("link", "").strip(),
                                "source": name,
                                "published_date": published,
                                "summary": (entry.get("summary", "") or "").strip()[
                                    :MAX_SUMMARY_LENGTH
                                ],
                                "author": entry.get("author"),
                                "source_category": category,
                            }
                        )

                    sources_fetched += 1
                    logger.info(f"Fetched {len(parsed.entries)} entries from {name}")

                except httpx.HTTPStatusError as e:
                    logger.warning(f"HTTP {e.response.status_code} fetching {name}: {url}")
                    failed_feeds += 1
                except httpx.TimeoutException:
                    logger.warning(f"Timeout fetching {name}: {url}")
                    failed_feeds += 1
                except Exception as e:
                    logger.warning(f"Error fetching {name}: {e}")
                    failed_feeds += 1

        # Cap total entries to stay within context limits
        if len(all_entries) > MAX_TOTAL_ENTRIES:
            all_entries = all_entries[:MAX_TOTAL_ENTRIES]

        result = {
            "entries": all_entries,
            "stats": {
                "total_entries": len(all_entries),
                "sources_fetched": sources_fetched,
                "failed_feeds": failed_feeds,
            },
        }
        return json.dumps(result, default=str)

    return [fetch_all_feeds]
