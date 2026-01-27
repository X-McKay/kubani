"""
Kubani MCP Server Utilities - Shared base code for MCP servers.

Provides:
- MCPServerBase: Base class for all MCP servers
- Connection management utilities
- Standardized error handling
- Health check utilities
- Transport mode handling
"""

# Import modules incrementally as they're implemented (TDD pattern)
# Each module is imported individually to avoid import failures during development

__all__: list[str] = []

# Errors module
try:
    from kubani.framework.mcp.server.errors import (
        MCPConnectionError,
        MCPError,
        MCPTimeoutError,
        MCPValidationError,
    )

    __all__.extend(
        [
            "MCPError",
            "MCPConnectionError",
            "MCPTimeoutError",
            "MCPValidationError",
        ]
    )
except ImportError:
    pass

# Connection module
try:
    from kubani.framework.mcp.server.connection import ConnectionManager, ConnectionState

    __all__.extend(
        [
            "ConnectionManager",
            "ConnectionState",
        ]
    )
except ImportError:
    pass

# Health module
try:
    from kubani.framework.mcp.server.health import HealthCheck, HealthStatus

    __all__.extend(
        [
            "HealthCheck",
            "HealthStatus",
        ]
    )
except ImportError:
    pass

# Transport module
try:
    from kubani.framework.mcp.server.transport import TransportConfig, run_server

    __all__.extend(
        [
            "TransportConfig",
            "run_server",
        ]
    )
except ImportError:
    pass

# Base module (depends on other modules, import last)
try:
    from kubani.framework.mcp.server.base import MCPServerBase

    __all__.insert(0, "MCPServerBase")
except ImportError:
    pass
