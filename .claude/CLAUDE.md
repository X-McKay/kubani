# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Skill-First Development**: Before performing any task, check if a skill exists in `.claude/skills/`. Use `/skill-name` to invoke. After completing tasks, improve existing skills or create new ones for patterns you discover.

---

## Design Principles

These principles guide all development decisions in Kubani:

### 1. Agentic-First Design

Lean on AI as much as possible. Agents should be autonomous, self-improving, and capable of handling complex tasks with minimal human intervention.

- Prefer AI-driven solutions over hard-coded logic
- Design for continuous learning and improvement
- Enable agents to propose their own improvements

### 2. Simplicity Over Complexity

Keep the codebase clean, simple, and easy to navigate.

- Single source of truth for configuration (`config_unified.py`)
- Consistent patterns across all components
- Remove duplication aggressively
- Use mixins and design patterns to reduce boilerplate

### 3. Easy Iteration and Evaluation

Development should be fast and feedback-rich.

- Local development with cluster services via `kubani-dev local-run`
- Hot-reload for rapid iteration
- Comprehensive evaluation framework with multiple layers
- Clear metrics and observability

### 4. Registry-Centric Architecture

Everything is registered, discoverable, and synchronized.

- Agents, skills, and models are registered in the central registry
- Automatic sync between Git and registry
- UI provides visibility into all registered components

### 5. MCP-First Tool Integration

All external tool access goes through MCP servers.

- Standardized tool interfaces via Model Context Protocol
- Consistent error handling and metrics
- Easy to add new capabilities

---

## Architecture Overview

### Core Components

| Component | Purpose | Location |
|-----------|---------|----------|
| **Core Agents** | Shared agent framework with skills, memory, and MCP integration | `agents/core/` |
| **K8s Monitor** | Kubernetes monitoring and remediation agent | `agents/k8s-monitor/` |
| **News Monitor** | News aggregation and digest generation agent | `agents/news-monitor/` |
| **Learning System** | Voyager-inspired continuous learning | `agents/core/src/core_agents/learning/voyager/` |
| **Registry** | Metadata registry for agents, skills, and models | `registry/` |
| **UI** | Web interface for agent management | `ui/` |

### MCP Servers

| Server | Port | Purpose | Location |
|--------|------|---------|----------|
| **Temporal MCP** | 8081 | Workflow management | `tools/temporal-mcp-server/` |
| **Qdrant MCP** | 8082 | Vector database operations | `tools/qdrant-mcp-server/` |
| **Memory MCP** | 8083 | Unified memory interface | `tools/memory-mcp-server/` |
| **Discord MCP** | 8084 | Discord messaging | `tools/discord-mcp-server/` |
| **Kubernetes MCP** | 8080 | Kubernetes operations | `tools/kubernetes-mcp-server/` |

### Memory Systems

| System | Use Case |
|--------|----------|
| **Qdrant** | Vector embeddings for semantic search |
| **Neo4j** | Knowledge graph for relationships |
| **Redis** | Cache, pub/sub, and event streaming |

---

## Configuration System

### Hierarchical Loading

Configuration loads in this order (later overrides earlier):

```
1. config.default.yaml    → Base defaults (committed)
2. config.{env}.yaml      → Environment-specific (committed)
3. config.local.yaml      → Local overrides (gitignored)
4. Environment variables  → KUBANI_ prefix with __ nesting
```

### Usage

```python
from core_agents.config_unified import get_config

config = get_config()
print(config.llm.api_url)
print(config.temporal.host)
print(config.mcp.temporal_url)
```

### Environment Variables

```bash
export KUBANI_ENVIRONMENT=development
export KUBANI_LLM__API_URL=http://localhost:8000/v1
export KUBANI_TEMPORAL__HOST=localhost:7233
```

---

## Development Workflow

### Local Development

```bash
# Install kubani-dev CLI
pip install -e tools/kubani-dev

# Initialize configuration
kubani-dev init

# Run agent locally with cluster services
kubani-dev local-run --agent k8s-monitor --temporal cluster --output console

# Run with hot-reload for rapid iteration
kubani-dev local-run --agent k8s-monitor --hot-reload

# Run with mock services (no cluster needed)
kubani-dev local-run --agent k8s-monitor --mock-services
```

### Testing

```bash
# Run all tests
just test

# Run agent-specific tests
kubani-dev test k8s-monitor

# Run with coverage
kubani-dev test k8s-monitor --coverage
```

### Evaluation

```bash
# Run evaluation suite
kubani-dev eval run --suite evaluations/k8s/pod_remediation.yaml

# Run specific layer
kubani-dev eval run --suite evaluations/k8s/pod_remediation.yaml --layer llm_judge
```

### Deployment

```bash
# Deploy with verification
kubani-dev deploy --agent k8s-monitor --wait

# Deploy all agents
kubani-dev deploy --all --wait
```

### Registry Sync

Sync skills, agents, and MCP configuration to the registry:

```bash
# Sync everything to registry
kubani-dev sync

# Preview what would be synced
kubani-dev sync --dry-run

# Sync specific resources
kubani-dev sync --skills --no-agents --no-mcp
```

**Auto-sync on push (opt-in):**

```bash
# Enable the pre-push hook to auto-sync when pushing to main
git config core.hooksPath .githooks
```

Once enabled, `kubani-dev sync` runs automatically when you push to main.

---

## MCP Integration

### Unified MCP Client

```python
from core_agents.mcp import get_mcp_client

client = get_mcp_client()

# Memory operations
await client.memory.store_learning(
    agent_id="k8s-monitor",
    learning_type="pattern",
    content="OOM kills indicate memory pressure",
    confidence=0.85,
)

# Temporal operations
workflows = await client.temporal.list_workflows(status="running")
await client.temporal.signal_workflow(workflow_id, "pause")

# Discord operations
await client.discord.send_embed(
    channel_id=config.discord.alerts_channel,
    title="Alert",
    description="Pod crash detected",
)

# Qdrant operations
results = await client.qdrant.search_vectors(
    collection="skills",
    query_vector=embedding,
    limit=5,
)
```

### Creating MCP Servers

Use the `BaseMCPServer` class from `mcp-common`:

```python
from mcp_common import BaseMCPServer, tool_handler

class MyMCPServer(BaseMCPServer):
    def __init__(self):
        super().__init__(
            name="my-mcp-server",
            version="1.0.0",
            description="My custom MCP server",
        )

    def register_tools(self) -> None:
        @self.server.tool()
        @tool_handler
        async def my_tool(param: str) -> dict:
            return {"result": param}

if __name__ == "__main__":
    server = MyMCPServer()
    server.run_sync()
```

---

## Continuous Learning System

### Components

1. **Critic Agent**: Evaluates execution quality, provides feedback
2. **Reflection Agent**: Synthesizes cross-agent knowledge
3. **Skill Synthesizer**: Proposes new skills from patterns

### Approval Workflow

New skills are posted to Discord for review:
- ✅ Approve and deploy
- ❌ Reject
- 🔄 Request modifications

### Usage

```python
from core_agents.learning import LearningManager, LearningConfig

manager = LearningManager(LearningConfig())
await manager.initialize()

# Log an execution for learning
await manager.log_execution(
    execution_id="exec-123",
    agent_name="k8s-monitor",
    task="Investigate pod failure",
    trace=[...],
    outcome={"resolved": True},
    success=True,
)

# Run learning cycle
await manager.run_learning_cycle()
```

---

## Agent Development

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

### Creating Agents

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

---

## Key Commands

| Command | Purpose |
|---------|---------|
| `just setup` | Initial project setup |
| `just test` | Run all tests |
| `just lint` | Ruff linting |
| `just ci` | Pre-commit checks |
| `kubani-dev init` | Initialize configuration |
| `kubani-dev local-run` | Run agent locally |
| `kubani-dev test` | Run agent tests |
| `kubani-dev eval` | Run evaluations |
| `kubani-dev deploy` | Deploy to cluster |
| `kubani-dev sync` | Sync skills, agents, MCP to registry |

---

## Claude Code Skills

Skills in `.claude/skills/` provide task-specific guidance:

### Core Workflows
- **local-development** - Complete local development guide
- **agent-evaluation** - Evaluation framework usage
- **continuous-learning** - Learning system operations
- **deployment** - Deployment automation

### Development
- **agents** - Agent management
- **new-agent** - Create new agents
- **mcp-servers** - MCP server development
- **mcp-builder** - Build MCP servers
- **skill-creator** - Create new skills

### Operations
- **cluster-status** - Check cluster health
- **troubleshoot** - Diagnose issues
- **rollback** - Rollback deployments
- **validate** - Validate configurations

---

## Directory Structure

```
kubani/
├── agents/                 # Agent implementations
│   ├── core/              # Shared framework
│   │   └── src/core_agents/
│   │       ├── config_unified.py  # Central configuration
│   │       ├── mcp/              # MCP client
│   │       ├── learning/         # Learning system
│   │       │   └── voyager/      # Critic, Reflection, Synthesizer
│   │       └── memory/           # Memory systems
│   ├── k8s-monitor/       # Kubernetes monitoring
│   └── news-monitor/      # News aggregation
├── tools/                  # CLI tools and MCP servers
│   ├── kubani-dev/        # Development CLI
│   ├── mcp-common/        # MCP base classes
│   ├── temporal-mcp-server/
│   ├── qdrant-mcp-server/
│   ├── memory-mcp-server/
│   └── discord-mcp-server/
├── registry/              # Metadata registry
├── ui/                    # Web interface
├── skills/                # Skill definitions
├── evaluations/           # Evaluation suites
├── gitops/                # Kubernetes manifests
├── config.default.yaml    # Default configuration
├── config.production.yaml # Production configuration
└── .claude/               # Claude Code configuration
    ├── CLAUDE.md          # This file
    └── skills/            # Claude Code skills
```

---

## External Services

| Service | URL | Purpose |
|---------|-----|---------|
| vLLM (LLM) | https://llm.almckay.io/v1 | Language model |
| vLLM (Embeddings) | https://embeddings.almckay.io/v1 | Embeddings |
| Qdrant | https://qdrant.almckay.io | Vector database |
| Neo4j | bolt://neo4j.almckay.io:7687 | Graph database |
| Redis | redis://redis.almckay.io:6379 | Cache |
| Temporal | temporal.almckay.io:7233 | Workflow engine |

---

## Best Practices

### Code Quality
- Run `just ci` before committing
- Write tests for new functionality
- Use type hints consistently
- Follow existing patterns in the codebase

### Agent Development
- Start with the agent template (`kubani-dev new`)
- Use the unified config system
- Integrate with MCP servers for tool access
- Add evaluation suites for new agents

### Skill Development
- Follow the SKILL.md format
- Include clear triggers and examples
- Test skills before deployment
- Update skills based on learning feedback

### Deployment
- Always use `kubani-dev deploy --wait`
- Monitor the deployment status
- Check logs after deployment
- Have a rollback plan ready

---

## Troubleshooting

### Common Issues

**Temporal Connection Failed**
```bash
# Check Temporal accessibility
curl -s https://temporal.almckay.io/health

# Or start local Temporal
temporal server start-dev
```

**MCP Server Not Responding**
```bash
# Check MCP server health
curl -s http://localhost:8081/health  # Temporal MCP
curl -s http://localhost:8082/health  # Qdrant MCP
```

**Configuration Not Loading**
```bash
# Verify config files exist
ls -la config.*.yaml

# Check environment
echo $KUBANI_ENVIRONMENT
```

---

## Getting Help

1. Check the skill for your task: `.claude/skills/`
2. Read the component README
3. Check the docs: `docs/`
4. Review test files for examples
5. Ask in Discord
