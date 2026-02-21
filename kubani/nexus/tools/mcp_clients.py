"""MCP client factory for the Nexus PI agent.

Creates Strands MCPClient instances for Memory, Skills, and Fetch.
These are passed directly to Agent(tools=[...]) which auto-discovers
all tools from each server.

Uses strands.tools.mcp.MCPClient -- NOT the custom
kubani.framework.mcp.client.MCPClient.
"""

from __future__ import annotations

import logging

from strands.tools.mcp import MCPClient

logger = logging.getLogger(__name__)


def create_mcp_clients() -> list[MCPClient]:
    """Create MCPClient instances for PI agent MCP servers.

    Returns:
        List of MCPClient instances. Each auto-discovers tools
        when passed to Agent(tools=[...]).
    """
    from kubani.framework.config import get_config

    config = get_config()
    clients: list[MCPClient] = []

    # SSE-based MCP servers (already deployed on cluster).
    # sse_client() expects the full endpoint URL including /sse.
    # Respect the enabled flags from config.
    sse_servers = {}
    if config.mcp.memory_enabled and config.mcp.memory_url:
        sse_servers["memory"] = config.mcp.memory_url
    if config.mcp.skills_enabled and config.mcp.skills_url:
        sse_servers["skills"] = config.mcp.skills_url

    for name, base_url in sse_servers.items():
        try:
            from mcp.client.sse import sse_client

            sse_url = base_url.rstrip("/") + "/sse"
            client = MCPClient(lambda u=sse_url: sse_client(u))
            clients.append(client)
            logger.info(f"Created MCPClient for {name} at {sse_url}")
        except Exception as e:
            logger.warning(f"Failed to create MCPClient for {name}: {e}")

    # Stdio-based: Fetch MCP (in-process, no deployment needed).
    # Uses pip-installed mcp-server-fetch, not uvx.
    try:
        from mcp import StdioServerParameters
        from mcp.client.stdio import stdio_client

        fetch_client = MCPClient(
            lambda: stdio_client(
                StdioServerParameters(command="python", args=["-m", "mcp_server_fetch"])
            )
        )
        clients.append(fetch_client)
        logger.info("Created MCPClient for fetch (stdio)")
    except Exception as e:
        logger.warning(f"Failed to create fetch MCPClient: {e}")

    return clients
