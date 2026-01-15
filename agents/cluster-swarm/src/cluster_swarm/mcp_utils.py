"""
MCP client utilities for cluster-swarm.

Provides helper functions to create and manage MCP clients for:
- Kubernetes operations
- Memory/learning storage
- Discord communication
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def create_kubernetes_mcp_client():
    """
    Create MCP client for kubernetes-mcp-server.

    Returns:
        MCPClient instance for Kubernetes operations
    """
    from mcp.client.streamable_http import streamablehttp_client
    from strands.tools.mcp import MCPClient

    mcp_url = os.getenv(
        "KUBERNETES_MCP_SERVER_URL",
        os.getenv("MCP_SERVER_URL", "https://kubernetes-mcp.almckay.io"),
    )
    if not mcp_url.endswith("/mcp"):
        mcp_url = f"{mcp_url}/mcp"

    logger.debug(f"Connecting to Kubernetes MCP server at {mcp_url}")
    return MCPClient(lambda: streamablehttp_client(mcp_url))


def create_discord_mcp_client():
    """
    Create MCP client for discord-mcp-server.

    Note: Discord MCP server uses SSE transport, not streamable HTTP.

    Returns:
        MCPClient instance for Discord operations
    """
    from mcp.client.sse import sse_client
    from strands.tools.mcp import MCPClient

    mcp_url = os.getenv("DISCORD_MCP_URL", "https://discord-mcp.almckay.io")
    # Ensure URL ends with /sse for SSE transport
    if mcp_url.endswith("/mcp"):
        mcp_url = mcp_url[:-4]
    if not mcp_url.endswith("/sse"):
        mcp_url = f"{mcp_url.rstrip('/')}/sse"

    logger.debug(f"Connecting to Discord MCP server at {mcp_url}")
    return MCPClient(lambda: sse_client(mcp_url))


def get_memory_tools() -> list[Any]:
    """
    Get memory MCP tools for learning storage and retrieval.

    Returns:
        List of memory tool functions
    """
    try:
        from memory_mcp.tools import (
            cache_delete,
            cache_get,
            cache_set,
            get_agent_learnings,
            query_learnings,
            store_learning,
        )

        return [
            store_learning,
            query_learnings,
            get_agent_learnings,
            cache_set,
            cache_get,
            cache_delete,
        ]
    except ImportError:
        logger.warning("memory-mcp-server not available, memory tools disabled")
        return []


def get_kubernetes_tools(mcp_client, apply_limits: bool = True) -> list[Any]:
    """
    Get Kubernetes MCP tools from client.

    Args:
        mcp_client: MCPClient instance
        apply_limits: Whether to wrap tools with result size limits (default: True)

    Returns:
        List of Kubernetes tool objects (wrapped with limits if apply_limits=True)
    """
    try:
        tools = mcp_client.list_tools_sync()
        logger.info(f"Loaded {len(tools)} Kubernetes MCP tools")

        if apply_limits:
            from cluster_swarm.tool_limits import wrap_tools_with_limits

            tools = wrap_tools_with_limits(tools)
            logger.info("Applied result size limits to Kubernetes tools")

        return tools
    except Exception as e:
        logger.error(f"Failed to load Kubernetes MCP tools: {e}")
        return []


def get_discord_tools(mcp_client) -> list[Any]:
    """
    Get Discord MCP tools from client.

    Args:
        mcp_client: MCPClient instance

    Returns:
        List of Discord tool objects
    """
    try:
        tools = mcp_client.list_tools_sync()
        logger.info(f"Loaded {len(tools)} Discord MCP tools")
        return tools
    except Exception as e:
        logger.error(f"Failed to load Discord MCP tools: {e}")
        return []
