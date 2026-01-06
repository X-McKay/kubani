# Agent Architecture Implementation Plan

> **Status: ✅ COMPLETE** - All 7 phases have been implemented. See [PLAN_hybrid_skills_a2a.md](PLAN_hybrid_skills_a2a.md) for the next evolution (A2A integration, Skill files, Strands Swarm).

## Implementation Summary

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 1 | Core Framework (Skills, Events, Approvals, Observability) | ✅ Complete |
| Phase 2 | Extract K8s Skills | ✅ Complete (8 skills) |
| Phase 3 | Sentinel Agent | ✅ Complete |
| Phase 4 | Healer Agent | ✅ Complete |
| Phase 5 | Explorer Agent (K8s) | ✅ Complete |
| Phase 6 | News Explorer | ✅ Complete |
| Phase 7 | Integration & Polish | ✅ Complete |

**Key Files:**
- Core modules: `agents/core/src/core_agents/{skills,events,approvals,observability}/`
- K8s agents: `agents/k8s-monitor/src/k8s_monitor/federated/`
- News agents: `agents/news-monitor/src/news_monitor/federated/`
- Dashboards: `gitops/apps/monitoring/dashboards/`
- Architecture doc: `docs/federated_architecture.md`

---

## Guiding Principles

Before diving into phases, these principles govern all implementation decisions:

### 1. MCP-First, Skills-Second

**MCP servers provide actions. Skills provide knowledge about WHEN and HOW to use them.**

```
┌─────────────────────────────────────────────────────────────────┐
│                        WRONG APPROACH                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Skill: restart_pod                                              │
│  Code:                                                           │
│    async def restart_pod(name, namespace):                       │
│        subprocess.run(["kubectl", "delete", "pod", name, "-n"...])│
│                                                                  │
│  ❌ Duplicates what kubernetes-mcp-server already does           │
│  ❌ Now we maintain kubectl wrapper code                         │
│  ❌ No consistency with other tools                              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                       CORRECT APPROACH                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Skill: restart_crashlooping_pod                                 │
│  Type: KNOWLEDGE (not code)                                      │
│  Content:                                                        │
│    description: "Restart a pod stuck in CrashLoopBackOff"        │
│    preconditions:                                                │
│      - "Pod status is CrashLoopBackOff"                          │
│      - "Restart count > 3"                                       │
│    actions:                                                      │
│      - tool: "mcp.kubernetes.pods_delete"                        │
│        params: {name: "$pod_name", namespace: "$namespace"}      │
│    verification:                                                 │
│      - "Pod status becomes Running within 60s"                   │
│      - "No new CrashLoopBackOff within 5m"                       │
│    rollback:                                                     │
│      - "N/A - Kubernetes recreates pod automatically"            │
│                                                                  │
│  ✅ Skill is pure knowledge - when to act, what to verify        │
│  ✅ MCP server handles actual kubectl execution                  │
│  ✅ No duplicate code to maintain                                │
│  ✅ Can suggest new MCP servers when capabilities missing        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2. Skills Are Knowledge, Not Code

Skills contain:
- **When** to apply (preconditions)
- **What** MCP tools to invoke (actions referencing MCP tools)
- **How** to verify success (success criteria)
- **What** to do if it fails (rollback/escalation)

Skills do NOT contain:
- kubectl subprocess calls
- Direct API client code
- Anything that duplicates MCP server functionality

### 3. Request MCP Servers When Needed

If an agent needs a capability that no MCP server provides:
1. First, check if an existing MCP server can be extended
2. If not, the agent should **request** a new MCP server be created/deployed
3. Never write one-off tool code as a workaround

```python
# Agent can emit this when it lacks capability
await event_bus.publish("system:mcp_server_requested", {
    "capability": "prometheus_query",
    "reason": "Need to query metrics for capacity forecasting",
    "suggested_server": "prometheus-mcp-server",
    "priority": "medium",
})
```

### 4. Minimal New Code

For each proposed component, ask:
- Does this already exist in an MCP server?
- Does this already exist in core-agents?
- Can we configure rather than code?
- Is this truly necessary?

---

## Current MCP Servers

### Deployed

| Server | Namespace | Capabilities |
|--------|-----------|--------------|
| `kubernetes-mcp-server` | ai-agents | pods_list, pods_get, pods_delete, pods_log, pods_exec, pods_run, resources_get, resources_list, resources_create_or_update, resources_delete, events_list, nodes_top, pods_top, helm_* |

### Available (Not Yet Deployed)

| Server | Source | Capabilities |
|--------|--------|--------------|
| `prometheus-mcp-server` | Community | query, query_range, alerts, targets |
| `loki-mcp-server` | Would need to build | query logs, tail streams |
| `discord-mcp-server` | Community | send_message, add_reaction, wait_for_reaction |
| `github-mcp-server` | Official | issues, PRs, workflows |
| `memory-mcp-server` | Deployed (CrashLoopBackOff) | mem0 operations |

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                         SIMPLIFIED ARCHITECTURE                               │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                              CORE                                        │ │
│  │                         (agents/core)                                    │ │
│  │                                                                          │ │
│  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐             │ │
│  │  │ Skill Schema   │  │ Event Bus      │  │ Approval Flow  │             │ │
│  │  │                │  │                │  │                │             │ │
│  │  │ • Knowledge    │  │ • Redis Streams│  │ • Discord      │             │ │
│  │  │   representation│ │ • Pub/Sub      │  │   reactions    │             │ │
│  │  │ • MCP tool refs│  │ • Cross-domain │  │ • Workflow     │             │ │
│  │  │ • Verification │  │                │  │   signals      │             │ │
│  │  └────────────────┘  └────────────────┘  └────────────────┘             │ │
│  │                                                                          │ │
│  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐             │ │
│  │  │ Observability  │  │ Memory         │  │ Existing       │             │ │
│  │  │ (OTel)         │  │ (enhanced)     │  │ (unchanged)    │             │ │
│  │  └────────────────┘  └────────────────┘  └────────────────┘             │ │
│  │                                                                          │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                      │                                        │
│                    ┌─────────────────┴─────────────────┐                     │
│                    ▼                                   ▼                     │
│  ┌──────────────────────────────┐   ┌──────────────────────────────┐        │
│  │       k8s-monitor            │   │       news-monitor           │        │
│  │                              │   │                              │        │
│  │  Skills: (knowledge only)    │   │  Skills: (knowledge only)    │        │
│  │  • When to restart pods      │   │  • How to score importance   │        │
│  │  • When to scale             │   │  • When topic is breaking    │        │
│  │  • Investigation patterns    │   │  • Source reliability rules  │        │
│  │                              │   │                              │        │
│  │  Agents:                     │   │  Agents:                     │        │
│  │  • Sentinel (watch events)   │   │  • Ingester (RSS watch)      │        │
│  │  • Healer (apply skills)     │   │  • Explorer (find sources)   │        │
│  │  • Explorer (learn skills)   │   │                              │        │
│  │                              │   │                              │        │
│  │  MCP Clients:                │   │  MCP Clients:                │        │
│  │  • kubernetes-mcp-server ✓   │   │  • (none currently)          │        │
│  │  • prometheus-mcp-server*    │   │                              │        │
│  │  • loki-mcp-server*          │   │                              │        │
│  │                              │   │                              │        │
│  └──────────────────────────────┘   └──────────────────────────────┘        │
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                          MCP SERVER LAYER                                │ │
│  │                                                                          │ │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐        │ │
│  │  │ kubernetes  │ │ prometheus* │ │ loki*       │ │ discord*    │        │ │
│  │  │ mcp-server  │ │ mcp-server  │ │ mcp-server  │ │ mcp-server  │        │ │
│  │  │ (deployed)  │ │ (to add)    │ │ (to build)  │ │ (for approvals)     │ │
│  │  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘        │ │
│  │                                                                          │ │
│  │  * = new infrastructure                                                  │ │
│  │                                                                          │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Skill Schema (Knowledge-Based)

```python
from pydantic import BaseModel
from typing import Literal

class MCPToolReference(BaseModel):
    """Reference to an MCP server tool - NOT executable code."""
    server: str           # e.g., "kubernetes-mcp-server"
    tool: str             # e.g., "pods_delete"
    params: dict          # Parameter template with $variables

class SkillAction(BaseModel):
    """A single action in a skill - always references MCP tools."""
    description: str
    mcp_tool: MCPToolReference
    timeout_seconds: int = 60

class Skill(BaseModel):
    """
    A skill is KNOWLEDGE about when and how to use MCP tools.
    It contains NO executable code - just structured knowledge.
    """
    id: str
    name: str
    domain: Literal["k8s", "news", "general"]
    category: Literal["diagnostic", "remediation", "collection", "analysis"]

    # Knowledge components
    description: str
    preconditions: list[str]      # Natural language conditions
    actions: list[SkillAction]    # MCP tool references
    success_criteria: list[str]   # How to verify it worked
    failure_handling: str         # What to do if it fails
    rollback_actions: list[SkillAction] | None  # Optional rollback

    # Learning metadata
    requires_approval: bool = False
    confidence: float = 0.5
    success_count: int = 0
    failure_count: int = 0

    # Composition
    prerequisite_skills: list[str] = []  # Skills that should succeed first
```

### Example K8s Skill (Knowledge, Not Code)

```yaml
id: "k8s-restart-crashloop"
name: "Restart CrashLoopBackOff Pod"
domain: "k8s"
category: "remediation"

description: |
  Restart a pod that is stuck in CrashLoopBackOff state.
  This is appropriate when the pod has been crashing repeatedly
  and a simple restart might resolve a transient issue.

preconditions:
  - "Pod status is CrashLoopBackOff"
  - "Pod has restarted more than 3 times"
  - "Pod is not part of a Job or CronJob"
  - "No OOMKilled events in last 10 minutes (would indicate memory issue)"

actions:
  - description: "Delete the pod to trigger recreation"
    mcp_tool:
      server: "kubernetes-mcp-server"
      tool: "pods_delete"
      params:
        name: "$pod_name"
        namespace: "$namespace"

success_criteria:
  - "New pod created within 30 seconds"
  - "New pod reaches Running state within 2 minutes"
  - "No CrashLoopBackOff within 5 minutes of restart"

failure_handling: |
  If pod does not reach Running state:
  1. Check events for the new pod
  2. Check logs from the new pod
  3. Escalate to human if pattern repeats 3 times

rollback_actions: null  # Kubernetes handles pod recreation

requires_approval: false
confidence: 0.85
```

### Example: When MCP Server is Missing

```yaml
id: "k8s-capacity-forecast"
name: "Forecast Resource Exhaustion"
domain: "k8s"
category: "diagnostic"

description: |
  Query historical metrics to predict when resources will be exhausted.

preconditions:
  - "Node or namespace specified"
  - "Prometheus is accessible"

actions:
  - description: "Query CPU usage trend"
    mcp_tool:
      server: "prometheus-mcp-server"  # NOT YET DEPLOYED
      tool: "query_range"
      params:
        query: "avg(node_cpu_seconds_total{node='$node'})"
        start: "$now - 7d"
        end: "$now"
        step: "1h"

# When agent tries to use this skill and prometheus-mcp-server
# is not available, it should emit:
#
# event: "system:mcp_server_requested"
# payload:
#   server: "prometheus-mcp-server"
#   reason: "Required for capacity forecasting skill"
#   blocking: true
```

---

## Implementation Phases

### Phase 1: Core Framework (Week 1-2)

**Goal:** Build the minimal core infrastructure that both agents will use.

#### 1.1 Skill Schema & Storage

| Component | Location | Description |
|-----------|----------|-------------|
| `Skill` model | `core/skills/schema.py` | Pydantic model (as above) |
| `SkillLibrary` | `core/skills/library.py` | Interface + Qdrant implementation |
| Skill retrieval | `core/skills/retrieval.py` | Semantic search by preconditions |

**Key Design Decisions:**
- Skills stored in Qdrant (already deployed)
- Embeddings of `description + preconditions` for retrieval
- No executable code in skills - just MCP tool references

#### 1.2 Event Bus

| Component | Location | Description |
|-----------|----------|-------------|
| `EventBus` | `core/events/bus.py` | Redis Streams wrapper |
| Event schemas | `core/events/schemas.py` | Typed event definitions |

**Events to Define:**
```python
class EventType(str, Enum):
    # K8s domain
    K8S_ISSUE_DETECTED = "k8s:issue_detected"
    K8S_REMEDIATION_STARTED = "k8s:remediation_started"
    K8S_REMEDIATION_COMPLETED = "k8s:remediation_completed"

    # News domain
    NEWS_BREAKING_DETECTED = "news:breaking_detected"
    NEWS_SOURCE_DISCOVERED = "news:source_discovered"

    # System
    SYSTEM_MCP_SERVER_REQUESTED = "system:mcp_server_requested"
    SYSTEM_APPROVAL_REQUESTED = "system:approval_requested"
    SYSTEM_APPROVAL_RECEIVED = "system:approval_received"
```

#### 1.3 Approval Flow

| Component | Location | Description |
|-----------|----------|-------------|
| `ApprovalRequest` | `core/approvals/schema.py` | Request model |
| `DiscordApprover` | `core/approvals/discord.py` | Post message, wait for reaction |

**Flow:**
```
Agent needs approval
    │
    ▼
Post to Discord with reactions (✅ approve, ❌ reject)
    │
    ▼
Wait for reaction (with timeout)
    │
    ├─── ✅ → Proceed with action
    ├─── ❌ → Abort, log reason
    └─── Timeout → Escalate or abort (configurable)
```

#### 1.4 Observability Foundation

| Component | Location | Description |
|-----------|----------|-------------|
| OTel setup | `core/observability/tracing.py` | Tracer configuration |
| Metrics | `core/observability/metrics.py` | Prometheus metrics |
| Dashboard templates | `gitops/apps/monitoring/dashboards/` | Grafana JSON |

**Metrics to Expose:**
```python
# Skill metrics
skill_executions_total = Counter("skill_executions_total", ["skill_id", "outcome"])
skill_execution_duration = Histogram("skill_execution_duration_seconds", ["skill_id"])
skill_confidence = Gauge("skill_confidence", ["skill_id"])

# Agent metrics
agent_events_processed = Counter("agent_events_processed_total", ["agent", "event_type"])
agent_mcp_calls = Counter("agent_mcp_calls_total", ["agent", "server", "tool", "outcome"])

# Approval metrics
approvals_requested = Counter("approvals_requested_total", ["action_type"])
approvals_granted = Counter("approvals_granted_total", ["action_type"])
approval_latency = Histogram("approval_latency_seconds", ["action_type"])
```

#### Phase 1 Deliverables

- [x] `core/skills/` module with schema and Qdrant storage
- [x] `core/events/` module with Redis Streams bus
- [x] `core/approvals/` module with Discord reaction flow
- [x] `core/observability/` enhanced with OTel tracing
- [x] Unit tests for all new core modules
- [x] Grafana dashboard template for agent observability

---

### Phase 2: Extract K8s Skills (Week 2-3)

**Goal:** Extract knowledge from existing k8s-monitor code into skills.

#### 2.1 Audit Existing Remediation Actions

Current actions in k8s-monitor:
```python
# From remediation_activities.py
SAFE_ACTIONS = {
    "restart_pod": ...,      # → Extract to skill
    "scale_deployment": ..., # → Extract to skill
}
```

#### 2.2 Create Initial Skill Set

Extract from existing code into knowledge-based skills:

| Current Code | New Skill | MCP Tool |
|--------------|-----------|----------|
| `restart_pod()` | `k8s-restart-crashloop` | `kubernetes-mcp-server:pods_delete` |
| `scale_deployment()` | `k8s-scale-deployment` | `kubernetes-mcp-server:resources_scale` |
| Investigation logic | `k8s-investigate-pod-failure` | `kubernetes-mcp-server:pods_log`, `events_list` |

#### 2.3 Skill Extraction Process

```python
# Tool to help extract skills from existing code
async def extract_skill_from_code(code: str, mcp_tools: list[str]) -> Skill:
    """
    Use LLM to analyze existing remediation code and extract:
    1. What conditions trigger this action (preconditions)
    2. What the action does (map to MCP tools)
    3. How to verify success (success criteria)
    """
    prompt = f"""
    Analyze this remediation code and extract a skill definition.

    Code:
    {code}

    Available MCP tools:
    {mcp_tools}

    Extract:
    1. Preconditions (when should this run?)
    2. Actions (which MCP tools to call?)
    3. Success criteria (how to verify it worked?)
    4. Failure handling (what if it doesn't work?)
    """
    ...
```

#### Phase 2 Deliverables

- [x] 10-15 K8s skills extracted from existing code (8 initial skills implemented)
- [x] Skills stored in Qdrant with embeddings
- [x] Skill retrieval tested with sample queries
- [x] Documentation of each skill

---

### Phase 3: Sentinel Agent (Week 3-4)

**Goal:** Real-time event watching with skill-based classification.

#### 3.1 Sentinel Architecture

```python
class SentinelAgent:
    """
    Watches Kubernetes events and logs in real-time.
    Classifies events using skill library.
    Emits structured events to bus.
    """

    def __init__(
        self,
        skill_library: SkillLibrary,
        event_bus: EventBus,
        mcp_client: MCPClient,  # kubernetes-mcp-server
    ):
        self.skills = skill_library
        self.bus = event_bus
        self.mcp = mcp_client

    async def watch_events(self):
        """Subscribe to Kubernetes events via MCP."""
        async for event in self.mcp.subscribe("events_list"):
            classification = await self.classify_event(event)
            if classification.is_actionable:
                await self.bus.publish(
                    EventType.K8S_ISSUE_DETECTED,
                    {
                        "event": event,
                        "classification": classification,
                        "matching_skills": classification.skill_ids,
                    }
                )

    async def classify_event(self, event: K8sEvent) -> Classification:
        """Find skills whose preconditions match this event."""
        matching_skills = await self.skills.search(
            query=f"{event.type}: {event.message}",
            filters={"domain": "k8s"},
        )
        return Classification(
            severity=self.infer_severity(event, matching_skills),
            is_actionable=len(matching_skills) > 0,
            skill_ids=[s.id for s in matching_skills],
        )
```

#### 3.2 MCP Server Needs Assessment

**Sentinel needs:**
1. ✅ `kubernetes-mcp-server` - events, pod status (deployed)
2. ❓ `loki-mcp-server` - log streaming (not available)

**Decision Point:** Do we need real-time log streaming?
- If yes: Build minimal loki-mcp-server
- If no: Use periodic log queries via kubectl logs (already in k8s-mcp)

#### Phase 3 Deliverables

- [x] Sentinel agent implementation
- [x] Event classification using skill preconditions
- [x] Integration with kubernetes-mcp-server
- [x] Events published to Redis Streams
- [x] OTel tracing for event processing
- [x] Decision on loki-mcp-server necessity (deferred - using kubectl logs via MCP)

---

### Phase 4: Healer Agent (Week 4-5)

**Goal:** Self-verifying remediation using skills and MCP tools.

#### 4.1 Healer Architecture

```python
class HealerAgent:
    """
    Receives issue events from bus.
    Retrieves matching skills.
    Executes skill actions via MCP.
    Verifies success.
    Requests approval for dangerous actions.
    """

    async def handle_issue(self, issue: IssueEvent):
        # 1. Retrieve matching skills
        skills = await self.skill_library.search(
            query=issue.description,
            filters={"domain": "k8s", "category": "remediation"},
        )

        if not skills:
            await self.escalate("No matching skills found", issue)
            return

        skill = skills[0]  # Highest confidence match

        # 2. Check if approval needed
        if skill.requires_approval:
            approved = await self.request_approval(skill, issue)
            if not approved:
                return

        # 3. Execute skill actions via MCP
        for action in skill.actions:
            result = await self.mcp.call(
                server=action.mcp_tool.server,
                tool=action.mcp_tool.tool,
                params=self.resolve_params(action.mcp_tool.params, issue),
            )

        # 4. Verify success
        verified = await self.verify_success(skill, issue)

        # 5. Update skill confidence
        await self.skill_library.record_outcome(
            skill_id=skill.id,
            success=verified,
        )

        # 6. Emit completion event
        await self.bus.publish(
            EventType.K8S_REMEDIATION_COMPLETED,
            {"issue": issue, "skill": skill.id, "success": verified},
        )
```

#### 4.2 Verification Loop (Voyager-Inspired)

```python
async def verify_success(self, skill: Skill, issue: IssueEvent) -> bool:
    """
    Check each success criterion.
    Use LLM as critic if criteria are natural language.
    """
    for criterion in skill.success_criteria:
        # Get current state via MCP
        current_state = await self.get_current_state(issue.resource)

        # Use LLM to evaluate criterion
        evaluation = await self.critic.evaluate(
            criterion=criterion,
            before_state=issue.original_state,
            after_state=current_state,
        )

        if not evaluation.met:
            return False

    return True
```

#### 4.3 Approval Flow Integration

```python
async def request_approval(self, skill: Skill, issue: IssueEvent) -> bool:
    """Post to Discord and wait for reaction."""
    request = ApprovalRequest(
        action=skill.name,
        reason=f"Issue: {issue.description}",
        resource=issue.resource,
        skill_id=skill.id,
    )

    message = await self.discord.post_approval_request(request)
    reaction = await self.discord.wait_for_reaction(
        message_id=message.id,
        timeout_seconds=300,  # 5 minutes
        valid_reactions=["✅", "❌"],
    )

    return reaction == "✅"
```

#### Phase 4 Deliverables

- [x] Healer agent implementation
- [x] Skill execution via MCP tools
- [x] Success verification with LLM critic
- [x] Discord approval integration
- [x] Skill confidence updates
- [x] Remediation tracing and metrics

---

### Phase 5: Explorer Agent (Week 5-6)

**Goal:** Propose and learn new skills with human approval.

#### 5.1 Explorer Architecture

```python
class ExplorerAgent:
    """
    Analyzes knowledge gaps.
    Proposes new skills based on patterns.
    Requires approval before adding skills.
    Can request new MCP servers when capabilities missing.
    """

    async def propose_exploration(self) -> ExplorationProposal:
        # 1. Analyze recent incidents without matching skills
        unmatched = await self.get_unmatched_incidents(days=7)

        # 2. Cluster similar incidents
        clusters = await self.cluster_incidents(unmatched)

        # 3. For each cluster, propose a skill
        proposals = []
        for cluster in clusters:
            proposal = await self.generate_skill_proposal(cluster)

            # Check if required MCP tools exist
            for action in proposal.actions:
                if not await self.mcp_available(action.mcp_tool.server):
                    proposal.requires_mcp_server = action.mcp_tool.server

            proposals.append(proposal)

        return proposals

    async def generate_skill_proposal(self, cluster: IncidentCluster) -> SkillProposal:
        """Use LLM to propose a skill based on incident patterns."""
        prompt = f"""
        Analyze these similar incidents and propose a skill to handle them.

        Incidents:
        {cluster.incidents}

        Available MCP servers and tools:
        {self.available_mcp_tools}

        Propose a skill with:
        1. Preconditions (when should this skill apply?)
        2. Actions (which MCP tools to use?)
        3. Success criteria (how to verify?)

        If needed MCP tools don't exist, specify which MCP server should be added.
        """
        ...
```

#### 5.2 Skill Approval Flow

```
Explorer proposes skill
    │
    ▼
Post skill definition to Discord for review
    │
    ▼
Human reviews preconditions, actions, criteria
    │
    ├─── ✅ → Add skill to library with low initial confidence
    ├─── 📝 → Human provides feedback, Explorer refines
    └─── ❌ → Reject with reason, log for learning
```

#### 5.3 MCP Server Requests

When Explorer identifies a capability gap:

```python
async def request_mcp_server(self, server: str, reason: str):
    """Emit event requesting new MCP server deployment."""
    await self.bus.publish(
        EventType.SYSTEM_MCP_SERVER_REQUESTED,
        {
            "server": server,
            "reason": reason,
            "proposed_by": "explorer",
            "priority": "medium",
            "incidents_affected": self.affected_incident_count,
        }
    )

    # Also post to Discord for visibility
    await self.discord.post(
        f"**MCP Server Requested:** `{server}`\n"
        f"**Reason:** {reason}\n"
        f"**Affected incidents:** {self.affected_incident_count}"
    )
```

#### Phase 5 Deliverables

- [x] Explorer agent implementation
- [x] Incident clustering for pattern detection
- [x] Skill proposal generation
- [x] Human approval flow for new skills
- [x] MCP server request mechanism
- [x] Integration tests

---

### Phase 6: News-Monitor Enhancement (Week 6-7)

**Goal:** Add source discovery Explorer to news-monitor.

#### 6.1 News Explorer Focus

Based on your priority (source discovery), the news Explorer will:

1. **Analyze coverage gaps** - Topics mentioned but poorly covered
2. **Discover new sources** - Find RSS feeds covering gap topics
3. **Validate sources** - Check reliability, frequency, relevance
4. **Propose additions** - Suggest new feeds for approval

#### 6.2 Implementation

```python
class NewsExplorerAgent:
    """
    Discovers new RSS feed sources based on coverage gaps.
    """

    async def analyze_coverage_gaps(self) -> list[CoverageGap]:
        """Find topics that are trending but poorly covered."""
        # Query recent articles from memory
        articles = await self.memory.query_articles_since(days=7)

        # Find topics with few sources
        topic_sources = defaultdict(set)
        for article in articles:
            for entity in article.entities:
                topic_sources[entity].add(article.source)

        gaps = [
            CoverageGap(topic=topic, source_count=len(sources))
            for topic, sources in topic_sources.items()
            if len(sources) < 3 and self.is_important_topic(topic)
        ]

        return gaps

    async def discover_sources(self, gap: CoverageGap) -> list[SourceProposal]:
        """Use web search to find RSS feeds covering the gap topic."""
        # This could use an MCP server for web search if available
        search_query = f"{gap.topic} RSS feed AI technology news"

        # For now, use existing web search capability
        results = await self.web_search(search_query)

        proposals = []
        for result in results:
            if await self.validate_rss_feed(result.url):
                proposals.append(SourceProposal(
                    url=result.url,
                    topic=gap.topic,
                    reason=f"Covers {gap.topic} with {result.frequency} updates",
                ))

        return proposals
```

#### Phase 6 Deliverables

- [x] News Explorer agent
- [x] Coverage gap analysis
- [x] Source discovery mechanism
- [x] Source validation
- [x] Human approval for new sources
- [x] Integration with existing news-monitor

---

### Phase 7: Integration & Polish (Week 7-8)

**Goal:** Full system integration, dashboards, documentation.

#### 7.1 Integration Testing

- [x] End-to-end test: Issue → Sentinel → Healer → Verification
- [x] Cross-domain event flow test
- [x] Approval flow test
- [x] Skill learning cycle test

#### 7.2 Grafana Dashboards

| Dashboard | Panels | Status |
|-----------|--------|--------|
| Agent Overview | Active agents, events/min, MCP calls/min | ✅ Deployed |
| Skill Performance | Execution count, success rate, confidence trends | ✅ Deployed |
| Remediation Activity | Issues detected, auto-resolved, escalated | ✅ Deployed |
| Approvals | Pending, approved, rejected, latency | ✅ Deployed |

#### 7.3 Documentation

- [x] Architecture overview in docs/ (`docs/federated_architecture.md`)
- [x] Skill authoring guide (included in `federated_architecture.md`)
- [x] MCP server integration guide (`docs/MCP_SERVER_INTEGRATION.md`)
- [x] Runbook for common operations (`docs/AGENT_RUNBOOK.md`)

#### Phase 7 Deliverables

- [x] Integration test suite
- [x] Grafana dashboards deployed
- [x] Documentation complete
- [x] Production deployment

---

## New Infrastructure Required

| Component | Effort | Priority | Notes |
|-----------|--------|----------|-------|
| prometheus-mcp-server | Medium | Phase 3-4 | Needed for metrics-based skills |
| loki-mcp-server | Medium | Phase 3 | Optional - evaluate need |
| discord-mcp-server | Low | Phase 1 | For approval reactions, may use direct API |

---

## Timeline Summary

| Week | Phase | Focus |
|------|-------|-------|
| 1-2 | Phase 1 | Core framework (skills, events, approvals, observability) |
| 2-3 | Phase 2 | Extract K8s skills from existing code |
| 3-4 | Phase 3 | Sentinel agent (event watching) |
| 4-5 | Phase 4 | Healer agent (skill execution, verification) |
| 5-6 | Phase 5 | Explorer agent (skill learning) |
| 6-7 | Phase 6 | News Explorer (source discovery) |
| 7-8 | Phase 7 | Integration, dashboards, documentation |

---

## Success Criteria

| Metric | Target |
|--------|--------|
| Skills extracted from existing code | 10-15 |
| Mean time to detection (MTTD) | < 5 minutes |
| Auto-remediation rate | > 50% of known patterns |
| Skill proposals per week | 2-3 |
| MCP server utilization | 100% (no duplicate tool code) |
| Dashboard coverage | All key metrics visible |

---

## Key Principles Recap

1. **MCP-first** - Actions via MCP servers, not custom code
2. **Skills are knowledge** - When/how to use MCP tools, not implementations
3. **Request missing capabilities** - Don't work around, request MCP servers
4. **Human in the loop** - Approvals for dangerous actions and new skills
5. **Observable from day one** - OTel tracing, Prometheus metrics, Grafana dashboards
6. **Simple over clever** - Leverage existing infrastructure, avoid duplication
