"""
MCP (Model Context Protocol) Client Module.

Provides unified access to all MCP servers for agent integration.

Usage:
    from core_agents.mcp import get_mcp_client

    client = get_mcp_client()

    # Temporal operations
    workflows = await client.temporal.list_workflows()

    # Memory operations
    await client.memory.store_learning(...)

    # Qdrant operations
    results = await client.qdrant.search_vectors(...)

    # Discord operations
    await client.discord.send_message(...)

    # Registry operations
    await client.registry.register_agent(...)
"""

from core_agents.mcp.client import (
    MCPClient,
    MCPResponse,
    MCPServerClient,
    TemporalMCPClient,
    QdrantMCPClient,
    MemoryMCPClient,
    DiscordMCPClient,
    RegistryMCPClient,
    get_mcp_client,
    close_mcp_client,
)

__all__ = [
    "MCPClient",
    "MCPResponse",
    "MCPServerClient",
    "TemporalMCPClient",
    "QdrantMCPClient",
    "MemoryMCPClient",
    "DiscordMCPClient",
    "RegistryMCPClient",
    "get_mcp_client",
    "close_mcp_client",
]
