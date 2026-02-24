# Kubani Nexus: Master Implementation Plan

**Author:** Manus AI
**Date:** February 6, 2026

## 1. Introduction

This document serves as the master index and phased rollout strategy for the Kubani Nexus project. It ties together the six detailed component implementation plans and organizes them into a logical sequence of implementation phases.

The goal is to deliver Nexus iteratively, with each phase producing a testable, demonstrable increment of functionality. This allows us to validate our design decisions early and often, and to course-correct as needed.

## 2. Finalized Architectural Decisions

The following key architectural decisions were resolved collaboratively and form the foundation for all implementation plans.

| # | Decision Area | Choice | Rationale |
| :--- | :--- | :--- | :--- |
| 1 | Core Orchestration | **Temporal-Native Workflow** | Maximum durability and observability for the "always-on" requirement. |
| 2 | Conversational Gateway | **Unified Python (FastAPI) Service** | Clean separation of concerns; keeps the entire agent backend in Python. |
| 3 | Execution Sandbox | **Ephemeral Sandbox per Execution** | Highest level of security; aligns with the "safer" core tenet. |
| 4 | Skill Self-Modification | **Autonomous OCI-Native Approach** | Enables safe, scalable autonomy via automated validation and a Skill Registry. |
| 5 | Memory Interface | **Unified Memory MCP Server** | Single, abstract interface to all memory layers; simplifies agent logic. |
| 6 | Mobile Interface | **Enhanced Web UI (PWA)** | Cost-effective; builds on the existing React-based UI. |

## 3. Component Plan Index

| Plan | Component | Document |
| :--- | :--- | :--- |
| 01 | Temporal-Native Orchestrator | [`01-orchestrator/implementation_plan.md`](./01-orchestrator/implementation_plan.md) |
| 02 | Conversational Gateway | [`02-gateway/implementation_plan.md`](./02-gateway/implementation_plan.md) |
| 03 | Ephemeral Execution Sandbox | [`03-sandbox/implementation_plan.md`](./03-sandbox/implementation_plan.md) |
| 04 | OCI-Native Skill Management | [`04-skills/implementation_plan.md`](./04-skills/implementation_plan.md) |
| 05 | Unified Memory MCP Server | [`05-memory/implementation_plan.md`](./05-memory/implementation_plan.md) |
| 06 | Enhanced Web UI (PWA) | [`06-ui/implementation_plan.md`](./06-ui/implementation_plan.md) |

## 4. Phased Rollout Strategy

The implementation is organized into four phases, ordered by dependency and priority.

### Phase 1: Foundation (Estimated: 2-3 weeks)

The goal of this phase is to establish the core communication loop: a user sends a message, the agent receives it, processes it, and sends a response.

| Task | Plan | Description |
| :--- | :--- | :--- |
| 1.1 | 01 | Implement the `NexusSyndicateWorkflow` with signal/query support. |
| 1.2 | 02 | Implement the Conversational Gateway with WebSocket and Discord integration. |
| 1.3 | 05 | Enhance the Memory MCP Server to use `mem0` with Qdrant, Neo4j, and Redis. |
| 1.4 | 01 | Implement the `ProcessMessageWorkflow` with basic intent classification and LLM-based response generation. |

**Milestone:** A user can send a message via Discord or a simple test client and receive a coherent, context-aware response from the agent. The agent can remember information from previous turns.

### Phase 2: Secure Execution (Estimated: 2-3 weeks)

The goal of this phase is to give the agent the ability to *do* things, securely.

| Task | Plan | Description |
| :--- | :--- | :--- |
| 2.1 | 03 | Build the `nexus-sandbox-base` Docker image. |
| 2.2 | 03 | Implement the `execute_skill_activity` with full sandbox lifecycle management. |
| 2.3 | 01 | Implement the `planning_activity` to decompose user requests into skill execution plans. |
| 2.4 | 01 | Wire the planning and execution activities into the `ProcessMessageWorkflow`. |

**Milestone:** A user can ask the agent to perform a task (e.g., "Check the cluster health"), and the agent will plan the steps, execute the relevant skills in secure sandboxes, and return the results.

### Phase 3: Autonomous Skills (Estimated: 3-4 weeks)

The goal of this phase is to implement the full OCI-native skill management pipeline.

| Task | Plan | Description |
| :--- | :--- | :--- |
| 3.1 | 04 | Deploy the `Skill Registry` service (FastAPI + PostgreSQL). |
| 3.2 | 04 | Implement the `SkillValidationWorkflow` with all validation stages. |
| 3.3 | 04 | Implement the `Skill Synthesizer` agent. |
| 3.4 | 04 | Integrate the `execute_skill_activity` with the `Skill Registry` for dynamic skill discovery. |

**Milestone:** The agent can be asked to create a new skill. It will synthesize the skill, package it as an OCI artifact, validate it automatically, and register it for future use.

### Phase 4: UI & Polish (Estimated: 2-3 weeks)

The goal of this phase is to deliver the full user experience.

| Task | Plan | Description |
| :--- | :--- | :--- |
| 4.1 | 06 | Implement the Conversational Panel in the Kubani UI. |
| 4.2 | 06 | Implement the Status & Activity Panel. |
| 4.3 | 06 | Implement the HITL Approval Panel. |
| 4.4 | 06 | Enable PWA features (manifest, service worker). |
| 4.5 | All | Decommission the old `k8s-monitor` and `news-digest` syndicates. |

**Milestone:** The full Kubani Nexus system is operational, with a polished, mobile-friendly UI for conversation, monitoring, and administration.

## 5. Development and Testing Workflow

Throughout all phases, the following workflow will be adhered to:

1.  **Local-First Development:** All components will be developed and tested locally first, connecting to cluster services (Temporal, Qdrant, etc.) via the existing `kubani dev` command and configuration system.
2.  **Bottom-Up Testing:** Following the existing `kubani` testing hierarchy (MCP -> Skills -> Agents -> Syndicates), each layer will be validated before building the next.
3.  **End-to-End Validation:** Before any phase is considered complete, an end-to-end test using the cluster's deployed LLMs (vLLM) will be performed to ensure real-world functionality.
4.  **Code Cleanup:** A final code cleanup pass will be performed at the end of each phase, followed by a re-test to ensure no regressions were introduced.

## 6. Cluster Changes Summary

| Action | Service | Reason |
| :--- | :--- | :--- |
| **Add** | `nexus-gateway` | New Conversational Gateway service. |
| **Add** | `skill-registry` | New Skill Registry service (FastAPI + PostgreSQL). |
| **Add** | `nexus-syndicate-worker` | New Temporal worker for the Nexus workflows. |
| **Add** | `skill-validation-worker` | New Temporal worker for the Skill Validation workflows. |
| **Enhance** | `memory-mcp-server` | Upgrade to use `mem0` as the core engine. |
| **Enhance** | `kubani-ui` | Add conversational, monitoring, and HITL panels. |
| **Remove** | `k8s-monitor` | Functionality absorbed by Nexus. |
| **Remove** | `news-monitor` | Functionality absorbed by Nexus. |
