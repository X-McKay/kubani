"""
Temporal workflow helpers for Kubani agents.

Provides utilities for connecting to the Temporal server and
common workflow patterns.
"""

import os
from typing import Any

from temporalio.client import Client


async def get_temporal_client(
    host: str | None = None,
    namespace: str = "default",
    **kwargs: Any,
) -> Client:
    """
    Create a Temporal client connected to the cluster's Temporal server.

    Args:
        host: Temporal frontend address. Defaults to TEMPORAL_HOST env var
              or the cluster-internal service.
        namespace: Temporal namespace to use.
        **kwargs: Additional arguments passed to Client.connect().

    Returns:
        Connected Temporal client.

    Example:
        >>> from core_agents import get_temporal_client
        >>> client = await get_temporal_client()
        >>> await client.start_workflow(...)
    """
    default_host = "temporal-frontend.temporal.svc.cluster.local:7233"
    target_host = host or os.environ.get("TEMPORAL_HOST", default_host)

    return await Client.connect(
        target_host,
        namespace=namespace,
        **kwargs,
    )


async def get_local_temporal_client(
    port: int = 7233,
    namespace: str = "default",
    **kwargs: Any,
) -> Client:
    """
    Create a Temporal client for local development.

    Uses localhost with the specified port (useful with port-forwarding).

    Args:
        port: Local port where Temporal frontend is accessible.
        namespace: Temporal namespace to use.

    Returns:
        Connected Temporal client.
    """
    return await Client.connect(
        f"localhost:{port}",
        namespace=namespace,
        **kwargs,
    )
