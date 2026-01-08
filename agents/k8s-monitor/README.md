# k8s-monitor

Kubernetes cluster health monitoring agent with AI-powered remediation and learning capabilities.

## Overview

k8s-monitor is an autonomous agent that:

1. **Monitors** cluster health via Kubernetes API
2. **Detects** issues (OOMKilled, CrashLoopBackOff, resource exhaustion, etc.)
3. **Investigates** root causes using LLM reasoning
4. **Remediates** issues automatically with verification
5. **Learns** from past remediations via graph + vector memory
6. **Notifies** via Discord webhooks

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Temporal Workflows                          │
│  ┌─────────────────┐  ┌──────────────────────────────────────┐  │
│  │ Health Check    │  │ Health Check + Remediation           │  │
│  │ (report only)   │  │ (auto-fix with verification)         │  │
│  └─────────────────┘  └──────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Federated Agents                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                       │
│  │ Sentinel │  │ Healer   │  │ Explorer │                       │
│  │ (watch)  │  │ (fix)    │  │ (learn)  │                       │
│  └──────────┘  └──────────┘  └──────────┘                       │
│       │              │             │                             │
│       └──────────────┼─────────────┘                             │
│                      ▼                                           │
│              Redis Streams (Event Bus)                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
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

## Memory System

The memory system combines three approaches for learning:

### 1. Vector Similarity (Qdrant)
- Stores remediation records as embeddings
- Finds semantically similar past issues
- Returns relevance scores for ranking

### 2. Graph Relationships (Neo4j)
- Extracts entities: Issues, Fixes, Outcomes, Pods, Deployments
- Creates relationships: `FIXED_BY`, `CAUSED_BY`, `SIMILAR_TO`, `RESULTED_IN`
- Enables queries like:
  - "What fixes worked for OOMKilled issues?"
  - "What causes CrashLoopBackOff in namespace X?"
  - "What outcomes resulted from restart fixes?"

### 3. Fast Cache (Redis)
- Issue signature deduplication (O(1) lookup)
- Permanent fix caching
- Breaking alert deduplication

### How Learning Works

When the agent encounters a new issue:

```python
# 1. Get combined context from memory
context = get_remediation_context(issue)

# Returns both:
# - Graph-Based Learning: Explicit relationship queries
# - Vector Search: Semantically similar past issues
```

When a remediation completes:

```python
# 2. Store for future learning
store_remediation_memory(record, permanent_fix="Increased memory to 512Mi")

# This:
# - Stores vector embedding in Qdrant
# - Extracts entities/relationships to Neo4j via K8S_GRAPH_PROMPT
# - Caches signature in Redis for deduplication
```

## Local Development

### Prerequisites

- Connected to Tailscale network (for cluster access)
- DNS resolves `*.almckay.io` to cluster services

### Quick Start

```bash
# 1. Set up development environment (from repo root)
just dev-setup

# 2. Verify connectivity
just dev-check

# 3. Run commands locally
just run-local k8s-monitor <command>
```

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

#### 1. Test Skills Bootstrap (Qdrant connectivity)

```bash
just run-local k8s-monitor bootstrap-skills
```

Expected output:
```
HTTP Request: POST https://qdrant.almckay.io/collections/skills/points "HTTP/1.1 200 OK"
Skills bootstrapped successfully
```

#### 2. Test Health Check (Full workflow)

```bash
just run-local k8s-monitor check
```

Expected output:
```
Connecting to Temporal at temporal.almckay.io:7233
Starting workflow: health-check-manual-...
Workflow completed: {'analysis_status': 'healthy', 'discord_posted': True, ...}
```

#### 3. Test Memory System

```bash
# Interactive Python test (from repo root)
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

#### 4. Test with Remediation

```bash
just run-local k8s-monitor check-remediation
```

This will:
1. Run health check
2. If issues found, investigate root cause
3. Attempt remediation
4. Verify fix
5. Store in memory for learning

### Environment Variables

The `.env` file (created by `just dev-setup`) contains:

| Variable | Description |
|----------|-------------|
| `TEMPORAL_HOST` | Temporal gRPC endpoint |
| `VLLM_API_URL` | LLM API for reasoning |
| `EMBEDDINGS_API_URL` | Embeddings API for memory |
| `QDRANT_HOST/PORT/API_KEY` | Vector database |
| `NEO4J_URL/USERNAME/PASSWORD` | Graph database |
| `REDIS_HOST/PORT/PASSWORD` | Cache and event bus |
| `KUBECONFIG` | Kubernetes access |

### Debugging Tips

#### View Temporal workflows
```bash
temporal workflow list --query 'WorkflowType="ClusterHealthCheckWorkflow"'
```

#### Check Neo4j graph
```bash
export $(grep -v '^#' .env | xargs)
uv run python -c "
from k8s_monitor.memory import get_neo4j_driver
driver = get_neo4j_driver()
with driver.session() as s:
    # List relationship types
    for r in s.run('CALL db.relationshipTypes()'):
        print(r['relationshipType'])
"
```

#### Inspect Qdrant collections
```bash
curl -s https://qdrant.almckay.io/collections \
  -H "api-key: $(grep QDRANT_API_KEY .env | cut -d= -f2)" | jq .
```

#### View Redis keys
```bash
export $(grep -v '^#' .env | xargs)
redis-cli -h redis.almckay.io -a "$REDIS_PASSWORD" keys "k8s-monitor:*"
```

## Components

### Tools (`tools.py`)
Kubernetes inspection tools decorated with `@tool`:
- `get_node_status()` - Node health and capacity
- `get_pod_status_summary()` - Pod phases by namespace
- `get_recent_events()` - Cluster warnings and errors
- `get_deployment_status()` - Deployment health
- `get_resource_usage()` - CPU/memory requests
- `get_pvc_status()` - Storage status

### Agent (`agent.py`)
Strands agent configured with K8s tools and a system prompt for cluster analysis.

### Memory (`memory.py`)
Hybrid memory system with:
- `store_remediation_memory()` - Store completed remediations
- `search_similar_issues()` - Vector similarity search
- `get_remediation_context()` - Combined graph + vector context
- `query_fixes_for_issue_type()` - Neo4j graph queries
- `query_issue_causes()` - Root cause patterns
- `query_remediation_chains()` - Issue → Fix → Outcome chains

### Federated Agents (`federated/`)
Voyager-inspired architecture:
- **Sentinel** - Watches K8s events, classifies using skill library
- **Healer** - Executes remediations with verification
- **Explorer** - Learns new skills from failures

## Project Structure

```
k8s-monitor/
├── src/k8s_monitor/
│   ├── worker.py              # Temporal worker entry point
│   ├── workflows.py           # Health check workflows
│   ├── activities.py          # Health check activities
│   ├── remediation_workflows.py  # Remediation workflows
│   ├── remediation_activities.py # Remediation activities
│   ├── memory.py              # Memory system (Qdrant + Neo4j + Redis)
│   ├── memory_config.py       # K8S_GRAPH_PROMPT and config
│   ├── models.py              # Pydantic models
│   ├── tools.py               # Kubernetes tools
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
- **Deployment**: Runs the Temporal worker
- **Job**: Starts the scheduled workflow on deployment
- **RBAC**: ClusterRole with read-only K8s access
- **Secret**: Discord webhook URL (encrypted with SOPS)

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
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
