# Kubani Registry Service

Centralized metadata registry for the Kubani AI agent ecosystem. Provides persistent storage and APIs for managing agents, MCP servers, skills, deployments, models, and endpoints.

## Features

- **Agent Registry**: Track registered agents with capabilities, heartbeats, and status
- **MCP Server Registry**: Manage MCP server configurations and access policies
- **Skill Metadata**: Store skill metrics (confidence, success/failure counts) synced from Qdrant
- **Deployment Tracking**: Audit trail for agent deployments with rollback support
- **Model Registry**: Track LLM models with capabilities and serving endpoints
- **Endpoint Registry**: Service discovery with health checking and URL resolution

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Redis (optional, for caching)

### Local Development

```bash
# Install dependencies
uv sync --all-extras

# Set environment variables (or use .env.development)
export REGISTRY_DATABASE_URL=postgresql://kubani:kubani@localhost:5432/kubani_registry  # pragma: allowlist secret

# Run database migrations
uv run alembic upgrade head

# Start the service
uv run kubani-registry
```

### Using Docker

```bash
# Build image
earthly +docker --VERSION=0.1.0

# Run container
docker run -p 8000:8000 \
  -e REGISTRY_DATABASE_URL=postgresql://user:pass@host:5432/kubani_registry \  # pragma: allowlist secret
  registry.almckay.io/kubani-registry:0.1.0
```

## Configuration

| Environment Variable | Description | Default |
|---------------------|-------------|---------|
| `REGISTRY_DATABASE_URL` | PostgreSQL connection string | `postgresql://kubani:kubani@localhost:5432/kubani_registry` | <!-- pragma: allowlist secret -->
| `REGISTRY_REDIS_URL` | Redis connection string (optional) | `redis://localhost:6379` |
| `REGISTRY_HOST` | Service host | `0.0.0.0` |
| `REGISTRY_PORT` | Service port | `8000` |
| `REGISTRY_LOG_LEVEL` | Logging level | `INFO` |
| `REGISTRY_DATABASE_ECHO` | Echo SQL statements | `false` |
| `REGISTRY_HEARTBEAT_TIMEOUT_SECONDS` | Mark agents unhealthy after | `90` |
| `REGISTRY_HEALTH_CHECK_INTERVAL` | Endpoint health check interval | `60` |

## API Endpoints

### Agents

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/agents` | Register or update an agent |
| `GET` | `/api/v1/agents` | List all agents |
| `GET` | `/api/v1/agents/{id}` | Get agent by ID |
| `DELETE` | `/api/v1/agents/{id}` | Unregister an agent |
| `PUT` | `/api/v1/agents/{id}/heartbeat` | Update agent heartbeat |
| `GET` | `/api/v1/agents/capability/{name}` | Find agents by capability |

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/endpoints` | Register an endpoint |
| `GET` | `/api/v1/endpoints` | List all endpoints |
| `GET` | `/api/v1/endpoints/{id}` | Get endpoint by ID |
| `PUT` | `/api/v1/endpoints/{id}/health` | Update health status |
| `GET` | `/api/v1/endpoints/resolve/{id}` | Resolve endpoint URL |
| `GET` | `/api/v1/endpoints/type/{type}` | List by service type |

### Models

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/models` | Register a model |
| `GET` | `/api/v1/models` | List all models |
| `GET` | `/api/v1/models/{id}` | Get model by ID |
| `GET` | `/api/v1/models/type/{type}` | List by model type |
| `PUT` | `/api/v1/models/{id}/status` | Update model status |

### MCP Servers

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/mcp/servers` | Register an MCP server |
| `GET` | `/api/v1/mcp/servers` | List all MCP servers |
| `GET` | `/api/v1/mcp/servers/{id}` | Get server by ID |
| `DELETE` | `/api/v1/mcp/servers/{id}` | Delete an MCP server |
| `POST` | `/api/v1/mcp/servers/{id}/policies` | Create access policy |
| `GET` | `/api/v1/mcp/policy/{agent_id}` | Get effective policy for agent |

### Skills

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/skills` | Create/update skill metadata |
| `GET` | `/api/v1/skills` | List skills with filters |
| `GET` | `/api/v1/skills/{id}` | Get skill by ID |
| `PUT` | `/api/v1/skills/{id}/outcome` | Record execution outcome |
| `PUT` | `/api/v1/skills/{id}/status` | Update validation status |

### Deployments

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/deployments` | Record a deployment |
| `GET` | `/api/v1/deployments` | List recent deployments |
| `GET` | `/api/v1/deployments/agent/{id}` | Get deployment history |
| `GET` | `/api/v1/deployments/agent/{id}/latest` | Get latest active deployment |
| `POST` | `/api/v1/deployments/{id}/rollback` | Rollback to deployment |

### Health & Metrics

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness probe |
| `GET` | `/ready` | Readiness probe (checks DB) |
| `GET` | `/metrics` | Prometheus metrics |
| `GET` | `/docs` | Swagger UI |

## MCP Server

The registry includes an MCP server for Claude Code integration:

```bash
# Run MCP server locally
uv run kubani-registry-mcp
```

Add to `.claude/mcp.json`:

```json
{
  "mcpServers": {
    "kubani-registry": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/kubani/registry", "kubani-registry-mcp"],
      "env": {
        "REGISTRY_URL": "http://localhost:8000"
      }
    }
  }
}
```

Or via SSE for cluster access:

```json
{
  "mcpServers": {
    "kubani-registry": {
      "url": "https://registry.almckay.io/mcp/sse"
    }
  }
}
```

### MCP Tools

- `list_agents` - List registered agents with status
- `get_agent` - Get agent details by ID
- `list_endpoints` - List service endpoints
- `get_endpoint` - Get endpoint details
- `resolve_endpoint` - Resolve to best URL
- `list_models` - List LLM models
- `list_mcp_servers` - List MCP servers
- `get_mcp_policy` - Get effective policy for agent
- `list_deployments` - List recent deployments
- `list_skills` - List skills with confidence scores

## Database Schema

The registry uses PostgreSQL with the following tables:

- `agents` - Registered agents
- `agent_capabilities` - Agent capabilities (1:N)
- `mcp_servers` - MCP server configurations
- `mcp_policies` - Access policies for MCP servers
- `skill_metadata` - Skill metrics and status
- `deployments` - Deployment audit trail
- `models` - LLM model registry
- `endpoints` - Service endpoints
- `model_endpoints` - Model-endpoint associations
- `endpoint_dependencies` - Service dependencies

### Migrations

```bash
# Apply migrations
uv run alembic upgrade head

# Create new migration
uv run alembic revision --autogenerate -m "description"

# Rollback one migration
uv run alembic downgrade -1
```

## Client Library

For Python agents, use the `RegistryClient` from `core_agents`:

```python
from core_agents.registry import RegistryClient, get_registry_client

# Get singleton client
client = get_registry_client()

# Register agent
await client.register_agent(
    agent_id="my-agent",
    name="My Agent",
    capabilities=[{"name": "analyze", "description": "Analyze data"}],
)

# Start heartbeat background task
await client.start_heartbeat()

# Resolve endpoint URL
endpoint = await client.resolve_endpoint("vllm-general")
print(endpoint.url)  # http://vllm.vllm.svc:8000/v1
```

## Development

### Running Tests

```bash
# All tests
uv run pytest

# Unit tests only
uv run pytest tests/test_models.py

# Integration tests (requires PostgreSQL)
uv run pytest tests/test_api.py

# With coverage
uv run pytest --cov=kubani_registry --cov-report=term-missing
```

### Code Quality

```bash
# Linting
uv run ruff check src/

# Formatting
uv run ruff format src/

# Type checking
uv run mypy src/
```

### Building

```bash
# Build Docker image
earthly +docker --VERSION=0.1.0

# Push to registry
earthly --push +push --VERSION=0.1.0

# Run tests in container
earthly +test
```

## Deployment

### Kubernetes (GitOps)

Manifests are in `gitops/apps/registry/`:

```bash
# Apply manually
kubectl apply -k gitops/apps/registry/

# Or let Flux sync automatically
git push origin main
```

### Environment URLs

| Environment | URL |
|-------------|-----|
| Development | `http://localhost:8000` |
| Cluster Internal | `http://registry.ai-agents.svc:8000` |
| External (Tailscale) | `https://registry.almckay.io` |

## Architecture

```
registry/
├── src/
│   ├── kubani_registry/          # FastAPI service
│   │   ├── main.py               # Application entry point
│   │   ├── config.py             # Pydantic settings
│   │   ├── api/v1/               # API endpoints
│   │   │   ├── agents.py
│   │   │   ├── endpoints.py
│   │   │   ├── models.py
│   │   │   ├── mcp.py
│   │   │   ├── skills.py
│   │   │   └── deployments.py
│   │   └── db/
│   │       ├── models.py         # SQLAlchemy ORM
│   │       └── session.py        # Async session management
│   └── kubani_registry_mcp/      # MCP server
│       ├── server.py
│       ├── tools.py
│       └── resources.py
├── alembic/                      # Database migrations
├── tests/
├── Earthfile                     # Build definitions
└── pyproject.toml
```

## License

MIT License - See LICENSE file for details.
