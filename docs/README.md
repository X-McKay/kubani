# Kubani Documentation

Welcome to the Kubani documentation! This documentation is organized to mirror the repository structure, making it easy to find information about the component you're working with.

## Quick Navigation

**I want to...**
- [Get started quickly](getting-started/quickstart.md) → 5-minute setup
- [Develop an agent](kubani/agents/development/creating-agents.md) → Agent development guide
- [Run agents locally](platform/cli/guides/local-development.md) → Local development workflow
- [Deploy to production](infrastructure/operations/production-checklist.md) → Production deployment
- [Use kubani CLI](platform/cli/reference/commands.md) → CLI reference
- [Understand the architecture](architecture/overview.md) → System design
- [Troubleshoot issues](troubleshooting/common-issues.md) → Common problems

## Documentation by Repository Component

### [kubani/](kubani/)
Core package containing framework, agents, syndicates, MCP servers, skills, and evaluations.

- [**Framework**](kubani/framework/) - Core framework (config, events, memory, MCP, learning)
- [**Agents**](kubani/agents/) - Reusable agent implementations
- [**Syndicates**](kubani/syndicates/) - Multi-agent orchestration (k8s-monitor, news-digest)
- [**MCP Servers**](kubani/mcp/) - Model Context Protocol infrastructure
- [**Skills**](kubani/skills/) - Skill definitions and development
- [**Evaluations**](kubani/evaluations/) - Evaluation framework

### [platform/](platform/)
Platform tooling for development, deployment, and management.

- [**CLI (kubani)**](platform/cli/) - Development CLI and workflows
- [**Registry**](platform/registry/) - Metadata registry service
- [**Skill Dev Tools**](platform/skill-dev-tools/) - Skill development framework
- [**UI**](platform/ui/) - Web interface

### [infrastructure/](infrastructure/)
Infrastructure as code, deployment, and operations.

- [**Cluster Management**](infrastructure/cluster/) - Node provisioning and cluster operations
- [**GitOps**](infrastructure/gitops/) - Flux-based deployments and validation
- [**Ansible**](infrastructure/ansible/) - Infrastructure automation
- [**Configuration**](infrastructure/configuration/) - DNS, GPU, secrets, storage, authentication
- [**Operations**](infrastructure/operations/) - Production operations and maintenance

### [architecture/](architecture/)
System-wide architecture and design documentation.

- [**Overview**](architecture/overview.md) - High-level system architecture
- [**Core Concepts**](architecture/core-concepts/) - Fundamental concepts and patterns
- [**Subsystems**](architecture/subsystems/) - Memory, events, workflows
- [**Deployment**](architecture/deployment/) - Deployment architecture

### [adr/](adr/)
Architecture Decision Records documenting key technical decisions.

- [ADR Index](adr/README.md) - All architecture decisions

### [planning/](planning/)
Project planning, roadmap, and backlog.

- [**Roadmap**](planning/roadmap/) - Current and future plans
- [**Backlog**](planning/backlog.md) - Feature backlog
- [**Research**](planning/research/) - Experimental work

## Documentation by Task

### Getting Started
- [Quickstart Guide](getting-started/quickstart.md)
- [Installation](getting-started/installation.md)
- [Core Concepts](getting-started/concepts.md) (coming soon)

### Development
- [Local Development Setup](platform/cli/guides/local-development.md)
- [Creating Agents](kubani/agents/development/creating-agents.md)
- [Testing](platform/cli/guides/testing.md)
- [Contributing](platform/cli/development/contributing.md)

### Operations
- [Production Checklist](infrastructure/operations/production-checklist.md)
- [GitOps Deployment](infrastructure/gitops/guides/deploying-services.md)
- [Operations Runbook](kubani/syndicates/reference/operations-runbook.md)
- [Maintenance](infrastructure/operations/maintenance/)

### Configuration
- [DNS & Traefik](infrastructure/configuration/dns.md)
- [GPU Setup](infrastructure/configuration/gpu.md)
- [Secrets Management](infrastructure/configuration/secrets.md)
- [Authentication](infrastructure/configuration/authentication.md)
- [Storage (NAS)](infrastructure/configuration/storage.md)

### Troubleshooting
- [Common Issues](troubleshooting/common-issues.md)
- [By Component](troubleshooting/by-component/)
- [Debugging Workflows](troubleshooting/debugging-workflows/)

## Reference Documentation

- [kubani CLI Commands](platform/cli/reference/commands.md)
- [Configuration Schema](kubani/framework/reference/config-schema.md) (coming soon)
- [Error Codes](platform/cli/reference/error-codes.md)
- [MCP Server APIs](kubani/mcp/reference/) (coming soon)

## Architecture & Design

- [System Overview](architecture/overview.md)
- [Federated Agents](architecture/core-concepts/federated-agents.md)
- [Learning System](architecture/core-concepts/learning-system.md)
- [MCP Integration](kubani/mcp/architecture/mcp-design.md)
- [Architecture Decisions](adr/)

## Archive

- [Historical Plans](archive/plans/) - Completed implementation plans
- [Deprecated Docs](archive/deprecated/) - Superseded documentation

---

## Navigation Tips

- Each major section has its own README with detailed navigation
- Use your IDE's file search to quickly find documentation
- Documentation mirrors the code structure for easy discovery
- Cross-references use relative links for portability

## Contributing to Docs

See [Contributing Guide](platform/cli/development/contributing.md) for how to improve documentation.
