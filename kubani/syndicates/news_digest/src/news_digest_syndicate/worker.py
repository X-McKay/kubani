"""Temporal worker entry point for News Digest Syndicate.

This module provides the main entry points for running the News Digest:
- worker: Runs the Temporal worker that processes workflows
- schedules: Creates and manages Temporal schedules

The News Digest uses two workflows:
- NewsCollectionWorkflow: Runs every 15 minutes to collect articles
- NewsDigestWorkflow: Runs 2x/day to compose and publish digests

Usage:
    # Start the worker
    news-digest-worker

    # Initialize schedules (one-time setup)
    news-digest-schedules

Architecture:
    The worker runs both workflows on the same task queue.
    Schedules are created separately and trigger workflow executions.
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

# Each syndicate has its own Temporal namespace for isolation
TEMPORAL_NAMESPACE = "news-digest"
TASK_QUEUE = "news-digest"


def get_temporal_settings() -> tuple[str, str]:
    """Get Temporal connection settings from environment.

    Returns:
        tuple of (host, namespace)
        - Host defaults to localhost:7233
        - Namespace defaults to 'news-digest' (syndicate-specific)
    """
    host = os.environ.get("TEMPORAL_HOST", "localhost:7233")
    # Allow override but default to syndicate-specific namespace
    namespace = os.environ.get("TEMPORAL_NAMESPACE", TEMPORAL_NAMESPACE)
    return host, namespace


# =============================================================================
# Activity Registration
# =============================================================================


def get_activities() -> list:
    """Get all activities needed by the workflows."""
    from kubani.framework.temporal import (
        check_article_exists_activity,
        check_repo_exists_activity,
        collect_feeds_activity,
        query_articles_activity,
        query_knowledge_activity,
        run_agent_activity,
        send_breaking_news_activity,
        store_article_activity,
        store_knowledge_activity,
        store_repo_activity,
        store_trend_snapshot_activity,
    )

    return [
        run_agent_activity,
        collect_feeds_activity,
        store_article_activity,
        check_article_exists_activity,
        query_articles_activity,
        store_knowledge_activity,
        query_knowledge_activity,
        store_trend_snapshot_activity,
        send_breaking_news_activity,
        # Repo activities
        store_repo_activity,
        check_repo_exists_activity,
    ]


# =============================================================================
# Workflow Registration
# =============================================================================


def get_workflows() -> list:
    """Get all workflows for this syndicate."""
    from kubani.syndicates.news_digest.workflows import (
        NewsCollectionWorkflow,
        NewsDigestWorkflow,
    )

    return [
        NewsCollectionWorkflow,
        NewsDigestWorkflow,
    ]


# =============================================================================
# Worker Entry Point
# =============================================================================


async def run_worker() -> None:
    """Run the News Digest syndicate worker.

    This worker processes both NewsCollectionWorkflow and NewsDigestWorkflow
    on the news-digest task queue.
    """
    temporal_host, temporal_namespace = get_temporal_settings()

    logger.info(f"Connecting to Temporal at {temporal_host}")
    logger.info(f"Namespace: {temporal_namespace}")
    logger.info(f"Task queue: {TASK_QUEUE}")

    # Connect to Temporal
    client = await Client.connect(
        temporal_host,
        namespace=temporal_namespace,
    )

    # Get workflows and activities
    workflows = get_workflows()
    activities = get_activities()

    logger.info(f"Registering {len(workflows)} workflows: {[w.__name__ for w in workflows]}")
    logger.info(f"Registering {len(activities)} activities")

    # Create and run the worker
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
    """Create Temporal schedules for the News Digest workflows.

    Creates two schedules:
    1. news-collection-schedule: Every 15 minutes
    2. news-digest-schedule: 9 AM and 9 PM daily
    """
    from kubani.framework.temporal import (
        CRON_TWICE_DAILY_9AM_9PM,
        EVERY_15_MINUTES,
        ScheduleConfig,
        setup_syndicate_schedules,
    )
    from kubani.syndicates.news_digest.workflows import (
        NewsCollectionWorkflow,
        NewsDigestWorkflow,
    )

    temporal_host, temporal_namespace = get_temporal_settings()

    logger.info(f"Connecting to Temporal at {temporal_host}")

    client = await Client.connect(
        temporal_host,
        namespace=temporal_namespace,
    )

    # Define schedules
    schedules = [
        # Collection runs every 15 minutes
        ScheduleConfig(
            schedule_id="news-collection-schedule",
            workflow_type=NewsCollectionWorkflow,
            workflow_id_prefix="news-collection",
            task_queue=TASK_QUEUE,
            workflow_input=None,  # Uses default CollectionInput
            interval_minutes=EVERY_15_MINUTES,
            memo={"syndicate": "news-digest", "workflow": "collection"},
        ),
        # Digest runs twice daily at 9 AM and 9 PM
        ScheduleConfig(
            schedule_id="news-digest-schedule",
            workflow_type=NewsDigestWorkflow,
            workflow_id_prefix="news-digest",
            task_queue=TASK_QUEUE,
            workflow_input=None,  # Uses default DigestInput
            cron_expression=CRON_TWICE_DAILY_9AM_9PM,
            memo={"syndicate": "news-digest", "workflow": "digest"},
        ),
    ]

    # Create schedules
    results = await setup_syndicate_schedules("news-digest", schedules, client)

    for schedule_id, status in results.items():
        logger.info(f"Schedule {schedule_id}: {status}")

    logger.info("Schedule setup complete")


async def teardown_schedules() -> None:
    """Remove News Digest schedules."""
    from kubani.framework.temporal import teardown_syndicate_schedules

    temporal_host, temporal_namespace = get_temporal_settings()

    client = await Client.connect(
        temporal_host,
        namespace=temporal_namespace,
    )

    schedule_ids = [
        "news-collection-schedule",
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
        "news-collection-schedule",
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
        sys.argv = sys.argv[1:]  # Remove 'schedules' from args
        schedules()
    else:
        main()
