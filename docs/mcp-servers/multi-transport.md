# Multi-Transport Support for MCP Servers

All Kubani MCP servers support three transport mechanisms: SSE (Server-Sent Events), stdio, and HTTP. This document describes how to configure and use each transport mode.

## Transport Modes

### 1. SSE (Server-Sent Events)
- **Use case**: Production deployments, web-based clients, remote access
- **Port**: Configurable (default: 8080)
- **Protocol**: HTTP with streaming
- **Best for**: Agents running in Kubernetes, web UIs, remote connections

### 2. stdio (Standard Input/Output)
- **Use case**: Local development, CLI tools, direct process communication
- **Port**: N/A (uses stdin/stdout)
- **Protocol**: JSON-RPC over stdio
- **Best for**: Local testing, IDE integrations, command-line tools

### 3. HTTP (Streamable HTTP)
- **Use case**: HTTP-based clients, REST-like interactions
- **Port**: Configurable (default: 8080)
- **Protocol**: HTTP with streaming support
- **Best for**: HTTP clients that need streaming responses

## Configuration

### Command-Line Arguments

All MCP servers accept the following command-line arguments:

```bash
# Start with SSE transport (default port 8080)
python -m discord_mcp.server --mode sse

# Start with SSE on custom port
python -m discord_mcp.server --mode sse --port 9000

# Start with stdio transport
python -m discord_mcp.server --mode stdio

# Start with HTTP transport
python -m discord_mcp.server --mode http --port 8080

# Specify host binding
python -m discord_mcp.server --mode sse --host 0.0.0.0 --port 8080
```

### Environment Variables

Transport configuration can also be set via environment variables:

```bash
# Set transport mode
export MCP_TRANSPORT=sse  # or stdio, http

# Set host and port
export MCP_HOST=0.0.0.0
export MCP_PORT=8080

# Set allowed hosts for security
export MCP_ALLOWED_HOSTS="example.com:*,*.example.com:*"
```

### Kubernetes Deployment

In Kubernetes deployments, configure transport via container args:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: discord-mcp-server
spec:
  template:
    spec:
      containers:
      - name: mcp-server
        image: discord-mcp:latest
        args:
          - --mode
          - sse
          - --port
          - "8080"
          - --host
          - "0.0.0.0"
        ports:
          - name: http
            containerPort: 8080
```

## Server-Specific Configuration

### Discord MCP Server

```bash
# SSE mode (production)
python -m discord_mcp.server --mode sse --port 8080

# stdio mode (local development)
python -m discord_mcp.server --mode stdio

# HTTP mode
python -m discord_mcp.server --mode http --port 8080
```

**Environment variables required:**
- `DISCORD_BOT_TOKEN`: Discord bot token
- `DISCORD_GUILD_ID`: (Optional) Default guild ID

### Memory MCP Server

```bash
# SSE mode (production)
python -m memory_mcp.server --mode sse --port 8080

# stdio mode (local development)
python -m memory_mcp.server --mode stdio
```

**Environment variables required:**
- `QDRANT_HOST`, `QDRANT_PORT`: Qdrant connection
- `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`: Neo4j connection
- `REDIS_HOST`, `REDIS_PORT`: Redis connection

### Skills MCP Server

```bash
# SSE mode (production)
python -m skills_mcp.server --mode sse --port 8080

# With custom skills path
python -m skills_mcp.server --mode sse --skills-path /path/to/skills
```

**Environment variables:**
- `SKILLS_PATH`: Path to skills directory
- `MICROSANDBOX_ENABLED`: Enable Microsandbox execution
- `MICROSANDBOX_URL`: Microsandbox service URL

### Temporal MCP Server

```bash
# SSE mode (production)
python -m temporal_mcp.server --mode sse --port 8080
```

**Environment variables required:**
- `TEMPORAL_HOST`: Temporal server host
- `TEMPORAL_PORT`: Temporal server port (default: 7233)
- `TEMPORAL_NAMESPACE`: Temporal namespace (default: default)

### Qdrant MCP Server

```bash
# SSE mode (production)
python -m qdrant_mcp.server --mode sse --port 8080
```

**Environment variables required:**
- `QDRANT_HOST`: Qdrant host
- `QDRANT_PORT`: Qdrant port (default: 6333)
- `QDRANT_API_KEY`: (Optional) Qdrant API key
- `QDRANT_HTTPS`: Use HTTPS (default: false)

## Testing Multi-Transport Support

### Manual Testing

Test each transport mode manually:

```bash
# Test SSE mode
python -m discord_mcp.server --mode sse --port 8080 &
curl http://localhost:8080/sse

# Test stdio mode
echo '{"jsonrpc":"2.0","method":"tools/list","id":1}' | python -m discord_mcp.server --mode stdio

# Test HTTP mode
python -m discord_mcp.server --mode http --port 8080 &
curl http://localhost:8080/
```

### Automated Testing

Run property-based tests to verify transport consistency:

```bash
# Run multi-transport property tests
uv run pytest tests/properties/test_multi_transport.py -v

# Run for specific server
uv run pytest tests/properties/test_multi_transport.py::test_discord_multi_transport -v
```

## Transport Behavior Consistency

All transport modes provide identical functionality:
- Same tools available
- Same input/output formats
- Same error handling
- Same authentication/authorization

The only differences are:
- Connection mechanism (SSE vs stdio vs HTTP)
- Network requirements (SSE/HTTP need network, stdio doesn't)
- Performance characteristics (stdio is fastest for local use)

## Security Considerations

### SSE and HTTP Modes

- **DNS Rebinding Protection**: Enabled by default
- **Allowed Hosts**: Configure via `MCP_ALLOWED_HOSTS` environment variable
- **TLS**: Use reverse proxy (nginx, Tailscale) for TLS termination
- **Authentication**: Implement at reverse proxy level

### stdio Mode

- **Local Only**: No network exposure
- **Process Isolation**: Runs in same security context as parent process
- **No Authentication**: Assumes trusted local environment

## Troubleshooting

### SSE Connection Issues

```bash
# Check if server is listening
netstat -an | grep 8080

# Test connection
curl -v http://localhost:8080/sse

# Check logs
tail -f /var/log/mcp-server.log
```

### stdio Communication Issues

```bash
# Test with simple JSON-RPC message
echo '{"jsonrpc":"2.0","method":"tools/list","id":1}' | python -m discord_mcp.server --mode stdio

# Check stderr for errors
python -m discord_mcp.server --mode stdio 2>error.log
```

### HTTP Connection Issues

```bash
# Check if server is listening
curl -v http://localhost:8080/

# Test with HTTP client
curl -X POST http://localhost:8080/ \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
```

## Implementation Details

All servers use the shared `TransportConfig` class from `kubani.framework.mcp.server.transport`:

```python
from kubani.framework.mcp.server.transport import TransportConfig, run_server_async

# Parse transport config from command-line args
config = TransportConfig.from_args()

# Or from environment variables
config = TransportConfig.from_env()

# Run server with config
await run_server_async(mcp, config)
```

The `run_server_async` function handles transport selection automatically based on the configuration.

## Best Practices

1. **Production**: Use SSE mode with proper reverse proxy and TLS
2. **Development**: Use stdio mode for fastest iteration
3. **Testing**: Test all three modes to ensure consistency
4. **Deployment**: Always specify `--mode` explicitly in deployment manifests
5. **Security**: Configure `MCP_ALLOWED_HOSTS` for SSE/HTTP modes
6. **Monitoring**: Use health and metrics endpoints (port 9090) regardless of transport mode

## References

- [MCP Specification](https://spec.modelcontextprotocol.io/)
- [FastMCP Documentation](https://github.com/jlowin/fastmcp)
- [Development Guide](development-guide.md)
- [Testing Guide](testing-guide.md)
