"""
Temporal worker for the Kubernetes monitoring agent.

This module starts a Temporal worker that polls for workflow and
activity tasks from the Temporal server.
"""

import asyncio
import logging
import os
import sys

from temporalio.client import Client
from temporalio.worker import Worker

from k8s_monitor.activities import (
    collect_and_analyze_cluster,
    post_health_confirmation,
    post_to_discord,
)
from k8s_monitor.remediation_activities import (
    attempt_fix_activity,
    investigate_issue_activity,
    post_remediation_discord,
    store_remediation_memory_activity,
    verify_issue_resolved,
)
from k8s_monitor.remediation_workflows import (
    HealthCheckWithRemediationWorkflow,
    IssueRemediationWorkflow,
    ScheduledHealthCheckWithRemediationWorkflow,
)
from k8s_monitor.workflow_health import (
    check_workflow_health,
    cleanup_workflow_issues,
    post_workflow_health_discord,
)
from k8s_monitor.workflows import ClusterHealthCheckWorkflow, ScheduledHealthCheckWorkflow

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Task queue name for this agent
TASK_QUEUE = "k8s-monitor"

# Old workflow IDs that should be terminated during migration
# These are workflows created with old naming conventions that are no longer valid
# Note: Migration completed. Only add exact workflow IDs here to avoid matching valid workflows.
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
            # List workflows matching the pattern
            query = f'WorkflowId STARTS_WITH "{pattern}"'
            workflows = [w async for w in client.list_workflows(query=query)]

            for workflow_exec in workflows:
                workflow_id = workflow_exec.id
                run_id = workflow_exec.run_id

                try:
                    handle = client.get_workflow_handle(workflow_id, run_id=run_id)
                    desc = await handle.describe()

                    # Only terminate if still running
                    if desc.status.name == "RUNNING":
                        logger.warning(
                            f"Terminating legacy workflow: {workflow_id} "
                            f"(pattern: {pattern})"
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


async def run_worker() -> None:
    """
    Connect to Temporal and run the worker.

    The worker will poll for tasks on the k8s-monitor task queue
    and execute workflows and activities as assigned.
    """
    # Get Temporal connection settings from environment
    temporal_host = os.environ.get(
        "TEMPORAL_HOST",
        "temporal-frontend.temporal.svc.cluster.local:7233",
    )
    temporal_namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")

    logger.info(f"Connecting to Temporal at {temporal_host}")

    # Connect to Temporal
    client = await Client.connect(
        temporal_host,
        namespace=temporal_namespace,
    )

    # Run migration/cleanup before starting worker
    await cleanup_legacy_workflows(client)

    logger.info(f"Starting worker on task queue: {TASK_QUEUE}")

    # Create and run the worker
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[
            ClusterHealthCheckWorkflow,
            ScheduledHealthCheckWorkflow,
            IssueRemediationWorkflow,
            HealthCheckWithRemediationWorkflow,
            ScheduledHealthCheckWithRemediationWorkflow,
        ],
        activities=[
            collect_and_analyze_cluster,
            post_health_confirmation,
            post_to_discord,
            investigate_issue_activity,
            attempt_fix_activity,
            verify_issue_resolved,
            post_remediation_discord,
            store_remediation_memory_activity,
            # Workflow health monitoring
            check_workflow_health,
            cleanup_workflow_issues,
            post_workflow_health_discord,
        ],
    )

    logger.info("Worker started, polling for tasks...")
    await worker.run()


async def start_scheduled_workflow(with_remediation: bool = False) -> None:
    """
    Start the scheduled health check workflow if not already running.

    Args:
        with_remediation: If True, start the workflow with auto-remediation enabled.

    This is typically called once on deployment to start the hourly
    health check schedule.
    """
    temporal_host = os.environ.get(
        "TEMPORAL_HOST",
        "temporal-frontend.temporal.svc.cluster.local:7233",
    )
    temporal_namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")
    interval_hours = int(os.environ.get("HEALTH_CHECK_INTERVAL_HOURS", "1"))

    logger.info(f"Connecting to Temporal at {temporal_host}")

    client = await Client.connect(
        temporal_host,
        namespace=temporal_namespace,
    )

    workflow_id = "k8s-monitor-scheduled" + ("-remediation" if with_remediation else "")
    workflow_class = (
        ScheduledHealthCheckWithRemediationWorkflow
        if with_remediation
        else ScheduledHealthCheckWorkflow
    )

    try:
        # Check if workflow is already running
        handle = client.get_workflow_handle(workflow_id)
        desc = await handle.describe()
        if desc.status.name == "RUNNING":
            logger.info(f"Scheduled workflow already running: {workflow_id}")
            return
    except Exception:
        # Workflow doesn't exist, we'll create it
        pass

    mode = "with auto-remediation" if with_remediation else "report-only"
    logger.info(
        f"Starting scheduled health check workflow ({mode}) with {interval_hours}h interval"
    )

    await client.start_workflow(
        workflow_class.run,
        interval_hours,
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )

    logger.info(f"Scheduled workflow started: {workflow_id}")


async def run_single_check() -> None:
    """
    Run a single health check (useful for testing).
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

    logger.info("Starting single health check workflow")

    handle = await client.start_workflow(
        ClusterHealthCheckWorkflow.run,
        id=f"health-check-manual-{asyncio.get_event_loop().time()}",
        task_queue=TASK_QUEUE,
    )

    result = await handle.result()
    logger.info(f"Health check completed: {result}")
    return result


async def run_single_check_with_remediation() -> None:
    """
    Run a single health check with auto-remediation (useful for testing).
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

    logger.info("Starting single health check with remediation workflow")

    handle = await client.start_workflow(
        HealthCheckWithRemediationWorkflow.run,
        id=f"health-check-remediation-manual-{asyncio.get_event_loop().time()}",
        task_queue=TASK_QUEUE,
    )

    result = await handle.result()
    logger.info(f"Health check with remediation completed: {result}")
    return result


def main() -> None:
    """
    Main entry point for the worker.

    Supports the following commands:
    - worker: Run the Temporal worker (default)
    - schedule: Start the scheduled workflow (report-only)
    - schedule-remediation: Start the scheduled workflow with auto-remediation
    - check: Run a single health check (report-only)
    - check-remediation: Run a single health check with auto-remediation
    """
    command = sys.argv[1] if len(sys.argv) > 1 else "worker"

    if command == "worker":
        asyncio.run(run_worker())
    elif command == "schedule":
        asyncio.run(start_scheduled_workflow(with_remediation=False))
    elif command == "schedule-remediation":
        asyncio.run(start_scheduled_workflow(with_remediation=True))
    elif command == "check":
        asyncio.run(run_single_check())
    elif command == "check-remediation":
        asyncio.run(run_single_check_with_remediation())
    else:
        print(f"Unknown command: {command}")
        print(
            "Usage: k8s-monitor-worker [worker|schedule|schedule-remediation|check|check-remediation]"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
