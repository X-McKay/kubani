# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Kubani is a Kubernetes cluster automation system for heterogeneous hardware connected via Tailscale VPN. It provisions and manages multi-node K3s clusters across workstations, servers, and edge devices without complex networking setup.

## Build & Development Commands

```bash
# Setup
./setup.sh                    # Full environment setup (installs mise, uv, dependencies)
mise install                  # Install tools (Python 3.11, kubectl, helm, uv)
uv sync                       # Install Python dependencies

# Testing
make test                     # Run all tests with coverage
make test-unit                # Unit tests only (tests/unit/)
make test-props               # Property-based tests only (tests/properties/)
uv run pytest tests/unit/test_node.py -v  # Run single test file

# Code Quality
make lint                     # Ruff linting
make format                   # Ruff formatting
make type-check               # Mypy type checking
make check-all                # All checks (lint + type-check)

# CLI Tools
cluster-mgr provision         # Provision cluster via Ansible
cluster-mgr discover          # Discover Tailscale nodes
cluster-mgr status            # Check cluster status
cluster-tui                   # Launch terminal UI for monitoring
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
- Run `make test` before committing - coverage report generates automatically

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

agent_platform/               # Shared utilities for all agents
├── llm/                      # LLM client abstractions
├── temporal/                 # Temporal workflow helpers
└── discord.py                # Discord notification integration
```

### Building Agents

Use Earthly for reproducible builds:

```bash
# Build locally with auto-versioned tag
earthly ./agents/k8s-monitor+docker

# Build with specific version
earthly ./agents/k8s-monitor+docker --VERSION=v0.1.0

# Build and push to registry
earthly --push ./agents/k8s-monitor+push --VERSION=main-abc123

# Run tests
earthly ./agents/k8s-monitor+test

# Run linting
earthly ./agents/k8s-monitor+lint
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
# List available versions
docker images registry.almckay.io/k8s-monitor --format '{{.Tag}}'

# Deploy specific version
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

- `pyproject.toml`: Dependencies, entry points, tool configuration
- `ansible/inventory/hosts.yml`: Cluster node definitions (Tailscale IPs)
- `ansible/inventory/group_vars/all.yml`: Global cluster variables
- `.sops.yaml`: Encryption rules for secrets
- `agents/k8s-monitor/Earthfile`: Agent build definition
- `.github/workflows/build.yml`: CI/CD pipeline for agents
- `gitops/apps/ai-agents/k8s-monitor/`: Kubernetes manifests for agent