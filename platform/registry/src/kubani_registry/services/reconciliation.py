"""MCP server reconciliation service.

This service periodically reconciles the registry with the actual Kubernetes deployments.
It marks servers as inactive if they no longer exist in the cluster and removes entries
that have been inactive for more than 24 hours.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from kubernetes_asyncio import client, config
from sqlalchemy import select

from ..db import MCPServer
from ..db.session import get_session_factory

logger = logging.getLogger(__name__)

# Reconciliation interval in seconds
RECONCILIATION_INTERVAL = 300  # 5 minutes

# Time after which inactive servers are removed
INACTIVE_REMOVAL_THRESHOLD = timedelta(hours=24)

# Label selector for MCP server deployments
MCP_SERVER_LABEL = "mcp.kubani.io/server=true"


class ReconciliationService:
    """Service for reconciling MCP server registry with Kubernetes deployments."""

    def __init__(self):
        """Initialize the reconciliation service."""
        self.k8s_apps_v1: client.AppsV1Api | None = None
        self.running = False

    async def initialize(self) -> None:
        """Initialize Kubernetes client."""
        try:
            # Try to load in-cluster config first
            config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes configuration")
        except config.ConfigException:
            try:
                # Fall back to kubeconfig
                await config.load_kube_config()
                logger.info("Loaded Kubernetes configuration from kubeconfig")
            except config.ConfigException as e:
                logger.warning("Failed to load Kubernetes configuration: %s", e)
                logger.warning("Reconciliation service will not be able to query Kubernetes")
                return

        self.k8s_apps_v1 = client.AppsV1Api()

    async def get_mcp_deployments(self) -> set[str]:
        """
        Get all MCP server deployment names from Kubernetes.

        Returns:
            Set of MCP server IDs from deployment labels
        """
        if not self.k8s_apps_v1:
            logger.warning("Kubernetes client not initialized, skipping deployment query")
            return set()

        try:
            # Query all namespaces for MCP server deployments
            deployments = await self.k8s_apps_v1.list_deployment_for_all_namespaces(
                label_selector=MCP_SERVER_LABEL
            )

            mcp_server_ids = set()
            for deployment in deployments.items:
                # Extract MCP server ID from labels
                labels = deployment.metadata.labels or {}
                server_id = labels.get("mcp.kubani.io/server-id")
                if server_id:
                    mcp_server_ids.add(server_id)
                else:
                    # Fall back to deployment name if server-id label not present
                    # Remove common suffixes
                    name = deployment.metadata.name
                    if name.endswith("-server"):
                        name = name[: -len("-server")]
                    mcp_server_ids.add(name)

            logger.info("Found %d MCP server deployments in Kubernetes", len(mcp_server_ids))
            return mcp_server_ids

        except Exception as e:
            logger.error("Failed to query Kubernetes deployments: %s", e)
            return set()

    async def reconcile(self) -> None:
        """
        Reconcile registry with Kubernetes deployments.

        - Marks servers as inactive if they don't exist in Kubernetes
        - Removes servers that have been inactive for more than 24 hours
        """
        logger.info("Starting MCP server reconciliation")

        # Get active deployments from Kubernetes
        active_deployments = await self.get_mcp_deployments()

        # Get session factory
        session_factory = get_session_factory()
        async with session_factory() as session:
            # Get all registered MCP servers
            result = await session.execute(select(MCPServer))
            registered_servers = result.scalars().all()

            inactive_count = 0
            removed_count = 0
            now = datetime.now(timezone.utc)

            for server in registered_servers:
                # Check if server exists in Kubernetes
                if server.id not in active_deployments:
                    # Server not found in Kubernetes
                    if server.status != "inactive":
                        # Mark as inactive
                        logger.info(
                            "Marking MCP server %s as inactive (not found in cluster)",
                            server.id,
                        )
                        server.status = "inactive"
                        server.updated_at = now
                        inactive_count += 1
                    else:
                        # Already inactive, check if it should be removed
                        threshold = INACTIVE_REMOVAL_THRESHOLD
                        if server.updated_at and (now - server.updated_at) > threshold:
                            logger.info(
                                "Removing MCP server %s (inactive for more than 24 hours)",
                                server.id,
                            )
                            await session.delete(server)
                            removed_count += 1
                else:
                    # Server exists in Kubernetes, ensure it's not marked as inactive
                    if server.status == "inactive":
                        logger.info("Reactivating MCP server %s (found in cluster)", server.id)
                        server.status = "active"
                        server.updated_at = now

            # Commit changes
            await session.commit()

            logger.info(
                "Reconciliation complete: %d marked inactive, %d removed",
                inactive_count,
                removed_count,
            )

    async def run(self) -> None:
        """Run the reconciliation service in a loop."""
        self.running = True
        logger.info(
            "Starting reconciliation service (interval: %d seconds)",
            RECONCILIATION_INTERVAL,
        )

        while self.running:
            try:
                await self.reconcile()
            except Exception as e:
                logger.error("Error during reconciliation: %s", e, exc_info=True)

            # Wait for next interval
            await asyncio.sleep(RECONCILIATION_INTERVAL)

    def stop(self) -> None:
        """Stop the reconciliation service."""
        logger.info("Stopping reconciliation service")
        self.running = False


# Global reconciliation service instance
_reconciliation_service: ReconciliationService | None = None


async def start_reconciliation_service() -> asyncio.Task | None:
    """
    Start the reconciliation service as a background task.

    Returns:
        The asyncio Task running the service, or None if initialization failed
    """
    global _reconciliation_service

    _reconciliation_service = ReconciliationService()
    await _reconciliation_service.initialize()

    if _reconciliation_service.k8s_apps_v1:
        task = asyncio.create_task(_reconciliation_service.run())
        return task
    else:
        logger.warning("Reconciliation service not started (Kubernetes client unavailable)")
        return None


def stop_reconciliation_service() -> None:
    """Stop the reconciliation service."""
    global _reconciliation_service
    if _reconciliation_service:
        _reconciliation_service.stop()
