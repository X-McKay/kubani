---
name: local-development
description: Complete guide for local agent development using kubani-dev CLI, unified configuration, MCP integration, and seamless iteration.
---

# Local Development Guide

This is the comprehensive guide for developing Kubani agents locally with cluster services.

## Quick Start

```bash
# Install kubani-dev CLI
uv pip install -e platform/cli

# Initialize configuration
kubani-dev init

# Run agent locally with cluster services
kubani-dev local-run --agent k8s-monitor --temporal cluster --output console

# Run with hot-reload for rapid iteration
kubani-dev local-run --agent k8s-monitor --hot-reload
```

## kubani-dev CLI Reference

### Core Commands

| Command | Description |
|---------|-------------|
| `kubani-dev init` | Initialize configuration |
| `kubani-dev local-run` | Run agent locally |
| `kubani-dev test` | Run tests |
| `kubani-dev eval` | Run evaluations |
| `kubani-dev deploy` | Deploy to cluster |

### local-run Options

```bash
kubani-dev local-run --agent <name> [options]

Options:
  --temporal [local|cluster]  Temporal mode (default: local)
  --output [console|discord|both]  Output mode (default: console)
  --hot-reload               Enable hot-reload on file changes
  --mock-services            Use mock services (no cluster needed)
  --tunnel                   Enable cluster service tunneling
```

### Examples

```bash
# Basic local run
kubani-dev local-run --agent k8s-monitor

# With cluster Temporal and Discord output
kubani-dev local-run --agent k8s-monitor --temporal cluster --output both

# With hot-reload for development
kubani-dev local-run --agent k8s-monitor --hot-reload

# With mock services (no cluster needed)
kubani-dev local-run --agent k8s-monitor --mock-services
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

# MCP Server URLs
mcp:
  temporal_url: http://localhost:8081
  qdrant_url: http://localhost:8082
  memory_url: http://localhost:8083
  discord_url: http://localhost:8084

# Temporal configuration
temporal:
  host: localhost:7233  # or temporal.almckay.io:7233 for cluster
  namespace: default

# Memory services
memory:
  qdrant:
    host: qdrant.almckay.io
    port: 443
  neo4j:
    uri: bolt://neo4j.almckay.io:7687
  redis:
    host: redis.almckay.io

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
```

## MCP Client Integration

Agents use the unified MCP client for all tool access:

```python
from kubani.framework.mcp import get_mcp_client
from kubani.framework.config import get_config

config = get_config()
client = get_mcp_client()

# Check MCP server health
health = await client.health_check_all()

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

## Testing

```bash
# Run all tests for an agent
kubani-dev test k8s-monitor

# Run with coverage
kubani-dev test k8s-monitor --coverage

# Run specific tests
kubani-dev test k8s-monitor --filter "test_pod"
```

## Evaluation

```bash
# Run full evaluation suite
kubani-dev eval k8s-monitor

# Run specific evaluation layer
kubani-dev eval k8s-monitor --layer llm

# Run specific evaluation suite
kubani-dev eval run --suite evaluations/k8s/pod_remediation.yaml
```

## Deployment

```bash
# Build container image
kubani-dev build k8s-monitor

# Deploy to cluster
kubani-dev deploy --agent k8s-monitor --wait

# Monitor deployment
kubani-dev deploy --agent k8s-monitor --status
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

## See Also

- [Agent Evaluation](../agent-evaluation/SKILL.md) - Evaluation framework
- [Continuous Learning](../continuous-learning/SKILL.md) - Learning system
- [Deployment](../deployment/SKILL.md) - Deployment automation
- [MCP Servers](../mcp-servers/SKILL.md) - MCP server development
