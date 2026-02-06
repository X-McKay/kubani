# Post-Deployment Testing for MCP Servers

This document describes the post-deployment test suite for MCP servers and how to use it.

## Overview

Post-deployment tests verify that deployed MCP servers are accessible and functional in the cluster environment. These tests run against live deployments and validate:

1. **SSE Connectivity** - Servers are accessible via SSE transport
2. **Registry Discovery** - Servers are registered and discoverable
3. **End-to-End Tool Execution** - Tools can be called and execute successfully
4. **Backend Connectivity** - Servers can connect to their backend services

## Test Categories

### SSE Connectivity Tests (Subtask 10.1)

Tests that verify SSE endpoints are accessible:

- `test_sse_endpoint_accessible` - Basic SSE endpoint connectivity
- `test_sse_connection_from_external` - Connection via Tailscale egress URLs
- `test_sse_connection_from_within_cluster` - Connection from within Kubernetes cluster
- `test_health_endpoint_accessible` - Health endpoint accessibility
- `test_metrics_endpoint_accessible` - Metrics endpoint accessibility

**Requirements validated:** 2.5

### Registry Discovery Tests (Subtask 10.2)

Tests that verify registry integration:

- `test_registry_accessible` - Registry service is accessible
- `test_query_mcp_servers_from_registry` - Can query for MCP servers
- `test_server_registered_in_registry` - Each server is registered
- `test_registry_connection_info_correct` - Connection info is correct and usable

**Requirements validated:** 8.3

### End-to-End Tool Execution Tests (Subtask 10.3)

Tests that verify tool execution:

- `test_tool_execution_via_http` - Tools can be called via HTTP
- `test_server_backend_connectivity` - Backend services are accessible
- `test_end_to_end_server_discovery_and_connection` - Complete discovery and connection flow

**Requirements validated:** 8.1, 8.2

## Running Tests

### Locally (requires Tailscale connection)

Run all post-deployment tests:

```bash
just mcp-test-deployed
```

Or using pytest directly:

```bash
uv run pytest kubani/mcp/servers/tests/test_deployment.py -v -m deployment
```

Run tests for a specific server:

```bash
uv run pytest kubani/mcp/servers/tests/test_deployment.py -v -m deployment -k discord
```

### In CI/CD

Post-deployment tests run automatically:

1. **After deployments** - Triggered by the "Deploy MCP Servers" workflow
2. **On schedule** - Daily at 6 AM UTC
3. **Manual trigger** - Via GitHub Actions workflow dispatch

The workflow is defined in `.github/workflows/mcp-deployment-tests.yml`.

### Environment Variables

- `REGISTRY_URL` - Internal registry URL (default: `http://registry.ai-agents.svc:8000`)
- `REGISTRY_EXTERNAL_URL` - External registry URL (default: `https://registry.almckay.io`)

## Test Configuration

### Server Configuration

Servers are configured in `test_deployment.py`:

```python
DEPLOYED_SERVERS = {
    "discord-mcp": {
        "external_url": "https://discord-mcp.almckay.io",
        "internal_url": "http://discord-mcp-server.ai-agents.svc:8080",
        "test_tool": "list_channels",
        "test_args": {},
        "skip_reason": None,
    },
    # ... more servers
}
```

### Environment Detection

Tests automatically detect whether they're running inside or outside the Kubernetes cluster:

- **Inside cluster** - Uses internal service URLs (`*.svc:8080`)
- **Outside cluster** - Uses external Tailscale URLs (`*.almckay.io`)

## CI/CD Integration

### GitHub Actions Workflow

The workflow (`.github/workflows/mcp-deployment-tests.yml`) includes:

1. **Tailscale Setup** - Connects to the cluster network
2. **Test Execution** - Runs all post-deployment tests
3. **Result Publishing** - Uploads test results as artifacts
4. **Failure Notifications** - Creates GitHub issues on failure

### Required Secrets

- `TAILSCALE_OAUTH_CLIENT_ID` - Tailscale OAuth client ID
- `TAILSCALE_OAUTH_SECRET` - Tailscale OAuth secret

### Workflow Triggers

- **Schedule**: Daily at 6 AM UTC
- **Workflow Run**: After "Deploy MCP Servers" completes successfully
- **Manual**: Via workflow dispatch (can specify specific server)

## Troubleshooting

### Tests Fail to Connect

1. **Check Tailscale connection**:
   ```bash
   tailscale status
   ```

2. **Verify server is deployed**:
   ```bash
   kubectl get pods -n ai-agents -l app.kubernetes.io/name=discord-mcp-server
   ```

3. **Check server health**:
   ```bash
   curl https://discord-mcp.almckay.io/health
   ```

### Registry Tests Fail

1. **Verify registry is accessible**:
   ```bash
   curl https://registry.almckay.io/health
   ```

2. **Check server registration**:
   ```bash
   curl https://registry.almckay.io/api/v1/mcp/servers
   ```

### Backend Connectivity Tests Fail

1. **Check server health endpoint** for backend status:
   ```bash
   curl https://memory-mcp.almckay.io/health | jq .backends
   ```

2. **Verify backend services are running**:
   ```bash
   kubectl get pods -n database
   kubectl get pods -n cache
   ```

## Adding New Tests

To add tests for a new MCP server:

1. Add server configuration to `DEPLOYED_SERVERS` in `test_deployment.py`
2. Specify external and internal URLs
3. Define a test tool and arguments
4. Tests will automatically run for the new server

Example:

```python
DEPLOYED_SERVERS = {
    # ... existing servers
    "new-mcp": {
        "external_url": "https://new-mcp.almckay.io",
        "internal_url": "http://new-mcp-server.ai-agents.svc:8080",
        "test_tool": "list_items",
        "test_args": {},
        "skip_reason": None,
    },
}
```

## Test Markers

Tests use the `deployment` marker:

```python
@pytest.mark.deployment
async def test_something():
    ...
```

Run only deployment tests:

```bash
pytest -m deployment
```

Skip deployment tests:

```bash
pytest -m "not deployment"
```

## Related Documentation

- [MCP Server Development Guide](../../../docs/mcp-servers/development-guide.md)
- [MCP Server Testing Guide](../../../docs/mcp-servers/testing-guide.md)
- [MCP Server Deployment Guide](../../../docs/mcp-servers/deployment-guide.md)
- [Integration Testing Guide](./INTEGRATION_TESTING.md)
