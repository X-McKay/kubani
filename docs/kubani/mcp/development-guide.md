# MCP Server Development Guide

This guide explains how to create, test, and deploy MCP (Model Context Protocol) servers in Kubani.

## Overview

Kubani MCP servers provide tool interfaces for AI agents using the Model Context Protocol. All servers share a common base from `kubani.framework.mcp.server` for consistent patterns.

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Your MCP Server                               │
├─────────────────────────────────────────────────────────────────┤
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                 kubani.framework.mcp.server                │  │
│  │  MCPServerBase | TransportConfig | ConnectionManager       │  │
│  │  HealthCheck | Errors | Testing                           │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              │                                   │
│                              ▼                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                      FastMCP (mcp)                         │  │
│  │  Tool registration | Protocol handling | Transport         │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Create Package Structure

```bash
# Create the server directory
mkdir -p kubani/mcp/servers/myserver/src/myserver_mcp
mkdir -p kubani/mcp/servers/myserver/tests

# Create files
touch kubani/mcp/servers/myserver/src/myserver_mcp/__init__.py
touch kubani/mcp/servers/myserver/src/myserver_mcp/server.py
touch kubani/mcp/servers/myserver/tests/__init__.py
touch kubani/mcp/servers/myserver/tests/test_server.py
touch kubani/mcp/servers/myserver/pyproject.toml
touch kubani/mcp/servers/myserver/README.md
```

### 2. Create pyproject.toml

```toml
[project]
name = "myserver-mcp"
version = "0.1.0"
description = "MCP server for MyService"
requires-python = ">=3.11"
dependencies = [
    "mcp>=1.0.0",
    "kubani-framework",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
]

[project.scripts]
myserver-mcp = "myserver_mcp:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/myserver_mcp"]
```

### 3. Implement the Server

```python
# src/myserver_mcp/server.py
"""MyServer MCP Server."""

import logging
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

# Import framework utilities
from kubani.framework.mcp.server import (
    ConnectionManager,
    MCPConnectionError,
    TransportConfig,
)
from kubani.framework.mcp.server.transport import run_server_async

logger = logging.getLogger(__name__)

# Global state
_connection_manager = ConnectionManager(name="myservice")
_client: Any = None


async def _connect() -> None:
    """Connect to the backend service."""
    global _client
    host = os.environ.get("MYSERVICE_HOST", "localhost")
    port = int(os.environ.get("MYSERVICE_PORT", "9000"))

    # Replace with your actual connection logic
    from myservice import Client
    _client = await Client.connect(host=host, port=port)


async def _disconnect() -> None:
    """Disconnect from the backend service."""
    global _client
    if _client:
        await _client.close()
        _client = None


def _get_client_or_error():
    """Get the connected client or raise an error."""
    _connection_manager.ensure_connected()
    return _client


def create_server() -> FastMCP:
    """Create the MCP server with all tools registered."""
    mcp = FastMCP("myserver-mcp")

    @mcp.tool()
    async def list_items(limit: int = 10) -> dict:
        """List items from the service.

        Args:
            limit: Maximum number of items to return

        Returns:
            List of items
        """
        client = _get_client_or_error()
        items = await client.list_items(limit=limit)
        return {"items": items}

    @mcp.tool()
    async def get_item(item_id: str) -> dict:
        """Get a specific item by ID.

        Args:
            item_id: The item identifier

        Returns:
            Item details
        """
        client = _get_client_or_error()
        item = await client.get_item(item_id)
        if not item:
            raise ValueError(f"Item not found: {item_id}")
        return item

    @mcp.tool()
    async def health() -> dict:
        """Check server health."""
        try:
            _connection_manager.ensure_connected()
            return {
                "status": "healthy",
                "connected": True,
                "backend": "myservice",
            }
        except MCPConnectionError:
            return {
                "status": "unhealthy",
                "connected": False,
                "error": "Not connected to backend",
            }

    return mcp


async def run() -> None:
    """Run the MCP server."""
    config = TransportConfig.from_args()
    mcp = create_server()

    try:
        # Connect to backend
        await _connection_manager.connect(_connect)
        logger.info("Connected to MyService backend")

        # Run the server
        await run_server_async(mcp, config)
    finally:
        # Clean disconnect
        await _connection_manager.disconnect(_disconnect)
        logger.info("Disconnected from MyService backend")


def main() -> None:
    """Entry point for the MCP server."""
    import asyncio
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    asyncio.run(run())


if __name__ == "__main__":
    main()
```

### 4. Create Package Init

```python
# src/myserver_mcp/__init__.py
"""MyServer MCP Server package."""

from .server import create_server, main, run

__all__ = ["create_server", "main", "run"]
```

### 5. Add Tests

```python
# tests/test_server.py
"""Tests for MyServer MCP server."""

import pytest

from kubani.framework.mcp.server.testing import (
    MCPContract,
    MCPTestHarness,
    ToolContract,
)

from myserver_mcp import create_server


# Define the contract for this server
MYSERVER_CONTRACT = MCPContract(
    server_name="myserver-mcp",
    tools=[
        ToolContract(
            name="list_items",
            parameters={"limit": {"type": "integer", "required": False}},
        ),
        ToolContract(
            name="get_item",
            parameters={"item_id": {"type": "string", "required": True}},
        ),
        ToolContract(name="health"),
    ],
)


class TestMyServerMCP:
    """Tests for MyServer MCP server."""

    @pytest.fixture
    def server(self):
        """Create server instance."""
        return create_server()

    @pytest.fixture
    def harness(self, server):
        """Create test harness."""
        return MCPTestHarness(server, MYSERVER_CONTRACT)

    @pytest.mark.asyncio
    async def test_tools_exist(self, harness):
        """Test that all contracted tools exist."""
        result = await harness.validate_tools_exist()
        assert result.passed, f"Missing tools: {result.missing_tools}"

    @pytest.mark.asyncio
    async def test_health_tool(self, harness):
        """Test the health tool."""
        await harness.setup()
        try:
            result = await harness.call_tool("health")
            assert "status" in result
        finally:
            await harness.teardown()
```

### 6. Add to Registry

Create `kubani/mcp/registry/servers/myserver.json`:

```json
{
  "name": "myserver-mcp",
  "description": "MCP server for MyService operations",
  "type": "internal",
  "package": "kubani/mcp/servers/myserver",
  "command": "myserver-mcp",
  "environment": {
    "MYSERVICE_HOST": {
      "required": true,
      "description": "MyService host"
    },
    "MYSERVICE_PORT": {
      "required": false,
      "default": "9000",
      "description": "MyService port"
    }
  },
  "capabilities": {
    "tools": ["list_items", "get_item", "health"],
    "resources": [],
    "prompts": []
  },
  "policies": {
    "allowed_agents": ["*"],
    "rate_limit": {
      "requests_per_minute": 100
    }
  }
}
```

Then regenerate the registry:

```bash
just mcp-generate-registry
```

## Framework Components

### TransportConfig

Handles command-line arguments and environment variables for transport configuration:

```python
from kubani.framework.mcp.server import TransportConfig

# From CLI args (--mode, --host, --port)
config = TransportConfig.from_args()

# From environment (MCP_TRANSPORT, MCP_HOST, MCP_PORT)
config = TransportConfig.from_env()

# Supports stdio, sse, and http modes
```

### ConnectionManager

Manages backend connection lifecycle:

```python
from kubani.framework.mcp.server import ConnectionManager

manager = ConnectionManager(name="myservice")

# Connect (tracks state)
await manager.connect(my_connect_function)

# Check status
if manager.is_connected:
    # ...

# Ensure connected (raises MCPConnectionError if not)
manager.ensure_connected()

# Disconnect
await manager.disconnect(my_disconnect_function)
```

### Error Classes

Standardized error types:

```python
from kubani.framework.mcp.server import (
    MCPError,           # Base error
    MCPConnectionError, # Connection issues
    MCPTimeoutError,    # Operation timeouts
    MCPValidationError, # Invalid inputs
)
```

### Health Checks

Standardized health monitoring:

```python
from kubani.framework.mcp.server import HealthCheck, HealthStatus

async def check_backend():
    await client.ping()
    return True

check = HealthCheck(name="backend", check_fn=check_backend, timeout=5.0)
result = await check.run()

print(result.status)      # HealthStatus.HEALTHY
print(result.latency_ms)  # 12.5
```

## Testing

### Contract-Based Testing

Define contracts for your tools and validate them:

```python
from kubani.framework.mcp.server.testing import (
    MCPContract,
    MCPTestHarness,
    ToolContract,
)

contract = MCPContract(
    server_name="myserver-mcp",
    tools=[
        ToolContract(
            name="my_tool",
            parameters={"query": {"type": "string", "required": True}},
        ),
    ],
)

harness = MCPTestHarness(server, contract)

# Validate tools exist
result = await harness.validate_tools_exist()
assert result.passed

# Call tools
await harness.setup()
result = await harness.call_tool("my_tool", query="test")
await harness.teardown()
```

### Mock Backends

Use mock backends for testing without real services:

```python
from kubani.framework.mcp.server.testing import MockQdrant, MockRedis

mock_qdrant = MockQdrant()
await mock_qdrant.connect()
await mock_qdrant.create_collection("test", vector_size=128)
```

## Deployment

### Claude Code Configuration

Add to `.claude/mcp.json`:

```json
{
  "mcpServers": {
    "myserver": {
      "command": "myserver-mcp",
      "env": {
        "MYSERVICE_HOST": "myservice.example.com",
        "MYSERVICE_PORT": "9000"
      }
    }
  }
}
```

### Kubernetes Deployment

The server can be deployed as a standalone service:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myserver-mcp
spec:
  replicas: 1
  template:
    spec:
      containers:
        - name: myserver-mcp
          image: kubani/myserver-mcp:latest
          args: ["--mode", "sse", "--port", "8080"]
          ports:
            - containerPort: 8080
          env:
            - name: MYSERVICE_HOST
              value: "myservice.svc.cluster.local"
```

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install uv
RUN pip install uv

# Copy and install
COPY kubani/framework /app/kubani/framework
COPY kubani/mcp/servers/myserver /app/kubani/mcp/servers/myserver

RUN uv pip install --system -e /app/kubani/framework
RUN uv pip install --system -e /app/kubani/mcp/servers/myserver

ENTRYPOINT ["myserver-mcp"]
CMD ["--mode", "sse", "--port", "8080"]
```

## Best Practices

### 1. Always Use Framework Components

Don't reinvent connection management or error handling:

```python
# Good
from kubani.framework.mcp.server import ConnectionManager, MCPConnectionError

# Avoid
class MyConnectionManager:  # Reinventing the wheel
    pass
```

### 2. Provide Health Tools

Every server should have a health tool:

```python
@mcp.tool()
async def health() -> dict:
    """Check server health."""
    return {"status": "healthy", "connected": True}
```

### 3. Use Type Hints and Docstrings

FastMCP uses these for the tool schema:

```python
@mcp.tool()
async def create_item(
    name: str,
    description: str = "",
    tags: list[str] | None = None,
) -> dict:
    """Create a new item.

    Args:
        name: Item name (required)
        description: Optional description
        tags: Optional list of tags

    Returns:
        Created item with ID
    """
    pass
```

### 4. Handle Errors Gracefully

Catch backend errors and wrap them:

```python
from kubani.framework.mcp.server import MCPConnectionError

@mcp.tool()
async def my_tool(query: str) -> dict:
    try:
        return await client.query(query)
    except ConnectionError as e:
        raise MCPConnectionError(str(e), server="myservice")
```

### 5. Add to Registry

Always add your server to the registry for discoverability and policy enforcement.

### 6. Write Tests

Use the contract testing framework to ensure your server meets its API contract.

## See Also

- [Framework Server Utilities](../../../kubani/framework/mcp/server/README.md)
- [MCP Specification](https://modelcontextprotocol.io/)
- [FastMCP Documentation](https://github.com/modelcontextprotocol/python-sdk)
