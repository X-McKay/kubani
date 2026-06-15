# Kubani

Kubani is the repository for the homelab cluster itself: provisioning, GitOps, and operations.

The repo is being intentionally narrowed to infrastructure concerns:

- `infrastructure/ansible/` for host bootstrap and K3s provisioning
- `infrastructure/gitops/` for Flux-managed manifests
- `infrastructure/scripts/` for infra helpers and validation
- `docs/infrastructure/` and `docs/troubleshooting/` for runbooks

Runtime code, MCP server implementations, and UI code are being split into separate workstreams so this repository stays focused on operating the cluster.

## Quick Start

```bash
mise install
uv sync --group dev
just ansible-deps
uv run pre-commit install

cp infrastructure/ansible/inventory/hosts.yml.example infrastructure/ansible/inventory/hosts.yml
cp infrastructure/ansible/inventory/group_vars/all.yml.example infrastructure/ansible/inventory/group_vars/all.yml

just inventory
just provision
just validate-local
```

## Common Commands

```bash
just inventory             # Validate Ansible inventory
just ansible-deps          # Install required Ansible collections locally
just ansible-ping          # Check Ansible reachability
just provision             # Provision or reconcile the cluster
just upgrade-k3s           # Explicitly allow a planned K3s version upgrade
just bootstrap-flux        # Explicitly install Flux controllers and root objects
just repair-flux-bootstrap # Explicitly repair Flux bootstrap drift
just upgrade-flux-cli      # Explicitly allow a Flux CLI version upgrade
just upgrade-flux-controllers # Explicitly allow Flux controller upgrades
just provision-host strix  # Provision one host
just validate-local        # Inventory, secrets, and kustomize builds
just validate-cluster      # Runtime cluster checks
just live-service-probes   # Read-only live service interaction probes
just flux-status           # Show Flux resources
just flux-reconcile        # Reconcile Flux stack, then validate Flux and live probes
just post-reconcile-validate # Validate Flux readiness and live service probes
just nodes                 # Show Kubernetes nodes
```

## Repository Layout

```text
.
├── infrastructure/
│   ├── ansible/
│   ├── gitops/
│   ├── scripts/
│   └── sops/
├── docs/
│   ├── infrastructure/
│   └── troubleshooting/
├── justfile
├── .mise.toml
└── pyproject.toml
```

## Scope

The target end state is an infra-only Kubani repository. See [docs/infrastructure/repository-scope.md](docs/infrastructure/repository-scope.md) for the repository boundary and follow-on split notes.
