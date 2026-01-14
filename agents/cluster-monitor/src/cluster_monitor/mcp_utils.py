"""
MCP client utilities for cluster-monitor.

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
    
    Returns:
        MCPClient instance for Discord operations
    """
    from mcp.client.streamable_http import streamablehttp_client
    from strands.tools.mcp import MCPClient

    mcp_url = os.getenv("DISCORD_MCP_SERVER_URL", "https://discord-mcp.almckay.io")
    if not mcp_url.endswith("/sse"):
        mcp_url = f"{mcp_url}/sse"

    logger.debug(f"Connecting to Discord MCP server at {mcp_url}")
    return MCPClient(lambda: streamablehttp_client(mcp_url))


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


def get_kubernetes_tools(mcp_client) -> list[Any]:
    """
    Get Kubernetes MCP tools from client.
    
    Args:
        mcp_client: MCPClient instance
        
    Returns:
        List of Kubernetes tool objects
    """
    try:
        tools = mcp_client.list_tools_sync()
        logger.info(f"Loaded {len(tools)} Kubernetes MCP tools")
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
