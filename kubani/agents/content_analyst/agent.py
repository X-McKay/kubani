"""
Content Analyst Agent - Analyzes content for insights and trends.

Implements the analyze-article skill: uses LLM to extract insights,
detect important items, and identify trends.

Features:
- Parallel LLM analysis with configurable concurrency (default: 8 workers)
- Semaphore-limited to prevent LLM overload
- Content hash deduplication

Usage:
    from agents.content_analyst import ContentAnalystAgent

    agent = ContentAnalystAgent()
    result = await agent.analyze_articles(articles)
"""

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from kubani.agents._base import KubaniAgent

logger = logging.getLogger(__name__)


# ============================================================================
# Models
# ============================================================================


class ArticleCategory:
    """Categories for classifying articles."""

    RESEARCH = "research"
    BUSINESS = "business"
    PRODUCT = "product"
    SECURITY = "security"
    POLICY = "policy"
    GENERAL = "general"


class TrendStatus:
    """Status of a trending topic."""

    BREAKING = "breaking"
    HOT = "hot"
    RISING = "rising"
    ESTABLISHED = "established"
    FADING = "fading"


@dataclass
class ProcessedArticle:
    """Article after processing by the content analyst."""

    url: str
    title: str
    source: str
    source_category: str = ""
    published_at: datetime | None = None
    original_summary: str = ""
    ai_summary: str = ""
    category: str = ArticleCategory.GENERAL
    entities: list[str] = field(default_factory=list)
    importance_score: int = 5
    is_breaking: bool = False
    content_hash: str = ""
    processed_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    # Aliases for syndicate compatibility
    @property
    def summary(self) -> str:
        return self.ai_summary or self.original_summary

    @property
    def topics(self) -> list[str]:
        return self.entities


@dataclass
class TrendingTopic:
    """A topic that's trending across multiple sources."""

    topic: str
    status: str = TrendStatus.RISING
    article_count: int = 0
    first_seen: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_seen: datetime = field(default_factory=lambda: datetime.now(UTC))
    sources: list[str] = field(default_factory=list)
    related_articles: list[str] = field(default_factory=list)
    momentum: float = 0.0

    # Aliases for syndicate compatibility
    @property
    def mention_count(self) -> int:
        return self.article_count


@dataclass
class AnalysisResult:
    """Result from analyzing articles."""

    processed_articles: list[ProcessedArticle] = field(default_factory=list)
    breaking_articles: list[ProcessedArticle] = field(default_factory=list)
    trends: list[TrendingTopic] = field(default_factory=list)
    articles_analyzed: int = 0
    articles_failed: int = 0
    duplicates_filtered: int = 0


# ============================================================================
# LLM Response Schema
# ============================================================================


class ArticleAnalysisResponse(BaseModel):
    """Structured output from LLM article analysis."""

    summary: str
    category: str
    entities: list[str]
    importance_score: int
    is_breaking: bool
    breaking_reason: str | None = None


# ============================================================================
# Prompts
# ============================================================================


ANALYSIS_PROMPT = """Analyze the following news article and provide:

1. **Summary**: A concise 2-3 sentence summary highlighting the key points.
2. **Category**: One of: research, business, product, security, policy, general
3. **Entities**: List of key entities mentioned (companies, people, technologies, models)
4. **Importance Score**: 1-10 rating where:
   - 1-3: Minor news, incremental updates
   - 4-6: Notable news, meaningful developments
   - 7-8: Important news, significant impact
   - 9-10: Major news, industry-changing announcements
5. **Is Breaking**: True if this is major breaking news that should trigger an immediate alert
6. **Breaking Reason**: If breaking, explain why (e.g., "Major model release", "Security vulnerability")

Consider these factors for importance:
- Source credibility and significance
- Novelty of the information
- Potential industry impact
- Whether this is from an official company announcement
- Security implications

Article:
Title: {title}
Source: {source}
Content: {content}

Respond in JSON format:
{{
    "summary": "...",
    "category": "research|business|product|security|policy|general",
    "entities": ["entity1", "entity2", ...],
    "importance_score": 1-10,
    "is_breaking": true/false,
    "breaking_reason": "..." or null
}}"""


# ============================================================================
# Agent Implementation
# ============================================================================


def _generate_content_hash(title: str, url: str) -> str:
    """Generate a hash for content deduplication."""
    content = f"{title}:{url}".lower()
    return hashlib.sha256(content.encode()).hexdigest()[:16]


class ContentAnalystAgent(KubaniAgent):
    """
    Analyzes content for insights, trends, and important items.

    Implements the analyze-article skill using LLM for analysis.
    """

    AGENT_DIR = Path(__file__).parent

    def __init__(self, agent_dir: Path | None = None):
        """Initialize the Content Analyst agent."""
        super().__init__(agent_dir)

        # Analyst-specific configuration
        analyst_config = self.config.get("analyst", {})
        self.parallel_workers = analyst_config.get("parallel_workers", 8)

        breaking_config = analyst_config.get("breaking_news", {})
        self.min_importance = breaking_config.get("min_importance_score", 8)

        # LLM client - lazy initialization
        self._llm_client = None

    def _get_llm_client(self):
        """Get or create LLM client."""
        if self._llm_client is None:
            from openai import OpenAI

            self._llm_client = OpenAI(
                api_key="not-needed",
                base_url=os.environ.get(
                    "VLLM_API_URL", "http://llm-api.vllm.svc.cluster.local:8000/v1"
                ),
            )
        return self._llm_client

    def _get_model(self) -> str:
        """Get the LLM model name."""
        return os.environ.get("VLLM_MODEL", "nvidia/Qwen3-14B-FP4")

    def _analyze_single_article(self, article: dict[str, Any]) -> ProcessedArticle:
        """
        Analyze a single article using LLM.

        Implements the analyze-article skill logic.
        """
        title = article.get("title", "")
        url = article.get("url", "")
        source = article.get("source", "")
        source_category = article.get("source_category", "")
        original_summary = article.get("summary", "")
        published_at = article.get("published_date")

        # Parse published_at if string
        if isinstance(published_at, str) and published_at:
            try:
                published_at = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
            except ValueError:
                published_at = None

        try:
            # Step 1: Prepare content (truncate if needed)
            content = f"{title}\n\n{original_summary}"
            if len(content) > 2000:
                content = content[:2000] + "..."

            # Step 2: Call LLM for analysis
            client = self._get_llm_client()
            response = client.chat.completions.create(
                model=self._get_model(),
                messages=[
                    {
                        "role": "system",
                        "content": "You are an AI news analyst. Analyze articles and provide structured analysis in JSON format.",
                    },
                    {
                        "role": "user",
                        "content": ANALYSIS_PROMPT.format(
                            title=title,
                            source=source,
                            content=content,
                        ),
                    },
                ],
                temperature=0.3,
                max_tokens=500,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )

            # Step 3: Parse response
            response_text = response.choices[0].message.content
            analysis = self._parse_analysis_response(response_text)

            # Step 4: Apply importance boost for company blogs
            importance = analysis.importance_score
            if source_category == "company_blogs" and importance < 7:
                importance = min(importance + 2, 10)

            # Step 5: Generate content hash
            content_hash = _generate_content_hash(title, url)

            return ProcessedArticle(
                url=url,
                title=title,
                source=source,
                source_category=source_category,
                published_at=published_at,
                original_summary=original_summary,
                ai_summary=analysis.summary,
                category=analysis.category.lower(),
                entities=analysis.entities,
                importance_score=importance,
                is_breaking=analysis.is_breaking,
                content_hash=content_hash,
                processed_at=datetime.now(UTC),
            )

        except Exception as e:
            logger.error(f"Failed to analyze article '{title[:50]}...': {e}")

            # Fallback behavior per skill spec
            return ProcessedArticle(
                url=url,
                title=title,
                source=source,
                source_category=source_category,
                published_at=published_at,
                original_summary=original_summary,
                ai_summary=original_summary,
                category=ArticleCategory.GENERAL,
                entities=[],
                importance_score=5,
                is_breaking=False,
                content_hash=_generate_content_hash(title, url),
                processed_at=datetime.now(UTC),
            )

    def _parse_analysis_response(self, response_text: str) -> ArticleAnalysisResponse:
        """Parse LLM response into structured analysis."""
        try:
            # Strip Qwen3 thinking tags
            response_text = re.sub(r"<think>.*?</think>", "", response_text, flags=re.DOTALL)
            response_text = response_text.strip()

            # Find JSON in response (may have markdown code blocks)
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
            elif "```" in response_text:
                json_start = response_text.find("```") + 3
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()

            data = json.loads(response_text)

            return ArticleAnalysisResponse(
                summary=data.get("summary", ""),
                category=data.get("category", "general"),
                entities=data.get("entities", []),
                importance_score=min(max(data.get("importance_score", 5), 1), 10),
                is_breaking=data.get("is_breaking", False),
                breaking_reason=data.get("breaking_reason"),
            )

        except json.JSONDecodeError:
            logger.warning(f"Failed to parse JSON from response: {response_text[:200]}")
            return ArticleAnalysisResponse(
                summary="",
                category="general",
                entities=[],
                importance_score=5,
                is_breaking=False,
            )

    async def analyze_articles(
        self,
        articles: list[dict[str, Any]],
        deduplicate: bool = True,
    ) -> AnalysisResult:
        """
        Analyze a batch of articles in parallel.

        Uses semaphore-limited concurrency to prevent LLM overload.
        The parallel_workers config (default: 8) controls concurrency.

        Args:
            articles: Raw articles to analyze
            deduplicate: Whether to filter duplicates

        Returns:
            AnalysisResult with processed articles and stats
        """
        from kubani.framework.resilience import run_with_semaphore

        result = AnalysisResult()

        if not articles:
            return result

        logger.info(
            f"Analyzing {len(articles)} articles (parallel_workers={self.parallel_workers})"
        )

        # Create analysis tasks for parallel execution
        # Each task is a lambda that captures its article
        tasks = [lambda a=article: self._analyze_single_article_async(a) for article in articles]

        # Run analysis in parallel with semaphore limiting
        processed_results = await run_with_semaphore(
            tasks,
            max_concurrent=self.parallel_workers,
            return_exceptions=True,
        )

        # Process results and deduplicate
        seen_hashes: set[str] = set()
        for processed in processed_results:
            if isinstance(processed, Exception):
                logger.error(f"Failed to process article: {processed}")
                result.articles_failed += 1
                continue

            result.articles_analyzed += 1

            # Deduplicate by content hash
            if deduplicate and processed.content_hash in seen_hashes:
                result.duplicates_filtered += 1
                continue

            seen_hashes.add(processed.content_hash)
            result.processed_articles.append(processed)

        logger.info(
            f"Analysis complete: {result.articles_analyzed} analyzed, "
            f"{len(result.processed_articles)} processed, "
            f"{result.duplicates_filtered} duplicates filtered, "
            f"{result.articles_failed} failed"
        )

        return result

    async def _analyze_single_article_async(self, article: dict[str, Any]) -> ProcessedArticle:
        """Async wrapper for _analyze_single_article for use with run_with_semaphore."""
        # The actual analysis is synchronous (OpenAI client is sync)
        # but wrapping allows semaphore-controlled concurrency
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._analyze_single_article, article)

    async def detect_breaking_news(
        self,
        articles: list[ProcessedArticle],
    ) -> list[ProcessedArticle]:
        """
        Detect breaking news articles.

        Args:
            articles: Processed articles to check

        Returns:
            List of breaking news articles
        """
        breaking = [
            a for a in articles if a.is_breaking and a.importance_score >= self.min_importance
        ]

        if breaking:
            logger.info(f"Detected {len(breaking)} breaking news articles")

        return breaking

    async def analyze_trends(
        self,
        articles: list[ProcessedArticle],
        hot_threshold: int = 3,
    ) -> list[TrendingTopic]:
        """
        Analyze trends across articles.

        Args:
            articles: Processed articles to analyze
            hot_threshold: Number of sources for "hot" status

        Returns:
            List of trending topics
        """
        if not articles:
            return []

        logger.info(f"Analyzing trends across {len(articles)} articles")

        # Group articles by entity
        entity_articles: dict[str, list[ProcessedArticle]] = {}
        for article in articles:
            for entity in article.entities:
                entity_lower = entity.lower().strip()
                if len(entity_lower) < 3:
                    continue
                if entity_lower not in entity_articles:
                    entity_articles[entity_lower] = []
                entity_articles[entity_lower].append(article)

        # Build trends from entities with multiple articles
        trends = []
        for entity, entity_arts in entity_articles.items():
            if len(entity_arts) < 2:
                continue

            sources = list({a.source for a in entity_arts})
            status = TrendStatus.HOT if len(sources) >= hot_threshold else TrendStatus.RISING

            trend = TrendingTopic(
                topic=entity.title(),
                status=status,
                article_count=len(entity_arts),
                first_seen=min(
                    (a.published_at or a.processed_at for a in entity_arts),
                    default=datetime.now(UTC),
                ),
                last_seen=max(
                    (a.published_at or a.processed_at for a in entity_arts),
                    default=datetime.now(UTC),
                ),
                sources=sources,
                related_articles=[a.url for a in entity_arts],
                momentum=len(sources) / hot_threshold,
            )
            trends.append(trend)

        # Sort by status priority and momentum
        status_priority = {
            TrendStatus.BREAKING: 0,
            TrendStatus.HOT: 1,
            TrendStatus.RISING: 2,
            TrendStatus.ESTABLISHED: 3,
            TrendStatus.FADING: 4,
        }
        trends.sort(key=lambda t: (status_priority.get(t.status, 5), -t.momentum))

        logger.info(f"Identified {len(trends)} trending topics")
        return trends

    async def full_analysis(
        self,
        articles: list[dict[str, Any]],
    ) -> AnalysisResult:
        """
        Run complete analysis pipeline.

        1. Analyze each article
        2. Detect breaking news
        3. Analyze trends

        Args:
            articles: Raw articles to process

        Returns:
            Complete AnalysisResult
        """
        result = await self.analyze_articles(articles, deduplicate=True)

        if result.processed_articles:
            result.breaking_articles = await self.detect_breaking_news(result.processed_articles)
            result.trends = await self.analyze_trends(result.processed_articles)

        return result

    # ========================================================================
    # analyze-trends-historical skill implementation
    # ========================================================================

    async def analyze_trends_historical(
        self,
        current_articles: list[ProcessedArticle],
        lookback_days: int = 14,
        min_mentions: int = 2,
    ) -> dict[str, Any]:
        """
        Analyze trends compared against historical data from memory.

        Implements the analyze-trends-historical skill.

        Args:
            current_articles: Articles from current period
            lookback_days: Days of history to compare against
            min_mentions: Minimum mentions to consider a trend

        Returns:
            Historical trend analysis with velocity classification
        """
        logger.info(
            f"Analyzing historical trends for {len(current_articles)} articles "
            f"(lookback: {lookback_days} days)"
        )

        # Step 1: Extract current period entities
        current_entities: dict[str, int] = {}
        for article in current_articles:
            for entity in article.entities:
                entity_lower = entity.lower().strip()
                if len(entity_lower) >= 3:
                    current_entities[entity_lower] = current_entities.get(entity_lower, 0) + 1

        # Step 2: Query historical data from memory
        historical_entities = await self._get_historical_entities(lookback_days)

        # Step 3: Calculate velocity for each entity
        trends = []
        for entity, current_count in current_entities.items():
            if current_count < min_mentions:
                continue

            historical_count = historical_entities.get(entity, 0)
            velocity = self._calculate_velocity(current_count, historical_count, lookback_days)

            trends.append(
                {
                    "entity": entity.title(),
                    "current_mentions": current_count,
                    "historical_mentions": historical_count,
                    "velocity": velocity["rate"],
                    "velocity_class": velocity["class"],
                }
            )

        # Step 4: Identify emerging and declining topics
        emerging = [t for t in trends if t["velocity_class"] in ["surging", "rising"]]
        declining = [t for t in trends if t["velocity_class"] in ["declining", "fading"]]

        # Sort by velocity
        trends.sort(key=lambda t: t["velocity"], reverse=True)
        emerging.sort(key=lambda t: t["velocity"], reverse=True)
        declining.sort(key=lambda t: t["velocity"])

        # Step 5: Generate summary
        summary = self._generate_trend_summary(trends, emerging, declining)

        result = {
            "trends": trends[:20],  # Top 20
            "emerging_topics": [t["entity"] for t in emerging[:5]],
            "declining_topics": [t["entity"] for t in declining[:5]],
            "summary": summary,
            "lookback_days": lookback_days,
            "total_entities_analyzed": len(current_entities),
        }

        logger.info(
            f"Historical trend analysis complete: "
            f"{len(emerging)} emerging, {len(declining)} declining"
        )
        return result

    async def _get_historical_entities(self, lookback_days: int) -> dict[str, int]:
        """
        Get historical entity counts from memory.

        Falls back to empty dict if memory unavailable.
        """
        try:
            from kubani.framework.mcp import get_mcp_client

            client = get_mcp_client()

            # Query memory for historical trend snapshots
            snapshots = await client.memory.query_learnings(
                agent_id="content-analyst",
                learning_type="trend_snapshot",
                limit=lookback_days,
            )

            # Aggregate entity counts from snapshots
            entities: dict[str, int] = {}
            for snapshot in snapshots:
                context = snapshot.get("context", {})
                for entity, count in context.get("entities", {}).items():
                    entities[entity] = entities.get(entity, 0) + count

            return entities

        except Exception as e:
            logger.warning(f"Could not fetch historical data from memory: {e}")
            return {}

    def _calculate_velocity(
        self,
        current: int,
        historical: int,
        lookback_days: int,
    ) -> dict[str, Any]:
        """
        Calculate trend velocity and classify it.

        Returns:
            Dict with rate (float) and class (str)
        """
        # Normalize historical to daily average
        daily_historical = historical / lookback_days if lookback_days > 0 else 0

        # Calculate change rate
        if daily_historical > 0:
            rate = (current - daily_historical) / daily_historical
        elif current > 0:
            rate = 2.0  # New topic, treat as surging
        else:
            rate = 0.0

        # Classify velocity
        if rate >= 1.0:
            velocity_class = "surging"
        elif rate >= 0.3:
            velocity_class = "rising"
        elif rate >= -0.3:
            velocity_class = "stable"
        elif rate >= -0.7:
            velocity_class = "declining"
        else:
            velocity_class = "fading"

        return {"rate": round(rate, 2), "class": velocity_class}

    def _generate_trend_summary(
        self,
        trends: list[dict[str, Any]],
        emerging: list[dict[str, Any]],
        declining: list[dict[str, Any]],
    ) -> str:
        """Generate a natural language trend summary."""
        parts = []

        if emerging:
            top_emerging = [t["entity"] for t in emerging[:3]]
            parts.append(f"Emerging topics: {', '.join(top_emerging)}")

        if declining:
            top_declining = [t["entity"] for t in declining[:3]]
            parts.append(f"Declining interest in: {', '.join(top_declining)}")

        surging = [t for t in trends if t["velocity_class"] == "surging"]
        if surging:
            parts.append(f"{len(surging)} topics showing rapid growth")

        if not parts:
            return "No significant trend changes detected"

        return ". ".join(parts) + "."

    async def store_trend_snapshot(
        self,
        articles: list[ProcessedArticle],
    ) -> None:
        """
        Store current period entities for future trend analysis.

        Called after processing to build historical data.
        """
        entities: dict[str, int] = {}
        for article in articles:
            for entity in article.entities:
                entity_lower = entity.lower().strip()
                if len(entity_lower) >= 3:
                    entities[entity_lower] = entities.get(entity_lower, 0) + 1

        try:
            from kubani.framework.mcp import get_mcp_client

            client = get_mcp_client()
            await client.memory.store_learning(
                agent_id="content-analyst",
                learning_type="trend_snapshot",
                content=f"Trend snapshot with {len(entities)} entities",
                confidence=1.0,
                context={
                    "entities": entities,
                    "article_count": len(articles),
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )
            logger.info(f"Stored trend snapshot with {len(entities)} entities")

        except Exception as e:
            logger.warning(f"Failed to store trend snapshot: {e}")

    async def on_skill_complete(self, skill_name: str, result: dict[str, Any]) -> None:
        """Record skill outcomes for learning."""
        success = result.get("articles_analyzed", 0) > 0
        await self.record_outcome(skill_name, result, success=success)
