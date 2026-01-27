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

## Target Test Structure

```
skill_auto/tests/
├── __init__.py
├── conftest.py                      # Shared fixtures (mock clients, etc.)
│
├── capabilities/                    # Unit tests for each capability
│   ├── __init__.py
│   ├── test_draft_skill.py
│   ├── test_draft_test_cases.py
│   ├── test_detect_skill_overlap.py
│   ├── test_evaluate_skill.py
│   ├── test_improve_skill.py
│   └── test_promote_skill.py
│
├── temporal/                        # Temporal-specific tests
│   ├── __init__.py
│   ├── test_activities.py
│   └── test_workflow.py
│
├── test_models.py                   # Model and scoring tests
├── test_utils.py                    # Utility function tests
└── test_e2e.py                      # End-to-end integration tests
```

### Current Tests to Migrate

| Current Test File | Target Location | Action |
|-------------------|-----------------|--------|
| `test_core.py` | `test_utils.py` | Migrate utility tests |
| `test_llm_service.py` | `capabilities/test_draft_skill.py`, etc. | Split by capability |
| `test_file_service.py` | `capabilities/test_promote_skill.py` | Migrate file ops tests |
| `test_eval_service.py` | `capabilities/test_evaluate_skill.py` | Migrate |
| `test_activities.py` | `temporal/test_activities.py` | Migrate |
| `test_workflow.py` | `temporal/test_workflow.py` | Migrate |
| `test_e2e.py` | `test_e2e.py` | Keep at root |
| `domain/test_decisions.py` | `test_models.py` | Merge into models tests |
| `services/test_llm_service.py` | Delete | Duplicate of `test_llm_service.py` |

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

**Tests:** No new tests needed - protocols are tested via implementations.

#### Step 1.3: Create `utils.py`

Consolidate utility functions:

**Source from:**
- `core.py` → `extract_json`, `clean_llm_output`, `infer_skill_name`, `parse_skill_frontmatter`, `format_skill_content`, `validate_test_case_yaml`, `ensure_test_cases_structure`
- `llm_service.py` → `clean_yaml_output`, `clean_markdown_output`

**Deduplicate:** Remove redundant implementations.

**Verification:** Unit tests for utility functions.

**Tests - Create `tests/test_utils.py`:**
```python
# tests/test_utils.py
"""Tests for utility functions."""

import pytest
from skill_auto.utils import (
    extract_json,
    clean_llm_output,
    clean_yaml_output,
    clean_markdown_output,
    parse_skill_frontmatter,
    validate_test_case_yaml,
)

class TestExtractJson:
    def test_extracts_json_from_markdown_block(self):
        text = '```json\n{"key": "value"}\n```'
        assert extract_json(text) == {"key": "value"}

    def test_extracts_json_with_surrounding_text(self):
        text = 'Here is the result: {"key": "value"} and more text'
        assert extract_json(text) == {"key": "value"}

    def test_raises_on_no_json(self):
        with pytest.raises(ValueError):
            extract_json("no json here")

class TestCleanYamlOutput:
    def test_removes_code_blocks(self):
        text = "```yaml\nkey: value\n```"
        assert clean_yaml_output(text) == "key: value"

    def test_removes_thinking_tags(self):
        text = "<think>thinking...</think>\nkey: value"
        assert clean_yaml_output(text) == "key: value"

# ... more tests migrated from test_core.py
```

**Migrate from:** `test_core.py` (JSON extraction, validation tests)

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

**Tests - Create `tests/test_models.py`:**
```python
# tests/test_models.py
"""Tests for data models and scoring functions."""

import pytest
from skill_auto.models import (
    EvalMetrics,
    IterationResult,
    IterationContext,
    compute_score,
    is_plateau,
    detect_regression,
    should_continue_iteration,
)

class TestComputeScore:
    def test_perfect_score(self):
        metrics = EvalMetrics(accuracy=1.0, latency_ms=100, ...)
        assert compute_score(metrics) == pytest.approx(1.0, rel=0.01)

    def test_accuracy_weighted_higher(self):
        # Accuracy contributes 70%, latency 30%
        ...

class TestIsPlateau:
    def test_detects_plateau_when_no_improvement(self):
        history = [...]  # scores: 0.8, 0.801, 0.802
        assert is_plateau(history) is True

    def test_not_plateau_with_significant_improvement(self):
        history = [...]  # scores: 0.8, 0.85, 0.9
        assert is_plateau(history) is False

class TestShouldContinueIteration:
    def test_stops_when_cancelled(self):
        ctx = IterationContext(is_cancelled=True, ...)
        should_continue, reason = should_continue_iteration(ctx)
        assert should_continue is False
        assert reason == "cancelled"

    def test_stops_at_max_iterations(self):
        ctx = IterationContext(current_iteration=10, max_iterations=10, ...)
        should_continue, reason = should_continue_iteration(ctx)
        assert should_continue is False
        assert reason == "max_iterations_reached"

# ... more tests migrated from domain/test_decisions.py
```

**Migrate from:** `domain/test_decisions.py`, scoring tests from `test_core.py`

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

**Tests - Create `tests/capabilities/test_draft_skill.py`:**
```python
# tests/capabilities/test_draft_skill.py
"""Tests for draft_skill capability."""

import pytest
from skill_auto.capabilities.draft_skill import draft_skill
from skill_auto.models import SkillSpec

class MockLLMClient:
    """Mock LLM client that returns valid skill spec JSON."""

    def __init__(self, response: str):
        self.response = response
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append(messages)
        return {"content": self.response}

VALID_SKILL_SPEC_JSON = '''{
    "name": "test-skill",
    "description": "A test skill",
    "inputs": {"query": {"type": "string", "description": "Input query", "required": true}},
    "outputs": {"result": {"type": "string", "description": "Output result"}},
    "steps": ["Step 1", "Step 2"],
    "error_handling": ["Handle errors gracefully"],
    "examples": []
}'''

class TestDraftSkill:
    @pytest.mark.asyncio
    async def test_returns_valid_skill_spec(self):
        client = MockLLMClient(VALID_SKILL_SPEC_JSON)
        result = await draft_skill(client, "Create a skill that does X")

        assert isinstance(result, SkillSpec)
        assert result.name == "test-skill"
        assert "query" in result.inputs

    @pytest.mark.asyncio
    async def test_includes_context_in_prompt(self):
        client = MockLLMClient(VALID_SKILL_SPEC_JSON)
        await draft_skill(client, "Do X", context="Extra context here")

        # Verify context was included in the prompt
        user_message = client.calls[0][1]["content"]
        assert "Extra context here" in user_message

    @pytest.mark.asyncio
    async def test_raises_on_invalid_json(self):
        client = MockLLMClient("not valid json")
        with pytest.raises(ValueError):
            await draft_skill(client, "Create a skill")
```

**Migrate from:** `test_llm_service.py` (infer_skill tests)

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

**Tests - Create `tests/capabilities/test_draft_test_cases.py`:**
```python
class TestDraftTestCases:
    @pytest.mark.asyncio
    async def test_returns_valid_yaml(self):
        client = MockLLMClient(VALID_TEST_CASES_YAML)
        result = await draft_test_cases(client, {"name": "test-skill", ...})

        # Should be valid YAML
        import yaml
        parsed = yaml.safe_load(result)
        assert "test_cases" in parsed

    @pytest.mark.asyncio
    async def test_includes_seed_tests_in_prompt(self):
        client = MockLLMClient(VALID_TEST_CASES_YAML)
        await draft_test_cases(client, spec, seed_tests="existing: tests")

        user_message = client.calls[0][1]["content"]
        assert "existing: tests" in user_message
```

**Migrate from:** `test_llm_service.py` (generate_test_cases tests)

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

**Tests - Create `tests/capabilities/test_detect_skill_overlap.py`:**
```python
class TestDetectSkillOverlap:
    @pytest.mark.asyncio
    async def test_returns_no_overlap_for_empty_skills(self):
        client = MockLLMClient("{}")  # Won't be called
        result = await detect_skill_overlap(client, "new skill", [])

        assert result.has_overlap is False
        assert result.recommendation == "proceed"

    @pytest.mark.asyncio
    async def test_detects_overlap(self):
        response = '{"has_overlap": true, "overlapping_skills": ["existing-skill"], ...}'
        client = MockLLMClient(response)
        result = await detect_skill_overlap(client, "similar skill", [{"name": "existing-skill"}])

        assert result.has_overlap is True
        assert "existing-skill" in result.overlapping_skills
```

**Migrate from:** `test_llm_service.py` (detect_overlap tests)

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

**Tests - Create `tests/capabilities/test_evaluate_skill.py`:**
```python
class TestEvaluateSkill:
    def test_returns_metrics_and_feedback(self, tmp_path):
        # Create a mock skill directory
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: test\n---\n# Test")
        (skill_dir / "test_cases.yaml").write_text("test_cases: []")

        client = MockLLMClient(...)
        metrics, feedback = evaluate_skill(str(skill_dir), client)

        assert isinstance(metrics, EvalMetrics)
        assert isinstance(feedback, str)

    def test_calculates_accuracy_correctly(self, tmp_path):
        # Test with known pass/fail results
        ...

class TestResultsToMetrics:
    def test_converts_percentage_to_fraction(self):
        raw = {"metrics": {"accuracy": 85.0, ...}}
        metrics = results_to_metrics(raw)
        assert metrics.accuracy == 0.85  # Not 85.0

class TestFormatEvaluationFeedback:
    def test_includes_failing_tests(self):
        raw = {"test_results": [{"name": "test1", "passed": False, "error": "failed"}]}
        feedback = format_evaluation_feedback(raw)
        assert "test1" in feedback
        assert "failed" in feedback
```

**Migrate from:** `test_eval_service.py`

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

**Tests - Create `tests/capabilities/test_improve_skill.py`:**
```python
class TestImproveSkill:
    @pytest.mark.asyncio
    async def test_returns_improved_content(self):
        improved_content = "---\nname: improved\n---\n# Improved Skill"
        client = MockLLMClient(improved_content)

        result = await improve_skill(
            client,
            skill_content="---\nname: original\n---\n# Original",
            feedback="Needs better error handling",
        )

        assert "improved" in result.lower() or result == improved_content

    @pytest.mark.asyncio
    async def test_includes_feedback_in_prompt(self):
        client = MockLLMClient("improved content")
        await improve_skill(client, "content", "specific feedback here")

        user_message = client.calls[0][1]["content"]
        assert "specific feedback here" in user_message
```

**Migrate from:** `test_eval_service.py` (ImproveService tests), `test_llm_service.py`

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

**Tests - Create `tests/capabilities/test_promote_skill.py`:**
```python
class MockFileSystem:
    """In-memory filesystem for testing."""

    def __init__(self):
        self.files: dict[str, str] = {}
        self.dirs: set[str] = set()

    def read(self, path: str) -> str:
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]

    def write(self, path: str, content: str) -> None:
        self.files[path] = content

    def exists(self, path: str) -> bool:
        return path in self.files or path in self.dirs

    def mkdir(self, path: str) -> None:
        self.dirs.add(path)

    def move(self, src: str, dst: str) -> None:
        # Move all files with src prefix to dst prefix
        ...

    def list_files(self, path: str, pattern: str) -> list[str]:
        ...


class TestPromoteSkill:
    def test_moves_skill_to_target_category(self):
        fs = MockFileSystem()
        fs.files["dev/test-skill/SKILL.md"] = "content"
        fs.files["dev/test-skill/metadata.json"] = '{"status": "development"}'

        result = promote_skill(fs, "dev/test-skill", "general", "skills")

        assert result["success"] is True
        assert result["promoted_path"] == "skills/general/test-skill"
        assert "skills/general/test-skill/SKILL.md" in fs.files

    def test_updates_metadata_status(self):
        fs = MockFileSystem()
        fs.files["dev/test-skill/SKILL.md"] = "content"
        fs.files["dev/test-skill/metadata.json"] = '{"status": "development"}'

        promote_skill(fs, "dev/test-skill", "general", "skills")

        metadata = json.loads(fs.files["skills/general/test-skill/metadata.json"])
        assert metadata["status"] == "production"


class TestLoadExistingSkills:
    def test_loads_skills_from_directory(self):
        fs = MockFileSystem()
        fs.files["skills/general/skill1/SKILL.md"] = "---\nname: skill1\ndescription: First\n---"
        fs.files["skills/general/skill2/SKILL.md"] = "---\nname: skill2\ndescription: Second\n---"

        skills = load_existing_skills(fs, "skills")

        assert len(skills) == 2
        assert any(s["name"] == "skill1" for s in skills)

    def test_excludes_development_when_requested(self):
        fs = MockFileSystem()
        fs.files["skills/_development/wip/SKILL.md"] = "---\nname: wip\n---"
        fs.files["skills/general/prod/SKILL.md"] = "---\nname: prod\n---"

        skills = load_existing_skills(fs, "skills", include_development=False)

        assert len(skills) == 1
        assert skills[0]["name"] == "prod"
```

**Migrate from:** `test_file_service.py`

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

**Tests - Create `tests/temporal/test_activities.py`:**
```python
# tests/temporal/test_activities.py
"""Tests for Temporal activities."""

import pytest
from unittest.mock import patch, MagicMock

class TestDraftSkillActivity:
    @pytest.mark.asyncio
    async def test_calls_capability_and_returns_dict(self):
        with patch("skill_auto.temporal.activities._get_llm_client") as mock_client:
            with patch("skill_auto.temporal.activities.draft_skill") as mock_draft:
                mock_draft.return_value = MagicMock(model_dump=lambda: {"name": "test"})

                from skill_auto.temporal.activities import draft_skill_activity
                result = await draft_skill_activity("description")

                assert result == {"name": "test"}
                mock_draft.assert_called_once()


class TestEvaluateSkillActivity:
    @pytest.mark.asyncio
    async def test_returns_metrics_as_dict(self):
        # Verify serialization for Temporal
        ...
```

**Migrate from:** `test_activities.py`

#### Step 3.2: Move `workflow.py` to `temporal/workflow.py`

Update imports to use new capability locations.

**Changes:**
- Import from `..capabilities.*` instead of sibling modules
- Import from `..models` instead of `.models`
- Simplify activity calls (cleaner interfaces)

**Tests - Update `tests/temporal/test_workflow.py`:**
```python
# tests/temporal/test_workflow.py
"""Tests for SkillAutoWorkflow."""

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from skill_auto.temporal.workflow import SkillAutoWorkflow
from skill_auto.models import SkillAutoInput

class TestSkillAutoWorkflow:
    @pytest.mark.asyncio
    async def test_workflow_create_mode(self):
        async with await WorkflowEnvironment.start_local() as env:
            # Test with mocked activities
            ...

    @pytest.mark.asyncio
    async def test_workflow_stops_on_target_accuracy(self):
        ...

    @pytest.mark.asyncio
    async def test_workflow_handles_cancellation(self):
        ...
```

**Migrate from:** `test_workflow.py`

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

### Phase 5: Delete Old Code and Tests

Only after all tests pass with new structure.

#### Step 5.1: Delete duplicate source files

```bash
rm kubani/workflows/skill_auto/core.py
rm kubani/workflows/skill_auto/llm_service.py
rm kubani/workflows/skill_auto/file_service.py
rm kubani/workflows/skill_auto/eval_service.py
rm -rf kubani/workflows/skill_auto/domain/
rm -rf kubani/workflows/skill_auto/services/
```

#### Step 5.2: Delete old test files

```bash
# Tests that have been migrated to new locations
rm kubani/workflows/skill_auto/tests/test_core.py           # → test_utils.py, test_models.py
rm kubani/workflows/skill_auto/tests/test_llm_service.py    # → capabilities/test_*.py
rm kubani/workflows/skill_auto/tests/test_file_service.py   # → capabilities/test_promote_skill.py
rm kubani/workflows/skill_auto/tests/test_eval_service.py   # → capabilities/test_evaluate_skill.py
rm kubani/workflows/skill_auto/tests/test_activities.py     # → temporal/test_activities.py
rm kubani/workflows/skill_auto/tests/test_workflow.py       # → temporal/test_workflow.py

# Delete duplicate test directories
rm -rf kubani/workflows/skill_auto/tests/domain/            # → test_models.py
rm -rf kubani/workflows/skill_auto/tests/services/          # Duplicate tests
```

#### Step 5.3: Move remaining source files

```bash
# Old workflow.py and worker.py should already be moved to temporal/
rm kubani/workflows/skill_auto/workflow.py  # if still exists
rm kubani/workflows/skill_auto/worker.py    # if still exists
```

#### Step 5.4: Verify no orphaned imports

```bash
# Check for any imports of deleted modules
grep -r "from.*core import" kubani/workflows/skill_auto/
grep -r "from.*llm_service import" kubani/workflows/skill_auto/
grep -r "from.*file_service import" kubani/workflows/skill_auto/
grep -r "from.*eval_service import" kubani/workflows/skill_auto/
grep -r "from.*domain" kubani/workflows/skill_auto/
grep -r "from.*services" kubani/workflows/skill_auto/
```

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
| Phase 1 | `pytest kubani/workflows/skill_auto/tests/` passes (existing tests still work) |
| Phase 2 | New capability tests pass: `pytest kubani/workflows/skill_auto/tests/capabilities/` |
| Phase 3 | Temporal tests pass: `pytest kubani/workflows/skill_auto/tests/temporal/` |
| Phase 4 | All imports work, no warnings |
| Phase 5 | No references to deleted files, no orphaned tests |
| Phase 6 | `just ci` passes, test coverage maintained |

### Test Commands Per Phase

```bash
# Phase 1: Verify existing tests still pass
pytest kubani/workflows/skill_auto/tests/ -v

# Phase 2: Run new capability tests
pytest kubani/workflows/skill_auto/tests/capabilities/ -v
pytest kubani/workflows/skill_auto/tests/test_models.py -v
pytest kubani/workflows/skill_auto/tests/test_utils.py -v

# Phase 3: Run temporal tests
pytest kubani/workflows/skill_auto/tests/temporal/ -v

# Phase 5: Verify no broken imports in tests
pytest kubani/workflows/skill_auto/tests/ --collect-only

# Phase 6: Full test suite with coverage
pytest kubani/workflows/skill_auto/tests/ -v --cov=kubani/workflows/skill_auto --cov-report=term-missing
```

---

## Risk Mitigation

1. **Incremental approach** - Each phase is independently deployable
2. **Tests first** - Verify existing tests pass before each deletion
3. **Backward compatibility** - Add shims if external code depends on old paths
4. **Git history** - Use `git mv` where possible to preserve history

---

## Estimated Effort

| Phase | Code | Tests | Total |
|-------|------|-------|-------|
| Phase 1: Create structure | ~1.5 hours | ~1 hour | ~2.5 hours |
| Phase 2: Capability modules | ~2 hours | ~2 hours | ~4 hours |
| Phase 3: Temporal layer | ~1.5 hours | ~1 hour | ~2.5 hours |
| Phase 4: Exports | ~30 min | ~15 min | ~45 min |
| Phase 5: Delete old code/tests | ~30 min | ~30 min | ~1 hour |
| Phase 6: Cleanup | ~30 min | ~15 min | ~45 min |

**Total: ~11.5 hours** (includes comprehensive test migration)

---

## Shared Test Fixtures

Update `tests/conftest.py` with reusable fixtures:

```python
# tests/conftest.py
"""Shared test fixtures for skill_auto tests."""

import pytest
from typing import Any

class MockLLMClient:
    """Mock LLM client for testing capabilities."""

    def __init__(self, responses: list[str] | str = "{}"):
        self.responses = [responses] if isinstance(responses, str) else responses
        self.call_index = 0
        self.calls: list[list[dict]] = []

    def chat(self, messages: list[dict[str, str]], **kwargs) -> dict[str, Any]:
        self.calls.append(messages)
        response = self.responses[min(self.call_index, len(self.responses) - 1)]
        self.call_index += 1
        return {"content": response}


class MockFileSystem:
    """In-memory filesystem for testing."""

    def __init__(self, files: dict[str, str] | None = None):
        self.files: dict[str, str] = files or {}
        self.dirs: set[str] = set()

    def read(self, path: str) -> str:
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]

    def write(self, path: str, content: str) -> None:
        self.files[path] = content

    def exists(self, path: str) -> bool:
        return path in self.files or path in self.dirs

    def mkdir(self, path: str) -> None:
        self.dirs.add(path)

    def list_files(self, path: str, pattern: str) -> list[str]:
        import fnmatch
        return [p for p in self.files.keys() if fnmatch.fnmatch(p, f"{path}/{pattern}")]

    def move(self, src: str, dst: str) -> None:
        to_move = [(k, v) for k, v in self.files.items() if k.startswith(src)]
        for old_path, content in to_move:
            new_path = old_path.replace(src, dst, 1)
            self.files[new_path] = content
            del self.files[old_path]

    def copy(self, src: str, dst: str) -> None:
        self.files[dst] = self.files[src]

    def delete(self, path: str) -> None:
        self.files.pop(path, None)

    def list_dir(self, path: str) -> list[str]:
        import os
        return list(set(
            os.path.basename(p.replace(path + "/", "").split("/")[0])
            for p in self.files.keys()
            if p.startswith(path + "/")
        ))


@pytest.fixture
def mock_llm_client():
    """Factory fixture for creating mock LLM clients."""
    def _create(responses: list[str] | str = "{}"):
        return MockLLMClient(responses)
    return _create


@pytest.fixture
def mock_filesystem():
    """Factory fixture for creating mock filesystems."""
    def _create(files: dict[str, str] | None = None):
        return MockFileSystem(files)
    return _create
```

---

## Success Criteria

### Code Quality
- [ ] Line count reduced by ~50% (5000+ → ~2200)
- [ ] Each capability is independently testable
- [ ] No Temporal imports in `capabilities/`
- [ ] Clear, self-documenting file names
- [ ] No duplicate code across files

### Test Quality
- [ ] All existing test scenarios covered in new structure
- [ ] Each capability has dedicated test file
- [ ] Tests use mock protocols (no real LLM/filesystem calls in unit tests)
- [ ] Test coverage maintained or improved
- [ ] No orphaned test files

### CI/CD
- [ ] `just ci` passes
- [ ] `pytest kubani/workflows/skill_auto/tests/` passes
- [ ] No import warnings or deprecation notices
