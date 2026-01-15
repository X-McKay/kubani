"""
Worker entry point for cluster-monitor agent.

Runs the Sentinel, Correlator, and Orchestrator services.

Architecture:
- Sentinel: Watches Kubernetes events, classifies and publishes K8S_ISSUE_DETECTED
- Correlator: Groups related events and publishes K8S_INVESTIGATION_REQUESTED
- Orchestrator: Conducts investigations and posts updates to Discord
"""

import asyncio
import logging
import signal
import sys

from cluster_monitor.correlator import EventCorrelator
from cluster_monitor.orchestrator import InvestigationOrchestrator
from cluster_monitor.sentinel import SentinelService

logger = logging.getLogger(__name__)


async def run_services():
    """Run Sentinel, Correlator, and Orchestrator services concurrently."""
    sentinel = SentinelService()
    correlator = EventCorrelator()
    orchestrator = InvestigationOrchestrator()

    # Run all three services concurrently
    await asyncio.gather(
        sentinel.run(),
        correlator.run(),
        orchestrator.run(),
    )


def handle_shutdown(sig, frame):
    """Handle shutdown signals gracefully."""
    logger.info(f"Received signal {sig}, shutting down...")
    sys.exit(0)


def main():
    """Main entry point for the cluster-monitor worker."""
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Handle shutdown signals
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    logger.info("Starting cluster-monitor worker (Sentinel → Correlator → Orchestrator)")

    try:
        asyncio.run(run_services())
    except KeyboardInterrupt:
        logger.info("Shutting down cluster-monitor worker")
    except Exception as e:
        logger.error(f"Fatal error in cluster-monitor worker: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
