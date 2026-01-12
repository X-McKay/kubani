# ADR-005: Registry-Centric Architecture

## Status
Accepted

## Context

Kubani consists of multiple agents, skills, and models that need to be discovered, managed, and monitored. Without a central registry, there is no single place to understand what capabilities exist in the system, which agents are running, or what skills are available.

The challenge is compounded by the need to synchronize between Git (where skills are defined) and runtime (where agents consume skills). Manual synchronization is error-prone and creates drift between what is defined and what is deployed.

## Decision

We implemented a registry-centric architecture where all agents, skills, and models are registered in a central registry service. The registry serves as the single source of truth for metadata about system capabilities.

The registry provides several key functions. Agent registration occurs automatically when agents start, with agents reporting their capabilities, status, and health. Skill cataloging maintains a searchable index of all skills with their triggers, categories, and versions. Model registration tracks available LLM and embedding models with their capabilities and endpoints.

Synchronization between Git and the registry happens through the `skills-sync` CLI command, which runs during deployment. Skills defined in the `skills/` directory are parsed and registered, ensuring the registry reflects the current state of the codebase.

The UI queries the registry to provide visibility into the system. Users can browse available skills, see which agents are running, and monitor system health through the registry API.

Bidirectional sync enables changes made through the UI to be committed back to Git, maintaining Git as the authoritative source while allowing convenient UI-based management.

## Consequences

### Positive

The registry provides a single place to understand system capabilities. New team members can browse the registry to learn what agents and skills exist without reading through the entire codebase.

Automatic agent registration ensures the registry always reflects the current state of running agents. There is no manual step to keep the registry updated when agents are deployed or scaled.

Skill discovery becomes dynamic rather than static. Agents can query the registry to find skills matching specific triggers or categories, enabling flexible skill selection at runtime.

The UI can provide rich management capabilities by building on the registry API. Features like skill browsing, agent monitoring, and deployment management all use the registry as their data source.

### Negative

The registry is a critical dependency. If the registry is unavailable, agents cannot discover skills dynamically, and the UI cannot display system state. The registry must be highly available and resilient.

Synchronization between Git and the registry adds complexity. The sync process must handle conflicts, versioning, and partial failures gracefully. Drift between Git and the registry can cause confusion if not detected and resolved.

The registry adds another service to deploy and maintain. While the registry is relatively simple, it requires its own database, monitoring, and operational procedures.

### Neutral

The registry pattern is common in microservices architectures, so the concepts will be familiar to many developers. However, the specific implementation choices (API design, sync mechanisms) require documentation and training.

## Alternatives Considered

### File-Based Discovery

Reading skills directly from the filesystem would eliminate the need for a registry but would not support dynamic discovery or UI-based management. Each agent would need access to the skills directory, complicating deployment.

### Distributed Registry

A distributed registry using something like etcd or Consul would provide high availability but would add operational complexity. The current centralized approach is simpler and sufficient for the expected scale.

### No Registry

Operating without a registry would reduce complexity but would make it difficult to understand system capabilities, monitor agent health, or provide UI-based management. The benefits of the registry outweigh the operational cost.

### Kubernetes-Native Discovery

Using Kubernetes service discovery and ConfigMaps would leverage existing infrastructure but would tightly couple the system to Kubernetes. The registry provides a more portable abstraction that could work in other environments.
