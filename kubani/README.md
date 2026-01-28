# Kubani

Agent framework with Skills, Agents, and Syndicates.

## Components

- **framework/** - Core framework (config, events, memory, MCP, Temporal, etc.)
- **agents/** - Reusable agent implementations
- **syndicates/** - Multi-agent orchestration via Temporal workflows
- **skills/** - Skill definitions (Markdown + YAML)

## Syndicates

Syndicates are multi-agent orchestrations built on Temporal workflows.
Each syndicate has its own Temporal namespace for isolation.

### K8s Monitor

```bash
# Start the worker
k8s-monitor-worker
```

```python
from kubani.syndicates.k8s_monitor.workflows import (
    K8sRemediationWorkflow,
    K8sInvestigationSwarm,
)
```

### News Digest

```bash
# Start the worker
news-digest-worker
```

```python
from kubani.syndicates.news_digest.workflows import (
    NewsCollectionWorkflow,
    NewsDigestWorkflow,
)
```

## Architecture

Syndicates use two workflow patterns:

- **Workflow pattern**: Deterministic sequences for known procedures (e.g., K8sRemediationWorkflow)
- **Swarm pattern**: Emergent behavior for complex investigations (e.g., K8sInvestigationSwarm)

All workflows inherit from `ObservableWorkflowMixin` providing:
- Status queries (`get_status`, `get_events`)
- Control signals (`pause`, `resume`, `cancel`)
- Event logging and metrics
