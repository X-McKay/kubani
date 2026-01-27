"""
News Digest Syndicate - AI news collection and publishing.

Orchestrates article collection, analysis, research collection,
and rich digest publishing to keep users informed about AI developments.

Usage:
    from syndicates.news_digest import NewsDigestSyndicate

    syndicate = NewsDigestSyndicate()
    await syndicate.start()
"""

import asyncio
import logging
from pathlib import Path
from typing import Any

from kubani.agents.content_analyst import ContentAnalystAgent
from kubani.agents.digest_publisher import DigestPublisherAgent
from kubani.agents.feed_collector import FeedCollectorAgent
from kubani.agents.research_analyst import ResearchAnalystAgent
from kubani.agents.research_collector import ResearchCollectorAgent
from kubani.agents.trend_analyst import TrendAnalystAgent
from kubani.framework.events import EventType, get_event_bus
from kubani.syndicates._base import Syndicate

logger = logging.getLogger(__name__)


class NewsDigestSyndicate(Syndicate):
    """
    AI news collection and publishing syndicate.

    Orchestrates six agents:
    - FeedCollectorAgent: Collects articles from RSS feeds
    - ResearchCollectorAgent: Collects arXiv papers and GitHub repos
    - ContentAnalystAgent: Analyzes articles with LLM
    - ResearchAnalystAgent: Analyzes papers and repos for digest inclusion
    - TrendAnalystAgent: Historical trend analysis over 7-14 day window
    - DigestPublisherAgent: Publishes rich executive digests to Discord

    Runs on a schedule to produce morning and afternoon digests,
    with frequent checks for breaking news and weekly trend reports.
    """

    SYNDICATE_DIR = Path(__file__).parent

    agents = [
        FeedCollectorAgent,
        ResearchCollectorAgent,
        ContentAnalystAgent,
        ResearchAnalystAgent,
        TrendAnalystAgent,
        DigestPublisherAgent,
    ]

    def __init__(self, syndicate_dir: Path | None = None):
        """Initialize the News Digest syndicate."""
        super().__init__(syndicate_dir)
        self._event_bus = None

    async def run(self) -> None:
        """
        Main orchestration loop.

        Runs scheduled tasks for:
        1. Morning digest (7am)
        2. Afternoon digest (3pm)
        3. Breaking news checks (every 15min)
        4. Weekly trend analysis (Sundays)
        """
        self._event_bus = await get_event_bus()

        # Get agent instances
        feed_collector = self.get_agent(FeedCollectorAgent)
        research_collector = self.get_agent(ResearchCollectorAgent)
        content_analyst = self.get_agent(ContentAnalystAgent)
        research_analyst = self.get_agent(ResearchAnalystAgent)
        publisher = self.get_agent(DigestPublisherAgent)

        logger.info(f"Starting {self.name} with agents: {[a.__name__ for a in self.agents]}")

        # Run all tasks concurrently
        await asyncio.gather(
            self._scheduled_digests(
                feed_collector, research_collector, content_analyst, research_analyst, publisher
            ),
            self._breaking_news_monitor(feed_collector, content_analyst, publisher),
            self._handle_collection_requests(
                feed_collector, research_collector, content_analyst, research_analyst, publisher
            ),
        )

    async def _scheduled_digests(
        self,
        feed_collector: FeedCollectorAgent,
        research_collector: ResearchCollectorAgent,
        content_analyst: ContentAnalystAgent,
        research_analyst: ResearchAnalystAgent,
        publisher: DigestPublisherAgent,
    ) -> None:
        """Run scheduled digest generation."""
        schedule = self.config.get("schedule", {})

        morning = schedule.get("morning_digest", {})
        afternoon = schedule.get("afternoon_digest", {})

        if not morning.get("enabled", True) and not afternoon.get("enabled", True):
            logger.info("Scheduled digests disabled")
            return

        logger.info("Starting scheduled digest loop")

        # In production, this would use actual cron scheduling
        # For now, we'll just run the pipeline on startup and then sleep
        while self._running:
            try:
                await self._run_executive_digest_pipeline(
                    feed_collector,
                    research_collector,
                    content_analyst,
                    research_analyst,
                    publisher,
                    digest_type="scheduled",
                )
            except Exception as e:
                logger.error(f"Error in scheduled digest: {e}")

            # Sleep until next scheduled time (simplified - would use actual cron)
            await asyncio.sleep(3600 * 8)  # 8 hours

    async def _breaking_news_monitor(
        self,
        feed_collector: FeedCollectorAgent,
        content_analyst: ContentAnalystAgent,
        publisher: DigestPublisherAgent,
    ) -> None:
        """Monitor for breaking news."""
        schedule = self.config.get("schedule", {}).get("breaking_news", {})
        if not schedule.get("enabled", True):
            logger.info("Breaking news monitoring disabled")
            return

        logger.info("Starting breaking news monitor")

        while self._running:
            try:
                # Quick collection for breaking news
                articles = await feed_collector.collect_as_dicts()

                if articles:
                    # Analyze for breaking news only
                    result = await content_analyst.analyze_articles(articles)
                    breaking = await content_analyst.detect_breaking_news(result.processed_articles)

                    if breaking:
                        logger.info(f"Breaking news detected: {len(breaking)} articles")

                        # Publish breaking news immediately
                        for article in breaking:
                            await self._publish_breaking(publisher, article)

                        # Publish event
                        await self._event_bus.publish(
                            EventType.NEWS_BREAKING_DETECTED,
                            {
                                "count": len(breaking),
                                "articles": [{"title": a.title, "url": a.url} for a in breaking],
                            },
                            source=self.name,
                        )

            except Exception as e:
                logger.error(f"Error in breaking news monitor: {e}")

            # Check every 15 minutes
            await asyncio.sleep(900)

    async def _handle_collection_requests(
        self,
        feed_collector: FeedCollectorAgent,
        research_collector: ResearchCollectorAgent,
        content_analyst: ContentAnalystAgent,
        research_analyst: ResearchAnalystAgent,
        publisher: DigestPublisherAgent,
    ) -> None:
        """Handle on-demand collection requests."""
        logger.info("Starting collection request handler")

        async for event in self._event_bus.subscribe(
            EventType.NEWS_COLLECTION_REQUESTED,
            consumer_group=self.name,
            consumer_name=f"{self.name}-collector",
        ):
            if not self._running:
                break

            try:
                payload = event.payload
                digest_type = payload.get("type", "on-demand")

                await self._run_executive_digest_pipeline(
                    feed_collector,
                    research_collector,
                    content_analyst,
                    research_analyst,
                    publisher,
                    digest_type=digest_type,
                )

            except Exception as e:
                logger.error(f"Error handling collection request: {e}")

    async def _run_executive_digest_pipeline(
        self,
        feed_collector: FeedCollectorAgent,
        research_collector: ResearchCollectorAgent,
        content_analyst: ContentAnalystAgent,
        research_analyst: ResearchAnalystAgent,
        publisher: DigestPublisherAgent,
        digest_type: str,
    ) -> None:
        """
        Run the full executive digest pipeline.

        Pipeline stages:
        1. Collect news articles from RSS feeds
        2. Collect research papers from arXiv
        3. Collect trending repos from GitHub
        4. Analyze news articles for insights
        5. Analyze papers for digest worthiness
        6. Analyze repos for spotlight worthiness
        7. Run historical trend analysis
        8. Compose and publish executive digest
        """
        logger.info(f"Running {digest_type} executive digest pipeline")

        # Step 1: Collect news articles
        articles = await feed_collector.collect_as_dicts()
        logger.info(f"Collected {len(articles)} news articles")

        # Step 2: Collect research papers from arXiv
        papers_result = await research_collector.fetch_arxiv_papers()
        papers = [p.to_dict() for p in papers_result.papers]
        logger.info(f"Collected {len(papers)} arXiv papers")

        # Step 3: Collect trending repos from GitHub
        repos_result = await research_collector.fetch_github_trending()
        repos = [r.to_dict() for r in repos_result.repos]
        logger.info(f"Collected {len(repos)} GitHub repos")

        if not articles and not papers:
            logger.info("No content to process")
            return

        # Step 4: Analyze news articles
        await self.handoff(
            from_agent=feed_collector,
            to_agent=content_analyst,
            context={"articles": len(articles), "papers": len(papers), "repos": len(repos)},
            reason=f"Collected {len(articles)} articles, {len(papers)} papers, {len(repos)} repos",
        )

        news_result = await content_analyst.full_analysis(articles) if articles else None
        logger.info(
            f"Analyzed {news_result.articles_analyzed if news_result else 0} articles, "
            f"found {len(news_result.trends) if news_result else 0} trends"
        )

        # Step 5: Analyze papers for digest worthiness
        paper_analyses = []
        if papers:
            await self.handoff(
                from_agent=content_analyst,
                to_agent=research_analyst,
                context={"papers": len(papers)},
                reason=f"Analyzing {len(papers)} papers for digest inclusion",
            )
            paper_analyses = await research_analyst.analyze_papers_batch(papers)
            paper_analyses = [p.to_dict() for p in paper_analyses]
            digest_worthy = sum(1 for p in paper_analyses if p.get("digest_worthy"))
            logger.info(f"Analyzed {len(paper_analyses)} papers, {digest_worthy} digest-worthy")

        # Step 6: Analyze repos for spotlight worthiness
        repo_analyses = []
        if repos:
            repo_analyses = await research_analyst.analyze_repos_batch(repos)
            repo_analyses = [r.to_dict() for r in repo_analyses]
            spotlight_worthy = sum(1 for r in repo_analyses if r.get("spotlight_worthy"))
            logger.info(f"Analyzed {len(repo_analyses)} repos, {spotlight_worthy} spotlight-worthy")

        # Step 7: Historical trend analysis
        trends_analysis = None
        if news_result and news_result.processed_articles:
            trends_analysis = await content_analyst.analyze_trends_historical(
                news_result.processed_articles,
                lookback_days=14,
            )
            # Store trend snapshot for future comparisons
            await content_analyst.store_trend_snapshot(news_result.processed_articles)

        # Step 8: Identify company updates
        company_articles = []
        if news_result:
            company_articles = [
                {
                    "title": a.title,
                    "url": a.url,
                    "source": a.source,
                    "summary": a.summary,
                    "ai_summary": a.ai_summary,
                    "importance_score": a.importance_score,
                }
                for a in news_result.processed_articles
                if a.source_category == "company_blogs" or a.importance_score >= 7
            ]

        # Step 9: Hand off to publisher
        await self.handoff(
            from_agent=research_analyst,
            to_agent=publisher,
            context={
                "articles": len(news_result.processed_articles) if news_result else 0,
                "papers": len(paper_analyses),
                "repos": len(repo_analyses),
                "company_updates": len(company_articles),
            },
            reason="All analysis complete, composing executive digest",
        )

        # Convert ProcessedArticle objects to dicts for publisher
        articles_dicts = []
        if news_result:
            articles_dicts = [
                {
                    "title": a.title,
                    "url": a.url,
                    "source": a.source,
                    "summary": a.summary,
                    "ai_summary": a.ai_summary,
                    "importance_score": a.importance_score,
                    "topics": a.topics,
                    "category": a.category,
                }
                for a in news_result.processed_articles
            ]

        # Publish executive digest
        publish_result = await publisher.compose_and_publish_executive(
            articles=articles_dicts,
            research_deepdives=paper_analyses,
            tool_spotlights=repo_analyses,
            company_updates=company_articles,
            trends=trends_analysis,
            digest_type=digest_type,
        )

        if publish_result.success:
            logger.info(
                f"Published {digest_type} executive digest ({publish_result.chunks_sent} chunks)"
            )

            await self._event_bus.publish(
                EventType.NEWS_DIGEST_PUBLISHED,
                {
                    "type": digest_type,
                    "articles_count": len(articles_dicts),
                    "papers_count": len(paper_analyses),
                    "repos_count": len(repo_analyses),
                    "message_id": publish_result.message_id,
                },
                source=self.name,
            )
        else:
            logger.error(f"Failed to publish executive digest: {publish_result.error}")

    async def _run_digest_pipeline(
        self,
        collector: FeedCollectorAgent,
        analyst: ContentAnalystAgent,
        publisher: DigestPublisherAgent,
        digest_type: str,
    ) -> None:
        """Run the basic digest pipeline (legacy, for simple digests)."""
        logger.info(f"Running {digest_type} digest pipeline (basic)")

        # Step 1: Collect articles
        articles = await collector.collect_as_dicts()
        logger.info(f"Collected {len(articles)} articles")

        if not articles:
            logger.info("No articles to process")
            return

        # Step 2: Hand off to analyst
        await self.handoff(
            from_agent=collector,
            to_agent=analyst,
            context={"articles": articles, "count": len(articles)},
            reason=f"Collected {len(articles)} articles for analysis",
        )

        # Analyze articles
        result = await analyst.full_analysis(articles)
        logger.info(
            f"Analyzed {result.articles_analyzed} articles, found {len(result.trends)} trends"
        )

        if not result.processed_articles:
            logger.info("No processed articles to publish")
            return

        # Step 3: Hand off to publisher
        await self.handoff(
            from_agent=analyst,
            to_agent=publisher,
            context={
                "processed_articles": len(result.processed_articles),
                "trends": len(result.trends),
                "breaking": len(result.breaking_articles),
            },
            reason=f"Analysis complete with {len(result.processed_articles)} articles",
        )

        # Convert ProcessedArticle objects to dicts for publisher
        articles_dicts = [
            {
                "title": a.title,
                "url": a.url,
                "source": a.source,
                "summary": a.summary,
                "importance_score": a.importance_score,
                "topics": a.topics,
            }
            for a in result.processed_articles
        ]

        trends_dicts = [
            {
                "topic": t.topic,
                "mention_count": t.mention_count,
                "momentum": t.momentum,
            }
            for t in result.trends
        ]

        # Publish digest
        publish_result = await publisher.compose_and_publish(articles_dicts, trends_dicts)

        if publish_result.success:
            logger.info(f"Published {digest_type} digest")

            await self._event_bus.publish(
                EventType.NEWS_DIGEST_PUBLISHED,
                {
                    "type": digest_type,
                    "articles_count": len(result.processed_articles),
                    "trends_count": len(result.trends),
                    "message_id": publish_result.message_id,
                },
                source=self.name,
            )
        else:
            logger.error(f"Failed to publish digest: {publish_result.error}")

    async def _publish_breaking(
        self,
        publisher: DigestPublisherAgent,
        article: Any,
    ) -> None:
        """Publish a breaking news article."""
        # This would use the publisher's breaking news method
        logger.info(f"Publishing breaking news: {article.title}")
