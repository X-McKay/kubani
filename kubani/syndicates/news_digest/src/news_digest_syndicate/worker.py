"""Temporal worker entry point for News Digest Syndicate.

This module provides the main entry points for running the News Digest:
- worker: Runs the Temporal worker that processes workflows
- schedules: Creates and manages Temporal schedules

The News Digest uses a three-stage pipeline:

Stage 1 — Ingest (source-specific schedules):
    - RSSIngestWorkflow: Every 30 minutes
    - ArxivIngestWorkflow: Every 4 hours
    - GitHubIngestWorkflow: Every 6 hours

Stage 2 — Analyze:
    - AnalyzeDocumentWorkflow: Triggered by ingest workflows (no schedule)

Stage 3 — Digest:
    - NewsDigestWorkflow: 9 AM and 9 PM daily

Usage:
    # Start the worker
    news-digest-worker

    # Initialize schedules (one-time setup)
    news-digest-schedules setup

Architecture:
    All workflows run on the same task queue. Ingest workflows are
    independently scheduled at frequencies tuned to each source's
    update cadence. The analyze workflow is triggered programmatically
    after each ingest completes. The digest workflow runs on a fixed
    schedule to compose and publish the final output.
"""

import asyncio
import logging
import os
import sys

from temporalio.client import Client
from temporalio.worker import Worker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# =============================================================================
# Worker Configuration
# =============================================================================

TEMPORAL_NAMESPACE = "news-digest"
TASK_QUEUE = "news-digest"


def get_temporal_settings() -> tuple[str, str]:
    """Get Temporal connection settings from environment.

    Returns:
        tuple of (host, namespace)
    """
    host = os.environ.get("TEMPORAL_HOST", "localhost:7233")
    namespace = os.environ.get("TEMPORAL_NAMESPACE", TEMPORAL_NAMESPACE)
    return host, namespace


# =============================================================================
# Activity Registration
# =============================================================================


def get_activities() -> list:
    """Get all activities needed by the pipeline workflows.

    Returns activities from both the framework (shared) and the
    syndicate-specific activities module.
    """
    # Framework activities (shared across syndicates)
    from kubani.framework.temporal import (
        collect_feeds_activity,
        publish_ui_activity,
        run_agent_activity,
        send_breaking_news_activity,
    )

    # Syndicate-specific pipeline activities
    from kubani.syndicates.news_digest.activities import (
        analyze_document_activity,
        batch_check_duplicates_activity,
        fetch_article_content_activity,
        publish_digest_to_discord_activity,
        query_analyzed_documents_activity,
        store_analyzed_document_activity,
        store_raw_documents_activity,
    )

    return [
        # Framework activities
        run_agent_activity,
        collect_feeds_activity,
        send_breaking_news_activity,
        publish_ui_activity,
        # Pipeline activities
        batch_check_duplicates_activity,
        store_raw_documents_activity,
        fetch_article_content_activity,
        analyze_document_activity,
        store_analyzed_document_activity,
        query_analyzed_documents_activity,
        publish_digest_to_discord_activity,
    ]


# =============================================================================
# Workflow Registration
# =============================================================================


def get_workflows() -> list:
    """Get all workflows for this syndicate."""
    from kubani.syndicates.news_digest.workflows import (
        AnalyzeDocumentWorkflow,
        ArxivIngestWorkflow,
        GitHubIngestWorkflow,
        NewsDigestWorkflow,
        RSSIngestWorkflow,
    )

    return [
        # Stage 1: Ingest
        RSSIngestWorkflow,
        ArxivIngestWorkflow,
        GitHubIngestWorkflow,
        # Stage 2: Analyze
        AnalyzeDocumentWorkflow,
        # Stage 3: Digest
        NewsDigestWorkflow,
    ]


# =============================================================================
# Worker Entry Point
# =============================================================================


async def run_worker() -> None:
    """Run the News Digest syndicate worker.

    Processes all three pipeline stages on the same task queue.
    """
    temporal_host, temporal_namespace = get_temporal_settings()

    logger.info(f"Connecting to Temporal at {temporal_host}")
    logger.info(f"Namespace: {temporal_namespace}")
    logger.info(f"Task queue: {TASK_QUEUE}")

    client = await Client.connect(
        temporal_host,
        namespace=temporal_namespace,
    )

    workflows = get_workflows()
    activities = get_activities()

    logger.info(f"Registering {len(workflows)} workflows: {[w.__name__ for w in workflows]}")
    logger.info(f"Registering {len(activities)} activities")

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=workflows,
        activities=activities,
    )

    logger.info("Starting News Digest worker...")

    try:
        await worker.run()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    finally:
        logger.info("Worker shutdown complete")


# =============================================================================
# Schedule Management
# =============================================================================


async def setup_schedules() -> None:
    """Create Temporal schedules for the News Digest pipeline.

    Creates four schedules, each tuned to the update frequency of its source:

    1. RSS Ingest: Every 30 minutes (RSS feeds update frequently)
    2. arXiv Ingest: Every 4 hours (arXiv publishes daily)
    3. GitHub Ingest: Every 6 hours (trending repos change slowly)
    4. News Digest: 9 AM and 9 PM daily (human consumption cadence)

    The AnalyzeDocumentWorkflow is NOT scheduled — it is triggered
    programmatically by each ingest workflow after it completes.
    """
    from kubani.framework.temporal import (
        CRON_TWICE_DAILY_9AM_9PM,
        EVERY_6_HOURS,
        EVERY_30_MINUTES,
        ScheduleConfig,
        setup_syndicate_schedules,
    )
    from kubani.syndicates.news_digest.workflows import (
        ArxivIngestWorkflow,
        GitHubIngestWorkflow,
        NewsDigestWorkflow,
        RSSIngestWorkflow,
    )

    temporal_host, temporal_namespace = get_temporal_settings()

    logger.info(f"Connecting to Temporal at {temporal_host}")

    client = await Client.connect(
        temporal_host,
        namespace=temporal_namespace,
    )

    EVERY_4_HOURS = 240  # minutes

    schedules = [
        # Stage 1: RSS Ingest — every 30 minutes
        ScheduleConfig(
            schedule_id="news-rss-ingest-schedule",
            workflow_type=RSSIngestWorkflow,
            workflow_id_prefix="news-rss-ingest",
            task_queue=TASK_QUEUE,
            workflow_input=None,
            interval_minutes=EVERY_30_MINUTES,
            memo={"syndicate": "news-digest", "workflow": "rss-ingest", "stage": "ingest"},
        ),
        # Stage 1: arXiv Ingest — every 4 hours
        ScheduleConfig(
            schedule_id="news-arxiv-ingest-schedule",
            workflow_type=ArxivIngestWorkflow,
            workflow_id_prefix="news-arxiv-ingest",
            task_queue=TASK_QUEUE,
            workflow_input=None,
            interval_minutes=EVERY_4_HOURS,
            memo={"syndicate": "news-digest", "workflow": "arxiv-ingest", "stage": "ingest"},
        ),
        # Stage 1: GitHub Ingest — every 6 hours
        ScheduleConfig(
            schedule_id="news-github-ingest-schedule",
            workflow_type=GitHubIngestWorkflow,
            workflow_id_prefix="news-github-ingest",
            task_queue=TASK_QUEUE,
            workflow_input=None,
            interval_minutes=EVERY_6_HOURS,
            memo={"syndicate": "news-digest", "workflow": "github-ingest", "stage": "ingest"},
        ),
        # Stage 3: Digest — twice daily at 9 AM and 9 PM
        ScheduleConfig(
            schedule_id="news-digest-schedule",
            workflow_type=NewsDigestWorkflow,
            workflow_id_prefix="news-digest",
            task_queue=TASK_QUEUE,
            workflow_input=None,
            cron_expression=CRON_TWICE_DAILY_9AM_9PM,
            memo={"syndicate": "news-digest", "workflow": "digest", "stage": "digest"},
        ),
    ]

    results = await setup_syndicate_schedules("news-digest", schedules, client)

    for schedule_id, status in results.items():
        logger.info(f"Schedule {schedule_id}: {status}")

    logger.info("Schedule setup complete")


async def teardown_schedules() -> None:
    """Remove all News Digest schedules."""
    from kubani.framework.temporal import teardown_syndicate_schedules

    temporal_host, temporal_namespace = get_temporal_settings()

    client = await Client.connect(
        temporal_host,
        namespace=temporal_namespace,
    )

    schedule_ids = [
        "news-rss-ingest-schedule",
        "news-arxiv-ingest-schedule",
        "news-github-ingest-schedule",
        "news-digest-schedule",
    ]

    results = await teardown_syndicate_schedules(schedule_ids, client)

    for schedule_id, success in results.items():
        status = "removed" if success else "not found"
        logger.info(f"Schedule {schedule_id}: {status}")


async def list_schedules() -> None:
    """List current News Digest schedules."""
    from kubani.framework.temporal import get_schedule_info

    temporal_host, temporal_namespace = get_temporal_settings()

    client = await Client.connect(
        temporal_host,
        namespace=temporal_namespace,
    )

    schedule_ids = [
        "news-rss-ingest-schedule",
        "news-arxiv-ingest-schedule",
        "news-github-ingest-schedule",
        "news-digest-schedule",
    ]

    for schedule_id in schedule_ids:
        info = await get_schedule_info(schedule_id, client)
        if info:
            logger.info(f"\n{schedule_id}:")
            logger.info(f"  Paused: {info['paused']}")
            logger.info(f"  Actions: {info['num_actions']}")
            logger.info(f"  Next: {info['next_action_times']}")
        else:
            logger.info(f"\n{schedule_id}: Not found")


# =============================================================================
# CLI Entry Points
# =============================================================================


def main() -> None:
    """Main entry point for worker."""
    asyncio.run(run_worker())


def schedules() -> None:
    """Entry point for schedule management."""
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "setup":
            asyncio.run(setup_schedules())
        elif cmd == "teardown":
            asyncio.run(teardown_schedules())
        elif cmd == "list":
            asyncio.run(list_schedules())
        else:
            print(f"Unknown command: {cmd}")
            print("Usage: news-digest-schedules [setup|teardown|list]")
            sys.exit(1)
    else:
        # Default to setup
        asyncio.run(setup_schedules())


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "schedules":
        sys.argv = sys.argv[1:]
        schedules()
    else:
        main()
