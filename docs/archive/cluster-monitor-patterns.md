# Cluster-Monitor Patterns for Consolidation

> **Purpose:** Reference documentation for patterns from cluster-monitor (v0.2.4) that are being consolidated into k8s-monitor (v0.4.0).

---

## 8-Stage Investigation Pipeline

The orchestrator in `agents/cluster-monitor/src/cluster_monitor/orchestrator.py` implements a sophisticated 8-stage pipeline:

### Stages

| Stage | Purpose | Key Actions |
|-------|---------|-------------|
| **ANALYZING** | Initial event classification | Post initial message, identify pattern |
| **QUERYING_MEMORY** | Check historical patterns | Search Qdrant for similar incidents |
| **INVESTIGATING** | Run diagnostic skills | Execute investigation workers |
| **PLANNING_REMEDIATION** | Determine action | Check memory for known fixes |
| **EXECUTING_ACTION** | Run remediation | Delegate to remediator worker |
| **VERIFYING** | Check success | Verify resolution via investigator |
| **SUMMARIZING** | Generate narrative | Post summary, store learnings |
| **COMPLETED/FAILED** | Terminal states | Final outcome |

### State Machine

```python
class InvestigationStage(str, Enum):
    CORRELATING = "correlating"
    ANALYZING = "analyzing"
    QUERYING_MEMORY = "querying_memory"
    INVESTIGATING = "investigating"
    PLANNING_REMEDIATION = "planning_remediation"
    EXECUTING_ACTION = "executing_action"
    VERIFYING = "verifying"
    SUMMARIZING = "summarizing"
    COMPLETED = "completed"
    FAILED = "failed"
```

---

## Event Correlation

The correlator in `agents/cluster-monitor/src/cluster_monitor/correlator.py`:

### Configuration

- **Correlation window:** 30 seconds (configurable via `CORRELATION_WINDOW_SECONDS`)
- **Critical immediate reasons:** OOMKilled, NodeNotReady, EvictionThresholdMet (bypass correlation)
- **Ignored resources:** cluster-monitor, cluster-swarm (prevent loops)

### Correlation Key Generation

Events are grouped by:
1. **Error pattern** (timeout, connection_error, oom, storage, image_pull, other)
2. **Namespace**

```python
def _generate_correlation_key(self, event: K8sEvent) -> str:
    pattern = self._extract_error_pattern(event.message)
    return f"{pattern}:{event.namespace}"
```

### Error Pattern Extraction

| Pattern | Keywords |
|---------|----------|
| `timeout` | timeout, deadline exceeded, timed out |
| `connection_error` | connection refused, connection reset, no route to host |
| `oom` | oom, out of memory |
| `storage` | disk, storage |
| `image_pull` | image + pull/not found |
| `other` | Default |

---

## Key Models

From `agents/cluster-monitor/src/cluster_monitor/models.py`:

### K8sEvent

```python
class K8sEvent(BaseModel):
    event_id: str
    event_type: str  # "Warning", "Error", "Normal"
    reason: str
    message: str
    namespace: str
    resource_name: str
    resource_kind: str
    severity: Severity
    timestamp: str
    count: int = 1
```

### InvestigationState

```python
class InvestigationState(BaseModel):
    investigation_id: str
    correlation_id: str
    stage: InvestigationStage
    discord_thread_id: str | None = None
    events: list[K8sEvent] = Field(default_factory=list)
    findings: dict[str, Any] = Field(default_factory=dict)
    actions_taken: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str
    updated_at: str

    def update_stage(self, new_stage: InvestigationStage) -> None:
        self.stage = new_stage
        self.updated_at = datetime.now(UTC).isoformat()
```

### CorrelatedIssue

```python
class CorrelatedIssue(BaseModel):
    correlation_id: str
    events: list[K8sEvent]
    pattern_type: str  # "timeout", "crash_loop", etc.
    affected_namespaces: list[str]
    affected_resources: list[str]
    severity: Severity
    created_at: str
```

### WorkerTask/WorkerResult

```python
class WorkerTask(BaseModel):
    task_id: str
    task_type: str  # "investigate", "query_memory", "remediate", "narrate"
    context: dict[str, Any]
    created_at: str

class WorkerResult(BaseModel):
    task_id: str
    success: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    completed_at: str
```

---

## Orchestrator → Worker Delegation

The orchestrator delegates to specialized workers:

| Worker | Task Types | Purpose |
|--------|------------|---------|
| **InvestigatorWorker** | investigate | Run diagnostic skills |
| **MemoryWorker** | query_memory, store_learning | Qdrant interactions |
| **RemediatorWorker** | plan_remediation, execute_remediation | Fix issues |
| **NarratorWorker** | narrate, verify | Discord updates, verification |

---

## Integration Points in k8s-monitor

### Existing Architecture

k8s-monitor has:
- **Sentinel:** Watches events, classifies with patterns + LLM
- **Healer:** Agentic remediation with MCP tools
- **Explorer:** Skill learning

### Consolidation Mapping

| cluster-monitor | → k8s-monitor |
|-----------------|---------------|
| EventCorrelator | Sentinel (enhance with correlation) |
| InvestigationOrchestrator | Temporal workflow (RemediationOrchestrationWorkflow) |
| Workers (Investigator, Memory, etc.) | Temporal activities |
| Redis state persistence | Temporal workflow state (durable) |

### Key Differences

1. **cluster-monitor** uses direct asyncio + Redis for orchestration
2. **k8s-monitor** uses Temporal workflows for durability
3. **cluster-monitor** has explicit worker classes
4. **k8s-monitor** uses MCP tools in agentic Healer

### What to Preserve

1. [OK] 8-stage investigation pipeline → Temporal workflow
2. [OK] 30-second correlation window → EventCorrelator class
3. [OK] InvestigationState model → Add to k8s-monitor models
4. [OK] Error pattern extraction → Integrate into Sentinel
5. [OK] Discord thread-based updates → Temporal activities

---

## Migration Notes

### Phase 1: Add Models
- Add InvestigationStage, InvestigationState, CorrelatedIssue to k8s-monitor/models.py

### Phase 2: Add Correlation
- Add EventCorrelator to Sentinel
- Use same correlation key generation

### Phase 3: Add Workflow
- Create RemediationOrchestrationWorkflow
- Convert worker delegation to activities

### Phase 4: Shadow Mode
- Run both agents in shadow mode
- Compare decisions
- Validate equivalence

### Phase 5: Cutover
- Disable cluster-monitor
- k8s-monitor handles all events
