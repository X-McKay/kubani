# Skill Auto Workflow Testability Refactor

**Date:** 2026-01-25
**Status:** Completed
**Author:** Claude (with user collaboration)

---

## Overview

Refactor the skill_auto workflow to enable isolated unit testing of each component. The current 1,300-line `activities.py` mixes LLM calls, file I/O, and business logic, making it hard to test without running the full Temporal workflow.

## Goals

1. Test business logic (JSON extraction, scoring, validation) without any mocks
2. Test LLM interactions with only HTTP mocking
3. Test file operations with in-memory mock filesystem
4. Test Temporal workflow with sandbox environment
5. Fast feedback loop - core tests run in <1 second

## Architecture

### New Module Structure

```
kubani/workflows/skill_auto/
├── __init__.py
├── core.py              # Pure functions (no I/O)
├── llm_service.py       # LLM interaction layer
├── file_service.py      # Filesystem operations
├── eval_service.py      # Evaluation wrapper
├── activities.py        # Thin Temporal wrappers
├── workflow.py          # Orchestration (unchanged)
├── models.py            # Data models (unchanged)
├── worker.py            # Worker entry (unchanged)
├── promote.py           # Promotion workflow (unchanged)
└── tests/
    ├── __init__.py
    ├── conftest.py          # Shared fixtures
    ├── test_core.py         # Pure function tests
    ├── test_llm_service.py  # LLM with mock HTTP
    ├── test_file_service.py # File with mock FS
    ├── test_eval_service.py # Eval with mock evaluator
    ├── test_activities.py   # Activities with mocked services
    └── test_workflow.py     # Temporal sandbox tests
```

### Module Responsibilities

#### core.py - Pure Functions

No I/O dependencies. Testable instantly.

- `extract_json(text: str) -> dict` - Robust JSON extraction with brace counting
- `compute_score(metrics: EvalMetrics) -> float` - Composite scoring
- `is_plateau(history: list) -> bool` - Plateau detection
- `detect_regression(history: list, score: float) -> dict` - Regression check
- `infer_skill_name(description: str) -> str` - Name derivation
- `parse_skill_frontmatter(content: str) -> dict` - YAML frontmatter parsing
- `format_skill_content(spec: dict) -> str` - SKILL.md generation
- `validate_test_case_yaml(yaml_str: str) -> tuple[bool, str]` - YAML validation

#### llm_service.py - LLM Interaction

Protocol-based for easy mocking.

```python
class LLMServiceProtocol(Protocol):
    async def chat(self, messages: list[dict], temperature: float = 0.7) -> str: ...

class LLMService:
    # Real implementation using httpx

async def infer_skill_structure(llm: LLMServiceProtocol, description: str) -> dict
async def detect_overlap(llm: LLMServiceProtocol, description: str, existing: list) -> OverlapResult
async def generate_test_cases(llm: LLMServiceProtocol, spec: dict) -> str
async def generate_harder_tests(llm: LLMServiceProtocol, ...) -> str
```

#### file_service.py - Filesystem Operations

Protocol-based for in-memory testing.

```python
class FileServiceProtocol(Protocol):
    def read(self, path: str) -> str: ...
    def write(self, path: str, content: str) -> None: ...
    def exists(self, path: str) -> bool: ...
    def mkdir(self, path: str) -> None: ...
    def list_files(self, path: str, pattern: str) -> list[str]: ...

class FileService:
    # Real implementation using pathlib

def load_existing_skills(fs: FileServiceProtocol, path: str) -> list[dict]
def write_skill_files(fs: FileServiceProtocol, spec: dict, tests: str, dir: str) -> dict
def save_iteration_result(fs: FileServiceProtocol, path: str, result: IterationResult) -> dict
```

#### eval_service.py - Evaluation Wrapper

Wraps existing SkillEvaluatorLLM and SkillImprover.

```python
class EvaluatorProtocol(Protocol):
    def evaluate_skill(self, skill_path: str) -> dict: ...

class ImproverProtocol(Protocol):
    def improve_skill(self, skill_path: str, feedback: str) -> dict: ...

class EvalService:
    # Wraps kubani_dev.skill_evaluator_llm.SkillEvaluatorLLM

def results_to_metrics(raw_result: dict) -> EvalMetrics
```

#### activities.py - Thin Wrappers

Activities become simple glue code:

```python
@activity.defn
async def activity_infer_skill_structure(description: str) -> dict:
    llm = _get_llm_service()
    return await infer_skill_structure(llm, description)
```

### Test Strategy

| Layer | What's Tested | Mocking Required | Speed |
|-------|---------------|------------------|-------|
| test_core.py | Pure logic | None | <1s |
| test_llm_service.py | LLM prompts/parsing | Mock LLM protocol | <1s |
| test_file_service.py | File operations | In-memory FS | <1s |
| test_eval_service.py | Eval result conversion | Mock evaluator | <1s |
| test_activities.py | Activity wiring | Mock services | <2s |
| test_workflow.py | Full orchestration | Temporal sandbox | ~10s |

### Known Bug Fix

The `_extract_json` function currently uses `text.rfind("}")` which fails on:
- Nested JSON objects
- Multiple JSON objects in response
- Trailing content after JSON

New implementation in `core.py` will use brace counting to find the first complete JSON object.

## Implementation Phases

### Phase 1: Core Module
- [ ] Create core.py with pure functions
- [ ] Implement robust extract_json with brace counting
- [ ] Move compute_score, is_plateau, detect_regression from models.py
- [ ] Add parse_skill_frontmatter, format_skill_content, validate_test_case_yaml
- [ ] Write test_core.py with comprehensive tests

### Phase 2: Service Layers
- [ ] Create llm_service.py with LLMServiceProtocol
- [ ] Create file_service.py with FileServiceProtocol
- [ ] Create eval_service.py wrapping existing evaluators
- [ ] Write tests for each service layer

### Phase 3: Refactor Activities
- [ ] Refactor activities.py to use service layers
- [ ] Remove duplicate code
- [ ] Write test_activities.py

### Phase 4: Workflow Tests
- [ ] Create test_workflow.py with Temporal sandbox
- [ ] Test key workflow scenarios (success, plateau, regression)

### Phase 5: Verify End-to-End
- [ ] Run full workflow with real LLM
- [ ] Verify all bugs are fixed
- [ ] Clean up any remaining issues

## Success Criteria

1. `pytest test_core.py` runs in <1 second
2. All pure logic tests pass without any mocking
3. The JSON extraction bug is fixed and tested
4. Full test coverage for scoring, plateau detection, regression detection
5. Temporal workflow tests pass in sandbox environment
