# Auto Mode for Skill Development

**Date:** 2026-01-24
**Status:** Implementation Complete
**Author:** Claude (with user collaboration)

---

## Overview

Auto mode chains the skill development workflow autonomously: `create → eval → improve → repeat` until quality goals are met or limits reached. It enables developers to kick off skill creation with just a description and check back when it's ready, while also supporting programmatic invocation from agents and the continuous learning system.

### Use Cases

1. **Developer convenience** - Provide a description, auto mode handles the rest
2. **Programmatic creation** - Agents/learning system can trigger skill synthesis
3. **Future: Bulk generation** - Design supports batch operations

---

## Entry Points

### CLI - New Skill

```bash
kubani-dev skill auto --description "A skill that helps diagnose OOMKilled pods"
```

### CLI - Improve Existing Skill

```bash
kubani-dev skill auto --improve kubani/skills/_development/oom-diagnostics
```

### Programmatic - Temporal Workflow

```python
await client.start_workflow(
    SkillAutoWorkflow.run,
    SkillAutoInput(description="...", mode="create"),
    id="skill-auto-oom-diagnostics",
    task_queue="skill-development",
)
```

### Optional Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--seed-tests <file>` | None | Provide initial test cases |
| `--max-iterations <n>` | 5 | Hard cap on improvement cycles |
| `--target-accuracy <pct>` | 80 | Quality threshold to stop |
| `--review-each-iteration` | False | Pause for approval after each cycle |
| `--no-promote` | False | Skip promotion step |
| `--no-notify` | False | Disable Discord notifications (default: notify to `skill-notifications`) |
| `--background` | False | Run as background Temporal workflow |
| `--allow-overlap` | False | Allow creation/promotion even if overlap detected |

---

## Iteration Loop

```
┌─────────────────────────────────────────────────────────────┐
│                    SkillAutoWorkflow                        │
├─────────────────────────────────────────────────────────────┤
│  1. CreateSkillWorkflow (if new) OR load existing skill     │
│     └─ Generates: SKILL.md, test_cases.yaml, metadata.json  │
│                                                             │
│  2. Loop until done:                                        │
│     ├─ EvalWorkflow (quick mode by default)                 │
│     │   └─ Returns: accuracy, latency, critic feedback      │
│     │                                                       │
│     ├─ Check stopping criteria (see below)                  │
│     │   └─ If met → exit loop                               │
│     │                                                       │
│     ├─ If --review-each-iteration → await human signal      │
│     │                                                       │
│     └─ ImproveWorkflow                                      │
│         └─ Updates SKILL.md based on eval feedback          │
│                                                             │
│  3. If promotion approved → PromoteWorkflow                 │
└─────────────────────────────────────────────────────────────┘
```

### Stopping Criteria

| Condition | Action |
|-----------|--------|
| `accuracy >= target AND latency acceptable` | Success - exit loop |
| `iterations >= max_iterations` | Hard cap - exit with warning |
| `plateau detected` | Diminishing returns - exit early |
| `accuracy dropped significantly` | Regression - pause for review |

### Quality Score

Improvement is measured across both accuracy and latency:

```
score = accuracy * 0.7 + (1 / normalized_latency) * 0.3
```

Plateau detected when `score_improvement < 2%` for 2 consecutive iterations.

### Improve From Best (Not Latest)

The system always improves from the best-known version, not the most recent:

```python
@dataclass
class SkillAutoState:
    skill_path: str
    iteration: int = 0
    history: list[IterationResult] = field(default_factory=list)
    best_version: SkillVersion | None = None
    best_score: float = 0.0
    status: str = "running"

@dataclass
class SkillVersion:
    content: str  # SKILL.md content
    test_cases: str  # test_cases.yaml content
    metrics: EvalMetrics
    iteration: int
```

After each evaluation:
1. Compute score for current version
2. If `score > best_score`: update best_version
3. If `score < best_score` (regression): revert to best_version, improve from there
4. Regressions are logged but discarded

---

## Temporal Workflow Architecture

### Workflow Hierarchy

```
SkillAutoWorkflow (parent orchestrator)
├── check_skill_overlap (activity) - warns if overlap with existing skills
│
├── CreateSkillWorkflow (child) - only for new skills
│   ├── infer_skill_structure (activity)
│   ├── generate_test_cases (activity)
│   └── write_skill_files (activity)
│
├── EvalWorkflow (child) - runs each iteration
│   ├── load_skill (activity)
│   ├── run_test_cases (activity) - with heartbeating
│   ├── run_critic (activity)
│   └── compute_metrics (activity)
│
├── ImproveWorkflow (child) - runs after eval if not stopping
│   ├── analyze_failures (activity)
│   ├── generate_improvements (activity)
│   └── apply_improvements (activity)
│
└── PromoteWorkflow (child) - only if approved
    ├── check_promotion_overlap (activity) - blocks if overlap with production
    ├── await_approval (activity)
    ├── promote_skill (activity)
    └── sync_registry (activity)
```

### Signals Supported

- `pause` - Stop after current phase completes
- `resume` - Continue from paused state
- `cancel` - Abort and clean up
- `approve_promotion` - Gate for production promotion

### Why Sub-Workflows

Sub-workflows provide:
- Independent queryability per phase
- Natural resume points after failures
- Cleaner separation of concerns
- No heartbeat concerns for long-running operations

---

## Error Handling & Resilience

### Network/LLM Failures

| Failure Type | Handling |
|--------------|----------|
| LLM timeout | Activity retries 3x with exponential backoff (10s, 30s, 90s) |
| LLM rate limit | Backoff with jitter, respect retry-after header |
| Network error | Retry at activity level, workflow continues from checkpoint |
| Disk write failure | Fail activity, workflow pauses for investigation |

### Evaluation Failures

| Scenario | Action |
|----------|--------|
| All tests fail on first eval | Pause workflow, notify Discord |
| Accuracy regresses >20% | Pause workflow, notify Discord |
| Critic returns low confidence (<0.3) | Flag in metrics, continue |
| Test case itself is invalid | Log warning, exclude from accuracy |

### Retry Policy

```python
retry_policy = RetryPolicy(
    initial_interval=timedelta(seconds=10),
    maximum_interval=timedelta(minutes=5),
    maximum_attempts=3,
    non_retryable_error_types=["SkillValidationError", "UserCancelled"],
)
```

### State Persistence

- Each iteration writes `iteration_N.json` to skill directory
- Parent workflow state is Temporal-durable
- On resume, workflow loads last completed iteration

---

## Test Generation Strategy

### For New Skills (No Seeds)

```
1. LLM infers skill structure from description
2. Generate 3-5 test cases covering:
   - Happy path (typical usage)
   - Edge case (boundary conditions)
   - Error case (invalid input handling)
3. Each test includes: input, expected_behavior, assertions
```

### For Existing Skills or With Seeds

- Load existing/seed test cases as starting point
- LLM expands with 2-3 additional cases

### Progressive Test Hardening

When plateau detected, before giving up:
1. Analyze passing vs failing tests
2. Generate 2 harder test cases targeting weaknesses
3. Re-run evaluation with expanded suite

---

## Progress Reporting & Observability

### Layer 1: CLI Streaming (Interactive)

```
🚀 Starting auto skill development...
   Skill: oom-diagnostics (inferred)
   Target: 80% accuracy | Max iterations: 5

📝 Creating skill structure...
   ✓ Generated SKILL.md (450 tokens)
   ✓ Generated 4 test cases

🔄 Iteration 1/5
   ├─ Test 1: ✓ passed (2.3s)
   ├─ Test 2: ✗ failed - missing memory limit check
   └─ Accuracy: 75% | Latency: 2.1s | Score: 0.72

✅ Complete after 3 iterations
   Final: 85% accuracy, 1.9s latency
```

### Layer 2: Status Queries (Programmatic)

```bash
$ kubani-dev skill auto-status oom-diagnostics

Workflow: skill-auto-oom-diagnostics
Status: running
Iteration: 2/5
Best score: 0.72 (iteration 1)
```

### Layer 3: Discord Notifications

```
#skill-notifications

✅ Skill Auto Complete: oom-diagnostics
├─ Iterations: 3
├─ Final: 85% accuracy, 1.9s latency
└─ 🔔 React ✅ to approve promotion, ❌ to reject
```

---

## CLI & Temporal Integration

### Execution Modes

```bash
# Foreground (default) - streams progress, blocks
kubani-dev skill auto --description "..."

# Background - returns immediately
kubani-dev skill auto --description "..." --background

# Background with local Temporal
kubani-dev skill auto --description "..." --background --temporal local
```

### CLI Flag to Temporal Mapping

| CLI Flag | Temporal Equivalent |
|----------|---------------------|
| `--max-iterations 5` | `SkillAutoInput.max_iterations = 5` |
| `--target-accuracy 80` | `SkillAutoInput.target_accuracy = 0.80` |
| `--review-each-iteration` | Workflow pauses, awaits `resume` signal |
| `Ctrl+C` in foreground | Sends `cancel` signal to workflow |

### Foreground Implementation

```python
async def run_foreground(input: SkillAutoInput):
    handle = await client.start_workflow(SkillAutoWorkflow.run, input, ...)

    while True:
        state = await handle.query(SkillAutoWorkflow.get_state)
        render_progress(state)

        if state.status in ("completed", "failed", "paused"):
            break
        await asyncio.sleep(2)

    return await handle.result()
```

### Programmatic Invocation

```python
from kubani.framework.temporal import get_temporal_client
from kubani.workflows.skill_auto import SkillAutoWorkflow, SkillAutoInput

client = await get_temporal_client()

handle = await client.start_workflow(
    SkillAutoWorkflow.run,
    SkillAutoInput(
        description="A skill that helps diagnose OOMKilled pods",
        mode="create",
        max_iterations=5,
        notify_channel="skill-notifications",
    ),
    id=f"skill-auto-{skill_name}",
    task_queue="skill-development",
)

# Query, signal, etc.
state = await handle.query(SkillAutoWorkflow.get_state)
await handle.signal(SkillAutoWorkflow.pause)
```

---

## Security & Permissions

### Skill Execution Sandboxing

| Concern | Mitigation |
|---------|------------|
| LLM-generated code | Skills are prompts, not executable code |
| Filesystem access | Writes only to `_development/`, promotion requires approval |
| Resource exhaustion | Hard caps: 5 iterations, 30 min timeout, token limits |
| Infinite loops | Plateau detection + hard cap |

### Promotion Gates

```
Auto mode creates/improves in _development/
              │
              ▼
    ┌─────────────────────┐
    │  Promotion Request  │
    │  (Discord message)  │
    └─────────────────────┘
              │
    ┌─────────┴─────────┐
    ▼                   ▼
 ✅ Approve         ❌ Reject
    │                   │
    ▼                   ▼
 Production         Stay in dev
```

### Allowed Tools

Auto-generated skills inherit default allowed_tools:
- Read-only: file reading, search, web fetch
- No destructive: no file writes, no bash, no system modifications

Dangerous tools require manual review before promotion.

### Audit Trail

- `iteration_N.json` for each iteration
- Temporal workflow history
- Discord notification record
- Registry metadata: `created_by: "auto-mode"`

---

## Skill Overlap Detection

Prevents duplicate or conflicting skills by checking for overlap before creation and blocking promotion of overlapping skills.

### Detection Mechanism

```python
async def detect_skill_overlap(
    description: str,
    existing_skills: list[SkillMetadata],
) -> OverlapResult:
    """
    Uses LLM to compare new skill description against existing skills.
    Returns overlap assessment with confidence and reasoning.
    """
    return OverlapResult(
        has_overlap: bool,
        confidence: float,  # 0.0 - 1.0
        overlapping_skills: list[str],  # skill names
        reasoning: str,
        recommendation: str,  # "proceed", "merge", "abort"
    )
```

### Behavior by Phase

| Phase | Overlap Detected | Action |
|-------|------------------|--------|
| Creation (new skill) | Warning only | Log warning, notify Discord, continue to `_development/` |
| Improvement (existing) | N/A | Skip check - skill already exists |
| Promotion | Exception | Raise `SkillOverlapError`, block promotion |

### Creation Phase Warning

```
⚠️  Potential overlap detected!
    New skill: oom-diagnostics
    Overlaps with: memory-troubleshooting (78% confidence)
    Reasoning: Both skills diagnose memory-related pod failures

    Proceeding to _development/ - review before promotion.
```

### Promotion Phase Block

```python
class SkillOverlapError(Exception):
    """Raised when attempting to promote a skill that overlaps with production skills."""

    def __init__(self, skill_name: str, overlapping: list[str], reasoning: str):
        self.skill_name = skill_name
        self.overlapping = overlapping
        self.reasoning = reasoning
        super().__init__(
            f"Cannot promote '{skill_name}': overlaps with {overlapping}. "
            f"Reason: {reasoning}. "
            "Consider merging or differentiating the skill."
        )
```

### Workflow Integration

```
SkillAutoWorkflow
├── check_skill_overlap (activity) ← NEW: runs before CreateSkillWorkflow
│   ├── Load all existing skills from kubani/skills/
│   ├── Compare description against each skill's purpose/triggers
│   ├── If overlap detected → log warning, continue
│   └── Store overlap info in state for promotion check
│
├── CreateSkillWorkflow (child)
│   ...
│
└── PromoteWorkflow (child)
    ├── check_promotion_overlap (activity) ← NEW: blocks if overlap
    │   ├── Re-check against production skills only
    │   ├── If overlap → raise SkillOverlapError
    │   └── If clear → proceed
    ├── await_approval (activity)
    ...
```

### Override Flag

For cases where overlap is intentional (e.g., replacing an old skill):

```bash
# CLI
kubani-dev skill auto --description "..." --allow-overlap

# Temporal
SkillAutoInput(description="...", allow_overlap=True)
```

When `--allow-overlap` is set:
- Creation: No warning
- Promotion: Warning instead of exception, requires explicit approval in Discord

---

## Implementation Roadmap

### Phase 1: Core Workflow ✅
- [x] Define `SkillAutoInput` and `SkillAutoState` dataclasses
- [x] Implement `SkillAutoWorkflow` parent orchestrator
- [x] Implement `check_skill_overlap` activity (pre-creation warning)
- [x] Implement `CreateSkillWorkflow` child
- [x] Implement `EvalWorkflow` child (adapt existing evaluator)
- [x] Implement `ImproveWorkflow` child (adapt existing improver)

### Phase 2: CLI Integration ✅
- [x] Add `skill auto` command with all flags
- [x] Implement foreground polling/streaming
- [x] Add `skill auto-status` command
- [x] Handle Ctrl+C → cancel signal

### Phase 3: Observability ✅
- [x] Discord notification integration
- [x] Iteration result logging
- [x] Status file for programmatic queries

### Phase 4: Promotion Flow ✅
- [x] Implement `check_promotion_overlap` activity (blocks if overlap)
- [x] Implement `PromoteWorkflow` child
- [x] Discord approval reaction handling
- [x] Registry sync on promotion

### Phase 5: Hardening ✅
- [x] Progressive test hardening on plateau
- [x] Regression detection and revert logic
- [x] Comprehensive error handling

---

## Open Questions

1. **Test case quality**: How do we validate that LLM-generated test cases are actually good tests? May need human review of test cases before first eval.

2. **Model selection**: Should auto mode use the same model for skill execution as it does for improvement suggestions? Or use a stronger model for meta-tasks?

3. **Cost tracking**: Should we track and report token usage/cost per auto run?
