# Skill Auto Code Quality Improvements

## Overview

Analysis of `kubani/workflows/skill_auto/` to identify simplification and quality improvement opportunities.

**Current State:** ~5,000+ lines across 16+ Python files
**Goal:** Simple, elegant, minimal code that is easy to test and navigate

---

## Executive Summary

The codebase has grown organically and accumulated significant duplication and over-engineering. The core issues are:

1. **Same code in multiple places** - Scoring functions appear 3 times, LLM service appears twice
2. **Premature abstraction** - `domain/` and `services/` subdirectories add complexity without clear benefit
3. **Verbose boilerplate** - Activities file is 851 lines of mostly thin wrappers
4. **Manual implementations** - Hand-rolled JSON extraction when libraries exist

**Estimated reduction potential:** 40-50% fewer lines while improving clarity.

---

## Issue 1: Massive Duplication

### Scoring Functions (3 copies!)

The same `compute_score`, `is_plateau`, `detect_regression` functions exist in:
- `models.py` (lines 150-261)
- `core.py` (lines 143-266)
- `domain/scoring.py` (lines 18-158)

**Recommendation:** Single source of truth in `domain/scoring.py`, delete other copies.

### LLM Service (2 implementations!)

Nearly identical LLM services:
- `llm_service.py` (536 lines) - Creates OpenAI client in constructor
- `services/llm.py` (400 lines) - Takes client via dependency injection

Both have:
- Same Pydantic models (`InputParam`, `OutputField`, `SkillExample`, `SkillSpec`, `OverlapAnalysis`)
- Same `_call_llm` and `_parse_json_response` methods
- Same prompt templates
- Same `clean_yaml_output` and `clean_markdown_output` helpers

**Recommendation:** Keep only `services/llm.py` (the DI version is more testable). Delete `llm_service.py`.

### Protocol Definitions (2 places)

- `file_service.py` has `FileServiceProtocol`
- `services/protocols.py` has `FileSystem` (same thing, different name)

**Recommendation:** Single protocols module with consistent naming.

---

## Issue 2: Over-Engineering

### Unnecessary `domain/` Directory

Current state:
```
domain/
├── __init__.py (326 lines of re-exports)
├── models.py (98 lines) - Just re-exports from ../models.py + 2 tiny classes
├── scoring.py (171 lines) - Duplicate of code in models.py
└── decisions.py (81 lines) - 2 pure functions
```

The `domain/models.py` is almost entirely re-exports:
```python
# Import existing models to re-export for convenience
from ..models import (
    EvalMetrics, IterationResult, OverlapResult, ...
)
```

Only 2 new models (`IterationContext`, `ContinueDecision`) are defined.

**Recommendation Options:**
- **A) Flatten:** Move `IterationContext`, `ContinueDecision` to `models.py`, delete `domain/`
- **B) Commit:** Move ALL models to `domain/`, make it the single source

### Unnecessary `services/` Directory

Current state:
```
services/
├── __init__.py
├── protocols.py (175 lines) - Protocol definitions
└── llm.py (400 lines) - Duplicate of llm_service.py
```

This creates confusion about where code belongs.

**Recommendation:** Either commit to services pattern everywhere or flatten.

---

## Issue 3: Verbose Activity Wrappers

`activities.py` is **851 lines** but most activities are thin wrappers that:
1. Create a service from config
2. Call through to the service method
3. Close the service

Example pattern repeated 15+ times:
```python
@activity.defn
async def some_activity(args...):
    llm = _get_llm_service()
    try:
        return await some_function(llm, args...)
    finally:
        await llm.close()
```

### Massive Boilerplate for Dict Handling

Activities like `save_iteration_result` spend 40+ lines handling both dict and dataclass inputs:
```python
iteration = (
    iteration_result.iteration
    if hasattr(iteration_result, "iteration")
    else iteration_result.get("iteration", 0)
)
# ... repeated for every field
```

**Recommendations:**
1. Use `dataclasses.asdict()` for consistent serialization
2. Create a single `_from_dict_or_obj(data, field, default)` helper
3. Consider using Temporal's built-in dataclass converter

---

## Issue 4: Manual Implementations vs Libraries

### JSON Extraction (55 lines of hand-rolled code)

`core.py` has a 55-line `extract_json()` function with manual brace counting:
```python
depth = 0
in_string = False
escape_next = False
for i, char in enumerate(text[start:], start=start):
    # ... manual parsing
```

**Recommendations:**
- Use `json-repair` library for LLM output (handles malformed JSON)
- Or use `demjson3` which is tolerant of JSON5/JavaScript syntax
- Or use regex to find JSON block + `json.loads` (simpler fallback)

### Output Cleaning (duplicated)

`clean_yaml_output` and `clean_markdown_output` appear in both:
- `llm_service.py`
- `services/llm.py`

**Recommendation:** Single location, possibly use `strip_markdown` library.

---

## Issue 5: Inconsistent Patterns

### Async Methods That Don't Need Async

Several methods are `async def` but don't await anything:
```python
async def close(self) -> None:
    """Close the service (no-op, but maintains interface)."""
    pass
```

This creates confusion and forces callers to await unnecessarily.

### Mixed Protocol Usage

Some places use Protocols for DI, others create instances directly:
- `LLMService` in `llm_service.py` creates OpenAI client internally
- `LLMService` in `services/llm.py` accepts client via protocol

**Recommendation:** Consistent DI pattern everywhere.

---

## Proposed Improvements (By Priority)

### High Impact / Low Risk

| Change | Lines Saved | Benefit |
|--------|-------------|---------|
| Delete duplicate scoring functions | ~200 | Single source of truth |
| Delete `llm_service.py` (keep `services/llm.py`) | ~500 | Eliminate duplication |
| Consolidate protocols to one file | ~100 | Clearer organization |
| Add dict helper for activities | ~150 | Less boilerplate |

**Estimated total: ~950 lines saved**

### Medium Impact / Medium Risk

| Change | Lines Saved | Benefit |
|--------|-------------|---------|
| Flatten `domain/` directory | ~200 | Simpler structure |
| Use json-repair library | ~50 | More robust, less code |
| Unify Pydantic models location | ~100 | Single definition |

### Architectural Options

**Option A: Flatten Structure**
```
skill_auto/
├── models.py       # All data models + Pydantic schemas
├── scoring.py      # Pure scoring functions
├── decisions.py    # Pure decision functions
├── protocols.py    # All protocol definitions
├── services/
│   ├── llm.py      # LLM service (DI)
│   ├── file.py     # File service (DI)
│   └── eval.py     # Eval service (DI)
├── activities.py   # Temporal activities (thin)
├── workflow.py     # Temporal workflow
└── worker.py       # Temporal worker
```

**Option B: Full Domain-Driven**
```
skill_auto/
├── domain/
│   ├── models.py   # All pure data models
│   ├── scoring.py  # Pure functions
│   └── decisions.py
├── services/
│   ├── protocols.py
│   ├── llm.py
│   ├── file.py
│   └── eval.py
├── infrastructure/
│   ├── activities.py
│   ├── workflow.py
│   └── worker.py
└── __init__.py
```

**Option C: Minimal (Recommended)**
```
skill_auto/
├── models.py       # Data models, scoring, decisions (~400 lines)
├── protocols.py    # All protocols (~150 lines)
├── llm.py          # LLM service (~300 lines)
├── files.py        # File operations (~200 lines)
├── eval.py         # Evaluation (~150 lines)
├── activities.py   # Temporal activities (~400 lines)
├── workflow.py     # Temporal workflow (~400 lines)
├── promote.py      # Promotion workflow (~190 lines)
├── worker.py       # Worker (~120 lines)
└── __init__.py     # Exports (~50 lines)
```

Total: ~2,360 lines (vs current ~5,000+)

---

## Quick Wins (Can Do Now)

1. **Delete `domain/models.py`** - It's just re-exports
2. **Delete `core.py` scoring functions** - Keep only in `domain/scoring.py`
3. **Delete `models.py` scoring functions** - Use `domain/scoring.py`
4. **Add `_get_value(data, field, default)` helper** to activities.py

---

## Testing Improvements

Current test structure mirrors the duplicated code structure. With simplification:

1. **Unit tests for pure functions** - `scoring.py`, `decisions.py` (fast, no mocking)
2. **Service tests with mock protocols** - `llm.py`, `files.py` (protocol-based DI)
3. **Integration tests** - workflow with mock activities

The DI approach in `services/llm.py` is already testable:
```python
class MockLLMClient:
    def chat(self, messages, **kwargs):
        return {"content": '{"name": "test"}'}

service = LLMService(MockLLMClient())
# Test without real LLM calls
```

---

## Chosen Direction: Option D3 (Activity-Based with Temporal Separation)

After discussion, we chose an **activity-based organization** that:
- Groups code by capability (what it does) rather than by layer (what type it is)
- Separates pure business logic from Temporal infrastructure
- Uses explicit, self-documenting file names

### Final Structure

```
skill_auto/
├── capabilities/              # Pure business logic (no Temporal)
│   ├── draft_skill.py
│   ├── draft_test_cases.py
│   ├── detect_skill_overlap.py
│   ├── evaluate_skill.py
│   ├── improve_skill.py
│   └── promote_skill.py
│
├── temporal/                  # Temporal-specific code
│   ├── workflow.py
│   ├── activities.py
│   └── worker.py
│
├── models.py                  # Shared data models
├── protocols.py               # Shared protocols (LLMClient, FileSystem)
└── utils.py                   # Shared utilities (JSON extraction, output cleaning)
```

### Why This Approach

| Benefit | Explanation |
|---------|-------------|
| **Self-documenting** | File names tell you exactly what they do |
| **Easy to understand** | To understand "how evaluation works", read one file |
| **Framework-agnostic core** | `capabilities/` has no Temporal dependency, easy to test |
| **Easy to extend** | Adding a new capability = adding one file |
| **Clear boundaries** | Business logic vs infrastructure clearly separated |

### Import Examples

```python
from skill_auto.capabilities.draft_skill import draft_skill
from skill_auto.capabilities.evaluate_skill import evaluate_skill
from skill_auto.models import EvalMetrics, SkillVersion
from skill_auto.protocols import LLMClient
```

---

## Next Steps

See implementation plan: [2026-01-26-skill-auto-refactor-plan.md](../drafts/2026-01-26-skill-auto-refactor-plan.md)
