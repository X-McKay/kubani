"""
Worker entry point for cluster-monitor agent.

Runs the Correlator and Orchestrator services.
"""

import asyncio
import logging
import signal
import sys

from cluster_monitor.correlator import EventCorrelator
from cluster_monitor.orchestrator import InvestigationOrchestrator

logger = logging.getLogger(__name__)


async def run_services():
    """Run both Correlator and Orchestrator services concurrently."""
    correlator = EventCorrelator()
    orchestrator = InvestigationOrchestrator()

    # Run both services concurrently
    await asyncio.gather(
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

    logger.info("Starting cluster-monitor worker (Orchestrator-Worker architecture)")

    try:
        asyncio.run(run_services())
    except KeyboardInterrupt:
        logger.info("Shutting down cluster-monitor worker")
    except Exception as e:
        logger.error(f"Fatal error in cluster-monitor worker: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
