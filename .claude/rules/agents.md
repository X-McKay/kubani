---
paths:
  - agents/**/*
---

# AI Agent Development Rules

When working with AI agents in the `agents/` directory:

## Development Tool

Use `kubani-dev` CLI for all agent development:

```bash
kubani-dev run <agent> --hot-reload   # Run locally
kubani-dev test <agent>               # Run tests
kubani-dev eval <agent>               # Run evaluation
kubani-dev build <agent>              # Build container
kubani-dev deploy <agent>             # Deploy to cluster
```

## Code Standards

- Use Python 3.11+ with full type annotations
- Use Pydantic models for all data structures
- Follow the patterns in `agents/core/` for shared functionality
- All agents depend on `core-agents` for base utilities
- Use `AgentFactory` for creating agents
- Use `GraphFactory` for hybrid workflows

## File Structure

Each agent must have:
```
agents/<agent-name>/
├── src/<agent_name>/
│   ├── __init__.py
│   ├── worker.py           # Temporal worker entry point
│   ├── workflows.py        # Temporal workflow definitions
│   ├── activities.py       # Temporal activity definitions
│   ├── models.py           # Pydantic data models
│   ├── agent_info.py       # A2A capability definitions
│   └── federated/          # Optional: federated agents
│       ├── sentinel.py     # Event classification
│       ├── healer.py       # Remediation
│       └── explorer.py     # Discovery
├── tests/
├── pyproject.toml          # Must include version
└── Earthfile               # Docker build definition
```

## Core Library Usage

Use the enhanced core library modules:

```python
# Agent creation
from kubani.framework import AgentConfig, get_agent_factory
factory = get_agent_factory()
agent = factory.create_agent(AgentConfig(...))

# Workflow graphs
from kubani.framework import GraphConfig
graph = factory.create_graph(GraphConfig(...))

# Context engineering
from kubani.framework.context import ContextManager
ctx = ContextManager(session_id="...")

# Continuous learning
from kubani.framework.learning import get_learning_manager
manager = get_learning_manager()

# Hierarchical memory
from kubani.framework.memory import HierarchicalMemorySystem
memory = HierarchicalMemorySystem(agent_id="...")

# Dynamic plugins
from kubani.framework.plugins import get_plugin_manager
plugins = get_plugin_manager()
```

## Versioning

- Version is in `pyproject.toml`: `version = "0.1.0"`
- Image tags use `{version}-{git-sha}` format
- Bump version before deploying changes: `just bump <agent> patch|minor|major`

## Building

- Use kubani-dev: `kubani-dev build <agent>`
- Or Earthly: `earthly ./agents/<agent>+docker`
- Core changes trigger rebuild of ALL agents

## Temporal Patterns

- Use descriptive workflow IDs: `<agent>-<action>-<timestamp>`
- Activities should be idempotent where possible
- Handle timeouts and retries appropriately
- Log important state transitions
- Use `AgentWorker` for standardized worker setup

## Testing

- Run tests: `kubani-dev test <agent>`
- Run evaluation: `kubani-dev eval <agent>`
- Include unit tests for activities
- Test workflow logic with mocks
- Use evaluation layers (automated, llm, simulation)

## Evaluation Framework

Run multi-layer evaluation:

```bash
kubani-dev eval <agent>                # Full evaluation
kubani-dev eval <agent> --layer llm    # LLM-as-judge only
```

Evaluation layers:
- **automated**: Fast, deterministic checks
- **llm**: LLM-as-judge evaluation
- **simulation**: Scenario-based testing
- **human**: Human review interface

## Observability

Use kubani-dev for observability:

```bash
kubani-dev dashboard        # Start dashboard
kubani-dev trace <agent>    # View traces
kubani-dev metrics <agent>  # View metrics
```
