"""
Temporal worker for the news monitor agent.

Starts a Temporal worker that polls for workflow and activity tasks
from the Temporal server.

Uses the generic AgentWorker class from core_agents for standardized
worker setup and command handling.

Architecture:
- Ingestion: Collects and processes articles from RSS feeds (scheduled every 30min)
- Digest: Generates and publishes digests from processed articles (scheduled every 4h)
- Explorer: Discovers new RSS sources based on coverage gaps (federated agent)
"""

import asyncio
import logging
import os
import sys

from core_agents.worker import (
    AgentCapabilityConfig,
    AgentWorker,
    AgentWorkerConfig,
    CommandConfig,
    ScheduledWorkflowConfig,
)

# Core activities that don't need skills (storage/query)
from news_monitor.activities import (
    query_recent_articles,
)

# Activities use federated agents for skills-based execution
from news_monitor.federated_activities import (
    analyze_articles_batch,
    analyze_single_article,
    analyze_trends,
    collect_articles,
    compose_digest,
    detect_breaking_news,
    publish_breaking_alert,
    publish_digest,
    run_full_pipeline,
)

# Workflows orchestrate activities
from news_monitor.workflows import (
    ArticleIngestionWorkflow,
    DigestGenerationWorkflow,
    ProcessSingleArticleWorkflow,
    ScheduledArticleIngestionWorkflow,
    ScheduledDigestGenerationWorkflow,
)

logger = logging.getLogger(__name__)

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
        from news_monitor.federated import run_news_explorer_cycle
    except ImportError as e:
        logger.error(f"Failed to import federated agents: {e}")
        logger.error("Federated agents will not run. Install required dependencies.")
        return

    logger.info("Starting NewsExplorerAgent (source discovery)...")

    while True:
        try:
            logger.info("Running NewsExplorer cycle...")
            proposals = await run_news_explorer_cycle()
            logger.info(
                f"NewsExplorer cycle completed: {len(proposals)} proposals. "
                f"Next run in {EXPLORER_CYCLE_HOURS}h"
            )
        except asyncio.CancelledError:
            logger.info("NewsExplorer cancelled")
            raise
        except Exception as e:
            logger.error(f"NewsExplorer cycle failed: {e}")

        await asyncio.sleep(EXPLORER_CYCLE_HOURS * 3600)


# =============================================================================
# Command Handlers
# =============================================================================


async def handle_ingest(worker: AgentWorker) -> None:
    """Handle 'ingest' command - run single article ingestion."""
    period = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    result = await worker.run_single_workflow(
        ArticleIngestionWorkflow,
        "ingest-singleton",
        args=[period],
        singleton=True,
    )
    logger.info(f"Ingestion completed: {result}")


async def handle_digest(worker: AgentWorker) -> None:
    """Handle 'digest' command - generate and publish digest from processed articles."""
    period = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    result = await worker.run_single_workflow(
        DigestGenerationWorkflow,
        "digest-singleton",
        args=[period],
        singleton=True,
    )
    logger.info(f"Digest completed: {result}")


async def handle_schedule_ingest(worker: AgentWorker) -> None:
    """Handle 'schedule-ingest' command - start scheduled article ingestion."""
    interval = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    sw_config = ScheduledWorkflowConfig(
        workflow_class=ScheduledArticleIngestionWorkflow,
        workflow_id="news-monitor-article-ingestion",
    )
    await worker.start_scheduled_workflow(sw_config, interval)


async def handle_schedule_digest(worker: AgentWorker) -> None:
    """Handle 'schedule-digest' command - start scheduled digest generation."""
    interval = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    sw_config = ScheduledWorkflowConfig(
        workflow_class=ScheduledDigestGenerationWorkflow,
        workflow_id="news-monitor-digest-generation",
    )
    await worker.start_scheduled_workflow(sw_config, interval)


async def handle_schedule(worker: AgentWorker) -> None:
    """Handle 'schedule' command - start both ingestion and digest workflows."""
    await handle_schedule_ingest(worker)
    await handle_schedule_digest(worker)


def create_worker() -> AgentWorker:
    """Create the news monitor worker."""
    agent_version = os.environ.get("AGENT_VERSION", "0.3.6")

    capabilities = [
        AgentCapabilityConfig(
            name="rss-ingestion",
            description="Collect and process articles from RSS feeds",
            tags=["news", "rss", "ingestion"],
        ),
        AgentCapabilityConfig(
            name="breaking-news-detection",
            description="Detect and alert on breaking news stories",
            tags=["news", "alerts", "breaking"],
        ),
        AgentCapabilityConfig(
            name="digest-generation",
            description="Generate periodic AI news digests with trend analysis",
            tags=["news", "digest", "trends"],
        ),
        AgentCapabilityConfig(
            name="source-discovery",
            description="Discover new RSS sources based on coverage gaps",
            tags=["news", "explorer", "sources"],
        ),
    ]

    config = AgentWorkerConfig(
        task_queue="news-monitor",
        name="news-monitor",
        description="AI news monitoring with trend analysis",
        agent_version=agent_version,
        agent_endpoint="http://news-monitor.ai-agents.svc:8000",
        capabilities=capabilities,
        enable_registry=os.environ.get("KUBANI_REGISTRY_ENABLED", "true").lower() == "true",
        workflows=[
            # Core workflows
            ArticleIngestionWorkflow,
            DigestGenerationWorkflow,
            ProcessSingleArticleWorkflow,
            # Scheduled wrappers
            ScheduledArticleIngestionWorkflow,
            ScheduledDigestGenerationWorkflow,
        ],
        activities=[
            # Federated activities (skills-based)
            collect_articles,
            analyze_single_article,
            analyze_articles_batch,
            detect_breaking_news,
            analyze_trends,
            compose_digest,
            publish_digest,
            publish_breaking_alert,
            run_full_pipeline,
            # Storage/query activities
            query_recent_articles,
        ],
        federated_agents_factory=start_federated_agents,
        custom_commands=[
            CommandConfig(
                name="ingest",
                description="Run single article ingestion",
                handler=handle_ingest,
                args=["hours"],
            ),
            CommandConfig(
                name="digest",
                description="Generate and publish digest",
                handler=handle_digest,
                args=["hours"],
            ),
            CommandConfig(
                name="schedule-ingest",
                description="Start scheduled ingestion (default: 30min)",
                handler=handle_schedule_ingest,
                args=["minutes"],
            ),
            CommandConfig(
                name="schedule-digest",
                description="Start scheduled digest (default: 4h)",
                handler=handle_schedule_digest,
                args=["hours"],
            ),
            CommandConfig(
                name="schedule",
                description="Start both ingestion and digest schedules",
                handler=handle_schedule,
            ),
        ],
    )
    return AgentWorker(config)


def main() -> None:
    """Main entry point for the worker."""
    worker = create_worker()
    worker.run()


if __name__ == "__main__":
    main()
