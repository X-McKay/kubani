# MCP Common

Common utilities and base classes for Kubani MCP servers.

## Overview

This package provides a consistent foundation for building MCP servers in the Kubani ecosystem:

- **BaseMCPServer**: Abstract base class with health checks, metrics, and lifecycle management
- **tool_handler**: Decorator for consistent error handling and metrics collection
- **ToolResult**: Standard result model for tool responses
- **ServerMetrics**: Automatic metrics collection for monitoring

## Installation

```bash
pip install -e tools/mcp-common
```

## Usage

### Creating a New MCP Server

```python
from mcp_common import BaseMCPServer, tool_handler

class MyMCPServer(BaseMCPServer):
    def __init__(self):
        super().__init__(
            name="my-mcp-server",
            version="1.0.0",
            description="My custom MCP server",
        )
        self.db = None

    async def initialize(self) -> None:
        """Called when server starts."""
        self.db = await connect_to_database()

    async def cleanup(self) -> None:
        """Called when server stops."""
        if self.db:
            await self.db.close()

    def register_tools(self) -> None:
        @self.server.tool()
        @tool_handler
        async def my_tool(param: str) -> dict:
            """Tool with automatic error handling."""
            result = await self.db.query(param)
            return {"data": result}

        @self.server.tool()
        @tool_handler
        async def another_tool(id: int) -> str:
            """Returns are automatically wrapped in ToolResult."""
            return f"Processed {id}"

if __name__ == "__main__":
    server = MyMCPServer()
    server.run_sync()
```

### Built-in Tools

All servers automatically get these tools:

- `health()`: Returns server health status and metrics
- `info()`: Returns server name, version, and description

### Metrics

The `ServerMetrics` class automatically tracks:

- Server uptime
- Total requests
- Successful/failed requests
- Average latency
- Success rate

Access metrics via the `health()` tool or `server.metrics`.

## Design Principles

1. **Consistency**: All MCP servers follow the same patterns
2. **Observability**: Built-in metrics and health checks
3. **Error Handling**: Automatic error wrapping with `tool_handler`
4. **Lifecycle Management**: Clean initialization and cleanup hooks

## See Also

- [Temporal MCP Server](../temporal-mcp-server/README.md)
- [Qdrant MCP Server](../qdrant-mcp-server/README.md)
- [Memory MCP Server](../memory-mcp-server/README.md)
- [Discord MCP Server](../discord-mcp-server/README.md)
