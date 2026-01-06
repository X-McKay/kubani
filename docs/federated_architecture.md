# Federated Agent Architecture

This document describes the Voyager-inspired federated agent architecture implemented in Kubani.

## Overview

The federated architecture transforms k8s-monitor and news-monitor from simple workflow-based systems into truly agentic multi-agent ecosystems with continuous learning capabilities.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FEDERATED ARCHITECTURE                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                              CORE                                      │   │
│  │                         (agents/core)                                  │   │
│  │                                                                        │   │
│  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐           │   │
│  │  │ Skill Library  │  │ Event Bus      │  │ Approval Flow  │           │   │
│  │  │                │  │                │  │                │           │   │
│  │  │ • Knowledge    │  │ • Redis Streams│  │ • Discord      │           │   │
│  │  │   as skills    │  │ • Pub/Sub      │  │   reactions    │           │   │
│  │  │ • MCP tool refs│  │ • Consumer     │  │ • Timeout      │           │   │
│  │  │ • Verification │  │   groups       │  │   handling     │           │   │
│  │  └────────────────┘  └────────────────┘  └────────────────┘           │   │
│  │                                                                        │   │
│  │  ┌────────────────┐  ┌────────────────┐                               │   │
│  │  │ Observability  │  │ Memory         │                               │   │
│  │  │ (Prometheus)   │  │ (mem0)         │                               │   │
│  │  └────────────────┘  └────────────────┘                               │   │
│  │                                                                        │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                      │                                       │
│                    ┌─────────────────┴─────────────────┐                    │
│                    ▼                                   ▼                    │
│  ┌──────────────────────────────┐   ┌──────────────────────────────┐       │
│  │       k8s-monitor            │   │       news-monitor           │       │
│  │                              │   │                              │       │
│  │  Agents:                     │   │  Agents:                     │       │
│  │  • Sentinel (watch)          │   │  • NewsExplorer (discover)   │       │
│  │  • Healer (remediate)        │   │                              │       │
│  │  • Explorer (learn)          │   │                              │       │
│  │                              │   │                              │       │
│  └──────────────────────────────┘   └──────────────────────────────┘       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Key Design Principles

### 1. MCP-First, Skills-Second

**MCP servers provide actions. Skills provide knowledge about WHEN and HOW to use them.**

```python
# WRONG: Skill contains executable code
async def restart_pod(name, namespace):
    subprocess.run(["kubectl", "delete", "pod", name, "-n", namespace])

# CORRECT: Skill is knowledge referencing MCP tools
skill = Skill(
    id="k8s-restart-crashloop",
    name="Restart CrashLoopBackOff Pod",
    actions=[
        SkillAction(
            description="Delete pod to trigger recreation",
            mcp_tool=MCPToolReference(
                server="kubernetes-mcp-server",
                tool="pods_delete",
                params={"name": "$pod_name", "namespace": "$namespace"},
            ),
        )
    ],
    success_criteria=["Pod reaches Running state within 2 minutes"],
)
```

### 2. Skills Are Knowledge, Not Code

Skills contain:
- **When** to apply (preconditions)
- **What** MCP tools to invoke (actions with MCPToolReference)
- **How** to verify success (success criteria)
- **What** to do if it fails (failure handling)

Skills do NOT contain:
- kubectl subprocess calls
- Direct API client code
- Anything that duplicates MCP server functionality

### 3. Request MCP Servers When Needed

If an agent needs a capability that no MCP server provides:

```python
await event_bus.publish(
    EventType.SYSTEM_MCP_SERVER_REQUESTED,
    {
        "server": "prometheus-mcp-server",
        "reason": "Need to query metrics for capacity forecasting",
        "priority": "medium",
    }
)
```

### 4. Observable from Day One

All components expose Prometheus metrics:

- `skill_executions_total` - Skill execution counts by outcome
- `skill_execution_duration_seconds` - Execution latency histogram
- `skill_confidence` - Current confidence level per skill
- `agent_events_published_total` - Events published by type
- `agent_events_processed_total` - Events processed by consumer
- `approvals_requested_total` - Approval requests by action
- `approval_latency_seconds` - Time to get approval

## Core Components

### Skill Library

The skill library stores and retrieves skills based on semantic matching.

```python
from core_agents.skills import SkillLibrary, get_skill_library

# Get singleton instance
library = await get_skill_library()

# Search for matching skills
results = await library.search(
    query="pod stuck in CrashLoopBackOff",
    domain=SkillDomain.K8S,
    category=SkillCategory.REMEDIATION,
    limit=3,
)

# Record outcomes to update confidence
await library.record_outcome(
    SkillOutcome(skill_id="k8s-restart-crashloop", success=True)
)
```

### Event Bus

Redis Streams-based event bus for cross-agent communication.

```python
from core_agents.events import EventBus, EventType, get_event_bus

bus = await get_event_bus()

# Publish an event
await bus.publish(
    event_type=EventType.K8S_ISSUE_DETECTED,
    payload={"pod": "my-pod", "reason": "CrashLoopBackOff"},
    source="k8s-sentinel",
)

# Subscribe to events
async for event in bus.subscribe(
    EventType.K8S_ISSUE_DETECTED,
    consumer_group="healers",
    consumer_name="healer-1",
):
    await handle_issue(event)
```

### Approval Flow

Human-in-the-loop approvals via Discord reactions.

```python
from core_agents.approvals import ApprovalRequest, get_discord_approver

approver = get_discord_approver()

request = ApprovalRequest(
    action="scale_deployment",
    resource="deployment/api-server",
    reason="High CPU usage detected",
    skill_id="k8s-scale-deployment",
)

result = await approver.request_approval(request)

if result.approved:
    # Proceed with action
    pass
```

## K8s Domain Agents

### SentinelAgent

Watches Kubernetes events in real-time and classifies them.

```python
from k8s_monitor.federated import SentinelAgent

sentinel = SentinelAgent(poll_interval=30.0)
await sentinel.start()  # Runs continuously
```

The Sentinel:
1. Polls Kubernetes events via MCP
2. Filters Warning events (ignores Normal)
3. Matches events against known issue patterns
4. Searches skill library for matching preconditions
5. Publishes `K8S_ISSUE_DETECTED` events to the bus

### HealerAgent

Executes skill-based remediation with verification.

```python
from k8s_monitor.federated import HealerAgent

healer = HealerAgent()
await healer.start()  # Subscribes to issue events
```

The Healer:
1. Subscribes to `K8S_ISSUE_DETECTED` events
2. Retrieves matching remediation skills
3. Requests approval for dangerous actions (via Discord)
4. Executes skill actions via MCP tools
5. Verifies success using LLM critic (Voyager pattern)
6. Updates skill confidence based on outcome
7. Publishes completion/failure events

### ExplorerAgent

Proposes new skills based on unmatched incident patterns.

```python
from k8s_monitor.federated import ExplorerAgent

explorer = ExplorerAgent()

# Analyze patterns and generate proposals
proposals = await explorer.analyze_and_propose()

# Submit for human approval
for proposal in proposals:
    await explorer.submit_for_approval(proposal)
```

The Explorer:
1. Tracks incidents that couldn't be matched to skills
2. Clusters similar incidents by pattern
3. Uses LLM to propose new skill definitions
4. Submits skills to Discord for human approval
5. Adds approved skills to library with low initial confidence
6. Requests new MCP servers when capabilities are missing

## News Domain Agents

### NewsExplorerAgent

Discovers new RSS sources based on coverage gaps.

```python
from news_monitor.federated import NewsExplorerAgent

explorer = NewsExplorerAgent()

# Find topics with limited coverage
gaps = await explorer.analyze_coverage_gaps()

# Discover new sources
proposals = await explorer.discover_sources(gaps[0])

# Submit for approval
await explorer.submit_for_approval(proposals[0])
```

## Event Types

### K8s Domain Events
- `k8s:issue_detected` - Issue found by Sentinel
- `k8s:remediation_started` - Healer beginning work
- `k8s:remediation_completed` - Successfully resolved
- `k8s:remediation_failed` - Failed or escalated

### News Domain Events
- `news:article_ingested` - New article processed
- `news:breaking_detected` - Breaking news alert
- `news:source_discovered` - New RSS source found

### System Events
- `system:mcp_server_requested` - Agent needs new capability
- `system:approval_requested` - Action needs approval
- `system:approval_received` - Approval response received

### Agent Events
- `agent:started` - Agent came online
- `agent:stopped` - Agent shut down
- `agent:error` - Agent encountered error
- `agent:skill_learned` - New skill added to library

## Grafana Dashboards

Three dashboards provide visibility into the federated architecture:

### Agent Overview Dashboard
- Total events processed
- Total skills executed
- Skill success rate
- Pending approvals
- Events published rate
- MCP tool calls rate
- Skill confidence levels

### Remediation Activity Dashboard
- Issues detected (1h/24h)
- Auto-resolved count
- Escalated count
- Auto-resolution rate
- Events by type
- Skills used distribution
- Time to remediate

### Approvals Dashboard
- Pending approvals
- Approved/rejected counts
- Response latency
- Approval rate by action type

## Adding New Skills

To add a new K8s skill:

```python
from core_agents.skills import (
    MCPToolReference,
    Skill,
    SkillAction,
    SkillCategory,
    SkillDomain,
)

new_skill = Skill(
    id="k8s-handle-oomkilled",
    name="Handle OOMKilled Pods",
    domain=SkillDomain.K8S,
    category=SkillCategory.REMEDIATION,
    description="Handle pods that were killed due to OOM",
    preconditions=[
        "Pod has OOMKilled status",
        "Pod has restarted due to OOM",
    ],
    actions=[
        SkillAction(
            description="Get pod events for context",
            mcp_tool=MCPToolReference(
                server="kubernetes-mcp-server",
                tool="events_list",
                params={"namespace": "$namespace"},
            ),
        ),
        SkillAction(
            description="Delete pod to trigger recreation",
            mcp_tool=MCPToolReference(
                server="kubernetes-mcp-server",
                tool="pods_delete",
                params={"name": "$pod_name", "namespace": "$namespace"},
            ),
        ),
    ],
    success_criteria=[
        "New pod created",
        "Pod reaches Running state",
        "No OOM event in 5 minutes",
    ],
    failure_handling="Escalate - may need memory limit increase",
    requires_approval=False,
    confidence=0.5,
    tags=["oom", "memory", "pod"],
)

# Add to library
library = await get_skill_library()
await library.add(new_skill)
```

## Configuration

### Redis (Event Bus)
```bash
REDIS_URL=redis://localhost:6379
```

### Qdrant (Skill Library)
```bash
QDRANT_URL=http://localhost:6333
VLLM_API_URL=http://localhost:8000/v1  # For embeddings
```

### Discord (Approvals)
```bash
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

## Testing

Run the federated architecture tests:

```bash
# Core tests
uv run pytest agents/core/tests/test_skills.py -v
uv run pytest agents/core/tests/test_events.py -v
uv run pytest agents/core/tests/test_approvals.py -v
uv run pytest agents/core/tests/test_federated_integration.py -v

# K8s agent tests
uv run pytest agents/k8s-monitor/tests/test_explorer.py -v

# News agent tests
uv run pytest agents/news-monitor/tests/test_news_explorer.py -v
```
