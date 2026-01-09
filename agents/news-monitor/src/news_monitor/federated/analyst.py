"""
News Analyst Agent - Executes diagnostic skills.

This federated agent handles:
- analyze-article: LLM analysis of article content
- detect-breaking-news: Identify breaking news for alerts
- analyze-trends: Detect trending topics across articles

It uses the skill definitions for configuration and the existing
implementation code for actual execution.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from core_agents.skills import record_skill_outcome_to_registry
from news_monitor.agents.analyst import ContentAnalystAgent
from news_monitor.agents.trends import TrendAnalyzerAgent
from news_monitor.federated.skills import get_news_skill
from news_monitor.memory import is_duplicate_article, store_article
from news_monitor.models import ProcessedArticle, RawArticle, TrendingTopic

logger = logging.getLogger(__name__)

# Number of parallel workers for article processing
MAX_PARALLEL_WORKERS = 8


@dataclass
class AnalysisResult:
    """Result from analyzing articles."""

    processed_articles: list[ProcessedArticle] = field(default_factory=list)
    breaking_articles: list[ProcessedArticle] = field(default_factory=list)
    trends: list[TrendingTopic] = field(default_factory=list)
    articles_analyzed: int = 0
    articles_failed: int = 0
    duplicates_filtered: int = 0


class NewsAnalystAgent:
    """
    Federated agent that executes news analysis skills.

    Skills used:
    - news/diagnostic/analyze-article
    - news/diagnostic/detect-breaking-news
    - news/diagnostic/analyze-trends
    """

    def __init__(self, parallel_workers: int = MAX_PARALLEL_WORKERS):
        """
        Initialize the analyst agent.

        Args:
            parallel_workers: Number of parallel workers for LLM calls
        """
        self.parallel_workers = parallel_workers
        self._skill_analyze = None
        self._skill_breaking = None
        self._skill_trends = None
        self._content_analyst = None
        self._trend_analyzer = None

    async def _load_skills(self) -> None:
        """Load skill definitions."""
        if self._skill_analyze is None:
            self._skill_analyze = await get_news_skill("news/diagnostic/analyze-article")
        if self._skill_breaking is None:
            self._skill_breaking = await get_news_skill("news/diagnostic/detect-breaking-news")
        if self._skill_trends is None:
            self._skill_trends = await get_news_skill("news/diagnostic/analyze-trends")

    def _get_content_analyst(self) -> ContentAnalystAgent:
        """Get or create content analyst."""
        if self._content_analyst is None:
            self._content_analyst = ContentAnalystAgent()
        return self._content_analyst

    def _get_trend_analyzer(self) -> TrendAnalyzerAgent:
        """Get or create trend analyzer."""
        if self._trend_analyzer is None:
            self._trend_analyzer = TrendAnalyzerAgent()
        return self._trend_analyzer

    def _analyze_single_article(self, article: RawArticle) -> ProcessedArticle | None:
        """
        Analyze a single article (from analyze-article skill).

        Steps:
        1. Prepare content (truncate if needed)
        2. Call LLM for analysis
        3. Parse response
        4. Apply source boost
        5. Generate content hash
        """
        try:
            analyst = self._get_content_analyst()
            return analyst.analyze_article(article)
        except Exception as e:
            title = article.title[:50] if article.title else "unknown"
            logger.warning(f"Failed to analyze '{title}...': {e}")
            return None

    async def analyze_articles(
        self,
        raw_articles: list[RawArticle],
        deduplicate: bool = True,
    ) -> AnalysisResult:
        """
        Analyze a batch of articles.

        Executes the analyze-article skill on each article in parallel.

        Args:
            raw_articles: Articles to analyze
            deduplicate: Whether to filter duplicates and store unique articles

        Returns:
            AnalysisResult with processed articles and stats
        """
        await self._load_skills()

        result = AnalysisResult()

        if not raw_articles:
            return result

        logger.info(f"Analyzing {len(raw_articles)} articles with {self.parallel_workers} workers")

        # Process articles in parallel
        processed = []
        with ThreadPoolExecutor(max_workers=self.parallel_workers) as executor:
            future_to_article = {
                executor.submit(self._analyze_single_article, article): article
                for article in raw_articles
            }

            for future in as_completed(future_to_article):
                article_result = future.result()
                if article_result is not None:
                    processed.append(article_result)
                    result.articles_analyzed += 1
                else:
                    result.articles_failed += 1

        # Deduplicate if requested
        if deduplicate:
            unique = []
            for article in processed:
                if not is_duplicate_article(article):
                    store_article(article)
                    unique.append(article)
                else:
                    result.duplicates_filtered += 1
            processed = unique

        result.processed_articles = processed

        logger.info(
            f"Analysis complete: {result.articles_analyzed} analyzed, "
            f"{result.articles_failed} failed, {result.duplicates_filtered} duplicates"
        )

        # Record skill outcome to registry
        success = result.articles_analyzed > 0 and result.articles_failed < result.articles_analyzed
        await record_skill_outcome_to_registry(
            skill_id="news/diagnostic/analyze-article",
            success=success,
            skill_name="Analyze Article",
            domain="news",
            category="diagnostic",
        )

        return result

    async def detect_breaking_news(
        self,
        articles: list[ProcessedArticle],
    ) -> list[ProcessedArticle]:
        """
        Detect breaking news articles (from detect-breaking-news skill).

        Criteria:
        - is_breaking = True (set by LLM)
        - importance_score >= 8

        Args:
            articles: Processed articles to check

        Returns:
            List of articles qualifying as breaking news
        """
        await self._load_skills()

        # Apply criteria from skill
        breaking = [a for a in articles if a.is_breaking and a.importance_score >= 8]

        if breaking:
            logger.info(f"Detected {len(breaking)} breaking news articles")

        return breaking

    async def analyze_trends(
        self,
        articles: list[ProcessedArticle],
    ) -> list[TrendingTopic]:
        """
        Analyze trends across articles (from analyze-trends skill).

        Steps:
        1. Extract topics from entities
        2. Detect hot topics (3+ sources)
        3. Compare to historical data
        4. Calculate momentum
        5. Detect entity clusters

        Args:
            articles: Processed articles to analyze

        Returns:
            List of trending topics
        """
        await self._load_skills()

        if not articles:
            return []

        logger.info(f"Analyzing trends across {len(articles)} articles")

        analyzer = self._get_trend_analyzer()
        trends = analyzer.analyze_trends(articles)

        logger.info(f"Identified {len(trends)} trends")

        # Record skill outcome to registry
        await record_skill_outcome_to_registry(
            skill_id="news/diagnostic/analyze-trends",
            success=True,  # Trend analysis is best-effort, always succeeds
            skill_name="Analyze Trends",
            domain="news",
            category="diagnostic",
        )

        return trends

    async def full_analysis(
        self,
        raw_articles: list[RawArticle],
    ) -> AnalysisResult:
        """
        Run complete analysis pipeline.

        Executes all three diagnostic skills:
        1. analyze-article on each article
        2. detect-breaking-news on results
        3. analyze-trends on results

        Args:
            raw_articles: Raw articles to process

        Returns:
            Complete AnalysisResult
        """
        # Step 1: Analyze articles
        result = await self.analyze_articles(raw_articles, deduplicate=True)

        if not result.processed_articles:
            return result

        # Step 2: Detect breaking news
        result.breaking_articles = await self.detect_breaking_news(result.processed_articles)

        # Step 3: Analyze trends
        result.trends = await self.analyze_trends(result.processed_articles)

        return result


async def run_analysis(
    raw_articles: list[RawArticle],
    parallel_workers: int = MAX_PARALLEL_WORKERS,
) -> AnalysisResult:
    """
    Run the analysis pipeline.

    Args:
        raw_articles: Articles to analyze
        parallel_workers: Number of parallel workers

    Returns:
        AnalysisResult with all analysis outputs
    """
    analyst = NewsAnalystAgent(parallel_workers=parallel_workers)
    return await analyst.full_analysis(raw_articles)
