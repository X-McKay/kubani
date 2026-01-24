# Architecture Documentation

System-wide architecture and design documentation for Kubani.

## Quick Links

- [**System Overview**](overview.md) - High-level architecture
- [**Federated Agents**](core-concepts/federated-agents.md) - Multi-agent patterns
- [**Learning System**](core-concepts/learning-system.md) - Continuous learning architecture
- [**Architecture Decisions**](../adr/) - ADRs documenting key decisions

## Overview

- [**System Overview**](overview.md) - Complete system architecture
  - Component architecture
  - Network architecture
  - Data flow
  - Security model
  - Scalability and HA

## Core Concepts

Fundamental architectural patterns and concepts:

- [**Federated Agents**](core-concepts/federated-agents.md) - Distributed agent architecture
- [**Learning System**](core-concepts/learning-system.md) - Voyager-inspired continuous learning
- **Agents and Syndicates** (coming soon) - Agent patterns
- **Skills System** (coming soon) - Skill architecture

## Subsystems

Deep dives into major subsystems:

- **Memory Architecture** (coming soon) - Qdrant, Neo4j, Redis integration
- **Event Bus** (coming soon) - Redis Streams event system
- **Temporal Workflows** (coming soon) - Workflow orchestration

## Deployment

Deployment architecture and patterns:

- **Deployment Model** (coming soon) - How Kubani deploys
- **CI/CD Architecture** (../infrastructure/gitops/architecture/ci-cd.md) - Build and deploy pipeline
- **GitOps Model** (coming soon) - Flux-based GitOps

## Component-Specific Architecture

- [**Framework Architecture**](../kubani/framework/architecture/) - Core framework design
- [**MCP Integration**](../kubani/mcp/architecture/mcp-design.md) - MCP server architecture
- [**Syndicate Architecture**](../kubani/syndicates/architecture/) - Multi-agent systems

## Architecture Decisions

See [Architecture Decision Records (ADRs)](../adr/) for documented decisions:

- [ADR-001: Unified Configuration](../adr/001-unified-configuration.md)
- [ADR-002: MCP-First Integration](../adr/002-mcp-first-integration.md)
- [ADR-003: Voyager Learning System](../adr/003-voyager-learning-system.md)
- [ADR-004: Federated Agent Pattern](../adr/004-federated-agent-pattern.md)
- [ADR-005: Registry-Centric Architecture](../adr/005-registry-centric-architecture.md)

## Design Principles

Kubani follows these core design principles:

### 1. Agentic-First Design
Lean on AI as much as possible. Agents should be autonomous and self-improving.

### 2. Simplicity Over Complexity
Keep the codebase clean and easy to navigate. Single source of truth for configuration.

### 3. Easy Iteration and Evaluation
Fast development feedback loop with comprehensive evaluation framework.

### 4. Registry-Centric Architecture
Everything is registered, discoverable, and synchronized.

### 5. MCP-First Tool Integration
All external tool access goes through MCP servers for consistency.

## Related Documentation

- [Getting Started](../getting-started/) - Quick intro to concepts
- [Development](../platform/cli/guides/) - Building on the architecture
- [Operations](../infrastructure/operations/) - Running the system
- [Troubleshooting](../troubleshooting/) - Solving architectural issues

## Contributing

See [Contributing Guide](../platform/cli/development/contributing.md) for how to contribute to architecture documentation.
