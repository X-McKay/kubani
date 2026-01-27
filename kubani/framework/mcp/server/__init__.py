"""
Kubani MCP Server Utilities - Shared base code for MCP servers.

Provides:
- MCPServerBase: Base class for all MCP servers
- Connection management utilities
- Standardized error handling
- Health check utilities
- Transport mode handling
"""

from kubani.framework.mcp.server.base import MCPServerBase
from kubani.framework.mcp.server.connection import ConnectionManager, ConnectionState
from kubani.framework.mcp.server.errors import (
    MCPConnectionError,
    MCPError,
    MCPTimeoutError,
    MCPValidationError,
)
from kubani.framework.mcp.server.health import HealthCheck, HealthStatus
from kubani.framework.mcp.server.transport import TransportConfig, run_server

__all__ = [
    # Base
    "MCPServerBase",
    # Connection
    "ConnectionManager",
    "ConnectionState",
    # Errors
    "MCPError",
    "MCPConnectionError",
    "MCPTimeoutError",
    "MCPValidationError",
    # Health
    "HealthCheck",
    "HealthStatus",
    # Transport
    "TransportConfig",
    "run_server",
]
