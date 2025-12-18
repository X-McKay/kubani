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
just check                    # Mypy type checking
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

- Python 3.11+ with strict mypy configuration
- All functions require type annotations (`disallow_untyped_defs = true`)
- Pydantic models provide runtime validation

## AI Agents

The `agents/` directory contains AI-powered agents that monitor and manage the cluster:

```
agents/
└── k8s-monitor/              # Kubernetes cluster health monitoring agent
    ├── src/k8s_monitor/      # Agent source code
    │   ├── worker.py         # Temporal worker entry point
    │   ├── agent.py          # ReAct agent implementation
    │   ├── tools.py          # Kubernetes tools (kubectl, logs, etc.)
    │   ├── memory.py         # mem0 memory system for learning
    │   └── remediation_*.py  # Automated remediation workflows
    ├── tests/                # Agent tests
    ├── Earthfile             # Earthly build definition
    └── pyproject.toml        # Agent dependencies

agents/core/                  # Reusable core agents library (pip package)
├── src/core_agents/
│   ├── base.py               # create_model(), create_agent()
│   ├── discord_agent.py      # DiscordAgent for notifications
│   ├── memory_agent.py       # MemoryAgent for learning
│   ├── discord_utils.py      # Low-level Discord helpers
│   └── temporal.py           # Temporal client helpers
├── Earthfile                 # Build wheel + push to registry
└── pyproject.toml
```

### Building Agents

Use Just commands (which wrap Earthly) for reproducible builds:

```bash
# Build agent Docker image
just build k8s-monitor

# Build with specific version
just build-version k8s-monitor v0.1.0

# Build and push to registry
just push k8s-monitor main-abc123

# Run tests for specific agent
just test-agent k8s-monitor

# Run tests for all agents
just test-agents

# Local development (syncs deps and runs worker)
just dev k8s-monitor

# Create new agent from template
just new-agent my-new-agent
```

Or use Earthly directly:

```bash
earthly ./agents/k8s-monitor+docker
earthly --push ./agents/k8s-monitor+push --VERSION=v0.1.0
```

## Image Versioning

### Tagging Convention

- **Branch builds**: `{branch}-{short-sha}` (e.g., `main-abc1234`)
- **Tagged releases**: Semantic version (e.g., `1.0.0`)
- **Latest**: Always points to most recent build

### CI/CD Workflow

1. Push to `main` triggers build with `main-{sha}` tag
2. CI creates PR to update gitops manifests with new tag
3. Tagged releases (`v*`) use version number directly
4. All builds also update `latest` tag

### Rollback

To rollback to a previous version:

```bash
# Deploy specific version using just
just deploy-monitor main-abc1234

# Or manually via kubectl
KUBECONFIG=/home/al/.kube/config kubectl set image deployment/k8s-monitor \
  worker=registry.almckay.io/k8s-monitor:main-abc1234 \
  start-scheduler=registry.almckay.io/k8s-monitor:main-abc1234 \
  -n ai-agents
```

## Claude Slash Commands

The following slash commands are available in Claude Code:

- `/build` - Build k8s-monitor Docker image
  - `/build` - Build locally with auto-versioned tag
  - `/build push` - Build and push to registry
  - `/build v0.1.0` - Build with specific version
  - `/build push v0.1.0` - Build and push with specific version

- `/deploy` - Deploy or rollback k8s-monitor agent
  - `/deploy` - Deploy latest version
  - `/deploy main-abc1234` - Deploy specific commit
  - `/deploy v0.1.0` - Deploy tagged release

## Important Files

- `justfile`: All development commands (run `just` to see them)
- `.mise.toml`: Tool versions (Python, kubectl, uv, just, earthly)
- `pyproject.toml`: Dependencies, entry points, tool configuration
- `ansible/inventory/hosts.yml`: Cluster node definitions (Tailscale IPs)
- `ansible/inventory/group_vars/all.yml`: Global cluster variables
- `.sops.yaml`: Encryption rules for secrets
- `agents/k8s-monitor/Earthfile`: Agent build definition
- `.github/workflows/build.yml`: CI/CD pipeline for agents
- `gitops/apps/ai-agents/k8s-monitor/`: Kubernetes manifests for agent