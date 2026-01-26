# Skill Auto Temporal Workflow Troubleshooting

**Status:** Draft
**Created:** 2026-01-26
**Author:** Claude Code

## Problem Statement

The skill-auto Temporal workflow fails with a `'metrics'` KeyError when running via the Temporal worker, even though the core logic works correctly when executed directly with Python.

### Symptoms

1. Workflow starts successfully and gets a workflow ID
2. Worker shows warnings about modules being imported after initial workflow load:
   ```
   Module kubani.workflows.skill_auto.domain.decisions was imported after initial workflow load
   Module kubani.workflows.skill_auto.domain.models was imported after initial workflow load
   Module kubani.workflows.skill_auto.domain.scoring was imported after initial workflow load
   ```
3. Workflow fails with `'metrics'` KeyError at `workflow.py:243`
4. The `run_evaluation` activity appears to return a result without the `metrics` key

### What Works

- All 185 unit tests pass
- Direct Python execution of the evaluation pipeline works correctly
- The assertion checker fix allows evaluations to complete with proper accuracy scoring
- Full improvement workflow works when run via direct Python calls (bypassing Temporal)

## Investigation Plan

### Phase 1: Activity Result Inspection

**Goal:** Understand what `run_evaluation` activity actually returns vs. what workflow expects

1. **Add comprehensive logging to activities**
   - Log the exact return value of `run_evaluation` before returning
   - Log the activity input parameters
   - Verify the return dict structure matches what workflow expects

2. **Check Temporal UI for activity details**
   - View activity inputs/outputs in Temporal Web UI
   - Check for any serialization issues
   - Look for activity retries or failures

3. **Test activity in isolation**
   ```python
   # Run just the activity function directly
   from kubani.workflows.skill_auto.activities import run_evaluation
   result = await run_evaluation(...)
   print(result.keys())  # Should include 'metrics'
   ```

### Phase 2: Workflow Sandbox Investigation

**Goal:** Understand if Temporal's workflow sandbox is causing issues

1. **Investigate sandbox import warnings**
   - The warnings about modules imported after workflow load suggest sandbox issues
   - Check if domain modules need to be pre-imported in workflow
   - Review Temporal sandbox documentation for best practices

2. **Test with sandbox disabled**
   ```python
   # In worker.py, try running without sandbox
   Worker(
       client,
       task_queue="skill-development",
       workflows=[SkillAutoWorkflow],
       activities=[...],
       workflow_runner=SandboxedWorkflowRunner(
           restrictions=SandboxRestrictions(
               invalid_module_members={},  # Less restrictive
           )
       ),
   )
   ```

3. **Check module import order**
   - Ensure all domain modules are imported at workflow module level
   - Move imports from inside functions to top of file

### Phase 3: Serialization Analysis

**Goal:** Verify data serializes correctly between activities and workflow

1. **Check return type annotations**
   - `run_evaluation` returns `dict[str, Any]`
   - Verify all values in dict are JSON-serializable
   - Check if Pydantic models are being returned instead of dicts

2. **Add explicit dict conversion**
   ```python
   # In run_evaluation activity
   result = {
       "metrics": {
           "accuracy": float(metrics.accuracy),
           "latency_p50_ms": float(metrics.latency_p50_ms),
           ...
       },
       "test_results": [r.model_dump() for r in test_results],
       ...
   }
   return result
   ```

3. **Test with simple activity first**
   - Create a minimal test activity that returns `{"metrics": {}}`
   - Verify workflow can receive it
   - Incrementally add complexity

### Phase 4: Worker Configuration Review

**Goal:** Ensure worker is configured correctly

1. **Check worker task queue**
   - Verify worker and workflow use same task queue ("skill-development")
   - Confirm no typos in queue names

2. **Review worker lifecycle**
   - Check worker stays running during workflow execution
   - Look for worker crashes or disconnections
   - Monitor Temporal server logs

3. **Verify activity registration**
   - Confirm all activities are registered with worker
   - Check for duplicate activity registrations
   - Verify activity function signatures match

## Potential Root Causes

### 1. Sandbox Import Issue (Most Likely)
The sandbox warnings suggest domain modules aren't properly handled. Temporal's workflow sandbox restricts imports to ensure determinism, but this may be preventing activities from returning proper results.

**Fix:** Pre-import all domain modules in workflow file, or adjust sandbox restrictions.

### 2. Activity Exception Swallowed
The activity might be raising an exception that's being caught and returning incomplete data.

**Fix:** Add try/except logging around entire activity body, ensure all code paths return complete dict.

### 3. Serialization Issue with Pydantic Models
`EvaluationMetrics` is a Pydantic model. If it's being returned directly instead of as a dict, serialization might fail silently.

**Fix:** Explicitly call `.model_dump()` on all Pydantic models before returning.

### 4. Activity Timeout
Activity might be timing out before completion, causing partial results.

**Fix:** Increase activity timeout, add heartbeating for long-running evaluations.

## Implementation Steps

### Step 1: Add Diagnostic Logging
```python
# In activities.py run_evaluation
import json
logger.info(f"run_evaluation: Returning result with keys: {list(result.keys())}")
logger.info(f"run_evaluation: Result preview: {json.dumps(result, default=str)[:500]}")
```

### Step 2: Fix Sandbox Imports
```python
# At top of workflow.py, add explicit imports
from kubani.workflows.skill_auto.domain.decisions import should_stop_iteration
from kubani.workflows.skill_auto.domain.models import IterationState
from kubani.workflows.skill_auto.domain.scoring import calculate_composite_score
```

### Step 3: Ensure Dict Serialization
```python
# In activities.py
def _serialize_result(result: dict) -> dict:
    """Ensure all values are JSON-serializable."""
    return json.loads(json.dumps(result, default=str))
```

### Step 4: Add Activity Heartbeating
```python
# For long-running evaluations
activity.heartbeat("Running evaluation...")
```

## Success Criteria

1. Workflow completes full iteration cycle without `'metrics'` error
2. No sandbox import warnings
3. Activity results contain expected structure
4. Workflow can perform multiple improvement iterations

## Testing Plan

1. **Unit test:** Run `just test` to ensure no regressions
2. **Integration test:** Run workflow via CLI with test skill
3. **E2E test:** Create real skill and verify full improvement cycle

## References

- Temporal Python SDK sandbox docs: https://docs.temporal.io/develop/python/sandbox
- Pydantic serialization: https://docs.pydantic.dev/latest/concepts/serialization/
- Current workflow: `kubani/workflows/skill_auto/workflow.py`
- Current activities: `kubani/workflows/skill_auto/activities.py`
