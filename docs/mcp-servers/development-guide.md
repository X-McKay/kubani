# MCP Server Development Guide

This guide walks you through creating a new MCP (Model Context Protocol) server for the Kubani platform. MCP servers expose tools and capabilities that AI agents can use to interact with external systems.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Framework Components](#framework-components)
- [Multi-Transport Support](#multi-transport-support)
- [Secrets Management](#secrets-management)
- [Best Practices](#best-practices)
- [Example Implementation](#example-implementation)

## Overview

An MCP server in Kubani:
- Exposes tools via the Model Context Protocol
- Supports multiple transport mechanisms (SSE, stdio, HTTP)
- Integrates with the Kubani Registry for service discovery
- Provides health checks and Prometheus metrics
- Is generic and reusable across all agents

## Prerequisites

- Python 3.11+
- `uv` package manager
- Basic understanding of async Python
- Familiarity with the MCP protocol

## Quick Start

### 1. Create Server Structure

```bash
# Create directory structure
mkdir -p kubani/mcp/servers/myserver/src/myserver_mcp
mkdir -p kubani/mcp/servers/myserver/tests

# Create package files
touch kubani/mcp/servers/myserver/src/myserver_mcp/__init__.py
touch kubani/mcp/servers/myserver/src/myserver_mcp/server.py
touch kubani/mcp/servers/myserver/pyproject.toml
```

### 2. Define pyproject.toml

```toml
[project]
name = "myserver-mcp"
version = "0.1.0"
description = "MCP server for MyService integration"
requires-python = ">=3.11"
dependencies = [
    "fastmcp>=0.2.0",
    "kubani-framework",
    # Add your backend client libraries here
]

[project.scripts]
myserver-mcp = "myserver_mcp.server:main"
```

### 3. Implement the Server

Create `kubani/mcp/servers/myserver/src/myserver_mcp/server.py`:

```python
"""MyServer MCP Server implementation."""

import asyncio
import logging
import os
import sys
from contextlib import suppress

from aiohttp import web
from kubani.framework.mcp.server.health import HealthCheckManager
from kubani.framework.mcp.server.metrics import MetricsCollector
from kubani.framework.mcp.server.registry import RegistryClient
from kubani.framework.mcp.server.transport import TransportConfig, run_server_async
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

logger = logging.getLogger(__name__)

# Global framework components
_health_manager: HealthCheckManager | None = None
_metrics: MetricsCollector | None = None
_registry_client: RegistryClient | None = None
_heartbeat_task: asyncio.Task | None = None


async def initialize_backend():
    """Initialize backend connections and framework components."""
    global _health_manager, _metrics
    
    # Initialize your backend client here
    # backend_client = MyBackendClient(...)
    
    # Initialize framework components
    _health_manager = HealthCheckManager(version="0.1.0")
    _metrics = MetricsCollector(server_name="myserver-mcp")
    
    # Register health checks
    async def check_backend_health() -> bool:
        """Check if backend is accessible."""
        try:
            # Implement your health check logic
            # await backend_client.ping()
            return True
        except Exception:
            return False
    
    _health_manager.register("backend", check_backend_health, timeout=5.0)


async def shutdown_backend():
    """Clean up backend connections."""
    global _heartbeat_task
    
    # Cancel heartbeat task
    if _heartbeat_task:
        _heartbeat_task.cancel()
        with suppress(asyncio.CancelledError):
            await _heartbeat_task
    
    # Unregister from registry
    if _registry_client:
        await _registry_client.unregister()
    
    # Clean up backend connections
    # await backend_client.close()


async def register_with_registry():
    """Register this MCP server with the Kubani Registry."""
    global _registry_client, _heartbeat_task, _health_manager
    
    registry_url = os.environ.get("REGISTRY_URL")
    if not registry_url:
        logger.info("REGISTRY_URL not set, skipping registry registration")
        return
    
    server_id = os.environ.get("MCP_SERVER_ID", "myserver-mcp")
    external_url = os.environ.get("MCP_EXTERNAL_URL", "https://myserver-mcp.almckay.io/sse")
    internal_url = os.environ.get(
        "MCP_INTERNAL_URL", "http://myserver-mcp-server.ai-agents.svc:8080/sse"
    )
    
    _registry_client = RegistryClient(
        registry_url=registry_url,
        server_id=server_id,
    )
    
    # List your tool names
    capabilities = [
        "my_tool_1",
        "my_tool_2",
    ]
    
    success = await _registry_client.register(
        name="MyServer MCP Server",
        description="Integration with MyService for AI agents",
        transport="sse",
        connection_config={
            "url": external_url,
            "internal_url": internal_url,
        },
        capabilities=capabilities,
    )
    
    if success:
        logger.info("Successfully registered with Kubani Registry")
        
        # Start heartbeat task
        async def get_backend_status() -> dict[str, str]:
            """Get backend health status for heartbeat."""
            if _health_manager:
                health = await _health_manager.check_all()
                return {
                    name: backend.status.value 
                    for name, backend in health.backends.items()
                }
            return {}
        
        _heartbeat_task = asyncio.create_task(
            _registry_client.start_heartbeat(
                interval=30, 
                get_backend_status=get_backend_status
            )
        )
    else:
        logger.warning("Failed to register with registry")


def create_server() -> FastMCP:
    """Create and configure the MCP server."""
    # Get allowed hosts from environment
    allowed_hosts_env = os.environ.get("MCP_ALLOWED_HOSTS", "")
    allowed_hosts = ["localhost:*", "127.0.0.1:*"]
    if allowed_hosts_env:
        allowed_hosts.extend(h.strip() for h in allowed_hosts_env.split(",") if h.strip())
    
    mcp = FastMCP(
        name="MyServer MCP Server",
        instructions="Provides tools for interacting with MyService.",
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=allowed_hosts,
        ),
    )
    
    # Define your tools
    @mcp.tool()
    async def my_tool_1(param1: str, param2: int) -> dict:
        """
        Description of what this tool does.
        
        Args:
            param1: Description of param1
            param2: Description of param2
            
        Returns:
            Result dictionary
        """
        # Track metrics
        if _metrics:
            with _metrics.track_request("my_tool_1"):
                # Implement tool logic
                result = {"status": "success"}
                return result
        else:
            # Implement tool logic
            result = {"status": "success"}
            return result
    
    return mcp


def main():
    """Entry point for the MCP server."""
    import anyio
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr,
    )
    
    # Parse transport config
    config = TransportConfig.from_args()
    
    # Create the server
    mcp = create_server()
    
    # Create health and metrics HTTP endpoints
    async def health_handler(request):
        """Health check endpoint."""
        if _health_manager:
            health = await _health_manager.check_all()
            return web.json_response(health.to_dict())
        return web.json_response({"status": "healthy", "backends": {}})
    
    async def metrics_handler(request):
        """Metrics endpoint."""
        if _metrics:
            metrics_data = _metrics.get_metrics()
            return web.Response(
                body=metrics_data, 
                content_type="text/plain; version=0.0.4"
            )
        return web.Response(
            text="# No metrics available\n", 
            content_type="text/plain"
        )
    
    # Run with lifecycle management
    async def run_with_lifecycle():
        try:
            # Initialize backend and framework
            await initialize_backend()
            
            # Register with registry
            await register_with_registry()
            
            # Start metrics/health HTTP server on port 9090
            app = web.Application()
            app.router.add_get("/health", health_handler)
            app.router.add_get("/metrics", metrics_handler)
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, "0.0.0.0", 9090)
            await site.start()
            logger.info("Health and metrics endpoints available on port 9090")
            
            # Run MCP server
            await run_server_async(mcp, config)
        finally:
            await shutdown_backend()
    
    anyio.run(run_with_lifecycle)


if __name__ == "__main__":
    main()
```

## Framework Components

### HealthCheckManager

Manages health checks for backend services.

```python
from kubani.framework.mcp.server.health import HealthCheckManager

# Initialize
health_manager = HealthCheckManager(version="1.0.0")

# Register a health check
async def check_database():
    await db.ping()
    return True

health_manager.register("database", check_database, timeout=5.0)

# Run all checks
response = await health_manager.check_all()
print(response.status)  # HealthStatus.HEALTHY
```

### MetricsCollector

Collects Prometheus metrics for monitoring.

```python
from kubani.framework.mcp.server.metrics import MetricsCollector

# Initialize
metrics = MetricsCollector(server_name="myserver-mcp")

# Track a request
with metrics.track_request("my_tool"):
    await my_tool()

# Track backend call
with metrics.track_backend("my_backend"):
    await backend.call()

# Get metrics for HTTP endpoint
metrics_data = metrics.get_metrics()
```

### RegistryClient

Handles automatic registration with the Kubani Registry.

```python
from kubani.framework.mcp.server.registry import RegistryClient

# Initialize
client = RegistryClient(
    registry_url="http://registry.ai-agents.svc:8000",
    server_id="myserver-mcp",
)

# Register
await client.register(
    name="MyServer MCP",
    description="My service integration",
    transport="sse",
    connection_config={
        "url": "https://myserver-mcp.almckay.io/sse",
        "internal_url": "http://myserver-mcp-server.ai-agents.svc:8080/sse"
    },
    capabilities=["tool1", "tool2"],
)

# Start heartbeat
task = asyncio.create_task(client.start_heartbeat(interval=30))
```

## Multi-Transport Support

All MCP servers must support multiple transport mechanisms.

### Transport Configuration

Use `TransportConfig` to parse command-line arguments:

```python
from kubani.framework.mcp.server.transport import TransportConfig, run_server_async

# Parse from command line
config = TransportConfig.from_args()

# Or from environment variables
config = TransportConfig.from_env()

# Run server with config
await run_server_async(mcp, config)
```

### Command-Line Usage

```bash
# stdio (default)
myserver-mcp --mode stdio

# SSE (for cluster deployment)
myserver-mcp --mode sse --host 0.0.0.0 --port 8080

# HTTP
myserver-mcp --mode http --host 0.0.0.0 --port 8080
```

### Environment Variables

```bash
export MCP_TRANSPORT=sse
export MCP_HOST=0.0.0.0
export MCP_PORT=8080
export MCP_ALLOWED_HOSTS="myserver-mcp.almckay.io,*.internal"
```

## Secrets Management

**CRITICAL**: Never hardcode secrets or commit them to git.

### Best Practices

1. **Use Environment Variables**
   ```python
   # GOOD
   api_key = os.environ.get("MYSERVICE_API_KEY")
   if not api_key:
       raise ValueError("MYSERVICE_API_KEY environment variable required")
   
   # BAD - Never do this!
   api_key = "sk-1234567890abcdef"  # NEVER HARDCODE
   ```

2. **Validate Required Secrets**
   ```python
   def validate_config():
       """Validate all required secrets are present."""
       required = ["MYSERVICE_API_KEY", "MYSERVICE_SECRET"]
       missing = [var for var in required if not os.environ.get(var)]
       if missing:
           raise ValueError(f"Missing required environment variables: {missing}")
   ```

3. **Never Log Secrets**
   ```python
   # GOOD
   logger.info("Connecting to MyService API")
   
   # BAD - Never log secrets!
   logger.info(f"Using API key: {api_key}")
   ```

4. **Use Kubernetes Secrets**
   ```yaml
   env:
     - name: MYSERVICE_API_KEY
       valueFrom:
         secretKeyRef:
           name: myserver-secrets
           key: api-key
   ```

5. **Use SOPS for Encrypted Secrets**
   ```bash
   # Encrypt secrets with SOPS
   sops -e secrets.yaml > secrets.enc.yaml
   
   # Commit encrypted version only
   git add secrets.enc.yaml
   ```

### Pre-Commit Hooks

The repository has pre-commit hooks to detect secrets:

```bash
# Install pre-commit hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

Tools used:
- `detect-secrets`: Scans for hardcoded secrets
- `gitleaks`: Detects secrets in git history

### Secret Detection Tools

```bash
# Run secret scanning
uv run detect-secrets scan

# Check for leaked secrets
gitleaks detect --source . --verbose
```

## Best Practices

### 1. Generic Design

Make tools reusable across all agents:

```python
# GOOD - Generic with agent_id parameter
@mcp.tool()
async def store_data(agent_id: str, data: str) -> dict:
    """Store data with agent namespacing."""
    await db.store(f"agent:{agent_id}:data", data)
    return {"status": "success"}

# BAD - Agent-specific
@mcp.tool()
async def store_k8s_monitor_data(data: str) -> dict:
    """Store data for k8s-monitor agent."""
    await db.store("k8s-monitor:data", data)
    return {"status": "success"}
```

### 2. Error Handling

Use consistent error handling:

```python
@mcp.tool()
async def my_tool(param: str) -> dict:
    """Tool with proper error handling."""
    try:
        # Validate input
        if not param:
            raise ValueError("param is required")
        
        # Call backend
        result = await backend.call(param)
        return {"status": "success", "result": result}
        
    except ValueError as e:
        logger.warning(f"Validation error: {e}")
        raise
    except BackendError as e:
        logger.error(f"Backend error: {e}")
        raise RuntimeError(f"Backend operation failed: {e}")
    except Exception as e:
        logger.exception("Unexpected error")
        raise
```

### 3. Input Validation

Validate all inputs:

```python
from pydantic import BaseModel, Field

class MyToolInput(BaseModel):
    """Input model for my_tool."""
    param1: str = Field(..., min_length=1, max_length=100)
    param2: int = Field(..., ge=0, le=1000)

@mcp.tool()
async def my_tool(param1: str, param2: int) -> dict:
    """Tool with validated inputs."""
    # Validate using Pydantic
    input_data = MyToolInput(param1=param1, param2=param2)
    
    # Use validated data
    result = await process(input_data.param1, input_data.param2)
    return {"status": "success", "result": result}
```

### 4. Metrics Instrumentation

Instrument all tools and backend calls:

```python
@mcp.tool()
async def my_tool(param: str) -> dict:
    """Tool with metrics tracking."""
    if _metrics:
        with _metrics.track_request("my_tool"):
            # Backend call with metrics
            with _metrics.track_backend("my_backend"):
                result = await backend.call(param)
            return {"status": "success", "result": result}
    else:
        result = await backend.call(param)
        return {"status": "success", "result": result}
```

### 5. Async Best Practices

- Use `async`/`await` consistently
- Don't block the event loop
- Use `asyncio.gather()` for concurrent operations
- Handle cancellation properly

```python
@mcp.tool()
async def batch_operation(items: list[str]) -> dict:
    """Process multiple items concurrently."""
    # GOOD - Concurrent processing
    results = await asyncio.gather(
        *[process_item(item) for item in items],
        return_exceptions=True
    )
    
    # Handle results
    successes = [r for r in results if not isinstance(r, Exception)]
    failures = [r for r in results if isinstance(r, Exception)]
    
    return {
        "successes": len(successes),
        "failures": len(failures),
    }
```

### 6. Documentation

Document all tools clearly:

```python
@mcp.tool()
async def my_tool(
    param1: str,
    param2: int,
    optional_param: str | None = None,
) -> dict:
    """
    One-line summary of what the tool does.
    
    Longer description providing more context about when and how
    to use this tool. Include any important caveats or limitations.
    
    Args:
        param1: Description of param1 and its purpose
        param2: Description of param2 (must be between 0-100)
        optional_param: Optional parameter for advanced usage
        
    Returns:
        Dictionary containing:
        - status: "success" or "error"
        - result: The operation result
        - message: Human-readable message
        
    Raises:
        ValueError: If param1 is empty or param2 is out of range
        RuntimeError: If backend operation fails
        
    Example:
        >>> await my_tool("test", 42)
        {"status": "success", "result": {...}}
    """
    # Implementation
    pass
```

## Example Implementation

See the Discord MCP server for a complete example:
- `kubani/mcp/servers/discord/src/discord_mcp/server.py`

Key features demonstrated:
- Framework component integration
- Multi-transport support
- Registry registration
- Health checks and metrics
- Proper error handling
- Generic, reusable tools

## Next Steps

1. Implement your server following this guide
2. Write tests (see [Testing Guide](testing-guide.md))
3. Create deployment manifests (see [Deployment Guide](deployment-guide.md))
4. Register with the registry (see [Registry Integration Guide](registry-integration.md))

## Additional Resources

- [MCP Protocol Specification](https://modelcontextprotocol.io/)
- [FastMCP Documentation](https://github.com/jlowin/fastmcp)
- [Testing Guide](testing-guide.md)
- [Deployment Guide](deployment-guide.md)
