"""
Temporal worker for the news monitor agent.

Starts a Temporal worker that polls for workflow and activity tasks
from the Temporal server.

Uses the generic AgentWorker class from core_agents for standardized
worker setup and command handling.

Also runs federated agents for source discovery:
- NewsExplorerAgent: Discovers new RSS sources based on coverage gaps
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
from news_monitor.activities import analyze_trends as legacy_analyze_trends

# Legacy activities (kept for backward compatibility during migration)
from news_monitor.activities import (
    check_and_alert_breaking,
    check_breaking_news,
    collect_rss_feeds,
    deduplicate_and_store_article,
    deduplicate_articles,
    deduplicate_single_article,
    filter_seen_urls,
    process_articles,
    process_single_article,
    query_recent_articles,
)
from news_monitor.activities import compose_digest as legacy_compose_digest
from news_monitor.activities import publish_breaking_alert as legacy_publish_alert
from news_monitor.activities import publish_digest as legacy_publish_digest

# New federated activities (skills-based architecture)
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
# Custom Command Handlers
# =============================================================================


async def handle_schedule(worker: AgentWorker) -> None:
    """Handle 'schedule' command - legacy scheduled digest."""
    interval = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    sw_config = ScheduledWorkflowConfig(
        workflow_class=ScheduledNewsDigestWorkflow,
        workflow_id="news-monitor-scheduled-digest",
    )
    await worker.start_scheduled_workflow(sw_config, interval)


async def handle_schedule_breaking(worker: AgentWorker) -> None:
    """Handle 'schedule-breaking' command."""
    interval = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    sw_config = ScheduledWorkflowConfig(
        workflow_class=ScheduledBreakingNewsWorkflow,
        workflow_id="news-monitor-breaking-check",
    )
    await worker.start_scheduled_workflow(sw_config, interval)


async def handle_schedule_all(worker: AgentWorker) -> None:
    """Handle 'schedule-all' command - start both legacy workflows."""
    await handle_schedule(worker)
    await handle_schedule_breaking(worker)


async def handle_digest(worker: AgentWorker) -> None:
    """Handle 'digest' command - run single digest."""
    result = await worker.run_single_workflow(
        NewsDigestWorkflow,
        "news-digest-manual",
        args=[12],  # 12 hour lookback
    )
    logger.info(f"Digest completed: {result}")


async def handle_schedule_ingest(worker: AgentWorker) -> None:
    """Handle 'schedule-ingest' command."""
    interval = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    sw_config = ScheduledWorkflowConfig(
        workflow_class=ScheduledArticleIngestionWorkflow,
        workflow_id="news-monitor-article-ingestion",
    )
    await worker.start_scheduled_workflow(sw_config, interval)


async def handle_schedule_digest_gen(worker: AgentWorker) -> None:
    """Handle 'schedule-digest' command - periodic digest generation."""
    interval = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    sw_config = ScheduledWorkflowConfig(
        workflow_class=ScheduledDigestGenerationWorkflow,
        workflow_id="news-monitor-digest-generation",
    )
    await worker.start_scheduled_workflow(sw_config, interval)


async def handle_schedule_new(worker: AgentWorker) -> None:
    """Handle 'schedule-new' command - start new architecture workflows."""
    await handle_schedule_ingest(worker)
    await handle_schedule_digest_gen(worker)


async def handle_ingest(worker: AgentWorker) -> None:
    """Handle 'ingest' command - run single ingestion."""
    result = await worker.run_single_workflow(
        ArticleIngestionWorkflow,
        "ingest-manual",
        args=[2],  # 2 hour lookback
    )
    logger.info(f"Ingestion completed: {result}")


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
            # New federated activities (skills-based)
            collect_articles,
            analyze_single_article,
            analyze_articles_batch,
            detect_breaking_news,
            analyze_trends,
            compose_digest,
            publish_digest,
            publish_breaking_alert,
            run_full_pipeline,
            # Legacy activities (backward compatibility)
            collect_rss_feeds,
            filter_seen_urls,
            process_articles,
            deduplicate_articles,
            deduplicate_single_article,
            legacy_analyze_trends,
            legacy_compose_digest,
            legacy_publish_digest,
            check_breaking_news,
            legacy_publish_alert,
            process_single_article,
            deduplicate_and_store_article,
            check_and_alert_breaking,
            query_recent_articles,
        ],
        federated_agents_factory=start_federated_agents,
        custom_commands=[
            # Legacy commands (batch processing)
            CommandConfig(
                name="schedule",
                description="Start scheduled digest (default: 12h)",
                handler=handle_schedule,
                args=["hours"],
            ),
            CommandConfig(
                name="schedule-breaking",
                description="Start breaking news check (1h)",
                handler=handle_schedule_breaking,
                args=["hours"],
            ),
            CommandConfig(
                name="schedule-all",
                description="Start both legacy workflows",
                handler=handle_schedule_all,
            ),
            CommandConfig(
                name="digest",
                description="Run single digest (testing)",
                handler=handle_digest,
            ),
            # New commands (continuous ingestion + periodic digest)
            CommandConfig(
                name="schedule-ingest",
                description="Start article ingestion (default: 30min)",
                handler=handle_schedule_ingest,
                args=["minutes"],
            ),
            CommandConfig(
                name="schedule-digest",
                description="Start digest generation (default: 4h)",
                handler=handle_schedule_digest_gen,
                args=["hours"],
            ),
            CommandConfig(
                name="schedule-new",
                description="Start both new workflows",
                handler=handle_schedule_new,
            ),
            CommandConfig(
                name="ingest",
                description="Run single ingestion (testing)",
                handler=handle_ingest,
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
