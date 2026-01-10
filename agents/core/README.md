# Core Agents

Reusable core library for building AI agents in the Kubani ecosystem.

## Installation

```bash
pip install -e agents/core
```

## Modules

### Factory (`factory.py`)

Create agents and workflow graphs with standardized configuration:

```python
from core_agents import (
    AgentConfig,
    AgentFactory,
    GraphConfig,
    get_agent_factory,
)

# Get singleton factory
factory = get_agent_factory()

# Create an agent
agent = factory.create_agent(AgentConfig(
    name="my-agent",
    description="Does something useful",
    system_prompt="You are a helpful assistant.",
    tools=[my_tool],
))

# Create a workflow graph
graph = factory.create_graph(GraphConfig(
    name="my-workflow",
    nodes=[node1, node2, node3],
    edges=[("node1", "node2"), ("node2", "node3")],
))
```

### Context Engineering (`context/`)

Maintain agent focus and prevent repeated mistakes:

```python
from core_agents.context import ContextManager

ctx = ContextManager(session_id="my-session")

# Task tracking
ctx.add_todo("Analyze the issue")
ctx.complete_todo("Analyze the issue")

# Error prevention
ctx.record_error("API timeout", resolution="Retry with backoff")

# Context compression
compressed = ctx.compress_history(messages, max_tokens=4000)
```

### Workflows (`workflows/`)

Build hybrid workflow-agent graphs using Strands Graph:

```python
from core_agents.workflows import WorkflowBuilder

workflow = (
    WorkflowBuilder("incident-triage")
    .add_node("classify", classify_event)
    .add_node("analyze", analyze_with_agent)
    .add_node("remediate", execute_fix)
    .add_edge("classify", "analyze")
    .add_conditional_edge("analyze", route_by_severity)
    .build()
)

result = await workflow.execute({"event": event_data})
```

### Plugins (`plugins/`)

Dynamic MCP plugin architecture:

```python
from core_agents.plugins import get_plugin_manager, PluginConfig

manager = get_plugin_manager()

# Load an MCP plugin
await manager.load_plugin(PluginConfig(
    name="kubernetes-mcp",
    type="mcp",
    source="kubernetes-mcp-server",
    capabilities=["kubernetes", "pods"],
))

# Get all loaded plugins
plugins = manager.list_plugins()
```

### Learning (`learning/`)

Continuous learning framework:

```python
from core_agents.learning import get_learning_manager

manager = get_learning_manager()

# Record interaction
await manager.record_interaction(
    agent_id="my-agent",
    input_data={"query": "..."},
    output_data={"response": "..."},
    success=True,
)

# Get learned patterns
patterns = await manager.get_patterns("my-agent")

# Evolve skills based on patterns
await manager.evolve_skills("my-agent")
```

### Memory (`memory/`)

Hierarchical memory with automatic promotion and forgetting:

```python
from core_agents.memory import HierarchicalMemorySystem

memory = HierarchicalMemorySystem(agent_id="my-agent")

# Add memory (starts in working memory)
await memory.add("Important fact", metadata={"type": "fact"})

# Search across all tiers
results = await memory.search("query", limit=5)

# Get memory statistics
stats = memory.get_stats()
print(f"Working: {stats.working_count}, Episodic: {stats.episodic_count}")
```

### Skills MCP Server (`skills/mcp_server.py`)

Expose skills as discoverable MCP endpoints:

```python
from core_agents.skills import SkillsMCPServer

server = SkillsMCPServer(skills_dir="/path/to/skills")
await server.start(port=8080)
```

### Communication (`communication/`)

A2A protocol and agent registry:

```python
from core_agents.communication import (
    AgentInfo,
    AgentCapability,
    register_agent_on_startup,
    get_agent_registry,
)

# Register agent
await register_agent_on_startup(AgentInfo(
    id="my-agent",
    name="My Agent",
    capabilities=[AgentCapability(name="analyze", description="...")],
))

# Discover agents
registry = get_agent_registry()
agents = await registry.find_by_capability("analyze")
```

### Intelligence (`intelligence/`)

Built-in intelligence modules:

```python
from core_agents.intelligence import (
    get_anomaly_detector,
    get_capacity_planner,
    get_pattern_matcher,
)

# Anomaly detection
detector = get_anomaly_detector()
anomalies = detector.detect(metrics_data)

# Capacity planning
planner = get_capacity_planner()
forecast = planner.forecast(resource_data, horizon_days=7)

# Pattern matching
matcher = get_pattern_matcher()
patterns = matcher.find_patterns(event_history)
```

### Observability (`observability/`)

Metrics and tracing:

```python
from core_agents.observability import (
    get_metrics_collector,
    trace_agent_call,
)

# Collect metrics
metrics = get_metrics_collector()
metrics.record("agent.calls", 1, tags={"agent": "my-agent"})

# Trace calls
with trace_agent_call("my-agent", "analyze"):
    result = await agent.analyze(data)
```

## Agents

Pre-built agents for common use cases:

```python
from core_agents import DiscordAgent, MemoryAgent

# Discord notifications
discord = DiscordAgent()
discord("Send a health check summary to Discord")

# Memory-enabled agent
memory = MemoryAgent(
    tools=[my_search_tool],
    system_prompt="Custom prompt...",
)
memory("Search for similar past issues")
```

## Configuration

Environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_BASE_URL` | vLLM endpoint | `https://llm.almckay.io/v1` |
| `EMBEDDINGS_BASE_URL` | Embeddings endpoint | `https://embeddings.almckay.io/v1` |
| `QDRANT_URL` | Qdrant endpoint | `https://qdrant.almckay.io` |
| `NEO4J_URL` | Neo4j endpoint | `bolt://neo4j.almckay.io:7687` |
| `REDIS_URL` | Redis endpoint | `redis://redis.almckay.io:6379` |
| `TEMPORAL_HOST` | Temporal gRPC endpoint | `temporal.almckay.io:7233` |

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/

# Type check
ty check src/core_agents

# Format
ruff format src/ tests/
ruff check src/ tests/
```
