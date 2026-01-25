"""
News Digest Syndicate - AI news collection and publishing.

Orchestrates article collection, analysis, and digest publishing
to keep users informed about AI developments.

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
from kubani.framework.events import EventType, get_event_bus
from kubani.syndicates._base import Syndicate

logger = logging.getLogger(__name__)


class NewsDigestSyndicate(Syndicate):
    """
    AI news collection and publishing syndicate.

    Orchestrates three agents:
    - FeedCollectorAgent: Collects articles from RSS feeds
    - ContentAnalystAgent: Analyzes articles with LLM
    - DigestPublisherAgent: Publishes digests to Discord

    Runs on a schedule to produce morning and afternoon digests,
    with frequent checks for breaking news.
    """

    SYNDICATE_DIR = Path(__file__).parent

    agents = [
        FeedCollectorAgent,
        ContentAnalystAgent,
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
        """
        self._event_bus = await get_event_bus()

        # Get agent instances
        collector = self.get_agent(FeedCollectorAgent)
        analyst = self.get_agent(ContentAnalystAgent)
        publisher = self.get_agent(DigestPublisherAgent)

        logger.info(f"Starting {self.name} with agents: {[a.__name__ for a in self.agents]}")

        # Run all tasks concurrently
        await asyncio.gather(
            self._scheduled_digests(collector, analyst, publisher),
            self._breaking_news_monitor(collector, analyst, publisher),
            self._handle_collection_requests(collector, analyst, publisher),
        )

    async def _scheduled_digests(
        self,
        collector: FeedCollectorAgent,
        analyst: ContentAnalystAgent,
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
                await self._run_digest_pipeline(collector, analyst, publisher, "scheduled")
            except Exception as e:
                logger.error(f"Error in scheduled digest: {e}")

            # Sleep until next scheduled time (simplified - would use actual cron)
            await asyncio.sleep(3600 * 8)  # 8 hours

    async def _breaking_news_monitor(
        self,
        collector: FeedCollectorAgent,
        analyst: ContentAnalystAgent,
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
                articles = await collector.collect_as_dicts()

                if articles:
                    # Analyze for breaking news only
                    result = await analyst.analyze_articles(articles)
                    breaking = await analyst.detect_breaking_news(result.processed_articles)

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
        collector: FeedCollectorAgent,
        analyst: ContentAnalystAgent,
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

                await self._run_digest_pipeline(collector, analyst, publisher, digest_type)

            except Exception as e:
                logger.error(f"Error handling collection request: {e}")

    async def _run_digest_pipeline(
        self,
        collector: FeedCollectorAgent,
        analyst: ContentAnalystAgent,
        publisher: DigestPublisherAgent,
        digest_type: str,
    ) -> None:
        """Run the full digest pipeline."""
        logger.info(f"Running {digest_type} digest pipeline")

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
