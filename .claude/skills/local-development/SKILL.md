---
name: local-development
description: Run agents locally with cluster services using the unified development workflow. Supports Temporal mode selection, output routing, MCP integration, and seamless iteration.
---

# Local Development Workflow

The local development workflow enables seamless agent development with cluster services via the unified configuration system and MCP client.

## Quick Start

```bash
# Run agent locally with cluster services
kubani-dev local-run --agent k8s-monitor --temporal cluster --output console

# Run with local Temporal (no cluster needed)
kubani-dev local-run --agent k8s-monitor --temporal local --output console

# Run with hot-reload for rapid iteration
kubani-dev local-run --agent k8s-monitor --temporal cluster --output both --hot-reload
```

## Configuration System

### Hierarchical Config Loading

Configuration is loaded in order (later overrides earlier):

1. `config.default.yaml` - Base defaults (committed)
2. `config.{environment}.yaml` - Environment-specific (committed)
3. `config.local.yaml` - Local overrides (gitignored)
4. Environment variables with `KUBANI_` prefix

### Create Local Config

```bash
cat > config.local.yaml << 'EOF'
environment: development

# MCP Server URLs (local or cluster)
mcp:
  temporal_url: http://localhost:8081
  qdrant_url: http://localhost:8082
  memory_url: http://localhost:8083
  discord_url: http://localhost:8084

# Temporal configuration
temporal:
  host: localhost:7233  # or temporal.almckay.io:7233 for cluster
  namespace: default
  enabled: true

# Memory services
memory:
  qdrant:
    host: qdrant.almckay.io
    port: 443
  neo4j:
    uri: bolt://neo4j.almckay.io:7687
  redis:
    host: redis.almckay.io
    port: 6379

# LLM configuration
llm:
  api_url: https://llm.almckay.io/v1
  model: nvidia/Qwen3-14B-FP4

# Local development settings
local_dev:
  enabled: true
  output_mode: console
  hot_reload: true
EOF
```

### Environment Variables

Override any config with environment variables:

```bash
export KUBANI_ENVIRONMENT=development
export KUBANI_TEMPORAL__HOST=localhost:7233
export KUBANI_LLM__API_URL=https://llm.almckay.io/v1
export KUBANI_MCP__TEMPORAL_URL=http://localhost:8081
```

## MCP Client Integration

Agents use the unified MCP client for all tool access:

```python
from core_agents.mcp import get_mcp_client
from core_agents.config_unified import get_config

config = get_config()
client = get_mcp_client()

# Check MCP server health
health = await client.health_check_all()
print(health)  # {'temporal': True, 'qdrant': True, 'memory': True, ...}

# Temporal operations
workflows = await client.temporal.list_workflows(status="running")
await client.temporal.signal_workflow(workflow_id, "pause")

# Memory operations
await client.memory.store_learning(
    agent_id="k8s-monitor",
    learning_type="pattern",
    content="OOM kills indicate memory pressure",
    confidence=0.85,
)
results = await client.memory.query_learnings(query="memory issues")

# Qdrant operations
await client.qdrant.search_vectors(
    collection="skills",
    query_vector=embedding,
    limit=5,
)

# Discord operations
await client.discord.send_embed(
    channel_id=config.discord.alerts_channel,
    title="Test Alert",
    description="Testing from local development",
)
```

## Running Agents

### K8s Monitor

```bash
# Basic local run
kubani-dev local-run --agent k8s-monitor --temporal cluster --output console

# With hot-reload
kubani-dev local-run --agent k8s-monitor --temporal cluster --hot-reload

# With mock services (no cluster needed)
kubani-dev local-run --agent k8s-monitor --temporal local --mock-services
```

### News Monitor

```bash
# Run news monitor locally
kubani-dev local-run --agent news-monitor --temporal cluster --output console

# Test digest generation
kubani-dev local-run --agent news-monitor --temporal local --workflow generate-digest
```

## Temporal Modes

### Local Temporal

```bash
# Start local Temporal first
temporal server start-dev

# Run agent with local Temporal
kubani-dev local-run --agent k8s-monitor --temporal local
```

### Cluster Temporal

```bash
# Connect to cluster Temporal (requires Tailscale)
kubani-dev local-run --agent k8s-monitor --temporal cluster
```

## Output Modes

| Mode | Description |
|------|-------------|
| `console` | Output to stdout (default) |
| `discord` | Output to Discord channels |
| `both` | Output to both console and Discord |

```bash
kubani-dev local-run --agent k8s-monitor --output console
kubani-dev local-run --agent k8s-monitor --output discord
kubani-dev local-run --agent k8s-monitor --output both
```

## Debugging

### View Logs

```bash
# Run with debug logging
KUBANI_LOG_LEVEL=DEBUG kubani-dev local-run --agent k8s-monitor

# View Temporal UI
open https://temporal.almckay.io
```

### Test Configuration

```python
from core_agents.config_unified import get_config

config = get_config()
print(f"Environment: {config.environment}")
print(f"Temporal: {config.temporal.host}")
print(f"LLM: {config.llm.api_url}")
print(f"MCP Servers: {config.get_mcp_servers()}")
```

### Test MCP Connectivity

```python
from core_agents.mcp import get_mcp_client

client = get_mcp_client()
health = await client.health_check_all()
print(health)
```

## Troubleshooting

### Temporal Connection Failed

```bash
# Check Temporal accessibility
curl -s https://temporal.almckay.io/health

# Or start local Temporal
temporal server start-dev
```

### MCP Server Not Responding

```bash
# Check MCP server health
curl -s http://localhost:8081/health  # Temporal MCP
curl -s http://localhost:8082/health  # Qdrant MCP
curl -s http://localhost:8083/health  # Memory MCP
```

### LLM API Errors

```bash
# Test LLM connectivity
curl -s https://llm.almckay.io/v1/models
```

## Development Workflow

```bash
# 1. Create local config
cp config.default.yaml config.local.yaml
# Edit with your settings

# 2. Start local development with hot-reload
kubani-dev local-run --agent k8s-monitor --hot-reload

# 3. Make code changes (auto-reloads)

# 4. Test with cluster services
kubani-dev local-run --agent k8s-monitor --temporal cluster --output both

# 5. Run evaluations
kubani-dev eval run --suite evaluations/k8s/pod_remediation.yaml

# 6. Deploy when ready
kubani-dev deploy --agent k8s-monitor --wait
```
