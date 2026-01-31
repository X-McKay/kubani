"""
Feed Collector Agent - Skills-centric RSS feed collection.

Thin orchestrator that delegates to collection skills:
- fetch-rss-feeds: Fetch articles from RSS/Atom feeds
- filter-ai-relevant: Filter for AI/ML relevance
- deduplicate-articles: Remove duplicates using Redis

Usage:
    from kubani.agents.feed_collector import FeedCollectorAgent

    agent = FeedCollectorAgent()
    result = await agent.collect(max_age_hours=24)
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kubani.agents._base import SkillsOrchestrator

from .feeds import get_enabled_feeds

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


class FeedCollectorAgent(SkillsOrchestrator):
    """
    Skills-centric feed collector.

    Discovers and delegates to news/collection skills:
    - fetch-rss-feeds
    - filter-ai-relevant
    - deduplicate-articles
    """

    AGENT_DIR = Path(__file__).parent
    SKILLS_DOMAIN = "news"
    SKILLS_CATEGORY = "collection"

    def __init__(self, agent_dir: Path | None = None):
        """Initialize the Feed Collector agent."""
        super().__init__(agent_dir)

        # Collector-specific configuration
        collector_config = self.config.get("collector", {})
        self.default_max_age_hours = collector_config.get("max_age_hours", 24)
        self.default_filter_ai = collector_config.get("filter_ai_relevant", True)

    async def collect(
        self,
        max_age_hours: int | None = None,
        filter_ai_relevant: bool | None = None,
    ) -> CollectionResult:
        """
        Collect articles from RSS feeds using skills.

        Args:
            max_age_hours: Maximum article age (default from config)
            filter_ai_relevant: Whether to filter for AI relevance

        Returns:
            CollectionResult with articles and stats
        """
        max_age = max_age_hours or self.default_max_age_hours
        filter_ai = filter_ai_relevant if filter_ai_relevant is not None else self.default_filter_ai

        # Get feed configuration
        feeds = get_enabled_feeds()
        feeds_info = [
            {"name": f.name, "url": f.url, "category": f.category.value}
            for f in feeds
        ]

        # Generate task prompt
        task_prompt = self._get_task_prompt(
            feeds=feeds_info,
            max_age_hours=max_age,
            filter_ai_relevant=filter_ai,
        )

        # Delegate to LLM with skills
        try:
            response = await self.run(task_prompt)
            result = self._parse_collection_result(response)
            await self.on_skill_complete("collect", {"total": result.total_collected})
            return result
        except Exception as e:
            logger.error(f"Collection failed: {e}")
            await self.on_error(e, {"task": "collect"})
            return CollectionResult()

    def _get_task_prompt(
        self,
        feeds: list[dict],
        max_age_hours: int,
        filter_ai_relevant: bool,
    ) -> str:
        """Generate task prompt for collection."""
        feeds_json = json.dumps(feeds[:5], indent=2)  # Show sample feeds

        return f"""Collect articles from RSS feeds.

## Task Parameters
- Maximum article age: {max_age_hours} hours
- Filter for AI relevance: {filter_ai_relevant}
- Total feeds to process: {len(feeds)}

## Sample Feeds (first 5)
```json
{feeds_json}
```

## Instructions

Use the available skills to:

1. **Fetch RSS feeds** using the fetch-rss-feeds skill
   - Process all {len(feeds)} configured feeds
   - Extract title, URL, source, published_date, summary from each entry
   - Handle feed errors gracefully (log and continue)

2. **Filter by age**
   - Skip articles older than {max_age_hours} hours

3. **Filter AI relevance** (if enabled: {filter_ai_relevant})
   - Use the filter-ai-relevant skill for general_tech category feeds
   - Keep all articles from ai_focused, company_blogs, research categories

4. **Deduplicate articles** using the deduplicate-articles skill
   - Remove duplicates by URL within this run
   - Mark URLs as seen for future runs (7-day TTL)

## Output Format

Return a JSON object:
```json
{{
  "articles": [
    {{
      "title": "Article title",
      "url": "https://...",
      "source": "Feed name",
      "published_date": "ISO datetime",
      "summary": "Article summary",
      "author": "Author name or null",
      "tags": ["tag1", "tag2"],
      "source_category": "ai_focused"
    }}
  ],
  "stats": {{
    "total_collected": 42,
    "seen_filtered": 10,
    "sources_fetched": 18,
    "failed_feeds": 2
  }}
}}
```

Read the SKILL.md files for detailed instructions on each skill."""

    def _parse_collection_result(self, response: str) -> CollectionResult:
        """Parse LLM response into CollectionResult."""
        try:
            # Try to extract JSON from response
            data = self._extract_json(response)

            articles = [
                RawArticle(
                    title=a.get("title", ""),
                    url=a.get("url", ""),
                    source=a.get("source", ""),
                    published_date=a.get("published_date", ""),
                    summary=a.get("summary", ""),
                    author=a.get("author"),
                    tags=a.get("tags", []),
                    source_category=a.get("source_category", ""),
                )
                for a in data.get("articles", [])
            ]

            stats = data.get("stats", {})

            return CollectionResult(
                articles=articles,
                total_collected=stats.get("total_collected", len(articles)),
                seen_filtered=stats.get("seen_filtered", 0),
                sources_fetched=stats.get("sources_fetched", 0),
                failed_feeds=stats.get("failed_feeds", 0),
            )
        except Exception as e:
            logger.warning(f"Failed to parse collection result: {e}")
            return CollectionResult()

    async def collect_as_dicts(self) -> list[dict[str, Any]]:
        """Collect articles and return as serializable dicts."""
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
        success = result.get("total", 0) > 0
        await self.record_outcome(skill_name, result, success=success)
