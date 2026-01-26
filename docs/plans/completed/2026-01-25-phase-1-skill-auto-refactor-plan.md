
# Detailed Implementation Plan: Phase 1 - `skill_auto` Refactor

**Date:** 2026-01-25
**Status:** Draft
**Author:** Manus AI

## 1. Objective

This document provides a highly prescriptive, step-by-step guide for refactoring the `skill_auto` workflow. The primary goal is to decouple all business logic from the Temporal framework, enabling rapid, isolated unit testing and improving code clarity and maintainability. **Developers must adhere strictly to the function signatures, file locations, and test requirements outlined below.**

## 2. Epic 1: Create `skill_auto` Domain Layer

**Goal:** Extract all pure business logic and data structures into a new, framework-independent `domain` directory. This layer must not have any dependencies on Temporal, external services, or I/O.

---

### **Task 1.1: Create Directory Structure**

**Action:** Create the following new directories to house the separated layers.

1.  `kubani/workflows/skill_auto/domain/`
2.  `kubani/workflows/skill_auto/services/`
3.  `tests/workflows/skill_auto/domain/`
4.  `tests/workflows/skill_auto/services/`

**Verification:** The directories must exist at the specified paths.

---

### **Task 1.2: Implement Domain Models**

**Action:** Move and consolidate all Pydantic models related to the workflow's state and data structures into a single file.

-   **File:** `kubani/workflows/skill_auto/domain/models.py`
-   **Purpose:** To provide a single source of truth for the data structures used throughout the workflow, ensuring type safety and clear contracts between layers.

**Implementation:**

```python
# kubani/workflows/skill_auto/domain/models.py

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

# (Add other necessary imports)

class EvalMetrics(BaseModel):
    """Metrics from a single skill evaluation run."""
    score: float = Field(..., description="Overall score from 0.0 to 1.0.")
    reasoning: str = Field(..., description="The reasoning behind the score.")
    passed: bool = Field(..., description="Whether the skill passed the evaluation criteria.")

class IterationResult(BaseModel):
    """Result of a single improvement iteration."""
    iteration: int
    files: Dict[str, str] = Field(..., description="A map of file paths to their content for this iteration.")
    metrics: EvalMetrics

class SkillAutoState(BaseModel):
    """The complete state of the skill_auto workflow."""
    skill_name: str
    description: str
    iteration: int = 0
    best_score: float = 0.0
    best_iteration: int = 0
    history: List[IterationResult] = []
    status: str = "starting"
    # ... any other state fields currently in the workflow ...

class IterationContext(BaseModel):
    """Data context required for making decisions about the iteration loop."""
    current_iteration: int
    max_iterations: int
    best_score: float
    target_accuracy: float
    history: List[IterationResult]
    is_cancelled: bool

```

**Verification:** The `models.py` file must contain all necessary Pydantic models, and they must be importable from other modules.

---

### **Task 1.3: Implement Pure Decision Functions**

**Action:** Extract the iteration control logic from the `SkillAutoWorkflow` class into pure, easily testable functions.

-   **File:** `kubani/workflows/skill_auto/domain/decisions.py`
-   **Purpose:** To isolate decision-making logic from the workflow's state machine, allowing for instant testing of all possible branching scenarios.

**Implementation:**

```python
# kubani/workflows/skill_auto/domain/decisions.py

from typing import Tuple, List
from .models import IterationContext, IterationResult

def is_plateau(history: List[IterationResult], window: int = 3) -> bool:
    """Checks if the score has plateaued over the last few iterations."""
    if len(history) < window:
        return False
    recent_scores = [h.metrics.score for h in history[-window:]]
    return all(score == recent_scores[0] for score in recent_scores)

def should_continue_iteration(ctx: IterationContext) -> Tuple[bool, str]:
    """
    Determines if the improvement loop should continue based on the provided context.
    This is a pure function with no side effects.

    Args:
        ctx: An IterationContext object containing all necessary data for the decision.

    Returns:
        A tuple containing a boolean (True to continue) and a string reason for the decision.
    """
    if ctx.is_cancelled:
        return False, "cancelled"
    if ctx.current_iteration >= ctx.max_iterations:
        return False, "max_iterations_reached"
    if ctx.best_score >= ctx.target_accuracy:
        return False, "target_accuracy_met"
    if is_plateau(ctx.history):
        return False, "score_plateaued"
    
    return True, "continue_improving"

```

### **Task 1.4: Implement Unit Tests for Decisions**

**Action:** Create comprehensive unit tests for the decision logic.

-   **File:** `tests/workflows/skill_auto/domain/test_decisions.py`
-   **Purpose:** To guarantee the correctness of the core iteration logic under all conditions, without needing a Temporal test environment.

**Implementation:**

```python
# tests/workflows/skill_auto/domain/test_decisions.py

import pytest
from kubani.workflows.skill_auto.domain.decisions import should_continue_iteration
from kubani.workflows.skill_auto.domain.models import IterationContext, IterationResult, EvalMetrics

# Helper to create a dummy history
def create_history(scores: list[float]) -> list[IterationResult]:
    return [
        IterationResult(
            iteration=i,
            files={},
            metrics=EvalMetrics(score=s, reasoning="", passed=True)
        ) for i, s in enumerate(scores)
    ]

@pytest.mark.parametrize("ctx_overrides, expected_continue, expected_reason", [
    # Test Case 1: Happy path, continue
    ({}, True, "continue_improving"),
    
    # Test Case 2: Max iterations reached
    ({"current_iteration": 10, "max_iterations": 10}, False, "max_iterations_reached"),
    
    # Test Case 3: Target accuracy met
    ({"best_score": 0.95, "target_accuracy": 0.9}, False, "target_accuracy_met"),
    
    # Test Case 4: Workflow cancelled
    ({"is_cancelled": True}, False, "cancelled"),
    
    # Test Case 5: Score has plateaued
    ({"history": create_history([0.5, 0.6, 0.7, 0.7, 0.7])}, False, "score_plateaued"),
    
    # Test Case 6: Plateau window not met yet
    ({"history": create_history([0.7, 0.7])}, True, "continue_improving"),
])
def test_should_continue_iteration(ctx_overrides, expected_continue, expected_reason):
    """Tests all scenarios for the should_continue_iteration function."""
    base_context = {
        "current_iteration": 5,
        "max_iterations": 10,
        "best_score": 0.8,
        "target_accuracy": 0.9,
        "history": create_history([0.5, 0.6, 0.7, 0.75, 0.8]),
        "is_cancelled": False,
    }
    
    # Apply test-specific overrides
    test_ctx_dict = {**base_context, **ctx_overrides}
    ctx = IterationContext(**test_ctx_dict)
    
    should_continue, reason = should_continue_iteration(ctx)
    
    assert should_continue == expected_continue
    assert reason == expected_reason

```

**Verification:** All tests in `test_decisions.py` must pass when run with `pytest`.

## 3. Epic 2: Refactor `skill_auto` Service Layer

**Goal:** Refactor all service modules (`llm_service`, `eval_service`, etc.) to remove hidden dependencies on global configuration. Services must accept their dependencies via their constructors, making them independently testable.

---

### **Task 2.1: Define Service Protocols**

**Action:** Define `Protocol` classes for external dependencies, such as the LLM client. This allows for creating mock implementations for testing.

-   **File:** `kubani/workflows/skill_auto/services/protocols.py` (New file)
-   **Purpose:** To establish clear contracts for external dependencies, enabling true dependency inversion and simplifying mocking.

**Implementation:**

```python
# kubani/workflows/skill_auto/services/protocols.py

from typing import Protocol, Any, Dict

class LLMClient(Protocol):
    """Defines the contract for an LLM client used by the services."""
    async def complete(self, prompt: str, **kwargs) -> str:
        ...

    async def close(self) -> None:
        ...

class FileSystem(Protocol):
    """Defines the contract for file system operations."""
    def read(self, path: str) -> str:
        ...

    def write(self, path: str, content: str) -> None:
        ...

    def list_files(self, path: str, recursive: bool = False) -> list[str]:
        ...

```

**Verification:** The `protocols.py` file must exist and contain the specified `Protocol` definitions.

---

### **Task 2.2: Refactor `LLMService` with Dependency Injection**

**Action:** Modify the `LLMService` to accept an `LLMClient` protocol implementation in its constructor instead of creating one from global config.

-   **File:** `kubani/workflows/skill_auto/services/llm.py` (New file, logic moved from `llm_service.py`)
-   **Purpose:** To decouple the service's business logic (e.g., prompt building, response parsing) from the specific implementation of the LLM client.

**Implementation:**

```python
# kubani/workflows/skill_auto/services/llm.py

from .protocols import LLMClient
from ..domain.models import OverlapResult # Example model

class LLMService:
    """Service for all LLM-related operations, using dependency injection."""
    
    def __init__(self, client: LLMClient):
        """Initializes the service with a specific LLM client implementation."""
        self._client = client

    async def detect_skill_overlap(
        self,
        description: str,
        existing_skills: list[dict[str, Any]],
    ) -> OverlapResult:
        """Detects skill overlap using the injected LLM client."""
        prompt = self._build_overlap_prompt(description, existing_skills)
        response_str = await self._client.complete(prompt, max_tokens=500)
        # Assume _parse_response is a private method that parses the string
        response_data = self._parse_response(response_str)
        return OverlapResult(**response_data)

    def _build_overlap_prompt(self, description: str, existing_skills: list) -> str:
        """Builds the prompt for overlap detection. This is a pure, testable function."""
        # ... existing prompt building logic ...
        return "..."

    def _parse_response(self, response: str) -> dict:
        """Parses the LLM's JSON response. This is a pure, testable function."""
        # ... existing parsing logic ...
        return {}

```

### **Task 2.3: Implement Unit Tests for `LLMService`**

**Action:** Create unit tests for the refactored `LLMService` using a mock client.

-   **File:** `tests/workflows/skill_auto/services/test_llm_service.py`
-   **Purpose:** To verify the service's logic (prompt building, parsing) works correctly, independent of any actual LLM.

**Implementation:**

```python
# tests/workflows/skill_auto/services/test_llm_service.py

import pytest
from kubani.workflows.skill_auto.services.llm import LLMService
from kubani.workflows.skill_auto.services.protocols import LLMClient

class MockLLMClient(LLMClient):
    """A mock LLM client for testing the service layer."""
    def __init__(self, response_to_return: str):
        self.last_prompt = None
        self._response = response_to_return

    async def complete(self, prompt: str, **kwargs) -> str:
        self.last_prompt = prompt
        return self._response

    async def close(self) -> None:
        pass

@pytest.mark.asyncio
async def test_detect_skill_overlap_parses_correctly():
    """Ensures the service correctly calls the client and parses its response."""
    # 1. Arrange
    mock_response = '{"has_overlap": true, "reasoning": "Similar to skill X"}'
    mock_client = MockLLMClient(response_to_return=mock_response)
    llm_service = LLMService(client=mock_client)
    
    # 2. Act
    result = await llm_service.detect_skill_overlap("A new skill", [])
    
    # 3. Assert
    assert result.has_overlap is True
    assert result.reasoning == "Similar to skill X"
    assert "A new skill" in mock_client.last_prompt # Verify prompt was built

```

**Verification:** All tests in `test_llm_service.py` must pass. Repeat this pattern for all other services (`EvaluationService`, `ImprovementService`, etc.), ensuring they all use dependency injection and have corresponding unit tests with mocks.

## 4. Epic 3: Update `skill_auto` Workflow & Activities

**Goal:** Reconnect the Temporal framework layer (workflows and activities) to the new, testable service layer. This layer should be as thin as possible, containing no business logic.

---

### **Task 3.1: Refactor Activities as Thin Wrappers**

**Action:** Rewrite all activities to do nothing more than instantiate the required services and call their methods. All configuration should be read here, at the boundary of the application, and passed into the services.

-   **File:** `kubani/workflows/skill_auto/activities.py`
-   **Purpose:** To create a clear boundary between the Temporal infrastructure and the application's core logic. This is the only place where global configuration should be accessed.

**Implementation:**

```python
# kubani/workflows/skill_auto/activities.py

from temporalio import activity
from ..config import get_config # Or a similar config-loading function
from .services.llm import LLMService
from .services.evaluation import EvaluationService
from .services.protocols import LLMClient # This might be a concrete implementation
from .domain.models import OverlapResult, EvalMetrics

# This is a helper that would instantiate the actual LLM client.
# It lives at the edge of the application.
def _create_llm_client() -> LLMClient:
    config = get_config().llm
    # Assuming you have a concrete implementation, e.g., from an external library
    return ConcreteLLMClient(base_url=config.api_url, api_key=config.api_key)

@activity.defn
async def detect_skill_overlap_activity(
    description: str,
    existing_skills: list[dict[str, Any]],
) -> OverlapResult:
    """Activity to detect skill overlap."""
    # 1. Instantiate dependencies at the boundary
    llm_client = _create_llm_client()
    llm_service = LLMService(client=llm_client)
    
    activity.heartbeat()
    
    # 2. Call the service method
    try:
        return await llm_service.detect_skill_overlap(description, existing_skills)
    finally:
        # 3. Clean up resources
        await llm_client.close()

@activity.defn
async def evaluate_skill_activity(skill_files: dict[str, str]) -> EvalMetrics:
    """Activity to evaluate a skill's performance."""
    # 1. Instantiate dependencies
    eval_config = get_config().evaluation
    # Assuming EvaluationService also uses DI
    eval_service = EvaluationService(config=eval_config)
    
    activity.heartbeat()
    
    # 2. Call the service method
    return await eval_service.evaluate(skill_files)

```

**Verification:** The activities must not contain any `if/else` statements, loops, or other logic that belongs in the service or domain layers. Their sole purpose is instantiation, delegation, and cleanup.

---

### **Task 3.2: Simplify the `SkillAutoWorkflow`**

**Action:** Remove all business logic from the workflow class itself. The workflow should only orchestrate activity calls and manage state, using the pure functions from the domain layer to make decisions.

-   **File:** `kubani/workflows/skill_auto/workflow.py`
-   **Purpose:** To make the workflow a pure orchestrator, whose logic is easy to follow and whose state transitions are predictable.

**Implementation:**

```python
# kubani/workflows/skill_auto/workflow.py

from temporalio.workflow import workflow, execute_activity
from .activities import detect_skill_overlap_activity, evaluate_skill_activity, ...
from .domain.models import SkillAutoState, IterationContext, SkillAutoInput
from .domain.decisions import should_continue_iteration

@workflow.defn
class SkillAutoWorkflow:
    @workflow.run
    async def run(self, input: SkillAutoInput) -> dict:
        self._state = SkillAutoState(skill_name=input.skill_name, description=input.description)

        # Phase 1: Overlap Check
        self._state.status = "checking_overlap"
        overlap_result = await execute_activity(
            detect_skill_overlap_activity,
            args=[self._state.description, input.existing_skills],
            # ... timeouts ...
        )
        if overlap_result.has_overlap:
            self._state.status = "finished_overlap"
            return self._state.dict()

        # Phase 2: Initial Creation & Eval-Improve Loop
        self._state.status = "improving"
        while True:
            # 1. Make decision using pure function
            iter_ctx = IterationContext(
                current_iteration=self._state.iteration,
                max_iterations=input.max_iterations,
                best_score=self._state.best_score,
                target_accuracy=input.target_accuracy,
                history=self._state.history,
                is_cancelled=workflow.is_cancelled,
            )
            should_continue, reason = should_continue_iteration(iter_ctx)
            
            if not should_continue:
                self._state.status = f"finished_{reason}"
                break

            # 2. Determine action (create or improve) and execute activities
            # ... (call create_skill_activity or improve_skill_activity)
            
            # 3. Update state from activity results
            # ... (self._state.iteration += 1, self._state.history.append(...))

        # Phase 3: Finalization
        self._state.status = "finalizing"
        # ... (call finalize_skill_activity)
        
        return self._state.dict()
```

**Verification:** The `workflow.py` file should contain almost no complex logic. All `if` statements should be based on the results of activity calls or the pure decision functions from the domain layer.

---

### **Task 3.3: Update Workflow Tests**

**Action:** Adapt the existing high-level workflow tests to verify the orchestration logic.

-   **File:** `tests/workflows/skill_auto/test_workflow.py`
-   **Purpose:** To ensure the workflow correctly sequences activities and manages state, even though the underlying business logic is now tested elsewhere.

**Implementation:**

The tests will now focus on mocking activity results and asserting that the workflow takes the correct path.

```python
# tests/workflows/skill_auto/test_workflow.py

from temporalio.testing import WorkflowEnvironment
from your_project.workflows.skill_auto.workflow import SkillAutoWorkflow

async def test_skill_auto_workflow_stops_on_target_accuracy():
    """Tests that the workflow orchestrator stops when an activity returns a high score."""
    async with await WorkflowEnvironment.start_time_skipping() as env:
        # Mock the activities to return specific results
        async def mock_eval_activity(files):
            # On the first run, return a low score
            if len(workflow.state.history) == 0:
                return EvalMetrics(score=0.7, ...)
            # On the second run, return a high score
            else:
                return EvalMetrics(score=0.95, ...)

        # ... mock other activities ...

        task_queue = "test-queue"
        # Execute the workflow with mocked activities
        handle = await env.client.start_workflow(
            SkillAutoWorkflow.run,
            args=[SkillAutoInput(target_accuracy=0.9)],
            id="test-workflow",
            task_queue=task_queue,
            activity_overrides={ "evaluate_skill_activity": mock_eval_activity, ... },
        )
        result = await handle.result()

        # Assert that the workflow finished because the target was met
        assert result["status"] == "finished_target_accuracy_met"
        assert result["iteration"] == 2 # Ran twice

```

**Verification:** The workflow tests must pass, confirming that the orchestration logic correctly responds to the (mocked) results of its activities.
