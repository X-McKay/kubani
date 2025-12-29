# AI Agents Roadmap

This document tracks planned improvements and future features for the AI agents system.

## Completed

### Phase 1: Foundation (Completed)

- [x] **1.3 Unified Observability Hooks** - `core_agents/observability.py`
  - Token usage tracking, latency metrics, tool call success rates
  - Auto-enabled in `create_agent()` for all agents

- [x] **5.3 MCP Server Registry** - `gitops/infrastructure/mcp-registry/`
  - ConfigMap-based registry for MCP server discovery
  - Agent policies for access control
  - `core_agents/mcp_registry.py` client utilities

- [x] **2.1 Native MCP Integration** - k8s-monitor agents
  - Dual transport support (stdio for dev, SSE for cluster)
  - ClusterScout, ClusterTriage, PodDiagnostician, ClusterRemediator now use MCP

### Phase 2: Memory & Intelligence (Completed)

- [x] **1.1 Graph Memory Infrastructure** - Qdrant + Neo4j deployment
  - Qdrant: High-performance vector store for semantic search
  - Neo4j: Graph database for relationship tracking (mem0g)
  - GitOps manifests: `gitops/infrastructure/qdrant/`, `gitops/infrastructure/neo4j/`
  - Prometheus metrics integration for both databases
  - `core_agents/mem0_utils.py` updated with:
    - `get_mem0_config()` - Qdrant-based vector memory
    - `get_graph_mem0_config()` - Qdrant + Neo4j graph memory
    - `get_k8s_graph_mem0_config()` - K8s-optimized with custom entity extraction
  - Track connections: Issue → Fix → Outcome
  - Query paths: "What fixes worked for OOMKilled pods?"

- [x] **1.2 Hierarchical Memory** - `core_agents/hierarchical_memory.py`
  - Three-tier memory system:
    - Working memory (current session context, in-memory)
    - Episodic memory (recent events, 7-30 day retention)
    - Semantic memory (permanent patterns, never expires)
  - Auto-expiration for episodic memories
  - Cross-tier search
  - Memory promotion (episodic → semantic)

- [x] **3.4 User Preferences Memory** - `core_agents/user_preferences.py`
  - Track user topic interests from engagement
  - Engagement types: like, dislike, bookmark, view, share, dismiss
  - Score decay over time (configurable half-life)
  - Content ranking by user preference
  - Integration-ready for news-monitor personalization

### Phase 3: Agent Communication (Completed)

- [x] **5.1 Temporal Saga Patterns** - `core_agents/saga.py`
  - Saga pattern for distributed transactions with compensation
  - `SagaStep`: Forward action + compensation (rollback) action
  - `Saga`: Executes steps, auto-compensates on failure
  - Signal channel registry for cross-workflow coordination
  - Pre-defined channels: issue-detected, remediation-complete, agent-handoff
  - Integration helpers: `create_saga_workflow_id()`, `create_signal_workflow_id()`

- [x] **5.2 A2A Protocol** - `core_agents/a2a.py`
  - Leverages Strands' built-in A2A support (Google A2A spec)
  - `create_a2a_server()`: Expose Strands agents via A2A HTTP protocol
  - Kubani-specific `AgentRegistry` with well-known agents
  - Service discovery by capability: `find_agent_for("pod-diagnosis")`
  - Temporal integration: `get_task_queue_for_agent()`
  - Auto-derived skills from agent tools

- [x] **2.4 Recurrence Intelligence** - `core_agents/recurrence.py`
  - Pattern detection for recurring issues:
    - TEMPORAL: Time-based patterns (hourly, daily)
    - RESOURCE: Same resource/deployment affected repeatedly
    - CLUSTER: Multiple issues occurring together
    - PERIODIC: Regular interval patterns
  - `PatternMatcher`: Records issues, detects patterns
  - `RecurrencePattern`: Pattern details with confidence score
  - `suggest_prevention()`: Automated prevention recommendations
  - Severity classification based on issue types and frequency

### Phase 4: Proactive Capabilities (Completed)

- [x] **2.2 Anomaly Detection** - `core_agents/intelligence/anomaly.py`
  - Statistical baseline tracking for metrics (mean, std dev, percentiles)
  - Z-score based anomaly detection with configurable thresholds
  - Alert types: SPIKE, DROP, DRIFT, VOLATILITY, THRESHOLD, TREND
  - Severity levels: INFO, WARNING, CRITICAL
  - Default thresholds for common K8s metrics (CPU, memory, disk, restarts, errors)
  - `AnomalyDetector`: Tracks metrics, builds baselines, checks for anomalies
  - `check_metric()`: Convenience function for simple usage

- [x] **4.4 Capacity Planner** - `core_agents/intelligence/capacity.py`
  - Resource usage tracking (CPU, memory, storage, GPU, pods)
  - Growth rate calculation and usage forecasting
  - Capacity recommendations with urgency levels (LOW, MEDIUM, HIGH, CRITICAL)
  - Recommendation types: SCALE_UP, SCALE_DOWN, REBALANCE, OPTIMIZE, ALERT
  - Node imbalance detection across cluster
  - `CapacityPlanner`: Records usage, forecasts capacity, generates recommendations
  - `record_node_usage()`: Convenience function for simple usage

## Planned

### Phase 5: Content & Security

- [ ] **3.2 Configurable Feeds** - Dynamic news sources
  - Admin interface for feed management
  - Source reliability scoring

- [ ] **4.3 security-monitor** - Security-focused agent
  - CVE monitoring and alerting
  - RBAC audit and recommendations
  - Network policy analysis
  - Secret rotation tracking

## Future Considerations

### Centralized Registry Service

**Status**: Deferred (revisit after Phase 3)

Replace static ConfigMaps with a dynamic FastAPI registry service backed by PostgreSQL:

```
registry-service/
├── mcp_servers/      # MCP server endpoints, capabilities, policies
├── models/           # LLM configs (vLLM URLs, model IDs, parameters)
├── agents/           # Agent metadata, versions, health status
└── policies/         # Access control, approval workflows
```

**Benefits**:
- Dynamic configuration without GitOps deploys
- Runtime service discovery
- Versioned config with audit trails
- Unified admin interface

**Dependencies**:
- More agents deployed (justifies complexity)
- Cross-agent communication patterns established (5.1, 5.2)
- Clear admin workflow requirements

### Additional Ideas

- **cost-monitor** - Track LLM token usage, estimate costs (less relevant for self-hosted)
- **docs-agent** - Auto-generate documentation from cluster state
- **migration-assistant** - Help with K8s version upgrades
- **backup-monitor** - Verify backup jobs, test restores

## Architecture Principles

1. **MCP-First** - Use MCP servers for external integrations where possible
2. **Memory-Enhanced** - All agents should learn from past interactions
3. **Observable** - Unified metrics and tracing across all agents
4. **Safe by Default** - Safety hooks enabled, dangerous ops require approval
5. **GitOps Compatible** - Config changes through Git, Flux handles deployment

## Memory Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        AI Agent Memory System                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                     │
│  │   vLLM      │    │   Qdrant    │    │   Neo4j     │                     │
│  │ Embeddings  │───▶│   Vector    │    │   Graph     │                     │
│  │             │    │   Store     │    │   Store     │                     │
│  └─────────────┘    └─────────────┘    └─────────────┘                     │
│        │                   │                  │                              │
│        │                   ▼                  ▼                              │
│        │           ┌─────────────────────────────────┐                      │
│        │           │            mem0                 │                      │
│        └──────────▶│     Memory Management           │                      │
│                    │   - add/search memories         │                      │
│                    │   - entity extraction           │                      │
│                    │   - relationship tracking       │                      │
│                    └─────────────────────────────────┘                      │
│                                   │                                          │
│                    ┌──────────────┼──────────────┐                          │
│                    ▼              ▼              ▼                          │
│            ┌────────────┐ ┌────────────┐ ┌────────────┐                    │
│            │ Hierarchical│ │   User     │ │  K8s Graph │                    │
│            │   Memory    │ │ Preferences│ │   Memory   │                    │
│            ├────────────┤ ├────────────┤ ├────────────┤                    │
│            │• Working   │ │• Interests │ │• Entities  │                    │
│            │• Episodic  │ │• Engagement│ │• Relations │                    │
│            │• Semantic  │ │• Decay     │ │• Patterns  │                    │
│            └────────────┘ └────────────┘ └────────────┘                    │
│                                                                              │
│  Configuration Functions:                                                    │
│  - get_mem0_config()           → Qdrant vector memory                       │
│  - get_graph_mem0_config()     → Qdrant + Neo4j graph memory                │
│  - get_k8s_graph_mem0_config() → K8s-tuned entity extraction                │
│                                                                              │
│  Memory Classes:                                                             │
│  - HierarchicalMemory          → Working/episodic/semantic tiers            │
│  - UserPreferences             → Engagement-based personalization           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Agent Communication Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Agent Communication (Phase 3)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      A2A Protocol (Strands)                          │   │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐              │   │
│  │  │ k8s-monitor │◀──▶│  A2AServer  │◀──▶│news-monitor │              │   │
│  │  │   :9000     │    │   (HTTP)    │    │   :9000     │              │   │
│  │  └─────────────┘    └─────────────┘    └─────────────┘              │   │
│  │         │                  │                  │                       │   │
│  │         └──────────────────┼──────────────────┘                       │   │
│  │                            ▼                                          │   │
│  │                   ┌─────────────────┐                                 │   │
│  │                   │  AgentRegistry  │                                 │   │
│  │                   │ find_agent_for()│                                 │   │
│  │                   │ get_a2a_endpoint│                                 │   │
│  │                   └─────────────────┘                                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    Temporal Saga Patterns                            │   │
│  │                                                                       │   │
│  │  ┌────────────┐   ┌────────────┐   ┌────────────┐                   │   │
│  │  │ SagaStep 1 │──▶│ SagaStep 2 │──▶│ SagaStep 3 │                   │   │
│  │  │  (forward) │   │  (forward) │   │  (forward) │   SUCCESS ──▶     │   │
│  │  └────────────┘   └────────────┘   └────────────┘                   │   │
│  │        │                │                │                           │   │
│  │        ▼                ▼                ▼                           │   │
│  │  ┌────────────┐   ┌────────────┐   ┌────────────┐                   │   │
│  │  │compensate 1│◀──│compensate 2│◀──│   FAIL!    │◀── on failure     │   │
│  │  │  (rollback)│   │  (rollback)│   └────────────┘                   │   │
│  │  └────────────┘   └────────────┘                                    │   │
│  │                                                                       │   │
│  │  Signal Channels: issue-detected, remediation-complete, agent-handoff│   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    Recurrence Intelligence                           │   │
│  │                                                                       │   │
│  │  PatternMatcher                      RecurrencePattern               │   │
│  │  ┌────────────────┐                 ┌──────────────────────────────┐│   │
│  │  │ record_issue() │──detect───────▶ │ PERIODIC: every 2 hours      ││   │
│  │  │ get_patterns() │                 │ RESOURCE: pod/app-* failing  ││   │
│  │  │ get_statistics │                 │ CLUSTER: 5 issues at once    ││   │
│  │  └────────────────┘                 └──────────────────────────────┘│   │
│  │         │                                        │                   │   │
│  │         ▼                                        ▼                   │   │
│  │  ┌────────────────┐                 ┌──────────────────────────────┐│   │
│  │  │suggest_prevent │──────────────▶  │ "Memory issues detected.     ││   │
│  │  │   ion()        │                 │  Increase memory limits..."  ││   │
│  │  └────────────────┘                 └──────────────────────────────┘│   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  Key Classes:                                                                │
│  - A2AServer, create_a2a_server()  → Strands A2A HTTP server                │
│  - AgentRegistry, AgentCapability  → Service discovery                      │
│  - Saga, SagaStep, SagaResult      → Distributed transactions               │
│  - SignalChannelRegistry           → Cross-workflow signals                 │
│  - PatternMatcher, RecurrencePattern → Issue pattern detection              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Proactive Intelligence Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Proactive Intelligence (Phase 4)                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      Anomaly Detection                               │   │
│  │                                                                       │   │
│  │  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐   │   │
│  │  │ Metric Data  │───▶│  Baseline    │───▶│   AnomalyAlert       │   │   │
│  │  │ (CPU, Mem)   │    │ (mean, std)  │    │ (SPIKE/DROP/TREND)   │   │   │
│  │  └──────────────┘    └──────────────┘    └──────────────────────┘   │   │
│  │         │                   │                      │                 │   │
│  │         ▼                   ▼                      ▼                 │   │
│  │  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐   │   │
│  │  │ Z-Score      │    │ Threshold    │    │    Severity          │   │   │
│  │  │ Analysis     │    │ Checking     │    │ INFO/WARNING/CRITICAL│   │   │
│  │  └──────────────┘    └──────────────┘    └──────────────────────┘   │   │
│  │                                                                       │   │
│  │  Key Classes: AnomalyDetector, MetricBaseline, AnomalyAlert          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      Capacity Planning                               │   │
│  │                                                                       │   │
│  │  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐   │   │
│  │  │ResourceUsage │───▶│  Forecast    │───▶│  Recommendations     │   │   │
│  │  │ (per node)   │    │ (growth rate)│    │  (SCALE_UP/DOWN)     │   │   │
│  │  └──────────────┘    └──────────────┘    └──────────────────────┘   │   │
│  │         │                   │                      │                 │   │
│  │         ▼                   ▼                      ▼                 │   │
│  │  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐   │   │
│  │  │ Cluster      │    │ Days Until   │    │    Urgency           │   │   │
│  │  │ Aggregate    │    │ Critical     │    │ LOW/MEDIUM/HIGH/CRIT │   │   │
│  │  └──────────────┘    └──────────────┘    └──────────────────────┘   │   │
│  │                                                                       │   │
│  │  Additional: Node imbalance detection, under-utilization alerts      │   │
│  │  Key Classes: CapacityPlanner, ResourceUsage, CapacityForecast       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```
