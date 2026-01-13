"""
Temporal workflows for the news monitor.

Architecture:
- ArticleIngestionWorkflow: Collects and processes new articles (scheduled every 30min)
- DigestGenerationWorkflow: Generates digest from already-processed articles (scheduled every 4h)
- ProcessSingleArticleWorkflow: Child workflow for per-article processing

The ingestion and digest workflows are completely decoupled - ingestion stores
articles in Qdrant continuously, while digest queries and publishes periodically.
"""

import asyncio
from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    # Core activities for ingestion pipeline
    from news_monitor.activities import (
        check_and_alert_breaking,
        collect_rss_feeds,
        deduplicate_and_store_article,
        filter_seen_urls,
        process_single_article,
        query_recent_articles,
    )

    # Federated activities for digest generation
    from news_monitor.federated_activities import (
        analyze_trends,
        compose_digest,
        publish_digest,
    )


# =============================================================================
# Continuous Ingestion Workflows
# =============================================================================


@workflow.defn
class ProcessSingleArticleWorkflow:
    """
    Child workflow that processes a single article independently.

    Benefits:
    - 10-minute timeout for deduplication (vs 5 min per article in batch)
    - Independent retries per article
    - No batch timeout pressure
    - Breaking news detection during ingestion (fast path)
    """

    @workflow.run
    async def run(self, article_data: dict) -> dict | None:
        """
        Process a single article: analyze, deduplicate, store, check breaking.

        Args:
            article_data: Raw article dictionary

        Returns:
            Stored article dict if unique, None if duplicate
        """
        # Step 1: Process article (LLM analysis) - 5 min timeout
        processed = await workflow.execute_activity(
            process_single_article,
            args=[article_data],
            start_to_close_timeout=timedelta(minutes=5),
        )

        if not processed:
            workflow.logger.warning("Article processing failed")
            return None

        # Step 2: Deduplicate and store (10 min timeout for mem0 graph memory)
        # This is the slow operation that was causing timeouts
        stored = await workflow.execute_activity(
            deduplicate_and_store_article,
            args=[processed],
            start_to_close_timeout=timedelta(minutes=10),
        )

        if not stored:
            workflow.logger.debug("Article is duplicate")
            return None  # Duplicate

        # Step 3: Check for breaking news and alert immediately
        await workflow.execute_activity(
            check_and_alert_breaking,
            args=[stored],
            start_to_close_timeout=timedelta(minutes=2),
        )

        return stored


@workflow.defn
class ArticleIngestionWorkflow:
    """
    Workflow for continuous article ingestion.

    Collects articles from RSS feeds and spawns child workflows
    for each article, allowing independent processing with generous
    timeouts. This decouples ingestion from digest generation.
    """

    @workflow.run
    async def run(self, max_age_hours: int = 2) -> dict:
        """
        Ingest new articles from RSS feeds.

        Args:
            max_age_hours: Maximum age of articles to collect

        Returns:
            Summary of ingestion results
        """
        workflow.logger.info(f"Starting article ingestion (max age: {max_age_hours}h)")

        # 1. Collect from RSS feeds
        raw_articles = await workflow.execute_activity(
            collect_rss_feeds,
            args=[max_age_hours],
            start_to_close_timeout=timedelta(minutes=10),
        )

        if not raw_articles:
            return {"status": "no_articles", "ingested": 0}

        workflow.logger.info(f"Collected {len(raw_articles)} raw articles")

        # 2. Fast pre-filter with Redis (O(1) lookup per URL)
        new_articles = await workflow.execute_activity(
            filter_seen_urls,
            args=[raw_articles],
            start_to_close_timeout=timedelta(minutes=2),
        )

        if not new_articles:
            return {"status": "no_new_articles", "ingested": 0}

        workflow.logger.info(f"After URL filter: {len(new_articles)} new articles")

        # 3. Spawn child workflow for each article (parallel, independent timeouts)
        child_tasks = []
        for i, article in enumerate(new_articles):
            # Each article gets its own workflow with independent timeout
            task = workflow.execute_child_workflow(
                ProcessSingleArticleWorkflow.run,
                args=[article],
                id=f"process-article-{workflow.now().strftime('%Y%m%d-%H%M%S')}-{i}",
            )
            child_tasks.append(task)

        # 4. Wait for all child workflows to complete
        results = await asyncio.gather(*child_tasks, return_exceptions=True)

        # Count results
        ingested = sum(1 for r in results if r is not None and not isinstance(r, Exception))
        duplicates = sum(1 for r in results if r is None)
        errors = sum(1 for r in results if isinstance(r, Exception))

        # Log any errors
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                workflow.logger.warning(f"Article {i} failed: {r}")

        workflow.logger.info(
            f"Ingestion complete: {ingested} stored, {duplicates} duplicates, {errors} errors"
        )

        return {
            "status": "complete",
            "ingested": ingested,
            "duplicates": duplicates,
            "errors": errors,
            "total_collected": len(raw_articles),
        }


@workflow.defn
class DigestGenerationWorkflow:
    """
    Workflow for generating digests from already-ingested articles.

    Queries Qdrant for articles processed since the last digest,
    analyzes trends, and publishes. This is fast because articles
    are already processed - no LLM calls needed for deduplication.
    """

    @workflow.run
    async def run(self, period_hours: int = 4) -> dict:
        """
        Generate and publish a news digest.

        Args:
            period_hours: Hours of articles to include

        Returns:
            Published digest data
        """
        workflow.logger.info(f"Generating digest for last {period_hours} hours")

        # 1. Query recent articles from Qdrant (fast, no LLM calls)
        articles = await workflow.execute_activity(
            query_recent_articles,
            args=[period_hours],
            start_to_close_timeout=timedelta(minutes=2),
        )

        if not articles:
            return {"status": "no_articles", "message": "No articles in period"}

        workflow.logger.info(f"Found {len(articles)} articles for digest")

        # 2. Analyze trends
        trends = await workflow.execute_activity(
            analyze_trends,
            args=[articles],
            start_to_close_timeout=timedelta(minutes=5),
        )

        # 3. Compose digest (increased timeout for LLM deep dives)
        digest = await workflow.execute_activity(
            compose_digest,
            args=[articles, trends, period_hours],
            start_to_close_timeout=timedelta(minutes=15),
        )

        # 4. Publish to Discord
        result = await workflow.execute_activity(
            publish_digest,
            args=[digest],
            start_to_close_timeout=timedelta(minutes=2),
        )

        return result


@workflow.defn
class ScheduledArticleIngestionWorkflow:
    """
    Long-running workflow for scheduled article ingestion.

    Runs every 30 minutes to continuously ingest new articles.
    Uses continue-as-new pattern to avoid unbounded history.
    """

    @workflow.run
    async def run(self, interval_minutes: int = 30) -> str:
        """
        Run continuous article ingestion.

        Args:
            interval_minutes: Minutes between ingestion runs (default: 30)

        Returns:
            Status message
        """
        # Run the ingestion workflow
        await workflow.execute_child_workflow(
            ArticleIngestionWorkflow.run,
            args=[2],  # 2 hours lookback
            id=f"ingest-{workflow.now().strftime('%Y%m%d-%H%M')}",
        )

        # Wait for next interval
        await asyncio.sleep(interval_minutes * 60)

        # Continue as new for the next cycle
        workflow.continue_as_new(args=[interval_minutes])


@workflow.defn
class ScheduledDigestGenerationWorkflow:
    """
    Long-running workflow for scheduled digest generation.

    Runs every 4 hours to generate and publish digests from
    already-ingested articles. Uses continue-as-new pattern.
    """

    @workflow.run
    async def run(self, interval_hours: int = 4) -> str:
        """
        Run periodic digest generation.

        Args:
            interval_hours: Hours between digests (default: 4)

        Returns:
            Status message
        """
        # Run the digest generation workflow
        await workflow.execute_child_workflow(
            DigestGenerationWorkflow.run,
            args=[interval_hours],
            id=f"digest-{workflow.now().strftime('%Y%m%d-%H%M')}",
        )

        # Wait for next interval
        await asyncio.sleep(interval_hours * 3600)

        # Continue as new for the next cycle
        workflow.continue_as_new(args=[interval_hours])
