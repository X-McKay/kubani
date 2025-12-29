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

## In Progress

### Phase 2: Memory & Intelligence

- [ ] **1.1 Graph Memory (mem0g)** - Enable relationship tracking between entities
  - Track connections: Issue → Fix → Outcome
  - Query paths: "What fixes worked for OOMKilled pods?"

- [ ] **1.2 Hierarchical Memory** - Three-tier memory system
  - Working memory (current session context)
  - Episodic memory (recent remediations, 7-30 days)
  - Semantic memory (permanent patterns, best practices)

- [ ] **3.4 User Preferences Memory** - news-monitor personalization
  - Track user topic interests from feedback
  - Adjust importance scoring based on engagement

## Planned

### Phase 3: Agent Communication

- [ ] **5.1 Temporal Saga Patterns** - Cross-agent workflows
  - Shared signal channels for coordination
  - Compensating actions for rollback

- [ ] **5.2 A2A Protocol** - Agent-to-Agent communication
  - Standardized message format for inter-agent requests
  - Service discovery for agent capabilities

- [ ] **2.4 Recurrence Intelligence** - Smart pattern detection
  - Auto-detect recurring issues
  - Suggest permanent fixes after N occurrences
  - Escalation workflows for chronic problems

### Phase 4: Proactive Capabilities

- [ ] **2.2 Anomaly Detection** - Predictive monitoring
  - Baseline normal metrics patterns
  - Alert on deviations before failures
  - Integration with Prometheus/metrics-server

- [ ] **3.2 Configurable Feeds** - Dynamic news sources
  - Admin interface for feed management
  - Source reliability scoring

- [ ] **4.4 capacity-planner** - Resource forecasting agent
  - Analyze usage trends
  - Predict capacity needs
  - Recommend scaling actions

### Phase 5: Security & Advanced

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
