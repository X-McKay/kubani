"""
Temporal worker entry point for K8s Monitor Syndicate.

This module provides the main entry points for running the K8s Monitor:
- worker: Runs the Temporal worker that processes workflows
- schedule: Starts the scheduled health check workflow

Usage:
    # Start the worker
    k8s-monitor-worker

    # Start the scheduled workflow
    k8s-monitor-schedule
"""

import asyncio
import logging
import os
import sys

from temporalio.client import Client

from syndicates.k8s_monitor import K8sMonitorSyndicate

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def run_worker() -> None:
    """Run the K8s Monitor syndicate worker."""
    # Get Temporal connection settings
    temporal_host = os.environ.get("TEMPORAL_HOST", "localhost:7233")
    temporal_namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")

    logger.info(f"Connecting to Temporal at {temporal_host}")

    # Connect to Temporal
    client = await Client.connect(
        temporal_host,
        namespace=temporal_namespace,
    )

    # Create and start the syndicate
    syndicate = K8sMonitorSyndicate()

    logger.info(f"Starting {syndicate.name} v{syndicate.version}")
    logger.info(f"Agents: {[a.__name__ for a in syndicate.agents]}")

    try:
        await syndicate.start()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    finally:
        await syndicate.stop()


async def run_schedule() -> None:
    """Start the scheduled health check workflow."""
    temporal_host = os.environ.get("TEMPORAL_HOST", "localhost:7233")
    temporal_namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")
    interval_hours = int(os.environ.get("HEALTH_CHECK_INTERVAL_HOURS", "1"))

    logger.info(f"Connecting to Temporal at {temporal_host}")

    client = await Client.connect(
        temporal_host,
        namespace=temporal_namespace,
    )

    # Start the scheduled workflow
    # This is a placeholder - actual implementation would use Temporal schedules
    logger.info(f"Would start health check schedule (every {interval_hours}h)")
    logger.info("Schedule management not yet implemented in syndicate pattern")


def main() -> None:
    """Main entry point for worker."""
    asyncio.run(run_worker())


def schedule() -> None:
    """Entry point for starting schedules."""
    asyncio.run(run_schedule())


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "schedule":
        schedule()
    else:
        main()
