# Kubani

Kubernetes cluster automation for heterogeneous hardware connected via Tailscale VPN. Provisions and manages multi-node K3s clusters across workstations, servers, and edge devices.

## Quick Start

```bash
# Install mise (runtime version manager)
curl https://mise.run | sh

# Clone and setup
git clone <repository-url>
cd kubani
./setup.sh

# Configure your cluster
cp ansible/inventory/hosts.yml.example ansible/inventory/hosts.yml
# Edit hosts.yml with your node Tailscale IPs

# Provision
just provision
```

## Commands

All commands are managed via [Just](https://github.com/casey/just). Run `just` to see available commands.

```bash
just                  # List all commands
just setup            # Initial setup
just provision        # Provision cluster
just status           # Check cluster status
just tui              # Launch monitoring TUI

# Development
just test             # Run tests
just lint             # Lint code
just check            # Type check
just ci               # Pre-commit checks

# Agent builds
just build k8s-monitor    # Build agent image
just push k8s-monitor     # Push to registry
```

## Project Structure

```
kubani/
├── ansible/              # Infrastructure automation (K3s provisioning)
├── gitops/               # Kubernetes manifests (Flux CD syncs from here)
├── agents/               # AI agents (k8s-monitor, core library)
├── cluster_manager/      # Python CLI and TUI tools
├── templates/            # Agent template for creating new agents
├── tests/                # Test suite
└── docs/                 # Documentation
```

## Documentation

See the [docs/](docs/) directory for detailed guides:

- [Development Guide](docs/DEVELOPMENT.md) - Development workflow and tooling
- [Architecture](docs/ARCHITECTURE.md) - System design and components
- [Agent Development](docs/AGENT_DEVELOPMENT.md) - Building AI agents
- [GPU Configuration](docs/GPU_CONFIGURATION.md) - NVIDIA GPU setup
- [DNS Configuration](docs/DNS_CONFIGURATION.md) - DNS and Traefik routing
- [Secrets Management](docs/SECRETS_MANAGEMENT.md) - SOPS encryption
- [Troubleshooting](docs/TROUBLESHOOTING.md) - Common issues and solutions

## Prerequisites

- [Mise](https://mise.jdx.dev/) - Installs Python, kubectl, uv, just, earthly
- [Tailscale](https://tailscale.com/) - Installed on all cluster nodes
- SSH access to cluster nodes with sudo privileges

## License

MIT
