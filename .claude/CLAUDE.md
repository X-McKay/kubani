# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Kubani is a Kubernetes cluster automation system for heterogeneous hardware connected via Tailscale VPN. It provisions and manages multi-node K3s clusters across workstations, servers, and edge devices without complex networking setup.

## Build & Development Commands

All commands are managed via [Just](https://github.com/casey/just). Run `just` to see all available commands.

```bash
# Setup
./setup.sh                    # Bootstrap (installs mise, then runs just setup)
just setup                    # Full project setup (installs tools and dependencies)
just install                  # Install Python dependencies only

# Testing
just test                     # Run all tests (root + agents)
just test-root                # Root project tests only
just test-unit                # Unit tests only (tests/unit/)
just test-props               # Property-based tests only
just test-agents              # All agent tests via Earthly
just test-agent k8s-monitor   # Test specific agent

# Code Quality
just lint                     # Ruff linting
just fmt                      # Ruff formatting
just check                    # ty type checking
just check-all                # All checks (lint, format, type)
just ci                       # Quick CI check before pushing

# Agent Development (NEW - kubani-dev CLI)
kubani-dev run k8s-monitor    # Run agent locally with hot-reload
kubani-dev test k8s-monitor   # Run agent tests
kubani-dev eval k8s-monitor   # Run evaluation suite
kubani-dev dashboard          # Start observability dashboard
kubani-dev new my-agent       # Create new agent from template

# Agent Builds
just build k8s-monitor        # Build agent Docker image
just build-version k8s-monitor v1.0.0  # Build with version
just push k8s-monitor v1.0.0  # Push to registry

# Version Management
just agent-versions           # List all agent versions
just bump k8s-monitor patch   # Bump version (patch/minor/major)

# Cluster Operations
just provision                # Provision cluster via Ansible
just status                   # Check cluster status
just discover                 # Discover Tailscale nodes
just tui                      # Launch terminal UI

# Model Management
just model-current            # Show current model configuration
just model-list               # List models on cluster PVC
just model-download Qwen/Qwen3-14B  # Download model from HuggingFace
just model-switch Qwen/Qwen3-14B    # Update ConfigMaps with new model
just model-deploy             # Apply changes and restart deployments
```

## kubani-dev CLI (Agent Development Tool)

The `kubani-dev` CLI is the primary tool for agent development, testing, and evaluation.

### Installation

```bash
cd tools/kubani-dev
pip install -e .
```

### Commands

```bash
# Initialize configuration
kubani-dev init

# Run agent locally
kubani-dev run k8s-monitor              # Basic run
kubani-dev run k8s-monitor --hot-reload # With hot-reload
kubani-dev run k8s-monitor --mock-mcp   # With mock MCP servers

# Testing
kubani-dev test k8s-monitor             # Run all tests
kubani-dev test k8s-monitor --coverage  # With coverage report

# Evaluation
kubani-dev eval k8s-monitor             # Run evaluation suite
kubani-dev eval k8s-monitor --layer llm # LLM-as-judge evaluation only

# Observability
kubani-dev dashboard                    # Start observability dashboard
kubani-dev trace k8s-monitor            # View execution traces
kubani-dev metrics k8s-monitor          # View agent metrics

# Deployment
kubani-dev build k8s-monitor            # Build container image
kubani-dev deploy k8s-monitor           # Deploy to cluster
kubani-dev monitor k8s-monitor          # Monitor deployment

# Agent Creation
kubani-dev new my-agent                 # Create from default template
kubani-dev new my-agent --template federated  # Use federated template

# Skills Management
kubani-dev skills validate              # Validate all skills
kubani-dev skills list                  # List available skills
```

## Local Development

Agents can be developed locally using the external cluster services via Tailscale.

### Quick Start

```bash
# 1. Setup environment (one-time)
kubani-dev init                # Creates .kubani-dev/config.yaml

# 2. Verify connectivity
kubani-dev run k8s-monitor --mock-mcp  # Test with mocks first

# 3. Run agent locally with hot-reload
kubani-dev run k8s-monitor --hot-reload
```

### External Services

All services are accessible via Tailscale at `*.almckay.io`:

| Service | URL | Port |
|---------|-----|------|
| vLLM (LLM) | https://llm.almckay.io/v1 | 443 |
| vLLM (Embeddings) | https://embeddings.almckay.io/v1 | 443 |
| Qdrant | https://qdrant.almckay.io | 443 |
| Neo4j | bolt://neo4j.almckay.io | 7687 |
| Redis | redis://redis.almckay.io | 6379 |
| Temporal (gRPC) | temporal.almckay.io | 7233 |
| Temporal (UI) | https://temporal.almckay.io | 443 |

## Architecture

```
cluster_manager/              # Python CLI/TUI tools
├── cli.py                    # Typer CLI commands
├── tui/app.py               # Textual TUI application
├── models/                   # Pydantic data models
├── tailscale.py             # Tailscale network discovery
├── inventory.py             # Ansible inventory management
└── secrets.py               # SOPS secrets integration

agents/                       # AI-powered agents
├── core/                     # Reusable core agents library
│   └── src/core_agents/
│       ├── factory.py        # AgentFactory, GraphFactory, DI container
│       ├── context/          # Context engineering (todo, errors, compression)
│       ├── workflows/        # Strands Graph workflow support
│       ├── plugins/          # Dynamic MCP plugin architecture
│       ├── learning/         # Continuous learning framework
│       ├── skills/           # Skills MCP server
│       └── memory/           # Hierarchical memory with promotion/forgetting
├── k8s-monitor/              # Kubernetes cluster health monitoring
│   └── src/k8s_monitor/
│       └── federated/        # Sentinel, Healer, Explorer, Triage Graph
└── news-monitor/             # AI news monitoring with personalization
    └── src/news_monitor/
        ├── shared_agents.py  # Singleton agent pattern
        └── user_profiles.py  # Personalized digest generation

tools/                        # Development tools
├── kubani-dev/               # Agent development CLI
│   └── src/kubani_dev/
│       ├── cli.py            # Main CLI entry point
│       ├── runner.py         # Hot-reload agent runner
│       ├── evaluation.py     # Multi-layer evaluation framework
│       ├── testing.py        # Test runner
│       ├── dashboard.py      # Observability dashboard
│       ├── trace.py          # Execution trace viewer
│       ├── metrics.py        # Metrics collection
│       └── deploy.py         # Build and deploy commands
└── observability-dashboard/  # Real-time agent monitoring

ansible/                      # Infrastructure automation
├── playbooks/site.yml       # Main entry point
├── roles/                   # k3s_control_plane, k3s_worker, gpu_support, gitops
└── inventory/hosts.yml      # Cluster topology

gitops/                       # Kubernetes manifests (Flux CD syncs from here)
├── flux-system/             # Flux controllers
├── infrastructure/          # cert-manager, traefik, storage, networking
└── apps/                    # Application deployments

skills/                       # Agent skills library
├── TEMPLATE.md              # Enhanced skill specification format
├── general/                 # General-purpose skills
├── kubernetes/              # Kubernetes-specific skills
└── news/                    # News monitoring skills
```

## Key Patterns

### AgentFactory Pattern

For creating Strands agents with standardized configuration:

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

### GraphFactory Pattern (NEW)

For creating hybrid workflow-agent graphs:

```python
from core_agents import GraphConfig, get_agent_factory

factory = get_agent_factory()
graph = factory.create_graph(GraphConfig(
    name="triage-workflow",
    nodes=[classify_node, analyze_node, action_node],
    edges=[("classify", "analyze"), ("analyze", "action")],
))
```

### Context Engineering (NEW)

For maintaining agent focus and preventing repeated mistakes:

```python
from core_agents.context import ContextManager

ctx = ContextManager(session_id="my-session")
ctx.add_todo("Analyze the issue")
ctx.record_error("API timeout", resolution="Retry with backoff")
compressed = ctx.compress_history(messages, max_tokens=4000)
```

### Continuous Learning (NEW)

For agents that improve over time:

```python
from core_agents.learning import get_learning_manager

manager = get_learning_manager()
await manager.record_interaction(
    agent_id="k8s-healer",
    input_data={"issue": "CrashLoopBackOff"},
    output_data={"action": "restart_pod"},
    success=True,
)
patterns = await manager.get_patterns("k8s-healer")
```

### Dynamic Plugin Architecture (NEW)

For loading MCP servers dynamically:

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

## Testing Approach

- **Unit tests**: Standard pytest for individual components
- **Property tests**: Hypothesis-based tests for model invariants
- **Evaluation framework**: Multi-layer evaluation (automated, LLM-judge, simulation)
- Run `just ci` before committing - runs lint, test, and type checks

### Evaluation Layers (NEW)

```bash
# Run full evaluation
kubani-dev eval k8s-monitor

# Run specific layer
kubani-dev eval k8s-monitor --layer automated  # Fast, deterministic
kubani-dev eval k8s-monitor --layer llm        # LLM-as-judge
kubani-dev eval k8s-monitor --layer simulation # Scenario simulation
```

## Type System

- Python 3.11+ with ty (fast type checker from Astral)
- All functions should have type annotations
- Pydantic models provide runtime validation

## Claude Code Skills

Skills in `.claude/skills/` provide task-specific guidance:

### Agent Development
- **agents** - Manage and develop AI agents
- **new-agent** - Create new agent from template
- **kubani-dev** - Use kubani-dev CLI for development (NEW)

### Deployment
- **deploy** - Deploy agents to cluster
- **rollback** - Rollback agent deployments
- **bump-version** - Bump agent versions

### Cluster Operations
- **cluster-status** - Check cluster health and status
- **validate** - Validate cluster configuration
- **troubleshoot** - Diagnose and fix cluster issues
- **add-node** - Add new node to cluster
- **bootstrap-node** - Bootstrap a node without joining

### Development
- **skill-creator** - Create new Claude Code skills
- **mcp-builder** - Build MCP servers for custom tools

### Project Rules

Context-aware rules in `.claude/rules/` provide automatic guidance:

- **agents.md** - AI agent development patterns (applies to `agents/**/*`)
- **gitops.md** - GitOps deployment standards (applies to `gitops/**/*`)
- **kubernetes.md** - Kubernetes operation safety rules
- **commits.md** - Conventional commit message format

## Rollback Procedures

### Via GitOps (Recommended)

```bash
# Find previous version
git log --oneline -5 gitops/apps/ai-agents/k8s-monitor/deployment.yaml

# Restore previous manifest
git checkout abc1234 -- gitops/apps/ai-agents/k8s-monitor/deployment.yaml
git commit -m "chore(gitops): rollback k8s-monitor"
git push
# Flux auto-syncs the change
```

### Via kubani-dev

```bash
kubani-dev deploy k8s-monitor --rollback
```

## Model Management

Models are configured via ConfigMaps in both `vllm` and `ai-agents` namespaces:

```bash
# To install a new model:
just model-install Qwen/Qwen3-30B-A3B

# Or step by step:
just model-download Qwen/Qwen3-30B-A3B  # Downloads to ~/models/
just model-copy Qwen3-30B-A3B           # Copies to cluster PVC
just model-switch Qwen/Qwen3-30B-A3B    # Updates ConfigMaps
just model-deploy                        # Restarts deployments
```

## Important Files

- `justfile`: All development commands (run `just` to see them)
- `.mise.toml`: Tool versions (Python, kubectl, uv, just, earthly)
- `pyproject.toml`: Dependencies, entry points, tool configuration
- `ansible/inventory/hosts.yml`: Cluster node definitions (Tailscale IPs)
- `.sops.yaml`: Encryption rules for secrets
- `Earthfile`: Root build orchestration for all agents
- `.github/workflows/build.yml`: CI/CD pipeline with auto-discovery
- `tools/kubani-dev/`: Agent development CLI (NEW)
- `agents/core/src/core_agents/`: Core agent library with new modules (NEW)
- `skills/TEMPLATE.md`: Enhanced skill specification format (NEW)
- `manus_test.sh`: Cluster verification script (NEW)
