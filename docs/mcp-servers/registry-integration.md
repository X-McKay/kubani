# MCP Server Registry Integration Guide

This guide explains how MCP servers integrate with the Kubani Registry for automatic service discovery and lifecycle management.

## Table of Contents

- [Overview](#overview)
- [Registry Architecture](#registry-architecture)
- [Registration Process](#registration-process)
- [Heartbeat Mechanism](#heartbeat-mechanism)
- [Lifecycle Management](#lifecycle-management)
- [Service Discovery](#service-discovery)
- [Implementation Guide](#implementation-guide)
- [Troubleshooting](#troubleshooting)

## Overview

The Kubani Registry provides centralized service discovery for MCP servers. It:
- Tracks all deployed MCP servers
- Maintains connection information for each server
- Monitors server health via heartbeats
- Automatically reconciles with Kubernetes deployments
- Enables dynamic service discovery for agents

## Registry Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Kubani Registry                          │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Registration API                                     │  │
│  │  - POST /api/v1/mcp/servers (register)              │  │
│  │  - PUT /api/v1/mcp/servers/{id}/heartbeat           │  │
│  │  - GET /api/v1/mcp/servers (query)                  │  │
│  │  - DELETE /api/v1/mcp/servers/{id} (unregister)     │  │
│  └──────────────────────────────────────────────────────┘  │
│                           │                                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Database (PostgreSQL)                               │  │
│  │  - Server metadata                                   │  │
│  │  - Connection config                                 │  │
│  │  - Health status                                     │  │
│  │  - Last heartbeat timestamp                          │  │
│  └──────────────────────────────────────────────────────┘  │
│                           │                                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Reconciliation Service (every 5 minutes)            │  │
│  │  - Query Kubernetes for MCP deployments             │  │
│  │  - Mark missing servers as inactive                 │  │
│  │  - Remove servers inactive > 24 hours               │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                           ▲
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
   ┌────▼────┐       ┌────▼────┐       ┌────▼────┐
   │ Discord │       │ Memory  │       │ Skills  │
   │   MCP   │       │   MCP   │       │   MCP   │
   └─────────┘       └─────────┘       └─────────┘
   
   - Register on startup
   - Send heartbeats every 30s
   - Unregister on shutdown
```

## Registration Process

### When Registration Occurs

MCP servers register with the registry:
1. **On startup** - After initializing backend connections
2. **Before accepting requests** - Ensures registry knows about the server
3. **Automatically** - No manual intervention required

### Registration Data

When registering, servers provide:

```python
{
    "id": "discord-mcp",                    # Unique server identifier
    "name": "Discord MCP Server",           # Human-readable name
    "description": "Bidirectional Discord integration for AI agents",
    "transport": "sse",                     # Transport type (sse, stdio, http)
    "connection_config": {
        "url": "https://discord-mcp.almckay.io/sse",  # External URL
        "internal_url": "http://discord-mcp-server.ai-agents.svc:8080/sse"  # Internal URL
    },
    "capabilities": [                       # List of tool names
        "send_message",
        "get_messages",
        "add_reaction",
        ...
    ],
    "status": "healthy",                    # Initial status
    "health_endpoint": "/health",           # Health check path
    "metrics_endpoint": "/metrics"          # Metrics path
}
```

### Registration Response

The registry responds with:
- **201 Created** - Registration successful
- **409 Conflict** - Server ID already exists (updates existing entry)
- **400 Bad Request** - Invalid registration data
- **500 Internal Server Error** - Registry error

### Implementation

Using the framework's `RegistryClient`:

```python
from kubani.framework.mcp.server.registry import RegistryClient

# Initialize client
registry_client = RegistryClient(
    registry_url="http://registry.ai-agents.svc:8000",
    server_id="myserver-mcp",
)

# Register
success = await registry_client.register(
    name="MyServer MCP Server",
    description="Integration with MyService",
    transport="sse",
    connection_config={
        "url": "https://myserver-mcp.almckay.io/sse",
        "internal_url": "http://myserver-mcp-server.ai-agents.svc:8080/sse"
    },
    capabilities=["tool1", "tool2", "tool3"],
)

if success:
    logger.info("Successfully registered with registry")
else:
    logger.warning("Failed to register with registry")
```

## Heartbeat Mechanism

### Purpose

Heartbeats serve multiple purposes:
1. **Liveness indication** - Proves server is still running
2. **Health status** - Reports backend health
3. **Timestamp update** - Updates last_heartbeat for monitoring
4. **Status synchronization** - Keeps registry in sync with actual state

### Heartbeat Interval

- **Default**: 30 seconds
- **Configurable**: Can be adjusted based on needs
- **Tolerance**: Registry marks unhealthy after 2 minutes without heartbeat

### Heartbeat Data

```python
{
    "status": "healthy",           # Overall server status
    "backend_status": {            # Optional backend health
        "discord_api": "healthy",
        "redis_cache": "healthy",
        "database": "degraded"
    }
}
```

### Implementation

The framework handles heartbeats automatically:

```python
# Start heartbeat task
async def get_backend_status() -> dict[str, str]:
    """Get backend health status for heartbeat."""
    if health_manager:
        health = await health_manager.check_all()
        return {
            name: backend.status.value 
            for name, backend in health.backends.items()
        }
    return {}

heartbeat_task = asyncio.create_task(
    registry_client.start_heartbeat(
        interval=30,
        get_backend_status=get_backend_status
    )
)

# On shutdown
heartbeat_task.cancel()
await heartbeat_task
```

### Heartbeat Lifecycle

```
Server Startup
     │
     ├─► Register with registry
     │
     ├─► Start heartbeat task
     │        │
     │        ├─► Every 30s: Send heartbeat
     │        │        │
     │        │        ├─► Success: Continue
     │        │        └─► Failure: Log warning, retry
     │        │
     │        └─► Loop until cancelled
     │
Server Shutdown
     │
     ├─► Cancel heartbeat task
     │
     └─► Unregister from registry
```

## Lifecycle Management

### Server States

MCP servers can be in one of three states:

1. **healthy** - Server is running and responding to heartbeats
2. **unhealthy** - Server missed heartbeats but still exists in cluster
3. **inactive** - Server no longer exists in Kubernetes

### State Transitions

```
    Register
       │
       ▼
   [healthy] ◄──────────────┐
       │                     │
       │ No heartbeat        │ Heartbeat received
       │ for 2 minutes       │
       ▼                     │
  [unhealthy] ───────────────┘
       │
       │ Not found in
       │ Kubernetes
       ▼
   [inactive]
       │
       │ Inactive for
       │ 24 hours
       ▼
    Removed
```

### Reconciliation Service

The registry runs a reconciliation service every 5 minutes:

1. **Query Kubernetes** - Get all deployments with label `mcp.kubani.io/server=true`
2. **Compare with registry** - Find servers in registry but not in Kubernetes
3. **Mark inactive** - Set status to "inactive" for missing servers
4. **Remove old entries** - Delete servers inactive for more than 24 hours
5. **Reactivate** - If a server reappears, change status back to "healthy"

### Reconciliation Logic

```python
# Pseudo-code for reconciliation
active_deployments = get_kubernetes_deployments()
registered_servers = get_registry_servers()

for server in registered_servers:
    if server.id not in active_deployments:
        if server.status != "inactive":
            # Mark as inactive
            server.status = "inactive"
            server.updated_at = now()
        else:
            # Check if should be removed
            if (now() - server.updated_at) > 24_hours:
                delete(server)
    else:
        # Server exists, ensure not marked inactive
        if server.status == "inactive":
            server.status = "healthy"
            server.updated_at = now()
```

### Kubernetes Label

For reconciliation to work, deployments must have the label:

```yaml
metadata:
  labels:
    mcp.kubani.io/server: "true"
    mcp.kubani.io/server-id: "myserver-mcp"  # Optional, falls back to deployment name
```

## Service Discovery

### Querying the Registry

Agents can discover MCP servers by querying the registry:

```bash
# Get all MCP servers
curl http://registry.ai-agents.svc:8000/api/v1/mcp/servers

# Get specific server
curl http://registry.ai-agents.svc:8000/api/v1/mcp/servers/discord-mcp

# Filter by status
curl http://registry.ai-agents.svc:8000/api/v1/mcp/servers?status=healthy
```

### Response Format

```json
{
  "servers": [
    {
      "id": "discord-mcp",
      "name": "Discord MCP Server",
      "description": "Bidirectional Discord integration",
      "transport": "sse",
      "connection_config": {
        "url": "https://discord-mcp.almckay.io/sse",
        "internal_url": "http://discord-mcp-server.ai-agents.svc:8080/sse"
      },
      "capabilities": [
        "send_message",
        "get_messages",
        "add_reaction"
      ],
      "status": "healthy",
      "health_endpoint": "/health",
      "metrics_endpoint": "/metrics",
      "last_heartbeat": "2026-02-06T10:30:00Z",
      "created_at": "2026-02-06T08:00:00Z",
      "updated_at": "2026-02-06T10:30:00Z"
    }
  ]
}
```

### Connection Selection

Agents should use:
- **internal_url** - When connecting from within the cluster
- **url** - When connecting from outside (via Tailscale)

```python
# Example: Agent selecting connection URL
def get_connection_url(server_info: dict, from_cluster: bool = True) -> str:
    """Get appropriate connection URL based on location."""
    if from_cluster:
        return server_info["connection_config"]["internal_url"]
    else:
        return server_info["connection_config"]["url"]
```

## Implementation Guide

### Complete Integration Example

```python
"""Complete registry integration example."""

import asyncio
import logging
import os
from contextlib import suppress

from kubani.framework.mcp.server.health import HealthCheckManager
from kubani.framework.mcp.server.registry import RegistryClient

logger = logging.getLogger(__name__)

# Global components
_registry_client: RegistryClient | None = None
_heartbeat_task: asyncio.Task | None = None
_health_manager: HealthCheckManager | None = None


async def initialize_registry_integration():
    """Initialize registry integration."""
    global _registry_client, _heartbeat_task, _health_manager
    
    # Get registry URL from environment
    registry_url = os.environ.get("REGISTRY_URL")
    if not registry_url:
        logger.info("REGISTRY_URL not set, skipping registry integration")
        return
    
    # Get server configuration
    server_id = os.environ.get("MCP_SERVER_ID", "myserver-mcp")
    external_url = os.environ.get(
        "MCP_EXTERNAL_URL", 
        "https://myserver-mcp.almckay.io/sse"
    )
    internal_url = os.environ.get(
        "MCP_INTERNAL_URL",
        "http://myserver-mcp-server.ai-agents.svc:8080/sse"
    )
    
    # Initialize registry client
    _registry_client = RegistryClient(
        registry_url=registry_url,
        server_id=server_id,
    )
    
    # Define capabilities (list of tool names)
    capabilities = [
        "my_tool_1",
        "my_tool_2",
        "my_tool_3",
    ]
    
    # Register with registry
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
        logger.info("Started heartbeat task")
    else:
        logger.warning("Failed to register with registry, continuing without registration")


async def shutdown_registry_integration():
    """Shutdown registry integration."""
    global _registry_client, _heartbeat_task
    
    # Cancel heartbeat task
    if _heartbeat_task:
        logger.info("Stopping heartbeat task")
        _heartbeat_task.cancel()
        with suppress(asyncio.CancelledError):
            await _heartbeat_task
    
    # Unregister from registry
    if _registry_client:
        logger.info("Unregistering from registry")
        await _registry_client.unregister()


# In your main function
async def main():
    """Main entry point."""
    try:
        # Initialize backend and health checks
        await initialize_backend()
        
        # Initialize registry integration
        await initialize_registry_integration()
        
        # Run MCP server
        await run_server()
        
    finally:
        # Cleanup
        await shutdown_registry_integration()
        await shutdown_backend()
```

### Environment Variables

Required environment variables for registry integration:

```bash
# Registry configuration
export REGISTRY_URL="http://registry.ai-agents.svc:8000"
export MCP_SERVER_ID="myserver-mcp"

# Connection URLs
export MCP_EXTERNAL_URL="https://myserver-mcp.almckay.io/sse"
export MCP_INTERNAL_URL="http://myserver-mcp-server.ai-agents.svc:8080/sse"
```

In Kubernetes deployment:

```yaml
env:
  - name: REGISTRY_URL
    value: "http://registry.ai-agents.svc:8000"
  - name: MCP_SERVER_ID
    value: "myserver-mcp"
  - name: MCP_EXTERNAL_URL
    value: "https://myserver-mcp.almckay.io/sse"
  - name: MCP_INTERNAL_URL
    value: "http://myserver-mcp-server.ai-agents.svc:8080/sse"
```

## Troubleshooting

### Server Not Appearing in Registry

**Symptoms**: Server is running but not listed in registry

**Checks**:
1. Verify REGISTRY_URL is set correctly
2. Check server logs for registration errors
3. Verify registry service is running
4. Test registry connectivity from pod

```bash
# Check environment variable
kubectl exec -n ai-agents deployment/myserver-mcp-server -- \
  env | grep REGISTRY_URL

# Test registry connectivity
kubectl exec -n ai-agents deployment/myserver-mcp-server -- \
  curl -v http://registry.ai-agents.svc:8000/api/v1/mcp/servers

# Check server logs
kubectl logs -n ai-agents deployment/myserver-mcp-server | grep -i registry
```

### Heartbeat Failures

**Symptoms**: Server registered but marked as unhealthy

**Checks**:
1. Verify heartbeat task is running
2. Check for network issues
3. Verify registry is accepting heartbeats
4. Check server logs for heartbeat errors

```bash
# Check server logs for heartbeat
kubectl logs -n ai-agents deployment/myserver-mcp-server | grep -i heartbeat

# Check registry logs
kubectl logs -n ai-agents deployment/registry | grep -i heartbeat
```

### Server Marked as Inactive

**Symptoms**: Server is running but marked inactive in registry

**Checks**:
1. Verify deployment has required labels
2. Check reconciliation service logs
3. Verify server ID matches deployment

```bash
# Check deployment labels
kubectl get deployment myserver-mcp-server -n ai-agents -o yaml | grep -A 5 labels

# Verify mcp.kubani.io/server label
kubectl get deployment myserver-mcp-server -n ai-agents \
  -o jsonpath='{.metadata.labels.mcp\.kubani\.io/server}'

# Check reconciliation logs
kubectl logs -n ai-agents deployment/registry | grep -i reconcil
```

### Registration Conflicts

**Symptoms**: 409 Conflict error during registration

**Cause**: Server ID already exists in registry

**Solutions**:
1. Use unique server IDs
2. Unregister old entry if it's stale
3. Let reconciliation clean up old entries

```bash
# Check existing registrations
curl http://registry.ai-agents.svc:8000/api/v1/mcp/servers

# Manually unregister (if needed)
curl -X DELETE http://registry.ai-agents.svc:8000/api/v1/mcp/servers/myserver-mcp
```

### Connection URL Issues

**Symptoms**: Agents can't connect using registry-provided URLs

**Checks**:
1. Verify URLs are correct in registration
2. Test both internal and external URLs
3. Check DNS resolution
4. Verify ingress configuration

```bash
# Test internal URL from within cluster
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -- \
  curl -v http://myserver-mcp-server.ai-agents.svc:8080/health

# Test external URL (from outside cluster)
curl -v https://myserver-mcp.almckay.io/health
```

## Best Practices

1. **Always register on startup** - Before accepting requests
2. **Always unregister on shutdown** - Clean up registry entries
3. **Use unique server IDs** - Avoid conflicts
4. **Provide both URLs** - Internal and external connection options
5. **Include all capabilities** - List all tool names
6. **Monitor heartbeats** - Alert on heartbeat failures
7. **Use proper labels** - Enable reconciliation
8. **Handle failures gracefully** - Continue running even if registration fails

## Next Steps

1. Implement registry integration in your MCP server
2. Verify registration in registry
3. Test heartbeat mechanism
4. Verify reconciliation works correctly
5. Test service discovery from agents

## Additional Resources

- [Development Guide](development-guide.md)
- [Testing Guide](testing-guide.md)
- [Deployment Guide](deployment-guide.md)
- [Registry API Documentation](../../platform/registry/README.md)
