# Cluster Monitor vs Cluster Swarm - Implementation Comparison

This document provides a side-by-side comparison of the two experimental Kubernetes monitoring agents implemented for evaluation.

## Quick Reference

| Aspect | cluster-monitor | cluster-swarm |
|--------|----------------|---------------|
| **Architecture** | Orchestrator-Worker | Swarm Intelligence |
| **Approach** | Structured delegation | Collaborative agents |
| **Entry Point** | Orchestrator | Triage Agent |
| **Workflow** | Fixed 7-stage pipeline | Dynamic handoffs |
| **State Management** | Redis (explicit state machine) | Swarm context (passed between agents) |
| **Predictability** | High | Medium |
| **Debugging** | Easy (linear logs) | Complex (multi-agent traces) |

## Architecture Comparison

### cluster-monitor (Orchestrator-Worker)

```
Correlator → Orchestrator → Workers (Investigator, Memory, Remediator, Narrator)
```

**Philosophy:** Central coordinator delegates tasks to specialized workers. Each worker has a single responsibility and returns results to the orchestrator.

**Workflow Stages:**
1. Analyzing
2. Querying Memory
3. Investigating
4. Planning Remediation
5. Executing Action
6. Verifying
7. Summarizing

**State:** Explicitly managed in Redis with `InvestigationState` model.

### cluster-swarm (Swarm Intelligence)

```
Correlator → Triage → {Investigator, Memory, Remediation, Communications} (collaborative)
```

**Philosophy:** Peer agents collaborate through handoffs. Each agent decides who to hand off to based on what it discovers.

**Agent Roles:**
- **Triage:** Entry point, routes to specialists
- **Investigator:** Diagnostic specialist
- **Memory:** Learning and pattern specialist
- **Remediation:** Fix specialist
- **Communications:** Discord specialist

**State:** Passed as `SwarmContext` between agents during handoffs.

## Code Structure Comparison

### cluster-monitor

```
cluster-monitor/
├── src/cluster_monitor/
│   ├── __init__.py
│   ├── models.py           # InvestigationState, WorkerTask, WorkerResult
│   ├── correlator.py       # EventCorrelator service
│   ├── orchestrator.py     # InvestigationOrchestrator
│   ├── workers.py          # All worker agents
│   └── worker.py           # Entry point
├── tests/
│   └── test_correlator.py
├── pyproject.toml
└── README.md
```

**Lines of Code:** ~800 (excluding tests and docs)

### cluster-swarm

```
cluster-swarm/
├── src/cluster_swarm/
│   ├── __init__.py
│   ├── models.py           # SwarmContext, CorrelatedIssue
│   ├── swarm.py            # All swarm agents + ClusterSwarm
│   └── worker.py           # Entry point
├── tests/
│   └── test_swarm.py
├── pyproject.toml
└── README.md
```

**Lines of Code:** ~500 (excluding tests and docs)

*Note: cluster-swarm is more concise because agent collaboration logic is handled by the Strands SDK, whereas cluster-monitor implements explicit orchestration.*

## Key Implementation Differences

### Investigation Initiation

**cluster-monitor:**
```python
# Orchestrator receives INVESTIGATION_REQUESTED event
# Creates InvestigationState with explicit stage tracking
state = InvestigationState(
    investigation_id=investigation_id,
    correlation_id=correlated_issue.correlation_id,
    stage=InvestigationStage.ANALYZING,
    events=correlated_issue.events,
)

# Follows fixed workflow
await self._stage_analyze(state)
await self._stage_query_memory(state)
await self._stage_investigate(state)
# ... etc
```

**cluster-swarm:**
```python
# Swarm receives INVESTIGATION_REQUESTED event
# Creates SwarmContext for agent collaboration
context = SwarmContext(
    correlation_id=correlated_issue.correlation_id,
    events=correlated_issue.events,
    pattern_type=correlated_issue.pattern_type,
    severity=correlated_issue.severity,
)

# Triage agent decides next steps dynamically
# Agents hand off to each other based on findings
```

### Worker/Agent Invocation

**cluster-monitor:**
```python
# Orchestrator explicitly delegates to workers
result = await self._delegate_to_worker("investigate", context)

# Worker returns structured result
class WorkerResult(BaseModel):
    task_id: str
    success: bool
    data: dict[str, Any]
    error: str | None = None
```

**cluster-swarm:**
```python
# Agents hand off to each other via Strands
# Each agent decides who to hand off to next
# Handoff includes updated SwarmContext

# Example: Investigator hands off to Memory
# "I've found timeout issues. Let me hand off to the 
#  memory agent to check for similar past incidents."
```

### Communication/Narration

**cluster-monitor:**
```python
# Dedicated Narrator Worker called at each stage
narrator_context = {
    "stage": "investigation_findings",
    "findings": result.data,
    "message": "I've completed the diagnostic investigation..."
}
await self._delegate_to_worker("narrate", narrator_context)
```

**cluster-swarm:**
```python
# Communications Agent is a peer in the swarm
# Other agents hand off to it when they need to communicate
# Communications Agent maintains narrative coherence
# and hands back to the working agent
```

## Evaluation Criteria

When testing both implementations, consider:

### 1. Investigation Quality
- **Depth:** How thorough are the investigations?
- **Accuracy:** Do they identify root causes correctly?
- **Completeness:** Are all relevant aspects examined?

### 2. Communication Quality
- **Clarity:** Are updates easy to understand?
- **Tone:** Do they feel conversational and engineer-like?
- **Transparency:** Is the investigation process clear?
- **Coherence:** Does the narrative flow logically?

### 3. Operational Metrics
- **Latency:** Time from issue detection to resolution
- **LLM Calls:** Number of LLM invocations per investigation
- **Success Rate:** Percentage of issues successfully resolved
- **False Positives:** Unnecessary investigations triggered

### 4. Developer Experience
- **Debugging:** How easy is it to understand what went wrong?
- **Iteration:** How quickly can you improve prompts/logic?
- **Observability:** Can you trace execution paths?
- **Maintenance:** How much effort to keep running?

### 5. Edge Cases
- **Novel Issues:** How well do they handle unexpected situations?
- **Partial Failures:** What happens if a worker/agent fails?
- **Concurrent Issues:** Can they handle multiple simultaneous investigations?
- **Resource Constraints:** Behavior under high load?

## Testing Strategy

### Phase 1: Synthetic Testing
1. Create mock K8S_ISSUE_DETECTED events
2. Inject them into the event bus
3. Observe both agents' responses
4. Compare investigation paths and outcomes

### Phase 2: Replay Testing
1. Replay real incidents from k8s-monitor history
2. Compare how each agent would have handled them
3. Evaluate against actual resolutions

### Phase 3: Live Testing
1. Deploy both agents to a test cluster
2. Run them in parallel (different consumer groups)
3. Compare real-time performance
4. Gather user feedback on communication quality

### Phase 4: A/B Testing
1. Route 50% of investigations to each agent
2. Measure success rates, latency, costs
3. Collect qualitative feedback
4. Determine winner or identify hybrid approach

## Metrics Collection

Both agents should emit metrics for comparison:

```python
# Investigation metrics
investigation_duration_seconds
investigation_stage_duration_seconds  # cluster-monitor only
investigation_llm_calls_total
investigation_success_rate

# Communication metrics
messages_posted_total
message_quality_score  # user feedback

# Cost metrics
llm_tokens_used_total
redis_operations_total

# Error metrics
worker_failures_total  # cluster-monitor
agent_handoff_failures_total  # cluster-swarm
investigation_failures_total
```

## Next Steps

1. **Connect MCP Servers:** Both implementations currently use mock results. Connect actual kubernetes-mcp-server, memory-mcp-server, and discord-mcp-server.

2. **Implement Agent Execution:** cluster-monitor needs actual worker agent execution; cluster-swarm needs actual Strands swarm execution.

3. **Add Observability:** Implement structured logging, metrics collection, and tracing for both.

4. **Run Tests:** Execute the testing strategy above and collect data.

5. **Analyze Results:** Compare quantitative metrics and qualitative feedback.

6. **Decide:** Choose one approach, or design a hybrid that combines the best of both.

## Hybrid Approach (Future Consideration)

A potential "best of both worlds" approach:

```
Orchestrator (structured workflow)
    ├── Stage 1: Analyze
    ├── Stage 2: Query Memory
    ├── Stage 3: Investigate (mini-swarm of diagnostic specialists)
    ├── Stage 4: Plan Remediation
    ├── Stage 5: Execute
    ├── Stage 6: Verify
    └── Stage 7: Summarize

Narrator Worker (consistent communication)
```

This maintains the predictability and consistency of the orchestrator model while allowing dynamic exploration during the investigation stage.

## Conclusion

Both implementations are **experimental** and require further development to be production-ready. The goal of this parallel implementation is to gather real-world data to inform the final architecture decision.

**cluster-monitor** is the pragmatic choice for most teams, offering predictability and maintainability.

**cluster-swarm** is the ambitious choice for teams seeking maximum adaptability and willing to invest in complex orchestration.

The data from testing will reveal which approach better serves the goal of creating an engineer-like monitoring experience.
