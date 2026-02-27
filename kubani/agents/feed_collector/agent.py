"""
Feed Collector Agent - RSS feed collection with real HTTP tools.

Uses a Strands Agent with a `fetch_all_feeds` tool (feedparser + httpx)
so the LLM can actually fetch RSS data. The LLM orchestrates the collection:
calls the tool, filters results by age/relevance, and returns structured output.

Usage:
    from kubani.agents.feed_collector import FeedCollectorAgent

    agent = FeedCollectorAgent()
    result = await agent.collect(max_age_hours=24)
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from kubani.agents._base import SkillsOrchestrator

from .feeds import get_enabled_feeds

if TYPE_CHECKING:
    from strands import Agent

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
    Feed collector with real RSS fetching tools.

    Provides a `fetch_all_feeds` Strands tool that uses feedparser + httpx
    to fetch real RSS data. The LLM calls this tool, then filters and
    formats the results.
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

    def get_additional_tools(self) -> list[Any]:
        """Provide RSS fetching tools for the agent."""
        from .tools import create_feed_tools

        return create_feed_tools()

    def _create_agent(self) -> "Agent":
        """Create Strands Agent with feed tools wired in."""
        from strands import Agent
        from strands.models.openai import OpenAIModel

        from kubani.framework.config import get_config

        config = get_config()
        max_tokens = self.limits.get("max_tokens", config.llm.max_tokens)

        model = OpenAIModel(
            client_args={
                "api_key": "not-needed",
                "base_url": config.llm.api_url,
            },
            model_id=config.llm.model,
            params={"max_tokens": max_tokens},
        )

        tools = self.get_additional_tools()

        return Agent(
            model=model,
            system_prompt=self.prompt,
            tools=tools,
        )

    async def collect(
        self,
        max_age_hours: int | None = None,
        filter_ai_relevant: bool | None = None,
    ) -> CollectionResult:
        """
        Collect articles from RSS feeds.

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
        feeds_info = [{"name": f.name, "url": f.url, "category": f.category.value} for f in feeds]

        # Generate task prompt
        task_prompt = self._get_task_prompt(
            feeds=feeds_info,
            max_age_hours=max_age,
            filter_ai_relevant=filter_ai,
        )

        # Delegate to LLM with tools
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
        feeds_json = json.dumps(feeds)

        return f"""Collect articles from {len(feeds)} RSS feeds.

## Step 1: Fetch all feeds

Call the `fetch_all_feeds` tool with this feeds_json argument:

{feeds_json}

## Step 2: Filter the results

From the tool results, keep only articles that:
- Have a published_date within the last {max_age_hours} hours (compare to current time)
- Have a non-empty title and url
{"- Are relevant to AI/ML (mentions AI, LLM, machine learning, neural network, GPT, Claude, etc.)" if filter_ai_relevant else ""}

## Step 3: Return JSON

Return ONLY a JSON object (no markdown, no explanation):
{{
  "articles": [
    {{
      "title": "...",
      "url": "...",
      "source": "...",
      "published_date": "...",
      "summary": "...",
      "author": "..." or null,
      "tags": [],
      "source_category": "..."
    }}
  ],
  "stats": {{
    "total_collected": <number of articles after filtering>,
    "seen_filtered": 0,
    "sources_fetched": <from tool stats>,
    "failed_feeds": <from tool stats>
  }}
}}"""

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
