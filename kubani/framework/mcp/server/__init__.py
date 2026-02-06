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
        MCPBackendError,
        MCPConnectionError,
        MCPError,
        MCPErrorHandler,
        MCPTimeoutError,
        MCPValidationError,
    )

    __all__.extend(
        [
            "MCPError",
            "MCPConnectionError",
            "MCPTimeoutError",
            "MCPValidationError",
            "MCPBackendError",
            "MCPErrorHandler",
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
    from kubani.framework.mcp.server.health import (
        BackendHealth,
        HealthCheck,
        HealthCheckManager,
        HealthCheckResponse,
        HealthResult,
        HealthStatus,
    )

    __all__.extend(
        [
            "HealthCheck",
            "HealthCheckManager",
            "HealthResult",
            "HealthStatus",
            "BackendHealth",
            "HealthCheckResponse",
        ]
    )
except ImportError:
    pass

# Metrics module
try:
    from kubani.framework.mcp.server.metrics import MetricsCollector

    __all__.extend(
        [
            "MetricsCollector",
        ]
    )
except ImportError:
    pass

# Registry module
try:
    from kubani.framework.mcp.server.registry import MCPServerRegistration, RegistryClient

    __all__.extend(
        [
            "RegistryClient",
            "MCPServerRegistration",
        ]
    )
except ImportError:
    pass

# Transport module
try:
    from kubani.framework.mcp.server.transport import (
        TransportConfig,
        TransportMode,
        run_server,
        run_server_async,
    )

    __all__.extend(
        [
            "TransportConfig",
            "TransportMode",
            "run_server",
            "run_server_async",
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
