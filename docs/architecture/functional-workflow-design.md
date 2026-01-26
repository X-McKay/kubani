# Functional Workflow Architecture

This document describes the layered architecture pattern used in Kubani's Temporal workflows. The pattern prioritizes testability, maintainability, and clear separation of concerns.

## Overview

The architecture divides workflow code into four distinct layers, each with a specific responsibility:

```
┌─────────────────────────────────────────────────────────────┐
│                    Workflow Layer                           │
│         (Orchestration, State Management, Signals)          │
├─────────────────────────────────────────────────────────────┤
│                    Activity Layer                           │
│           (Thin Wrappers, Service Instantiation)            │
├─────────────────────────────────────────────────────────────┤
│                    Service Layer                            │
│        (Dependency Injection, Business Composition)         │
├─────────────────────────────────────────────────────────────┤
│                    Domain Layer                             │
│          (Pure Functions, Models, Core Logic)               │
└─────────────────────────────────────────────────────────────┘
```

### Why This Architecture?

| Problem | Solution |
|---------|----------|
| Temporal activities are hard to unit test | Domain layer has pure functions that are trivially testable |
| Business logic is scattered across activities | Domain layer centralizes core logic |
| Dependencies are hard to mock | Service layer uses dependency injection via protocols |
| Activities do too much | Activities become thin wrappers that just instantiate services |

## The Four Layers

### 1. Domain Layer

**Location:** `kubani/workflows/{workflow_name}/domain/`

**Responsibility:** Pure functions and data models. No I/O, no side effects.

**Contains:**
- Pydantic models for inputs, outputs, and state
- Pure functions that transform data
- Business logic that doesn't require external dependencies

**Example:**

```python
# domain/models.py
from pydantic import BaseModel

class SkillSpec(BaseModel):
    name: str
    category: str
    description: str

class OverlapResult(BaseModel):
    has_overlap: bool
    overlapping_skills: list[str]
    similarity_scores: dict[str, float]

# domain/analysis.py
def detect_overlap(
    new_skill: SkillSpec,
    existing_skills: list[SkillSpec],
    threshold: float = 0.7
) -> OverlapResult:
    """Pure function - no I/O, completely deterministic."""
    overlapping = []
    scores = {}

    for existing in existing_skills:
        score = _calculate_similarity(new_skill, existing)
        scores[existing.name] = score
        if score >= threshold:
            overlapping.append(existing.name)

    return OverlapResult(
        has_overlap=len(overlapping) > 0,
        overlapping_skills=overlapping,
        similarity_scores=scores,
    )
```

**Testing:** Unit tests with no mocks required.

```python
def test_detect_overlap_finds_similar_skills():
    new_skill = SkillSpec(name="k8s-pod-debug", ...)
    existing = [SkillSpec(name="k8s-pod-troubleshoot", ...)]

    result = detect_overlap(new_skill, existing, threshold=0.5)

    assert result.has_overlap
    assert "k8s-pod-troubleshoot" in result.overlapping_skills
```

### 2. Service Layer

**Location:** `kubani/workflows/{workflow_name}/services/`

**Responsibility:** Compose domain functions with external dependencies. Uses dependency injection via protocols.

**Contains:**
- Protocol definitions for external dependencies
- Service classes that accept protocols via constructor
- Methods that orchestrate domain functions with I/O

**Example:**

```python
# services/protocols.py
from typing import Protocol

class LLMClient(Protocol):
    async def generate(self, prompt: str) -> str: ...

class VectorStore(Protocol):
    async def search(self, query: str, limit: int) -> list[dict]: ...

# services/drafting.py
from dataclasses import dataclass

@dataclass
class DraftingService:
    llm: LLMClient
    vector_store: VectorStore

    async def draft_skill(self, description: str) -> SkillDraft:
        # Search for similar existing skills
        similar = await self.vector_store.search(description, limit=5)

        # Use domain function to check overlap
        existing_specs = [SkillSpec(**s) for s in similar]
        new_spec = SkillSpec(name="draft", description=description, category="")
        overlap = detect_overlap(new_spec, existing_specs)

        if overlap.has_overlap:
            # Generate differentiated skill
            prompt = build_differentiation_prompt(description, overlap)
        else:
            prompt = build_standard_prompt(description)

        # Call LLM
        content = await self.llm.generate(prompt)
        return parse_skill_draft(content)
```

**Testing:** Integration tests with mock protocols.

```python
async def test_draft_skill_differentiates_from_existing():
    mock_llm = MockLLM(responses=["skill content..."])
    mock_store = MockVectorStore(results=[{"name": "similar-skill", ...}])

    service = DraftingService(llm=mock_llm, vector_store=mock_store)
    result = await service.draft_skill("A skill for debugging pods")

    assert "differentiation" in mock_llm.last_prompt.lower()
```

### 3. Activity Layer

**Location:** `kubani/workflows/{workflow_name}/activities.py`

**Responsibility:** Thin wrappers that instantiate services with real dependencies. Temporal activities are defined here.

**Contains:**
- Activity functions decorated with `@activity.defn`
- Service instantiation with real clients
- Minimal logic - just wiring

**Example:**

```python
# activities.py
from temporalio import activity

from kubani.framework.llm import get_llm_client
from kubani.framework.mcp import get_mcp_client

from .services.drafting import DraftingService

@activity.defn
async def draft_skill_activity(description: str) -> dict:
    """Thin wrapper - just instantiates service and calls it."""
    llm = get_llm_client()
    mcp = get_mcp_client()

    service = DraftingService(
        llm=llm,
        vector_store=mcp.qdrant,
    )

    result = await service.draft_skill(description)
    return result.model_dump()
```

**Testing:** End-to-end tests with Temporal test harness (or skip in favor of service layer tests).

### 4. Workflow Layer

**Location:** `kubani/workflows/{workflow_name}/workflow.py`

**Responsibility:** Orchestration, state management, signals, and queries. Calls activities.

**Contains:**
- Workflow class decorated with `@workflow.defn`
- State management via instance variables
- Signal and query handlers
- Activity invocations with retry policies

**Example:**

```python
# workflow.py
from temporalio import workflow

@workflow.defn
class SkillAutoWorkflow:
    def __init__(self):
        self._state = SkillAutoState()
        self._paused = False

    @workflow.run
    async def run(self, input: SkillAutoInput) -> SkillAutoResult:
        # Phase 1: Draft
        self._state.status = "drafting"
        draft = await workflow.execute_activity(
            draft_skill_activity,
            args=[input.description],
            start_to_close_timeout=timedelta(minutes=5),
        )

        # Phase 2: Evaluate
        self._state.status = "evaluating"
        # ... continue orchestration

    @workflow.query
    def get_state(self) -> SkillAutoState:
        return self._state

    @workflow.signal
    async def pause(self):
        self._paused = True
```

**Testing:** Temporal workflow tests with mocked activities.

## Data Flow

```
User Request
     │
     ▼
┌─────────────┐
│  Workflow   │  Orchestrates phases, manages state
└─────────────┘
     │ execute_activity()
     ▼
┌─────────────┐
│  Activity   │  Instantiates service with real deps
└─────────────┘
     │ calls service method
     ▼
┌─────────────┐
│  Service    │  Composes domain logic with I/O
└─────────────┘
     │ calls pure functions
     ▼
┌─────────────┐
│  Domain     │  Pure transformations, no side effects
└─────────────┘
     │
     ▼
   Result flows back up
```

## Testing Strategy

| Layer | Test Type | Mocks Required | Speed |
|-------|-----------|----------------|-------|
| Domain | Unit | None | Fast |
| Service | Integration | Protocol implementations | Medium |
| Activity | Optional | Real deps or skip | Slow |
| Workflow | Workflow | Mocked activities | Medium |

### Recommended Testing Priority

1. **Domain Layer (Required):** Test all pure functions. These are the cheapest and most valuable tests.

2. **Service Layer (Required):** Test service methods with mock protocols. Covers business logic composition.

3. **Workflow Layer (Required for complex flows):** Use Temporal's test harness with mocked activity results.

4. **Activity Layer (Optional):** Usually covered by service tests. Add only for complex instantiation logic.

## Directory Structure

```
kubani/workflows/skill_auto/
├── __init__.py
├── workflow.py              # Workflow layer
├── activities.py            # Activity layer
├── domain/
│   ├── __init__.py
│   ├── models.py           # Pydantic models
│   ├── analysis.py         # Pure analysis functions
│   ├── generation.py       # Pure generation functions
│   └── metrics.py          # Pure metric calculations
└── services/
    ├── __init__.py
    ├── protocols.py        # Dependency protocols
    ├── drafting.py         # Drafting service
    └── evaluation.py       # Evaluation service
```

## Migration Guide

When refactoring an existing workflow to this pattern:

### Step 1: Extract Models

Move all Pydantic models to `domain/models.py`.

### Step 2: Identify Pure Logic

Look for code that doesn't require I/O:
- Data transformations
- Validation logic
- Calculations
- String/prompt building

Extract these to `domain/*.py`.

### Step 3: Define Protocols

For each external dependency (LLM, database, API), create a Protocol in `services/protocols.py`.

### Step 4: Create Services

Create service classes that:
- Accept protocols via constructor
- Call domain functions
- Handle I/O through injected dependencies

### Step 5: Thin Out Activities

Reduce activities to:
- Instantiate real dependencies
- Create service with dependencies
- Call service method
- Return result

### Step 6: Update Tests

- Add unit tests for domain functions
- Add integration tests for services with mocks
- Keep or add workflow tests with mocked activities

## Example: Refactoring `detect_skill_overlap`

### Before (all in activity)

```python
@activity.defn
async def detect_skill_overlap_activity(skill_name: str) -> dict:
    # Mixed concerns: I/O, business logic, data transformation
    client = get_mcp_client()
    results = await client.qdrant.search(skill_name, limit=10)

    overlapping = []
    for r in results:
        if r["score"] > 0.7:
            overlapping.append(r["name"])

    return {"overlapping": overlapping, "count": len(overlapping)}
```

### After (layered)

```python
# domain/analysis.py
def find_overlapping_skills(
    search_results: list[SearchResult],
    threshold: float = 0.7
) -> list[str]:
    """Pure function."""
    return [r.name for r in search_results if r.score >= threshold]

# services/analysis.py
@dataclass
class AnalysisService:
    vector_store: VectorStore

    async def detect_overlap(self, skill_name: str) -> OverlapResult:
        results = await self.vector_store.search(skill_name, limit=10)
        overlapping = find_overlapping_skills(results)
        return OverlapResult(overlapping=overlapping, count=len(overlapping))

# activities.py
@activity.defn
async def detect_skill_overlap_activity(skill_name: str) -> dict:
    service = AnalysisService(vector_store=get_mcp_client().qdrant)
    result = await service.detect_overlap(skill_name)
    return result.model_dump()
```

## Best Practices

1. **Keep domain functions small and focused.** Each should do one thing.

2. **Protocols should be minimal.** Only include methods the service actually uses.

3. **Services should be stateless.** State lives in the workflow layer.

4. **Activities should be boring.** If an activity has interesting logic, extract it.

5. **Test the domain layer thoroughly.** It's cheap and catches most bugs.

6. **Use protocols, not concrete types.** This enables testing without complex mocks.

7. **Don't skip the service layer.** It's the bridge that makes everything testable.
