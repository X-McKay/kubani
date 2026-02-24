# Kubani Nexus: Architectural Decision Record

**Author:** Manus AI
**Date:** February 6, 2026

## Summary

This document records the key architectural decisions made for the Kubani Nexus project, including the context, options considered, and the rationale for each choice. These decisions were resolved collaboratively between the project owner and the design team.

---

## ADR-N01: Core Orchestration Model

**Status:** Accepted

**Context:** The Nexus agent must be "always-on" and resilient to pod restarts and cluster events. We needed to decide how to structure the core agent loop.

**Decision:** Implement the core agent as a **long-running Temporal workflow**. User interactions are sent as signals, and the workflow maintains all conversational state.

**Rationale:** Temporal provides out-of-the-box durability and observability. The agent's state persists across any failure, and the full conversation history is visible in the Temporal UI. While more complex than a simple service, the `kubani` project already has a strong Temporal foundation.

**Alternatives Rejected:** A standard Kubernetes service with Redis-backed state was considered but rejected because it sacrifices the durability of the core conversational loop.

---

## ADR-N02: Conversational Gateway

**Status:** Accepted

**Context:** We needed a service to bridge user-facing clients (Discord, Kubani UI) and the asynchronous Temporal workflow.

**Decision:** Build a **Unified Gateway Service in Python (FastAPI)** that manages WebSocket connections, integrates with the Discord MCP server, and uses Temporal signals and Redis Pub/Sub for communication.

**Rationale:** Keeps the entire agent backend in Python, simplifying dependencies. Provides clean separation of concerns between the UI layer and the agent's core logic.

**Alternatives Rejected:** Embedding the gateway logic directly into the Kubani UI's Rust backend was rejected due to increased complexity and language mixing.

---

## ADR-N03: Execution Sandbox

**Status:** Accepted

**Context:** All skill execution must be secure and isolated to prevent unintended side effects.

**Decision:** Use an **ephemeral Docker container per skill execution**. Each container is created, used, and destroyed for every single skill invocation.

**Rationale:** Provides the highest possible level of security and isolation. No state can leak between executions. Aligns directly with the "safer" core tenet of the project.

**Alternatives Rejected:** Reusable, long-lived sandbox containers were rejected due to the high risk of state leakage and cross-contamination between skill executions.

---

## ADR-N04: Skill Self-Modification

**Status:** Accepted

**Context:** The agent needs the ability to create and update its own skills, inspired by the "Pi" agent pattern. This must be done safely.

**Decision:** Implement an **Autonomous OCI-Native Approach**. Skills are packaged as versioned OCI artifacts, stored in the cluster's Harbor registry, and subjected to an automated, multi-stage validation pipeline (static analysis, sandbox execution, LLM peer review). A risk score determines whether the skill is auto-approved, requires human review, or is auto-rejected.

**Rationale:** Enables safe, scalable autonomy. The agent can create and deploy low-risk skills end-to-end without human intervention. All skills are versioned, immutable artifacts with a complete audit trail. This is more cloud-native and scalable than a filesystem-based GitOps flow.

**Alternatives Rejected:** A HITL-gated GitOps flow (requiring human approval for every change) was rejected because it creates a bottleneck and limits the agent's autonomy. Direct filesystem writes were rejected due to lack of auditability.

---

## ADR-N05: Unified Memory Interface

**Status:** Accepted

**Context:** The agent needs a robust memory system spanning multiple databases (Qdrant, Neo4j, Redis).

**Decision:** Enhance the existing **Memory MCP Server** to serve as the single, authoritative interface to all memory layers, using the `mem0` library as the core engine.

**Rationale:** Provides a clean, abstract API for the agent and its skills. Centralizes memory management complexity in one service. Aligns with the `kubani` project's MCP-first philosophy.

**Alternatives Rejected:** Direct database access from skills was rejected due to tight coupling and poor testability. Separate per-database MCP servers were rejected because they fragment the memory interface.

---

## ADR-N06: Mobile Interface

**Status:** Accepted

**Context:** The agent needs to be accessible from mobile devices.

**Decision:** Enhance the existing **React-based Kubani UI** and make it installable as a **Progressive Web App (PWA)**.

**Rationale:** Cost-effective and builds on the existing codebase. A well-designed PWA provides a native-like experience on mobile devices without the overhead of a separate native app.

**Alternatives Rejected:** A dedicated native mobile app (React Native) was rejected as unnecessary for the initial implementation. It can be revisited if specific native device capabilities are required in the future.
