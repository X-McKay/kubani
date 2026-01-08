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

# Agent Builds
just build k8s-monitor        # Build agent Docker image
just build-version k8s-monitor v1.0.0  # Build with version
just push k8s-monitor v1.0.0  # Push to registry
just dev k8s-monitor          # Local dev mode for agent
just new-agent my-agent       # Create new agent from template

# Version Management
just agent-versions           # List all agent versions
just bump k8s-monitor patch   # Bump version (patch/minor/major)
just bump-from-commits k8s-monitor    # Auto-detect version bump from commits
just bump-all-from-commits    # Bump all agents based on commits
just bump-preview k8s-monitor # Preview what would change

# Cluster Operations
just provision                # Provision cluster via Ansible
just status                   # Check cluster status
just discover                 # Discover Tailscale nodes
just tui                      # Launch terminal UI

# Model Management
just model-current            # Show current model configuration
just model-list               # List models on cluster PVC
just model-download Qwen/Qwen3-14B  # Download model from HuggingFace
just model-copy Qwen3-14B     # Copy downloaded model to cluster
just model-switch Qwen/Qwen3-14B    # Update ConfigMaps with new model
just model-deploy             # Apply changes and restart deployments
just model-install Qwen/Qwen3-14B   # Full workflow: download -> copy -> switch -> deploy

# Local Development
just dev-setup                # Create .env from template
just dev-check                # Verify connectivity to external services
just dev k8s-monitor          # Run agent with Temporal (full workflow support)
just dev-federated k8s-monitor # Run federated agents only (no Temporal needed)
```

## Local Development

Agents can be developed locally using the external cluster services via Tailscale.

### Quick Start

```bash
# 1. Setup environment (one-time)
just dev-setup                # Creates .env from .env.development template

# 2. Verify connectivity
just dev-check                # Tests all external service connections

# 3. Run agent locally
just dev k8s-monitor          # Full worker with Temporal
just dev-federated k8s-monitor # Federated agents only (faster iteration)
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

### Development Modes

- **`just dev <agent>`**: Runs full Temporal worker, supports workflows and activities
- **`just dev-federated <agent>`**: Runs only federated agents (Sentinel, Healer, Explorer), no Temporal required - faster iteration for agent logic

## Architecture

```
cluster_manager/              # Python CLI/TUI tools
├── cli.py                    # Typer CLI commands
├── tui/app.py               # Textual TUI application
├── models/                   # Pydantic data models (node.py, cluster.py)
├── tailscale.py             # Tailscale network discovery
├── inventory.py             # Ansible inventory management
└── secrets.py               # SOPS secrets integration

ansible/                      # Infrastructure automation
├── playbooks/site.yml       # Main entry point
├── roles/                   # k3s_control_plane, k3s_worker, gpu_support, gitops
└── inventory/hosts.yml      # Cluster topology (create from hosts.yml.example)

gitops/                       # Kubernetes manifests (Flux CD syncs from here)
├── flux-system/             # Flux controllers
├── infrastructure/          # cert-manager, traefik, storage, networking
└── apps/                    # Application deployments
```

## Key Patterns

- **Pydantic models** with strict validation for all configuration (cluster_manager/models/)
- **Property-based testing** with Hypothesis for correctness guarantees
- **Ansible-driven provisioning** via ansible-runner (programmatic execution)
- **GitOps deployment** through Flux CD - changes in gitops/ auto-deploy
- **SOPS with age encryption** for secrets stored in Git

## Testing Approach

- Unit tests: Standard pytest for individual components
- Property tests: Hypothesis-based tests in tests/properties/ for model invariants
- Run `just ci` before committing - runs lint, test, and type checks

## Type System

- Python 3.11+ with ty (fast type checker from Astral)
- All functions should have type annotations
- Pydantic models provide runtime validation

## AI Agents

The `agents/` directory contains AI-powered agents that monitor and manage the cluster:

```
agents/
├── core/                     # Reusable core agents library (pip package)
│   ├── src/core_agents/
│   │   ├── base.py           # create_model(), create_agent()
│   │   ├── discord_agent.py  # DiscordAgent for notifications
│   │   ├── memory_agent.py   # MemoryAgent for learning
│   │   ├── discord_utils.py  # Low-level Discord helpers
│   │   ├── mem0_utils.py     # mem0 + vLLM embeddings configuration
│   │   └── temporal.py       # Temporal client helpers
│   ├── Earthfile             # Build wheel + push to registry
│   └── pyproject.toml
│
├── k8s-monitor/              # Kubernetes cluster health monitoring agent
│   ├── src/k8s_monitor/
│   │   ├── worker.py         # Temporal worker entry point
│   │   ├── agent.py          # ReAct agent implementation
│   │   ├── tools.py          # Kubernetes tools (kubectl, logs, etc.)
│   │   └── memory.py         # mem0 memory system for learning
│   ├── tests/
│   ├── Earthfile
│   └── pyproject.toml        # version = "0.1.0"
│
└── news-monitor/             # AI news monitoring with trend analysis
    ├── src/news_monitor/
    │   ├── worker.py         # Temporal worker entry point
    │   ├── workflows.py      # News digest and breaking news workflows
    │   └── memory.py         # mem0 for article deduplication
    ├── tests/
    ├── Earthfile
    └── pyproject.toml        # version = "0.1.0"
```

### Adding a New Agent

1. Create the agent directory structure:
   ```bash
   just new-agent my-agent
   ```

2. Add a `pyproject.toml` with `version = "0.1.0"`

3. Create an `Earthfile` following the k8s-monitor template

4. Create GitOps manifests at `gitops/apps/ai-agents/my-agent/`

5. Push to main - CI will auto-discover and build the new agent

### AgentWorker Pattern

All agents use the `AgentWorker` class from `core_agents` for standardized Temporal worker setup:

```python
from core_agents.worker import (
    AgentWorker,
    AgentWorkerConfig,
    CommandConfig,
    ScheduledWorkflowConfig,
)

def create_worker() -> AgentWorker:
    config = AgentWorkerConfig(
        task_queue="my-agent",
        name="my-agent",
        description="My agent description",
        workflows=[MyWorkflow, ScheduledWorkflow],
        activities=[my_activity, another_activity],
        # Optional: federated agents that run alongside Temporal worker
        federated_agents_factory=start_federated_agents,
        # Optional: startup hooks (run after Temporal connect)
        startup_hooks=[cleanup_legacy_workflows],
        # Optional: scheduled workflows
        scheduled_workflows=[
            ScheduledWorkflowConfig(
                workflow_class=ScheduledWorkflow,
                workflow_id="my-agent-scheduled",
                default_interval_hours=1,
            ),
        ],
        # Optional: custom CLI commands
        custom_commands=[
            CommandConfig(
                name="check",
                description="Run single check",
                handler=handle_check,
            ),
        ],
    )
    return AgentWorker(config)

def main() -> None:
    worker = create_worker()
    worker.run()  # Parses sys.argv and runs appropriate command
```

The `AgentWorker` automatically provides:
- Standard logging setup
- Temporal client connection with env vars (TEMPORAL_HOST, TEMPORAL_NAMESPACE)
- `worker` command (default) - runs Temporal worker
- `federated-only` command - runs only federated agents
- `schedule-<name>` commands for scheduled workflows
- `--help` for CLI documentation

### AgentFactory Pattern

For creating Strands agents with standardized configuration, use the `AgentFactory`:

```python
from core_agents import (
    AgentConfig,
    AgentFactory,
    ModelConfig,
    SwarmConfig,
    get_agent_factory,
    quick_agent,
)

# Create a factory (or use singleton)
factory = get_agent_factory()

# Create a single agent with full configuration
config = AgentConfig(
    name="my-agent",
    description="Does something useful",
    system_prompt="You are a helpful assistant.",
    tools=[my_tool, another_tool],
    mcp_clients=[mcp_client],  # Optional MCP clients
    enable_observability=True,  # Default: True
)
agent = factory.create_agent(config)

# Or use quick_agent for simpler cases
agent = quick_agent(
    name="quick-agent",
    description="Quick helper",
    system_prompt="Be quick.",
    tools=[],
)

# Create a swarm of agents
swarm_config = SwarmConfig(
    agents=[agent1, agent2, agent3],
    entry_point=agent1,
    max_handoffs=10,
    execution_timeout=300.0,
)
swarm = factory.create_swarm(swarm_config)
```

The `AgentFactory` provides:
- Model caching (reuses OpenAI models with same config)
- Automatic observability hooks for metrics
- Consistent configuration across all agents
- Support for MCP client integration

For domain-specific factories, extend `AgentFactory`:

```python
class K8sAgentFactory(AgentFactory):
    """Kubernetes-specific agent factory."""

    def __init__(self):
        super().__init__(default_observability=True)
        self._mcp_client = None

    def get_mcp_client(self):
        if self._mcp_client is None:
            self._mcp_client = create_mcp_client()
        return self._mcp_client
```

## CI/CD Pipeline

### How It Works

The CI/CD pipeline automatically builds and deploys agents when code is merged to main:

```
Push/Merge to main → CI discovers agents → Builds changed agents → Updates GitOps manifests → Flux deploys to cluster
```

### Image Versioning

Image tags use the format `{pyproject.version}-{git-sha}`:

| Trigger | Tag Format | Example |
|---------|-----------|---------|
| Push to main | `{version}-{sha7}` | `0.1.0-abc1234` |
| Git tag `v*` | `{version}` | `0.1.0` |

Version comes from each agent's `pyproject.toml`:
```toml
[project]
version = "0.1.0"
```

### Smart Rebuilds

CI only rebuilds what changed:
- Change to `agents/k8s-monitor/` → rebuilds k8s-monitor only
- Change to `agents/core/` → rebuilds ALL agents (core is a dependency)
- Change to `agents/news-monitor/` → rebuilds news-monitor only

### Manual Triggers

Use GitHub Actions workflow_dispatch:
- Build specific agent: `agent: k8s-monitor`
- Build all agents: `agent: all`
- Force rebuild: `force: true`

## Claude Code Skills

This project uses Claude Code Skills for specialized operations. Skills are automatically triggered based on your request.

### Available Skills

Skills are located in `.claude/skills/` and provide domain-specific capabilities:

#### Agent Management
- **agents** - List all agents with versions and deployment status
- **build** - Build agent Docker images with Earthly
- **deploy** - Deploy agents via GitOps or kubectl
- **rollback** - Rollback to previous versions
- **bump-version** - Increment semantic versions
- **new-agent** - Create new agent from template

#### Cluster Operations
- **cluster-status** - Check cluster health and status
- **validate** - Validate cluster configuration
- **troubleshoot** - Diagnose and fix cluster issues
- **add-node** - Add new node to cluster
- **bootstrap-node** - Bootstrap a node without joining

#### Development
- **skill-creator** - Create new Claude Code skills with templates and best practices
- **mcp-builder** - Build MCP servers for custom tools, resources, and prompts

### Project Rules

Context-aware rules in `.claude/rules/` provide automatic guidance:

- **agents.md** - AI agent development patterns (applies to `agents/**/*`)
- **gitops.md** - GitOps deployment standards (applies to `gitops/**/*`)
- **kubernetes.md** - Kubernetes operation safety rules
- **commits.md** - Conventional commit message format

### How Skills Work

1. **Discovery**: Claude loads skill descriptions at startup
2. **Activation**: When your request matches a skill, Claude uses it
3. **Execution**: Full instructions load only when needed

Example: "Deploy k8s-monitor to 0.2.1" triggers the **deploy** skill automatically.

### Slash Commands (Legacy)

Slash commands in `.claude/commands/` are also available but skills are preferred:

- `/agents`, `/build`, `/deploy`, `/rollback`, `/bump-version`
- `/cluster-status`, `/validate`, `/troubleshoot`
- `/add-node`, `/bootstrap-node`, `/new-agent`

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

### Immediate (Bypasses Flux)

```bash
# Using kubectl (will be overwritten on next Flux sync)
KUBECONFIG=/home/al/.kube/config kubectl rollout undo deployment/k8s-monitor -n ai-agents

# Or set specific version
KUBECONFIG=/home/al/.kube/config kubectl set image deployment/k8s-monitor \
  --all -n ai-agents "*=registry.almckay.io/k8s-monitor:0.1.0-abc1234"
```

## Model Management

Models are configured via ConfigMaps in both `vllm` and `ai-agents` namespaces:

- `gitops/apps/vllm/model-config.yaml`: Primary model configuration
- `gitops/apps/ai-agents/k8s-monitor/model-config.yaml`: Duplicate for ai-agents namespace

The `just model-switch` command updates both ConfigMaps automatically. Models are stored on the cluster at the PVC path defined in the justfile (`model_pvc_path` variable).

### Workflow

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
- `ansible/inventory/group_vars/all.yml`: Global cluster variables
- `.sops.yaml`: Encryption rules for secrets
- `Earthfile`: Root build orchestration for all agents
- `.github/workflows/build.yml`: CI/CD pipeline with auto-discovery
- `.github/workflows/release.yml`: Automated release workflow
- `scripts/bump-version.py`: Semantic version bumping for agents
- `scripts/generate-changelog.py`: Changelog generation from conventional commits
- `gitops/apps/ai-agents/`: Kubernetes manifests for all agents
- `gitops/apps/vllm/model-config.yaml`: LLM model configuration
- `docs/CI-CD-PLAN.md`: Detailed CI/CD architecture documentation
