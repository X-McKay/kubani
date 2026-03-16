"""
MCP Client Module.

Provides unified access to all MCP servers.

Usage:
    from framework.mcp import get_mcp_client, MCPClient

    client = get_mcp_client()

    # Use specific MCP servers
    await client.temporal.list_workflows()
    await client.memory.store_learning(...)
    await client.skills.execute_skill(...)
"""

from .client import (
    DiscordMCPClient,
    MCPClient,
    MCPResponse,
    MCPServerClient,
    MemoryMCPClient,
    QdrantMCPClient,
    RegistryMCPClient,
    SkillsMCPClient,
    TemporalMCPClient,
    close_mcp_client,
    get_mcp_client,
)

# Server utilities (available when all server submodules are implemented)
try:
    from kubani.framework.mcp.server import (
        ConnectionManager,
        ConnectionState,
        HealthCheck,
        HealthStatus,
        MCPConnectionError,
        MCPError,
        MCPServerBase,
        MCPTimeoutError,
        MCPValidationError,
        TransportConfig,
        run_server,
    )

    _SERVER_AVAILABLE = True
except ImportError:
    _SERVER_AVAILABLE = False

__all__ = [
    # Client classes
    "MCPClient",
    "MCPServerClient",
    "MCPResponse",
    "TemporalMCPClient",
    "QdrantMCPClient",
    "MemoryMCPClient",
    "DiscordMCPClient",
    "RegistryMCPClient",
    "SkillsMCPClient",
    # Client functions
    "get_mcp_client",
    "close_mcp_client",
    # Server utilities (when available)
    "MCPServerBase",
    "ConnectionManager",
    "ConnectionState",
    "MCPError",
    "MCPConnectionError",
    "MCPTimeoutError",
    "MCPValidationError",
    "HealthCheck",
    "HealthStatus",
    "TransportConfig",
    "run_server",
]
