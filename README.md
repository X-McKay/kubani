# Kubani

AI-powered Kubernetes cluster automation and news monitoring platform with continuous learning capabilities.

## Overview

Kubani is a multi-agent system for intelligent infrastructure management. It provisions and manages multi-node K3s clusters across heterogeneous hardware connected via Tailscale VPN, and provides AI-powered monitoring, remediation, and news aggregation.

**Key Features:**

- **Federated Agent Architecture**: Specialized agents for different domains (K8s, News)
- **Voyager-Inspired Learning**: Continuous improvement through Critic, Reflection, and Skill Synthesis
- **MCP Integration**: Standardized tool access via Model Context Protocol servers
- **Unified Configuration**: Single configuration system across all components
- **Discord Integration**: Alerts, approvals, and feedback collection

## Quick Start

```bash
# Install mise (runtime version manager)
curl https://mise.run | sh

# Clone and setup
git clone https://github.com/X-McKay/kubani.git
cd kubani
./setup.sh

# Install development tools
pip install -e tools/kubani-dev

# Initialize configuration
kubani-dev init

# Run an agent locally
kubani-dev local-run --agent k8s-monitor --hot-reload
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
├── agents/                 # Agent implementations
│   ├── core/              # Shared agent framework
│   ├── k8s-monitor/       # Kubernetes monitoring agent
│   └── news-monitor/      # News aggregation agent
├── tools/                  # Development and MCP tools
│   ├── kubani-dev/        # Development CLI
│   ├── temporal-mcp-server/
│   ├── qdrant-mcp-server/
│   ├── memory-mcp-server/
│   └── discord-mcp-server/
├── registry/              # Agent and skill registry
├── ui/                    # Web interface
├── skills/                # Skill definitions (SKILL.md)
├── evaluations/           # Evaluation suites
├── ansible/               # Infrastructure automation (K3s provisioning)
├── gitops/                # Kubernetes manifests (Flux CD syncs from here)
├── cluster_manager/       # Python CLI and TUI tools
└── docs/                  # Documentation
```

## Agents

### K8s Monitor

Intelligent Kubernetes cluster monitoring with automated remediation:

- Pod failure investigation
- Resource optimization
- Anomaly detection
- Pattern-based healing

### News Monitor

AI-powered news aggregation and analysis:

- Multi-source collection
- Relevance filtering
- Executive brief generation
- Breaking news alerts

## Development

### Local Development

```bash
# Run with cluster services
kubani-dev local-run --agent k8s-monitor --temporal cluster --output console

# Run with hot-reload
kubani-dev local-run --agent k8s-monitor --hot-reload

# Run with mock services (no cluster needed)
kubani-dev local-run --agent k8s-monitor --mock-services
```

### Configuration

Configuration is loaded hierarchically:

1. `config.default.yaml` - Base defaults
2. `config.{environment}.yaml` - Environment-specific
3. `config.local.yaml` - Local overrides (gitignored)
4. Environment variables with `KUBANI_` prefix

### Testing

```bash
# Run tests
kubani-dev test k8s-monitor

# Run evaluations
kubani-dev eval k8s-monitor
```

### Deployment

```bash
# Deploy to cluster
kubani-dev deploy --agent k8s-monitor --wait
```

## MCP Servers

Kubani provides several MCP servers for agent tool access:

| Server | Purpose |
|--------|---------|
| Temporal MCP | Workflow management |
| Qdrant MCP | Vector operations |
| Memory MCP | Unified memory interface |
| Discord MCP | Discord integration |

## Continuous Learning

The Voyager-inspired learning system includes:

- **Critic Agent**: Evaluates execution quality
- **Reflection Agent**: Synthesizes cross-agent knowledge
- **Skill Synthesizer**: Generates new skills from patterns
- **Discord Approvals**: Human-in-the-loop for skill proposals

## Documentation

- [Development Guide](docs/development/DEVELOPMENT_GUIDE.md) - Development workflow and tooling
- [Learning System Architecture](docs/architecture/LEARNING_SYSTEM.md) - Continuous learning design
- [Setup Instructions](MANUS_SETUP.md) - Initial setup guide
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
