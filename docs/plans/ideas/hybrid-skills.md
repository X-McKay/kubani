# Plan: Hybrid Skills Architecture with A2A

This document outlines a phased approach to adopting Claude Agent Skills format for documentation/discovery while keeping the existing execution engine, plus completing the Strands A2A integration for inter-agent communication.

## Executive Summary

**Goal:** Best of both worlds - keep execution precision (MCP refs, confidence tracking, semantic search) while gaining progressive loading, cross-platform compatibility, and standardized agent discovery.

**Approach:**
1. Create SKILL.md files that mirror existing Python skills for documentation/discovery
2. Keep Pydantic `Skill` models as the source of truth for execution
3. Build a loader that syncs SKILL.md ↔ Skill objects
4. Complete A2A implementation for agent-to-agent communication
5. Adopt Strands Swarm pattern for dynamic multi-agent coordination

**Timeline:** 6 phases, can be done incrementally with working software after each phase

---

## Architecture Overview

### Current State
```
┌─────────────────────────────────────────────────────────────┐
│                    CURRENT ARCHITECTURE                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  skills.py (Python)     ──────►  Qdrant (vector search)     │
│  ├── Skill objects               ├── Semantic matching      │
│  ├── MCPToolReference            ├── Confidence filtering   │
│  └── SkillAction                 └── Domain/category filter │
│                                                              │
│  events/bus.py          ──────►  Redis Streams              │
│  └── EventBus                    └── Consumer groups        │
│                                                              │
│  communication/a2a.py   ──────►  Stub (not implemented)     │
│  └── AgentRegistry                                          │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Target State
```
┌─────────────────────────────────────────────────────────────┐
│                     HYBRID ARCHITECTURE                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  .claude/skills/k8s/    ◄─────►  agents/core/skills/        │
│  ├── SKILL.md (docs)      sync   ├── Skill objects          │
│  └── skill.json (exec)    ◄───   ├── MCPToolReference       │
│                                  └── SkillAction             │
│                                          │                   │
│                                          ▼                   │
│                                   Qdrant (unchanged)         │
│                                                              │
│  Redis Streams          ──────►  Internal events (keep)     │
│  └── Fast, durable               └── K8S_ISSUE_DETECTED     │
│                                                              │
│  Strands A2A            ──────►  External discovery         │
│  ├── A2AServer                   ├── Agent cards            │
│  └── A2AAgentTool                └── Cross-agent calls      │
│                                                              │
│  Strands Swarm          ──────►  Dynamic coordination       │
│  └── HandoffTool                 └── Sentinel→Healer→...    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Skill File Structure

**Goal:** Create filesystem-based skill definitions that can be loaded by Claude while maintaining execution metadata.

### 1.1 Directory Structure

Create a new skill directory structure:

```
.claude/skills/
├── k8s/                              # Domain directory
│   ├── remediation/                  # Category subdirectory
│   │   ├── restart-crashloop/
│   │   │   ├── SKILL.md              # Human-readable (Claude loads this)
│   │   │   └── execution.json        # Machine-readable (our library loads this)
│   │   ├── handle-imagepullbackoff/
│   │   │   ├── SKILL.md
│   │   │   └── execution.json
│   │   └── scale-deployment/
│   │       ├── SKILL.md
│   │       └── execution.json
│   ├── diagnostic/
│   │   ├── investigate-pod-failure/
│   │   │   ├── SKILL.md
│   │   │   └── execution.json
│   │   └── check-node-resources/
│   │       ├── SKILL.md
│   │       └── execution.json
│   └── collection/
│       ├── list-recent-events/
│       │   ├── SKILL.md
│       │   └── execution.json
│       └── list-pods-in-namespace/
│           ├── SKILL.md
│           └── execution.json
└── news/                             # Future: news domain skills
    └── ...
```

### 1.2 SKILL.md Format

Each skill gets a human-readable SKILL.md:

```markdown
---
name: restart-crashloop
description: Restart pods stuck in CrashLoopBackOff. Use when a pod has been crashing repeatedly and a simple restart might resolve a transient issue.
---

# Restart CrashLoopBackOff Pod

Restart a pod that is stuck in CrashLoopBackOff state. This is appropriate when the pod has been crashing repeatedly and a simple restart might resolve a transient issue.

## When to Use

This skill should be applied when:
- Pod status is CrashLoopBackOff
- Pod has restarted more than 3 times
- Pod is not part of a Job or CronJob
- No OOMKilled events in last 10 minutes

## Parameters

- `pod_name`: Name of the pod to restart (required)
- `namespace`: Kubernetes namespace (required)

## Steps

1. **Delete pod to trigger recreation**
   - Uses: `kubernetes-mcp-server:pods_delete`
   - Timeout: 30 seconds

## Success Criteria

- New pod created within 30 seconds
- New pod reaches Running state within 2 minutes
- No CrashLoopBackOff within 5 minutes of restart

## Failure Handling

If pod does not reach Running state:
1. Check events for the new pod
2. Check logs from the new pod
3. Escalate to human if pattern repeats 3 times

## Safety

- **Requires Approval:** No
- **Confidence:** 85%
- **Tags:** pod, crashloop, restart, remediation
```

### 1.3 execution.json Format

Machine-readable execution metadata:

```json
{
  "id": "k8s-restart-crashloop",
  "domain": "k8s",
  "category": "remediation",
  "actions": [
    {
      "description": "Delete the pod to trigger recreation",
      "mcp_tool": {
        "server": "kubernetes-mcp-server",
        "tool": "pods_delete",
        "params": {
          "name": "$pod_name",
          "namespace": "$namespace"
        }
      },
      "timeout_seconds": 30
    }
  ],
  "rollback_actions": null,
  "requires_approval": false,
  "prerequisite_skills": [],
  "confidence": 0.85,
  "success_count": 0,
  "failure_count": 0,
  "created_by": "manual"
}
```

### 1.4 Deliverables

| Item | Description | Files Changed |
|------|-------------|---------------|
| Skill directories | Create 8 K8s skill directories | `.claude/skills/k8s/**` |
| SKILL.md files | Human-readable skill documentation | 8 new files |
| execution.json files | Machine-readable execution metadata | 8 new files |
| Migration script | Convert existing Python skills to file format | New script |

### 1.5 Decision Points

**Q1: Should execution.json be generated from SKILL.md or vice versa?**
- Option A: SKILL.md is source of truth, execution.json is generated
- Option B: execution.json is source of truth, SKILL.md is generated
- **Recommended:** Option B - execution.json is source of truth, SKILL.md is human documentation that can be manually edited for better readability

**Q2: Where should skill files live?**
- Option A: `.claude/skills/` (consistent with existing Claude Skills)
- Option B: `agents/core/skills/` (near the code that uses them)
- Option C: `skills/` at project root (dedicated location)
- **Recommended:** Option A - leverages Claude's built-in skill discovery

**Q3: How to handle runtime state (confidence, counts)?**
- Option A: Store in execution.json, update on disk
- Option B: Store only in Qdrant, execution.json is initial values
- **Recommended:** Option B - execution.json has initial values, Qdrant is runtime state

---

## Phase 2: Skill Loader

**Goal:** Build a loader that reads skill files and populates the Qdrant library.

### 2.1 New Loader Module

Create `agents/core/src/core_agents/skills/loader.py`:

```python
"""
Skill loader - reads SKILL.md and execution.json to create Skill objects.
"""

from pathlib import Path
from core_agents.skills.schema import Skill, SkillAction, MCPToolReference

class SkillLoader:
    """Loads skills from filesystem into Skill objects."""

    def __init__(self, skills_dir: Path | str = ".claude/skills"):
        self.skills_dir = Path(skills_dir)

    def load_all(self) -> list[Skill]:
        """Load all skills from the filesystem."""
        ...

    def load_skill(self, skill_path: Path) -> Skill:
        """Load a single skill from directory containing SKILL.md and execution.json."""
        ...

    def sync_to_library(self, library: SkillLibrary) -> SyncResult:
        """Sync filesystem skills to the library (add new, update existing)."""
        ...
```

### 2.2 Bootstrap Changes

Modify `k8s_monitor/federated/skills.py`:

```python
# Before: Skills defined inline
K8S_SKILLS: list[Skill] = [Skill(...), ...]

# After: Skills loaded from filesystem
from core_agents.skills.loader import SkillLoader

async def bootstrap_k8s_skills() -> list[str]:
    loader = SkillLoader()
    library = await get_skill_library()
    result = await loader.sync_to_library(library, domain="k8s")
    return result.added_ids
```

### 2.3 Validation

Add validation to ensure execution.json matches SKILL.md:

```python
def validate_skill_consistency(skill_dir: Path) -> list[ValidationError]:
    """Ensure execution.json and SKILL.md are consistent."""
    # Check that execution.json actions match SKILL.md steps
    # Check that preconditions in execution.json match "When to Use"
    # Check that success_criteria match "Success Criteria"
    ...
```

### 2.4 Deliverables

| Item | Description | Files Changed |
|------|-------------|---------------|
| SkillLoader class | Load skills from filesystem | `agents/core/src/core_agents/skills/loader.py` |
| Sync logic | Sync filesystem → Qdrant | Same file |
| Validation | Ensure consistency | Same file |
| Update bootstrap | Use loader instead of inline | `k8s_monitor/federated/skills.py` |
| Tests | Test loader and sync | `agents/core/tests/test_skill_loader.py` |

### 2.5 Decision Points

**Q4: How to handle skill updates?**
- Option A: Overwrite Qdrant on every startup
- Option B: Only add new skills, never update existing
- Option C: Smart merge (update if execution.json changed, keep runtime stats)
- **Recommended:** Option C - smart merge preserves learning while allowing updates

**Q5: Should loader run at startup or on-demand?**
- Option A: Startup sync (always consistent but slower startup)
- Option B: On-demand sync (faster startup, manual sync command)
- Option C: Watch mode (inotify-based hot reload)
- **Recommended:** Option A for production, Option C optional for development

---

## Phase 3: A2A Server Implementation

**Goal:** Expose agents via the A2A protocol for external discovery and invocation.

### 3.1 Complete A2AServer Integration

Update `agents/core/src/core_agents/communication/a2a.py`:

```python
from strands import Agent
from strands.multiagent.a2a import A2AServer

def create_kubani_a2a_server(
    agent: Agent,
    agent_info: AgentInfo,
    port: int = 9000,
) -> A2AServer:
    """Create an A2A server with Kubani agent metadata."""

    # Convert capabilities to A2A skills
    skills = [cap.to_a2a_skill() for cap in agent_info.capabilities]

    return A2AServer(
        agent,
        host="0.0.0.0",
        port=port,
        version=agent_info.version,
        skills=skills,
    )
```

### 3.2 Agent Info Definitions

Create agent info files for each agent:

`agents/k8s-monitor/src/k8s_monitor/agent_info.py`:
```python
from core_agents.communication import AgentCapability, AgentInfo

K8S_MONITOR_AGENT = AgentInfo(
    id="k8s-monitor",
    name="Kubernetes Monitor",
    description="Monitors Kubernetes cluster health and performs remediation",
    capabilities=[
        AgentCapability(
            name="pod-diagnosis",
            description="Diagnose failing pods and identify root cause",
            tags=["k8s", "pods", "diagnosis"],
        ),
        AgentCapability(
            name="pod-remediation",
            description="Remediate common pod issues like CrashLoopBackOff",
            tags=["k8s", "pods", "remediation"],
        ),
        AgentCapability(
            name="cluster-health",
            description="Check overall cluster health and resource usage",
            tags=["k8s", "cluster", "health"],
        ),
    ],
    endpoint="k8s-monitor.ai-agents.svc.cluster.local",
    version="0.3.0",
)
```

### 3.3 Worker Integration

Update workers to start A2A server:

```python
# k8s_monitor/worker.py
from k8s_monitor.agent_info import K8S_MONITOR_AGENT
from core_agents.communication import create_kubani_a2a_server, register_agent_on_startup

async def main():
    # Register with global registry
    await register_agent_on_startup(K8S_MONITOR_AGENT)

    # Create agent
    agent = Agent(...)

    # Start A2A server (runs alongside Temporal worker)
    a2a_server = create_kubani_a2a_server(agent, K8S_MONITOR_AGENT)

    # Run both
    await asyncio.gather(
        temporal_worker.run(),
        a2a_server.serve_async(),  # Non-blocking
    )
```

### 3.4 Kubernetes Deployment Updates

Add A2A port to deployments:

```yaml
# gitops/apps/ai-agents/k8s-monitor/deployment.yaml
spec:
  template:
    spec:
      containers:
        - name: k8s-monitor
          ports:
            - containerPort: 9000
              name: a2a
              protocol: TCP
---
# Add Service for A2A
apiVersion: v1
kind: Service
metadata:
  name: k8s-monitor-a2a
  namespace: ai-agents
spec:
  selector:
    app.kubernetes.io/name: k8s-monitor
  ports:
    - port: 9000
      targetPort: a2a
      protocol: TCP
```

### 3.5 Deliverables

| Item | Description | Files Changed |
|------|-------------|---------------|
| A2A server factory | Create servers with Kubani config | `core_agents/communication/a2a.py` |
| Agent info definitions | Define capabilities per agent | `k8s_monitor/agent_info.py`, etc. |
| Worker integration | Start A2A alongside Temporal | `k8s_monitor/worker.py` |
| K8s manifests | Add A2A ports and services | `gitops/apps/ai-agents/*/` |
| Tests | Test A2A server creation | `agents/core/tests/test_a2a.py` |

### 3.6 Decision Points

**Q6: Should A2A run on same port as health checks or separate?**
- Option A: Same port, different paths (/a2a, /health)
- Option B: Separate ports (9000 for A2A, 8080 for health)
- **Recommended:** Option B - cleaner separation, easier firewall rules

**Q7: How to handle A2A authentication?**
- Option A: No auth (internal cluster only)
- Option B: mTLS via service mesh
- Option C: Bearer token auth
- **Recommended:** Option A initially, add mTLS via Istio/Linkerd later

---

## Phase 4: A2A Client Integration

**Goal:** Enable agents to discover and call other agents via A2A.

### 4.1 A2A Agent Tool

Create a tool wrapper for calling other agents:

```python
# agents/core/src/core_agents/communication/a2a_tool.py

from strands import tool
from a2a.client import A2AClient

class A2AAgentTool:
    """Tool that wraps a remote A2A agent for local invocation."""

    def __init__(self, agent_url: str, agent_name: str):
        self.client = A2AClient(agent_url)
        self.agent_name = agent_name

    @tool
    async def call_agent(self, message: str) -> str:
        """Call the remote agent with a message."""
        response = await self.client.send_message(message)
        return response.content
```

### 4.2 Dynamic Agent Discovery

```python
# agents/core/src/core_agents/communication/discovery.py

async def discover_agents_for_capability(capability: str) -> list[AgentInfo]:
    """Discover agents that provide a capability via K8s service discovery."""

    # 1. Check local registry
    registry = get_agent_registry()
    local = registry.find_agents_for(capability)

    # 2. Query K8s for A2A services
    # kubectl get svc -l a2a.io/enabled=true
    ...

    return local + discovered
```

### 4.3 Deliverables

| Item | Description | Files Changed |
|------|-------------|---------------|
| A2AAgentTool | Wrap remote agents as tools | `core_agents/communication/a2a_tool.py` |
| Discovery | Find agents by capability | `core_agents/communication/discovery.py` |
| Integration | Use in Healer for delegation | `k8s_monitor/federated/healer.py` |
| Tests | Test discovery and invocation | `agents/core/tests/test_a2a_client.py` |

### 4.4 Decision Points

**Q8: Should agents be exposed as individual tools or a single "delegate" tool?**
- Option A: One tool per agent (explicit, type-safe)
- Option B: Single delegate tool with agent name param (flexible)
- **Recommended:** Option B - more flexible for dynamic discovery

---

## Phase 5: Strands Swarm Integration

**Goal:** Replace custom Sentinel→Healer→Explorer event pipeline with Strands Swarm.

### 5.1 Swarm Definition

Create a K8s remediation swarm:

```python
# agents/k8s-monitor/src/k8s_monitor/federated/swarm.py

from strands import Agent
from strands.multiagent import Swarm

def create_k8s_remediation_swarm() -> Swarm:
    """Create a swarm for K8s issue remediation."""

    sentinel = Agent(
        name="sentinel",
        description="Watches for K8s issues and hands off to specialists",
        tools=[k8s_event_watcher, handoff_to_healer],
    )

    healer = Agent(
        name="healer",
        description="Remediates K8s issues using skills from the library",
        tools=[skill_executor, verify_remediation, handoff_to_explorer],
    )

    explorer = Agent(
        name="explorer",
        description="Proposes new skills for unhandled issues",
        tools=[analyze_incidents, propose_skill, request_mcp_server],
    )

    return Swarm(
        agents=[sentinel, healer, explorer],
        max_handoffs=10,
        shared_state={"correlation_id": None},
    )
```

### 5.2 Handoff Tools

```python
from strands.multiagent import HandoffTool

handoff_to_healer = HandoffTool(
    target_agent="healer",
    description="Hand off to healer when an issue is detected",
)

handoff_to_explorer = HandoffTool(
    target_agent="explorer",
    description="Hand off to explorer when no skill matches the issue",
)
```

### 5.3 Migration Path

| Current | Swarm Equivalent |
|---------|------------------|
| `SentinelAgent` subscribes to K8s events | Sentinel agent with event watcher tool |
| Publishes `K8S_ISSUE_DETECTED` to Redis | Uses `handoff_to_healer` |
| `HealerAgent` subscribes to events | Healer receives context from handoff |
| Updates skill confidence | Same, via skill library |
| Publishes completion event | Uses `handoff_to_explorer` or returns |

### 5.4 Keep Redis for Durability

The Swarm pattern handles in-memory coordination. Keep Redis Streams for:
- Durability across restarts
- Audit logging
- Cross-cluster events (future)

```python
# Hybrid: Swarm for coordination, Redis for persistence
async def run_remediation(issue: K8sIssue):
    # Log to Redis for durability
    await event_bus.publish(EventType.K8S_ISSUE_DETECTED, issue.dict())

    # Run swarm for coordination
    swarm = create_k8s_remediation_swarm()
    result = await swarm.invoke(f"Handle issue: {issue}")

    # Log completion to Redis
    await event_bus.publish(EventType.K8S_REMEDIATION_COMPLETED, result)
```

### 5.5 Deliverables

| Item | Description | Files Changed |
|------|-------------|---------------|
| Swarm definition | K8s remediation swarm | `k8s_monitor/federated/swarm.py` (update) |
| Handoff tools | Sentinel→Healer→Explorer | Same file |
| Migration | Refactor agents to use swarm | All federated/*.py |
| Tests | Test swarm coordination | `tests/test_swarm.py` |

### 5.6 Decision Points

**Q9: Full migration to Swarm or hybrid with existing agents?**
- Option A: Full migration (cleaner, but more work)
- Option B: Hybrid (keep existing, add Swarm as alternative)
- **Recommended:** Option B initially, migrate fully once proven

**Q10: How to handle approval in Swarm context?**
- Option A: Approval as a tool (blocks agent until approved)
- Option B: Approval as separate agent in swarm
- Option C: Keep existing Discord approver, call from Healer
- **Recommended:** Option C - approval is orthogonal to coordination

---

## Phase 6: Documentation and Testing

**Goal:** Ensure everything works together and is well-documented.

### 6.1 Update Documentation

| Document | Updates |
|----------|---------|
| `docs/federated_architecture.md` | Add skill file structure, A2A, Swarm |
| `CLAUDE.md` | Add skill authoring instructions |
| New: `docs/skills_authoring.md` | How to create new skills |
| New: `docs/a2a_integration.md` | A2A protocol usage |

### 6.2 Integration Tests

```python
# agents/core/tests/test_hybrid_integration.py

async def test_skill_file_to_qdrant_sync():
    """Skill files sync correctly to Qdrant."""

async def test_a2a_discovery_and_invocation():
    """Agents can discover and call each other via A2A."""

async def test_swarm_remediation_flow():
    """Swarm handles issue → diagnosis → remediation → verification."""

async def test_hybrid_event_persistence():
    """Redis persists events while Swarm coordinates."""
```

### 6.3 End-to-End Test

```python
async def test_e2e_crashloop_remediation():
    """Full flow: CrashLoopBackOff detected → skill matched → remediated → verified."""

    # 1. Create a failing pod
    # 2. Wait for Sentinel to detect
    # 3. Verify Healer picks up
    # 4. Verify skill executed via MCP
    # 5. Verify pod recovers
    # 6. Check skill confidence updated
```

### 6.4 Deliverables

| Item | Description | Files Changed |
|------|-------------|---------------|
| Architecture docs | Update all docs | `docs/*.md` |
| Skill authoring guide | How to create skills | `docs/skills_authoring.md` |
| Integration tests | Test full flow | `tests/test_*_integration.py` |
| E2E tests | Full cluster tests | `tests/e2e/` |

---

## Summary

### Phase Timeline

| Phase | Description | Effort | Dependencies |
|-------|-------------|--------|--------------|
| 1 | Skill File Structure | 2-3 days | None |
| 2 | Skill Loader | 2-3 days | Phase 1 |
| 3 | A2A Server | 2-3 days | None (parallel with 1-2) |
| 4 | A2A Client | 1-2 days | Phase 3 |
| 5 | Strands Swarm | 3-4 days | Phases 2, 4 |
| 6 | Documentation & Testing | 2-3 days | All phases |

**Total:** ~14-18 days of work

### Key Decision Points Summary

| # | Question | Recommended |
|---|----------|-------------|
| Q1 | Source of truth | execution.json (machine-readable) |
| Q2 | Skill file location | `.claude/skills/` |
| Q3 | Runtime state storage | Qdrant only (execution.json = initial) |
| Q4 | Skill update strategy | Smart merge |
| Q5 | Loader timing | Startup sync |
| Q6 | A2A port strategy | Separate port (9000) |
| Q7 | A2A auth | None initially (cluster internal) |
| Q8 | Agent tool pattern | Single delegate tool |
| Q9 | Swarm migration | Hybrid first |
| Q10 | Approval in Swarm | Keep existing Discord approver |

### What's Preserved

- Semantic skill search via Qdrant
- Confidence tracking and learning
- MCP tool references with parameter templates
- Rollback actions
- Prerequisite skills
- Redis Streams for durability
- Discord approvals

### What's Gained

- Progressive context loading for Claude
- Skill discoverability across Claude products
- A2A protocol for agent discovery
- Cross-platform agent communication
- Strands Swarm coordination patterns
- Human-readable skill documentation
