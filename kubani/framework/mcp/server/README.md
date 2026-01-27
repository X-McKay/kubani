# Kubani MCP Server Utilities

Shared base code for all Kubani MCP servers, providing consistent patterns for:

- **Connection Management**: Lifecycle management for backend connections
- **Health Checks**: Standardized health monitoring
- **Error Handling**: Consistent error classes and responses
- **Transport**: Unified command-line argument parsing
- **Testing**: Contract-based test harness and mocks

## Quick Start

### Creating a New MCP Server

```python
from kubani.framework.mcp.server import MCPServerBase, TransportConfig
from kubani.framework.mcp.server.transport import run_server_async
from mcp.server.fastmcp import FastMCP

class MyMCPServer(MCPServerBase):
    name = "my-mcp-server"
    description = "Does useful things with the backend"

    def __init__(self):
        super().__init__()
        self._client = None

    @property
    def client(self):
        self.ensure_connected()
        return self._client

    async def connect_backend(self):
        self._client = await MyBackend.connect(
            host=os.environ.get("MY_BACKEND_HOST", "localhost"),
        )

    async def disconnect_backend(self):
        if self._client:
            await self._client.close()
            self._client = None

    def register_tools(self, mcp: FastMCP):
        @mcp.tool()
        async def my_tool(query: str) -> dict:
            """Do something with the query."""
            result = await self.client.process(query)
            return {"result": result}


def main():
    import logging
    logging.basicConfig(level=logging.INFO)

    server = MyMCPServer()
    mcp = server.create_server()
    config = TransportConfig.from_args()

    async def run():
        try:
            await server.startup()
            await run_server_async(mcp, config)
        finally:
            await server.shutdown()

    import anyio
    anyio.run(run)


if __name__ == "__main__":
    main()
```

## Components

### MCPServerBase

Abstract base class that all MCP servers should inherit from:

```python
class MCPServerBase(ABC):
    name: str          # Server name
    description: str   # Server description

    @abstractmethod
    async def connect_backend(self) -> None: ...

    @abstractmethod
    async def disconnect_backend(self) -> None: ...

    @abstractmethod
    def register_tools(self, mcp: FastMCP) -> None: ...
```

### ConnectionManager

Manages connection lifecycle with state tracking:

```python
from kubani.framework.mcp.server import ConnectionManager

manager = ConnectionManager(name="my-backend")

# Connect
await manager.connect(my_connect_function)

# Check status
if manager.is_connected:
    pass

# Ensure connected (raises MCPConnectionError if not)
manager.ensure_connected()

# Disconnect
await manager.disconnect(my_disconnect_function)
```

### Health Checks

Standardized health monitoring:

```python
from kubani.framework.mcp.server import HealthCheck, HealthStatus

async def check_db():
    await db.ping()
    return True

hc = HealthCheck(name="database", check_fn=check_db, timeout=5.0)
result = await hc.run()

print(result.status)      # HealthStatus.HEALTHY
print(result.latency_ms)  # 12.5
```

### Transport Configuration

Unified argument parsing:

```python
from kubani.framework.mcp.server import TransportConfig

# From command line args
config = TransportConfig.from_args()

# From environment variables
config = TransportConfig.from_env()

# Manual
config = TransportConfig(
    mode=TransportMode.SSE,
    host="0.0.0.0",
    port=8080,
)
```

### Error Classes

Standardized MCP errors:

```python
from kubani.framework.mcp.server import (
    MCPError,
    MCPConnectionError,
    MCPTimeoutError,
    MCPValidationError,
)

raise MCPConnectionError("Cannot connect", server="qdrant")
raise MCPTimeoutError("Slow query", timeout=30.0)
raise MCPValidationError("Bad input", field="query", value="")
```

## Testing

### Contract-Based Testing

```python
from kubani.framework.mcp.server.testing import (
    MCPTestHarness,
    MCPContract,
    ToolContract,
)

contract = MCPContract(
    server_name="my-server",
    tools=[
        ToolContract(
            name="my_tool",
            parameters={"query": {"type": "string", "required": True}},
        ),
    ],
)

server = MyMCPServer()
harness = MCPTestHarness(server, contract)

# Validate all tools exist
result = await harness.validate_tools_exist()
assert result.passed

# Call a tool
await harness.setup()
result = await harness.call_tool("my_tool", query="test")
await harness.teardown()
```

### Mock Backends

```python
from kubani.framework.mcp.server.testing import MockQdrant, MockRedis

mock = MockQdrant()
await mock.connect()
await mock.create_collection("test", vector_size=128)
results = await mock.search("test", query_vector=[1.0, 0.0])
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MCP_TRANSPORT` | Transport mode (stdio, sse, http) | `stdio` |
| `MCP_HOST` | Host to bind to | `0.0.0.0` |
| `MCP_PORT` | Port to bind to | `8080` |
| `MCP_ALLOWED_HOSTS` | Comma-separated allowed hosts | `localhost:*,127.0.0.1:*` |

## Development

```bash
# Run tests
cd kubani/framework && uv run pytest mcp/server/ -v

# Run with coverage
uv run pytest mcp/server/ --cov=kubani.framework.mcp.server
```
