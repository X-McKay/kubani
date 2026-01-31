"""
Content Analyst Agent - Skills-centric article analysis.

Thin orchestrator that delegates to analysis skills:
- analyze-article: Extract insights, entities, importance
- detect-trends: Identify trending topics
- identify-breaking-news: Flag breaking stories

Usage:
    from kubani.agents.content_analyst import ContentAnalystAgent

    agent = ContentAnalystAgent()
    result = await agent.full_analysis(articles)
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kubani.agents._base import SkillsOrchestrator

logger = logging.getLogger(__name__)


@dataclass
class ProcessedArticle:
    """Article after LLM analysis."""

    url: str
    title: str
    source: str
    source_category: str
    published_at: datetime | None
    original_summary: str
    ai_summary: str
    category: str
    entities: list[str]
    importance_score: int
    is_breaking: bool
    breaking_reason: str | None
    content_hash: str
    processed_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class TrendingTopic:
    """Topic trending across multiple sources."""

    entity: str
    article_count: int
    sources: list[str]
    status: str  # HOT, RISING, STABLE
    momentum: float


@dataclass
class AnalysisResult:
    """Result from full analysis."""

    processed_articles: list[ProcessedArticle] = field(default_factory=list)
    breaking_articles: list[ProcessedArticle] = field(default_factory=list)
    trends: list[TrendingTopic] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)


class ContentAnalystAgent(SkillsOrchestrator):
    """
    Skills-centric content analyst.

    Discovers and delegates to news/analysis skills:
    - analyze-article
    - detect-trends
    - identify-breaking-news
    """

    AGENT_DIR = Path(__file__).parent
    SKILLS_DOMAIN = "news"
    SKILLS_CATEGORY = "analysis"

    def __init__(self, agent_dir: Path | None = None):
        """Initialize the Content Analyst agent."""
        super().__init__(agent_dir)

        # Analyst-specific configuration
        analyst_config = self.config.get("analyst", {})
        self.min_importance = analyst_config.get("min_breaking_importance", 8)
        self.max_workers = analyst_config.get("max_workers", 8)

    async def analyze_articles(self, articles: list[dict]) -> list[ProcessedArticle]:
        """Analyze articles using analyze-article skill."""
        if not articles:
            return []

        task_prompt = f"""Analyze these {len(articles)} articles.

Use the analyze-article skill to:
1. Generate concise summaries
2. Categorize by topic (research, business, product, security, policy)
3. Extract key entities
4. Assign importance scores (1-10)
5. Flag breaking news

Articles to analyze:
```json
{json.dumps(articles[:10], indent=2)}
```
{"..." if len(articles) > 10 else ""}

Return JSON array of processed articles with fields:
url, title, source, source_category, original_summary, ai_summary, category,
entities, importance_score, is_breaking, breaking_reason, content_hash"""

        response = await self.run(task_prompt)
        return self._parse_processed_articles(response)

    async def detect_breaking_news(
        self, articles: list[ProcessedArticle]
    ) -> list[ProcessedArticle]:
        """Filter breaking news using identify-breaking-news skill."""
        if not articles:
            return []

        articles_data = [
            {
                "url": a.url,
                "title": a.title,
                "source": a.source,
                "importance_score": a.importance_score,
                "is_breaking": a.is_breaking,
                "breaking_reason": a.breaking_reason,
            }
            for a in articles[:20]
        ]

        task_prompt = f"""Identify breaking news from these analyzed articles.

Use the identify-breaking-news skill to filter articles that:
- Have importance_score >= {self.min_importance}
- Are flagged as is_breaking = true
- Represent major announcements or events

Articles:
```json
{json.dumps(articles_data, indent=2)}
```

Return JSON array of breaking articles only."""

        response = await self.run(task_prompt)
        return self._parse_processed_articles(response)

    async def analyze_trends(
        self, articles: list[ProcessedArticle]
    ) -> list[TrendingTopic]:
        """Detect trends using detect-trends skill."""
        if not articles:
            return []

        articles_data = [
            {"title": a.title, "entities": a.entities, "source": a.source}
            for a in articles
        ]

        task_prompt = f"""Analyze trends across these {len(articles)} articles.

Use the detect-trends skill to:
1. Extract entities from all articles
2. Group by entity occurrence
3. Identify HOT topics (3+ sources)
4. Identify RISING topics (2 sources)
5. Calculate momentum

Articles:
```json
{json.dumps(articles_data, indent=2)}
```

Return JSON array of trending topics with fields:
entity, article_count, sources, status, momentum"""

        response = await self.run(task_prompt)
        return self._parse_trends(response)

    async def full_analysis(self, articles: list[dict]) -> AnalysisResult:
        """Run complete analysis pipeline."""
        processed = await self.analyze_articles(articles)
        breaking = await self.detect_breaking_news(processed)
        trends = await self.analyze_trends(processed)

        await self.on_skill_complete(
            "full_analysis",
            {
                "processed": len(processed),
                "breaking": len(breaking),
                "trends": len(trends),
            },
        )

        return AnalysisResult(
            processed_articles=processed,
            breaking_articles=breaking,
            trends=trends,
            stats={
                "total_processed": len(processed),
                "breaking_count": len(breaking),
                "trend_count": len(trends),
            },
        )

    def _parse_processed_articles(self, response: str) -> list[ProcessedArticle]:
        """Parse LLM response into ProcessedArticles."""
        try:
            data = self._extract_json(response)
            articles = data if isinstance(data, list) else data.get("articles", [])
            return [
                ProcessedArticle(
                    url=a.get("url", ""),
                    title=a.get("title", ""),
                    source=a.get("source", ""),
                    source_category=a.get("source_category", ""),
                    published_at=None,
                    original_summary=a.get("original_summary", ""),
                    ai_summary=a.get("ai_summary", ""),
                    category=a.get("category", "general"),
                    entities=a.get("entities", []),
                    importance_score=a.get("importance_score", 5),
                    is_breaking=a.get("is_breaking", False),
                    breaking_reason=a.get("breaking_reason"),
                    content_hash=a.get("content_hash", ""),
                )
                for a in articles
            ]
        except Exception as e:
            logger.warning(f"Failed to parse articles: {e}")
            return []

    def _parse_trends(self, response: str) -> list[TrendingTopic]:
        """Parse LLM response into TrendingTopics."""
        try:
            data = self._extract_json(response)
            trends = data if isinstance(data, list) else data.get("trends", [])
            return [
                TrendingTopic(
                    entity=t.get("entity", ""),
                    article_count=t.get("article_count", 0),
                    sources=t.get("sources", []),
                    status=t.get("status", "STABLE"),
                    momentum=t.get("momentum", 0.0),
                )
                for t in trends
            ]
        except Exception as e:
            logger.warning(f"Failed to parse trends: {e}")
            return []

    async def on_skill_complete(self, skill_name: str, result: dict[str, Any]) -> None:
        """Record skill outcomes for learning."""
        success = result.get("processed", 0) > 0 or result.get("total", 0) > 0
        await self.record_outcome(skill_name, result, success=success)
