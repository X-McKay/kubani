# Detailed Implementation Plan: Phase 2 - `agent_auto` Core Logic

**Date:** 2026-01-25
**Status:** Draft
**Author:** Manus AI

## 1. Objective

This document provides a prescriptive guide for building the core domain and service layers for the new `agent_auto` workflow. This phase focuses exclusively on creating the testable, framework-independent business logic. All function signatures, file locations, and test requirements must be followed precisely to ensure a robust and maintainable implementation.

## 2. Epic 4: Create `agent_auto` Domain Layer

**Goal:** Build the pure, testable, and framework-independent core logic for agent automation. This layer will contain all data models, analysis functions, generation logic, and metric calculations. It must have no external dependencies.

---

### **Task 4.1: Create Directory Structure**

**Action:** Create the necessary directories for the new workflow's domain and service layers.

1.  `kubani/workflows/agent_auto/domain/`
2.  `kubani/workflows/agent_auto/services/`
3.  `tests/workflows/agent_auto/domain/`
4.  `tests/workflows/agent_auto/services/`

**Verification:** The directories must exist at the specified paths.

---

### **Task 4.2: Implement Domain Models**

**Action:** Define all Pydantic models that represent the data and state for the `agent_auto` workflow.

-   **File:** `kubani/workflows/agent_auto/domain/models.py`
-   **Purpose:** To establish a clear, type-safe data contract for all inputs, outputs, and state transitions within the workflow.

**Implementation:**

```python
# kubani/workflows/agent_auto/domain/models.py

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class AgentSpec(BaseModel):
    """Specification for the agent to be generated."""
    name: str
    description: str
    required_skills: List[str]
    config_patterns: Dict[str, Any]

class AgentTestCase(BaseModel):
    """A single test case for evaluating an agent."""
    name: str
    prompt: str
    expected_skills: List[str]
    expected_output: str # Or a more complex structure

class AgentEvaluationResult(BaseModel):
    """The result of a single agent evaluation run."""
    objective_accuracy: float = Field(..., description="Overall score based on test case outcomes.")
    skill_precision: float = Field(..., description="Of the skills invoked, how many were correct?")
    skill_recall: float = Field(..., description="Of the skills required, how many were invoked?")
    invoked_skills: List[str]
    missing_skills: List[str]
    extraneous_skills: List[str]
    failures: List[str] = Field(..., description="List of failed test case names.")

class ImprovementSuggestions(BaseModel):
    """Suggestions for how to improve an agent based on an evaluation."""
    prompt_clarifications: List[str]
    skill_additions: List[str]
    skill_removals: List[str]
    config_changes: Dict[str, Any]

class AgentAutoState(BaseModel):
    """The complete state of the agent_auto workflow."""
    agent_name: str
    description: str
    agent_path: Optional[str] = None
    test_cases: List[AgentTestCase] = []
    eval_history: List[AgentEvaluationResult] = []
    # ... other state fields ...

```

**Verification:** The `models.py` file must contain these Pydantic models.

---

### **Task 4.3: Implement Analysis Functions**

**Action:** Create pure functions for analyzing agent requirements and evaluation results.

-   **File:** `kubani/workflows/agent_auto/domain/analysis.py`
-   **Purpose:** To isolate the core intelligence of the workflow (understanding requests and diagnosing failures) into testable units.

**Implementation:**

```python
# kubani/workflows/agent_auto/domain/analysis.py

from .models import AgentSpec, AgentEvaluationResult, ImprovementSuggestions

def analyze_agent_requirements(description: str) -> AgentSpec:
    """
    Analyzes a high-level description to produce a concrete agent specification.
    NOTE: In a real implementation, this would use an LLM, but for the domain layer,
    we can simulate it or use a simple keyword-based approach to keep it pure.
    For this task, a simple, rule-based implementation is sufficient.
    """
    # Example rule-based implementation
    required_skills = []
    if "monitor" in description and "kubernetes" in description:
        required_skills.append("k8s/pod/list")
    
    return AgentSpec(
        name="generated_agent",
        description=description,
        required_skills=required_skills,
        config_patterns={"skills.allowed": ["*"], "model": "gpt-4.1-mini"}
    )

def analyze_evaluation_failures(eval_result: AgentEvaluationResult) -> ImprovementSuggestions:
    """
    Analyzes an evaluation result to generate concrete suggestions for improvement.
    This is a pure function.
    """
    suggestions = ImprovementSuggestions(prompt_clarifications=[], skill_additions=[], skill_removals=[], config_changes={})
    
    if eval_result.missing_skills:
        suggestions.prompt_clarifications.append(
            f"Consider adding logic to the prompt to handle cases requiring these missing skills: {eval_result.missing_skills}"
        )
        suggestions.skill_additions.extend(eval_result.missing_skills)

    if eval_result.extraneous_skills:
        suggestions.prompt_clarifications.append(
            f"The prompt may be too ambiguous, causing incorrect invocation of these skills: {eval_result.extraneous_skills}"
        )
        # We might not want to automatically remove skills, but suggest it.

    return suggestions

```

### **Task 4.4: Implement Unit Tests for Analysis**

**Action:** Write unit tests for the analysis functions.

-   **File:** `tests/workflows/agent_auto/domain/test_analysis.py`
-   **Purpose:** To verify the correctness of the requirement analysis and failure diagnosis logic.

**Implementation:**

```python
# tests/workflows/agent_auto/domain/test_analysis.py

from kubani.workflows.agent_auto.domain.analysis import analyze_evaluation_failures
from kubani.workflows.agent_auto.domain.models import AgentEvaluationResult

def test_analyze_failures_suggests_skill_addition_for_missing_skills():
    """Tests that missing skills in an eval result lead to skill addition suggestions."""
    # Arrange
    eval_result = AgentEvaluationResult(
        objective_accuracy=0.5,
        skill_precision=1.0,
        skill_recall=0.5,
        invoked_skills=["skill/a"],
        missing_skills=["skill/b"],
        extraneous_skills=[],
        failures=["Test Case 2"]
    )

    # Act
    suggestions = analyze_evaluation_failures(eval_result)

    # Assert
    assert suggestions.skill_additions == ["skill/b"]
    assert "missing skills: [\'skill/b\']" in suggestions.prompt_clarifications[0]

```

**Verification:** All tests in `test_analysis.py` must pass.

---

### **Task 4.5: Implement Metrics Functions**

**Action:** Create pure functions for calculating evaluation metrics.

-   **File:** `kubani/workflows/agent_auto/domain/metrics.py`
-   **Purpose:** To provide a testable and reusable way to calculate agent performance based on observed and expected behavior.

**Implementation:**

```python
# kubani/workflows/agent_auto/domain/metrics.py

from typing import Set

def calculate_skill_precision(invoked: Set[str], required: Set[str]) -> float:
    """Calculates precision: Of the skills invoked, how many were correct?"""
    if not invoked:
        return 1.0 # By convention, if nothing was invoked, precision is perfect.
    
    correctly_invoked = invoked.intersection(required)
    return len(correctly_invoked) / len(invoked)

def calculate_skill_recall(invoked: Set[str], required: Set[str]) -> float:
    """Calculates recall: Of the skills required, how many were invoked?"""
    if not required:
        return 1.0 # If no skills were required, recall is perfect.
        
    correctly_invoked = invoked.intersection(required)
    return len(correctly_invoked) / len(required)

```

### **Task 4.6: Implement Unit Tests for Metrics**

**Action:** Write unit tests for the metrics functions.

-   **File:** `tests/workflows/agent_auto/domain/test_metrics.py`
-   **Purpose:** To ensure the performance metrics are calculated correctly.

**Implementation:**

```python
# tests/workflows/agent_auto/domain/test_metrics.py

import pytest
from kubani.workflows.agent_auto.domain.metrics import calculate_skill_precision, calculate_skill_recall

@pytest.mark.parametrize("invoked, required, expected_precision, expected_recall", [
    ({"a", "b"}, {"a", "b"}, 1.0, 1.0),      # Perfect match
    ({"a"}, {"a", "b"}, 1.0, 0.5),             # Missed one (low recall)
    ({"a", "b"}, {"a"}, 0.5, 1.0),             # Invoked extra (low precision)
    ({"c"}, {"a", "b"}, 0.0, 0.0),             # Completely wrong
    (set(), {"a"}, 1.0, 0.0),                   # Invoked none, required some
    ({"a"}, set(), 0.0, 1.0),                   # Invoked some, required none
    (set(), set(), 1.0, 1.0),                   # Invoked none, required none
])
def test_skill_metrics(invoked, required, expected_precision, expected_recall):
    precision = calculate_skill_precision(invoked, required)
    recall = calculate_skill_recall(invoked, required)
    assert precision == pytest.approx(expected_precision)
    assert recall == pytest.approx(expected_recall)

```

**Verification:** All tests in `test_metrics.py` must pass.

## 3. Epic 5: Create `agent_auto` Service Layer

**Goal:** Implement the business logic services that compose the pure functions from the domain layer into meaningful operations. These services will use dependency injection and be testable with mocks.

---

### **Task 5.1: Implement `DraftingService`**

**Action:** Create the service responsible for the initial drafting of an agent.

-   **File:** `kubani/workflows/agent_auto/services/drafting.py`
-   **Purpose:** To orchestrate the process of analyzing requirements, identifying skill gaps, and generating the initial agent files.

**Implementation:**

```python
# kubani/workflows/agent_auto/services/drafting.py

from .protocols import LLMClient, FileSystem, SkillRepository # Assume SkillRepository protocol exists
from ..domain.analysis import analyze_agent_requirements
from ..domain.generation import generate_agent_prompt, generate_agent_config # Assume these exist

class DraftingService:
    def __init__(self, llm_client: LLMClient, fs: FileSystem, skill_repo: SkillRepository):
        self._llm = llm_client
        self._fs = fs
        self._skill_repo = skill_repo

    async def draft_agent(self, description: str) -> dict:
        """
        Orchestrates the agent drafting process.
        1. Analyzes description to get an AgentSpec.
        2. Checks which required skills already exist.
        3. Returns a list of missing skills and the generated agent files.
        """
        # In a real scenario, this would use the LLM, but we use the pure function
        agent_spec = analyze_agent_requirements(description)

        existing_skills = self._skill_repo.get_skills_by_name(agent_spec.required_skills)
        existing_skill_names = {s.name for s in existing_skills}
        missing_skills = [s for s in agent_spec.required_skills if s not in existing_skill_names]

        # Don't write files yet; the workflow will do that after creating missing skills.
        # Instead, return the content to be written.
        agent_prompt = generate_agent_prompt(agent_spec)
        agent_config = generate_agent_config(agent_spec)

        return {
            "missing_skills": missing_skills,
            "files_to_create": {
                f"agents/{agent_spec.name}/prompt.md": agent_prompt,
                f"agents/{agent_spec.name}/config.yaml": agent_config,
            }
        }

```

### **Task 5.2: Implement `EvaluationService`**

**Action:** Create the service responsible for evaluating an agent against a set of test cases.

-   **File:** `kubani/workflows/agent_auto/services/evaluation.py`
-   **Purpose:** To run an agent, capture its outputs and invoked skills, and score its performance using the pure metrics functions.

**Implementation:**

```python
# kubani/workflows/agent_auto/services/evaluation.py

from .protocols import AgentRunner # Assume a protocol for running an agent sandbox
from ..domain.models import AgentTestCase, AgentEvaluationResult
from ..domain.metrics import calculate_skill_precision, calculate_skill_recall

class EvaluationService:
    def __init__(self, agent_runner: AgentRunner):
        self._runner = agent_runner

    async def evaluate_agent(
        self, agent_path: str, test_cases: list[AgentTestCase]
    ) -> AgentEvaluationResult:
        """Runs all test cases against the agent and computes metrics."""
        total_invoked = set()
        total_required = set()
        failures = []
        passed_count = 0

        for test in test_cases:
            # The runner would execute the agent in a sandbox and return results
            run_result = await self._runner.run(agent_path, test.prompt)
            
            required = set(test.expected_skills)
            invoked = set(run_result.invoked_skills)

            total_invoked.update(invoked)
            total_required.update(required)

            # Simple pass/fail based on output match
            if run_result.output.strip() == test.expected_output.strip():
                passed_count += 1
            else:
                failures.append(test.name)

        return AgentEvaluationResult(
            objective_accuracy=passed_count / len(test_cases),
            skill_precision=calculate_skill_precision(total_invoked, total_required),
            skill_recall=calculate_skill_recall(total_invoked, total_required),
            invoked_skills=list(total_invoked),
            missing_skills=list(total_required - total_invoked),
            extraneous_skills=list(total_invoked - total_required),
            failures=failures,
        )

```

### **Task 5.3: Implement Integration Tests for Services**

**Action:** Write integration tests for the new services, using mock implementations of their dependencies.

-   **File:** `tests/workflows/agent_auto/services/test_drafting_service.py`
-   **Purpose:** To verify that the services correctly compose their dependencies and produce the expected output.

**Implementation:**

```python
# tests/workflows/agent_auto/services/test_drafting_service.py

import pytest
from kubani.workflows.agent_auto.services.drafting import DraftingService
from .mocks import MockLLMClient, MockFileSystem, MockSkillRepository # Assume these exist

@pytest.mark.asyncio
async def test_draft_agent_identifies_missing_skills():
    """Tests that the drafting service correctly identifies skills that need to be created."""
    # Arrange
    mock_llm = MockLLMClient(response_to_return="...") # Not used if using pure function
    mock_fs = MockFileSystem()
    # Mock repo has 'skill/a' but not 'skill/b'
    mock_repo = MockSkillRepository(existing_skills=[{"name": "skill/a"}])

    service = DraftingService(llm_client=mock_llm, fs=mock_fs, skill_repo=mock_repo)

    # Act
    # The description should trigger a requirement for both skills via the pure analysis function
    result = await service.draft_agent("An agent that needs skill/a and skill/b")

    # Assert
    assert result["missing_skills"] == ["skill/b"]
    assert "agents/generated_agent/prompt.md" in result["files_to_create"]

```

**Verification:** All service-level integration tests must pass.
