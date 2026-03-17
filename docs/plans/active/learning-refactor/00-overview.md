# Learning System Refactor — Overview

**Date:** 2026-03-09
**Status:** Draft
**Author:** Claude + Al

---

## Problem Statement

The learning system was built before the framework matured. It uses `asyncio` loops in a monolithic `Syndicate` class, bypasses Temporal, lacks observability, and is difficult to test. It also passively waits for `AGENT_EXECUTION_COMPLETE` events instead of proactively mining the execution data that already exists in Temporal.

Meanwhile, the k8s-monitor and news-digest syndicates have established clear, proven patterns:
- Temporal workflows with `ObservableWorkflowMixin`
- Declarative `ScheduleConfig` schedules
- Context injection for testability
- `KubaniAgent` base class with MCP tools
- Single-activity patterns delegating to agents
- Worker entry points with CLI schedule management

The learning system must be rebuilt to match these patterns while becoming more capable.

## Goals

1. **Align with modern patterns** — Temporal workflows, observable, context injection, KubaniAgent
2. **Retain the Voyager-inspired 3-agent design** — Critic, Reflection, and Improvement agents with clear separation of concerns
3. **Proactive data collection** — Mine Temporal directly instead of waiting for events
4. **Universal coverage** — Automatically monitor ALL syndicates (k8s-monitor, news-digest, nexus, and future agents)
5. **Actionable output** — Produce structured improvement proposals, not just insights
6. **Testable** — Full LocalContext support for development without services

## Architecture

Four-stage pipeline (like news-digest, with an extra synthesis stage):

```
Stage 1: Collect        Stage 2: Evaluate       Stage 3: Reflect        Stage 4: Improve
(every hour)            (triggered by S1)        (triggered by S2)       (daily)

Query Temporal for   →  CriticAgent          →  ReflectionAgent      →  ImprovementAgent
recent workflow runs    scores each              synthesizes cross-      proposes changes
across all namespaces   execution                agent patterns          + publishes to Discord
```

### Three Agents (modernized KubaniAgent subclasses)

| Agent | Role | MCP Tools | Triggered By |
|-------|------|-----------|--------------|
| **CriticAgent** | Evaluates individual executions: scores success, efficiency, quality | Temporal MCP, Memory MCP | Stage 1 (collection) |
| **ReflectionAgent** | Synthesizes cross-agent patterns, identifies trends and skill opportunities | Memory MCP | Stage 2 (critic evaluations) |
| **ImprovementAgent** | Proposes skills, prompt changes, config updates from reflection insights | Memory MCP, Skills MCP | Daily schedule |

### Key Data Flow

```
Temporal History (all namespaces)
    ↓ collect_executions_activity
ExecutionRecord (Memory MCP)
    ↓ run_critic_activity (CriticAgent)
CriticEvaluation (Memory MCP)
    ↓ run_reflection_activity (ReflectionAgent)
ReflectionInsight (Memory MCP)
    ↓ propose_improvements_activity (ImprovementAgent)
ProposedImprovement (Memory MCP + Discord)
```

## Phases

| Phase | Description | Deliverables |
|-------|-------------|--------------|
| **[Phase 1](./01-phase1-data-models-and-collection.md)** | Data models, collection workflow, activities | `models.py`, `CollectExecutionsWorkflow`, `activities.py` |
| **[Phase 2](./02-phase2-critic-and-reflection.md)** | Critic agent, reflection agent, evaluation + reflection workflows | `CriticAgent`, `ReflectionAgent`, `EvaluateExecutionsWorkflow`, `ReflectWorkflow` |
| **[Phase 3](./03-phase3-improvement-agent-and-workflow.md)** | Improvement agent, improvement workflow, Discord publishing | `ImprovementAgent`, `ImprovementWorkflow` |
| **[Phase 4](./04-phase4-worker-build-deploy.md)** | Worker entry point, Earthfile, deployment, migration | `worker.py`, `Earthfile`, `deployment.yaml` |

## Files Changed

### New Files
```
kubani/syndicates/learning_system/
├── models.py                          # ExecutionRecord, CriticEvaluation, ReflectionInsight, ProposedImprovement
├── activities.py                      # Activities (collect, critic, reflect, improve, store, publish)
├── workflows/
│   ├── __init__.py
│   ├── collect.py                     # CollectExecutionsWorkflow
│   ├── evaluate.py                    # EvaluateExecutionsWorkflow (Critic)
│   ├── reflect.py                     # ReflectWorkflow (Reflection)
│   └── improve.py                     # ImprovementWorkflow
├── pipeline/
│   ├── __init__.py
│   ├── context.py                     # LearningPipelineContext protocol
│   └── contexts/
│       ├── temporal_context.py        # Production context
│       └── local_context.py           # Test context
├── src/learning_system_syndicate/
│   ├── __init__.py
│   └── worker.py                      # Entry point + schedule management
├── pyproject.toml                     # Package definition
├── Earthfile                          # Container build
└── tests/
    ├── conftest.py
    ├── test_models.py
    ├── test_collect_workflow.py
    ├── test_evaluate_workflow.py
    ├── test_reflect_workflow.py
    └── test_improve_workflow.py

kubani/agents/critic/
├── agent.py                           # CriticAgent (KubaniAgent subclass, modernized)
├── config.yaml                        # Skills, MCP servers, limits
└── prompt.md                          # System prompt

kubani/agents/reflection/
├── agent.py                           # ReflectionAgent (KubaniAgent subclass, modernized)
├── config.yaml                        # Skills, MCP servers, limits
└── prompt.md                          # System prompt

kubani/agents/improvement_agent/
├── agent.py                           # ImprovementAgent (KubaniAgent subclass)
├── config.yaml                        # Skills, MCP servers, limits
└── prompt.md                          # System prompt
```

### Modified Files
```
config/default.yaml                    # Update learning section
config/production.yaml                 # Update learning overrides
infrastructure/gitops/apps/ai-agents/learning-agent/deployment.yaml  # New deployment
infrastructure/gitops/apps/ai-agents/learning-agent/kustomization.yaml
```

### Deleted Files (Phase 4, after new system is validated)
```
kubani/agents/critic/agent.py          # Replaced by modernized version (old custom class → KubaniAgent)
kubani/agents/critic/models.py         # Models moved to syndicate models.py
kubani/agents/reflection/agent.py      # Replaced by modernized version
kubani/agents/reflection/models.py     # Models moved to syndicate models.py
kubani/agents/skill_synthesizer/       # Replaced by improvement_agent
kubani/syndicates/learning_system/syndicate.py  # Replaced by workflows
kubani/syndicates/learning_system/events.py     # Events now in activities
kubani/syndicates/_base/               # No longer needed (syndicates are just workflow collections)
```

## Non-Goals

- Changing the Memory MCP server API
- Changing the Temporal MCP server API
- Modifying other syndicates (k8s-monitor, news-digest)
- Building a UI for learning results (use existing activity feed)
