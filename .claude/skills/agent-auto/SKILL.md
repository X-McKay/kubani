---
name: agent-auto
description: Autonomous agent development workflow - draft, create skills, evaluate, and improve agents automatically until quality goals are met
---

# Autonomous Agent Development

The `agent-auto` workflow automates the complete agent creation lifecycle: `draft → create skills → write files → eval → improve → publish` until quality goals are met or limits reached.

## Quick Start

```bash
# Create a new agent from description
kubani-dev agent draft \
  --name pod-health-monitor \
  --description "An agent that monitors Kubernetes pod health and suggests remediation"

# With custom accuracy targets
kubani-dev agent draft \
  --name news-digest \
  --description "Aggregate news from multiple sources" \
  --target-accuracy 0.9 \
  --max-iterations 10

# Control child skill creation quality
kubani-dev agent draft \
  --name k8s-watcher \
  --description "Monitor Kubernetes resources" \
  --child-skill-max-iterations 2 \
  --child-skill-target-accuracy 0.6
```

## Workflow Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    AgentAutoWorkflow                        │
├─────────────────────────────────────────────────────────────┤
│  1. Draft Agent                                             │
│     ├─ Analyze requirements from description                │
│     ├─ Identify required skills                             │
│     └─ Generate initial agent structure                     │
│                                                             │
│  2. Create Missing Skills (via child workflows)             │
│     ├─ Start SkillAutoWorkflow for each missing skill       │
│     ├─ Wait for all child workflows to complete             │
│     └─ Fail parent if any child fails (critical)            │
│                                                             │
│  3. Write Agent Files                                       │
│     └─ Generate: worker.py, workflows.py, activities.py     │
│                                                             │
│  4. Eval-Improve Loop                                       │
│     ├─ Evaluate agent against test cases                    │
│     ├─ Calculate metrics (accuracy, precision, recall)      │
│     ├─ Analyze failures and generate improvements           │
│     └─ Apply improvements and repeat                        │
│                                                             │
│  5. Publish (if successful)                                 │
│     └─ Finalize agent and mark as ready for deployment      │
└─────────────────────────────────────────────────────────────┘
```

## Architecture

The workflow follows the **Functional Workflow Architecture** pattern with four layers:

### Domain Layer
Pure functions and models with no side effects:
- `domain/models.py` - Data structures (AgentSpec, EvaluationResult, etc.)
- `domain/metrics.py` - Pure metric calculations (precision, recall)
- `domain/analysis.py` - Requirement analysis and failure analysis

### Service Layer
Business logic with dependency injection:
- `services/drafting.py` - Agent drafting service
- `services/evaluation.py` - Agent evaluation service
- `services/protocols.py` - Interface definitions (LLMClient, AgentRunner)

### Activity Layer
Thin wrappers that instantiate services:
- `activities.py` - Temporal activities that delegate to services

### Workflow Layer
Orchestration and state management:
- `workflow.py` - Main AgentAutoWorkflow with phase management

## CLI Options

| Option | Default | Description |
|--------|---------|-------------|
| `--name`, `-n` | Required | Agent name |
| `--description`, `-d` | Required | Natural language description of the agent |
| `--target-accuracy` | 0.8 | Target evaluation accuracy (0.0-1.0) |
| `--max-iterations` | 5 | Maximum improvement iterations |
| `--child-skill-max-iterations` | 3 | Max iterations for auto-generated skills |
| `--child-skill-target-accuracy` | 0.70 | Target accuracy for auto-generated skills |
| `--non-interactive` | false | Don't wait for completion |
| `--temporal-address` | localhost:7233 | Temporal server address |

## Monitoring

Check workflow status:

```bash
# Human-readable status
kubani-dev agent status pod-health-monitor

# JSON output for scripting
kubani-dev agent status pod-health-monitor --json
```

Cancel a running workflow:

```bash
# With confirmation
kubani-dev agent cancel pod-health-monitor

# Force cancel
kubani-dev agent cancel pod-health-monitor --force
```

## Evaluation Metrics

The workflow tracks three key metrics:

- **Objective Accuracy**: Overall success rate across test cases
- **Skill Precision**: Of skills invoked, how many were correct?
- **Skill Recall**: Of skills needed, how many were invoked?

## Child Workflow Integration

When the agent requires skills that don't exist, the workflow automatically:

1. Identifies missing skills from the agent requirements
2. Starts a `SkillAutoWorkflow` child workflow for each missing skill
3. Waits for all child workflows to complete
4. **Fails the parent workflow if any child fails** (prevents incomplete agents)

You can control the quality/speed tradeoff for auto-generated skills:

```bash
# Fast but lower quality (for prototyping)
--child-skill-max-iterations 1 --child-skill-target-accuracy 0.5

# Slower but higher quality (for production)
--child-skill-max-iterations 5 --child-skill-target-accuracy 0.85
```

## Error Handling

### Child Skill Creation Failure

If a required skill cannot be created, the parent workflow will fail with:

```
Failed to create 2 required skill(s): k8s/pod/debug (timeout), k8s/node/inspect (accuracy not met)
```

This prevents the creation of non-functional agents.

### Accuracy Not Met

If the agent doesn't reach target accuracy after max iterations:

```
Agent creation finished with status: finished_failed_to_meet_accuracy
Final accuracy: 72.00% (target: 80%)
```

The agent is still created and can be manually improved.

## Output Structure

After completion, the agent is created at:

```
agents/<agent-name>/
├── src/<agent_name>/
│   ├── __init__.py
│   ├── worker.py          # Temporal worker entry point
│   ├── workflows.py       # Workflow definitions
│   ├── activities.py      # Activity implementations
│   └── prompts.py         # Agent prompts
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   └── test_agent.py
├── pyproject.toml
└── README.md
```

## Best Practices

1. **Start with clear descriptions**: The better the description, the better the initial draft
2. **Provide test cases**: If you have specific scenarios, add them to guide evaluation
3. **Tune child skill parameters**: Balance speed vs. quality based on your use case
4. **Monitor in Temporal UI**: For complex agents, watch the workflow execution in Temporal
5. **Iterate manually if needed**: If auto-improvement stalls, manually refine and re-run

## Related Skills

- `skill-auto` - Create individual skills
- `agent-evaluation` - Evaluate existing agents
- `workflow-monitor` - Monitor Temporal workflows

## See Also

- [Creating Agents Automatically](../../../docs/platform/cli/guides/creating-agents-automatically.md) - Full tutorial
- [Functional Workflow Architecture](../../../docs/architecture/functional-workflow-design.md) - Architecture details
- [Agent Development Guide](../../../docs/kubani/agents/development.md) - Manual agent creation
