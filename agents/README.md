# AI Agents

This directory contains AI-powered agents that monitor and manage the Kubernetes cluster.

## Architecture

```
agents/
├── core/                  # Reusable core library
│   └── src/core_agents/
│       ├── agents/        # Generic agents (Discord, Memory)
│       ├── communication/ # A2A protocol, agent registry
│       ├── memory/        # mem0 config, hierarchical memory
│       ├── intelligence/  # Anomaly detection, capacity planning
│       ├── integrations/  # Discord, Temporal, MCP
│       └── observability/ # Metrics, hooks
│
├── k8s-monitor/           # Kubernetes health monitoring
│   └── src/k8s_monitor/
│       ├── agent_info.py    # Capability definitions
│       ├── memory_config.py # K8s-specific memory config
│       └── worker.py        # Temporal worker
│
└── news-monitor/          # AI news monitoring
    └── src/news_monitor/
        ├── agent_info.py    # Capability definitions
        ├── memory_config.py # News-specific memory config
        └── worker.py        # Temporal worker
```

## Core Library

The `core` package provides domain-agnostic utilities shared by all agents:

### Memory Configuration

```python
from core_agents import get_mem0_config, get_graph_mem0_config

# Basic vector memory (Qdrant)
config = get_mem0_config()

# Graph memory (Qdrant + Neo4j)
config = get_graph_mem0_config(
    graph_custom_prompt="Your domain-specific prompt..."
)
```

Each agent defines its own domain-specific prompts in `memory_config.py`.

### Agent Registration

Agents self-register at startup for A2A discovery:

```python
from core_agents.communication import register_agent_on_startup
from .agent_info import AGENT_INFO

async def run_worker():
    await register_agent_on_startup(AGENT_INFO)
    # ... start Temporal worker
```

### Intelligence Modules

```python
from core_agents.intelligence import (
    get_anomaly_detector,    # Statistical anomaly detection
    get_capacity_planner,    # Resource forecasting
    get_pattern_matcher,     # Recurring issue detection
)
```

## Creating a New Agent

Use the `/new-agent` Claude skill or follow these steps:

1. **Create directory structure**:
   ```bash
   mkdir -p agents/my-agent/{src/my_agent,tests}
   ```

2. **Create pyproject.toml** with `core-agents` dependency

3. **Create agent_info.py** with capabilities:
   ```python
   from core_agents.communication import AgentCapability, AgentInfo

   AGENT_INFO = AgentInfo(
       id="my-agent",
       name="My Agent",
       description="What it does",
       endpoint="my-agent.ai-agents.svc.cluster.local",
       capabilities=[
           AgentCapability(
               name="my-capability",
               description="What it does",
               tags=["my", "tags"],
           ),
       ],
   )
   ```

4. **Create memory_config.py** (if using mem0):
   ```python
   from core_agents import get_graph_mem0_config

   MY_GRAPH_PROMPT = """
   Extract entities and relationships for your domain...
   """

   def get_my_graph_mem0_config(**kwargs):
       return get_graph_mem0_config(
           graph_custom_prompt=MY_GRAPH_PROMPT,
           **kwargs,
       )
   ```

5. **Create worker.py** with self-registration

6. **Create GitOps manifests** in `gitops/apps/ai-agents/`

## Development Workflow

### Local Development

```bash
# Install dependencies
cd agents/my-agent
uv pip install -e ".[dev]"

# Run tests
pytest tests/

# Format code
ruff format src/ tests/
ruff check src/ tests/
```

### Building

```bash
# Build specific agent
earthly ./agents/my-agent+docker --VERSION=0.1.0-abc1234

# Build all agents
just build-agents
```

### Testing

```bash
# Run agent tests via Earthly
just test-agent my-agent

# Run all agent tests
just test-agents

# Run core tests
earthly ./agents/core+test
```

### Deployment

```bash
# Push and deploy via GitOps
docker push registry.almckay.io/my-agent:0.1.0-abc1234
# Then update gitops/apps/ai-agents/my-agent/deployment.yaml
# Flux will auto-sync
```

## Memory Architecture

All agents use Qdrant + Neo4j for memory:

- **Qdrant**: High-performance vector similarity search
- **Neo4j**: Graph-based entity/relationship tracking
- **mem0**: Unified memory API with fact extraction

Agents define domain-specific graph prompts for entity extraction:
- k8s-monitor: Pods, Issues, Fixes, Outcomes
- news-monitor: Companies, Products, Technologies, Topics

## Communication

Agents communicate via:

1. **Temporal workflows**: Reliable task orchestration
2. **A2A protocol**: Direct agent-to-agent requests
3. **Agent registry**: Capability-based service discovery

## Extension Points

The core library is designed for extensibility:

- **Memory**: Use `get_graph_mem0_config(graph_custom_prompt=...)` for domain-specific extraction
- **Registration**: Define capabilities in `agent_info.py` for discovery
- **Intelligence**: Use built-in anomaly/capacity/pattern modules or extend them
