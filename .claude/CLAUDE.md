# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Skill-First Development**: Before performing any task, check if a skill exists in `.claude/skills/`. Use `/skill-name` to invoke. After completing tasks, improve existing skills or create new ones for patterns you discover.

## Project Overview

Kubani is a Kubernetes-native AI agent platform for automated monitoring, remediation, and continuous learning. The platform leverages Temporal for workflow orchestration, MCP servers for tool integration, and a federated agent architecture for scalable operations.

## Architecture Overview

### Core Components

| Component | Purpose | Location |
|-----------|---------|----------|
| **Core Agents** | Shared agent framework with skills, memory, and MCP integration | `agents/core/` |
| **K8s Monitor** | Kubernetes monitoring and remediation agent | `agents/k8s-monitor/` |
| **News Monitor** | News aggregation and digest generation agent | `agents/news-monitor/` |
| **Learning Agent** | Continuous learning with Critic, Reflection, and Skill Synthesis | `agents/core/src/core_agents/learning/voyager/` |
| **Registry** | Metadata registry for agents, skills, and models | `registry/` |
| **UI** | Web interface for agent management and monitoring | `ui/` |

### MCP Servers

MCP (Model Context Protocol) servers provide standardized tool interfaces for agents.

| Server | Port | Purpose | Location |
|--------|------|---------|----------|
| **Discord MCP** | 8084 | Discord messaging and reactions | `tools/discord-mcp-server/` |
| **Kubernetes MCP** | 8080 | Kubernetes cluster operations | `tools/kubernetes-mcp-server/` |
| **Temporal MCP** | 8081 | Workflow management | `tools/temporal-mcp-server/` |
| **Qdrant MCP** | 8082 | Vector database operations | `tools/qdrant-mcp-server/` |
| **Memory MCP** | 8083 | Unified memory (Qdrant + Neo4j + Redis) | `tools/memory-mcp-server/` |

### Memory Systems

| System | Use Case |
|--------|----------|
| **Qdrant** | Vector embeddings for semantic search (skills, learnings) |
| **Neo4j** | Knowledge graph for relationships and reasoning |
| **Redis** | Cache, pub/sub, and event streaming |

## Build & Development Commands

All commands are managed via [Just](https://github.com/casey/just). Run `just` to see all available commands.

```bash
# Setup
./setup.sh                    # Bootstrap (installs mise, then runs just setup)
just setup                    # Full project setup

# Testing
just test                     # Run all tests
just test-agent k8s-monitor   # Test specific agent

# Code Quality
just lint                     # Ruff linting
just fmt                      # Ruff formatting
just check                    # ty type checking
just ci                       # Quick CI check before pushing

# Agent Development (kubani-dev CLI)
kubani-dev local-run --agent k8s-monitor --temporal cluster --output console
kubani-dev eval run --suite evaluations/k8s/pod_remediation.yaml
kubani-dev deploy --agent k8s-monitor --wait

# Builds
just build k8s-monitor        # Build agent Docker image
just push k8s-monitor v1.0.0  # Push to registry
```

## Local Development Workflow

### Configuration System

Configuration uses a hierarchical YAML system with pydantic-settings validation:

```
config.default.yaml    → Base defaults (committed)
config.production.yaml → Production overrides (committed)
config.local.yaml      → Local overrides (gitignored)
```

Environment variables override YAML with `KUBANI_` prefix and `__` for nesting:
```bash
export KUBANI_LLM__API_URL=http://localhost:8000/v1
export KUBANI_TEMPORAL__HOST=localhost:7233
```

### Running Agents Locally

```bash
# Run agent locally with cluster services
kubani-dev local-run --agent k8s-monitor --temporal cluster --output console

# Run with local Temporal (no cluster needed)
kubani-dev local-run --agent k8s-monitor --temporal local --output both

# Run with mock services for testing
kubani-dev local-run --agent k8s-monitor --mock-services
```

### External Services (via Tailscale)

| Service | URL | Port |
|---------|-----|------|
| vLLM (LLM) | https://llm.almckay.io/v1 | 443 |
| vLLM (Embeddings) | https://embeddings.almckay.io/v1 | 443 |
| Qdrant | https://qdrant.almckay.io | 443 |
| Neo4j | bolt://neo4j.almckay.io | 7687 |
| Redis | redis://redis.almckay.io | 6379 |
| Temporal (gRPC) | temporal.almckay.io | 7233 |
| Temporal (UI) | https://temporal.almckay.io | 443 |

## MCP Integration

Agents use the unified MCP client for tool access:

```python
from core_agents.mcp import get_mcp_client

client = get_mcp_client()

# Store a learning
await client.memory.store_learning(
    agent_id="k8s-monitor",
    learning_type="pattern",
    content="OOM kills indicate memory pressure",
    confidence=0.85,
)

# Query similar learnings
results = await client.memory.query_learnings(
    query="memory issues",
    min_confidence=0.7,
)

# Manage Temporal workflows
workflows = await client.temporal.list_workflows(status="running")
await client.temporal.signal_workflow(workflow_id, "pause")

# Discord notifications
await client.discord.send_embed(
    channel_id=config.discord.alerts_channel,
    title="Alert",
    description="Pod crash detected",
)
```

## Continuous Learning System

The learning system follows a Voyager-inspired architecture with three main components.

### Critic Agent
Evaluates agent execution quality and provides structured feedback. Runs hourly to analyze recent executions and identify improvement opportunities.

### Reflection Agent
Synthesizes learnings across agents, identifies patterns, and builds the knowledge graph. Runs daily to consolidate insights.

### Skill Synthesizer
Proposes new skills based on successful execution patterns. Requires Discord approval before deployment.

### Approval Workflow
New skills and modifications are posted to Discord for team review:
- ✅ Approve
- ❌ Reject  
- 🔄 Request revision

## Evaluation Framework

```bash
# Run evaluation suite
kubani-dev eval run --suite evaluations/k8s/pod_remediation.yaml

# Run specific evaluation layer
kubani-dev eval run --suite evaluations/k8s/pod_remediation.yaml --layer automated
kubani-dev eval run --suite evaluations/k8s/pod_remediation.yaml --layer llm_judge
```

Evaluation suites are defined in YAML:
```yaml
name: pod-remediation
description: Evaluate pod failure remediation
test_cases:
  - name: oom-kill-detection
    input:
      scenario: pod_oom_killed
      pod_name: test-pod
    expected:
      action_type: increase_memory
      success: true
```

## Deployment

### Deploy Command

```bash
# Deploy with verification
kubani-dev deploy --agent k8s-monitor --wait --timeout 300

# Deploy all agents
kubani-dev deploy --all --wait
```

### GitOps Structure

```
gitops/apps/ai-agents/
├── k8s-monitor/
├── news-monitor/
├── learning-agent/
├── discord-mcp-server/
├── temporal-mcp-server/
├── qdrant-mcp-server/
└── memory-mcp-server/
```

## Key Patterns

### Agent Structure

```
agents/{agent-name}/
├── src/{agent_name}/
│   ├── worker.py          # Temporal worker entry point
│   ├── federated/         # Sub-agents (explorer, executor, etc.)
│   ├── workflows/         # Temporal workflows
│   └── activities/        # Temporal activities
├── pyproject.toml
└── README.md
```

### AgentFactory Pattern

```python
from core_agents import AgentConfig, get_agent_factory

factory = get_agent_factory()
agent = factory.create_agent(AgentConfig(
    name="my-agent",
    description="Does something useful",
    system_prompt="You are a helpful assistant.",
    tools=[my_tool],
))
```

### Skill Definition

Skills are defined in Markdown with YAML frontmatter:

```markdown
---
name: investigate-pod-failure
version: "1.0.0"
category: k8s/diagnostic
triggers:
  - pod_crash_loop
  - oom_killed
---

# Investigate Pod Failure

## Purpose
Diagnose why a pod is failing...
```

## Claude Code Skills

Skills in `.claude/skills/` provide task-specific guidance:

### Development Workflow
- **local-development** - Run agents locally with cluster services
- **agent-evaluation** - Run and manage evaluation suites
- **continuous-learning** - Work with the learning system
- **mcp-servers** - Develop and manage MCP servers
- **deployment** - Deploy agents to cluster

### Agent Development
- **agents** - Manage and develop AI agents
- **new-agent** - Create new agent from template
- **kubani-dev** - Use kubani-dev CLI

### Cluster Operations
- **cluster-status** - Check cluster health
- **troubleshoot** - Diagnose and fix issues

## Directory Structure

```
kubani/
├── agents/                 # Agent implementations
│   ├── core/              # Shared framework
│   ├── k8s-monitor/       # Kubernetes monitoring
│   └── news-monitor/      # News aggregation
├── tools/                  # CLI tools and MCP servers
│   ├── kubani-dev/        # Development CLI
│   ├── discord-mcp-server/
│   ├── temporal-mcp-server/
│   ├── qdrant-mcp-server/
│   └── memory-mcp-server/
├── registry/              # Metadata registry service
├── ui/                    # Web interface
├── skills/                # Skill definitions
├── evaluations/           # Evaluation suites
├── gitops/                # Kubernetes manifests
├── config.default.yaml    # Default configuration
└── config.production.yaml # Production configuration
```

## Quick Reference

### Common Commands

| Command | Purpose |
|---------|---------|
| `just dev` | Start local development |
| `just test` | Run all tests |
| `just ci` | Pre-commit checks |
| `kubani-dev local-run` | Run agent locally |
| `kubani-dev eval run` | Run evaluations |
| `kubani-dev deploy` | Deploy to cluster |

### Ports

| Service | Port |
|---------|------|
| Temporal UI | 8080 |
| Temporal MCP | 8081 |
| Qdrant MCP | 8082 |
| Memory MCP | 8083 |
| Discord MCP | 8084 |
| Registry | 8000 |

## Important Files

- `justfile`: All development commands
- `config.default.yaml`: Default configuration
- `config.production.yaml`: Production configuration
- `.mise.toml`: Tool versions
- `pyproject.toml`: Dependencies and entry points
