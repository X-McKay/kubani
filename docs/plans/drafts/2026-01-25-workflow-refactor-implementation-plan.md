# Implementation Plan: Functional Workflow Architecture

**Date:** 2026-01-25
**Status:** Draft
**Author:** Manus AI

## 1. Overview

This document provides a detailed, task-level implementation plan for refactoring the `skill_auto` workflow and creating the new `agent_auto` workflow. The goal is to implement the functional, layered architecture proposed in the "Proposal for a Functional and Testable Automation Workflow Architecture" document.

This plan is broken down into four main phases, which are further divided into epics and individual tasks. Each task is designed to be a small, manageable unit of work.

## 2. High-Level Roadmap

- **Phase 1: Refactor `skill_auto` Workflow (Est. 1-2 Weeks):** Apply the new architecture to the existing skill automation workflow to create a robust, testable, and reusable component.
- **Phase 2: Build `agent_auto` Core Logic (Est. 2-3 Weeks):** Implement the foundational domain and service layers for the agent automation workflow, focusing on comprehensive testing.
- **Phase 3: Orchestrate `agent_auto` Workflow (Est. 2-3 Weeks):** Wire the core logic together using a Temporal workflow, including the integration of the `skill_auto` child workflow.
- **Phase 4: CLI Integration & Documentation (Est. 1 Week):** Connect the new workflow to the user-facing CLI and produce comprehensive documentation.

## 3. Detailed Implementation Plan

### Phase 1: Refactor `skill_auto` Workflow

**Goal:** Decouple business logic from the Temporal framework in the `skill_auto` workflow, making it highly testable and reusable.

| Epic | Task ID | Task Description | Files to Create/Modify |
| :--- | :--- | :--- | :--- |
| **Epic 1: Create `skill_auto` Domain Layer** | 1.1 | Create the directory structure: `kubani/workflows/skill_auto/domain/` and `kubani/workflows/skill_auto/services/`. | New directories |
| | 1.2 | Move all Pydantic models (`SkillAutoState`, `EvalMetrics`, etc.) from `models.py` to `domain/models.py`. | `domain/models.py` |
| | 1.3 | Create `domain/decisions.py` and implement pure functions `should_continue_iteration` and `determine_action` by extracting logic from `workflow.py`. | `domain/decisions.py` |
| | 1.4 | Create `domain/scoring.py` and move the `compute_score` function into it. | `domain/scoring.py` |
| | 1.5 | Create `tests/workflows/skill_auto/domain/` and write comprehensive unit tests for all functions in the new domain layer. These tests should require no mocks. | `tests/workflows/skill_auto/domain/*` |
| **Epic 2: Refactor `skill_auto` Service Layer** | 2.1 | Refactor `llm_service.py`, `eval_service.py`, `file_service.py` into the new `services/` directory. | `services/llm.py`, `services/evaluation.py`, etc. |
| | 2.2 | Modify all services to accept their dependencies (e.g., LLM clients, configuration objects) via their `__init__` methods (Dependency Injection). | `services/*.py` |
| | 2.3 | Remove all direct calls to `get_config()` from within the services. | `services/*.py` |
| | 2.4 | Create `tests/workflows/skill_auto/services/` and write integration tests for each service, using mocks for external dependencies (e.g., `MockLLMClient`, `InMemoryFileSystem`). | `tests/workflows/skill_auto/services/*` |
| **Epic 3: Update `skill_auto` Workflow & Activities** | 3.1 | Refactor all activities in `activities.py` to be thin wrappers that instantiate services (passing in config) and call the relevant service method. | `activities.py` |
| | 3.2 | Strip all business logic from `SkillAutoWorkflow` in `workflow.py`. Its only role should be to manage state and orchestrate activity calls. | `workflow.py` |
| | 3.3 | Update the existing Temporal workflow tests to reflect the new, simpler workflow structure. | `tests/workflows/skill_auto/test_workflow.py` |

### Phase 2: Build `agent_auto` Core Logic

**Goal:** Implement the testable, backend logic for the `agent_auto` workflow, based on the approved design.

| Epic | Task ID | Task Description | Files to Create/Modify |
| :--- | :--- | :--- | :--- |
| **Epic 4: Create `agent_auto` Domain Layer** | 4.1 | Create the directory structure: `kubani/workflows/agent_auto/domain/` and `kubani/workflows/agent_auto/services/`. | New directories |
| | 4.2 | Implement all Pydantic models (`AgentAutoInput`, `AgentAutoState`, `AgentTestCase`, `AgentEvaluationResult`, `ImprovementSuggestions`) in `domain/models.py`. | `domain/models.py` |
| | 4.3 | Create `domain/analysis.py` and implement the pure functions `analyze_agent_requirements` and `analyze_evaluation_failures`. | `domain/analysis.py` |
| | 4.4 | Create `domain/generation.py` for pure functions that generate file content, like `generate_agent_prompt` and `generate_agent_config`. | `domain/generation.py` |
| | 4.5 | Create `domain/metrics.py` for pure metric calculation functions like `calculate_skill_accuracy` and `calculate_skill_precision`. | `domain/metrics.py` |
| | 4.6 | Write comprehensive unit tests for the entire `agent_auto` domain layer in `tests/workflows/agent_auto/domain/`. | `tests/workflows/agent_auto/domain/*` |
| **Epic 5: Create `agent_auto` Service Layer** | 5.1 | Implement the `DraftingService` in `services/drafting.py`. This service will use the `LLMService` and `SkillRepository` to discover and identify missing skills. | `services/drafting.py` |
| | 5.2 | Implement the `EvaluationService` in `services/evaluation.py`. This service will run test cases and use the domain metric functions to calculate results. | `services/evaluation.py` |
| | 5.3 | Implement the `ImprovementService` in `services/improvement.py`. This service will use `domain/analysis.py` and apply changes to agent files. | `services/improvement.py` |
| | 5.4 | Implement the `PublishingService` in `services/publishing.py` to handle file promotion and GitOps manifest generation. | `services/publishing.py` |
| | 5.5 | Write integration tests for all `agent_auto` services in `tests/workflows/agent_auto/services/`, mocking any dependencies. | `tests/workflows/agent_auto/services/*` |

### Phase 3: Orchestrate `agent_auto` Workflow

**Goal:** Wire the `agent_auto` services together into a fully functional Temporal workflow.

| Epic | Task ID | Task Description | Files to Create/Modify |
| :--- | :--- | :--- | :--- |
| **Epic 6: Implement `agent_auto` Workflow & Activities** | 6.1 | Create `kubani/workflows/agent_auto/workflow.py` and implement the `AgentAutoWorkflow` class to orchestrate the Draft, Eval-Improve, and Publish phases. | `workflow.py` |
| | 6.2 | Create `kubani/workflows/agent_auto/activities.py` and implement thin wrapper activities for each service method (e.g., `draft_agent_activity`, `evaluate_agent_activity`). | `activities.py` |
| | 6.3 | In the `draft_agent_activity`, implement the logic to launch the `SkillAutoWorkflow` as a **child workflow** for each missing skill identified by the `DraftingService`. | `activities.py` |
| | 6.4 | Write high-level workflow tests for `AgentAutoWorkflow` using the Temporal test harness to ensure the overall orchestration is correct. | `tests/workflows/agent_auto/test_workflow.py` |

### Phase 4: CLI Integration & Documentation

**Goal:** Expose the new workflow to users via the CLI and document the new architecture.

| Epic | Task ID | Task Description | Files to Create/Modify |
| :--- | :--- | :--- | :--- |
| **Epic 7: Update CLI** | 7.1 | Modify the `kubani-dev agent draft` command to be the entry point that triggers the `AgentAutoWorkflow`. | `platform/cli/src/kubani_dev/commands/agent.py` |
| | 7.2 | Implement logic to pass CLI flags (e.g., `--non-interactive`, `--description`) as input to the workflow. | `platform/cli/src/kubani_dev/commands/agent.py` |
| | 7.3 | Update the `eval`, `improve`, and `promote` commands to interact with the running workflow via signals or by triggering new workflows as appropriate. | `platform/cli/src/kubani_dev/commands/agent.py` |
| **Epic 8: Update Documentation** | 8.1 | Create a new document in `docs/architecture/` explaining the functional workflow architecture, the separation of layers, and the testing strategy. | `docs/architecture/functional-workflow-design.md` |
| | 8.2 | Update the agent and skill development guides to reflect the new automated workflows. | `docs/kubani/agents/development/*`, `docs/kubani/skills/development/*` |
| | 8.3 | Add a tutorial or guide on how to use the new `kubani-dev agent draft` command. | `docs/platform/cli/guides/creating-agents-automatically.md` |
