# Creating Agents Automatically

This tutorial walks you through creating a new AI agent using the automated `agent_auto` workflow. The workflow handles drafting, skill creation, testing, and improvement automatically.

## Prerequisites

- `kubani-dev` CLI installed
- Temporal server running (local or cluster)
- Access to the LLM service

## Overview

The automated agent creation workflow:

1. **Drafts** the agent structure based on your description
2. **Identifies** required skills and creates any that are missing
3. **Generates** the agent code files
4. **Evaluates** the agent against test cases
5. **Improves** iteratively until target accuracy is reached
6. **Publishes** the final agent

## Step 1: Draft Your Agent

Start the workflow with a description of what your agent should do:

```bash
kubani-dev agent draft \
  --name pod-health-monitor \
  --description "An agent that monitors Kubernetes pod health, detects issues like OOM kills and CrashLoopBackOff, and suggests remediation steps"
```

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `--name`, `-n` | Agent name (required) | - |
| `--description`, `-d` | What the agent does (required) | - |
| `--target-accuracy` | Accuracy threshold to reach | 0.8 (80%) |
| `--max-iterations` | Maximum improvement cycles | 5 |
| `--non-interactive` | Don't wait for completion | false |
| `--temporal-address` | Temporal server address | localhost:7233 |
| `--child-skill-max-iterations` | Max iterations for auto-generated skills | 3 |
| `--child-skill-target-accuracy` | Target accuracy for auto-generated skills | 0.70 |

### Example Output

```
╭─────────────────────── Starting Agent Creation Workflow ────────────────────────╮
│ Agent Name:      pod-health-monitor                                             │
│ Description:     An agent that monitors Kubernetes pod health...                │
│ Target Accuracy: 80%                                                            │
│ Max Iterations:  5                                                              │
│ Temporal:        localhost:7233                                                 │
╰─────────────────────────────────────────────────────────────────────────────────╯

✓ Workflow started with ID: agent-auto-pod-health-monitor
ℹ Monitor progress: kubani-dev agent status pod-health-monitor
ℹ Cancel workflow:  kubani-dev agent cancel pod-health-monitor

Waiting for workflow to complete... (Ctrl+C to detach)
```

## Step 2: Monitor Progress

While the workflow runs, you can check its status:

```bash
kubani-dev agent status pod-health-monitor
```

### Status Output

```
╭────────────────────── Agent Workflow: pod-health-monitor ───────────────────────╮
│ Workflow ID: agent-auto-pod-health-monitor                                      │
│ Status:      RUNNING                                                            │
│ Started:     2026-01-25 14:30:00                                                │
╰─────────────────────────────────────────────────────────────────────────────────╯

╭─────────────────────────────── Workflow State ──────────────────────────────────╮
│ Property      │ Value                                                           │
├───────────────┼─────────────────────────────────────────────────────────────────┤
│ Agent Name    │ pod-health-monitor                                              │
│ Status        │ improving                                                       │
│ Iteration     │ 2                                                               │
│ Agent Path    │ agents/pod-health-monitor                                       │
│ Last Accuracy │ 65.00%                                                          │
│ Evaluations   │ 2                                                               │
╰───────────────┴─────────────────────────────────────────────────────────────────╯
```

### JSON Output

For scripting or CI/CD integration:

```bash
kubani-dev agent status pod-health-monitor --json
```

```json
{
  "workflow_id": "agent-auto-pod-health-monitor",
  "status": "RUNNING",
  "start_time": "2026-01-25T14:30:00Z",
  "state": {
    "agent_name": "pod-health-monitor",
    "status": "improving",
    "iteration": 2,
    "agent_path": "agents/pod-health-monitor",
    "eval_history": [
      {"objective_accuracy": 0.50, "skill_precision": 0.60, "skill_recall": 0.55},
      {"objective_accuracy": 0.65, "skill_precision": 0.70, "skill_recall": 0.68}
    ]
  }
}
```

## Step 3: Understanding the Eval-Improve Loop

The workflow automatically runs evaluation cycles:

1. **Evaluate**: Run test cases against the agent
2. **Analyze**: Identify failures and areas for improvement
3. **Improve**: Apply suggested changes to prompts, skills, and configuration
4. **Repeat**: Until target accuracy is reached or max iterations hit

### What Gets Improved

- **Prompts**: System prompts and task descriptions
- **Skills**: New skills added, existing ones refined
- **Configuration**: Agent settings and tool parameters
- **Error handling**: Better failure recovery

### Accuracy Metrics

- **Objective Accuracy**: Overall success rate across test cases
- **Skill Precision**: Of skills invoked, how many were correct?
- **Skill Recall**: Of skills needed, how many were invoked?

## Step 4: Completion

When the workflow finishes, you'll see the result:

### Success

```
✓ Agent created successfully!
ℹ Agent path: agents/pod-health-monitor
ℹ Final accuracy: 85.00%
ℹ Iterations completed: 3
```

### Below Target

```
⚠ Agent creation finished with status: finished_failed_to_meet_accuracy
ℹ Final accuracy: 72.00% (target: 80%)
```

Even if the target isn't reached, the agent is still created and can be manually improved.

## Step 5: Explore the Result

After completion, examine the generated files:

```bash
ls agents/pod-health-monitor/
```

```
agents/pod-health-monitor/
├── src/pod_health_monitor/
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

## Canceling a Workflow

If you need to stop a running workflow:

```bash
kubani-dev agent cancel pod-health-monitor
```

You'll be asked to confirm:

```
Cancel workflow for agent 'pod-health-monitor'? [y/N]: y
✓ Cancel request sent to workflow for agent 'pod-health-monitor'
ℹ The workflow will stop after completing its current activity.
```

Use `--force` to skip confirmation:

```bash
kubani-dev agent cancel pod-health-monitor --force
```

## Non-Interactive Mode

For CI/CD pipelines or automation:

```bash
kubani-dev agent draft \
  --name pod-health-monitor \
  --description "Monitor pod health" \
  --non-interactive
```

The command returns immediately after starting the workflow. Use `agent status` to poll for completion.

## Connecting to a Custom Temporal Server

By default, the CLI connects to `localhost:7233`. To use a different server:

```bash
# Using command-line option
kubani-dev agent draft \
  --name my-agent \
  --description "My agent" \
  --temporal-address temporal.example.com:7233

# Using environment variable
export TEMPORAL_ADDRESS=temporal.example.com:7233
kubani-dev agent draft --name my-agent --description "My agent"
```

## Troubleshooting

### Temporal Connection Failed

```
✗ Failed to connect to Temporal at localhost:7233
ℹ Make sure Temporal is running. You can start it with: temporal server start-dev
```

Start a local Temporal server:

```bash
temporal server start-dev
```

### Workflow Not Found

```
✗ No workflow found for agent 'my-agent'
ℹ Start one with: kubani-dev agent draft --name my-agent --description '...'
```

The agent hasn't been created yet, or the workflow has already completed and been cleaned up.

### Low Final Accuracy

If the agent doesn't reach target accuracy:

1. Check the test cases - are they realistic?
2. Review the generated prompts in `src/<agent>/prompts.py`
3. Manually improve skills in the `skills/` directory
4. Re-run evaluation with `kubani-dev agent eval <name>`

## Next Steps

After creating your agent:

1. **Review the code**: Examine generated files, customize as needed
2. **Add tests**: Expand the test suite in `tests/`
3. **Deploy**: Use `kubani-dev deploy --agent <name>` to deploy to the cluster
4. **Monitor**: Check logs and metrics in the Temporal UI

## See Also

- [Agent Development Guide](../../../../kubani/agents/development/creating-agents.md) - Manual agent creation
- [Functional Workflow Architecture](../../../../architecture/functional-workflow-design.md) - How the workflow is structured
- [Local Development](./local-development.md) - Running agents locally
