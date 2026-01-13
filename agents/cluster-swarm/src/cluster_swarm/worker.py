"""
Worker entry point for cluster-swarm agent.

Runs the Swarm service (uses shared Correlator from cluster-monitor).
"""

import asyncio
import logging
import signal
import sys

from cluster_swarm.swarm import ClusterSwarm

logger = logging.getLogger(__name__)


def handle_shutdown(sig, frame):
    """Handle shutdown signals gracefully."""
    logger.info(f"Received signal {sig}, shutting down...")
    sys.exit(0)


def main():
    """Main entry point for the cluster-swarm worker."""
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Handle shutdown signals
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    logger.info("Starting cluster-swarm worker (Swarm Intelligence architecture)")

    try:
        swarm = ClusterSwarm()
        asyncio.run(swarm.run())
    except KeyboardInterrupt:
        logger.info("Shutting down cluster-swarm worker")
    except Exception as e:
        logger.error(f"Fatal error in cluster-swarm worker: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
