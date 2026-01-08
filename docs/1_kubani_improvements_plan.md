# Kubani Improvements Implementation Plan

**Based on**: [1_kubani_improvements.md](1_kubani_improvements.md)
**Created**: January 6, 2026
**Status**: In Progress

---

## Overview

This document tracks the implementation of improvements from the Manus AI review. Tasks are organized by phase and can be checked off as completed.

### Progress Summary

| Phase | Status | Progress |
|-------|--------|----------|
| Phase 1: Foundation | Complete | 16/16 |
| Phase 2: Intelligence | Complete | 20/20 |
| Phase 3: Operations | In Progress | 9/12 |
| Phase 4: Advanced Features | In Progress | 3/12 |

**Last Updated**: January 7, 2026

---

## Phase 1: Foundation

**Goal**: Address critical architectural issues and improve observability.

### 1.1 Replace Polling with Kubernetes Watch Streams

**Priority**: High | **Effort**: 1 week | **Reference**: Section 3.2, Recommendation 4

Replace the 30-second polling interval in SentinelAgent with real-time Kubernetes watch streams.

- [x] **1.1.1** Analyze current polling implementation in k8s-monitor
  - Identify polling code locations
  - Document current behavior and interval settings
  - List all event types currently monitored

- [x] **1.1.2** Implement Kubernetes watch client
  - Create `agents/k8s-monitor/src/k8s_monitor/watch.py`
  - Implement async watch stream using `kubernetes` library
  - Add reconnection logic with exponential backoff
  - Add filtering for relevant event types (Warning, Error)

- [x] **1.1.3** Integrate watch stream into SentinelAgent
  - Replace polling loop with watch stream
  - Maintain backward compatibility during transition
  - Add graceful shutdown handling

- [x] **1.1.4** Add tests and validate
  - Unit tests for watch stream reconnection
  - Integration test for event detection latency
  - Verify event detection latency < 1 second

---

### 1.2 Implement A2A (Agent-to-Agent) Communication Framework

**Priority**: High | **Effort**: 2-3 weeks | **Reference**: Section 3.1, Recommendation 1

Enable direct synchronous communication between agents for time-sensitive operations.

- [x] **1.2.1** Design A2A communication protocol
  - Define message format and schema
  - Choose transport (gRPC vs HTTP)
  - Define timeout and retry policies
  - Document circuit breaker requirements

- [x] **1.2.2** Implement A2A client in core_agents
  - Create `agents/core/src/core_agents/communication/a2a.py`
  - Implement `A2AClient` class with async query method
  - Add service discovery mechanism
  - Implement circuit breaker pattern

- [x] **1.2.3** Implement A2A server capability
  - Create `agents/core/src/core_agents/communication/server.py`
  - Add endpoint registration mechanism
  - Implement request routing and handlers
  - Add health check endpoint

- [x] **1.2.4** Add A2A support to existing agents
  - Update k8s-monitor to expose A2A endpoints
  - Add A2A client usage in HealerAgent
  - Document A2A usage patterns

- [x] **1.2.5** Test and validate
  - Unit tests for A2A client/server
  - Integration test for cross-agent communication
  - Verify A2A latency < 100ms

---

### 1.3 Add End-to-End Integration Testing ✅

**Priority**: High | **Effort**: 4-5 weeks | **Reference**: Section 6.1

Create E2E test suite that validates complete workflows in a real Kubernetes environment.

- [x] **1.3.1** Set up test infrastructure
  - Create `tests/e2e/` directory structure
  - Create `tests/e2e/kind-config.yaml` for kind cluster
  - Create `tests/e2e/setup_cluster.sh` script (with Redis, namespaces)
  - Create `tests/e2e/conftest.py` with pytest fixtures

- [x] **1.3.2** Implement test utilities
  - Create `tests/e2e/utils.py` with helper functions
  - Implement `EventCapture` class for capturing Event Bus events
  - Implement `wait_for_event()` helper with timeout and filters
  - Implement `wait_for_pod_status()` helper
  - Implement `TestResourceManager` for cleanup

- [x] **1.3.3** Create core E2E test scenarios
  - `test_event_flow.py` - Event publishing and consumption
  - `test_agent_lifecycle.py` - Agent startup/health/restart/configuration
  - `test_healing_workflow.py` - Issue detection to resolution
  - `test_a2a_communication.py` - Agent-to-agent messaging and handoffs

- [x] **1.3.4** Add justfile commands
  - `just test-e2e` for running E2E tests
  - `just test-e2e-quick` for smoke tests
  - `just e2e-cluster-setup` for kind cluster setup
  - `just e2e-cluster-delete` for cleanup
  - `just e2e-full` for complete workflow

---

### 1.4 Consolidate Agent Entrypoints

**Priority**: Medium | **Effort**: 1 week | **Reference**: Section 5.1

Create generic `AgentWorker` class to reduce boilerplate in agent workers.

- [x] **1.4.1** Create AgentWorker class in core_agents
  - Create `agents/core/src/core_agents/worker.py`
  - Implement generic Temporal worker setup
  - Add configurable hooks factory
  - Add standard logging and metrics

- [x] **1.4.2** Migrate k8s-monitor to use AgentWorker
  - Refactor `agents/k8s-monitor/src/k8s_monitor/worker.py`
  - Verify all functionality preserved
  - Update tests

- [x] **1.4.3** Migrate news-monitor to use AgentWorker
  - Refactor `agents/news-monitor/src/news_monitor/worker.py`
  - Verify all functionality preserved
  - Update tests

- [x] **1.4.4** Update documentation and templates
  - Update agent template in `just new-agent`
  - Document AgentWorker usage in CLAUDE.md

---

## Phase 2: Intelligence

**Goal**: Enhance agent autonomy and learning capabilities.

### 2.1 Implement Hierarchical Agent Structure ✅

**Priority**: High | **Effort**: 4-6 weeks | **Reference**: Section 3.1, Recommendation 2

Refactor k8s-monitor into a hierarchy: Coordinator -> Triage -> Diagnosis -> Remediation.

- [x] **2.1.1** Design hierarchical architecture
  - Document agent hierarchy and responsibilities
  - Define handoff protocols between levels
  - Design shared context passing mechanism
  - Create architecture diagrams

- [x] **2.1.2** Implement TriageAgent
  - Create `agents/k8s-monitor/src/k8s_monitor/agents/triage.py`
  - Implement initial assessment logic
  - Add context gathering from cluster
  - Add severity and urgency determination

- [x] **2.1.3** Implement DiagnosisAgent hierarchy
  - Create `agents/k8s-monitor/src/k8s_monitor/agents/diagnosis/base.py`
  - Implement `PodDiagnostician` for pod-specific issues
  - Implement `NodeDiagnostician` for node-level problems
  - Implement `NetworkDiagnostician` for connectivity issues
  - Implement `StorageDiagnostician` for storage issues

- [x] **2.1.4** Implement RemediationAgent
  - Create `agents/k8s-monitor/src/k8s_monitor/agents/cluster_remediator.py`
  - Add skill retrieval from library
  - Implement approval request logic
  - Add execution and verification

- [x] **2.1.5** Create K8sCoordinatorAgent
  - Create `agents/k8s-monitor/src/k8s_monitor/agents/coordinator.py`
  - Implement Swarm-based handoff orchestration
  - Add metrics for each agent in hierarchy
  - Integrate with existing workflows

- [x] **2.1.6** Test and validate
  - Unit tests for each agent
  - Integration tests for handoffs
  - Verify 50% reduction in prompt complexity

---

### 2.2 Build Automated Skill Validation ✅

**Priority**: Medium-High | **Effort**: 5-7 weeks | **Reference**: Section 3.1, Recommendation 3

Create closed-loop learning system for automated skill testing and validation.

- [x] **2.2.1** Design skill validation workflow
  - Document validation stages (proposal -> sandbox -> verification -> promotion)
  - Define sandbox namespace requirements
  - Design confidence scoring algorithm
  - Document staged rollout process

- [x] **2.2.2** Implement sandbox environment
  - Create sandbox namespace provisioning logic
  - Implement resource cleanup after tests
  - Add isolation and security controls
  - Create test fixtures for common scenarios

- [x] **2.2.3** Implement SkillValidator class
  - Create `agents/core/src/core_agents/skills/validator.py`
  - Implement `validate_skill()` method
  - Add self-verification logic
  - Implement confidence score calculation

- [x] **2.2.4** Implement confidence-based skill selection
  - Update skill library search to include confidence weighting
  - Add `experimental` flag support for new skills (SkillStatus enum)
  - Implement skill promotion logic (SkillPromoter class)
  - Track skill success/failure rates

- [x] **2.2.5** Integrate with ExplorerAgent
  - Add `select_skill_with_confidence()` function
  - Implement weighted scoring of similarity and confidence

- [x] **2.2.6** Test and validate
  - Unit tests for SkillValidator
  - Confidence-based selection tests

---

### 2.3 Create WorldModelAgent ✅

**Priority**: Medium | **Effort**: 4-5 weeks | **Reference**: Section 4.1

Implement agent that maintains real-time comprehensive model of system state.

- [x] **2.3.1** Design WorldModel architecture
  - Define graph schema for cluster resources (ResourceNode, ResourceEdge)
  - Design query interface (WorldModelQuery, WorldModelResponse)
  - Plan state history retention (deque with configurable max)
  - Document integration points with other agents

- [x] **2.3.2** Implement WorldModelAgent
  - Create `agents/k8s-monitor/src/k8s_monitor/agents/world_model.py`
  - Implement graph-based state storage (nodes, edges, reverse edges)
  - Add event handlers for resource changes (created, updated, deleted)
  - Implement state history tracking

- [x] **2.3.3** Implement query interface
  - Implement `query()` method with multiple query types
  - Implement `_query_get_resource()` method
  - Implement `_query_get_lineage()` method (ancestors)
  - Implement `_query_get_affected()` method (descendants)
  - Implement `_query_namespace_status()` and `_query_cluster_summary()`

- [x] **2.3.4** Integrate with Event Bus
  - Subscribe to all relevant events via `handle_event()`
  - Build real-time graph updates
  - Track agent actions on resources

- [x] **2.3.5** Deploy and integrate
  - Integrated into k8s-monitor coordinator
  - Statistics tracking via `get_stats()`

---

### 2.4 Add AgentFactory Standardization

**Priority**: Medium | **Effort**: 1-2 weeks | **Reference**: Section 5.2

Create unified factory for standardized agent creation.

- [x] **2.4.1** Implement AgentFactory
  - Create `agents/core/src/core_agents/factory.py`
  - Implement `ModelConfig` and `SwarmConfig` dataclasses
  - Implement `create_single_agent()` method
  - Implement `create_swarm()` method
  - Add standard hooks for observability

- [x] **2.4.2** Migrate existing agents to use AgentFactory
  - Update k8s-monitor agents
  - Update news-monitor agents
  - Verify consistent behavior

- [x] **2.4.3** Update templates and documentation
  - Update `just new-agent` template
  - Document AgentFactory usage patterns
  - Add examples in CLAUDE.md

---

## Phase 3: Operations

**Goal**: Improve operational efficiency and deployment automation.

### 3.1 Create GitOpsAgent ✅

**Priority**: Medium | **Effort**: 2-3 weeks | **Reference**: Section 4.3

Fully automate GitOps deployment pipeline.

- [x] **3.1.1** Design automation workflow
  - Document event-driven deployment flow
  - Design rollback mechanism (auto_rollback parameter)
  - Plan Flux CD integration

- [x] **3.1.2** Implement GitOpsAgent
  - Create `agents/core/src/core_agents/integrations/gitops.py`
  - Implement `GitOpsManager` class with full deployment logic
  - Implement `GitOpsAgent` class for event-driven automation
  - Add manifest update logic (`update_image_tag()`)
  - Implement commit and push automation (`git_commit_and_push()`)

- [x] **3.1.3** Add verification and rollback
  - Implement `wait_for_reconciliation()` with polling
  - Implement `wait_for_rollout()` using kubectl
  - Implement `get_flux_kustomization_status()`
  - Implement automatic rollback on failure

- [x] **3.1.4** Integrate and deploy
  - Create `.github/workflows/release.yml` with full automation
  - Implement `quick_deploy()` convenience function
  - CI/CD pipeline emits deployment events

---

### 3.2 Implement Chaos Engineering Tests ✅

**Priority**: Medium | **Effort**: 3-4 weeks | **Reference**: Section 6.2

Add chaos tests to validate system behavior under failure conditions.

- [x] **3.2.1** Set up chaos infrastructure
  - Create `tests/chaos/` directory structure
  - Create `tests/chaos/framework.py` with `ChaosTestHelper`
  - Create `tests/chaos/conftest.py` with pytest configuration
  - Document chaos-mesh installation in justfile

- [x] **3.2.2** Implement chaos test scenarios
  - `test_redis_failure_recovery` - Redis (Event Bus) failure
  - `test_qdrant_failure_recovery` - Qdrant (Skill Library) failure
  - `test_network_partition` - Agent network isolation
  - `test_cpu_exhaustion` - CPU stress
  - `test_memory_exhaustion` - Memory pressure
  - `test_network_latency` - Slow LLM API handling
  - `test_cascading_failures` - Multiple simultaneous failures
  - `test_event_bus_reconnection` - Redis reconnection
  - `test_partial_system_availability` - Graceful degradation

- [x] **3.2.3** Add justfile integration
  - `just test-chaos` command
  - `just test-chaos-scenario <name>` command
  - `just chaos-install` and `just chaos-uninstall`

Note: Some tests are skipped due to chaos-mesh webhook connectivity issues on the cluster.

---

### 3.3 Add Semantic Versioning Automation 🔶

**Priority**: Low-Medium | **Effort**: 1 week | **Reference**: Section 6.3

Automate version bumping and changelog generation.

- [ ] **3.3.1** Configure commitlint
  - Create `.commitlintrc.json`
  - Define commit types and scopes
  - Add pre-commit hook

- [ ] **3.3.2** Configure semantic-release
  - Create `.releaserc.json`
  - Configure release rules
  - Set up changelog generation

- [x] **3.3.3** Update CI/CD
  - Create `.github/workflows/release.yml` ✅
  - Create `scripts/bump-version.py` ✅
  - Create `scripts/generate-changelog.py` ✅
  - Add release job with version bump, changelog, build, and GitHub release

- [x] **3.3.4** Document and train
  - Update CLAUDE.md with commit conventions ✅
  - Add commit message examples ✅
  - Conventional commits documented in `.claude/rules/commits.md` ✅

---

## Phase 4: Advanced Features

**Goal**: Add predictive and proactive capabilities.

### 4.1 Build AnomalyDetectionAgent

**Priority**: Low-Medium | **Effort**: 6-8 weeks | **Reference**: Section 4.4

Proactively detect unusual patterns before they become critical.

- [ ] **4.1.1** Design detection algorithms
  - Document statistical methods (z-score, moving average)
  - Design ML model approach (Isolation Forest)
  - Define baseline training requirements
  - Plan alert severity levels

- [ ] **4.1.2** Implement AnomalyDetectionAgent
  - Create `agents/anomaly-detection/` directory structure
  - Implement baseline training
  - Add statistical anomaly detection
  - Add ML-based detection (optional)

- [ ] **4.1.3** Integrate and deploy
  - Create GitOps manifests
  - Subscribe to metrics streams
  - Add Discord alerting
  - Create Grafana dashboard

---

### 4.2 Implement Centralized Configuration Management ✅

**Priority**: Low-Medium | **Effort**: 1 week | **Reference**: Section 5.3

Consolidate configuration using Pydantic settings.

- [x] **4.2.1** Implement CoreConfig
  - Create `agents/core/src/core_agents/config.py` (632 lines)
  - Define all configuration options (LLM, embeddings, event bus, skill library, graph memory, approval, observability, Temporal, A2A)
  - Implement singleton pattern (`get_config()`, `reset_config()`)
  - Add validation via Pydantic BaseSettings

- [x] **4.2.2** Migrate agents to use CoreConfig
  - Sub-configs available: `get_llm_config()`, `get_event_bus_config()`, etc.
  - Convenience functions: `get_vllm_url()`, `get_redis_url()`, etc.
  - `KUBANI_` environment variable prefix

- [x] **4.2.3** Document configuration
  - Configuration documented with Field descriptions
  - Environment-specific examples in docstrings

---

### 4.3 Additional Advanced Features

**Priority**: Low | **Reference**: Section 7, Phase 4

- [ ] **4.3.1** Skill composition metrics
  - Track skill composition success rates
  - Add recommendations for skill improvements

- [ ] **4.3.2** Predictive scaling
  - Analyze historical patterns
  - Implement proactive scaling recommendations

- [ ] **4.3.3** Agent performance optimizer
  - Automated optimization suggestions
  - Model selection recommendations

---

## Parallel Tracks

### Documentation Track (Ongoing)

- [ ] Update architecture diagrams as changes are made
- [ ] Create runbooks for new agents
- [ ] Document failure modes and recovery procedures
- [ ] Update CLAUDE.md with new patterns

### Testing Track (Ongoing)

- [ ] Increase unit test coverage to 80%+
- [ ] Add integration tests for each new feature
- [ ] Maintain chaos test suite
- [ ] Add performance benchmarks

### Observability Track (Ongoing)

- [ ] Expand Prometheus metrics
- [ ] Create Grafana dashboards for new agents
- [ ] Implement distributed tracing
- [ ] Set up alerting rules

---

## Notes and Decisions

### Completed Items

*(Record completed items with dates and notes here)*

### Blocked Items

*(Record any blocked items with reasons and dependencies)*

### Deferred Items

- **CostAndPerformanceAgent** (Section 4.2 in original review) - Deferred to revisit later. Would monitor resource consumption, token usage, and provide cost optimization suggestions.

### Design Decisions

*(Record important design decisions made during implementation)*

---

## References

- [Original Review Document](1_kubani_improvements.md)
- [Voyager Paper](https://voyager.minedojo.org/)
- [Multi-Agent Best Practices](https://www.getmaxim.ai/articles/best-practices-for-building-production-ready-multi-agent-systems/)
