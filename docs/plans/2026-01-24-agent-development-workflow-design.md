# Agent Development Workflow Design

**Date:** 2026-01-24
**Status:** Draft
**Author:** Claude Code + Human collaboration

## Overview

This document describes a sophisticated agent development workflow that mirrors the existing skill development process. The workflow follows a **Draft → Eval → Improve → Publish** cycle with agent-specific enhancements including skill dependency analysis, skill invocation verification, and GitOps integration.

### Design Principles

1. **Skill-First Foundation** - Agents are built on top of well-tested skills
2. **Sequential Skill Creation** - New skills are fully developed before agent creation
3. **Strict Skill Verification** - Required skills MUST be invoked during evaluation
4. **Full Improvement Scope** - Improvements consider skills, prompt, and config
5. **End-to-End Deployment** - Publish includes registry and GitOps manifests

---

## Phase 1: Agent Draft

### Overview

The agent draft phase is the most complex, as it must:
1. Understand the agent's purpose and objectives
2. Discover existing skills that can fulfill requirements
3. Identify gaps requiring new skills
4. Orchestrate skill creation (using existing skill workflow)
5. Generate agent files

### Conversational Flow

```
User: "Create an agent that monitors Temporal workflow health and remediates failures"

LLM: "I'll help you create a Temporal monitoring agent. Let me ask a few questions:

1. What types of Temporal failures should it detect?
   - Workflow timeouts
   - Activity failures
   - Task queue backlogs
   - All of the above"

[After gathering requirements...]

LLM: "Based on your requirements, I've analyzed existing skills:

**Existing Skills Available:**
- `temporal/diagnostic/check-workflow-status` - Check individual workflow health
- `general/notifications/discord-alert` - Send Discord alerts

**Skills Needed (will create):**
- `temporal/diagnostic/detect-backlog` - Detect task queue backlogs
- `temporal/remediation/restart-workflow` - Safely restart failed workflows

Should I proceed with creating these 2 new skills first?"
```

### Files Generated

```
kubani/agents/_development/temporal-monitor/
├── agent.py           # Agent class extending KubaniAgent
├── prompt.md          # System prompt
├── config.yaml        # Skills, capabilities, limits
├── test_cases.yaml    # LLM-generated evaluation scenarios
└── metadata.json      # Version, status, created_by
```

### Config.yaml Structure

```yaml
name: temporal-monitor
version: "0.1.0"
description: "Monitors Temporal workflows and remediates failures"

skills:
  allowed:
    - "temporal/diagnostic/*"
    - "temporal/remediation/*"
    - "general/notifications/*"
  denied: []

capabilities:
  - name: detect_failures
    description: "Detect Temporal workflow failures and backlogs"
  - name: remediate_workflow
    description: "Restart or repair failed workflows"

limits:
  max_tokens: 8192
  max_turns: 12

mcp_servers:
  - temporal-mcp-server
  - discord-mcp-server
```

---

## Phase 2: Agent Evaluation

### Overview

Agent evaluation verifies two dimensions:
1. **Objective Achievement** - Does the agent accomplish its stated goals?
2. **Skill Invocation** - Does the agent use the right skills at the right times?

### Test Case Structure

```yaml
# test_cases.yaml
test_cases:
  - name: detect_workflow_timeout
    description: "Agent should detect a timed-out workflow and alert"

    # Scenario setup
    scenario:
      description: "A workflow has been running for 2 hours past its timeout"
      mock_context:
        workflow_id: "payment-process-123"
        status: "TIMED_OUT"
        started_at: "2024-01-15T10:00:00Z"
        timeout_at: "2024-01-15T11:00:00Z"

    # What skills MUST be invoked
    required_skills:
      - skill: "temporal/diagnostic/check-workflow-status"
        with_params:
          workflow_id: "payment-process-123"
      - skill: "general/notifications/discord-alert"

    # Outcome assertions
    expected_outcomes:
      - type: contains
        field: response.action
        value: "alert_sent"
      - type: exists
        field: response.diagnosis

    # Critic evaluation criteria
    critic_criteria:
      - "Agent correctly identified the timeout condition"
      - "Alert included relevant workflow details"
      - "No unnecessary remediation attempted"
```

### Evaluation Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| **Objective Accuracy** | % of outcome assertions passed | ≥90% |
| **Skill Accuracy** | % of required skills correctly invoked | 100% |
| **Skill Precision** | Required skills / Total skills invoked | ≥80% |
| **Avg Latency** | Mean response time per test | Varies |
| **Tokens/Test** | Prompt + completion tokens | Minimize |

### Quick vs Full Mode

**Quick Mode:** Single config (large model + thinking), fast feedback
```bash
kubani-dev agent eval kubani/agents/_development/temporal-monitor
```

**Full Mode:** 4 configurations compared
```bash
kubani-dev agent eval kubani/agents/_development/temporal-monitor --mode full
```

Comparison matrix shows which model/thinking combo best balances accuracy and efficiency for this specific agent.

### Skill Invocation Tracking

The evaluator intercepts tool calls to track:
```python
{
  "skills_invoked": [
    {"skill": "temporal/diagnostic/check-workflow-status", "params": {...}},
    {"skill": "general/notifications/discord-alert", "params": {...}}
  ],
  "skills_required": ["temporal/diagnostic/check-workflow-status", "general/notifications/discord-alert"],
  "skill_accuracy": 100.0,
  "extra_skills_invoked": [],
  "missing_skills": []
}
```

---

## Phase 3: Agent Improvement

### Overview

The improvement phase analyzes evaluation results and makes targeted changes to:
1. **Skill Configuration** - Add missing skills, remove unnecessary ones, adjust patterns
2. **System Prompt** - Refine instructions for better reasoning and skill selection
3. **Operational Config** - Adjust limits, capabilities, MCP server requirements

### Improvement Analysis

When `kubani-dev agent improve` runs, it performs:

```python
# Analysis output structure
{
  "skill_analysis": {
    "missing_invocations": [
      {"test": "detect_backlog", "skill": "temporal/diagnostic/detect-backlog", "times_missed": 3}
    ],
    "unnecessary_invocations": [
      {"skill": "temporal/remediation/restart-workflow", "invoked_when": "diagnosis_only_tests"}
    ],
    "recommended_additions": ["temporal/collection/list-task-queues"],
    "recommended_removals": []
  },
  "prompt_analysis": {
    "unclear_instructions": ["When to escalate vs remediate is ambiguous"],
    "missing_context": ["No guidance on backlog thresholds"],
    "suggested_additions": [
      "Add explicit decision tree for remediation vs escalation",
      "Define backlog threshold: >100 pending tasks = critical"
    ]
  },
  "config_analysis": {
    "max_turns_insufficient": false,
    "missing_mcp_servers": [],
    "capability_gaps": ["detect_backlog not listed in capabilities"]
  }
}
```

### Improvement Goals

User specifies optimization priorities:

```bash
# Focus on accuracy (default)
kubani-dev agent improve <path> --goals accuracy

# Balance accuracy and latency
kubani-dev agent improve <path> --goals accuracy --goals latency

# All three dimensions
kubani-dev agent improve <path> --goals accuracy --goals latency --goals tokens
```

### Iterative Loop

```
┌─────────────────────────────────────────────────────────┐
│                    IMPROVE LOOP                         │
├─────────────────────────────────────────────────────────┤
│  1. Load latest evaluation results                      │
│  2. Analyze failures (objective + skill invocation)     │
│  3. Generate improvement suggestions                    │
│  4. Apply changes to: config.yaml, prompt.md, agent.py  │
│  5. Re-run evaluation                                   │
│  6. Compare metrics: improved? degraded? same?          │
│  7. If improved and meets threshold → exit              │
│     If degraded → rollback, try alternative             │
│     If same → suggest manual review                     │
└─────────────────────────────────────────────────────────┘
```

### Change Application

**Skill Pattern Changes** (config.yaml):
```yaml
# Before
skills:
  allowed:
    - "temporal/diagnostic/*"

# After (added collection for backlog detection)
skills:
  allowed:
    - "temporal/diagnostic/*"
    - "temporal/collection/list-task-queues"
```

**Prompt Refinements** (prompt.md):
```markdown
# Before
You are a Temporal monitoring agent...

# After (added decision guidance)
You are a Temporal monitoring agent...

## Decision Guidelines
- **Diagnose only** when: workflow is running, status is unknown
- **Remediate** when: workflow failed with retryable error, <3 previous retries
- **Escalate** when: workflow failed 3+ times, or involves payment/critical path
```

**Config Adjustments** (config.yaml):
```yaml
# Added missing capability
capabilities:
  - name: detect_backlog
    description: "Detect task queue backlogs exceeding threshold"
```

---

## Phase 4: Agent Publish

### Overview

Publishing an agent involves three steps:
1. **Promote** - Move from `_development` to production directory
2. **Register** - Add to platform registry for discovery
3. **GitOps** - Generate Kubernetes deployment manifests

### Promotion Command

```bash
kubani-dev agent promote kubani/agents/_development/temporal-monitor \
  --syndicate k8s_monitor \
  --bump minor
```

### Directory Structure After Promotion

```
kubani/agents/temporal_monitor/          # Production location
├── agent.py
├── prompt.md
├── config.yaml
├── metadata.json                        # Updated: status=production, version bumped
└── tests/
    └── test_temporal_monitor.py         # Generated from test_cases.yaml

infrastructure/gitops/agents/temporal-monitor/
├── deployment.yaml                      # Kubernetes Deployment
├── service.yaml                         # Kubernetes Service
├── configmap.yaml                       # Agent config as ConfigMap
└── kustomization.yaml                   # Kustomize integration
```

### Registry Registration

The agent is registered in the platform registry:

```json
{
  "id": "temporal-monitor",
  "name": "Temporal Monitor Agent",
  "version": "1.0.0",
  "description": "Monitors Temporal workflows and remediates failures",
  "syndicate": "k8s_monitor",
  "capabilities": [
    {"name": "detect_failures", "description": "Detect Temporal workflow failures"},
    {"name": "remediate_workflow", "description": "Restart failed workflows"}
  ],
  "skills_required": [
    "temporal/diagnostic/*",
    "temporal/remediation/*"
  ],
  "mcp_servers": ["temporal-mcp-server", "discord-mcp-server"],
  "status": "production",
  "evaluation_metrics": {
    "objective_accuracy": 95.0,
    "skill_accuracy": 100.0,
    "avg_latency_ms": 2340
  }
}
```

### GitOps Manifest Generation

**deployment.yaml** (auto-generated):
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: temporal-monitor
  namespace: ai-agents
  labels:
    app: temporal-monitor
    syndicate: k8s-monitor
spec:
  replicas: 1
  selector:
    matchLabels:
      app: temporal-monitor
  template:
    spec:
      containers:
        - name: agent
          image: ghcr.io/kubani/temporal-monitor:1.0.0
          envFrom:
            - configMapRef:
                name: temporal-monitor-config
          resources:
            requests:
              memory: "256Mi"
              cpu: "100m"
```

### Versioning

Semantic versioning with automatic bumping:
- `--bump patch` - Bug fixes, minor prompt tweaks (0.1.0 → 0.1.1)
- `--bump minor` - New capabilities, skill additions (0.1.0 → 0.2.0)
- `--bump major` - Breaking changes, objective changes (0.1.0 → 1.0.0)

---

## CLI Commands

### Agent Command Group

```bash
kubani-dev agent <command> [options]
```

| Command | Description |
|---------|-------------|
| `draft` | Create new agent interactively or from description |
| `eval` | Evaluate agent against test cases |
| `improve` | Automatically improve agent based on eval results |
| `promote` | Promote agent to production |
| `list` | List all agents (development and production) |
| `info` | Show detailed agent information |
| `validate` | Validate agent files and configuration |
| `run` | Execute agent locally with test context |

### Command Details

```bash
# Draft - Interactive mode (default)
kubani-dev agent draft

# Draft - Non-interactive with description
kubani-dev agent draft --name temporal-monitor \
  --description "Monitor Temporal workflows and remediate failures" \
  --non-interactive

# Evaluate - Quick mode (default)
kubani-dev agent eval kubani/agents/_development/temporal-monitor

# Evaluate - Full comparison mode
kubani-dev agent eval kubani/agents/_development/temporal-monitor \
  --mode full --parallel

# Improve - With specific goals
kubani-dev agent improve kubani/agents/_development/temporal-monitor \
  --goals accuracy --goals latency

# Promote - To production with GitOps
kubani-dev agent promote kubani/agents/_development/temporal-monitor \
  --syndicate k8s_monitor --bump minor

# List agents
kubani-dev agent list                    # All agents
kubani-dev agent list --status dev       # Development only
kubani-dev agent list --syndicate k8s    # Filter by syndicate

# Info
kubani-dev agent info temporal-monitor

# Validate
kubani-dev agent validate kubani/agents/_development/temporal-monitor
kubani-dev agent validate --all

# Run locally
kubani-dev agent run temporal-monitor \
  --context '{"workflow_id": "test-123", "action": "diagnose"}'
```

---

## Integration Points

### Integration with Existing Systems

| System | Integration |
|--------|-------------|
| **Skill Workflow** | Agent drafter invokes `kubani-dev skill draft/eval/improve` for new skills |
| **Evaluation Framework** | Reuses `EvalHarness`, `CodeGrader`, `ModelGrader` from skill evaluation |
| **Registry** | Agents registered via existing registry API |
| **MCP Servers** | Agents declare MCP dependencies, validated during draft |
| **Syndicates** | Promoted agents integrate into syndicate orchestration |
| **Continuous Learning** | Agent executions logged for learning cycle |

### New Components Required

```
platform/cli/src/kubani_dev/
├── commands/
│   └── agent.py              # Agent CLI commands (extend existing)
├── agent_drafter.py          # NEW: Agent drafting with skill discovery
├── agent_evaluator.py        # NEW: Agent evaluation with skill tracking
├── agent_improver.py         # NEW: Agent improvement logic
└── agent_promoter.py         # NEW: Promotion + GitOps generation
```

---

## Example End-to-End Workflow

```bash
# 1. DRAFT PHASE
$ kubani-dev agent draft
> Enter agent name: temporal-monitor
> Describe what this agent should do:
  Monitor Temporal workflow health, detect failures and backlogs,
  and automatically restart failed workflows when safe.

[LLM analyzes requirements...]

> Existing skills that can be used:
  ✓ temporal/diagnostic/check-workflow-status
  ✓ general/notifications/discord-alert

> Skills that need to be created:
  ○ temporal/diagnostic/detect-backlog
  ○ temporal/remediation/restart-workflow

> Create these 2 new skills? [Y/n]: Y

[Skill creation workflow runs for each...]
Creating temporal/diagnostic/detect-backlog...
  → Draft complete
  → Evaluating... 85% accuracy
  → Improving... 94% accuracy
  → Skill ready ✓

Creating temporal/remediation/restart-workflow...
  → Draft complete
  → Evaluating... 90% accuracy
  → Improving... 97% accuracy
  → Skill ready ✓

[Agent files generated...]
> Agent created at: kubani/agents/_development/temporal-monitor/

# 2. EVAL PHASE
$ kubani-dev agent eval kubani/agents/_development/temporal-monitor

Running 8 test cases...
  ✓ detect_workflow_timeout (skills: 2/2, outcome: pass)
  ✓ detect_backlog_critical (skills: 2/2, outcome: pass)
  ✗ remediate_retryable_failure (skills: 1/2, outcome: fail)
    Missing skill: temporal/remediation/restart-workflow
  ...

Results:
  Objective Accuracy: 87.5%
  Skill Accuracy: 85.0%
  Avg Latency: 2.3s
  Tokens/Test: 1,240

> Run improvement? [Y/n]: Y

# 3. IMPROVE PHASE
$ kubani-dev agent improve kubani/agents/_development/temporal-monitor --goals accuracy

Analyzing failures...
  - Test 'remediate_retryable_failure': Agent didn't invoke restart skill
  - Root cause: Prompt lacks clear remediation trigger conditions

Applying improvements...
  ✓ Updated prompt.md: Added remediation decision tree
  ✓ Updated config.yaml: Added capability declaration

Re-evaluating...
  Objective Accuracy: 100% (+12.5%)
  Skill Accuracy: 100% (+15%)

> Agent meets threshold. Ready for promotion.

# 4. PROMOTE PHASE
$ kubani-dev agent promote kubani/agents/_development/temporal-monitor \
    --syndicate k8s_monitor --bump minor

Promoting temporal-monitor v0.1.0 → v1.0.0...
  ✓ Moved to kubani/agents/temporal_monitor/
  ✓ Registered in platform registry
  ✓ Generated GitOps manifests in infrastructure/gitops/agents/temporal-monitor/
  ✓ Created PR for deployment

Agent temporal-monitor v1.0.0 promoted successfully!
```

---

## Key Differences from Skill Workflow

| Aspect | Skill Workflow | Agent Workflow |
|--------|----------------|----------------|
| **Dependencies** | None | Discovers and creates required skills first |
| **Evaluation Focus** | Output correctness | Objectives + skill invocation verification |
| **Improvement Scope** | SKILL.md only | Skills + prompt + config |
| **Publish Target** | `kubani/skills/` + registry | `kubani/agents/` + registry + GitOps manifests |
| **Versioning** | Semantic (skill version) | Semantic (agent version) + syndicate association |

---

## Next Steps

1. **Implementation Planning** - Create detailed implementation plan for CLI components
2. **Agent Drafter** - Build skill discovery and orchestration logic
3. **Agent Evaluator** - Extend evaluation framework with skill tracking
4. **Agent Improver** - Build improvement analysis and application
5. **Agent Promoter** - Build GitOps manifest generation
6. **Integration Testing** - End-to-end workflow validation
