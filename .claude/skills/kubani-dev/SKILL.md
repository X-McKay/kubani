---
name: kubani-dev
description: Use the kubani-dev CLI for agent development, testing, evaluation, and deployment. The primary tool for agent development workflow.
---

# kubani-dev CLI

The kubani-dev CLI is the primary tool for agent development in Kubani.

## Installation

```bash
pip install -e tools/kubani-dev
# Or via just:
just install-kubani-dev
```

## Quick Reference

```bash
# Initialize configuration
kubani-dev init

# Run agent locally
kubani-dev run k8s-monitor              # Basic run
kubani-dev run k8s-monitor --hot-reload # With hot-reload
kubani-dev run k8s-monitor --mock-mcp   # With mock MCP servers

# Testing
kubani-dev test k8s-monitor             # Run all tests
kubani-dev test k8s-monitor --coverage  # With coverage

# Evaluation
kubani-dev eval k8s-monitor             # Full evaluation
kubani-dev eval k8s-monitor --layer llm # LLM-as-judge only

# Observability
kubani-dev dashboard                    # Start dashboard
kubani-dev trace k8s-monitor            # View traces
kubani-dev metrics k8s-monitor          # View metrics

# Deployment
kubani-dev build k8s-monitor            # Build container
kubani-dev deploy k8s-monitor           # Deploy to cluster
kubani-dev monitor k8s-monitor          # Monitor deployment

# Agent Creation
kubani-dev new my-agent                 # Default template
kubani-dev new my-agent --template federated

# Skills
kubani-dev skills validate              # Validate all skills
kubani-dev skills list                  # List skills
```

## Commands

### init

Initialize kubani-dev configuration:

```bash
kubani-dev init
```

Creates `.kubani-dev/config.yaml` with:
- Agent paths
- Service endpoints
- Default settings

### run

Run an agent locally for development:

```bash
kubani-dev run <agent> [options]

Options:
  --hot-reload, -r    Enable hot-reloading on file changes
  --port, -p          Port for agent server (default: 8000)
  --mock-mcp          Use mock MCP servers
  --mock-redis        Use mock Redis
```

Examples:
```bash
kubani-dev run k8s-monitor --hot-reload
kubani-dev run news-monitor --mock-mcp --mock-redis
```

### test

Run tests for an agent:

```bash
kubani-dev test <agent> [options]

Options:
  --coverage          Generate coverage report
  --verbose, -v       Verbose output
  --filter, -k        Filter tests by name
```

### eval

Run evaluation suite:

```bash
kubani-dev eval <agent> [options]

Options:
  --layer             Evaluation layer (automated, llm, simulation, human)
  --output, -o        Output format (json, markdown)
```

Evaluation layers:
- **automated**: Fast, deterministic checks
- **llm**: LLM-as-judge evaluation
- **simulation**: Scenario-based testing
- **human**: Human review interface

### dashboard

Start the observability dashboard:

```bash
kubani-dev dashboard [options]

Options:
  --port, -p          Port for dashboard (default: 8080)
```

### trace

View execution traces:

```bash
kubani-dev trace <agent> [options]

Options:
  --last, -n          Number of recent traces (default: 10)
  --id                Specific trace ID
  --format, -f        Output format (table, json)
```

### metrics

View and export metrics:

```bash
kubani-dev metrics <agent> [options]

Options:
  --format, -f        Output format (json, prometheus)
  --period, -p        Time period (1h, 24h, 7d)
```

### build

Build agent container image:

```bash
kubani-dev build <agent> [options]

Options:
  --tag, -t           Image tag
  --push              Push to registry after build
```

### deploy

Deploy agent to cluster:

```bash
kubani-dev deploy <agent> [options]

Options:
  --rollback          Rollback to previous version
  --version, -v       Specific version to deploy
  --dry-run           Show what would be deployed
```

### monitor

Monitor agent deployment:

```bash
kubani-dev monitor <agent> [options]

Options:
  --follow, -f        Follow logs
  --metrics           Show metrics
```

### new

Create a new agent:

```bash
kubani-dev new <name> [options]

Options:
  --template, -t      Template (default, federated, minimal)
  --path, -p          Output path
```

### skills

Manage skills:

```bash
kubani-dev skills validate    # Validate all skills
kubani-dev skills list        # List available skills
kubani-dev skills show <name> # Show skill details
```

## Configuration

Configuration file: `.kubani-dev/config.yaml`

```yaml
# Agent configuration
agents:
  k8s-monitor:
    path: agents/k8s-monitor
    port: 8001
  news-monitor:
    path: agents/news-monitor
    port: 8002

# Service endpoints
services:
  llm: https://llm.almckay.io/v1
  embeddings: https://embeddings.almckay.io/v1
  qdrant: https://qdrant.almckay.io
  neo4j: bolt://neo4j.almckay.io:7687
  redis: redis://redis.almckay.io:6379
  temporal: temporal.almckay.io:7233

# Development settings
development:
  hot_reload: true
  mock_services: false
  log_level: INFO
```

## Workflow

Typical development workflow:

```bash
# 1. Initialize (one-time)
kubani-dev init

# 2. Develop with hot-reload
kubani-dev run k8s-monitor --hot-reload

# 3. Run tests
kubani-dev test k8s-monitor

# 4. Run evaluation
kubani-dev eval k8s-monitor

# 5. Build and deploy
kubani-dev build k8s-monitor
kubani-dev deploy k8s-monitor

# 6. Monitor
kubani-dev monitor k8s-monitor --follow
```
