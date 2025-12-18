"""
Temporal workflows for the news monitor.

Defines the main workflow orchestration for collecting, processing,
and publishing AI news digests.
"""

import asyncio
from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from news_monitor.activities import (
        analyze_trends,
        check_breaking_news,
        collect_rss_feeds,
        compose_digest,
        deduplicate_articles,
        process_articles,
        publish_breaking_alert,
        publish_digest,
    )


@workflow.defn
class NewsDigestWorkflow:
    """
    Main workflow for generating and publishing news digests.

    Collects articles from RSS feeds, processes them, identifies trends,
    composes a digest, and publishes to Discord.
    """

    @workflow.run
    async def run(self, period_hours: int = 12) -> dict:
        """
        Execute the news digest workflow.

        Args:
            period_hours: Hours covered by this digest (default: 12)

        Returns:
            Published digest data
        """
        # 1. Collect from all RSS feeds
        raw_articles = await workflow.execute_activity(
            collect_rss_feeds,
            args=[period_hours],
            start_to_close_timeout=timedelta(minutes=10),
        )

        if not raw_articles:
            return {"status": "no_articles", "message": "No articles collected"}

        # 2. Process articles (summarize, categorize, etc.)
        processed_articles = await workflow.execute_activity(
            process_articles,
            args=[raw_articles],
            start_to_close_timeout=timedelta(minutes=15),
        )

        # 3. Check for breaking news (run in parallel with dedup)
        breaking_task = workflow.execute_activity(
            check_breaking_news,
            args=[processed_articles],
            start_to_close_timeout=timedelta(minutes=2),
        )

        # 4. Deduplicate against memory
        unique_articles = await workflow.execute_activity(
            deduplicate_articles,
            args=[processed_articles],
            start_to_close_timeout=timedelta(minutes=5),
        )

        # Get breaking news results
        breaking_articles = await breaking_task

        # 5. Publish breaking alerts immediately
        for article in breaking_articles:
            await workflow.execute_activity(
                publish_breaking_alert,
                args=[article],
                start_to_close_timeout=timedelta(minutes=2),
            )

        if not unique_articles:
            return {"status": "no_new_articles", "message": "No new unique articles"}

        # 6. Analyze trends
        trends = await workflow.execute_activity(
            analyze_trends,
            args=[unique_articles],
            start_to_close_timeout=timedelta(minutes=5),
        )

        # 7. Compose digest
        digest = await workflow.execute_activity(
            compose_digest,
            args=[unique_articles, trends, period_hours],
            start_to_close_timeout=timedelta(minutes=5),
        )

        # 8. Publish to Discord
        result = await workflow.execute_activity(
            publish_digest,
            args=[digest],
            start_to_close_timeout=timedelta(minutes=2),
        )

        return result


@workflow.defn
class ScheduledNewsDigestWorkflow:
    """
    Scheduled workflow that runs news digest at regular intervals.

    Uses Temporal's continue-as-new pattern to run indefinitely.
    """

    @workflow.run
    async def run(self, interval_hours: int = 12) -> str:
        """
        Run the scheduled news digest workflow.

        Args:
            interval_hours: Hours between digests (default: 12)

        Returns:
            Status message
        """
        # Run the digest workflow
        result = await workflow.execute_child_workflow(
            NewsDigestWorkflow.run,
            args=[interval_hours],
            id=f"news-digest-{workflow.now().strftime('%Y%m%d-%H%M')}",
        )

        # Wait for next interval
        await asyncio.sleep(interval_hours * 3600)

        # Continue as new for the next cycle
        workflow.continue_as_new(args=[interval_hours])


@workflow.defn
class BreakingNewsCheckWorkflow:
    """
    Lightweight workflow for checking breaking news more frequently.

    Can be run every hour to catch high-priority news between digests.
    """

    @workflow.run
    async def run(self) -> dict:
        """
        Check for breaking news and publish alerts.

        Returns:
            Result with count of alerts published
        """
        # Collect recent articles (last 2 hours only)
        raw_articles = await workflow.execute_activity(
            collect_rss_feeds,
            args=[2],  # Only last 2 hours
            start_to_close_timeout=timedelta(minutes=5),
        )

        if not raw_articles:
            return {"status": "no_articles", "alerts_published": 0}

        # Process articles
        processed_articles = await workflow.execute_activity(
            process_articles,
            args=[raw_articles],
            start_to_close_timeout=timedelta(minutes=10),
        )

        # Deduplicate
        unique_articles = await workflow.execute_activity(
            deduplicate_articles,
            args=[processed_articles],
            start_to_close_timeout=timedelta(minutes=3),
        )

        # Check for breaking news
        breaking_articles = await workflow.execute_activity(
            check_breaking_news,
            args=[unique_articles],
            start_to_close_timeout=timedelta(minutes=2),
        )

        # Publish alerts
        alerts_published = 0
        for article in breaking_articles:
            result = await workflow.execute_activity(
                publish_breaking_alert,
                args=[article],
                start_to_close_timeout=timedelta(minutes=2),
            )
            if result:
                alerts_published += 1

        return {
            "status": "complete",
            "articles_checked": len(unique_articles),
            "alerts_published": alerts_published,
        }


@workflow.defn
class ScheduledBreakingNewsWorkflow:
    """
    Scheduled workflow for frequent breaking news checks.

    Runs every hour to catch breaking news between digests.
    """

    @workflow.run
    async def run(self, interval_hours: int = 1) -> str:
        """
        Run scheduled breaking news checks.

        Args:
            interval_hours: Hours between checks (default: 1)

        Returns:
            Status message
        """
        # Run the breaking news check
        result = await workflow.execute_child_workflow(
            BreakingNewsCheckWorkflow.run,
            id=f"breaking-check-{workflow.now().strftime('%Y%m%d-%H%M')}",
        )

        # Wait for next interval
        await asyncio.sleep(interval_hours * 3600)

        # Continue as new
        workflow.continue_as_new(args=[interval_hours])
