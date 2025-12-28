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
```

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

## Claude Slash Commands

The following slash commands are available:

### Agent Management

- `/agents` - List all agents with versions and deployment status
- `/agents k8s-monitor` - Detailed info for specific agent

- `/build` - Build agent Docker images
  - `/build` - Build changed agents
  - `/build k8s-monitor` - Build specific agent
  - `/build all push` - Build and push all agents
  - `/build k8s-monitor push 0.2.0-custom` - Custom version

- `/deploy` - Deploy agents via GitOps
  - `/deploy k8s-monitor` - Show current version
  - `/deploy k8s-monitor 0.1.0-abc1234` - Deploy specific version
  - `/deploy news-monitor 0.1.0-def5678 --immediate` - Bypass Flux

- `/rollback` - Rollback to previous version
  - `/rollback k8s-monitor 0.1.0-abc1234` - Rollback to specific version
  - `/rollback k8s-monitor 1` - Rollback to previous deployment

- `/bump-version` - Increment agent version
  - `/bump-version k8s-monitor patch` - 0.1.0 → 0.1.1
  - `/bump-version k8s-monitor minor` - 0.1.0 → 0.2.0
  - `/bump-version news-monitor 0.2.0` - Set specific version

### Cluster Operations

- `/cluster-status` - Check cluster health
- `/validate` - Validate cluster configuration
- `/troubleshoot` - Diagnose cluster issues
- `/add-node` - Add new node to cluster
- `/bootstrap-node` - Bootstrap a new node
- `/new-agent` - Create new agent from template

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
- `gitops/apps/ai-agents/`: Kubernetes manifests for all agents
- `gitops/apps/vllm/model-config.yaml`: LLM model configuration
- `docs/CI-CD-PLAN.md`: Detailed CI/CD architecture documentation
