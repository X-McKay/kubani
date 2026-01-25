---
name: skill-auto
description: Autonomous skill development workflow - create, evaluate, and improve skills automatically until quality goals are met
---

# Autonomous Skill Development

Auto mode chains the skill development workflow: `create → eval → improve → repeat` until quality goals are met or limits reached.

## Quick Start

```bash
# Create a new skill from description
kubani-dev skill auto --description "A skill that helps diagnose OOMKilled pods"

# Improve an existing skill
kubani-dev skill auto --improve kubani/skills/_development/oom-diagnostics

# Run in background (returns immediately)
kubani-dev skill auto --description "..." --background
```

## Workflow Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    SkillAutoWorkflow                        │
├─────────────────────────────────────────────────────────────┤
│  1. Check for overlap with existing skills                  │
│     └─ Warns if similar skill exists                        │
│                                                             │
│  2. Create skill (if new)                                   │
│     └─ Generates: SKILL.md, test_cases.yaml, metadata.json  │
│                                                             │
│  3. Iteration loop:                                         │
│     ├─ Evaluate skill against test cases                    │
│     ├─ Check stopping criteria                              │
│     │   └─ Success / Plateau / Max iterations / Regression  │
│     └─ Improve based on feedback                            │
│                                                             │
│  4. Promotion (if approved)                                 │
│     └─ Move to production, sync to registry                 │
└─────────────────────────────────────────────────────────────┘
```

## CLI Options

| Option | Default | Description |
|--------|---------|-------------|
| `--description` | Required | Natural language description of the skill |
| `--improve <path>` | - | Improve existing skill instead of creating new |
| `--max-iterations` | 5 | Maximum improvement cycles |
| `--target-accuracy` | 80 | Accuracy percentage to stop at |
| `--seed-tests <file>` | - | Provide initial test cases |
| `--review-each-iteration` | false | Pause for approval after each cycle |
| `--no-promote` | false | Skip promotion step |
| `--no-notify` | false | Disable Discord notifications |
| `--allow-overlap` | false | Allow creation even if overlap detected |
| `--background` | false | Run as background Temporal workflow |

## Examples

### Create a New Skill

```bash
# Basic creation
kubani-dev skill auto --description "A skill that analyzes Kubernetes pod logs for error patterns"

# With seed tests
kubani-dev skill auto \
  --description "A skill that monitors deployment rollout status" \
  --seed-tests my-tests.yaml

# Higher quality target
kubani-dev skill auto \
  --description "A skill that recommends resource limits" \
  --target-accuracy 90 \
  --max-iterations 10
```

### Improve Existing Skill

```bash
# Improve a development skill
kubani-dev skill auto --improve kubani/skills/_development/pod-diagnostics

# Improve with review gates
kubani-dev skill auto \
  --improve kubani/skills/_development/log-analyzer \
  --review-each-iteration
```

### Background Execution

```bash
# Start in background
kubani-dev skill auto --description "..." --background

# Check status
kubani-dev skill auto-status <workflow-id>
```

## Programmatic Usage

Start the workflow directly via Temporal:

```python
from kubani.workflows.skill_auto import SkillAutoWorkflow, SkillAutoInput
from temporalio.client import Client

client = await Client.connect("temporal.almckay.io:7233")

handle = await client.start_workflow(
    SkillAutoWorkflow.run,
    SkillAutoInput(
        description="A skill that helps diagnose OOMKilled pods",
        mode="create",
        max_iterations=5,
        target_accuracy=0.80,
        notify_channel="skill-notifications",
    ),
    id="skill-auto-oom-diagnostics",
    task_queue="skill-development",
)

# Query state
state = await handle.query(SkillAutoWorkflow.get_state)
print(f"Iteration: {state.iteration}, Best score: {state.best_score}")

# Signal control
await handle.signal(SkillAutoWorkflow.pause)
await handle.signal(SkillAutoWorkflow.resume)
await handle.signal(SkillAutoWorkflow.cancel)
```

## Stopping Criteria

| Condition | Action |
|-----------|--------|
| `accuracy >= target` | Success - workflow completes |
| `iterations >= max` | Hard cap - exits with warning |
| `score improvement < 2%` for 2 iterations | Plateau detected - exits early |
| `score dropped > 20%` from best | Regression - pauses for review |

## Quality Score

The composite score balances accuracy and latency:

```
score = accuracy * 0.7 + (baseline_latency / actual_latency) * 0.3
```

- Accuracy weighted at 70%
- Faster execution rewarded (30% weight)
- Baseline latency: 3000ms

## Promotion Flow

When skill development completes successfully:

1. **Overlap Check** - Verifies no conflict with production skills
2. **Discord Notification** - Posts promotion request with metrics
3. **Approval** - Wait for reaction (✅ approve, ❌ reject)
4. **Promotion** - Move from `_development/` to production category
5. **Registry Sync** - Register skill in central registry

```
Discord Message:
┌─────────────────────────────────────────┐
│ 🔔 Promotion Request: oom-diagnostics   │
├─────────────────────────────────────────┤
│ Accuracy: 88% | Tests: 8/9 | Latency: 1.2s │
│                                         │
│ React ✅ to approve, ❌ to reject       │
└─────────────────────────────────────────┘
```

## Progressive Test Hardening

When plateau is detected, before giving up:

1. Analyze which tests are failing and why
2. Generate 2 harder test cases targeting weaknesses
3. Re-run evaluation with expanded suite
4. Continue improvement if score improves

## Output Files

Skills are created in `kubani/skills/_development/<skill-name>/`:

```
kubani/skills/_development/oom-diagnostics/
├── SKILL.md           # Skill definition with frontmatter
├── test_cases.yaml    # Test cases for evaluation
├── metadata.json      # Creation metadata
├── iteration_1.json   # Iteration 1 results
├── iteration_2.json   # Iteration 2 results
└── ...
```

## Troubleshooting

### Workflow Not Starting

```bash
# Check Temporal is accessible
curl -s https://temporal.almckay.io/health

# Check worker is running
kubectl get pods -n ai-agents -l app=skill-auto-worker
```

### Low Accuracy After Max Iterations

- Review failing test cases in iteration files
- Consider providing seed tests with better coverage
- Increase `--max-iterations` for more improvement cycles
- Use `--review-each-iteration` to inspect intermediate results

### Promotion Blocked by Overlap

```bash
# Force promotion despite overlap (use carefully)
kubani-dev skill auto --improve <path> --allow-overlap
```

## See Also

- `/deployment` - Deploy skills and agents
- `/agent-evaluation` - Evaluation framework details
- `/continuous-learning` - How skills feed into learning system
