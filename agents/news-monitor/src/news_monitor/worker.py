"""
Temporal worker for the news monitor agent.

Starts a Temporal worker that polls for workflow and activity tasks
from the Temporal server.

Also runs federated agents for source discovery:
- NewsExplorerAgent: Discovers new RSS sources based on coverage gaps
"""

import asyncio
import logging
import os
import sys

from temporalio.client import Client
from temporalio.worker import Worker

from news_monitor.activities import (
    analyze_trends,
    check_and_alert_breaking,
    check_breaking_news,
    collect_rss_feeds,
    compose_digest,
    deduplicate_and_store_article,
    deduplicate_articles,
    deduplicate_single_article,
    filter_seen_urls,
    process_articles,
    process_single_article,
    publish_breaking_alert,
    publish_digest,
    query_recent_articles,
)
from news_monitor.workflows import (
    # New architecture: Continuous ingestion + Periodic digest
    ArticleIngestionWorkflow,
    # Legacy workflows (kept for backward compatibility)
    BreakingNewsCheckWorkflow,
    DigestGenerationWorkflow,
    NewsDigestWorkflow,
    ProcessSingleArticleWorkflow,
    ScheduledArticleIngestionWorkflow,
    ScheduledBreakingNewsWorkflow,
    ScheduledDigestGenerationWorkflow,
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

# Feature flag for federated agents
ENABLE_FEDERATED_AGENTS = os.environ.get("ENABLE_FEDERATED_AGENTS", "true").lower() == "true"

# Explorer cycle interval (how often to discover new sources)
EXPLORER_CYCLE_HOURS = int(os.environ.get("EXPLORER_CYCLE_HOURS", "24"))


async def start_federated_agents() -> None:
    """
    Start the federated news explorer agent.

    The NewsExplorerAgent:
    - Analyzes coverage gaps (topics with few sources)
    - Discovers new RSS sources using LLM
    - Validates proposed sources
    - Requests human approval via Discord
    - Emits NEWS_SOURCE_DISCOVERED events on approval
    """
    try:
        from news_monitor.federated import NewsExplorerAgent, run_news_explorer_cycle
    except ImportError as e:
        logger.error(f"Failed to import federated agents: {e}")
        logger.error("Federated agents will not run. Install required dependencies.")
        return

    explorer = NewsExplorerAgent()

    logger.info("Starting NewsExplorerAgent (source discovery)...")

    while True:
        try:
            logger.info("Running NewsExplorer cycle...")
            await run_news_explorer_cycle(explorer)
            logger.info(f"NewsExplorer cycle completed. Next run in {EXPLORER_CYCLE_HOURS}h")
        except asyncio.CancelledError:
            logger.info("NewsExplorer cancelled")
            raise
        except Exception as e:
            logger.error(f"NewsExplorer cycle failed: {e}")

        await asyncio.sleep(EXPLORER_CYCLE_HOURS * 3600)


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
            # Legacy workflows (kept for backward compatibility)
            NewsDigestWorkflow,
            ScheduledNewsDigestWorkflow,
            BreakingNewsCheckWorkflow,
            ScheduledBreakingNewsWorkflow,
            # New architecture: Continuous ingestion + Periodic digest
            ProcessSingleArticleWorkflow,
            ArticleIngestionWorkflow,
            DigestGenerationWorkflow,
            ScheduledArticleIngestionWorkflow,
            ScheduledDigestGenerationWorkflow,
        ],
        activities=[
            # Legacy activities
            collect_rss_feeds,
            filter_seen_urls,
            process_articles,
            deduplicate_articles,
            deduplicate_single_article,
            analyze_trends,
            compose_digest,
            publish_digest,
            check_breaking_news,
            publish_breaking_alert,
            # New activities for continuous ingestion
            process_single_article,
            deduplicate_and_store_article,
            check_and_alert_breaking,
            query_recent_articles,
        ],
    )

    logger.info("Worker started, polling for tasks...")

    # Start federated agents alongside the Temporal worker
    if ENABLE_FEDERATED_AGENTS:
        logger.info("Starting federated agents (NewsExplorer)...")
        federated_task = asyncio.create_task(start_federated_agents())
        try:
            await worker.run()
        finally:
            federated_task.cancel()
            try:
                await federated_task
            except asyncio.CancelledError:
                logger.info("Federated agents stopped")
    else:
        logger.info("Federated agents disabled (ENABLE_FEDERATED_AGENTS=false)")
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


# =============================================================================
# NEW ARCHITECTURE: Continuous Ingestion + Periodic Digest
# =============================================================================


async def start_article_ingestion(interval_minutes: int = 30) -> None:
    """
    Start the scheduled article ingestion workflow.

    This workflow runs continuously to ingest articles from RSS feeds,
    process them, and store in memory. Articles are processed with
    generous timeouts (10 min per article for deduplication).

    Args:
        interval_minutes: Minutes between ingestion runs (default: 30)
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

    workflow_id = "news-monitor-article-ingestion"

    try:
        handle = client.get_workflow_handle(workflow_id)
        desc = await handle.describe()
        if desc.status.name == "RUNNING":
            logger.info(f"Article ingestion workflow already running: {workflow_id}")
            return
    except Exception:
        pass

    logger.info(f"Starting article ingestion workflow with {interval_minutes}min interval")

    await client.start_workflow(
        ScheduledArticleIngestionWorkflow.run,
        args=[interval_minutes],
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )

    logger.info(f"Article ingestion workflow started: {workflow_id}")


async def start_digest_generation(interval_hours: int = 4) -> None:
    """
    Start the scheduled digest generation workflow.

    This workflow runs periodically to query already-ingested articles
    from Qdrant, analyze trends, and publish digests. This is fast
    because articles are already processed.

    Args:
        interval_hours: Hours between digests (default: 4)
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

    workflow_id = "news-monitor-digest-generation"

    try:
        handle = client.get_workflow_handle(workflow_id)
        desc = await handle.describe()
        if desc.status.name == "RUNNING":
            logger.info(f"Digest generation workflow already running: {workflow_id}")
            return
    except Exception:
        pass

    logger.info(f"Starting digest generation workflow with {interval_hours}h interval")

    await client.start_workflow(
        ScheduledDigestGenerationWorkflow.run,
        args=[interval_hours],
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )

    logger.info(f"Digest generation workflow started: {workflow_id}")


async def run_single_ingestion() -> None:
    """Run a single article ingestion (useful for testing)."""
    temporal_host = os.environ.get(
        "TEMPORAL_HOST",
        "temporal-frontend.temporal.svc.cluster.local:7233",
    )
    temporal_namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")

    client = await Client.connect(
        temporal_host,
        namespace=temporal_namespace,
    )

    logger.info("Starting single article ingestion workflow")

    handle = await client.start_workflow(
        ArticleIngestionWorkflow.run,
        args=[2],  # 2 hour lookback
        id=f"ingest-manual-{asyncio.get_event_loop().time()}",
        task_queue=TASK_QUEUE,
    )

    result = await handle.result()
    logger.info(f"Ingestion completed: {result}")
    return result


def main() -> None:
    """
    Main entry point for the worker.

    Supports the following commands:

    Worker:
    - worker: Run the Temporal worker (default)

    Legacy commands (batch processing):
    - schedule: Start the scheduled digest workflow (12h)
    - schedule-breaking: Start the breaking news check (1h)
    - schedule-all: Start both legacy scheduled workflows
    - digest: Run a single digest (for testing)

    New commands (continuous ingestion + periodic digest):
    - schedule-ingest: Start continuous article ingestion (every 30min)
    - schedule-digest: Start periodic digest generation (every 4h)
    - schedule-new: Start both new architecture workflows
    - ingest: Run a single article ingestion (for testing)
    """
    command = sys.argv[1] if len(sys.argv) > 1 else "worker"

    if command == "worker":
        asyncio.run(run_worker())

    # Legacy commands (batch processing)
    elif command == "schedule":
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 12
        asyncio.run(start_scheduled_digest(interval))
    elif command == "schedule-breaking":
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        asyncio.run(start_breaking_news_check(interval))
    elif command == "schedule-all":

        async def start_all_legacy():
            await start_scheduled_digest(12)
            await start_breaking_news_check(1)

        asyncio.run(start_all_legacy())
    elif command == "digest":
        asyncio.run(run_single_digest())

    # New commands (continuous ingestion + periodic digest)
    elif command == "schedule-ingest":
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 30
        asyncio.run(start_article_ingestion(interval))
    elif command == "schedule-digest":
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 4
        asyncio.run(start_digest_generation(interval))
    elif command == "schedule-new":

        async def start_all_new():
            await start_article_ingestion(30)  # Every 30 minutes
            await start_digest_generation(4)  # Every 4 hours

        asyncio.run(start_all_new())
    elif command == "ingest":
        asyncio.run(run_single_ingestion())

    elif command == "federated-only":
        # Run federated agents without Temporal worker
        asyncio.run(start_federated_agents())
    else:
        print(f"Unknown command: {command}")
        print("Usage: news-monitor-worker <command> [args]")
        print("")
        print("Commands:")
        print("  worker              Run Temporal worker + federated agents (default)")
        print("")
        print("  Legacy (batch processing):")
        print("  schedule [hours]    Start scheduled digest (default: 12h)")
        print("  schedule-breaking   Start breaking news check (1h)")
        print("  schedule-all        Start both legacy workflows")
        print("  digest              Run single digest (testing)")
        print("")
        print("  New (continuous ingestion + periodic digest):")
        print("  schedule-ingest [min]  Start article ingestion (default: 30min)")
        print("  schedule-digest [hrs]  Start digest generation (default: 4h)")
        print("  schedule-new           Start both new workflows")
        print("  ingest                 Run single ingestion (testing)")
        print("")
        print("  Federated agents:")
        print("  federated-only         Run only federated agents (NewsExplorer)")
        print("")
        print("Environment variables:")
        print("  ENABLE_FEDERATED_AGENTS  Enable federated agents (default: true)")
        print("  EXPLORER_CYCLE_HOURS     Explorer cycle interval (default: 24)")
        sys.exit(1)


if __name__ == "__main__":
    main()
