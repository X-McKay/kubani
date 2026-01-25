# K8s-Monitor Evolution: From Workflow to Truly Agentic System

> **ARCHIVED**: This document was written for k8s-monitor v0.2.14 and represents a Voyager-inspired architectural vision. Current version is v0.4.0. Many ideas from this document have influenced the evolution of the agent system, while others have been deprioritized in favor of simpler, more maintainable approaches. See [docs/planning/roadmap/ai-agents.md](../../planning/roadmap/ai-agents.md) for current roadmap.

## Executive Summary

This document proposes a fundamental reimagining of the k8s-monitor agent, drawing inspiration from the [Voyager](https://voyager.minedojo.org/) project's approach to lifelong learning and the [Strands Agents SDK](https://strandsagents.com/) multi-agent patterns. The goal is to transform the current scheduled workflow-based system into a continuously learning, multi-agent ecosystem that autonomously monitors, learns, and improves over time.

---

## Table of Contents

1. [Current State Analysis](#current-state-analysis)
2. [Inspiration: Voyager's Approach](#inspiration-voyagers-approach)
3. [Proposed Architecture](#proposed-architecture)
4. [Agent Specifications](#agent-specifications)
5. [Skill Library System](#skill-library-system)
6. [Continuous Learning Loop](#continuous-learning-loop)
7. [Memory Architecture](#memory-architecture)
8. [Implementation Phases](#implementation-phases)
9. [Infrastructure Requirements](#infrastructure-requirements)
10. [Success Metrics](#success-metrics)

---

## Current State Analysis

### What We Have Today

The current k8s-monitor (v0.2.14) is a **workflow-based system** with the following characteristics:

```
┌─────────────────────────────────────────────────────────────┐
│                    Current Architecture                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Temporal Scheduler (hourly)                                 │
│         │                                                    │
│         ▼                                                    │
│  ┌─────────────────┐                                        │
│  │ Health Check    │──▶ Swarm Analysis ──▶ Discord Alert    │
│  │ Workflow        │                                         │
│  └─────────────────┘                                        │
│         │                                                    │
│         ▼ (if issues found)                                  │
│  ┌─────────────────┐                                        │
│  │ Remediation     │──▶ 3 Attempts ──▶ Escalate             │
│  │ Workflow        │                                         │
│  └─────────────────┘                                        │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Strengths:**
- Durable workflow orchestration via Temporal
- Multi-agent swarm with 6 specialists (Triage, Scout, Diagnostician, Remediator, Memory, Discord)
- mem0-based memory for learning from past incidents
- Safe remediation with guards (restart, scale only)
- Comprehensive Discord notifications

**Limitations:**
1. **Reactive, not proactive** - Only runs on schedule or when triggered
2. **Limited skill repertoire** - Fixed set of remediation actions (restart, scale)
3. **No curriculum/exploration** - Doesn't actively seek to learn new patterns
4. **No skill composition** - Can't build complex behaviors from simple ones
5. **Memory is flat** - No hierarchical organization of knowledge
6. **Single perspective** - All agents share same model/context window
7. **No self-improvement** - Can't generate new diagnostic tools or runbooks

---

## Inspiration: Voyager's Approach

[Voyager](https://arxiv.org/abs/2305.16291) demonstrates three transformative concepts for autonomous agents:

### 1. Automatic Curriculum

Voyager doesn't wait to be told what to learn. It continuously proposes tasks based on:
- Current capabilities (what can I do now?)
- Environment state (what's available to explore?)
- Exploration progress (what haven't I tried?)

**K8s Application:** An agent that proactively investigates cluster patterns, not just reacting to failures.

### 2. Skill Library with Semantic Retrieval

Skills are stored as executable code with semantic embeddings:
```
Skill: "drain_node_safely"
├── Description embedding (for retrieval)
├── Executable code (the actual procedure)
├── Preconditions (when to use)
├── Success criteria (how to verify)
└── Composition links (builds on: cordon_node, evict_pods)
```

**K8s Application:** Build a library of runbooks that compound over time.

### 3. Iterative Self-Verification

Before committing a skill, Voyager:
1. Executes the generated program
2. Observes environment feedback
3. Uses a critic (GPT-4) to verify success
4. Iterates until verified or gives up

**K8s Application:** Don't just run remediation - verify it worked and learn from failures.

---

## Proposed Architecture

### Multi-Agent Constellation

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                        KUBANI AGENT CONSTELLATION                             │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                        CONTINUOUS AGENTS                                 │ │
│  │                    (Always running, event-driven)                        │ │
│  │                                                                          │ │
│  │  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐                 │ │
│  │  │   Sentinel   │   │   Analyst    │   │   Prophet    │                 │ │
│  │  │   Agent      │   │   Agent      │   │   Agent      │                 │ │
│  │  │              │   │              │   │              │                 │ │
│  │  │ • Watch logs │   │ • Metrics    │   │ • Trend      │                 │ │
│  │  │ • Events     │   │ • Patterns   │   │   forecast   │                 │ │
│  │  │ • Anomalies  │   │ • Capacity   │   │ • Predict    │                 │ │
│  │  │              │   │              │   │   failures   │                 │ │
│  │  └──────┬───────┘   └──────┬───────┘   └──────┬───────┘                 │ │
│  │         │                  │                  │                          │ │
│  │         └──────────────────┼──────────────────┘                          │ │
│  │                            ▼                                             │ │
│  │                   ┌────────────────┐                                     │ │
│  │                   │  Event Stream  │ (Kafka/Redis Streams)               │ │
│  │                   └────────┬───────┘                                     │ │
│  └────────────────────────────┼─────────────────────────────────────────────┘ │
│                               │                                               │
│  ┌────────────────────────────▼─────────────────────────────────────────────┐ │
│  │                        REACTIVE AGENTS                                   │ │
│  │                    (Triggered by events)                                 │ │
│  │                                                                          │ │
│  │  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐                 │ │
│  │  │  Responder   │   │   Healer     │   │   Curator    │                 │ │
│  │  │   Swarm      │   │   Agent      │   │   Agent      │                 │ │
│  │  │              │   │              │   │              │                 │ │
│  │  │ • Investigate│   │ • Execute    │   │ • Learn      │                 │ │
│  │  │ • Diagnose   │   │   runbooks   │   │ • Document   │                 │ │
│  │  │ • Coordinate │   │ • Verify     │   │ • Teach      │                 │ │
│  │  │              │   │ • Rollback   │   │              │                 │ │
│  │  └──────────────┘   └──────────────┘   └──────────────┘                 │ │
│  │                                                                          │ │
│  └──────────────────────────────────────────────────────────────────────────┘ │
│                                                                               │
│  ┌──────────────────────────────────────────────────────────────────────────┐ │
│  │                        EXPLORER AGENT                                    │ │
│  │                    (Voyager-inspired curriculum)                         │ │
│  │                                                                          │ │
│  │  • Proposes exploration tasks based on knowledge gaps                    │ │
│  │  • Generates and validates new diagnostic skills                         │ │
│  │  • Compounds simple skills into complex runbooks                         │ │
│  │  • Self-verifies skill effectiveness                                     │ │
│  │                                                                          │ │
│  └──────────────────────────────────────────────────────────────────────────┘ │
│                                                                               │
│  ┌──────────────────────────────────────────────────────────────────────────┐ │
│  │                        SHARED SYSTEMS                                    │ │
│  │                                                                          │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │ │
│  │  │   Skill     │  │  Memory     │  │  Metrics    │  │  Discord    │     │ │
│  │  │   Library   │  │  Hierarchy  │  │  Store      │  │  Notifier   │     │ │
│  │  │  (Qdrant)   │  │ (Neo4j+PG)  │  │ (Prometheus)│  │             │     │ │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘     │ │
│  │                                                                          │ │
│  └──────────────────────────────────────────────────────────────────────────┘ │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Agent Specifications

### 1. Sentinel Agent (Continuous Watcher)

**Role:** Real-time event stream processing and anomaly detection

**Runs:** Continuously as a Temporal long-running workflow or standalone daemon

**Capabilities:**
- Subscribe to Kubernetes event stream (watch API)
- Subscribe to Loki log streams (via LogQL)
- Subscribe to Prometheus alertmanager
- Pattern matching for known issue signatures
- Anomaly detection for unknown patterns
- Emit classified events to event stream

**Tools:**
```python
@tool
def watch_kubernetes_events(namespace: str = None, resource_types: list[str] = None) -> AsyncIterator[Event]:
    """Stream Kubernetes events in real-time."""

@tool
def watch_logs(query: str, namespace: str = None) -> AsyncIterator[LogEntry]:
    """Stream logs matching LogQL query from Loki."""

@tool
def check_alert_status() -> list[Alert]:
    """Get active alerts from Prometheus Alertmanager."""

@tool
def classify_event(event: Event) -> Classification:
    """Classify event severity and type using skill library patterns."""
```

**Memory Integration:**
- Query skill library for known patterns
- Store new patterns for later analysis by Explorer

---

### 2. Analyst Agent (Metrics & Capacity)

**Role:** Continuous metrics analysis, trend detection, capacity planning

**Runs:** Periodically (every 5-15 minutes) or on-demand

**Capabilities:**
- Query Prometheus for resource utilization trends
- Detect capacity hotspots before they become problems
- Identify resource waste and optimization opportunities
- Correlate metrics with events for root cause

**Tools:**
```python
@tool
def query_prometheus(query: str, duration: str = "1h") -> MetricsResult:
    """Execute PromQL query and return time series data."""

@tool
def get_node_capacity() -> list[NodeCapacity]:
    """Get current and projected capacity for all nodes."""

@tool
def analyze_resource_trends(resource: str, namespace: str = None) -> TrendAnalysis:
    """Analyze resource usage trends and project future needs."""

@tool
def find_resource_anomalies(lookback: str = "24h") -> list[Anomaly]:
    """Detect unusual resource consumption patterns."""
```

---

### 3. Prophet Agent (Predictive)

**Role:** Failure prediction and proactive alerting

**Runs:** Periodically (every 30 minutes)

**Capabilities:**
- Time-series forecasting for resource exhaustion
- Pattern matching against historical failure signatures
- Proactive alerting before issues manifest
- Maintenance window recommendations

**Tools:**
```python
@tool
def forecast_resource_exhaustion(resource: str, threshold: float = 0.9) -> Forecast:
    """Predict when resource will exceed threshold."""

@tool
def match_failure_patterns(current_state: ClusterState) -> list[PatternMatch]:
    """Match current state against known pre-failure patterns."""

@tool
def recommend_maintenance(timeframe: str = "7d") -> list[Recommendation]:
    """Suggest proactive maintenance based on predictions."""
```

**Memory Integration:**
- Learn from historical incidents (what preceded failures?)
- Build predictive models from accumulated experience

---

### 4. Responder Swarm (Investigation)

**Role:** Coordinate multi-agent investigation of detected issues

**Runs:** Triggered by Sentinel or Prophet events

**Architecture:** Uses Strands Swarm pattern with specialized agents:

```python
from strands.multiagent import Swarm

responder_swarm = Swarm(
    agents=[
        network_investigator,    # Network/DNS issues
        storage_investigator,    # PVC/volume issues
        compute_investigator,    # CPU/memory/GPU issues
        application_investigator, # App-specific (OOM, crashes)
        dependency_investigator,  # External service issues
    ],
    entry_point=triage_agent,
    max_handoffs=10,
    execution_timeout=300.0,
)
```

**Swarm Agents:**

| Agent | Specialization | Key Tools |
|-------|----------------|-----------|
| Triage | Initial classification | events, pod_status, skill_search |
| Network | DNS, services, ingress | nslookup, curl, netstat |
| Storage | PVC, volumes, mounts | pvc_status, mount_check, df |
| Compute | CPU, memory, GPU | top, describe, resource_quota |
| Application | Logs, restarts, OOM | logs, previous_logs, events |
| Dependency | External services | curl, dns, certificate_check |

---

### 5. Healer Agent (Remediation)

**Role:** Execute remediation runbooks with verification

**Runs:** Triggered by Responder Swarm diagnosis

**Capabilities:**
- Retrieve applicable runbooks from skill library
- Execute with rollback capability
- Self-verify success using critic pattern
- Learn from execution outcomes

**Voyager-Inspired Execution Loop:**
```python
async def heal_issue(diagnosis: Diagnosis) -> HealingResult:
    # 1. Retrieve relevant skills
    skills = await skill_library.search(diagnosis.description, limit=5)

    # 2. Select best skill or compose new one
    if skills and skills[0].confidence > 0.8:
        runbook = skills[0]
    else:
        runbook = await generate_runbook(diagnosis, existing_skills=skills)

    # 3. Execute with verification loop (max 3 attempts)
    for attempt in range(3):
        result = await execute_runbook(runbook, diagnosis.context)

        # 4. Self-verify using critic
        verification = await critic.verify(
            goal=diagnosis.description,
            action=runbook.description,
            result=result,
            cluster_state=await get_current_state()
        )

        if verification.success:
            # 5. Commit skill improvement to library
            await skill_library.record_success(runbook, diagnosis, result)
            return HealingResult(success=True, runbook=runbook, attempts=attempt+1)

        # 6. Get feedback and refine
        runbook = await refine_runbook(runbook, verification.feedback)

    # 7. Escalate if all attempts fail
    return HealingResult(success=False, escalated=True, attempts=3)
```

**Expanded Remediation Actions:**
```python
SAFE_ACTIONS = {
    # Current capabilities
    "restart_pod": RestartPodAction,
    "scale_deployment": ScaleDeploymentAction,

    # New capabilities with guards
    "drain_node": DrainNodeAction,           # Requires approval for production
    "apply_resource_limits": ResourceLimitAction,
    "restart_deployment": RestartDeploymentAction,
    "rollback_deployment": RollbackDeploymentAction,
    "cordon_node": CordonNodeAction,
    "delete_stuck_pod": DeletePodAction,     # Only for Evicted/Unknown states
    "clear_pvc": ClearPVCAction,             # Only for specific patterns
}

REQUIRES_APPROVAL = {"drain_node", "rollback_deployment"}
```

---

### 6. Curator Agent (Learning)

**Role:** Organize knowledge, create documentation, teach patterns

**Runs:** Periodically (daily) and after significant incidents

**Capabilities:**
- Analyze incident patterns across time
- Generate runbook documentation from successful remediations
- Identify knowledge gaps for Explorer
- Update skill library metadata and relationships
- Generate reports and dashboards

**Tools:**
```python
@tool
def analyze_incident_patterns(timeframe: str = "30d") -> PatternReport:
    """Identify recurring patterns and successful resolutions."""

@tool
def generate_runbook_documentation(skill_id: str) -> MarkdownDoc:
    """Create human-readable documentation for a skill."""

@tool
def identify_knowledge_gaps() -> list[KnowledgeGap]:
    """Find areas where we lack diagnostic or remediation skills."""

@tool
def update_skill_relationships(skill_id: str, relationships: dict):
    """Update skill composition and dependency graph."""
```

---

### 7. Explorer Agent (Voyager-Inspired Curriculum)

**Role:** Proactively expand system knowledge and capabilities

**Runs:** During low-activity periods or on-demand

**Automatic Curriculum Algorithm:**
```python
async def generate_exploration_task() -> ExplorationTask:
    # 1. Get current capability inventory
    skills = await skill_library.list_all()
    skill_coverage = analyze_coverage(skills)

    # 2. Get cluster state for context
    cluster_state = await get_cluster_state()
    namespaces = cluster_state.namespaces
    workload_types = cluster_state.workload_types

    # 3. Identify exploration opportunities
    gaps = await curator.identify_knowledge_gaps()

    # 4. Use LLM to propose contextually appropriate task
    prompt = f"""
    You are a Kubernetes operations expert exploring a cluster to build knowledge.

    Current skill coverage:
    {skill_coverage}

    Knowledge gaps identified:
    {gaps}

    Cluster context:
    - Namespaces: {namespaces}
    - Workload types: {workload_types}

    Propose ONE specific exploration task that would:
    1. Fill an identified knowledge gap
    2. Build on existing skills (compositionality)
    3. Be safely executable without causing issues

    Format: {{"task": "...", "rationale": "...", "builds_on": ["skill1", "skill2"]}}
    """

    return await llm.generate(prompt)
```

**Exploration Examples:**
- "Investigate how cert-manager renewals work to build certificate expiry prediction skill"
- "Analyze Flux reconciliation patterns to build GitOps health monitoring skill"
- "Explore GPU scheduling behavior to build GPU workload optimization skill"
- "Test node drain procedure in staging to verify drain_node runbook"

**Skill Generation & Verification:**
```python
async def explore_and_learn(task: ExplorationTask) -> Skill:
    # 1. Execute exploration
    observations = await execute_exploration(task)

    # 2. Generate candidate skill
    skill_code = await generate_skill_code(task, observations)

    # 3. Verify in safe context
    verification = await verify_skill(skill_code, task)

    if verification.success:
        # 4. Add to skill library with embeddings
        skill = Skill(
            name=task.name,
            code=skill_code,
            description=task.rationale,
            preconditions=verification.preconditions,
            success_criteria=verification.success_criteria,
            builds_on=task.builds_on,
        )
        await skill_library.add(skill)
        return skill
    else:
        # 5. Store as partial knowledge for future refinement
        await memory.store_exploration_attempt(task, observations, verification.feedback)
        return None
```

---

## Skill Library System

### Architecture

Inspired by Voyager's skill library, but adapted for Kubernetes operations:

```
┌─────────────────────────────────────────────────────────────────┐
│                       SKILL LIBRARY                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    VECTOR STORE (Qdrant)                  │   │
│  │                                                           │   │
│  │  Each skill indexed by embedding of:                      │   │
│  │  • Description (what it does)                             │   │
│  │  • Preconditions (when to use)                            │   │
│  │  • Success criteria (how to verify)                       │   │
│  │                                                           │   │
│  │  Enables semantic retrieval:                              │   │
│  │  "pod stuck in ImagePullBackOff" → restart_with_new_image │   │
│  │                                                           │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    GRAPH STORE (Neo4j)                    │   │
│  │                                                           │   │
│  │  Skill relationships:                                     │   │
│  │  ┌─────────────┐     ┌─────────────┐                     │   │
│  │  │drain_node   │────▶│cordon_node  │                     │   │
│  │  │safely       │     └─────────────┘                     │   │
│  │  │             │────▶┌─────────────┐                     │   │
│  │  └─────────────┘     │evict_pods   │                     │   │
│  │                      └─────────────┘                     │   │
│  │                                                           │   │
│  │  Enables:                                                 │   │
│  │  • Skill composition discovery                            │   │
│  │  • Prerequisite validation                                │   │
│  │  • Learning path generation                               │   │
│  │                                                           │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    CODE STORE (Git/DB)                    │   │
│  │                                                           │   │
│  │  Executable skill implementations:                        │   │
│  │                                                           │   │
│  │  @skill(                                                  │   │
│  │      name="restart_crashlooping_pod",                     │   │
│  │      preconditions=["pod.status == CrashLoopBackOff"],    │   │
│  │      success_criteria=["pod.status == Running",           │   │
│  │                        "pod.restarts < previous + 1"]     │   │
│  │  )                                                        │   │
│  │  async def restart_crashlooping_pod(pod: Pod) -> Result:  │   │
│  │      await kubectl.delete_pod(pod.name, pod.namespace)    │   │
│  │      await wait_for_ready(pod.name, pod.namespace)        │   │
│  │      return verify_health(pod)                            │   │
│  │                                                           │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Skill Schema

```python
from pydantic import BaseModel
from typing import Optional

class Skill(BaseModel):
    id: str
    name: str
    description: str
    category: SkillCategory  # diagnostic, remediation, optimization, monitoring

    # Semantic search fields
    preconditions: list[str]      # When this skill applies
    success_criteria: list[str]   # How to verify it worked

    # Executable code
    code: str                     # Python function body
    tools_required: list[str]     # kubectl, prometheus, etc.

    # Composition
    builds_on: list[str]          # Prerequisite skill IDs
    composed_of: list[str]        # Sub-skill IDs (for complex skills)

    # Learning metadata
    created_by: str               # "explorer", "curator", "human"
    success_count: int            # Times successfully used
    failure_count: int            # Times failed
    last_used: datetime
    confidence: float             # Calculated from success/failure ratio

    # Safety
    requires_approval: bool       # Needs human confirmation
    reversible: bool              # Can be rolled back
    rollback_skill_id: Optional[str]  # How to undo
```

### Skill Categories

| Category | Purpose | Examples |
|----------|---------|----------|
| **Diagnostic** | Investigate and understand issues | `analyze_oom_kill`, `trace_network_path`, `decode_crash_logs` |
| **Remediation** | Fix known issues | `restart_pod`, `scale_deployment`, `drain_node` |
| **Optimization** | Improve performance/efficiency | `right_size_resources`, `optimize_hpa_settings` |
| **Monitoring** | Continuous observation | `watch_certificate_expiry`, `track_deployment_frequency` |
| **Prediction** | Forecast issues | `predict_disk_exhaustion`, `forecast_scaling_needs` |

### Skill Retrieval

```python
async def find_relevant_skills(issue: Issue, limit: int = 5) -> list[Skill]:
    # 1. Generate search embedding
    search_text = f"{issue.type}: {issue.description}. Context: {issue.context}"
    embedding = await embeddings.encode(search_text)

    # 2. Vector search in Qdrant
    candidates = await qdrant.search(
        collection="skills",
        vector=embedding,
        limit=limit * 2,  # Get extra for filtering
    )

    # 3. Filter by preconditions
    applicable = []
    for skill in candidates:
        if await check_preconditions(skill.preconditions, issue):
            applicable.append(skill)

    # 4. Rank by confidence and recency
    ranked = sorted(
        applicable,
        key=lambda s: (s.confidence, -s.failure_count, s.last_used),
        reverse=True
    )

    return ranked[:limit]
```

---

## Continuous Learning Loop

### The Voyager-Inspired Learning Cycle

```
┌─────────────────────────────────────────────────────────────────┐
│                    CONTINUOUS LEARNING LOOP                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│         ┌──────────────┐                                        │
│         │   OBSERVE    │◀──────────────────────────────┐        │
│         │              │                               │        │
│         │ • Events     │                               │        │
│         │ • Metrics    │                               │        │
│         │ • Logs       │                               │        │
│         └──────┬───────┘                               │        │
│                │                                       │        │
│                ▼                                       │        │
│         ┌──────────────┐                               │        │
│         │    MATCH     │                               │        │
│         │              │                               │        │
│         │ Search skill │──────┐                        │        │
│         │ library for  │      │                        │        │
│         │ known pattern│      │ No match               │        │
│         └──────┬───────┘      │                        │        │
│                │              │                        │        │
│                │ Match found  │                        │        │
│                ▼              ▼                        │        │
│         ┌──────────────┐  ┌──────────────┐            │        │
│         │   EXECUTE    │  │   EXPLORE    │            │        │
│         │              │  │              │            │        │
│         │ Run matched  │  │ Generate new │            │        │
│         │ skill/runbook│  │ skill/pattern│            │        │
│         └──────┬───────┘  └──────┬───────┘            │        │
│                │                 │                     │        │
│                └────────┬────────┘                     │        │
│                         ▼                              │        │
│                  ┌──────────────┐                      │        │
│                  │    VERIFY    │                      │        │
│                  │              │                      │        │
│                  │ Use critic   │                      │        │
│                  │ to check     │                      │        │
│                  │ success      │                      │        │
│                  └──────┬───────┘                      │        │
│                         │                              │        │
│           ┌─────────────┴─────────────┐                │        │
│           ▼                           ▼                │        │
│    ┌──────────────┐           ┌──────────────┐        │        │
│    │   SUCCESS    │           │   FAILURE    │        │        │
│    │              │           │              │        │        │
│    │ • Increment  │           │ • Get critic │        │        │
│    │   confidence │           │   feedback   │        │        │
│    │ • Store in   │           │ • Refine and │────────┘        │
│    │   memory     │           │   retry OR   │                 │
│    │              │           │ • Escalate   │                 │
│    └──────┬───────┘           └──────────────┘                 │
│           │                                                     │
│           ▼                                                     │
│    ┌──────────────┐                                            │
│    │    LEARN     │                                            │
│    │              │                                            │
│    │ • Update     │                                            │
│    │   skill stats│                                            │
│    │ • Record     │                                            │
│    │   context    │                                            │
│    │ • Find       │                                            │
│    │   patterns   │────────────────────────────────────────────┘
│    │              │         (Loop continues)
│    └──────────────┘
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Self-Verification (Critic Pattern)

```python
class SkillCritic:
    """Voyager-inspired critic for skill verification."""

    async def verify(
        self,
        goal: str,
        skill: Skill,
        result: ExecutionResult,
        before_state: ClusterState,
        after_state: ClusterState,
    ) -> Verification:
        prompt = f"""
        You are a Kubernetes operations critic evaluating if an action achieved its goal.

        GOAL: {goal}

        ACTION TAKEN: {skill.description}

        EXPECTED SUCCESS CRITERIA:
        {skill.success_criteria}

        BEFORE STATE:
        {before_state.summary()}

        AFTER STATE:
        {after_state.summary()}

        EXECUTION RESULT:
        {result}

        Evaluate:
        1. Did the action achieve the goal? (yes/no)
        2. Were all success criteria met? List each with yes/no.
        3. Any unexpected side effects?
        4. If not successful, what specific feedback would help improve the skill?

        Response format:
        {{
            "success": true/false,
            "criteria_met": {{"criterion1": true, "criterion2": false}},
            "side_effects": ["effect1", "effect2"],
            "feedback": "Specific improvement suggestions..."
        }}
        """

        return await self.llm.generate(prompt, response_model=Verification)
```

---

## Memory Architecture

### Hierarchical Memory System

Moving beyond flat mem0 storage to a structured hierarchy:

```
┌─────────────────────────────────────────────────────────────────┐
│                    MEMORY HIERARCHY                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                EPISODIC MEMORY (Short-term)               │   │
│  │                     PostgreSQL + pgvector                 │   │
│  │                                                           │   │
│  │  • Individual incidents with full context                 │   │
│  │  • Recent events (last 30 days detailed)                  │   │
│  │  • Searchable by semantic similarity                      │   │
│  │                                                           │   │
│  │  Schema: incident_id, timestamp, description, context,    │   │
│  │          resolution, success, embedding                   │   │
│  │                                                           │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              │ Consolidation (daily)             │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                SEMANTIC MEMORY (Long-term)                │   │
│  │                          Neo4j                            │   │
│  │                                                           │   │
│  │  • Generalized patterns extracted from episodes           │   │
│  │  • Cause-effect relationships                             │   │
│  │  • Skill effectiveness statistics                         │   │
│  │                                                           │   │
│  │  Nodes: Pattern, Skill, Resource, Symptom, RootCause      │   │
│  │  Edges: CAUSES, RESOLVES, INDICATES, PRECEDES             │   │
│  │                                                           │   │
│  │  Example:                                                 │   │
│  │  (OOMKilled)-[:INDICATES]->(MemoryLeak)                   │   │
│  │  (MemoryLeak)-[:RESOLVES {confidence: 0.85}]->(RestartPod)│   │
│  │                                                           │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              │ Abstraction                       │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │               PROCEDURAL MEMORY (Skills)                  │   │
│  │                     Qdrant + Git                          │   │
│  │                                                           │   │
│  │  • Executable runbooks                                    │   │
│  │  • Diagnostic procedures                                  │   │
│  │  • Optimization playbooks                                 │   │
│  │                                                           │   │
│  │  See: Skill Library System                                │   │
│  │                                                           │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Memory Consolidation Process

```python
class MemoryConsolidator:
    """Voyager-inspired memory consolidation from episodes to patterns."""

    async def consolidate_daily(self):
        # 1. Fetch recent episodes
        episodes = await self.episodic.get_recent(days=7)

        # 2. Cluster similar episodes
        clusters = await self.cluster_episodes(episodes)

        # 3. For each cluster, extract or update pattern
        for cluster in clusters:
            if len(cluster.episodes) >= 3:  # Threshold for pattern
                pattern = await self.extract_pattern(cluster)

                existing = await self.semantic.find_similar_pattern(pattern)
                if existing:
                    await self.semantic.update_pattern(existing, cluster)
                else:
                    await self.semantic.create_pattern(pattern)

        # 4. Update skill confidence based on recent usage
        await self.update_skill_statistics()

        # 5. Archive old episodes (keep summary only)
        await self.episodic.archive_old(days=30)

    async def extract_pattern(self, cluster: EpisodeCluster) -> Pattern:
        prompt = f"""
        Analyze these similar Kubernetes incidents and extract a general pattern.

        Incidents:
        {[e.summary() for e in cluster.episodes]}

        Extract:
        1. Common symptoms (what was observed)
        2. Common root causes (why it happened)
        3. Effective resolutions (what fixed it)
        4. Predictive signals (what preceded it)

        Return as structured pattern.
        """
        return await self.llm.generate(prompt, response_model=Pattern)
```

---

## Implementation Phases

### Phase 1: Foundation (2-3 weeks)

**Objective:** Establish event-driven architecture and skill library foundation

**Tasks:**
1. Deploy Redis Streams or Kafka for event bus
2. Create Qdrant collection for skill library
3. Extend Neo4j schema for semantic memory
4. Implement base Skill model and repository
5. Create skill library API (add, search, update)
6. Migrate existing remediation actions to skills
7. Build skill verification framework

**Deliverables:**
- Event bus deployed and integrated
- Skill library with 10+ initial skills
- Skill CRUD API
- Basic verification tests

### Phase 2: Sentinel Agent (1-2 weeks)

**Objective:** Real-time event processing and classification

**Tasks:**
1. Implement Kubernetes watch stream consumer
2. Implement Loki log stream consumer
3. Build event classification using skill library
4. Create event emission to central bus
5. Discord integration for significant events
6. Unit and integration tests

**Deliverables:**
- Sentinel agent deployed as continuous worker
- Events flowing to central bus
- Classification accuracy > 80% on known patterns

### Phase 3: Enhanced Responder Swarm (2 weeks)

**Objective:** Improved investigation with skill-based approach

**Tasks:**
1. Refactor existing swarm agents to use skill library
2. Add new specialist agents (network, storage, dependency)
3. Implement skill retrieval in investigation flow
4. Add skill composition for complex investigations
5. Integrate with event bus for triggers

**Deliverables:**
- 6+ specialist investigation agents
- Skill-driven investigation flow
- Event-triggered responses

### Phase 4: Healer with Verification (2 weeks)

**Objective:** Self-verifying remediation with expanded capabilities

**Tasks:**
1. Implement Voyager-style verification loop
2. Add Critic for success verification
3. Expand remediation actions (drain, rollback, etc.)
4. Implement rollback mechanism for reversible actions
5. Add approval workflow for dangerous actions
6. Skill confidence updates based on outcomes

**Deliverables:**
- Self-verifying remediation loop
- 15+ remediation skills
- Rollback capability for reversible actions
- Approval workflow for high-risk actions

### Phase 5: Learning Agents (2-3 weeks)

**Objective:** Curator and Explorer for continuous improvement

**Tasks:**
1. Implement memory consolidation pipeline
2. Build Curator agent for pattern extraction
3. Implement Explorer curriculum generation
4. Add skill generation from exploration
5. Documentation generation from skills
6. Knowledge gap identification

**Deliverables:**
- Daily memory consolidation running
- Explorer proposing 2-3 exploration tasks/week
- Automatic runbook documentation

### Phase 6: Predictive Capabilities (2 weeks)

**Objective:** Analyst and Prophet for proactive monitoring

**Tasks:**
1. Implement Prometheus query tools
2. Build trend analysis capabilities
3. Add time-series forecasting
4. Implement pre-failure pattern matching
5. Proactive alerting integration
6. Capacity planning recommendations

**Deliverables:**
- Resource exhaustion predictions
- Proactive alerts before failures
- Weekly capacity reports

### Phase 7: Integration & Polish (1-2 weeks)

**Objective:** Full system integration and hardening

**Tasks:**
1. End-to-end integration testing
2. Performance optimization
3. Observability (metrics, traces, logs)
4. Dashboard creation (Grafana)
5. Documentation and runbook finalization
6. Chaos testing for resilience

**Deliverables:**
- Production-ready multi-agent system
- Comprehensive observability
- Operational documentation

---

## Infrastructure Requirements

### Current Services (Already Deployed)

| Service | Namespace | Purpose | Notes |
|---------|-----------|---------|-------|
| PostgreSQL | database | Episodic memory, mem0 | Already configured with pgvector |
| Qdrant | database | Skill embeddings | Already deployed |
| Neo4j | database | Semantic graph | Already deployed |
| Redis | cache | Event bus, caching | Already deployed |
| vLLM | vllm | LLM inference | Qwen3-14B |
| Embeddings | ai-agents | Vector embeddings | Qwen3-Embedding-0.6B |
| Prometheus | monitoring | Metrics storage | Full stack with Grafana |
| Loki | monitoring | Log aggregation | With Promtail |
| Temporal | temporal | Workflow orchestration | Already hosting workers |
| kubernetes-mcp-server | ai-agents | K8s operations | MCP protocol |

### New Services Needed

| Service | Purpose | Estimated Resources |
|---------|---------|---------------------|
| Event Bus (Redis Streams) | Agent communication | Uses existing Redis |
| Skill Library API | Skill CRUD operations | Part of k8s-monitor |
| Memory Consolidation Worker | Daily consolidation | Temporal workflow |

### Resource Estimates

Current k8s-monitor pod resources:
```yaml
resources:
  requests:
    memory: "512Mi"
    cpu: "250m"
  limits:
    memory: "1Gi"
    cpu: "1000m"
```

Proposed resources for multi-agent system:
```yaml
# Continuous agents (Sentinel, Analyst)
resources:
  requests:
    memory: "1Gi"
    cpu: "500m"
  limits:
    memory: "2Gi"
    cpu: "2000m"

# Reactive agents (Responder, Healer)
# Scales with activity, can use HPA
resources:
  requests:
    memory: "512Mi"
    cpu: "250m"
  limits:
    memory: "2Gi"
    cpu: "2000m"
```

---

## Success Metrics

### Quantitative Metrics

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| **Mean Time to Detection (MTTD)** | ~1 hour | < 5 minutes | Event → Alert latency |
| **Mean Time to Resolution (MTTR)** | Manual | < 15 minutes | Event → Remediated |
| **Auto-remediation Rate** | ~20% | > 60% | Issues fixed without human |
| **False Positive Rate** | Unknown | < 10% | Alerts that weren't issues |
| **Skill Library Size** | 6 | > 50 | Active, verified skills |
| **Prediction Accuracy** | N/A | > 70% | Predicted failures that occurred |
| **Learning Rate** | N/A | 2/week | New skills generated |

### Qualitative Metrics

1. **Reduction in on-call burden** - Fewer pages requiring human intervention
2. **Improved documentation** - Auto-generated runbooks match/exceed manual
3. **Knowledge retention** - New team members can query skill library
4. **Proactive insights** - Recommendations acted upon before issues

### Observability

```yaml
# Prometheus metrics to expose
metrics:
  - name: k8s_monitor_events_processed_total
    type: counter
    labels: [agent, event_type, outcome]

  - name: k8s_monitor_skill_executions_total
    type: counter
    labels: [skill_name, outcome]

  - name: k8s_monitor_remediation_duration_seconds
    type: histogram
    labels: [skill_name]

  - name: k8s_monitor_skill_confidence
    type: gauge
    labels: [skill_name]

  - name: k8s_monitor_prediction_accuracy
    type: gauge
    labels: [prediction_type]

  - name: k8s_monitor_memory_consolidations_total
    type: counter
    labels: [outcome]
```

---

## Open Questions & Discussion Points

1. **Model Specialization**: Should different agents use different models? (e.g., smaller model for Sentinel, larger for Healer)

2. **Approval Workflow**: How should we handle approval for dangerous actions? Slack? Discord? Email?

3. **Skill Library Versioning**: How do we handle skill updates without breaking existing workflows?

4. **Multi-Cluster**: Should this system be cluster-aware or cluster-specific?

5. **Cost Considerations**: vLLM token usage will increase significantly. How do we optimize?

6. **Safety Boundaries**: What actions should NEVER be automated? (e.g., namespace deletion)

7. **Human Feedback Loop**: How do operators validate/correct agent decisions?

8. **Chaos Testing**: Should Explorer be allowed to inject controlled failures for learning?

---

## References

### Research Papers
- [Voyager: An Open-Ended Embodied Agent with Large Language Models](https://arxiv.org/abs/2305.16291)
- [ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629)

### Documentation
- [Strands Agents SDK Documentation](https://strandsagents.com/latest/)
- [Strands Multi-Agent Patterns](https://strandsagents.com/latest/documentation/docs/user-guide/concepts/multi-agent/multi-agent-patterns/)
- [Strands Swarm Pattern](https://strandsagents.com/latest/documentation/docs/user-guide/concepts/multi-agent/swarm/)
- [MineDojo/Voyager GitHub](https://github.com/MineDojo/Voyager)

### Related Projects
- [mem0 Documentation](https://docs.mem0.ai/)
- [Temporal Workflows](https://docs.temporal.io/)
- [Model Context Protocol](https://modelcontextprotocol.io/)

---

## Next Steps

1. Review this document and provide feedback on priorities
2. Decide on Phase 1 scope and timeline
3. Create detailed implementation tasks in GitHub Issues
4. Set up observability baseline for before/after comparison
5. Begin Phase 1 implementation
