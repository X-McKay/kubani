# k8s-monitor

Kubernetes cluster health monitoring agent with AI-powered remediation and learning capabilities.

## Overview

k8s-monitor is an autonomous agent that:

1. **Monitors** cluster health via Kubernetes API (real-time watch + periodic checks)
2. **Detects** issues (OOMKilled, CrashLoopBackOff, resource exhaustion, etc.)
3. **Investigates** root causes using LLM reasoning
4. **Remediates** issues automatically with verification
5. **Learns** from past remediations via graph + vector memory
6. **Notifies** via Discord webhooks

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

### MCP Server Sidecar

The agent uses [kubernetes-mcp-server](https://github.com/containers/kubernetes-mcp-server) as a sidecar for Kubernetes operations:

- **Native Go implementation** - No Node.js dependencies
- **HTTP/SSE transport** - Accessible via `http://localhost:8080/mcp`
- **Full K8s API support** - Pods, Deployments, Events, Helm, etc.
- **Consistent interface** - Same behavior locally and in-cluster

### Federated Agents

Voyager-inspired architecture for autonomous remediation:

| Agent | Role | Trigger |
|-------|------|---------|
| **Sentinel** | Watches K8s events in real-time | K8s Watch API |
| **Healer** | Executes remediation skills | Issue detection |
| **Explorer** | Learns new skills from failures | Failed remediation |

### Memory System

```
┌─────────────────────────────────────────────────────────────────┐
│                      Memory System                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                       │
│  │ Qdrant   │  │ Neo4j    │  │ Redis    │                       │
│  │ (vector) │  │ (graph)  │  │ (cache)  │                       │
│  └──────────┘  └──────────┘  └──────────┘                       │
│       │              │             │                             │
│       └──────────────┼─────────────┘                             │
│                      ▼                                           │
│           Remediation Learning                                   │
│  • Vector similarity: "What similar issues have I seen?"         │
│  • Graph queries: "What fixes worked for OOMKilled?"             │
│  • Pattern learning: Issue → Fix → Outcome chains                │
└─────────────────────────────────────────────────────────────────┘
```

## Local Development

### Prerequisites

- Connected to Tailscale network (for cluster access)
- DNS resolves `*.almckay.io` to cluster services
- Docker installed (for MCP server)

### Quick Start

```bash
# 1. Set up development environment (from repo root)
just dev-setup

# 2. Verify connectivity
just dev-check

# 3. Start MCP server (in background)
just mcp-server-bg

# 4. Run federated agents (fast iteration)
just dev-federated k8s-monitor

# 5. Or run full Temporal worker
just dev k8s-monitor

# 6. When done, stop MCP server
just mcp-server-stop
```

### MCP Server Commands

| Command | Description |
|---------|-------------|
| `just mcp-server` | Run MCP server interactively (foreground) |
| `just mcp-server-bg` | Run MCP server in background |
| `just mcp-server-stop` | Stop background MCP server |
| `just mcp-server-check` | Check MCP server health |

The MCP server provides the same Kubernetes tools locally that the sidecar provides in-cluster.

### Available Commands

| Command | Description |
|---------|-------------|
| `worker` | Run Temporal worker (default) |
| `federated-only` | Run federated agents without Temporal |
| `check` | Single health check (report only) |
| `check-remediation` | Single health check with auto-remediation |
| `schedule` | Start scheduled health checks |
| `schedule-remediation` | Start scheduled checks with remediation |
| `bootstrap-skills` | Initialize skill library in Qdrant |

### Testing Workflow

#### 1. Start MCP Server

```bash
just mcp-server-bg
# Verify it's running
just mcp-server-check
```

#### 2. Test Federated Agents (Fast Iteration)

```bash
just dev-federated k8s-monitor
```

This runs Sentinel, Healer, and Explorer without Temporal - ideal for testing event detection and remediation logic.

#### 3. Test Full Workflow (with Temporal)

```bash
just run-local k8s-monitor check
```

Expected output:
```
Connecting to Temporal at temporal.almckay.io:7233
Starting workflow: health-check-manual-...
Workflow completed: {'analysis_status': 'healthy', 'discord_posted': True, ...}
```

#### 4. Test Memory System

```bash
export $(grep -v '^#' .env | xargs)
uv run python -c "
from k8s_monitor.memory import (
    get_redis,
    get_neo4j_driver,
    get_memory,
    query_fixes_for_issue_type,
)

# Test connections
print('Redis:', 'OK' if get_redis() else 'FAIL')
print('Neo4j:', 'OK' if get_neo4j_driver() else 'FAIL')
print('mem0:', 'OK' if get_memory() else 'FAIL')

# Test graph queries
fixes = query_fixes_for_issue_type('OOMKilled')
print(f'Graph query: {len(fixes)} fixes found for OOMKilled')
"
```

#### 5. Test MCP Tools Directly

```bash
cd agents/k8s-monitor && uv run python -c "
import asyncio
from k8s_monitor.mcp_tools import get_mcp_client

async def test():
    client = get_mcp_client()
    tools = await client.list_tools()
    print(f'Available MCP tools: {len(tools)}')
    for t in tools[:5]:
        print(f'  - {t}')

asyncio.run(test())
"
```

### Environment Variables

The `.env` file (created by `just dev-setup`) contains:

| Variable | Description |
|----------|-------------|
| `KUBERNETES_MCP_SERVER_URL` | MCP server URL (default: `http://localhost:8080/sse`) |
| `TEMPORAL_HOST` | Temporal gRPC endpoint |
| `VLLM_API_URL` | LLM API for reasoning |
| `EMBEDDINGS_API_URL` | Embeddings API for memory |
| `QDRANT_HOST/PORT/API_KEY` | Vector database |
| `NEO4J_URL/USERNAME/PASSWORD` | Graph database |
| `REDIS_HOST/PORT/PASSWORD` | Cache and event bus |
| `KUBECONFIG` | Kubernetes access |

### Debugging Tips

#### View MCP Server Logs
```bash
docker logs -f kubernetes-mcp-server
```

#### View Temporal Workflows
```bash
temporal workflow list --query 'WorkflowType="ClusterHealthCheckWorkflow"'
```

#### Check Neo4j Graph
```bash
export $(grep -v '^#' .env | xargs)
uv run python -c "
from k8s_monitor.memory import get_neo4j_driver
driver = get_neo4j_driver()
with driver.session() as s:
    for r in s.run('CALL db.relationshipTypes()'):
        print(r['relationshipType'])
"
```

#### Inspect Qdrant Collections
```bash
curl -s https://qdrant.almckay.io/collections \
  -H "api-key: $(grep QDRANT_API_KEY .env | cut -d= -f2)" | jq .
```

## Components

### MCP Tools (`mcp_tools.py`)
HTTP client for kubernetes-mcp-server:
- Session management with MCP protocol handshake
- SSE response parsing
- Async and sync interfaces

### Legacy Tools (`tools.py`)
Direct Kubernetes Python client tools:
- `get_node_status()` - Node health and capacity
- `get_pod_status_summary()` - Pod phases by namespace
- `get_recent_events()` - Cluster warnings and errors
- `get_deployment_status()` - Deployment health
- `get_resource_usage()` - CPU/memory requests
- `get_pvc_status()` - Storage status

### Memory (`memory.py`)
Hybrid memory system with:
- `store_remediation_memory()` - Store completed remediations
- `search_similar_issues()` - Vector similarity search
- `get_remediation_context()` - Combined graph + vector context
- `query_fixes_for_issue_type()` - Neo4j graph queries
- `query_issue_causes()` - Root cause patterns
- `query_remediation_chains()` - Issue → Fix → Outcome chains

### Federated Agents (`federated/`)
- **Sentinel** (`sentinel.py`) - Watches K8s events, classifies using skill library
- **Healer** (`healer.py`) - Executes remediations with verification
- **Explorer** (`explorer.py`) - Learns new skills from failures

## Project Structure

```
k8s-monitor/
├── src/k8s_monitor/
│   ├── worker.py              # Temporal worker entry point
│   ├── workflows.py           # Health check workflows
│   ├── activities.py          # Health check activities
│   ├── mcp_tools.py           # MCP HTTP client for K8s operations
│   ├── tools.py               # Legacy direct K8s tools
│   ├── memory.py              # Memory system (Qdrant + Neo4j + Redis)
│   ├── memory_config.py       # K8S_GRAPH_PROMPT and config
│   ├── models.py              # Pydantic models
│   └── federated/             # Voyager-inspired agents
│       ├── sentinel.py        # Event watcher
│       ├── healer.py          # Remediation executor
│       └── explorer.py        # Skill learner
├── tests/
├── pyproject.toml
├── Earthfile
└── README.md
```

## Deployment

The agent is deployed to Kubernetes via GitOps:

```bash
# Build and push (from repo root)
just build k8s-monitor
just push k8s-monitor <version>

# Or use the deploy skill
/deploy k8s-monitor
```

Manifests are in `gitops/apps/ai-agents/k8s-monitor/`.

Key resources:
- **Deployment**: Runs worker + MCP server sidecar
- **Job**: Starts the scheduled workflow on deployment
- **RBAC**: ClusterRole with K8s access for MCP server
- **Secret**: Discord webhook URL (encrypted with SOPS)

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `KUBERNETES_MCP_SERVER_URL` | `http://localhost:8080/sse` | MCP server (sidecar) |
| `TEMPORAL_HOST` | `temporal-frontend.temporal.svc:7233` | Temporal server |
| `TEMPORAL_NAMESPACE` | `default` | Temporal namespace |
| `VLLM_API_URL` | `http://llm-api.vllm.svc:8000/v1` | vLLM endpoint |
| `VLLM_MODEL` | `nvidia/Qwen3-14B-FP4` | Model for reasoning |
| `EMBEDDINGS_API_URL` | `http://embeddings-api.vllm.svc:8000/v1` | Embeddings |
| `QDRANT_HOST` | `qdrant.database.svc` | Vector database |
| `NEO4J_URL` | `bolt://neo4j.database.svc:7687` | Graph database |
| `REDIS_HOST` | `redis-master.cache.svc` | Cache/event bus |
| `DISCORD_WEBHOOK_URL` | (required) | Discord notifications |
| `HEALTH_CHECK_INTERVAL_HOURS` | `1` | Check frequency |
