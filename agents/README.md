# AI Agents

This directory contains AI-powered agents that monitor and manage the Kubernetes cluster.

## Architecture

```
agents/
├── core/                     # Reusable core library
│   └── src/core_agents/
│       ├── factory.py        # AgentFactory, GraphFactory, DI container
│       ├── context/          # Context engineering
│       │   ├── todo.py       # Task tracking and focus
│       │   ├── errors.py     # Error context preservation
│       │   ├── compression.py # Context optimization
│       │   └── manager.py    # Unified context management
│       ├── workflows/        # Strands Graph workflow support
│       │   ├── builder.py    # Workflow builder DSL
│       │   ├── graph.py      # Graph execution engine
│       │   └── executor.py   # Async workflow executor
│       ├── plugins/          # Dynamic MCP plugin architecture
│       │   ├── manager.py    # Plugin lifecycle management
│       │   ├── loader.py     # Plugin loaders (MCP, directory)
│       │   └── registry.py   # Plugin registry
│       ├── learning/         # Continuous learning framework
│       │   ├── manager.py    # Learning manager
│       │   ├── patterns.py   # Pattern matching
│       │   └── evolution.py  # Skill evolution
│       ├── skills/           # Skills as MCP servers
│       │   └── mcp_server.py # Skills MCP server
│       ├── memory/           # Hierarchical memory
│       │   └── hierarchical.py # Auto-promotion and forgetting
│       ├── communication/    # A2A protocol, agent registry
│       ├── intelligence/     # Anomaly detection, capacity planning
│       ├── integrations/     # Discord, Temporal, MCP
│       └── observability/    # Metrics, hooks
│
├── k8s-monitor/              # Kubernetes health monitoring
│   └── src/k8s_monitor/
│       └── federated/
│           ├── sentinel.py   # Event classification with LLM fallback
│           ├── healer.py     # Remediation agent
│           ├── explorer.py   # Proactive discovery
│           └── triage_graph.py # Hybrid workflow for incident triage
│
└── news-monitor/             # AI news monitoring
    └── src/news_monitor/
        ├── shared_agents.py  # Singleton agent pattern
        ├── user_profiles.py  # Personalized digest generation
        └── federated_activities.py # Temporal activities
```

## Core Library

The `core` package provides domain-agnostic utilities shared by all agents.

### AgentFactory

Create agents with standardized configuration:

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

### GraphFactory (Hybrid Workflows)

Create workflow graphs that combine deterministic steps with agent intelligence:

```python
from core_agents import GraphConfig, get_agent_factory

factory = get_agent_factory()
graph = factory.create_graph(GraphConfig(
    name="triage-workflow",
    nodes=[classify_node, analyze_node, action_node],
    edges=[("classify", "analyze"), ("analyze", "action")],
))
result = await graph.execute({"event": event_data})
```

### Context Engineering

Maintain agent focus and prevent repeated mistakes:

```python
from core_agents.context import ContextManager

ctx = ContextManager(session_id="my-session")

# Track tasks
ctx.add_todo("Analyze the issue")
ctx.complete_todo("Analyze the issue")

# Record errors to prevent repetition
ctx.record_error("API timeout", resolution="Retry with backoff")

# Compress context for long conversations
compressed = ctx.compress_history(messages, max_tokens=4000)
```

### Hierarchical Memory

Memory with automatic promotion and forgetting:

```python
from core_agents.memory import HierarchicalMemorySystem

memory = HierarchicalMemorySystem(agent_id="my-agent")

# Add memory (starts in working memory)
await memory.add("User prefers concise responses", metadata={"type": "preference"})

# Memory automatically promotes based on access patterns
# and decays unused memories over time

# Query with automatic tier selection
results = await memory.search("user preferences", limit=5)
```

### Continuous Learning

Agents that improve over time:

```python
from core_agents.learning import get_learning_manager

manager = get_learning_manager()

# Record successful interaction
await manager.record_interaction(
    agent_id="k8s-healer",
    input_data={"issue": "CrashLoopBackOff"},
    output_data={"action": "restart_pod"},
    success=True,
)

# Get learned patterns
patterns = await manager.get_patterns("k8s-healer")
```

### Dynamic Plugin Architecture

Load MCP servers dynamically:

```python
from core_agents.plugins import get_plugin_manager, PluginConfig

manager = get_plugin_manager()
await manager.load_plugin(PluginConfig(
    name="kubernetes-mcp",
    type="mcp",
    source="kubernetes-mcp-server",
    capabilities=["kubernetes", "pods"],
))
```

## Creating a New Agent

Use the `kubani-dev` CLI:

```bash
# Create from default template
kubani-dev new my-agent

# Create with federated template
kubani-dev new my-agent --template federated
```

Or manually:

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

4. **Create worker.py** with self-registration

5. **Create GitOps manifests** in `gitops/apps/ai-agents/`

## Development Workflow

### Using kubani-dev (Recommended)

```bash
# Initialize configuration
kubani-dev init

# Run agent locally with hot-reload
kubani-dev run my-agent --hot-reload

# Run tests
kubani-dev test my-agent

# Run evaluation
kubani-dev eval my-agent

# View traces
kubani-dev trace my-agent

# Start dashboard
kubani-dev dashboard
```

### Manual Development

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
kubani-dev build my-agent

# Or via just
just build my-agent
```

### Deployment

```bash
# Deploy via kubani-dev
kubani-dev deploy my-agent

# Or via GitOps
# Update gitops/apps/ai-agents/my-agent/deployment.yaml
# Flux will auto-sync
```

## Memory Architecture

All agents use Qdrant + Neo4j for memory with hierarchical tiers:

- **Working Memory**: Short-term, high-access items
- **Episodic Memory**: Session-based memories
- **Semantic Memory**: Long-term knowledge
- **Procedural Memory**: Learned patterns and skills

Features:
- **Automatic Promotion**: Frequently accessed memories promote to higher tiers
- **Decay and Forgetting**: Unused memories decay over time
- **Compression**: Old memories compress to save space

## Communication

Agents communicate via:

1. **Temporal workflows**: Reliable task orchestration
2. **A2A protocol**: Direct agent-to-agent requests
3. **Agent registry**: Capability-based service discovery
4. **MCP servers**: Tool and resource sharing

## Evaluation Framework

Multi-layer evaluation for agent quality:

```bash
# Run full evaluation
kubani-dev eval my-agent

# Run specific layer
kubani-dev eval my-agent --layer automated   # Fast, deterministic
kubani-dev eval my-agent --layer llm         # LLM-as-judge
kubani-dev eval my-agent --layer simulation  # Scenario simulation
```

## Extension Points

The core library is designed for extensibility:

- **Factory**: Register custom agent types with `factory.register_agent_type()`
- **Plugins**: Create custom plugin loaders
- **Learning**: Implement custom pattern matchers
- **Context**: Add custom context providers
- **Memory**: Implement custom memory tiers
