# Auto Mode Skill Development - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement autonomous skill development that chains create → eval → improve → repeat until quality goals are met.

**Architecture:** Temporal parent workflow orchestrates child workflows (Create, Eval, Improve, Promote) with activities for individual operations. CLI provides foreground streaming and background execution modes. Discord notifications for progress and approval gating.

**Tech Stack:** Temporal (workflows/activities), Click (CLI), LLMClient (skill operations), Discord MCP (notifications), Pydantic (data models)

---

## Phase 1: Core Data Models

### Task 1.1: Create Skill Auto Data Models

**Files:**
- Create: `kubani/workflows/skill_auto/models.py`
- Test: `tests/workflows/skill_auto/test_models.py`

**Step 1: Write the failing test**

```python
# tests/workflows/skill_auto/test_models.py
"""Tests for skill auto workflow data models."""

import pytest
from datetime import datetime


def test_skill_auto_input_defaults():
    """SkillAutoInput should have sensible defaults."""
    from kubani.workflows.skill_auto.models import SkillAutoInput

    input = SkillAutoInput(description="A skill that diagnoses OOM pods")

    assert input.description == "A skill that diagnoses OOM pods"
    assert input.mode == "create"
    assert input.max_iterations == 5
    assert input.target_accuracy == 0.80
    assert input.notify_channel == "skill-notifications"
    assert input.allow_overlap is False


def test_skill_auto_input_improve_mode():
    """SkillAutoInput should support improve mode with skill_path."""
    from kubani.workflows.skill_auto.models import SkillAutoInput

    input = SkillAutoInput(
        description="Improve existing skill",
        mode="improve",
        skill_path="kubani/skills/_development/oom-diagnostics",
    )

    assert input.mode == "improve"
    assert input.skill_path == "kubani/skills/_development/oom-diagnostics"


def test_skill_version_stores_content_and_metrics():
    """SkillVersion should store skill content and evaluation metrics."""
    from kubani.workflows.skill_auto.models import SkillVersion, EvalMetrics

    metrics = EvalMetrics(
        accuracy=0.85,
        latency_ms=2100.0,
        tests_passed=4,
        tests_total=5,
        critic_confidence=0.78,
    )
    version = SkillVersion(
        content="# Skill content",
        test_cases="test_cases:\n  - name: test1",
        metrics=metrics,
        iteration=1,
    )

    assert version.content == "# Skill content"
    assert version.metrics.accuracy == 0.85
    assert version.iteration == 1


def test_skill_auto_state_tracks_best_version():
    """SkillAutoState should track best version separately from current."""
    from kubani.workflows.skill_auto.models import SkillAutoState, SkillVersion, EvalMetrics

    state = SkillAutoState(skill_path="kubani/skills/_development/test-skill")

    assert state.iteration == 0
    assert state.best_version is None
    assert state.best_score == 0.0
    assert state.status == "running"


def test_overlap_result_model():
    """OverlapResult should capture overlap detection results."""
    from kubani.workflows.skill_auto.models import OverlapResult

    result = OverlapResult(
        has_overlap=True,
        confidence=0.78,
        overlapping_skills=["memory-troubleshooting"],
        reasoning="Both diagnose memory-related failures",
        recommendation="merge",
    )

    assert result.has_overlap is True
    assert "memory-troubleshooting" in result.overlapping_skills


def test_iteration_result_model():
    """IterationResult should capture a single iteration's outcome."""
    from kubani.workflows.skill_auto.models import IterationResult, EvalMetrics

    metrics = EvalMetrics(
        accuracy=0.80,
        latency_ms=1500.0,
        tests_passed=4,
        tests_total=5,
        critic_confidence=0.85,
    )
    result = IterationResult(
        iteration=1,
        metrics=metrics,
        score=0.76,
        improved=True,
        action="continue",
    )

    assert result.iteration == 1
    assert result.improved is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/workflows/skill_auto/test_models.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'kubani.workflows.skill_auto'"

**Step 3: Create directory structure**

```bash
mkdir -p kubani/workflows/skill_auto
mkdir -p tests/workflows/skill_auto
touch kubani/workflows/__init__.py
touch kubani/workflows/skill_auto/__init__.py
touch tests/workflows/__init__.py
touch tests/workflows/skill_auto/__init__.py
```

**Step 4: Write minimal implementation**

```python
# kubani/workflows/skill_auto/models.py
"""Data models for the Skill Auto workflow."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass
class EvalMetrics:
    """Evaluation metrics from a skill evaluation run."""

    accuracy: float  # 0.0 - 1.0
    latency_ms: float
    tests_passed: int
    tests_total: int
    critic_confidence: float  # 0.0 - 1.0
    tokens_prompt: int = 0
    tokens_completion: int = 0


@dataclass
class SkillVersion:
    """A snapshot of a skill at a specific iteration."""

    content: str  # SKILL.md content
    test_cases: str  # test_cases.yaml content
    metrics: EvalMetrics
    iteration: int
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class OverlapResult:
    """Result of skill overlap detection."""

    has_overlap: bool
    confidence: float  # 0.0 - 1.0
    overlapping_skills: list[str]
    reasoning: str
    recommendation: Literal["proceed", "merge", "abort"]


@dataclass
class IterationResult:
    """Result of a single eval-improve iteration."""

    iteration: int
    metrics: EvalMetrics
    score: float  # Composite score (accuracy + latency)
    improved: bool  # Whether this iteration improved on best
    action: Literal["continue", "stop_success", "stop_plateau", "stop_cap", "stop_regression"]
    error: str | None = None


@dataclass
class SkillAutoInput:
    """Input for the SkillAutoWorkflow."""

    description: str
    mode: Literal["create", "improve"] = "create"
    skill_path: str | None = None  # Required for improve mode
    seed_tests_path: str | None = None
    max_iterations: int = 5
    target_accuracy: float = 0.80
    review_each_iteration: bool = False
    skip_promotion: bool = False
    notify: bool = True
    notify_channel: str = "skill-notifications"
    allow_overlap: bool = False


@dataclass
class SkillAutoState:
    """Workflow state for SkillAutoWorkflow."""

    skill_path: str
    skill_name: str = ""
    iteration: int = 0
    history: list[IterationResult] = field(default_factory=list)
    best_version: SkillVersion | None = None
    best_score: float = 0.0
    status: Literal["running", "paused", "completed", "failed"] = "running"
    overlap_warning: OverlapResult | None = None
    error: str | None = None
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None


@dataclass
class SkillAutoResult:
    """Final result of the SkillAutoWorkflow."""

    success: bool
    skill_path: str
    final_metrics: EvalMetrics | None
    iterations_completed: int
    stop_reason: str
    promoted: bool = False
    error: str | None = None
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/workflows/skill_auto/test_models.py -v`
Expected: PASS (6 tests)

**Step 6: Commit**

```bash
git add kubani/workflows/ tests/workflows/
git commit -m "feat(skill-auto): add data models for auto workflow

- SkillAutoInput: workflow input with defaults
- SkillAutoState: tracks iteration, best version, status
- EvalMetrics, SkillVersion, IterationResult: evaluation data
- OverlapResult: skill overlap detection results"
```

---

### Task 1.2: Add Score Calculation Utility

**Files:**
- Modify: `kubani/workflows/skill_auto/models.py`
- Test: `tests/workflows/skill_auto/test_models.py`

**Step 1: Write the failing test**

```python
# Add to tests/workflows/skill_auto/test_models.py

def test_compute_score_weights_accuracy_and_latency():
    """Score should weight accuracy (70%) and latency (30%)."""
    from kubani.workflows.skill_auto.models import EvalMetrics, compute_score

    # High accuracy, medium latency
    metrics1 = EvalMetrics(accuracy=0.90, latency_ms=2000, tests_passed=9, tests_total=10, critic_confidence=0.85)
    score1 = compute_score(metrics1)

    # Medium accuracy, low latency
    metrics2 = EvalMetrics(accuracy=0.70, latency_ms=500, tests_passed=7, tests_total=10, critic_confidence=0.75)
    score2 = compute_score(metrics2)

    # High accuracy should win despite slower latency
    assert score1 > score2


def test_compute_score_normalized_latency():
    """Latency should be normalized - faster is better."""
    from kubani.workflows.skill_auto.models import EvalMetrics, compute_score

    fast = EvalMetrics(accuracy=0.80, latency_ms=500, tests_passed=8, tests_total=10, critic_confidence=0.80)
    slow = EvalMetrics(accuracy=0.80, latency_ms=5000, tests_passed=8, tests_total=10, critic_confidence=0.80)

    assert compute_score(fast) > compute_score(slow)


def test_is_plateau_detects_stagnation():
    """is_plateau should detect when score improvement is < 2% for 2 iterations."""
    from kubani.workflows.skill_auto.models import IterationResult, EvalMetrics, is_plateau

    metrics = EvalMetrics(accuracy=0.80, latency_ms=1500, tests_passed=8, tests_total=10, critic_confidence=0.80)

    history = [
        IterationResult(iteration=1, metrics=metrics, score=0.75, improved=True, action="continue"),
        IterationResult(iteration=2, metrics=metrics, score=0.76, improved=True, action="continue"),  # +1.3%
        IterationResult(iteration=3, metrics=metrics, score=0.765, improved=True, action="continue"),  # +0.7%
    ]

    assert is_plateau(history) is True


def test_is_plateau_false_when_improving():
    """is_plateau should return False when recent improvements are significant."""
    from kubani.workflows.skill_auto.models import IterationResult, EvalMetrics, is_plateau

    metrics = EvalMetrics(accuracy=0.80, latency_ms=1500, tests_passed=8, tests_total=10, critic_confidence=0.80)

    history = [
        IterationResult(iteration=1, metrics=metrics, score=0.70, improved=True, action="continue"),
        IterationResult(iteration=2, metrics=metrics, score=0.75, improved=True, action="continue"),  # +7%
        IterationResult(iteration=3, metrics=metrics, score=0.80, improved=True, action="continue"),  # +6.7%
    ]

    assert is_plateau(history) is False
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/workflows/skill_auto/test_models.py::test_compute_score_weights_accuracy_and_latency -v`
Expected: FAIL with "cannot import name 'compute_score'"

**Step 3: Write minimal implementation**

```python
# Add to kubani/workflows/skill_auto/models.py

# Constants for score calculation
ACCURACY_WEIGHT = 0.7
LATENCY_WEIGHT = 0.3
LATENCY_BASELINE_MS = 3000.0  # Normalize latency against this baseline
PLATEAU_THRESHOLD = 0.02  # 2% improvement threshold
PLATEAU_WINDOW = 2  # Check last N iterations


def compute_score(metrics: EvalMetrics) -> float:
    """
    Compute composite score from metrics.

    Score = accuracy * 0.7 + normalized_latency_score * 0.3

    Where normalized_latency_score = baseline / actual (capped at 1.0)
    Faster execution gets higher latency score.
    """
    # Accuracy component (0.0 - 1.0)
    accuracy_score = metrics.accuracy * ACCURACY_WEIGHT

    # Latency component - faster is better
    # Cap at 1.0 (can't score higher than baseline)
    latency_ratio = min(LATENCY_BASELINE_MS / max(metrics.latency_ms, 1.0), 1.0)
    latency_score = latency_ratio * LATENCY_WEIGHT

    return accuracy_score + latency_score


def is_plateau(history: list[IterationResult], window: int = PLATEAU_WINDOW, threshold: float = PLATEAU_THRESHOLD) -> bool:
    """
    Detect if improvement has plateaued.

    Returns True if score improvement is < threshold for the last `window` iterations.
    """
    if len(history) < window + 1:
        return False

    recent = history[-(window + 1):]

    for i in range(1, len(recent)):
        prev_score = recent[i - 1].score
        curr_score = recent[i].score

        if prev_score > 0:
            improvement = (curr_score - prev_score) / prev_score
            if improvement >= threshold:
                return False  # Found significant improvement

    return True  # All recent improvements below threshold
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/workflows/skill_auto/test_models.py -v`
Expected: PASS (10 tests)

**Step 5: Commit**

```bash
git add kubani/workflows/skill_auto/models.py tests/workflows/skill_auto/test_models.py
git commit -m "feat(skill-auto): add score calculation and plateau detection

- compute_score(): 70% accuracy + 30% latency (faster = better)
- is_plateau(): detect < 2% improvement over 2 iterations"
```

---

## Phase 2: Activities

### Task 2.1: Skill Overlap Detection Activity

**Files:**
- Create: `kubani/workflows/skill_auto/activities.py`
- Test: `tests/workflows/skill_auto/test_activities.py`

**Step 1: Write the failing test**

```python
# tests/workflows/skill_auto/test_activities.py
"""Tests for skill auto workflow activities."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_llm_client():
    """Mock LLM client for testing."""
    client = MagicMock()
    client.chat = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_detect_overlap_finds_similar_skill(mock_llm_client):
    """detect_skill_overlap should identify overlapping skills."""
    from kubani.workflows.skill_auto.activities import detect_skill_overlap
    from kubani.workflows.skill_auto.models import OverlapResult

    # Mock LLM response indicating overlap
    mock_llm_client.chat.return_value = {
        "content": '''```json
{
    "has_overlap": true,
    "confidence": 0.82,
    "overlapping_skills": ["memory-troubleshooting"],
    "reasoning": "Both skills diagnose memory-related pod failures",
    "recommendation": "merge"
}
```''',
        "tokens": {"prompt": 100, "completion": 50, "total": 150},
    }

    result = await detect_skill_overlap(
        description="A skill that helps diagnose OOMKilled pods",
        existing_skills=[
            {"name": "memory-troubleshooting", "description": "Diagnose memory issues in pods"},
            {"name": "cpu-throttling", "description": "Diagnose CPU throttling issues"},
        ],
        llm_client=mock_llm_client,
    )

    assert isinstance(result, OverlapResult)
    assert result.has_overlap is True
    assert result.confidence > 0.8
    assert "memory-troubleshooting" in result.overlapping_skills


@pytest.mark.asyncio
async def test_detect_overlap_no_overlap(mock_llm_client):
    """detect_skill_overlap should return no overlap when skills are distinct."""
    from kubani.workflows.skill_auto.activities import detect_skill_overlap

    mock_llm_client.chat.return_value = {
        "content": '''```json
{
    "has_overlap": false,
    "confidence": 0.95,
    "overlapping_skills": [],
    "reasoning": "This skill addresses a unique use case",
    "recommendation": "proceed"
}
```''',
        "tokens": {"prompt": 100, "completion": 50, "total": 150},
    }

    result = await detect_skill_overlap(
        description="A skill that manages Kubernetes RBAC policies",
        existing_skills=[
            {"name": "memory-troubleshooting", "description": "Diagnose memory issues"},
        ],
        llm_client=mock_llm_client,
    )

    assert result.has_overlap is False
    assert result.recommendation == "proceed"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/workflows/skill_auto/test_activities.py::test_detect_overlap_finds_similar_skill -v`
Expected: FAIL with "ModuleNotFoundError" or "cannot import name 'detect_skill_overlap'"

**Step 3: Write minimal implementation**

```python
# kubani/workflows/skill_auto/activities.py
"""Activities for the Skill Auto workflow."""

import json
import logging
import re
from pathlib import Path
from typing import Any

from temporalio import activity

from kubani.workflows.skill_auto.models import (
    EvalMetrics,
    OverlapResult,
    SkillVersion,
)

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> dict[str, Any]:
    """Extract JSON from text, handling markdown code blocks."""
    # Try to find JSON in code blocks first
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if json_match:
        text = json_match.group(1).strip()

    # Find JSON object
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        return json.loads(text[start:end])

    raise ValueError(f"Could not extract JSON from: {text[:200]}")


async def detect_skill_overlap(
    description: str,
    existing_skills: list[dict[str, str]],
    llm_client: Any,
) -> OverlapResult:
    """
    Detect if a new skill overlaps with existing skills.

    Args:
        description: Description of the new skill
        existing_skills: List of existing skills with name and description
        llm_client: LLM client for analysis

    Returns:
        OverlapResult with overlap assessment
    """
    if not existing_skills:
        return OverlapResult(
            has_overlap=False,
            confidence=1.0,
            overlapping_skills=[],
            reasoning="No existing skills to compare against",
            recommendation="proceed",
        )

    # Format existing skills for prompt
    skills_text = "\n".join(
        f"- {s['name']}: {s.get('description', 'No description')}"
        for s in existing_skills
    )

    prompt = f"""Analyze whether this new skill overlaps with any existing skills.

NEW SKILL DESCRIPTION:
{description}

EXISTING SKILLS:
{skills_text}

Respond with a JSON object:
{{
    "has_overlap": boolean,
    "confidence": float (0.0-1.0),
    "overlapping_skills": ["skill-name", ...],
    "reasoning": "explanation of why overlap exists or not",
    "recommendation": "proceed" | "merge" | "abort"
}}

Consider skills as overlapping if they:
- Address the same problem domain
- Would be triggered by similar scenarios
- Provide redundant functionality

Recommend "merge" if the new skill could enhance an existing one.
Recommend "abort" if the new skill is essentially a duplicate.
Recommend "proceed" if the skill is sufficiently distinct."""

    response = await llm_client.chat(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,  # Low temperature for consistent analysis
    )

    try:
        data = _extract_json(response["content"])
        return OverlapResult(
            has_overlap=data.get("has_overlap", False),
            confidence=data.get("confidence", 0.5),
            overlapping_skills=data.get("overlapping_skills", []),
            reasoning=data.get("reasoning", ""),
            recommendation=data.get("recommendation", "proceed"),
        )
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to parse overlap detection response: {e}")
        return OverlapResult(
            has_overlap=False,
            confidence=0.0,
            overlapping_skills=[],
            reasoning=f"Failed to analyze: {e}",
            recommendation="proceed",
        )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/workflows/skill_auto/test_activities.py -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add kubani/workflows/skill_auto/activities.py tests/workflows/skill_auto/test_activities.py
git commit -m "feat(skill-auto): add overlap detection activity

- detect_skill_overlap(): LLM-based comparison against existing skills
- Returns OverlapResult with confidence, reasoning, recommendation"
```

---

### Task 2.2: Load Existing Skills Activity

**Files:**
- Modify: `kubani/workflows/skill_auto/activities.py`
- Test: `tests/workflows/skill_auto/test_activities.py`

**Step 1: Write the failing test**

```python
# Add to tests/workflows/skill_auto/test_activities.py

@pytest.mark.asyncio
async def test_load_existing_skills_from_directory(tmp_path):
    """load_existing_skills should read skills from the skills directory."""
    from kubani.workflows.skill_auto.activities import load_existing_skills

    # Create test skill structure
    skill_dir = tmp_path / "skills" / "general" / "test-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill for testing
triggers:
  - test_trigger
---

# Test Skill

This is a test skill.
""")

    skills = await load_existing_skills(tmp_path / "skills")

    assert len(skills) == 1
    assert skills[0]["name"] == "test-skill"
    assert "test skill" in skills[0]["description"].lower()


@pytest.mark.asyncio
async def test_load_existing_skills_excludes_development(tmp_path):
    """load_existing_skills should exclude _development skills by default."""
    from kubani.workflows.skill_auto.activities import load_existing_skills

    # Production skill
    prod_dir = tmp_path / "skills" / "general" / "prod-skill"
    prod_dir.mkdir(parents=True)
    (prod_dir / "SKILL.md").write_text("""---
name: prod-skill
description: Production skill
---
# Prod Skill
""")

    # Development skill
    dev_dir = tmp_path / "skills" / "_development" / "dev-skill"
    dev_dir.mkdir(parents=True)
    (dev_dir / "SKILL.md").write_text("""---
name: dev-skill
description: Development skill
---
# Dev Skill
""")

    skills = await load_existing_skills(tmp_path / "skills", include_development=False)

    assert len(skills) == 1
    assert skills[0]["name"] == "prod-skill"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/workflows/skill_auto/test_activities.py::test_load_existing_skills_from_directory -v`
Expected: FAIL with "cannot import name 'load_existing_skills'"

**Step 3: Write minimal implementation**

```python
# Add to kubani/workflows/skill_auto/activities.py

import yaml


async def load_existing_skills(
    skills_path: Path,
    include_development: bool = True,
) -> list[dict[str, str]]:
    """
    Load metadata for all existing skills.

    Args:
        skills_path: Path to skills directory
        include_development: Whether to include _development skills

    Returns:
        List of skill metadata dicts with name, description, path
    """
    skills = []

    if not skills_path.exists():
        return skills

    for skill_md in skills_path.rglob("SKILL.md"):
        # Skip _development if not included
        if not include_development and "_development" in str(skill_md):
            continue

        try:
            content = skill_md.read_text()

            # Parse YAML frontmatter
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    frontmatter = yaml.safe_load(parts[1])
                    skills.append({
                        "name": frontmatter.get("name", skill_md.parent.name),
                        "description": frontmatter.get("description", ""),
                        "path": str(skill_md.parent),
                        "triggers": frontmatter.get("triggers", []),
                    })
        except Exception as e:
            logger.warning(f"Failed to load skill {skill_md}: {e}")

    return skills
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/workflows/skill_auto/test_activities.py -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add kubani/workflows/skill_auto/activities.py tests/workflows/skill_auto/test_activities.py
git commit -m "feat(skill-auto): add load_existing_skills activity

- Reads SKILL.md frontmatter for all skills
- Option to exclude _development skills"
```

---

### Task 2.3: Infer Skill Structure Activity

**Files:**
- Modify: `kubani/workflows/skill_auto/activities.py`
- Test: `tests/workflows/skill_auto/test_activities.py`

**Step 1: Write the failing test**

```python
# Add to tests/workflows/skill_auto/test_activities.py

@pytest.mark.asyncio
async def test_infer_skill_structure_generates_spec(mock_llm_client):
    """infer_skill_structure should generate skill spec from description."""
    from kubani.workflows.skill_auto.activities import infer_skill_structure

    mock_llm_client.chat.return_value = {
        "content": '''```json
{
    "name": "oom-diagnostics",
    "description": "Diagnose OOMKilled pod failures",
    "inputs": {
        "pod_name": {"type": "string", "description": "Name of the pod", "required": true},
        "namespace": {"type": "string", "description": "Kubernetes namespace", "required": true}
    },
    "outputs": {
        "diagnosis": {"type": "string", "description": "Root cause analysis"},
        "recommendations": {"type": "array", "description": "Suggested fixes"}
    },
    "steps": [
        "Get pod events and logs",
        "Check container memory limits",
        "Analyze memory usage patterns",
        "Provide recommendations"
    ],
    "examples": [
        {
            "name": "Basic OOM diagnosis",
            "description": "Diagnose a pod killed due to OOM",
            "input": {"pod_name": "api-server-1", "namespace": "production"},
            "expected_output": {"diagnosis": "Container exceeded memory limit"}
        }
    ]
}
```''',
        "tokens": {"prompt": 200, "completion": 300, "total": 500},
    }

    spec = await infer_skill_structure(
        description="A skill that helps diagnose OOMKilled pods",
        llm_client=mock_llm_client,
    )

    assert spec["name"] == "oom-diagnostics"
    assert "pod_name" in spec["inputs"]
    assert len(spec["steps"]) > 0
    assert len(spec["examples"]) > 0
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/workflows/skill_auto/test_activities.py::test_infer_skill_structure_generates_spec -v`
Expected: FAIL with "cannot import name 'infer_skill_structure'"

**Step 3: Write minimal implementation**

```python
# Add to kubani/workflows/skill_auto/activities.py

async def infer_skill_structure(
    description: str,
    llm_client: Any,
    context: str | None = None,
) -> dict[str, Any]:
    """
    Infer skill structure from a description.

    Uses LLM to generate a complete skill specification including
    name, inputs, outputs, steps, and example test cases.

    Args:
        description: Natural language description of the skill
        llm_client: LLM client for generation
        context: Optional additional context

    Returns:
        Skill specification dict
    """
    context_section = f"\n\nADDITIONAL CONTEXT:\n{context}" if context else ""

    prompt = f"""Generate a complete skill specification from this description.

SKILL DESCRIPTION:
{description}{context_section}

Respond with a JSON object:
{{
    "name": "kebab-case-name",
    "description": "One-line description of what the skill does",
    "inputs": {{
        "param_name": {{
            "type": "string|number|boolean|array|object",
            "description": "What this parameter is for",
            "required": true|false
        }}
    }},
    "outputs": {{
        "field_name": {{
            "type": "string|number|boolean|array|object",
            "description": "What this output contains"
        }}
    }},
    "steps": [
        "Step 1: What to do first",
        "Step 2: What to do next",
        ...
    ],
    "error_handling": [
        "Handle case when X fails",
        ...
    ],
    "examples": [
        {{
            "name": "Example name",
            "description": "What this example demonstrates",
            "input": {{"param": "value"}},
            "expected_output": {{"field": "expected value"}}
        }}
    ]
}}

Make the skill focused and specific. Include 2-3 diverse examples that cover:
- A typical happy path case
- An edge case or boundary condition
- An error case if applicable"""

    response = await llm_client.chat(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )

    return _extract_json(response["content"])
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/workflows/skill_auto/test_activities.py -v`
Expected: PASS (5 tests)

**Step 5: Commit**

```bash
git add kubani/workflows/skill_auto/activities.py tests/workflows/skill_auto/test_activities.py
git commit -m "feat(skill-auto): add infer_skill_structure activity

- LLM generates complete skill spec from description
- Includes inputs, outputs, steps, examples"
```

---

### Task 2.4: Generate Test Cases Activity

**Files:**
- Modify: `kubani/workflows/skill_auto/activities.py`
- Test: `tests/workflows/skill_auto/test_activities.py`

**Step 1: Write the failing test**

```python
# Add to tests/workflows/skill_auto/test_activities.py

@pytest.mark.asyncio
async def test_generate_test_cases_from_spec(mock_llm_client):
    """generate_test_cases should create test cases with assertions."""
    from kubani.workflows.skill_auto.activities import generate_test_cases

    mock_llm_client.chat.return_value = {
        "content": '''```yaml
test_cases:
  - name: basic_oom_diagnosis
    description: Diagnose a pod killed due to OOM
    inputs:
      pod_name: api-server-1
      namespace: production
    expected:
      diagnosis: Contains analysis of memory issue
    assertions:
      - type: exists
        field: diagnosis
        description: Should provide a diagnosis
      - type: not_empty
        field: recommendations
        description: Should provide recommendations
```''',
        "tokens": {"prompt": 200, "completion": 200, "total": 400},
    }

    spec = {
        "name": "oom-diagnostics",
        "description": "Diagnose OOMKilled pods",
        "inputs": {"pod_name": {"type": "string"}, "namespace": {"type": "string"}},
        "examples": [{"name": "basic", "input": {"pod_name": "test"}}],
    }

    test_cases_yaml = await generate_test_cases(spec, mock_llm_client)

    assert "test_cases:" in test_cases_yaml
    assert "basic_oom_diagnosis" in test_cases_yaml
    assert "assertions:" in test_cases_yaml
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/workflows/skill_auto/test_activities.py::test_generate_test_cases_from_spec -v`
Expected: FAIL with "cannot import name 'generate_test_cases'"

**Step 3: Write minimal implementation**

```python
# Add to kubani/workflows/skill_auto/activities.py

async def generate_test_cases(
    spec: dict[str, Any],
    llm_client: Any,
    seed_tests: str | None = None,
) -> str:
    """
    Generate test cases YAML from skill specification.

    Args:
        spec: Skill specification with examples
        llm_client: LLM client for generation
        seed_tests: Optional seed test cases to expand from

    Returns:
        YAML string with test cases
    """
    seed_section = ""
    if seed_tests:
        seed_section = f"""
SEED TEST CASES (expand from these):
{seed_tests}
"""

    examples_text = yaml.dump(spec.get("examples", []), default_flow_style=False)

    prompt = f"""Generate test cases for this skill specification.

SKILL: {spec.get('name')}
DESCRIPTION: {spec.get('description')}

INPUTS:
{yaml.dump(spec.get('inputs', {}), default_flow_style=False)}

OUTPUTS:
{yaml.dump(spec.get('outputs', {}), default_flow_style=False)}

EXAMPLES FROM SPEC:
{examples_text}
{seed_section}

Generate a YAML file with 3-5 test cases that cover:
1. Happy path - typical successful usage
2. Edge case - boundary conditions or unusual inputs
3. Error handling - invalid inputs or failure scenarios

Each test case should have:
- name: snake_case identifier
- description: What this test validates
- inputs: Input values for the test
- expected: Expected output fields (can be partial)
- assertions: List of checks with type, field, and description

Assertion types available:
- equals: Exact value match
- contains: Substring or membership check
- exists: Field is present
- not_empty: Field has a truthy value
- type: Check field type (string, number, boolean, list, dict)

Respond with ONLY the YAML content, no code blocks or explanation."""

    response = await llm_client.chat(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )

    content = response["content"].strip()

    # Remove code block markers if present
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

    return content
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/workflows/skill_auto/test_activities.py -v`
Expected: PASS (6 tests)

**Step 5: Commit**

```bash
git add kubani/workflows/skill_auto/activities.py tests/workflows/skill_auto/test_activities.py
git commit -m "feat(skill-auto): add generate_test_cases activity

- LLM generates test cases YAML from skill spec
- Supports seed tests for expansion
- Generates happy path, edge case, error handling tests"
```

---

### Task 2.5: Write Skill Files Activity

**Files:**
- Modify: `kubani/workflows/skill_auto/activities.py`
- Test: `tests/workflows/skill_auto/test_activities.py`

**Step 1: Write the failing test**

```python
# Add to tests/workflows/skill_auto/test_activities.py

@pytest.mark.asyncio
async def test_write_skill_files_creates_directory_structure(tmp_path):
    """write_skill_files should create skill directory with all files."""
    from kubani.workflows.skill_auto.activities import write_skill_files

    spec = {
        "name": "test-skill",
        "description": "A test skill",
        "inputs": {"query": {"type": "string", "required": True}},
        "outputs": {"result": {"type": "string"}},
        "steps": ["Step 1", "Step 2"],
    }
    test_cases = "test_cases:\n  - name: test1\n    inputs: {}"

    skill_path = await write_skill_files(
        spec=spec,
        test_cases=test_cases,
        output_dir=tmp_path / "skills" / "_development",
    )

    assert Path(skill_path).exists()
    assert (Path(skill_path) / "SKILL.md").exists()
    assert (Path(skill_path) / "test_cases.yaml").exists()
    assert (Path(skill_path) / "metadata.json").exists()

    # Verify SKILL.md has frontmatter
    skill_content = (Path(skill_path) / "SKILL.md").read_text()
    assert "---" in skill_content
    assert "name: test-skill" in skill_content
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/workflows/skill_auto/test_activities.py::test_write_skill_files_creates_directory_structure -v`
Expected: FAIL with "cannot import name 'write_skill_files'"

**Step 3: Write minimal implementation**

```python
# Add to kubani/workflows/skill_auto/activities.py

from datetime import datetime


async def write_skill_files(
    spec: dict[str, Any],
    test_cases: str,
    output_dir: Path,
) -> str:
    """
    Write skill files to disk.

    Creates:
    - SKILL.md with frontmatter and content
    - test_cases.yaml with test definitions
    - metadata.json with creation info

    Args:
        spec: Skill specification
        test_cases: Test cases YAML content
        output_dir: Directory to write to (e.g., kubani/skills/_development)

    Returns:
        Path to created skill directory
    """
    skill_name = spec["name"]
    skill_dir = output_dir / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)

    # Generate SKILL.md
    frontmatter = {
        "name": skill_name,
        "description": spec.get("description", ""),
        "version": "0.1.0",
        "category": "_development",
        "triggers": spec.get("triggers", []),
    }

    steps_text = "\n".join(f"1. {step}" for i, step in enumerate(spec.get("steps", []), 1))

    skill_content = f"""---
{yaml.dump(frontmatter, default_flow_style=False).strip()}
---

# {skill_name.replace('-', ' ').title()}

{spec.get('description', '')}

## Inputs

{_format_params(spec.get('inputs', {}))}

## Outputs

{_format_params(spec.get('outputs', {}))}

## Steps

{steps_text}

## Error Handling

{chr(10).join(f'- {e}' for e in spec.get('error_handling', ['Handle errors gracefully']))}
"""

    (skill_dir / "SKILL.md").write_text(skill_content)
    (skill_dir / "test_cases.yaml").write_text(test_cases)

    # Write metadata
    metadata = {
        "name": skill_name,
        "version": "0.1.0",
        "status": "development",
        "created_at": datetime.now().isoformat(),
        "created_by": "auto-mode",
        "allowed_tools": ["read", "search", "web_fetch"],
    }
    (skill_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    return str(skill_dir)


def _format_params(params: dict[str, Any]) -> str:
    """Format input/output parameters as markdown."""
    if not params:
        return "None"

    lines = []
    for name, info in params.items():
        if isinstance(info, dict):
            type_str = info.get("type", "any")
            desc = info.get("description", "")
            required = " (required)" if info.get("required") else ""
            lines.append(f"- **{name}** ({type_str}){required}: {desc}")
        else:
            lines.append(f"- **{name}**: {info}")

    return "\n".join(lines)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/workflows/skill_auto/test_activities.py -v`
Expected: PASS (7 tests)

**Step 5: Commit**

```bash
git add kubani/workflows/skill_auto/activities.py tests/workflows/skill_auto/test_activities.py
git commit -m "feat(skill-auto): add write_skill_files activity

- Creates SKILL.md with YAML frontmatter
- Creates test_cases.yaml and metadata.json
- Tracks created_by: auto-mode"
```

---

### Task 2.6: Run Evaluation Activity (Adapter)

**Files:**
- Modify: `kubani/workflows/skill_auto/activities.py`
- Test: `tests/workflows/skill_auto/test_activities.py`

**Step 1: Write the failing test**

```python
# Add to tests/workflows/skill_auto/test_activities.py

@pytest.mark.asyncio
async def test_run_evaluation_returns_metrics(tmp_path, mock_llm_client):
    """run_evaluation should return EvalMetrics from skill evaluation."""
    from kubani.workflows.skill_auto.activities import run_evaluation
    from kubani.workflows.skill_auto.models import EvalMetrics

    # Create a minimal skill
    skill_dir = tmp_path / "test-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: test\n---\n# Test")
    (skill_dir / "test_cases.yaml").write_text("""
test_cases:
  - name: test1
    inputs: {}
    assertions:
      - type: exists
        field: result
""")

    # Mock the evaluator
    with patch("kubani.workflows.skill_auto.activities.SkillEvaluatorLLM") as mock_eval_cls:
        mock_evaluator = MagicMock()
        mock_evaluator.evaluate_skill.return_value = {
            "accuracy": 0.85,
            "total_tests": 1,
            "passed_tests": 1,
            "average_latency_ms": 1500,
            "average_critic_confidence": 0.80,
            "total_tokens": {"prompt": 100, "completion": 50, "total": 150},
        }
        mock_eval_cls.return_value = mock_evaluator

        metrics = await run_evaluation(
            skill_path=str(skill_dir),
            llm_client=mock_llm_client,
        )

        assert isinstance(metrics, EvalMetrics)
        assert metrics.accuracy == 0.85
        assert metrics.tests_passed == 1
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/workflows/skill_auto/test_activities.py::test_run_evaluation_returns_metrics -v`
Expected: FAIL with "cannot import name 'run_evaluation'"

**Step 3: Write minimal implementation**

```python
# Add to kubani/workflows/skill_auto/activities.py

# Import at top of file
from kubani_dev.skill_evaluator_llm import SkillEvaluatorLLM


async def run_evaluation(
    skill_path: str,
    llm_client: Any,
    verbose: bool = False,
) -> EvalMetrics:
    """
    Run skill evaluation and return metrics.

    Wraps SkillEvaluatorLLM to run test cases and return structured metrics.

    Args:
        skill_path: Path to skill directory
        llm_client: LLM client for evaluation
        verbose: Whether to show verbose output

    Returns:
        EvalMetrics with evaluation results
    """
    evaluator = SkillEvaluatorLLM(llm_client)
    results = evaluator.evaluate_skill(Path(skill_path), verbose=verbose)

    return EvalMetrics(
        accuracy=results.get("accuracy", 0.0),
        latency_ms=results.get("average_latency_ms", 0.0),
        tests_passed=results.get("passed_tests", 0),
        tests_total=results.get("total_tests", 0),
        critic_confidence=results.get("average_critic_confidence", 0.0),
        tokens_prompt=results.get("total_tokens", {}).get("prompt", 0),
        tokens_completion=results.get("total_tokens", {}).get("completion", 0),
    )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/workflows/skill_auto/test_activities.py -v`
Expected: PASS (8 tests)

**Step 5: Commit**

```bash
git add kubani/workflows/skill_auto/activities.py tests/workflows/skill_auto/test_activities.py
git commit -m "feat(skill-auto): add run_evaluation activity

- Wraps SkillEvaluatorLLM for Temporal activity use
- Returns structured EvalMetrics"
```

---

### Task 2.7: Run Improvement Activity (Adapter)

**Files:**
- Modify: `kubani/workflows/skill_auto/activities.py`
- Test: `tests/workflows/skill_auto/test_activities.py`

**Step 1: Write the failing test**

```python
# Add to tests/workflows/skill_auto/test_activities.py

@pytest.mark.asyncio
async def test_run_improvement_updates_skill(tmp_path, mock_llm_client):
    """run_improvement should update SKILL.md based on eval feedback."""
    from kubani.workflows.skill_auto.activities import run_improvement

    # Create skill
    skill_dir = tmp_path / "test-skill"
    skill_dir.mkdir()
    original_content = "---\nname: test\n---\n# Test\nOriginal content"
    (skill_dir / "SKILL.md").write_text(original_content)

    eval_results = {
        "accuracy": 0.60,
        "tests": [
            {"name": "test1", "passed": False, "error": "Missing field X"},
        ],
    }

    with patch("kubani.workflows.skill_auto.activities.SkillImprover") as mock_imp_cls:
        mock_improver = MagicMock()
        mock_improver.improve_skill.return_value = {
            "improved_skill": "---\nname: test\n---\n# Test\nImproved content with field X",
        }
        mock_imp_cls.return_value = mock_improver

        await run_improvement(
            skill_path=str(skill_dir),
            eval_results=eval_results,
            llm_client=mock_llm_client,
        )

        # Verify backup was created
        backup_files = list(skill_dir.glob("SKILL.md.backup*"))
        assert len(backup_files) >= 1
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/workflows/skill_auto/test_activities.py::test_run_improvement_updates_skill -v`
Expected: FAIL with "cannot import name 'run_improvement'"

**Step 3: Write minimal implementation**

```python
# Add to kubani/workflows/skill_auto/activities.py

from kubani_dev.skill_improver import SkillImprover


async def run_improvement(
    skill_path: str,
    eval_results: dict[str, Any],
    llm_client: Any,
    improvement_goals: list[str] | None = None,
) -> str:
    """
    Run skill improvement based on evaluation feedback.

    Wraps SkillImprover to analyze failures and update skill.
    Creates backup before modifying.

    Args:
        skill_path: Path to skill directory
        eval_results: Evaluation results with failures and feedback
        llm_client: LLM client for improvement
        improvement_goals: Goals like ["accuracy", "latency"]

    Returns:
        Path to updated SKILL.md
    """
    skill_dir = Path(skill_path)
    skill_md = skill_dir / "SKILL.md"

    # Create backup
    backup_name = f"SKILL.md.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    (skill_dir / backup_name).write_text(skill_md.read_text())

    improver = SkillImprover(llm_client)
    result = improver.improve_skill(
        skill_dir=skill_dir,
        evaluation_results=eval_results,
        improvement_goals=improvement_goals or ["accuracy"],
    )

    # Write improved content
    if "improved_skill" in result:
        skill_md.write_text(result["improved_skill"])

    return str(skill_md)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/workflows/skill_auto/test_activities.py -v`
Expected: PASS (9 tests)

**Step 5: Commit**

```bash
git add kubani/workflows/skill_auto/activities.py tests/workflows/skill_auto/test_activities.py
git commit -m "feat(skill-auto): add run_improvement activity

- Wraps SkillImprover for Temporal activity use
- Creates timestamped backup before modifying"
```

---

### Task 2.8: Discord Notification Activity

**Files:**
- Modify: `kubani/workflows/skill_auto/activities.py`
- Test: `tests/workflows/skill_auto/test_activities.py`

**Step 1: Write the failing test**

```python
# Add to tests/workflows/skill_auto/test_activities.py

@pytest.mark.asyncio
async def test_send_notification_formats_progress():
    """send_notification should format progress messages for Discord."""
    from kubani.workflows.skill_auto.activities import send_notification
    from kubani.workflows.skill_auto.models import SkillAutoState, EvalMetrics

    with patch("kubani.workflows.skill_auto.activities.get_mcp_client") as mock_get:
        mock_client = MagicMock()
        mock_client.discord.send_message = AsyncMock(return_value=MagicMock(success=True, data={"message_id": "123"}))
        mock_get.return_value = mock_client

        state = SkillAutoState(
            skill_path="kubani/skills/_development/test-skill",
            skill_name="test-skill",
            iteration=2,
            best_score=0.75,
        )

        result = await send_notification(
            channel_name="skill-notifications",
            event="iteration_complete",
            state=state,
            metrics=EvalMetrics(accuracy=0.80, latency_ms=1500, tests_passed=4, tests_total=5, critic_confidence=0.85),
        )

        assert result["success"] is True
        # Verify message was sent
        mock_client.discord.send_message.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/workflows/skill_auto/test_activities.py::test_send_notification_formats_progress -v`
Expected: FAIL with "cannot import name 'send_notification'"

**Step 3: Write minimal implementation**

```python
# Add to kubani/workflows/skill_auto/activities.py

from kubani.framework.mcp import get_mcp_client


async def send_notification(
    channel_name: str,
    event: str,
    state: "SkillAutoState",
    metrics: EvalMetrics | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """
    Send Discord notification about workflow progress.

    Args:
        channel_name: Discord channel name
        event: Event type (started, iteration_complete, completed, failed)
        state: Current workflow state
        metrics: Optional current metrics
        error: Optional error message

    Returns:
        Dict with success status and message_id
    """
    client = get_mcp_client()

    if event == "started":
        content = f"""**Skill Auto: {state.skill_name}**
├─ Started: now
├─ Target: {state.skill_path}
└─ Status: Creating skill..."""

    elif event == "iteration_complete":
        accuracy_pct = f"{metrics.accuracy * 100:.0f}%" if metrics else "N/A"
        latency = f"{metrics.latency_ms:.0f}ms" if metrics else "N/A"
        content = f"""**Skill Auto: {state.skill_name}**
├─ Iteration: {state.iteration}
├─ Accuracy: {accuracy_pct} | Latency: {latency}
├─ Best score: {state.best_score:.2f}
└─ Status: {state.status}"""

    elif event == "completed":
        accuracy_pct = f"{metrics.accuracy * 100:.0f}%" if metrics else "N/A"
        content = f"""**Skill Auto Complete: {state.skill_name}**
├─ Iterations: {state.iteration}
├─ Final: {accuracy_pct} accuracy
└─ React ✅ to approve promotion, ❌ to reject"""

    elif event == "failed":
        content = f"""**Skill Auto Failed: {state.skill_name}**
├─ Iteration: {state.iteration}
├─ Error: {error or 'Unknown error'}
└─ Status: {state.status}"""

    else:
        content = f"Skill Auto [{event}]: {state.skill_name}"

    try:
        # Use channel name lookup
        result = await client.discord.send_message(
            channel_id=channel_name,  # MCP server handles name→ID lookup
            content=content,
        )
        return {"success": result.success, "message_id": result.data.get("message_id") if result.data else None}
    except Exception as e:
        logger.error(f"Failed to send Discord notification: {e}")
        return {"success": False, "error": str(e)}
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/workflows/skill_auto/test_activities.py -v`
Expected: PASS (10 tests)

**Step 5: Commit**

```bash
git add kubani/workflows/skill_auto/activities.py tests/workflows/skill_auto/test_activities.py
git commit -m "feat(skill-auto): add send_notification activity

- Discord notifications for started, iteration, complete, failed
- Formats progress with metrics and status"
```

---

## Phase 3: Temporal Activity Definitions

### Task 3.1: Register Activities with Temporal

**Files:**
- Modify: `kubani/workflows/skill_auto/activities.py`
- Create: `kubani/workflows/skill_auto/__init__.py`

**Step 1: Add Temporal decorators to activities**

```python
# Modify kubani/workflows/skill_auto/activities.py
# Add @activity.defn decorator to each activity function

from temporalio import activity

@activity.defn
async def detect_skill_overlap(...) -> OverlapResult:
    ...

@activity.defn
async def load_existing_skills(...) -> list[dict[str, str]]:
    ...

@activity.defn
async def infer_skill_structure(...) -> dict[str, Any]:
    ...

@activity.defn
async def generate_test_cases(...) -> str:
    ...

@activity.defn
async def write_skill_files(...) -> str:
    ...

@activity.defn
async def run_evaluation(...) -> EvalMetrics:
    ...

@activity.defn
async def run_improvement(...) -> str:
    ...

@activity.defn
async def send_notification(...) -> dict[str, Any]:
    ...
```

**Step 2: Create package init**

```python
# kubani/workflows/skill_auto/__init__.py
"""Skill Auto workflow package."""

from kubani.workflows.skill_auto.activities import (
    detect_skill_overlap,
    generate_test_cases,
    infer_skill_structure,
    load_existing_skills,
    run_evaluation,
    run_improvement,
    send_notification,
    write_skill_files,
)
from kubani.workflows.skill_auto.models import (
    EvalMetrics,
    IterationResult,
    OverlapResult,
    SkillAutoInput,
    SkillAutoResult,
    SkillAutoState,
    SkillVersion,
    compute_score,
    is_plateau,
)

__all__ = [
    # Models
    "EvalMetrics",
    "IterationResult",
    "OverlapResult",
    "SkillAutoInput",
    "SkillAutoResult",
    "SkillAutoState",
    "SkillVersion",
    "compute_score",
    "is_plateau",
    # Activities
    "detect_skill_overlap",
    "generate_test_cases",
    "infer_skill_structure",
    "load_existing_skills",
    "run_evaluation",
    "run_improvement",
    "send_notification",
    "write_skill_files",
]
```

**Step 3: Run tests to verify nothing broke**

Run: `pytest tests/workflows/skill_auto/ -v`
Expected: PASS (all tests)

**Step 4: Commit**

```bash
git add kubani/workflows/skill_auto/
git commit -m "feat(skill-auto): register activities with Temporal

- Add @activity.defn decorators to all activities
- Export all models and activities from package"
```

---

## Phase 4: Workflow Implementation

### Task 4.1: Create SkillAutoWorkflow

**Files:**
- Create: `kubani/workflows/skill_auto/workflow.py`
- Test: `tests/workflows/skill_auto/test_workflow.py`

**Step 1: Write the failing test**

```python
# tests/workflows/skill_auto/test_workflow.py
"""Tests for SkillAutoWorkflow."""

import pytest
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def workflow_env():
    """Create a mock workflow environment."""
    with patch("temporalio.workflow") as mock_workflow:
        mock_workflow.execute_activity = AsyncMock()
        yield mock_workflow


def test_skill_auto_workflow_has_required_methods():
    """SkillAutoWorkflow should have run, get_state, and signal methods."""
    from kubani.workflows.skill_auto.workflow import SkillAutoWorkflow

    assert hasattr(SkillAutoWorkflow, "run")
    assert hasattr(SkillAutoWorkflow, "get_state")
    assert hasattr(SkillAutoWorkflow, "pause")
    assert hasattr(SkillAutoWorkflow, "resume")
    assert hasattr(SkillAutoWorkflow, "cancel")


def test_skill_auto_workflow_decorated():
    """SkillAutoWorkflow should be decorated with @workflow.defn."""
    from kubani.workflows.skill_auto.workflow import SkillAutoWorkflow

    # Check if class has workflow metadata
    assert hasattr(SkillAutoWorkflow, "__temporal_workflow_definition")
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/workflows/skill_auto/test_workflow.py::test_skill_auto_workflow_has_required_methods -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# kubani/workflows/skill_auto/workflow.py
"""Skill Auto Temporal Workflow."""

import asyncio
from datetime import timedelta
from pathlib import Path

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from kubani.workflows.skill_auto.activities import (
        detect_skill_overlap,
        generate_test_cases,
        infer_skill_structure,
        load_existing_skills,
        run_evaluation,
        run_improvement,
        send_notification,
        write_skill_files,
    )
    from kubani.workflows.skill_auto.models import (
        EvalMetrics,
        IterationResult,
        OverlapResult,
        SkillAutoInput,
        SkillAutoResult,
        SkillAutoState,
        SkillVersion,
        compute_score,
        is_plateau,
    )


# Default retry policy for activities
DEFAULT_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=10),
    maximum_interval=timedelta(minutes=5),
    maximum_attempts=3,
    non_retryable_error_types=["SkillValidationError", "UserCancelled"],
)


@workflow.defn
class SkillAutoWorkflow:
    """
    Autonomous skill development workflow.

    Orchestrates: create → eval → improve → repeat until quality goals met.
    """

    def __init__(self) -> None:
        self._state: SkillAutoState | None = None
        self._paused = False
        self._cancelled = False

    @workflow.run
    async def run(self, input: SkillAutoInput) -> SkillAutoResult:
        """Main workflow execution."""
        # Initialize state
        skill_name = self._infer_skill_name(input.description)
        self._state = SkillAutoState(
            skill_path=input.skill_path or f"kubani/skills/_development/{skill_name}",
            skill_name=skill_name,
        )

        try:
            # Phase 1: Check for overlap (new skills only)
            if input.mode == "create" and not input.allow_overlap:
                await self._check_overlap(input)

            # Phase 2: Create skill (if new)
            if input.mode == "create":
                await self._create_skill(input)

            # Phase 3: Iteration loop
            while self._should_continue(input):
                await self._run_iteration(input)

            # Phase 4: Finalize
            return self._build_result()

        except Exception as e:
            self._state.status = "failed"
            self._state.error = str(e)
            if input.notify:
                await self._notify("failed", error=str(e))
            return SkillAutoResult(
                success=False,
                skill_path=self._state.skill_path,
                final_metrics=self._state.best_version.metrics if self._state.best_version else None,
                iterations_completed=self._state.iteration,
                stop_reason="error",
                error=str(e),
            )

    @workflow.query
    def get_state(self) -> SkillAutoState:
        """Query current workflow state."""
        return self._state

    @workflow.signal
    async def pause(self) -> None:
        """Pause workflow after current phase."""
        self._paused = True
        if self._state:
            self._state.status = "paused"

    @workflow.signal
    async def resume(self) -> None:
        """Resume paused workflow."""
        self._paused = False
        if self._state:
            self._state.status = "running"

    @workflow.signal
    async def cancel(self) -> None:
        """Cancel workflow."""
        self._cancelled = True
        if self._state:
            self._state.status = "failed"
            self._state.error = "Cancelled by user"

    def _infer_skill_name(self, description: str) -> str:
        """Infer skill name from description."""
        # Simple heuristic - take first few words, kebab-case
        words = description.lower().split()[:4]
        return "-".join(w for w in words if w.isalnum())[:30]

    def _should_continue(self, input: SkillAutoInput) -> bool:
        """Check if iteration loop should continue."""
        if self._cancelled:
            return False
        if self._state.iteration >= input.max_iterations:
            return False
        if self._state.best_score >= input.target_accuracy:
            return False
        if len(self._state.history) >= 3 and is_plateau(self._state.history):
            return False
        return True

    async def _check_overlap(self, input: SkillAutoInput) -> None:
        """Check for skill overlap."""
        existing = await workflow.execute_activity(
            load_existing_skills,
            args=[Path("kubani/skills"), False],  # Exclude _development
            start_to_close_timeout=timedelta(minutes=1),
        )

        if existing:
            overlap = await workflow.execute_activity(
                detect_skill_overlap,
                args=[input.description, existing],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=DEFAULT_RETRY_POLICY,
            )

            if overlap.has_overlap:
                self._state.overlap_warning = overlap
                # Log warning but continue (creation phase)
                workflow.logger.warning(
                    f"Overlap detected with {overlap.overlapping_skills}: {overlap.reasoning}"
                )

    async def _create_skill(self, input: SkillAutoInput) -> None:
        """Create new skill from description."""
        # Notify start
        if input.notify:
            await self._notify("started")

        # Infer structure
        spec = await workflow.execute_activity(
            infer_skill_structure,
            args=[input.description],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=DEFAULT_RETRY_POLICY,
        )

        # Generate test cases
        test_cases = await workflow.execute_activity(
            generate_test_cases,
            args=[spec, input.seed_tests_path],
            start_to_close_timeout=timedelta(minutes=3),
            retry_policy=DEFAULT_RETRY_POLICY,
        )

        # Write files
        skill_path = await workflow.execute_activity(
            write_skill_files,
            args=[spec, test_cases, Path("kubani/skills/_development")],
            start_to_close_timeout=timedelta(minutes=1),
        )

        self._state.skill_path = skill_path
        self._state.skill_name = spec.get("name", self._state.skill_name)

    async def _run_iteration(self, input: SkillAutoInput) -> None:
        """Run one eval-improve iteration."""
        self._state.iteration += 1

        # Check for pause
        if self._paused:
            await workflow.wait_condition(lambda: not self._paused or self._cancelled)
            if self._cancelled:
                return

        # Run evaluation
        metrics = await workflow.execute_activity(
            run_evaluation,
            args=[self._state.skill_path],
            start_to_close_timeout=timedelta(minutes=30),
            heartbeat_timeout=timedelta(minutes=5),
            retry_policy=DEFAULT_RETRY_POLICY,
        )

        # Compute score
        score = compute_score(metrics)
        improved = score > self._state.best_score

        # Update best version if improved
        if improved:
            skill_content = Path(self._state.skill_path, "SKILL.md").read_text()
            test_content = Path(self._state.skill_path, "test_cases.yaml").read_text()
            self._state.best_version = SkillVersion(
                content=skill_content,
                test_cases=test_content,
                metrics=metrics,
                iteration=self._state.iteration,
            )
            self._state.best_score = score

        # Determine action
        action = self._determine_action(input, metrics, score, improved)

        # Record iteration
        self._state.history.append(IterationResult(
            iteration=self._state.iteration,
            metrics=metrics,
            score=score,
            improved=improved,
            action=action,
        ))

        # Notify progress
        if input.notify:
            await self._notify("iteration_complete", metrics=metrics)

        # Check for review pause
        if input.review_each_iteration and action == "continue":
            self._paused = True
            self._state.status = "paused"
            await workflow.wait_condition(lambda: not self._paused or self._cancelled)

        # Run improvement if continuing
        if action == "continue" and not self._cancelled:
            # Revert to best if this iteration regressed
            if not improved and self._state.best_version:
                Path(self._state.skill_path, "SKILL.md").write_text(
                    self._state.best_version.content
                )

            await workflow.execute_activity(
                run_improvement,
                args=[self._state.skill_path, {"accuracy": metrics.accuracy}],
                start_to_close_timeout=timedelta(minutes=10),
                retry_policy=DEFAULT_RETRY_POLICY,
            )

    def _determine_action(
        self,
        input: SkillAutoInput,
        metrics: EvalMetrics,
        score: float,
        improved: bool,
    ) -> str:
        """Determine what action to take after evaluation."""
        if metrics.accuracy >= input.target_accuracy:
            return "stop_success"
        if self._state.iteration >= input.max_iterations:
            return "stop_cap"
        if len(self._state.history) >= 2 and is_plateau(self._state.history):
            return "stop_plateau"
        if not improved and len(self._state.history) >= 2:
            prev_score = self._state.history[-1].score if self._state.history else 0
            if prev_score > 0 and (prev_score - score) / prev_score > 0.2:
                return "stop_regression"
        return "continue"

    async def _notify(
        self,
        event: str,
        metrics: EvalMetrics | None = None,
        error: str | None = None,
    ) -> None:
        """Send Discord notification."""
        await workflow.execute_activity(
            send_notification,
            args=["skill-notifications", event, self._state, metrics, error],
            start_to_close_timeout=timedelta(seconds=30),
        )

    def _build_result(self) -> SkillAutoResult:
        """Build final result from state."""
        last_action = self._state.history[-1].action if self._state.history else "unknown"

        self._state.status = "completed"
        return SkillAutoResult(
            success=last_action == "stop_success",
            skill_path=self._state.skill_path,
            final_metrics=self._state.best_version.metrics if self._state.best_version else None,
            iterations_completed=self._state.iteration,
            stop_reason=last_action,
        )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/workflows/skill_auto/test_workflow.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add kubani/workflows/skill_auto/workflow.py tests/workflows/skill_auto/test_workflow.py
git commit -m "feat(skill-auto): implement SkillAutoWorkflow

- Full iteration loop with eval → improve → repeat
- Pause/resume/cancel signals
- State queries for progress monitoring
- Discord notifications at key events
- Regression detection with revert to best"
```

---

## Phase 5: CLI Integration

### Task 5.1: Add `skill auto` Command

**Files:**
- Modify: `platform/cli/src/kubani_dev/commands/skill.py`
- Test: Integration test (manual)

**Step 1: Add the command**

Add after line ~1786 in skill.py:

```python
@skill.command("auto")
@click.option("--description", "-d", required=True, help="Description of the skill to create")
@click.option("--improve", "-i", "skill_path", help="Path to existing skill to improve (instead of creating new)")
@click.option("--seed-tests", help="Path to seed test cases file")
@click.option("--max-iterations", default=5, type=int, help="Maximum improvement iterations")
@click.option("--target-accuracy", default=80, type=int, help="Target accuracy percentage")
@click.option("--review-each-iteration", is_flag=True, help="Pause for review after each iteration")
@click.option("--no-promote", is_flag=True, help="Skip promotion step")
@click.option("--no-notify", is_flag=True, help="Disable Discord notifications")
@click.option("--allow-overlap", is_flag=True, help="Allow creation even if overlap detected")
@click.option("--background", is_flag=True, help="Run as background Temporal workflow")
@click.option("--temporal", default="cluster", type=click.Choice(["cluster", "local"]), help="Temporal instance to use")
def auto_skill(
    description: str,
    skill_path: str | None,
    seed_tests: str | None,
    max_iterations: int,
    target_accuracy: int,
    review_each_iteration: bool,
    no_promote: bool,
    no_notify: bool,
    allow_overlap: bool,
    background: bool,
    temporal: str,
):
    """
    Autonomously create and improve a skill.

    Creates a skill from description, evaluates it, improves based on feedback,
    and repeats until quality goals are met or iteration limit reached.

    Examples:

        # Create new skill
        kubani-dev skill auto -d "A skill that diagnoses OOMKilled pods"

        # Improve existing skill
        kubani-dev skill auto -d "Improve accuracy" --improve kubani/skills/_development/oom-diagnostics

        # Run in background
        kubani-dev skill auto -d "..." --background
    """
    import asyncio
    from kubani.workflows.skill_auto.models import SkillAutoInput

    input = SkillAutoInput(
        description=description,
        mode="improve" if skill_path else "create",
        skill_path=skill_path,
        seed_tests_path=seed_tests,
        max_iterations=max_iterations,
        target_accuracy=target_accuracy / 100.0,
        review_each_iteration=review_each_iteration,
        skip_promotion=no_promote,
        notify=not no_notify,
        allow_overlap=allow_overlap,
    )

    if background:
        asyncio.run(_run_auto_background(input, temporal))
    else:
        asyncio.run(_run_auto_foreground(input, temporal))


async def _run_auto_foreground(input: "SkillAutoInput", temporal: str):
    """Run auto workflow in foreground with streaming progress."""
    from temporalio.client import Client
    from kubani.workflows.skill_auto.workflow import SkillAutoWorkflow
    import os

    # Connect to Temporal
    host = "localhost:7233" if temporal == "local" else os.environ.get("TEMPORAL_HOST", "temporal.almckay.io:7233")
    client = await Client.connect(host)

    # Start workflow
    workflow_id = f"skill-auto-{input.skill_path or 'new'}-{int(time.time())}"
    handle = await client.start_workflow(
        SkillAutoWorkflow.run,
        input,
        id=workflow_id,
        task_queue="skill-development",
    )

    info(f"Started workflow: {workflow_id}")

    # Poll for progress
    import time
    last_iteration = 0

    with spinner("Running auto skill development...") as sp:
        while True:
            try:
                state = await handle.query(SkillAutoWorkflow.get_state)

                if state.iteration > last_iteration:
                    sp.text = f"Iteration {state.iteration}: {state.status} (best: {state.best_score:.2f})"
                    last_iteration = state.iteration

                if state.status in ("completed", "failed"):
                    break

                await asyncio.sleep(2)
            except Exception:
                await asyncio.sleep(5)

    # Get result
    result = await handle.result()

    if result.success:
        success(f"Completed in {result.iterations_completed} iterations")
        success(f"Final accuracy: {result.final_metrics.accuracy * 100:.0f}%")
        success(f"Skill path: {result.skill_path}")
    else:
        error(f"Failed: {result.stop_reason}")
        if result.error:
            error(result.error)


async def _run_auto_background(input: "SkillAutoInput", temporal: str):
    """Start auto workflow in background."""
    from temporalio.client import Client
    from kubani.workflows.skill_auto.workflow import SkillAutoWorkflow
    import os

    host = "localhost:7233" if temporal == "local" else os.environ.get("TEMPORAL_HOST", "temporal.almckay.io:7233")
    client = await Client.connect(host)

    workflow_id = f"skill-auto-{input.skill_path or 'new'}-{int(time.time())}"
    handle = await client.start_workflow(
        SkillAutoWorkflow.run,
        input,
        id=workflow_id,
        task_queue="skill-development",
    )

    success(f"Started background workflow: {workflow_id}")
    info(f"Monitor with: kubani-dev skill auto-status {workflow_id}")
```

**Step 2: Add `skill auto-status` command**

```python
@skill.command("auto-status")
@click.argument("workflow_id")
@click.option("--temporal", default="cluster", type=click.Choice(["cluster", "local"]))
def auto_status(workflow_id: str, temporal: str):
    """Check status of a running auto workflow."""
    import asyncio
    asyncio.run(_check_auto_status(workflow_id, temporal))


async def _check_auto_status(workflow_id: str, temporal: str):
    """Query workflow status."""
    from temporalio.client import Client
    from kubani.workflows.skill_auto.workflow import SkillAutoWorkflow
    import os

    host = "localhost:7233" if temporal == "local" else os.environ.get("TEMPORAL_HOST", "temporal.almckay.io:7233")
    client = await Client.connect(host)

    handle = client.get_workflow_handle(workflow_id)

    try:
        state = await handle.query(SkillAutoWorkflow.get_state)

        print(f"Workflow: {workflow_id}")
        print(f"Status: {state.status}")
        print(f"Skill: {state.skill_name}")
        print(f"Iteration: {state.iteration}")
        print(f"Best score: {state.best_score:.2f}")

        if state.overlap_warning:
            warning(f"Overlap warning: {state.overlap_warning.overlapping_skills}")

        if state.error:
            error(f"Error: {state.error}")

    except Exception as e:
        error(f"Failed to query workflow: {e}")
```

**Step 3: Test manually**

```bash
# Verify command appears
kubani-dev skill auto --help

# Dry run (will fail without Temporal, but verifies parsing)
kubani-dev skill auto -d "Test skill" --background 2>&1 | head
```

**Step 4: Commit**

```bash
git add platform/cli/src/kubani_dev/commands/skill.py
git commit -m "feat(cli): add skill auto and auto-status commands

- skill auto: create/improve skills autonomously
- skill auto-status: query running workflow progress
- Foreground mode with streaming progress
- Background mode with Temporal workflow"
```

---

## Phase 6: Worker Setup

### Task 6.1: Create Skill Auto Worker

**Files:**
- Create: `kubani/workflows/skill_auto/worker.py`

**Step 1: Write worker entry point**

```python
# kubani/workflows/skill_auto/worker.py
"""Temporal worker for Skill Auto workflows."""

import asyncio
import logging
import os

from temporalio.client import Client
from temporalio.worker import Worker

from kubani.workflows.skill_auto.activities import (
    detect_skill_overlap,
    generate_test_cases,
    infer_skill_structure,
    load_existing_skills,
    run_evaluation,
    run_improvement,
    send_notification,
    write_skill_files,
)
from kubani.workflows.skill_auto.workflow import SkillAutoWorkflow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def run_worker() -> None:
    """Run the Skill Auto workflow worker."""
    temporal_host = os.environ.get("TEMPORAL_HOST", "localhost:7233")
    temporal_namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")

    logger.info(f"Connecting to Temporal at {temporal_host}")

    client = await Client.connect(
        temporal_host,
        namespace=temporal_namespace,
    )

    worker = Worker(
        client,
        task_queue="skill-development",
        workflows=[SkillAutoWorkflow],
        activities=[
            detect_skill_overlap,
            generate_test_cases,
            infer_skill_structure,
            load_existing_skills,
            run_evaluation,
            run_improvement,
            send_notification,
            write_skill_files,
        ],
    )

    logger.info("Starting Skill Auto worker on queue: skill-development")

    try:
        await worker.run()
    except KeyboardInterrupt:
        logger.info("Shutting down worker...")


def main() -> None:
    """Entry point."""
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
```

**Step 2: Add entry point to pyproject.toml**

Add to `kubani/pyproject.toml` under `[project.scripts]`:

```toml
skill-auto-worker = "kubani.workflows.skill_auto.worker:main"
```

**Step 3: Commit**

```bash
git add kubani/workflows/skill_auto/worker.py kubani/pyproject.toml
git commit -m "feat(skill-auto): add Temporal worker for skill development

- Registers all activities and SkillAutoWorkflow
- Task queue: skill-development
- Entry point: skill-auto-worker"
```

---

## Summary

This implementation plan covers:

1. **Phase 1**: Core data models (SkillAutoInput, SkillAutoState, EvalMetrics, etc.)
2. **Phase 2**: Activities (overlap detection, skill creation, evaluation, improvement, notifications)
3. **Phase 3**: Temporal activity registration
4. **Phase 4**: SkillAutoWorkflow with iteration loop, signals, queries
5. **Phase 5**: CLI commands (skill auto, skill auto-status)
6. **Phase 6**: Temporal worker setup

**Not covered (future phases)**:
- PromoteWorkflow with Discord approval reactions
- Progressive test hardening
- Full evaluation mode support
- Integration tests with live Temporal

---

**Plan complete and saved to `docs/plans/2026-01-24-auto-skill-development-implementation.md`.**

Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?
