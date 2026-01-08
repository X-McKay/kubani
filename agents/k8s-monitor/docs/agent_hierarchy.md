# K8s-Monitor Agent Hierarchy Design

## Overview

This document describes the hierarchical agent architecture for k8s-monitor, implementing a clear chain of responsibility for Kubernetes cluster monitoring and remediation.

## Agent Hierarchy

```
                    ┌─────────────────┐
                    │  K8sCoordinator │
                    │  (Entry Point)  │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
       ┌──────────┐   ┌──────────┐   ┌──────────────┐
       │  Triage  │   │  Scout   │   │DiscordNotify │
       │  Agent   │   │  Agent   │   │    Agent     │
       └────┬─────┘   └──────────┘   └──────────────┘
            │
            ▼
     ┌──────────────┐
     │  Diagnosis   │
     │   Router     │
     └──────┬───────┘
            │
    ┌───────┼───────┬────────┐
    │       │       │        │
    ▼       ▼       ▼        ▼
┌───────┐┌──────┐┌───────┐┌─────────┐
│  Pod  ││ Node ││Network││ Storage │
│ Diag  ││ Diag ││ Diag  ││  Diag   │
└───┬───┘└──────┘└───────┘└─────────┘
    │
    ▼
┌──────────────┐     ┌──────────────┐
│ Remediation  │────▶│   Memory     │
│    Agent     │     │    Agent     │
└──────────────┘     └──────────────┘
```

## Agent Responsibilities

### Tier 1: Coordination

#### K8sCoordinatorAgent
- **Purpose**: Top-level orchestrator for all k8s monitoring tasks
- **Responsibilities**:
  - Receive incoming requests (health checks, issue investigations)
  - Route to appropriate tier-2 agent based on request type
  - Aggregate results from sub-agents
  - Handle escalation decisions
- **Handoffs**:
  - Health check request → Scout
  - Specific issue → Triage
  - Final notification → DiscordNotifier

### Tier 2: Assessment

#### TriageAgent
- **Purpose**: Initial assessment and severity determination
- **Responsibilities**:
  - Gather context from cluster (quick status check)
  - Search memories for similar past issues
  - Determine severity (critical/warning/info)
  - Determine urgency (immediate/soon/scheduled)
  - Route to appropriate diagnosis agent
- **Handoffs**:
  - Pod-related → PodDiagnostician
  - Node-related → NodeDiagnostician
  - Network-related → NetworkDiagnostician
  - Storage-related → StorageDiagnostician

#### ScoutAgent
- **Purpose**: Cluster-wide health scanning (existing ClusterScout)
- **Responsibilities**:
  - Rapid cluster health assessment
  - Node status, deployment health, storage, resources
  - Severity determination
- **Handoffs**:
  - Issues found → Triage (with context)
  - All healthy → DiscordNotifier

### Tier 3: Diagnosis

#### DiagnosisRouter
- **Purpose**: Routes to specialized diagnosticians based on issue type
- **Sub-agents**:

##### PodDiagnostician
- **Purpose**: Deep pod/container investigation
- **Focus**: Logs, events, specs, restart reasons
- **Handoffs**: → Remediation or escalate

##### NodeDiagnostician (NEW)
- **Purpose**: Node-level problem diagnosis
- **Focus**: Node conditions, taints, resources, kubelet status
- **Handoffs**: → Remediation (if drain/cordon needed) or escalate

##### NetworkDiagnostician (NEW)
- **Purpose**: Connectivity and service mesh issues
- **Focus**: Service endpoints, ingress, DNS, network policies
- **Handoffs**: → Remediation or escalate

##### StorageDiagnostician (NEW)
- **Purpose**: Storage and volume issues
- **Focus**: PVC status, CSI driver issues, capacity
- **Handoffs**: → Remediation or escalate

### Tier 4: Action

#### RemediationAgent
- **Purpose**: Execute safe, reversible fixes
- **Safe Operations**:
  - Pod restart (delete to trigger recreation)
  - Scale deployments (within limits)
  - Cordon/uncordon nodes (manual only)
- **Unsafe Operations** (require approval):
  - Node drain
  - Deployment rollback
  - Resource limit changes
- **Handoffs**: → Memory (record outcome), DiscordNotifier

#### MemoryAgent
- **Purpose**: Institutional memory and pattern detection
- **Responsibilities**:
  - Store remediation outcomes
  - Detect recurring issues
  - Suggest permanent fixes
- **Handoffs**: → DiscordNotifier (if escalation needed)

### Tier 5: Communication

#### DiscordNotifierAgent
- **Purpose**: Human-facing notifications (terminal agent)
- **Responsibilities**:
  - Transform technical findings into clear notifications
  - Format for Discord embeds
  - NO further handoffs

## Handoff Protocol

### Context Object

All handoffs pass a structured context object:

```python
@dataclass
class HandoffContext:
    """Context passed between agents in the hierarchy."""

    # Original request
    request_id: str
    request_type: str  # "health_check", "issue_investigation"
    original_prompt: str

    # Resource identification
    resource_type: str | None = None  # Pod, Node, Deployment, etc.
    resource_name: str | None = None
    namespace: str | None = None

    # Assessment
    severity: str | None = None  # critical, warning, info
    urgency: str | None = None  # immediate, soon, scheduled

    # Findings (accumulated)
    findings: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    # Remediation
    proposed_fix: str | None = None
    fix_applied: bool = False
    fix_outcome: str | None = None

    # Memory
    similar_issues: list[str] = field(default_factory=list)
    recurrence_count: int = 0
```

### Handoff Rules

1. **Always pass context**: Every handoff includes the accumulated context
2. **Enrich, don't replace**: Each agent adds to findings/evidence
3. **Clear routing**: Each agent knows exactly where to route based on issue type
4. **No loops**: Handoffs flow downward (with exceptions for Memory)
5. **Terminal agent**: DiscordNotifier never hands off

## Metrics

Each agent exposes Prometheus metrics:

- `agent_requests_total{agent="pod_diagnostician"}` - Request count
- `agent_duration_seconds{agent="pod_diagnostician"}` - Processing time
- `agent_handoffs_total{from="triage", to="pod_diagnostician"}` - Handoff count
- `agent_errors_total{agent="pod_diagnostician"}` - Error count

## Migration Plan

1. Add `HandoffContext` dataclass
2. Create base `DiagnosisAgent` class with shared logic
3. Implement `NodeDiagnostician`
4. Implement `NetworkDiagnostician`
5. Implement `StorageDiagnostician`
6. Update existing agents to use `HandoffContext`
7. Create `K8sCoordinatorAgent` as new entry point
8. Update swarm configuration

## Testing Strategy

1. **Unit tests**: Each agent in isolation with mocked tools
2. **Handoff tests**: Verify context passing between agents
3. **Integration tests**: Full swarm execution with test scenarios
4. **Prompt tests**: Verify agents make correct routing decisions
