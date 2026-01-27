# Skill Auto Refactor Implementation Plan

## Overview

Refactor `kubani/workflows/skill_auto/` from ~5,000 lines across 16+ files to ~2,300 lines across 12 files, organized by capability rather than layer.

**Related:** [Ideas document](../ideas/2026-01-26-skill-auto-simplification.md)

---

## Target Structure

```
skill_auto/
├── capabilities/              # Pure business logic (no Temporal)
│   ├── __init__.py
│   ├── draft_skill.py         # ~150 lines
│   ├── draft_test_cases.py    # ~150 lines
│   ├── detect_skill_overlap.py # ~100 lines
│   ├── evaluate_skill.py      # ~150 lines
│   ├── improve_skill.py       # ~150 lines
│   └── promote_skill.py       # ~200 lines
│
├── temporal/                  # Temporal-specific code
│   ├── __init__.py
│   ├── workflow.py            # ~350 lines
│   ├── activities.py          # ~250 lines (thin wrappers)
│   └── worker.py              # ~100 lines
│
├── __init__.py                # Public exports
├── models.py                  # ~300 lines (data models + scoring)
├── protocols.py               # ~150 lines (LLMClient, FileSystem, etc.)
└── utils.py                   # ~150 lines (JSON extraction, output cleaning)

Total: ~2,200 lines (vs ~5,000 current)
```

---

## Implementation Phases

### Phase 1: Create New Structure (Non-Breaking)

Create the new directory structure and files alongside existing code. No deletions yet.

#### Step 1.1: Create directories and `__init__.py` files

```bash
mkdir -p kubani/workflows/skill_auto/capabilities
mkdir -p kubani/workflows/skill_auto/temporal
touch kubani/workflows/skill_auto/capabilities/__init__.py
touch kubani/workflows/skill_auto/temporal/__init__.py
```

#### Step 1.2: Create `protocols.py`

Consolidate all protocol definitions into one file:

**Source from:**
- `file_service.py` → `FileServiceProtocol`
- `services/protocols.py` → `LLMClient`, `FileSystem`, `DiscordClient`

**Target content:**
```python
# protocols.py
from typing import Any, Protocol

class LLMClient(Protocol):
    def chat(self, messages: list[dict[str, str]], **kwargs) -> dict[str, Any]: ...

class FileSystem(Protocol):
    def read(self, path: str) -> str: ...
    def write(self, path: str, content: str) -> None: ...
    def exists(self, path: str) -> bool: ...
    def mkdir(self, path: str) -> None: ...
    def list_files(self, path: str, pattern: str) -> list[str]: ...
    def copy(self, src: str, dst: str) -> None: ...
    def move(self, src: str, dst: str) -> None: ...
    def list_dir(self, path: str) -> list[str]: ...
    def delete(self, path: str) -> None: ...

class DiscordClient(Protocol):
    async def send_embed(self, channel_name: str, embed: dict) -> dict[str, Any]: ...
    async def add_reaction(self, channel_id: str, message_id: str, emoji: str) -> None: ...
    async def await_reaction(self, channel_id: str, message_id: str, valid_emojis: list[str], timeout_seconds: int) -> dict | None: ...
```

**Verification:** Import from new location, run tests.

#### Step 1.3: Create `utils.py`

Consolidate utility functions:

**Source from:**
- `core.py` → `extract_json`, `clean_llm_output`, `infer_skill_name`, `parse_skill_frontmatter`, `format_skill_content`, `validate_test_case_yaml`, `ensure_test_cases_structure`
- `llm_service.py` → `clean_yaml_output`, `clean_markdown_output`

**Deduplicate:** Remove redundant implementations.

**Verification:** Unit tests for utility functions.

#### Step 1.4: Create consolidated `models.py`

Consolidate all data models and scoring:

**Source from:**
- `models.py` → All dataclasses (`EvalMetrics`, `SkillVersion`, `IterationResult`, etc.)
- `domain/scoring.py` → `compute_score`, `is_plateau`, `detect_regression`, constants
- `domain/decisions.py` → `should_continue_iteration`, `make_continue_decision`
- `domain/models.py` → `IterationContext`, `ContinueDecision`
- `llm_service.py` / `services/llm.py` → Pydantic models (`SkillSpec`, `OverlapAnalysis`, etc.)

**Structure:**
```python
# models.py

# --- Data Classes ---
@dataclass
class EvalMetrics: ...

@dataclass
class SkillVersion: ...

# ... other dataclasses

# --- Pydantic Models (for LLM structured output) ---
class SkillSpec(BaseModel): ...

class OverlapAnalysis(BaseModel): ...

# --- Scoring Functions ---
ACCURACY_WEIGHT = 0.7
# ... constants

def compute_score(metrics: EvalMetrics) -> float: ...

def is_plateau(history: list[IterationResult]) -> bool: ...

def detect_regression(history: list[IterationResult], current_score: float) -> dict: ...

# --- Decision Functions ---
def should_continue_iteration(ctx: IterationContext) -> tuple[bool, str]: ...
```

**Verification:** Run all existing tests, they should still pass.

---

### Phase 2: Create Capability Modules

Each capability module is self-contained with its prompts, logic, and a single public function.

#### Step 2.1: Create `capabilities/draft_skill.py`

**Source from:**
- `llm_service.py` → `LLMService.infer_skill()` method and prompt
- `services/llm.py` → Same (deduplicate)

**Target:**
```python
# capabilities/draft_skill.py
"""Draft a skill specification from a natural language description."""

from ..models import SkillSpec
from ..protocols import LLMClient
from ..utils import parse_json_response

SYSTEM_PROMPT = "You are a skill specification designer..."

USER_PROMPT_TEMPLATE = """Generate a complete skill specification...
{description}
{context_section}
"""

async def draft_skill(
    client: LLMClient,
    description: str,
    context: str | None = None,
) -> SkillSpec:
    """
    Draft a skill specification from a description.

    Args:
        client: LLM client for generation
        description: Natural language description of the skill
        context: Optional additional context

    Returns:
        SkillSpec with validated structure
    """
    context_section = f"\n\nADDITIONAL CONTEXT:\n{context}" if context else ""
    user_prompt = USER_PROMPT_TEMPLATE.format(
        description=description,
        context_section=context_section,
    )

    response = client.chat([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ])

    return parse_json_response(response["content"], SkillSpec)
```

**Verification:** Unit test with mock `LLMClient`.

#### Step 2.2: Create `capabilities/draft_test_cases.py`

**Source from:**
- `llm_service.py` → `LLMService.generate_test_cases()` method and prompt

**Target:**
```python
# capabilities/draft_test_cases.py
"""Generate test cases for a skill specification."""

async def draft_test_cases(
    client: LLMClient,
    spec: dict[str, Any],
    seed_tests: str | None = None,
) -> str:
    """Generate test cases YAML from skill specification."""
    ...
```

#### Step 2.3: Create `capabilities/detect_skill_overlap.py`

**Source from:**
- `llm_service.py` → `LLMService.detect_overlap()` method and prompt
- `core.py` → `create_no_overlap_result`, `parse_overlap_response`

**Target:**
```python
# capabilities/detect_skill_overlap.py
"""Detect if a new skill overlaps with existing skills."""

async def detect_skill_overlap(
    client: LLMClient,
    description: str,
    existing_skills: list[dict[str, Any]],
) -> OverlapResult:
    """Check if a new skill overlaps with existing ones."""
    ...
```

#### Step 2.4: Create `capabilities/evaluate_skill.py`

**Source from:**
- `eval_service.py` → `EvalService`, `results_to_metrics`, `extract_failing_tests`, `format_evaluation_feedback`

**Target:**
```python
# capabilities/evaluate_skill.py
"""Evaluate a skill against its test cases."""

def evaluate_skill(
    skill_path: str,
    llm_client: Any,
) -> tuple[EvalMetrics, str]:
    """
    Evaluate a skill and return metrics + feedback.

    Returns:
        Tuple of (metrics, formatted_feedback)
    """
    ...
```

#### Step 2.5: Create `capabilities/improve_skill.py`

**Source from:**
- `eval_service.py` → `ImproveService`
- `llm_service.py` → `LLMService.generate_improvement()` method and prompt

**Target:**
```python
# capabilities/improve_skill.py
"""Improve a skill based on evaluation feedback."""

async def improve_skill(
    client: LLMClient,
    skill_content: str,
    feedback: str,
) -> str:
    """Generate improved SKILL.md content based on feedback."""
    ...
```

#### Step 2.6: Create `capabilities/promote_skill.py`

**Source from:**
- `file_service.py` → `promote_skill`, `load_existing_skills`
- `promote.py` → Promotion workflow logic

**Target:**
```python
# capabilities/promote_skill.py
"""Promote a skill from development to production."""

def promote_skill(
    fs: FileSystem,
    skill_path: str,
    target_category: str,
    skills_root: str,
) -> dict[str, Any]:
    """Move skill from _development to production location."""
    ...

def load_existing_skills(
    fs: FileSystem,
    skills_path: str,
    include_development: bool = True,
) -> list[dict[str, Any]]:
    """Load metadata for all existing skills."""
    ...
```

---

### Phase 3: Create Temporal Layer

#### Step 3.1: Create `temporal/activities.py`

Thin wrappers that:
1. Create services from config
2. Call capability functions
3. Handle Temporal serialization

**Target:**
```python
# temporal/activities.py
"""Temporal activities - thin wrappers around capabilities."""

from temporalio import activity
from kubani.framework.config import get_config

from ..capabilities.draft_skill import draft_skill
from ..capabilities.evaluate_skill import evaluate_skill
# ... other imports


def _get_llm_client():
    """Create LLM client from config."""
    config = get_config()
    # Return configured client
    ...


@activity.defn
async def draft_skill_activity(description: str, context: str | None = None) -> dict:
    """Activity wrapper for draft_skill capability."""
    client = _get_llm_client()
    spec = await draft_skill(client, description, context)
    return spec.model_dump()


@activity.defn
async def evaluate_skill_activity(skill_path: str) -> dict:
    """Activity wrapper for evaluate_skill capability."""
    client = _get_llm_client()
    metrics, feedback = evaluate_skill(skill_path, client)
    return {
        "metrics": asdict(metrics),
        "feedback": feedback,
    }

# ... other activities
```

#### Step 3.2: Move `workflow.py` to `temporal/workflow.py`

Update imports to use new capability locations.

**Changes:**
- Import from `..capabilities.*` instead of sibling modules
- Import from `..models` instead of `.models`
- Simplify activity calls (cleaner interfaces)

#### Step 3.3: Move `worker.py` to `temporal/worker.py`

Update imports and registrations.

---

### Phase 4: Update Exports and Backward Compatibility

#### Step 4.1: Update root `__init__.py`

```python
# skill_auto/__init__.py
"""Skill Auto workflow - autonomous skill development."""

# Public API
from .models import (
    EvalMetrics,
    SkillVersion,
    IterationResult,
    SkillAutoInput,
    SkillAutoResult,
    SkillAutoState,
)

from .temporal.workflow import SkillAutoWorkflow
from .temporal.worker import create_worker

__all__ = [
    "EvalMetrics",
    "SkillVersion",
    "IterationResult",
    "SkillAutoInput",
    "SkillAutoResult",
    "SkillAutoState",
    "SkillAutoWorkflow",
    "create_worker",
]
```

#### Step 4.2: Add deprecation shims (if needed)

If external code imports from old locations, add temporary re-exports with deprecation warnings.

---

### Phase 5: Delete Old Code

Only after all tests pass with new structure.

#### Step 5.1: Delete duplicate files

```bash
rm kubani/workflows/skill_auto/core.py
rm kubani/workflows/skill_auto/llm_service.py
rm kubani/workflows/skill_auto/file_service.py
rm kubani/workflows/skill_auto/eval_service.py
rm -rf kubani/workflows/skill_auto/domain/
rm -rf kubani/workflows/skill_auto/services/
```

#### Step 5.2: Move remaining files

```bash
# Old workflow.py and worker.py should already be moved to temporal/
rm kubani/workflows/skill_auto/workflow.py  # if still exists
rm kubani/workflows/skill_auto/worker.py    # if still exists
```

#### Step 5.3: Update test imports

Update all test files to import from new locations.

---

### Phase 6: Final Cleanup

#### Step 6.1: Remove unused imports

Run `ruff check --fix` to clean up.

#### Step 6.2: Update documentation

- Update any references to old file locations
- Update CLAUDE.md if needed

#### Step 6.3: Final verification

```bash
just test
just lint
```

---

## Verification Checkpoints

After each phase, verify:

| Phase | Verification |
|-------|--------------|
| Phase 1 | `pytest kubani/workflows/skill_auto/tests/` passes |
| Phase 2 | Each capability has unit test, all pass |
| Phase 3 | Workflow integration tests pass |
| Phase 4 | All imports work, no warnings |
| Phase 5 | No references to deleted files |
| Phase 6 | `just ci` passes |

---

## Risk Mitigation

1. **Incremental approach** - Each phase is independently deployable
2. **Tests first** - Verify existing tests pass before each deletion
3. **Backward compatibility** - Add shims if external code depends on old paths
4. **Git history** - Use `git mv` where possible to preserve history

---

## Estimated Effort

| Phase | Effort |
|-------|--------|
| Phase 1: Create structure | ~2 hours |
| Phase 2: Capability modules | ~3 hours |
| Phase 3: Temporal layer | ~2 hours |
| Phase 4: Exports | ~1 hour |
| Phase 5: Delete old code | ~30 min |
| Phase 6: Cleanup | ~30 min |

**Total: ~9 hours**

---

## Success Criteria

- [ ] All existing tests pass
- [ ] Line count reduced by ~50%
- [ ] Each capability is independently testable
- [ ] No Temporal imports in `capabilities/`
- [ ] Clear, self-documenting file names
- [ ] `just ci` passes
