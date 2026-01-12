"""
Common utilities for Kubani MCP servers.

This package provides:
- BaseMCPServer: Abstract base class for consistent MCP server implementation
- tool_handler: Decorator for consistent error handling and metrics
- ToolResult: Standard result model for tool responses
- ServerMetrics: Metrics collection for monitoring

Usage:
    from mcp_common import BaseMCPServer, tool_handler, ToolResult

    class MyServer(BaseMCPServer):
        def __init__(self):
            super().__init__(
                name="my-server",
                version="1.0.0",
                description="My MCP server",
            )

        def register_tools(self) -> None:
            @self.server.tool()
            @tool_handler
            async def my_tool(param: str) -> dict:
                return {"result": param}

    if __name__ == "__main__":
        server = MyServer()
        server.run_sync()
"""

from mcp_common.base import (
    BaseMCPServer,
    HealthCheckMixin,
    ServerMetrics,
    ToolResult,
    tool_handler,
)

__all__ = [
    "BaseMCPServer",
    "HealthCheckMixin",
    "ServerMetrics",
    "ToolResult",
    "tool_handler",
]

__version__ = "1.0.0"
