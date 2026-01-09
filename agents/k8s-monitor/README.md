# k8s-monitor

Kubernetes cluster health monitoring agent with AI-powered autonomous remediation.

## Overview

k8s-monitor is an autonomous agent that:

1. **Monitors** cluster events in real-time via K8s Watch API
2. **Detects** issues (OOMKilled, CrashLoopBackOff, DNSConfigForming, etc.)
3. **Investigates** root causes using an LLM agent with MCP tools
4. **Remediates** issues automatically or escalates to Discord
5. **Learns** by proposing new skills from unmatched incidents

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        k8s-monitor Pod                           │
│  ┌─────────────────┐         ┌─────────────────────────────┐   │
│  │   mcp-server    │◄───────►│         worker              │   │
│  │   (sidecar)     │  HTTP   │    (main container)         │   │
│  │   :8080         │         │                             │   │
│  └────────┬────────┘         │  ┌─────────────────────┐    │   │
│           │                  │  │  Federated Agents   │    │   │
│           │ kubeconfig       │  │  Sentinel │ Healer  │    │   │
│           │                  │  │  Explorer │         │    │   │
│           │                  │  └─────────────────────┘    │   │
│           │                  │            │                │   │
│           │                  │            ▼                │   │
│           │                  │    Redis Streams            │   │
│           │                  │    (Event Bus)              │   │
└───────────┼──────────────────┴─────────────────────────────┴───┘
            │
            ▼
    ┌───────────────┐
    │  Kubernetes   │
    │     API       │
    └───────────────┘
```

### Federated Agents

Simple event-driven architecture for autonomous remediation:

| Agent | Role | Description |
|-------|------|-------------|
| **Sentinel** | Watches K8s events | Uses Watch API or MCP polling, publishes to event bus |
| **Healer** | Investigates and fixes | Agent with MCP tools investigates autonomously |
| **Explorer** | Learns from failures | Proposes new SKILL.md files from unmatched incidents |

### How the Healer Works

The Healer is truly agentic - given an issue, it uses an LLM agent with MCP tools to:

1. Gather evidence (events, logs, pod details)
2. Identify root cause
3. Take appropriate action or escalate

```python
# The agent has access to kubernetes-mcp-server tools:
# - events_list, pods_get, pods_log, pods_delete
# - resources_get, resources_scale
# etc.
```

It decides what to investigate and what actions to take - there's no hardcoded remediation logic.

## Local Development

### Quick Start

```bash
# 1. Set up development environment (from repo root)
just dev-setup

# 2. Verify connectivity
just dev-check

# 3. Run federated agents (fast iteration)
just dev-federated k8s-monitor

# 4. Or run full Temporal worker
just dev k8s-monitor
```

### Available Commands

| Command | Description |
|---------|-------------|
| `worker` | Run Temporal worker (default) |
| `federated-only` | Run federated agents without Temporal |
| `check` | Single health check (report only) |
| `schedule` | Start scheduled health checks |

## Project Structure

```
k8s-monitor/
├── src/k8s_monitor/
│   ├── worker.py              # Temporal worker entry point
│   ├── workflows.py           # Health check workflows
│   ├── activities.py          # Health check activities
│   ├── mcp_tools.py           # MCP HTTP client for K8s operations
│   ├── tools.py               # Discord notification tool
│   ├── models.py              # Pydantic models
│   └── federated/             # Autonomous agents
│       ├── sentinel.py        # Event watcher (~300 lines)
│       ├── healer.py          # Agentic remediation (~270 lines)
│       └── explorer.py        # Skill learner (~270 lines)
├── tests/
├── pyproject.toml
└── README.md
```

## Skills

Skills are markdown files (SKILL.md) that provide context for the LLM agent. They're located in `skills/k8s/`:

- `skills/k8s/diagnostic/investigate-pod-failure/SKILL.md`
- `skills/k8s/diagnostic/investigate-dns-config/SKILL.md`
- `skills/k8s/remediation/restart-crashloop/SKILL.md`

The Healer reads relevant skills for context but makes its own decisions using MCP tools.

## Deployment

```bash
# Build and deploy (from repo root)
just build k8s-monitor
just push k8s-monitor <version>

# Or use the deploy skill
/deploy k8s-monitor
```

Manifests are in `gitops/apps/ai-agents/k8s-monitor/`.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `KUBERNETES_MCP_SERVER_URL` | `http://localhost:8080` | MCP server |
| `TEMPORAL_HOST` | `temporal-frontend.temporal.svc:7233` | Temporal server |
| `VLLM_API_URL` | `http://llm-api.vllm.svc:8000/v1` | LLM endpoint |
| `REDIS_HOST` | `redis-master.cache.svc` | Event bus |
| `DISCORD_WEBHOOK_URL` | (required) | Discord notifications |
