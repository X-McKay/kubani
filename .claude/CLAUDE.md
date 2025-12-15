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

## Important Files

- `pyproject.toml`: Dependencies, entry points, tool configuration
- `ansible/inventory/hosts.yml`: Cluster node definitions (Tailscale IPs)
- `ansible/inventory/group_vars/all.yml`: Global cluster variables
- `.sops.yaml`: Encryption rules for secrets