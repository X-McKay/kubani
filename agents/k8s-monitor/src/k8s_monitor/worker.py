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

from k8s_monitor.activities import collect_and_analyze_cluster, post_to_discord
from k8s_monitor.workflows import ClusterHealthCheckWorkflow, ScheduledHealthCheckWorkflow

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Task queue name for this agent
TASK_QUEUE = "k8s-monitor"


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

    logger.info(f"Starting worker on task queue: {TASK_QUEUE}")

    # Create and run the worker
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[
            ClusterHealthCheckWorkflow,
            ScheduledHealthCheckWorkflow,
        ],
        activities=[
            collect_and_analyze_cluster,
            post_to_discord,
        ],
    )

    logger.info("Worker started, polling for tasks...")
    await worker.run()


async def start_scheduled_workflow() -> None:
    """
    Start the scheduled health check workflow if not already running.

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

    workflow_id = "k8s-monitor-scheduled"

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

    logger.info(f"Starting scheduled health check workflow with {interval_hours}h interval")

    await client.start_workflow(
        ScheduledHealthCheckWorkflow.run,
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


def main() -> None:
    """
    Main entry point for the worker.

    Supports the following commands:
    - worker: Run the Temporal worker (default)
    - schedule: Start the scheduled workflow
    - check: Run a single health check
    """
    command = sys.argv[1] if len(sys.argv) > 1 else "worker"

    if command == "worker":
        asyncio.run(run_worker())
    elif command == "schedule":
        asyncio.run(start_scheduled_workflow())
    elif command == "check":
        asyncio.run(run_single_check())
    else:
        print(f"Unknown command: {command}")
        print("Usage: k8s-monitor-worker [worker|schedule|check]")
        sys.exit(1)


if __name__ == "__main__":
    main()
