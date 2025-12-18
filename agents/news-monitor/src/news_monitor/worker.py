"""
Temporal worker for the news monitor agent.

Starts a Temporal worker that polls for workflow and activity tasks
from the Temporal server.
"""

import asyncio
import logging
import os
import sys

from temporalio.client import Client
from temporalio.worker import Worker

from news_monitor.activities import (
    analyze_trends,
    check_breaking_news,
    collect_rss_feeds,
    compose_digest,
    deduplicate_articles,
    filter_seen_urls,
    process_articles,
    publish_breaking_alert,
    publish_digest,
)
from news_monitor.workflows import (
    BreakingNewsCheckWorkflow,
    NewsDigestWorkflow,
    ScheduledBreakingNewsWorkflow,
    ScheduledNewsDigestWorkflow,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Task queue name for this agent
TASK_QUEUE = "news-monitor"


async def run_worker() -> None:
    """
    Connect to Temporal and run the worker.

    The worker will poll for tasks on the news-monitor task queue
    and execute workflows and activities as assigned.
    """
    temporal_host = os.environ.get(
        "TEMPORAL_HOST",
        "temporal-frontend.temporal.svc.cluster.local:7233",
    )
    temporal_namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")

    logger.info(f"Connecting to Temporal at {temporal_host}")

    client = await Client.connect(
        temporal_host,
        namespace=temporal_namespace,
    )

    logger.info(f"Starting worker on task queue: {TASK_QUEUE}")

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[
            NewsDigestWorkflow,
            ScheduledNewsDigestWorkflow,
            BreakingNewsCheckWorkflow,
            ScheduledBreakingNewsWorkflow,
        ],
        activities=[
            collect_rss_feeds,
            filter_seen_urls,
            process_articles,
            deduplicate_articles,
            analyze_trends,
            compose_digest,
            publish_digest,
            check_breaking_news,
            publish_breaking_alert,
        ],
    )

    logger.info("Worker started, polling for tasks...")
    await worker.run()


async def start_scheduled_digest(interval_hours: int = 12) -> None:
    """
    Start the scheduled news digest workflow.

    Args:
        interval_hours: Hours between digests (default: 12)
    """
    temporal_host = os.environ.get(
        "TEMPORAL_HOST",
        "temporal-frontend.temporal.svc.cluster.local:7233",
    )
    temporal_namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")

    logger.info(f"Connecting to Temporal at {temporal_host}")

    client = await Client.connect(
        temporal_host,
        namespace=temporal_namespace,
    )

    workflow_id = "news-monitor-scheduled-digest"

    try:
        handle = client.get_workflow_handle(workflow_id)
        desc = await handle.describe()
        if desc.status.name == "RUNNING":
            logger.info(f"Scheduled digest workflow already running: {workflow_id}")
            return
    except Exception:
        pass

    logger.info(f"Starting scheduled digest workflow with {interval_hours}h interval")

    await client.start_workflow(
        ScheduledNewsDigestWorkflow.run,
        args=[interval_hours],
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )

    logger.info(f"Scheduled digest workflow started: {workflow_id}")


async def start_breaking_news_check(interval_hours: int = 1) -> None:
    """
    Start the scheduled breaking news check workflow.

    Args:
        interval_hours: Hours between checks (default: 1)
    """
    temporal_host = os.environ.get(
        "TEMPORAL_HOST",
        "temporal-frontend.temporal.svc.cluster.local:7233",
    )
    temporal_namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")

    client = await Client.connect(
        temporal_host,
        namespace=temporal_namespace,
    )

    workflow_id = "news-monitor-breaking-check"

    try:
        handle = client.get_workflow_handle(workflow_id)
        desc = await handle.describe()
        if desc.status.name == "RUNNING":
            logger.info(f"Breaking news check workflow already running: {workflow_id}")
            return
    except Exception:
        pass

    logger.info(f"Starting breaking news check workflow with {interval_hours}h interval")

    await client.start_workflow(
        ScheduledBreakingNewsWorkflow.run,
        args=[interval_hours],
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )

    logger.info(f"Breaking news check workflow started: {workflow_id}")


async def run_single_digest() -> None:
    """Run a single news digest (useful for testing)."""
    temporal_host = os.environ.get(
        "TEMPORAL_HOST",
        "temporal-frontend.temporal.svc.cluster.local:7233",
    )
    temporal_namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")

    client = await Client.connect(
        temporal_host,
        namespace=temporal_namespace,
    )

    logger.info("Starting single news digest workflow")

    handle = await client.start_workflow(
        NewsDigestWorkflow.run,
        args=[12],  # 12 hour lookback
        id=f"news-digest-manual-{asyncio.get_event_loop().time()}",
        task_queue=TASK_QUEUE,
    )

    result = await handle.result()
    logger.info(f"Digest completed: {result}")
    return result


def main() -> None:
    """
    Main entry point for the worker.

    Supports the following commands:
    - worker: Run the Temporal worker (default)
    - schedule: Start the scheduled digest workflow (12h)
    - schedule-breaking: Start the breaking news check (1h)
    - schedule-all: Start both scheduled workflows
    - digest: Run a single digest (for testing)
    """
    command = sys.argv[1] if len(sys.argv) > 1 else "worker"

    if command == "worker":
        asyncio.run(run_worker())
    elif command == "schedule":
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 12
        asyncio.run(start_scheduled_digest(interval))
    elif command == "schedule-breaking":
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        asyncio.run(start_breaking_news_check(interval))
    elif command == "schedule-all":
        async def start_all():
            await start_scheduled_digest(12)
            await start_breaking_news_check(1)
        asyncio.run(start_all())
    elif command == "digest":
        asyncio.run(run_single_digest())
    else:
        print(f"Unknown command: {command}")
        print("Usage: news-monitor-worker [worker|schedule|schedule-breaking|schedule-all|digest]")
        sys.exit(1)


if __name__ == "__main__":
    main()
