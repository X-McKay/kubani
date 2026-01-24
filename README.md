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
uv pip install -e platform/cli

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
├── kubani/                 # Core package
│   ├── framework/         # Core framework (config, events, memory, etc.)
│   ├── agents/            # Reusable agent implementations
│   ├── syndicates/        # Multi-agent orchestration systems
│   ├── mcp/               # MCP server infrastructure
│   ├── skills/            # Skill definitions (SKILL.md format)
│   └── evaluations/       # Evaluation suites
├── platform/              # Platform tooling
│   ├── cli/               # kubani-dev development CLI
│   ├── registry/          # Metadata registry service
│   ├── skill-dev-tools/   # Skill development framework
│   └── ui/                # Web interface
├── infrastructure/        # Infrastructure as code
│   ├── gitops/            # Kubernetes manifests (Flux)
│   ├── ansible/           # Node provisioning playbooks
│   └── scripts/           # Utility scripts
├── config/                # Configuration files (hierarchical YAML)
├── docs/                  # Documentation
└── tests/                 # Integration tests
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

## Skill Development

The Kubani skill development workflow is LLM-integrated and inspired by NVIDIA Voyager:

- **LLM-driven**: Skills are natural language SOPs executed by LLMs
- **Self-improving**: Critic agent and automatic retry enable continuous learning
- **High accuracy**: Achieved 98.3% average accuracy on complex skills

```bash
# Create a new skill
kubani-dev skill-llm draft "Find unused Kubernetes ConfigMaps"

# Evaluate it
kubani-dev skill-llm eval skills/development/your-skill --verbose

# Improve it
kubani-dev skill-llm improve skills/development/your-skill --goals accuracy

# Promote to production
kubani-dev skill-llm promote skills/development/your-skill --category core
```

See the [Skill Format Guide](kubani/skills/README.md) for skill structure and format details.

## Agent Development

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

Comprehensive documentation organized by component: [docs/](docs/)

**Getting Started:**
- [Quickstart Guide](docs/getting-started/quickstart.md) - 5-minute setup
- [Installation](docs/getting-started/installation.md) - Detailed install guide

**Development:**
- [Local Development](docs/platform/cli/guides/local-development.md) - Run agents locally
- [Creating Agents](docs/kubani/agents/development/creating-agents.md) - Build new agents
- [Testing](docs/platform/cli/guides/testing.md) - Testing workflows
- [Contributing](docs/platform/cli/development/contributing.md) - How to contribute

**Operations:**
- [Production Checklist](docs/infrastructure/operations/production-checklist.md) - Deploy to production
- [GitOps Deployment](docs/infrastructure/gitops/guides/deploying-services.md) - Flux-based deployment
- [Operations Runbook](docs/kubani/syndicates/reference/operations-runbook.md) - Syndicate operations

**Configuration:**
- [DNS & Traefik](docs/infrastructure/configuration/dns.md) - DNS and ingress
- [GPU Setup](docs/infrastructure/configuration/gpu.md) - NVIDIA GPU configuration
- [Secrets Management](docs/infrastructure/configuration/secrets.md) - SOPS encryption
- [Authentication](docs/infrastructure/configuration/authentication.md) - Authentik SSO

**Architecture:**
- [System Overview](docs/architecture/overview.md) - High-level architecture
- [Federated Agents](docs/architecture/core-concepts/federated-agents.md) - Multi-agent patterns
- [Learning System](docs/architecture/core-concepts/learning-system.md) - Continuous learning
- [MCP Integration](docs/kubani/mcp/architecture/mcp-design.md) - MCP server design
- [ADRs](docs/adr/) - Architecture decisions

**Reference:**
- [CLI Commands](docs/platform/cli/reference/commands.md) - kubani-dev reference
- [Error Codes](docs/platform/cli/reference/error-codes.md) - Error handling
- [Troubleshooting](docs/troubleshooting/common-issues.md) - Common issues

## Prerequisites

- [Mise](https://mise.jdx.dev/) - Installs Python, kubectl, uv, just, earthly
- [Tailscale](https://tailscale.com/) - Installed on all cluster nodes
- SSH access to cluster nodes with sudo privileges

## License

MIT
