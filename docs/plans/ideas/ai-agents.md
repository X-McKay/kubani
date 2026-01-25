# AI Agents Roadmap

This document tracks planned improvements and future features for the AI agents system.

## Planned

- [ ] ** 1.1 Re-organize Core Agent Functionality
  - Make sure no k8s-monitor or news-monitor logic or functionality is contained under 'core', and figure out an apporpriate way to systematically store things like agent specific memory configurations under the agents themselves.
  - Modify Claude skills to ensure the core functionality remains clean and isolated from the underlying agent workflows that leverage it

- [ ] **1.2 Configurable Feeds** - Dynamic news sources
  - Admin interface for feed management
  - Source reliability scoring

- [ ] **1.3 security-monitor** - Security-focused agent
  - CVE monitoring and alerting
  - RBAC audit and recommendations
  - Network policy analysis
  - Secret rotation tracking

- [ ] **2.1 Registry Service**
  - Replace static ConfigMaps with a dynamic FastAPI registry service backed by PostgreSQL:
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

### Additional Ideas to revisit at a later date

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
