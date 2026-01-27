"""
Testing utilities for MCP servers.

Provides:
- Contract definitions for server validation
- Test harness for running MCP tests
- Mock backends for unit testing
"""

# Contracts - defined first as they have no dependencies
from kubani.framework.mcp.server.testing.contracts import (
    MCPContract,
    ToolContract,
)

# Harness - depends on contracts
from kubani.framework.mcp.server.testing.harness import (
    MCPTestHarness,
    ValidationResult,
)

# Mocks - standalone
from kubani.framework.mcp.server.testing.mocks import (
    MockQdrant,
    MockRedis,
    MockTemporalClient,
)

__all__ = [
    # Contracts
    "MCPContract",
    "ToolContract",
    # Harness
    "MCPTestHarness",
    "ValidationResult",
    # Mocks
    "MockQdrant",
    "MockRedis",
    "MockTemporalClient",
]
