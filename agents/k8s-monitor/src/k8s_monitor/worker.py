"""
Temporal worker for the Kubernetes monitoring agent.

This module starts a Temporal worker that polls for workflow and
activity tasks from the Temporal server.

Uses the generic AgentWorker class from core_agents for standardized
worker setup and command handling.

Also starts federated agents for Voyager-inspired learning:
- Sentinel: Watches K8s events, classifies using skills
- Healer: Remediates issues with verification
- Explorer: Learns new skills from failures
"""

import asyncio
import logging
import os

from temporalio.client import Client

from core_agents.worker import (
    AgentCapabilityConfig,
    AgentWorker,
    AgentWorkerConfig,
    CommandConfig,
    ScheduledWorkflowConfig,
)

logger = logging.getLogger(__name__)

# Explorer cycle interval (how often to analyze failed remediations)
EXPLORER_CYCLE_HOURS = int(os.environ.get("EXPLORER_CYCLE_HOURS", "6"))

# Old workflow IDs that should be terminated during migration
LEGACY_WORKFLOW_PATTERNS = [
    "cluster_health_check",  # Old snake_case naming (exact match is safe)
]


async def cleanup_legacy_workflows(client: Client) -> None:
    """
    Clean up old/legacy workflows that use deprecated naming conventions.

    This function runs on worker startup to terminate any workflows
    that were created with old naming patterns and are now stuck
    because the workflow classes have been renamed.

    Args:
        client: Temporal client connection
    """
    logger.info("Checking for legacy workflows to clean up...")

    for pattern in LEGACY_WORKFLOW_PATTERNS:
        try:
            query = f'WorkflowId STARTS_WITH "{pattern}"'
            workflows = [w async for w in client.list_workflows(query=query)]

            for workflow_exec in workflows:
                workflow_id = workflow_exec.id
                run_id = workflow_exec.run_id

                try:
                    handle = client.get_workflow_handle(workflow_id, run_id=run_id)
                    desc = await handle.describe()

                    if desc.status.name == "RUNNING":
                        logger.warning(
                            f"Terminating legacy workflow: {workflow_id} (pattern: {pattern})"
                        )
                        await handle.terminate(
                            reason=f"Legacy workflow cleanup: workflow name pattern "
                            f"'{pattern}' is deprecated"
                        )
                        logger.info(f"Successfully terminated: {workflow_id}")

                except Exception as e:
                    logger.warning(f"Could not terminate workflow {workflow_id}: {e}")

        except Exception as e:
            logger.warning(f"Error listing workflows for pattern '{pattern}': {e}")

    logger.info("Legacy workflow cleanup complete")


async def start_federated_agents() -> None:
    """
    Start the federated agent architecture.

    This runs:
    - Sentinel: Watches K8s events via MCP, publishes to event bus
    - Healer: Uses agent with MCP tools to investigate and fix issues
    - Explorer: Proposes new skills from failures

    These agents communicate via Redis Streams.
    """
    try:
        from k8s_monitor.federated import (
            ExplorerAgent,
            HealerAgent,
            SentinelAgent,
            WatchMode,
            run_explorer_cycle,
        )
    except ImportError as e:
        logger.error(f"Failed to import federated agents: {e}")
        logger.error("Federated agents will not run. Install required dependencies.")
        return

    # Create agents - use watch mode for real-time event detection
    sentinel = SentinelAgent(watch_mode=WatchMode.AUTO, poll_interval=30.0)
    healer = HealerAgent()
    explorer = ExplorerAgent()

    logger.info("Starting Sentinel (event watcher)...")
    logger.info("Starting Healer (agentic remediation)...")
    logger.info("Starting Explorer (skill learner)...")

    async def run_explorer_periodically():
        """Run explorer cycle periodically."""
        while True:
            try:
                await asyncio.sleep(EXPLORER_CYCLE_HOURS * 3600)
                logger.info("Running Explorer cycle...")
                await run_explorer_cycle(explorer)
                logger.info("Explorer cycle completed")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Explorer cycle failed: {e}")

    await asyncio.gather(
        sentinel.start(),
        healer.start(),
        run_explorer_periodically(),
        return_exceptions=True,
    )


# =============================================================================
# Custom Command Handlers
# =============================================================================


async def handle_schedule(worker: AgentWorker) -> None:
    """Handle 'schedule' command - scheduled health check (report-only)."""
    from k8s_monitor.workflows import ScheduledHealthCheckWorkflow

    interval = int(os.environ.get("HEALTH_CHECK_INTERVAL_HOURS", "1"))
    sw_config = ScheduledWorkflowConfig(
        workflow_class=ScheduledHealthCheckWorkflow,
        workflow_id="k8s-monitor-scheduled",
    )
    await worker.start_scheduled_workflow(sw_config, interval)


async def handle_check(worker: AgentWorker) -> None:
    """Handle 'check' command - single health check."""
    from k8s_monitor.workflows import ClusterHealthCheckWorkflow

    result = await worker.run_single_workflow(
        ClusterHealthCheckWorkflow,
        "health-check-manual",
    )
    logger.info(f"Health check completed: {result}")


def _get_workflows() -> list:
    """Get all workflows for the worker (lazy import to avoid lint issues)."""
    from k8s_monitor.orchestration_workflow import RemediationOrchestrationWorkflow
    from k8s_monitor.workflows import ClusterHealthCheckWorkflow, ScheduledHealthCheckWorkflow

    return [
        ClusterHealthCheckWorkflow,
        ScheduledHealthCheckWorkflow,
        # Orchestration workflow (Phase 5 consolidation)
        RemediationOrchestrationWorkflow,
    ]


def _get_activities() -> list:
    """Get all activities for the worker (lazy import to avoid lint issues)."""
    from k8s_monitor.activities import (
        collect_and_analyze_cluster,
        post_health_confirmation,
        post_to_discord,
    )
    from k8s_monitor.orchestration_activities import (
        analyze_issue,
        execute_remediation,
        investigate_issue,
        plan_remediation,
        post_stage_update,
        query_memory,
        store_learning,
        summarize_investigation,
        verify_remediation,
        wait_for_approval,
    )
    from k8s_monitor.workflow_health import (
        check_workflow_health,
        cleanup_workflow_issues,
        post_workflow_health_discord,
    )

    return [
        # Health check activities
        collect_and_analyze_cluster,
        post_health_confirmation,
        post_to_discord,
        # Workflow health monitoring
        check_workflow_health,
        cleanup_workflow_issues,
        post_workflow_health_discord,
        # Orchestration activities (Phase 5 consolidation)
        analyze_issue,
        execute_remediation,
        investigate_issue,
        plan_remediation,
        post_stage_update,
        query_memory,
        store_learning,
        summarize_investigation,
        verify_remediation,
        wait_for_approval,
    ]


def create_worker() -> AgentWorker:
    """Create the k8s-monitor worker."""
    # Agent version from environment (set by GitOps deployment)
    agent_version = os.environ.get("AGENT_VERSION", "0.2.23")

    # Define agent capabilities for registry
    capabilities = [
        AgentCapabilityConfig(
            name="cluster-health-check",
            description="Perform comprehensive Kubernetes cluster health checks",
            tags=["kubernetes", "health", "monitoring"],
        ),
        AgentCapabilityConfig(
            name="issue-remediation",
            description="Automatically detect and remediate cluster issues",
            tags=["kubernetes", "remediation", "automation"],
        ),
        AgentCapabilityConfig(
            name="event-monitoring",
            description="Watch and classify Kubernetes events in real-time",
            tags=["kubernetes", "events", "sentinel"],
        ),
        AgentCapabilityConfig(
            name="skill-learning",
            description="Learn new remediation skills from failures",
            tags=["learning", "explorer", "skills"],
        ),
        AgentCapabilityConfig(
            name="orchestrated-remediation",
            description="8-stage investigation pipeline with memory and learning",
            tags=["kubernetes", "remediation", "orchestration", "temporal"],
        ),
    ]

    config = AgentWorkerConfig(
        task_queue="k8s-monitor",
        name="k8s-monitor",
        description="Kubernetes cluster health monitoring agent with auto-remediation",
        # Registry integration
        agent_version=agent_version,
        agent_endpoint="http://k8s-monitor.ai-agents.svc:8000",
        capabilities=capabilities,
        enable_registry=os.environ.get("KUBANI_REGISTRY_ENABLED", "true").lower() == "true",
        workflows=_get_workflows(),
        activities=_get_activities(),
        federated_agents_factory=start_federated_agents,
        startup_hooks=[cleanup_legacy_workflows],
        custom_commands=[
            CommandConfig(
                name="schedule",
                description="Start scheduled health check (report-only)",
                handler=handle_schedule,
            ),
            CommandConfig(
                name="check",
                description="Run single health check",
                handler=handle_check,
            ),
            # NOTE: schedule-remediation and check-remediation removed
            # Federated agents (Healer) handle remediation via skills
        ],
    )
    return AgentWorker(config)


def main() -> None:
    """Main entry point for the worker."""
    worker = create_worker()
    worker.run()


if __name__ == "__main__":
    main()
