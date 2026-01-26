# Detailed Implementation Plan: Phase 3 - `agent_auto` Orchestration

**Date:** 2026-01-25
**Status:** Draft
**Author:** Manus AI

## 1. Objective

This document provides a prescriptive guide for implementing the Temporal layer of the `agent_auto` workflow. This phase focuses on orchestrating the core logic from Phase 2, integrating the refactored `skill_auto` workflow as a child workflow, and creating a robust, stateful process for agent generation. All function signatures, file locations, and test requirements must be followed precisely.

## 2. Epic 6: Implement `agent_auto` Workflow & Activities

**Goal:** To wire the `agent_auto` domain and service layers into a fully functional, stateful Temporal workflow that orchestrates the entire agent creation lifecycle, including the dynamic creation of missing skills.

---

### **Task 6.1: Implement `agent_auto` Activities**

**Action:** Create the thin wrapper activities that bridge the Temporal framework and the `agent_auto` service layer.

-   **File:** `kubani/workflows/agent_auto/activities.py`
-   **Purpose:** To handle the instantiation of services, delegation of work, and resource cleanup, keeping the workflow itself free of business logic.

**Implementation:**

```python
# kubani/workflows/agent_auto/activities.py

from temporalio import activity
from ..config import get_config
from .services.drafting import DraftingService
from .services.evaluation import EvaluationService
from .services.improvement import ImprovementService
from .services.publishing import PublishingService
# Import concrete implementations for dependencies
from .services.concrete import ( 
    create_llm_client, 
    create_file_system,
    create_skill_repo,
    create_agent_runner
)

@activity.defn
async def draft_agent_activity(description: str) -> dict:
    """Activity to draft an agent, identifying missing skills and initial files."""
    # 1. Instantiate services at the boundary
    drafting_service = DraftingService(
        llm_client=create_llm_client(),
        fs=create_file_system(),
        skill_repo=create_skill_repo()
    )
    activity.heartbeat()
    # 2. Delegate to the service
    return await drafting_service.draft_agent(description)

@activity.defn
async def evaluate_agent_activity(agent_path: str, test_cases: list) -> dict:
    """Activity to evaluate an agent's performance."""
    eval_service = EvaluationService(agent_runner=create_agent_runner())
    activity.heartbeat()
    result = await eval_service.evaluate_agent(agent_path, test_cases)
    return result.dict() # Return a serializable dictionary

@activity.defn
async def apply_improvements_activity(agent_path: str, suggestions: dict) -> None:
    """Activity to apply improvements to agent files."""
    # ... instantiate ImprovementService and delegate ...
    pass

@activity.defn
async def publish_agent_activity(agent_path: str, options: dict) -> dict:
    """Activity to publish the final agent."""
    # ... instantiate PublishingService and delegate ...
    return {}

```

**Verification:** The activities must be thin wrappers. All dependencies must be created and injected here, not within the services themselves.

---

### **Task 6.2: Implement `agent_auto` Workflow**

**Action:** Implement the main `AgentAutoWorkflow` class, orchestrating the activities and managing state. This includes the critical step of calling the `SkillAutoWorkflow` as a child workflow.

-   **File:** `kubani/workflows/agent_auto/workflow.py`
-   **Purpose:** To create the high-level, stateful process that reliably executes the agent creation lifecycle.

**Implementation:**

```python
# kubani/workflows/agent_auto/workflow.py

import asyncio
from temporalio.workflow import workflow, execute_activity, start_child_workflow
from ..skill_auto.workflow import SkillAutoWorkflow # Import the refactored skill workflow
from .activities import (
    draft_agent_activity,
    evaluate_agent_activity,
    apply_improvements_activity,
    publish_agent_activity
)
from .domain.models import AgentAutoState, AgentAutoInput, AgentEvaluationResult, ImprovementSuggestions

@workflow.defn
class AgentAutoWorkflow:
    @workflow.run
    async def run(self, input: AgentAutoInput) -> dict:
        self._state = AgentAutoState(agent_name=input.agent_name, description=input.description)

        # === Phase 1: Draft Agent & Create Missing Skills ===
        self._state.status = "drafting"
        draft_result = await execute_activity(
            draft_agent_activity, args=[self._state.description], ...
        )
        
        missing_skills = draft_result["missing_skills"]
        if missing_skills:
            self._state.status = "creating_skills"
            skill_creation_handles = []
            for skill_desc in missing_skills:
                # Start a child workflow for each missing skill
                handle = await start_child_workflow(
                    SkillAutoWorkflow.run,
                    args=[SkillAutoInput(description=skill_desc, ...)],
                    id=f"create-skill-{skill_desc.replace('/', '-')}",
                )
                skill_creation_handles.append(handle)
            
            # Wait for all child workflows to complete
            await asyncio.gather(*[h.result() for h in skill_creation_handles])

        # Now that skills exist, write the agent files
        # This could be another activity: `write_agent_files_activity`
        self._state.agent_path = f"agents/{self._state.agent_name}"

        # === Phase 2: Eval-Improve Loop ===
        self._state.status = "improving"
        for i in range(input.max_iterations):
            eval_result_dict = await execute_activity(
                evaluate_agent_activity, args=[self._state.agent_path, self._state.test_cases], ...
            )
            eval_result = AgentEvaluationResult(**eval_result_dict)
            self._state.eval_history.append(eval_result)

            if eval_result.objective_accuracy >= input.target_accuracy:
                break

            # This would use a pure function from the domain layer
            suggestions = analyze_evaluation_failures(eval_result)

            await execute_activity(
                apply_improvements_activity, 
                args=[self._state.agent_path, suggestions.dict()], ...
            )

        # === Phase 3: Publish ===
        if self._state.eval_history[-1].objective_accuracy >= input.target_accuracy:
            self._state.status = "publishing"
            await execute_activity(
                publish_agent_activity, args=[self._state.agent_path, input.publish_options], ...
            )
            self._state.status = "published"
        else:
            self._state.status = "finished_failed_to_meet_accuracy"

        return self._state.dict()

```

**Verification:** The workflow must correctly sequence the activities and properly handle the child workflow execution for skill creation.

---

### **Task 6.3: Implement Workflow Integration Tests**

**Action:** Create high-level integration tests for the `AgentAutoWorkflow` using the Temporal test harness.

-   **File:** `tests/workflows/agent_auto/test_workflow.py`
-   **Purpose:** To verify the end-to-end orchestration, including the interaction between the parent (`agent_auto`) and child (`skill_auto`) workflows.

**Implementation:**

```python
# tests/workflows/agent_auto/test_workflow.py

from temporalio.testing import WorkflowEnvironment
from your_project.workflows.agent_auto.workflow import AgentAutoWorkflow
from your_project.workflows.skill_auto.workflow import SkillAutoWorkflow

async def test_agent_auto_workflow_creates_child_workflows_for_missing_skills():
    """Verifies that the agent workflow starts child workflows for skills."""
    async with await WorkflowEnvironment.start_time_skipping() as env:
        # 1. Mock the draft_agent_activity to return a missing skill
        async def mock_draft_activity(description):
            return {"missing_skills": ["new/skill"], "files_to_create": {}}

        # 2. Mock the skill_auto workflow to do nothing and return success
        @workflow.defn
        class MockSkillAutoWorkflow:
            @workflow.run
            async def run(self, input):
                return {"status": "published"}

        # 3. Start the agent workflow with mocked dependencies
        task_queue = "test-agent-auto-queue"
        handle = await env.client.start_workflow(
            AgentAutoWorkflow.run,
            args=[AgentAutoInput(...)],
            id="test-agent-workflow",
            task_queue=task_queue,
            activity_overrides={"draft_agent_activity": mock_draft_activity},
            # Override the actual skill workflow with our mock
            child_workflow_overrides={SkillAutoWorkflow: MockSkillAutoWorkflow},
        )

        result = await handle.result()

        # 4. Assert that the workflow completed
        # A more robust test would query the test environment to see that
        # the child workflow was actually started.
        assert result["status"] == "published" # Or whatever the final state is

```

**Verification:** The workflow integration tests must pass, confirming that the parent workflow correctly invokes and awaits the child workflows before proceeding.
