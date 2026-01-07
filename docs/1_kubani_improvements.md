# In-Depth Review: Kubani Federated Agent Architecture

**Author**: Manus AI
**Date**: January 6, 2026
**Repository**: https://github.com/X-McKay/kubani
**Branch**: feature/federated-agent-architecture

---

## Executive Summary

The Kubani project's federated agent architecture represents a sophisticated and well-designed approach to building autonomous, multi-agent systems for Kubernetes cluster management. The architecture demonstrates strong foundational principles including modularity, observability, and a forward-thinking **"Skills as Knowledge"** paradigm that separates declarative skill definitions from executable code.

This review identifies **ten key recommendations** across four major areas: agent framework architecture, new agents and workflows, code organization, and testing/release processes. The most critical improvements include evolving from pure orchestration to a hybrid coordination model, implementing automated skill validation, introducing new system-level agents (WorldModel, CostAndPerformance, GitOps), and strengthening end-to-end testing.

The system is production-ready for initial deployment but would benefit significantly from these enhancements to achieve true autonomous operation at scale.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Current State Analysis](#2-current-state-analysis)
3. [Strategic Recommendations](#3-strategic-recommendations)
4. [Proposed New Agents](#4-proposed-new-agents)
5. [Code Organization Improvements](#5-code-organization-improvements)
6. [Testing and Release Process Enhancements](#6-testing-and-release-process-enhancements)
7. [Implementation Roadmap](#7-implementation-roadmap)
8. [Conclusion](#8-conclusion)
9. [References](#9-references)

---

## 1. Architecture Overview

### 1.1. System Components

The federated architecture consists of several key components organized into a clear hierarchy:

| Component | Purpose | Technology |
|-----------|---------|------------|
| **Event Bus** | Central communication backbone | Redis Streams |
| **Skill Library** | Storage and retrieval of reusable behaviors | Qdrant (vector DB) |
| **Approval System** | Human-in-the-loop validation | Discord webhooks |
| **Core Agents Library** | Reusable agent primitives | Python package (wheel) |
| **Domain Agents** | Specialized agents (k8s-monitor, news-monitor) | Docker containers |
| **Orchestration** | Workflow execution | Temporal.io |

### 1.2. Agent Communication Patterns

The current system implements an **Orchestrated Coordination** pattern where the Event Bus acts as the central mediator. All agent-to-agent communication flows through this bus using a publish-subscribe model.

**Current Flow**:
```
SentinelAgent → EventBus → HealerAgent → SkillLibrary → MCP Tools → EventBus → Metrics
```

This pattern prioritizes consistency and debuggability but introduces potential bottlenecks as the system scales.

### 1.3. Skills as Knowledge Paradigm

One of the most innovative aspects of the architecture is the treatment of skills as **declarative knowledge** rather than executable code. Skills are stored as structured data (JSON/YAML) that reference MCP (Model Context Protocol) tools.

**Example Skill Structure**:
```yaml
name: "restart_crashlooping_pod"
description: "Restart a pod that is in CrashLoopBackOff state"
mcp_server: "kubernetes"
mcp_tool: "kubectl_delete_pod"
parameters:
  namespace: "{{namespace}}"
  pod_name: "{{pod_name}}"
verification:
  check: "pod_status"
  expected: "Running"
```

This approach provides several advantages: skills can be updated without redeploying agents, non-developers can create and modify skills, skills are version-controlled and auditable, and testing is simplified as skills can be validated independently.

---

## 2. Current State Analysis

### 2.1. Strengths

#### 2.1.1. Modular Architecture

The separation between `agents/core` (reusable library) and domain-specific agents (`k8s-monitor`, `news-monitor`) is exemplary. This allows for rapid development of new agents without duplicating infrastructure code. The use of a wheel-based distribution for the core library ensures that all agents share the same foundational primitives, reducing version drift and maintenance burden.

#### 2.1.2. Observability First

The inclusion of Prometheus metrics from day one is a best practice often overlooked in early-stage projects. The system tracks skill execution success/failure rates, event processing latency, approval request/response times, and agent-specific custom metrics. This observability foundation is critical for operating a production multi-agent system and demonstrates maturity in the design approach.

#### 2.1.3. Research-Informed Design

The architecture draws inspiration from cutting-edge research, particularly the Voyager agent [1]. The implementation of a skill library with semantic search and the self-verification pattern in the `HealerAgent` demonstrate a deep understanding of modern agent design principles. The explicit acknowledgment of Voyager in the codebase comments shows a commitment to learning from the state of the art.

#### 2.1.4. Production-Ready Infrastructure

The use of Earthly for reproducible builds, GitHub Actions for CI/CD, and Flux CD for GitOps deployment shows a commitment to production-grade infrastructure from the start. The build pipeline automatically discovers changed agents, builds only what's needed, and updates deployment manifests. This level of automation is rare in early-stage projects and positions Kubani well for scaling.

### 2.2. Weaknesses and Gaps

#### 2.2.1. Centralized Orchestration Bottleneck

While the Event Bus decouples agents, it also creates a single point of coordination. As the number of agents and event types grows, this could become a performance bottleneck. The system lacks the ability for agents to communicate directly for time-sensitive operations. The `SentinelAgent` must publish to the bus, wait for the `HealerAgent` to pick up the event, and then wait for the result to be published back. For critical issues requiring immediate response, this adds unnecessary latency.

#### 2.2.2. Polling-Based Event Detection

The `SentinelAgent` uses a polling mechanism to check for Kubernetes events every N seconds. This is inefficient and introduces latency. A true event-driven approach using Kubernetes watch streams would provide real-time responsiveness and reduce resource consumption. The current implementation checks the Kubernetes API every 30 seconds by default, meaning critical events could be delayed by up to half a minute before detection.

#### 2.2.3. Limited Autonomous Learning

The `ExplorerAgent` is designed to propose new skills, but the process is entirely manual. There is no mechanism for the agent to test new skills in a sandbox environment, automatically validate skill effectiveness, learn from failed skill executions, or compose new skills from existing primitives. This limits the system's ability to achieve true lifelong learning as demonstrated by Voyager [1].

#### 2.2.4. Fragmented State Management

System state is distributed across multiple locations: event history in Redis Streams, skill metadata in Qdrant, agent-specific state in memory, and cluster state in Kubernetes API. There is no unified view of "what is the current state of the entire system?" This makes debugging complex multi-agent interactions challenging and prevents the system from reasoning about its own state holistically.

#### 2.2.5. Insufficient Testing Coverage

The testing strategy focuses primarily on unit tests for individual agents. There is a notable absence of integration tests for agent-to-agent communication, end-to-end tests for complete workflows, chaos engineering tests for failure scenarios, and performance/load tests for the Event Bus. This gap represents a significant risk for production deployment.

---

## 3. Strategic Recommendations

### 3.1. Agent Framework and Architecture

#### Recommendation 1: Implement Hybrid Coordination Model

**Problem**: Pure orchestration through the Event Bus creates latency and potential bottlenecks.

**Solution**: Introduce direct Agent-to-Agent (A2A) communication for synchronous, high-priority interactions while maintaining the Event Bus for asynchronous, system-wide events. This aligns with the **Hybrid Coordination** pattern described in production multi-agent systems research [2].

**Implementation Steps**:

1. Complete the `agents/core/src/core_agents/communication/a2a.py` module
2. Add gRPC or HTTP endpoints to agents for direct communication
3. Implement request/response patterns with timeouts and circuit breakers
4. Use A2A for immediate queries, health checks, and urgent remediation requests
5. Use Event Bus for notifications, audit logs, metrics, and non-urgent tasks

**Example A2A Communication**:
```python
# HealerAgent queries WorldModelAgent directly for pod details
from core_agents.communication import A2AClient

a2a = A2AClient()
pod_details = await a2a.query(
    agent="world_model",
    query="get_pod_details",
    params={"namespace": "production", "pod": "api-server-abc123"},
    timeout=2.0  # Fast timeout for synchronous calls
)
```

**Benefits**: Reduced latency for critical operations (estimated 50-70% reduction), lower load on central Event Bus, improved system resilience (agents can communicate even if bus is temporarily unavailable), and maintained auditability through event logging.

**Effort**: Medium (2-3 weeks)
**Priority**: High

---

#### Recommendation 2: Adopt Hierarchical Agent Structure

**Problem**: Flat agent structure doesn't scale well for complex domains. The `k8s-monitor` agent tries to do too much, leading to complex prompts and difficult debugging.

**Solution**: Implement a hierarchical decomposition where high-level coordinator agents delegate to specialized sub-agents. This pattern is well-documented in multi-agent systems research [3] and provides clear responsibility boundaries.

**Proposed Hierarchy for K8s Monitoring**:

```
K8sCoordinatorAgent (Entry Point)
├── TriageAgent (Initial assessment)
│   ├── Gathers context from cluster
│   ├── Enriches event data with historical patterns
│   └── Determines severity and urgency
├── DiagnosisAgent (Deep analysis)
│   ├── PodDiagnostician (Pod-specific issues)
│   ├── NodeDiagnostician (Node-level problems)
│   └── NetworkDiagnostician (Connectivity issues)
└── RemediationAgent (Executes fixes)
    ├── Retrieves appropriate skill from library
    ├── Requests approval if needed
    └── Executes and verifies outcome
```

**Implementation Approach**:

1. Refactor `k8s-monitor` to separate concerns into distinct agent classes
2. Create specialized agent classes for each role with focused prompts
3. Implement clear handoff protocols between levels using the Swarm pattern
4. Add metrics for each agent in the hierarchy to track performance

**Example Handoff**:
```python
# CoordinatorAgent delegates to TriageAgent
result = await swarm.handoff(
    from_agent="coordinator",
    to_agent="triage",
    context={
        "event": k8s_event,
        "priority": "high",
        "reason": "CrashLoopBackOff detected"
    }
)
```

**Benefits**: Simpler and more focused agent prompts, easier to test individual components, better error isolation, clearer responsibility boundaries, and enables parallel processing at each level.

**Effort**: High (4-6 weeks)
**Priority**: High

---

#### Recommendation 3: Implement Automated Skill Validation and Learning

**Problem**: The `ExplorerAgent` proposes skills manually, and there's no automated validation before skills enter the main library. This creates a safety risk and limits the system's ability to learn autonomously.

**Solution**: Create a closed-loop learning system where skills are automatically tested in a sandbox before being promoted to production. This approach is inspired by Voyager's automatic curriculum and self-verification mechanisms [1].

**Proposed Workflow**:

1. **Skill Proposal**: `ExplorerAgent` proposes a new skill based on observed patterns or failures
2. **Sandbox Testing**: Skill is automatically tested in a dedicated "shadow" namespace
3. **Self-Verification**: Agent validates the skill achieved its intended outcome
4. **Confidence Scoring**: Initial confidence score assigned based on test results
5. **Staged Rollout**: Skill added to library with "experimental" flag
6. **Production Validation**: Skill used in real scenarios, confidence updated based on outcomes
7. **Promotion**: After N successful uses, skill promoted to "stable" status

**Implementation Details**:

```python
class SkillValidator:
    async def validate_skill(self, skill: Skill) -> ValidationResult:
        # Create sandbox environment
        sandbox = await self.create_sandbox_namespace()

        try:
            # Execute skill in sandbox
            result = await self.execute_skill(skill, sandbox)

            # Self-verify outcome
            verification = await self.verify_outcome(
                skill.verification_criteria,
                sandbox
            )

            # Calculate confidence score
            confidence = self.calculate_confidence(result, verification)

            return ValidationResult(
                success=verification.passed,
                confidence=confidence,
                logs=result.logs
            )
        finally:
            await self.cleanup_sandbox(sandbox)
```

**Confidence-Based Skill Selection**:
```python
# HealerAgent uses weighted scoring
def select_skill(self, query: str, skills: List[Skill]) -> Skill:
    scored_skills = []
    for skill in skills:
        similarity = self.semantic_similarity(query, skill.description)
        confidence = skill.confidence_score

        # Weighted combination
        score = (0.6 * similarity) + (0.4 * confidence)
        scored_skills.append((score, skill))

    return max(scored_skills, key=lambda x: x[0])[1]
```

**Benefits**: True autonomous learning capability, safer skill library (bad skills caught before production use), continuous improvement without manual intervention, and alignment with Voyager's lifelong learning principles [1].

**Effort**: High (5-7 weeks)
**Priority**: Medium-High

---

### 3.2. Event-Driven Architecture Improvements

#### Recommendation 4: Replace Polling with Kubernetes Watch Streams

**Problem**: Polling for Kubernetes events is inefficient, introduces latency, and wastes resources.

**Solution**: Use Kubernetes watch API to receive real-time event notifications. This is a standard pattern in Kubernetes operators and provides immediate responsiveness.

**Implementation**:
```python
from kubernetes import client, watch
import asyncio

class SentinelAgent:
    async def watch_events(self):
        v1 = client.CoreV1Api()
        w = watch.Watch()

        # Watch events across all namespaces
        for event in w.stream(
            v1.list_event_for_all_namespaces,
            timeout_seconds=0  # Infinite watch
        ):
            event_obj = event['object']
            event_type = event['type']  # ADDED, MODIFIED, DELETED

            if self._should_process(event_obj):
                await self._publish_to_bus(event_obj)

    def _should_process(self, event) -> bool:
        # Filter for relevant events
        return event.type in ['Warning', 'Error'] and \
               event.reason in self.monitored_reasons
```

**Error Handling**:
```python
async def watch_with_reconnect(self):
    while True:
        try:
            await self.watch_events()
        except Exception as e:
            logger.error(f"Watch stream failed: {e}")
            await asyncio.sleep(5)  # Backoff before reconnect
```

**Benefits**: Real-time event processing (no polling delay), reduced API server load, lower resource consumption, and immediate response to critical issues.

**Effort**: Low (1 week)
**Priority**: High

---

## 4. Proposed New Agents

### 4.1. WorldModelAgent

**Purpose**: Maintain a real-time, comprehensive model of the entire system state.

**Responsibilities**:
- Subscribe to all events on the Event Bus
- Build and maintain an in-memory graph of cluster resources
- Track agent activities and their effects on the system
- Answer queries about system state from other agents
- Detect anomalies by comparing current state to historical patterns

**Architecture**:
```python
import networkx as nx
from datetime import datetime

class WorldModelAgent:
    def __init__(self):
        self.graph = nx.DiGraph()
        self.state_history = []
        self.last_update = {}

    async def handle_event(self, event: Event):
        """Update graph based on event type"""
        if event.type == "pod_created":
            self.graph.add_node(
                event.pod_id,
                type="pod",
                namespace=event.namespace,
                created_at=datetime.now(),
                **event.metadata
            )
            # Add edge to parent deployment
            if event.deployment_id:
                self.graph.add_edge(event.deployment_id, event.pod_id)

        elif event.type == "pod_deleted":
            if event.pod_id in self.graph:
                self.graph.remove_node(event.pod_id)

        elif event.type == "agent_action":
            # Track which agent modified which resource
            self.graph.nodes[event.resource_id]['last_modified_by'] = event.agent_id
            self.graph.nodes[event.resource_id]['last_modified_at'] = datetime.now()

        # Store in history for temporal queries
        self.state_history.append({
            'timestamp': datetime.now(),
            'event': event,
            'graph_snapshot': self.graph.copy()
        })

    async def query_state(self, query: str) -> dict:
        """Answer questions about current state"""
        # Parse natural language query and return structured data
        # Examples:
        # "What pods are in namespace production?"
        # "Which agent last modified deployment api-server?"
        # "Show me all resources connected to pod xyz"
        pass

    def get_resource_lineage(self, resource_id: str) -> List[str]:
        """Get all ancestors of a resource"""
        return list(nx.ancestors(self.graph, resource_id))

    def get_affected_resources(self, resource_id: str) -> List[str]:
        """Get all descendants that would be affected by changes"""
        return list(nx.descendants(self.graph, resource_id))
```

**Query Interface**:
```python
# Other agents query WorldModel
world_model = A2AClient().connect("world_model")

# Get pod details
pod_info = await world_model.query({
    "type": "get_resource",
    "resource_type": "pod",
    "namespace": "production",
    "name": "api-server-abc123"
})

# Get modification history
history = await world_model.query({
    "type": "get_history",
    "resource_id": "deployment/api-server",
    "time_range": "last_24h"
})

# Find related resources
related = await world_model.query({
    "type": "get_related",
    "resource_id": "pod/api-server-abc123",
    "relationship": "all"
})
```

**Benefits**: Single source of truth for system state, simplifies other agents' logic (they query WorldModel instead of parsing events), enables powerful system-wide analysis, and provides foundation for predictive capabilities.

**Integration Points**:
- All agents query WorldModel for state information
- WorldModel publishes state change summaries periodically
- Metrics exported for state graph size, query latency, and update rate

**Effort**: Medium-High (4-5 weeks)
**Priority**: Medium

---

### 4.2. CostAndPerformanceAgent [Low Priority]

**Purpose**: Monitor and optimize resource consumption across the agent ecosystem.

**Responsibilities**:
- Track CPU, memory, GPU usage of all agents
- Monitor LLM token usage and costs per agent
- Measure latency for all agent operations
- Identify inefficient agents or skills
- Suggest optimizations
- Generate cost reports

**Key Metrics**:

| Metric | Description | Alert Threshold |
|--------|-------------|-----------------|
| `agent_cpu_usage` | CPU usage per agent | >80% for >5 min |
| `agent_memory_usage` | Memory usage per agent | >90% |
| `llm_tokens_per_operation` | Token usage per agent call | >10k tokens |
| `skill_execution_cost` | Estimated cost per skill | >$0.10 |
| `agent_latency_p99` | 99th percentile latency | >5 seconds |
| `mcp_tool_call_duration` | Time spent in MCP tools | >30 seconds |

**Implementation**:
```python
class CostAndPerformanceAgent:
    async def analyze_agent_efficiency(self, agent_id: str):
        metrics = await self.fetch_metrics(agent_id)

        # Analyze token usage
        if metrics.tokens_per_call > 10000:
            await self.suggest_optimization(
                agent_id,
                "High token usage detected. Consider using a smaller model or simplifying prompts."
            )

        # Analyze execution time
        if metrics.p99_latency > 5.0:
            await self.suggest_optimization(
                agent_id,
                "High latency detected. Consider caching frequent queries or optimizing tool calls."
            )

        # Analyze cost
        daily_cost = metrics.tokens_per_day * self.token_cost
        if daily_cost > 10.0:
            await self.publish_alert(
                f"Agent {agent_id} is costing ${daily_cost:.2f}/day"
            )

    async def generate_cost_report(self, time_range: str) -> CostReport:
        """Generate detailed cost breakdown"""
        agents = await self.get_all_agents()

        report = CostReport()
        for agent in agents:
            metrics = await self.fetch_metrics(agent.id, time_range)

            report.add_agent_cost(
                agent_id=agent.id,
                token_usage=metrics.total_tokens,
                estimated_cost=metrics.total_tokens * self.token_cost,
                skill_executions=metrics.skill_count,
                avg_latency=metrics.avg_latency
            )

        return report
```

**Cost Optimization Suggestions**:
```python
class OptimizationEngine:
    def suggest_optimizations(self, agent_metrics: AgentMetrics) -> List[Suggestion]:
        suggestions = []

        # Check for inefficient prompts
        if agent_metrics.prompt_length > 5000:
            suggestions.append(Suggestion(
                type="prompt_optimization",
                description="Prompt is very long. Consider removing examples or using RAG.",
                potential_savings="30-50% token reduction"
            ))

        # Check for redundant tool calls
        if agent_metrics.duplicate_tool_calls > 0.1:  # >10% duplicates
            suggestions.append(Suggestion(
                type="caching",
                description="Many duplicate tool calls detected. Implement caching.",
                potential_savings="20-40% latency reduction"
            ))

        # Check model selection
        if agent_metrics.task_complexity < 0.5 and agent_metrics.model == "gpt-4":
            suggestions.append(Suggestion(
                type="model_downgrade",
                description="Tasks are simple. Consider using gpt-4-mini.",
                potential_savings="60-80% cost reduction"
            ))

        return suggestions
```

**Benefits**: Visibility into operational costs, early detection of resource leaks or inefficiencies, data-driven optimization decisions, and cost control for production deployment.

**Effort**: Medium (3-4 weeks)
**Priority**: Medium

---

### 4.3. GitOpsAgent

**Purpose**: Fully automate the GitOps deployment pipeline.

**Responsibilities**:
- Listen for `agent:image_pushed` events
- Automatically update GitOps manifests with new image tags
- Create pull requests or direct commits to GitOps repo
- Verify Flux CD reconciliation success
- Rollback on deployment failures

**Current Manual Process** (from `.github/workflows/build.yml`):
```yaml
- name: Update deployment manifests
  run: |
    sed -i "s|registry.almckay.io/${name}:[^ ]*|registry.almckay.io/${name}:${TAG}|g" "$DEPLOY_FILE"
- name: Commit and push
  run: |
    git commit -m "chore(gitops): update agent images"
    git push
```

**Automated Process**:
```python
class GitOpsAgent:
    async def handle_image_pushed(self, event: ImagePushedEvent):
        """Handle new image push event"""
        logger.info(f"Processing image push for {event.agent_name}:{event.new_tag}")

        # Clone GitOps repo
        repo = await self.clone_gitops_repo()

        # Update manifest
        manifest_path = f"gitops/apps/ai-agents/{event.agent_name}/deployment.yaml"
        await self.update_image_tag(
            repo_path=repo.path,
            manifest_path=manifest_path,
            new_tag=event.new_tag
        )

        # Commit and push
        await repo.commit(
            message=f"chore: update {event.agent_name} to {event.new_tag}",
            author="GitOpsAgent <gitops@kubani.ai>"
        )
        await repo.push()

        # Verify deployment
        success = await self.wait_for_flux_reconciliation(
            agent_name=event.agent_name,
            expected_tag=event.new_tag,
            timeout=300
        )

        if not success:
            logger.error(f"Deployment failed for {event.agent_name}")
            await self.rollback(event.agent_name, event.previous_tag)
            await self.publish_alert(f"Deployment failed, rolled back to {event.previous_tag}")
        else:
            await self.publish_success(f"Successfully deployed {event.agent_name}:{event.new_tag}")

    async def wait_for_flux_reconciliation(
        self,
        agent_name: str,
        expected_tag: str,
        timeout: int
    ) -> bool:
        """Wait for Flux to reconcile and verify deployment"""
        start_time = time.time()

        while time.time() - start_time < timeout:
            # Check Flux kustomization status
            kustomization = await self.get_flux_kustomization("ai-agents")

            if kustomization.status == "Ready":
                # Verify actual deployment
                deployment = await self.get_deployment(agent_name)
                current_tag = deployment.spec.template.spec.containers[0].image.split(":")[-1]

                if current_tag == expected_tag:
                    return True

            await asyncio.sleep(5)

        return False
```

**Benefits**: Fully automated CI/CD pipeline, faster deployments, reduced human error, audit trail of all deployments, and automatic rollback on failures.

**Effort**: Low-Medium (2-3 weeks)
**Priority**: Medium

---

### 4.4. AnomalyDetectionAgent

**Purpose**: Proactively detect unusual patterns before they become critical issues.

**Responsibilities**:
- Analyze metrics and logs for anomalies
- Use statistical methods (z-score, moving averages) or ML models
- Detect unusual resource usage, abnormal error rates, unexpected traffic patterns
- Alert before issues escalate
- Learn normal behavior patterns over time

**Example Detections**:
- "Pod restart rate in namespace production is 3 standard deviations above normal"
- "Memory usage for deployment api-server has been steadily increasing for 6 hours (potential leak)"
- "API latency has doubled in the last 30 minutes"
- "Unusual number of failed authentication attempts detected"

**Implementation**:
```python
from sklearn.ensemble import IsolationForest
import numpy as np

class AnomalyDetectionAgent:
    def __init__(self):
        self.model = IsolationForest(contamination=0.1)
        self.baseline_data = []
        self.trained = False

    async def train_baseline(self, historical_metrics: List[Metric]):
        """Train on historical data to learn normal behavior"""
        features = self.extract_features(historical_metrics)
        self.model.fit(features)
        self.baseline_data = features
        self.trained = True

    async def analyze_metrics(self, current_metrics: List[Metric]):
        """Analyze current metrics for anomalies"""
        if not self.trained:
            logger.warning("Model not trained yet, skipping analysis")
            return

        features = self.extract_features(current_metrics)
        anomaly_scores = self.model.predict(features)

        for idx, score in enumerate(anomaly_scores):
            if score == -1:  # Anomaly detected
                metric = current_metrics[idx]
                await self.investigate_anomaly(metric)

    async def investigate_anomaly(self, metric: Metric):
        """Deep dive into detected anomaly"""
        # Calculate severity
        severity = self.calculate_severity(metric)

        # Get historical context
        historical = await self.get_historical_values(metric.name, lookback="7d")

        # Calculate statistical measures
        mean = np.mean(historical)
        std = np.std(historical)
        z_score = (metric.value - mean) / std

        # Publish alert
        await self.publish_alert(Alert(
            type="anomaly_detected",
            metric_name=metric.name,
            current_value=metric.value,
            expected_range=f"{mean - 2*std:.2f} - {mean + 2*std:.2f}",
            z_score=z_score,
            severity=severity,
            recommendation=self.get_recommendation(metric)
        ))

    def extract_features(self, metrics: List[Metric]) -> np.ndarray:
        """Extract features for ML model"""
        # Convert metrics to feature vectors
        # Features might include: value, rate of change, variance, etc.
        features = []
        for metric in metrics:
            features.append([
                metric.value,
                metric.rate_of_change,
                metric.variance,
                metric.percentile_rank
            ])
        return np.array(features)
```

**Statistical Methods**:
```python
class StatisticalAnomalyDetector:
    def detect_using_zscore(self, values: List[float], threshold: float = 3.0) -> List[int]:
        """Detect anomalies using z-score method"""
        mean = np.mean(values)
        std = np.std(values)

        anomalies = []
        for idx, value in enumerate(values):
            z_score = abs((value - mean) / std)
            if z_score > threshold:
                anomalies.append(idx)

        return anomalies

    def detect_using_moving_average(
        self,
        values: List[float],
        window: int = 10,
        threshold: float = 2.0
    ) -> List[int]:
        """Detect anomalies using moving average"""
        moving_avg = np.convolve(values, np.ones(window)/window, mode='valid')

        anomalies = []
        for idx in range(len(moving_avg)):
            if abs(values[idx + window - 1] - moving_avg[idx]) > threshold * np.std(values):
                anomalies.append(idx + window - 1)

        return anomalies
```

**Benefits**: Proactive issue detection, reduced MTTR (Mean Time To Resolution), learns normal behavior patterns, reduces alert fatigue (only alerts on true anomalies), and prevents small issues from becoming outages.

**Effort**: High (6-8 weeks, includes ML model training and validation)
**Priority**: Low-Medium

---

## 5. Code Organization Improvements

### 5.1. Consolidate Agent Entrypoints

**Problem**: Each agent has its own `worker.py` with duplicated Temporal setup code, leading to maintenance burden and inconsistency.

**Current State** (`agents/k8s-monitor/src/k8s_monitor/worker.py`):
```python
async def main():
    # Duplicated in every agent
    client = await Client.connect("temporal:7233")

    worker = Worker(
        client,
        task_queue="k8s-monitor",
        workflows=[ClusterHealthCheckWorkflow],
        activities=[scan_cluster, diagnose_pod, remediate_issue],
    )

    await worker.run()
```

**Proposed Solution**: Generic `AgentWorker` in `core_agents`:

```python
# agents/core/src/core_agents/worker.py
from temporalio.client import Client
from temporalio.worker import Worker
from typing import List, Type, Callable, Optional

class AgentWorker:
    """Generic worker for all agents"""

    def __init__(
        self,
        agent_name: str,
        workflows: List[Type],
        activities: List[Callable],
        temporal_url: str = "temporal:7233",
        hooks_factory: Optional[Callable] = None,
    ):
        self.agent_name = agent_name
        self.workflows = workflows
        self.activities = activities
        self.temporal_url = temporal_url
        self.hooks_factory = hooks_factory or default_hooks_factory

    async def run(self):
        """Start the worker"""
        # Connect to Temporal
        client = await Client.connect(self.temporal_url)

        # Create worker with standard configuration
        worker = Worker(
            client,
            task_queue=self.agent_name,
            workflows=self.workflows,
            activities=self.activities,
            max_concurrent_activities=10,
            max_concurrent_workflows=5,
        )

        # Attach hooks for observability
        hooks = self.hooks_factory(self.agent_name)

        logger.info(f"Starting worker for {self.agent_name}")
        await worker.run()
```

**Simplified Agent Worker** (`agents/k8s-monitor/src/k8s_monitor/worker.py`):
```python
from core_agents import AgentWorker
from k8s_monitor.workflows import ClusterHealthCheckWorkflow, RemediationWorkflow
from k8s_monitor.activities import scan_cluster, diagnose_pod, remediate_issue

async def main():
    worker = AgentWorker(
        agent_name="k8s-monitor",
        workflows=[ClusterHealthCheckWorkflow, RemediationWorkflow],
        activities=[scan_cluster, diagnose_pod, remediate_issue],
    )
    await worker.run()

if __name__ == "__main__":
    asyncio.run(main())
```

**Benefits**: Reduces boilerplate by ~50 lines per agent, centralizes worker configuration, easier to add new agents, consistent worker behavior across all agents, and easier to add global features (e.g., health checks, graceful shutdown).

**Effort**: Low (1 week)
**Priority**: Medium

---

### 5.2. Standardize Agent Creation with AgentFactory

**Problem**: Agent creation logic is spread across multiple files with inconsistent patterns, making it hard to maintain and extend.

**Proposed Solution**: Unified `AgentFactory` in `core_agents`:

```python
# agents/core/src/core_agents/factory.py
from strands import Agent
from strands.multiagent import Swarm
from typing import List, Callable, Optional
from dataclasses import dataclass

@dataclass
class ModelConfig:
    base_url: str = "http://llm-api.vllm.svc.cluster.local:8000/v1"
    model_id: str = "Qwen/Qwen3-14B-FP8"
    temperature: float = 0.7
    max_tokens: int = 4096

@dataclass
class SwarmConfig:
    max_handoffs: int = 10
    max_iterations: int = 20
    execution_timeout: float = 300.0
    node_timeout: float = 60.0

class AgentFactory:
    """Factory for creating standardized agents"""

    @staticmethod
    def create_single_agent(
        name: str,
        description: str,
        system_prompt: str,
        tools: List[Callable],
        model_config: Optional[ModelConfig] = None,
    ) -> Agent:
        """Create a single agent with standard configuration"""
        model_config = model_config or ModelConfig()

        # Create model
        model = create_model(
            base_url=model_config.base_url,
            model_id=model_config.model_id,
            temperature=model_config.temperature,
            max_tokens=model_config.max_tokens,
        )

        # Create standard hooks for observability
        hooks = create_standard_hooks(name)

        # Create agent
        return Agent(
            name=name,
            description=description,
            model=model,
            tools=tools,
            system_prompt=system_prompt,
            hooks=hooks,
        )

    @staticmethod
    def create_swarm(
        name: str,
        agents: List[Agent],
        entry_point: Agent,
        config: Optional[SwarmConfig] = None,
    ) -> Swarm:
        """Create a swarm with standard configuration"""
        config = config or SwarmConfig()

        return Swarm(
            agents,
            entry_point=entry_point,
            max_handoffs=config.max_handoffs,
            max_iterations=config.max_iterations,
            execution_timeout=config.execution_timeout,
            node_timeout=config.node_timeout,
        )

def create_standard_hooks(agent_name: str):
    """Create standard hooks for logging, metrics, and tracing"""
    return {
        'on_start': lambda ctx: log_agent_start(agent_name, ctx),
        'on_complete': lambda ctx: log_agent_complete(agent_name, ctx),
        'on_error': lambda ctx, error: log_agent_error(agent_name, ctx, error),
        'on_tool_call': lambda tool, args: track_tool_call(agent_name, tool, args),
    }
```

**Usage**:
```python
# agents/k8s-monitor/src/k8s_monitor/agents/sentinel.py
from core_agents import AgentFactory

class SentinelAgent:
    def __init__(self):
        self.agent = AgentFactory.create_single_agent(
            name="sentinel",
            description="Monitors Kubernetes events and detects issues",
            system_prompt=SENTINEL_PROMPT,
            tools=[watch_events, publish_event],
        )
```

**Benefits**: Consistent agent creation across the codebase, automatic attachment of observability hooks, easier to modify agent behavior globally, decouples agent logic from `strands` library details, and simplifies testing (can inject mock models/hooks).

**Effort**: Low-Medium (1-2 weeks)
**Priority**: Medium

---

### 5.3. Introduce Centralized Configuration Management

**Problem**: Configuration is scattered across environment variables, hardcoded values, and YAML files, making it difficult to manage and test.

**Proposed Solution**: Centralized configuration using Pydantic settings:

```python
# agents/core/src/core_agents/config.py
from pydantic_settings import BaseSettings
from typing import Optional

class CoreConfig(BaseSettings):
    """Core configuration for all agents"""

    # LLM Configuration
    vllm_api_url: str = "http://llm-api.vllm.svc.cluster.local:8000/v1"
    default_model_id: str = "Qwen/Qwen3-14B-FP8"
    model_temperature: float = 0.7
    model_max_tokens: int = 4096

    # Event Bus
    redis_url: str = "redis://redis:6379"
    event_stream_name: str = "kubani:events"
    event_retention_hours: int = 168  # 7 days

    # Skill Library
    qdrant_url: str = "http://qdrant:6333"
    skill_collection_name: str = "skills"
    skill_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # Approval System
    discord_webhook_url: Optional[str] = None
    approval_timeout_seconds: int = 3600  # 1 hour

    # Observability
    prometheus_port: int = 9090
    log_level: str = "INFO"
    enable_tracing: bool = True

    # Temporal
    temporal_url: str = "temporal:7233"
    temporal_namespace: str = "default"

    class Config:
        env_prefix = "KUBANI_"
        env_file = ".env"
        env_file_encoding = "utf-8"

# Singleton instance
_config: Optional[CoreConfig] = None

def get_config() -> CoreConfig:
    """Get the global configuration instance"""
    global _config
    if _config is None:
        _config = CoreConfig()
    return _config
```

**Usage**:
```python
from core_agents.config import get_config

config = get_config()

# Use configuration
model = create_model(
    base_url=config.vllm_api_url,
    model_id=config.default_model_id,
    temperature=config.model_temperature,
)

redis_client = Redis.from_url(config.redis_url)
```

**Environment-Specific Configs**:
```bash
# .env.development
KUBANI_LOG_LEVEL=DEBUG
KUBANI_VLLM_API_URL=http://localhost:8000/v1
KUBANI_REDIS_URL=redis://localhost:6379

# .env.production
KUBANI_LOG_LEVEL=INFO
KUBANI_VLLM_API_URL=http://llm-api.vllm.svc.cluster.local:8000/v1
KUBANI_REDIS_URL=redis://redis.kubani-system:6379
KUBANI_ENABLE_TRACING=true
```

**Testing**:
```python
# tests/conftest.py
import pytest
from core_agents.config import CoreConfig

@pytest.fixture
def test_config():
    """Override config for tests"""
    return CoreConfig(
        redis_url="redis://localhost:6379/1",  # Use different DB
        qdrant_url="http://localhost:6333",
        log_level="DEBUG",
    )
```

**Benefits**: Single source of truth for configuration, type-safe configuration with validation, easy to override for testing, environment-specific configs (dev/staging/prod), automatic documentation of all configuration options, and validation errors caught at startup.

**Effort**: Low (1 week)
**Priority**: Low-Medium

---

## 6. Testing and Release Process Enhancements

### 6.1. Implement End-to-End Integration Testing

**Problem**: Current tests focus on unit testing individual agents. There are no tests for agent-to-agent interactions or complete workflows, which is a significant gap for a distributed system.

**Proposed Solution**: E2E test suite that runs in a real Kubernetes cluster using `kind` (Kubernetes in Docker).

**Test Infrastructure Setup**:
```bash
# tests/e2e/setup_cluster.sh
#!/bin/bash
set -euo pipefail

# Create kind cluster
kind create cluster --name kubani-e2e --config tests/e2e/kind-config.yaml

# Deploy dependencies
kubectl apply -f tests/e2e/manifests/redis.yaml
kubectl apply -f tests/e2e/manifests/qdrant.yaml
kubectl apply -f tests/e2e/manifests/temporal.yaml

# Wait for dependencies
kubectl wait --for=condition=ready pod -l app=redis -n kubani-system --timeout=120s

# Deploy agents
kubectl apply -k gitops/apps/ai-agents/

# Wait for agents
kubectl wait --for=condition=ready pod -l app.kubernetes.io/part-of=kubani -n ai-agents --timeout=300s
```

**Test Scenario Example**:
```python
# tests/e2e/test_healing_workflow.py
import pytest
import asyncio
from kubernetes import client, config
from tests.utils import wait_for_event, capture_webhook, wait_for_pod_status

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_pod_crashloop_detection_and_healing():
    """Test complete workflow: detection → diagnosis → healing → verification"""

    # 1. Setup: Deploy a pod that will crash
    config.load_kube_config()
    v1 = client.CoreV1Api()

    pod_manifest = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": "crashloop-test",
            "namespace": "kubani-test"
        },
        "spec": {
            "containers": [{
                "name": "crasher",
                "image": "busybox",
                "command": ["sh", "-c", "exit 1"]  # Will crash immediately
            }],
            "restartPolicy": "Always"
        }
    }

    pod = v1.create_namespaced_pod(
        namespace="kubani-test",
        body=pod_manifest
    )

    # 2. Wait for SentinelAgent to detect the CrashLoopBackOff
    event = await wait_for_event(
        event_type="K8S_ISSUE_DETECTED",
        filters={"resource_name": "crashloop-test"},
        timeout=60
    )

    assert event.resource_type == "Pod"
    assert event.reason == "CrashLoopBackOff"
    assert event.namespace == "kubani-test"

    # 3. Wait for HealerAgent to start processing
    healing_event = await wait_for_event(
        event_type="HEALING_STARTED",
        filters={"resource_name": "crashloop-test"},
        timeout=120
    )

    assert healing_event.skill_name is not None

    # 4. Verify correct MCP tool was called
    webhook_call = await capture_webhook(
        server="kubernetes",
        tool="kubectl_delete_pod",
        timeout=60
    )

    assert webhook_call.params["pod_name"] == "crashloop-test"
    assert webhook_call.params["namespace"] == "kubani-test"

    # 5. Verify pod was restarted
    await wait_for_pod_status(
        name="crashloop-test",
        namespace="kubani-test",
        expected_status="Running",
        timeout=180
    )

    # 6. Verify healing completion event
    success_event = await wait_for_event(
        event_type="HEALING_COMPLETED",
        filters={"resource_name": "crashloop-test"},
        timeout=60
    )

    assert success_event.success == True
    assert success_event.verification_passed == True

    # 7. Cleanup
    v1.delete_namespaced_pod(
        name="crashloop-test",
        namespace="kubani-test"
    )
```

**Test Utilities**:
```python
# tests/utils.py
import asyncio
from typing import Optional, Dict, Any
from dataclasses import dataclass

@dataclass
class Event:
    type: str
    data: Dict[str, Any]
    timestamp: float

class EventCapture:
    """Capture events from the Event Bus for testing"""

    def __init__(self, redis_url: str):
        self.redis = Redis.from_url(redis_url)
        self.captured_events = []

    async def start_capture(self):
        """Start capturing events"""
        async for message in self.redis.xread({"kubani:events": "$"}, block=0):
            event = Event(
                type=message['type'],
                data=message['data'],
                timestamp=message['timestamp']
            )
            self.captured_events.append(event)

async def wait_for_event(
    event_type: str,
    filters: Optional[Dict[str, Any]] = None,
    timeout: int = 30
) -> Event:
    """Wait for a specific event to appear on the bus"""
    capture = EventCapture(os.getenv("REDIS_URL"))

    start_time = time.time()
    while time.time() - start_time < timeout:
        for event in capture.captured_events:
            if event.type == event_type:
                if filters is None or all(
                    event.data.get(k) == v for k, v in filters.items()
                ):
                    return event

        await asyncio.sleep(0.5)

    raise TimeoutError(f"Event {event_type} not found within {timeout}s")
```

**Additional Test Scenarios**:
```python
@pytest.mark.e2e
async def test_skill_library_retrieval():
    """Test that HealerAgent correctly retrieves skills from library"""
    pass

@pytest.mark.e2e
async def test_approval_workflow():
    """Test human-in-the-loop approval via Discord"""
    pass

@pytest.mark.e2e
async def test_multi_agent_coordination():
    """Test hierarchical agent handoffs"""
    pass

@pytest.mark.e2e
async def test_event_bus_failure_recovery():
    """Test agents recover gracefully from Event Bus failure"""
    pass
```

**CI Integration**:
```yaml
# .github/workflows/e2e-tests.yml
name: E2E Tests

on:
  pull_request:
  push:
    branches: [main]

jobs:
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup kind
        uses: helm/kind-action@v1

      - name: Setup test cluster
        run: ./tests/e2e/setup_cluster.sh

      - name: Run E2E tests
        run: pytest tests/e2e/ -v --tb=short

      - name: Collect logs on failure
        if: failure()
        run: |
          kubectl logs -n ai-agents -l app.kubernetes.io/part-of=kubani > agent-logs.txt
          kubectl get events -A > events.txt

      - name: Upload logs
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: e2e-logs
          path: |
            agent-logs.txt
            events.txt
```

**Benefits**: Catches integration bugs before production, validates entire workflow end-to-end, increases confidence in releases, documents expected system behavior, and provides regression protection.

**Effort**: Medium-High (4-5 weeks)
**Priority**: High

---

### 6.2. Add Chaos Engineering Tests

**Problem**: System behavior under failure conditions is completely untested, which is risky for a production system.

**Proposed Solution**: Introduce chaos tests that deliberately inject failures using `chaos-mesh`.

**Chaos Mesh Installation**:
```bash
# Install chaos-mesh in test cluster
kubectl create ns chaos-mesh
helm install chaos-mesh chaos-mesh/chaos-mesh -n chaos-mesh
```

**Test Scenarios**:

**1. Event Bus Failure**:
```yaml
# tests/chaos/redis_failure.yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
metadata:
  name: redis-failure
  namespace: chaos-mesh
spec:
  action: pod-kill
  mode: one
  selector:
    namespaces:
      - kubani-system
    labelSelectors:
      app: redis
  duration: "30s"
```

```python
@pytest.mark.chaos
async def test_event_bus_failure_recovery():
    """Test agents handle Redis failure gracefully"""

    # Verify system is healthy
    assert await check_all_agents_healthy()

    # Inject chaos: kill Redis
    await apply_chaos_experiment("redis_failure.yaml")

    # Verify agents don't crash
    await asyncio.sleep(10)
    pods = await get_agent_pods()
    assert all(pod.status.phase == "Running" for pod in pods)

    # Verify agents log errors appropriately
    logs = await get_agent_logs()
    assert "Failed to connect to Redis" in logs
    assert "Retrying connection" in logs

    # Wait for chaos to end
    await wait_for_chaos_completion("redis-failure")

    # Verify system recovers
    await asyncio.sleep(10)
    assert await check_all_agents_healthy()

    # Verify events are processed again
    test_event = create_test_event()
    await publish_event(test_event)

    result = await wait_for_event("HEALING_STARTED", timeout=60)
    assert result is not None
```

**2. Network Partition**:
```yaml
# tests/chaos/network_partition.yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: agent-partition
  namespace: chaos-mesh
spec:
  action: partition
  mode: all
  selector:
    namespaces:
      - ai-agents
    labelSelectors:
      app: healer
  direction: both
  duration: "60s"
```

**3. Resource Exhaustion**:
```yaml
# tests/chaos/memory_stress.yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: StressChaos
metadata:
  name: memory-stress
  namespace: chaos-mesh
spec:
  mode: one
  selector:
    namespaces:
      - ai-agents
    labelSelectors:
      app: sentinel
  stressors:
    memory:
      workers: 4
      size: "512MB"
  duration: "120s"
```

**4. LLM API Failure**:
```python
@pytest.mark.chaos
async def test_llm_api_timeout():
    """Test agents handle LLM API timeouts"""

    # Configure mock LLM to be slow
    await configure_mock_llm(latency="10s")

    # Trigger agent action
    event = create_test_event()
    await publish_event(event)

    # Verify timeout is handled
    result = await wait_for_event("HEALING_FAILED", timeout=30)
    assert result.error_type == "LLMTimeout"

    # Verify retry mechanism
    result = await wait_for_event("HEALING_RETRY", timeout=60)
    assert result is not None

    # Reset mock LLM
    await configure_mock_llm(latency="100ms")

    # Verify eventual success
    result = await wait_for_event("HEALING_COMPLETED", timeout=120)
    assert result.success == True
```

**Chaos Test Suite**:
```python
# tests/chaos/test_resilience.py
import pytest

@pytest.mark.chaos
class TestSystemResilience:

    async def test_redis_failure(self):
        """Event Bus failure and recovery"""
        pass

    async def test_qdrant_failure(self):
        """Skill Library unavailable"""
        pass

    async def test_network_partition(self):
        """Agent isolation"""
        pass

    async def test_cpu_exhaustion(self):
        """High CPU load"""
        pass

    async def test_memory_exhaustion(self):
        """Memory pressure"""
        pass

    async def test_llm_api_failure(self):
        """LLM API unavailable"""
        pass

    async def test_kubernetes_api_failure(self):
        """K8s API server issues"""
        pass

    async def test_cascading_failures(self):
        """Multiple simultaneous failures"""
        pass
```

**Benefits**: Validates failure handling, identifies single points of failure, improves system resilience, builds confidence in production reliability, and documents failure modes.

**Effort**: Medium (3-4 weeks)
**Priority**: Medium

---

### 6.3. Automate Version Bumping and Changelog Generation

**Problem**: Versioning and changelog creation are manual processes prone to human error and inconsistency.

**Proposed Solution**: Integrate `semantic-release` for automated versioning based on conventional commits.

**Step 1: Enforce Conventional Commits**:
```json
// .commitlintrc.json
{
  "extends": ["@commitlintrc/config-conventional"],
  "rules": {
    "type-enum": [2, "always", [
      "feat",     // New feature
      "fix",      // Bug fix
      "docs",     // Documentation only
      "style",    // Formatting, missing semi colons, etc
      "refactor", // Code change that neither fixes a bug nor adds a feature
      "perf",     // Performance improvement
      "test",     // Adding missing tests
      "chore",    // Maintain
      "ci"        // CI configuration
    ]],
    "scope-enum": [2, "always", [
      "core",
      "k8s-monitor",
      "news-monitor",
      "sentinel",
      "healer",
      "explorer",
      "gitops",
      "ci"
    ]]
  }
}
```

**Step 2: Configure semantic-release**:
```json
// .releaserc.json
{
  "branches": ["main"],
  "plugins": [
    ["@semantic-release/commit-analyzer", {
      "preset": "conventionalcommits",
      "releaseRules": [
        {"type": "feat", "release": "minor"},
        {"type": "fix", "release": "patch"},
        {"type": "perf", "release": "patch"},
        {"type": "refactor", "release": "patch"},
        {"breaking": true, "release": "major"}
      ]
    }],
    ["@semantic-release/release-notes-generator", {
      "preset": "conventionalcommits"
    }],
    ["@semantic-release/changelog", {
      "changelogFile": "CHANGELOG.md"
    }],
    ["@semantic-release/github", {
      "assets": [
        {"path": "agents/core/dist/*.whl", "label": "Core Agents Wheel"}
      ]
    }],
    ["@semantic-release/git", {
      "assets": ["CHANGELOG.md", "package.json"],
      "message": "chore(release): ${nextRelease.version} [skip ci]\n\n${nextRelease.notes}"
    }]
  ]
}
```

**Step 3: Update CI/CD**:
```yaml
# .github/workflows/release.yml
name: Release
on:
  push:
    branches: [main]

jobs:
  release:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      issues: write
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Need full history for semantic-release

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Install dependencies
        run: npm install -g semantic-release @semantic-release/changelog @semantic-release/git

      - name: Run semantic-release
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: npx semantic-release
```

**Commit Message Examples**:

```bash
# Minor version bump (0.1.0 → 0.2.0)
git commit -m "feat(k8s-monitor): add node diagnostician agent

Implements hierarchical agent structure with specialized node diagnostics.

Closes #123"

# Patch version bump (0.1.0 → 0.1.1)
git commit -m "fix(healer): correct skill confidence scoring

The confidence score was not being weighted properly, leading to
suboptimal skill selection.

Fixes #124"

# Major version bump (0.1.0 → 1.0.0)
git commit -m "feat(core)!: breaking change to Event Bus API

BREAKING CHANGE: Event Bus now requires event_version field in all events.
This enables better backward compatibility in the future.

Migration guide:
- Add 'event_version': '1.0' to all event publications
- Update event consumers to handle version field

Closes #125"

# No release (chore)
git commit -m "chore(ci): update GitHub Actions versions"
```

**Generated Changelog**:
```markdown
# Changelog

## [1.0.0] - 2026-01-15

### ⚠ BREAKING CHANGES

* **core**: Event Bus now requires event_version field in all events

### Features

* **k8s-monitor**: add node diagnostician agent ([#123](https://github.com/X-McKay/kubani/issues/123)) ([abc1234](https://github.com/X-McKay/kubani/commit/abc1234))
* **core**: breaking change to Event Bus API ([#125](https://github.com/X-McKay/kubani/issues/125)) ([def5678](https://github.com/X-McKay/kubani/commit/def5678))

### Bug Fixes

* **healer**: correct skill confidence scoring ([#124](https://github.com/X-McKay/kubani/issues/124)) ([ghi9012](https://github.com/X-McKay/kubani/commit/ghi9012))

## [0.1.1] - 2026-01-10

### Bug Fixes

* **sentinel**: fix polling interval configuration ([abc1234](https://github.com/X-McKay/kubani/commit/abc1234))

## [0.1.0] - 2026-01-05

### Features

* **core**: initial federated agent architecture ([abc1234](https://github.com/X-McKay/kubani/commit/abc1234))
* **k8s-monitor**: implement sentinel and healer agents ([def5678](https://github.com/X-McKay/kubani/commit/def5678))
```

**Pre-commit Hook**:
```bash
# .husky/commit-msg
#!/bin/sh
. "$(dirname "$0")/_/husky.sh"

npx --no-install commitlint --edit "$1"
```

**Benefits**: Consistent versioning across all agents, automatic changelog generation, enforced commit message standards, clear communication of changes to users, automated release notes, and reduced manual work.

**Effort**: Low (1 week)
**Priority**: Low-Medium

---

## 7. Implementation Roadmap

To maximize impact while managing complexity, the recommendations should be implemented in phases. This roadmap prioritizes high-impact, foundational improvements first.

### Phase 1: Foundation (Weeks 1-4)

**Goal**: Address critical architectural issues and improve observability.

| Task | Priority | Effort | Dependencies | Owner |
|------|----------|--------|--------------|-------|
| Replace polling with Kubernetes watch | High | 1 week | None | Backend |
| Implement A2A communication framework | High | 2-3 weeks | None | Backend |
| Add E2E integration tests | High | 4-5 weeks | Test infrastructure | QA/Backend |
| Consolidate agent entrypoints | Medium | 1 week | None | Backend |

**Deliverables**:
- Real-time event processing (no polling delay)
- Direct agent communication capability
- E2E test suite with 5+ scenarios covering critical workflows
- Simplified agent worker code (50% less boilerplate)

**Success Metrics**:
- Event detection latency < 1 second (vs. current 30 seconds)
- A2A communication latency < 100ms
- E2E test coverage for all critical workflows
- All agents migrated to new worker pattern

---

### Phase 2: Intelligence (Weeks 5-10)

**Goal**: Enhance agent autonomy and learning capabilities.

| Task | Priority | Effort | Dependencies | Owner |
|------|----------|--------|--------------|-------|
| Implement hierarchical agent structure | High | 4-6 weeks | A2A communication | Backend |
| Build automated skill validation | Medium-High | 5-7 weeks | Test infrastructure | Backend/ML |
| Create WorldModelAgent | Medium | 4-5 weeks | A2A communication | Backend |
| Add AgentFactory standardization | Medium | 1-2 weeks | None | Backend |

**Deliverables**:
- Refactored k8s-monitor with 3-level hierarchy
- Sandbox skill testing environment
- WorldModelAgent in production
- Standardized agent creation across all agents

**Success Metrics**:
- 50% reduction in agent prompt complexity
- Automated skill validation with 90%+ accuracy
- WorldModel query latency < 50ms
- All new agents use AgentFactory

---

### Phase 3: Operations (Weeks 11-14)

**Goal**: Improve operational efficiency and cost management.

| Task | Priority | Effort | Dependencies | Owner |
|------|----------|--------|--------------|-------|
| Develop CostAndPerformanceAgent | Medium | 3-4 weeks | WorldModel | Backend |
| Create GitOpsAgent | Medium | 2-3 weeks | A2A communication | DevOps |
| Implement chaos engineering tests | Medium | 3-4 weeks | E2E tests | QA |
| Add semantic versioning automation | Low-Medium | 1 week | None | DevOps |

**Deliverables**:
- Cost monitoring dashboard with per-agent breakdown
- Fully automated GitOps pipeline
- Chaos test suite with 8+ failure scenarios
- Automated versioning and changelog generation

**Success Metrics**:
- Cost visibility for all agents
- Zero manual steps in deployment pipeline
- 100% chaos test pass rate
- Automated releases on every merge to main

---

### Phase 4: Advanced Features (Weeks 15+)

**Goal**: Add predictive and proactive capabilities.

| Task | Priority | Effort | Dependencies | Owner |
|------|----------|--------|--------------|-------|
| Build AnomalyDetectionAgent | Low-Medium | 6-8 weeks | WorldModel, historical data | ML/Backend |
| Implement skill composition metrics | Low | 2-3 weeks | Skill validation | Backend |
| Add predictive scaling | Low | 4-6 weeks | AnomalyDetection | ML/Backend |
| Create agent performance optimizer | Low | 3-4 weeks | CostAndPerformance | Backend |

**Deliverables**:
- Proactive anomaly detection with ML models
- Skill composition analytics and recommendations
- Predictive resource scaling based on patterns
- Automated agent optimization suggestions

**Success Metrics**:
- 50% reduction in MTTR through proactive detection
- Skill composition success rate > 80%
- 30% reduction in resource waste through predictive scaling
- 20% cost reduction through automated optimization

---

### Parallel Tracks

Some tasks can be worked on in parallel across phases:

**Documentation Track** (Ongoing):
- Update architecture documentation as changes are made
- Create runbooks for new agents
- Document failure modes and recovery procedures
- Create video tutorials for common tasks

**Testing Track** (Ongoing):
- Increase unit test coverage to 80%+
- Add integration tests for each new feature
- Maintain chaos test suite
- Performance benchmarking

**Observability Track** (Ongoing):
- Expand Prometheus metrics
- Create Grafana dashboards for new agents
- Implement distributed tracing
- Set up alerting rules

---

## 8. Conclusion

The Kubani federated agent architecture represents a significant achievement in autonomous systems design. The project demonstrates a strong understanding of modern agent patterns, production-grade infrastructure practices, and the importance of observability and safety mechanisms like human-in-the-loop approvals.

### Key Strengths

The architecture's greatest strengths lie in its **modular design**, **"Skills as Knowledge" paradigm**, and **research-informed approach**. The separation between core reusable components and domain-specific agents creates a scalable foundation. The decision to treat skills as declarative knowledge referencing MCP tools rather than embedded code is particularly innovative and positions the system well for long-term maintainability and evolution.

### Critical Improvements

The most impactful improvements would be:

1. **Evolving from pure orchestration to a hybrid coordination model** to reduce latency and improve resilience
2. **Implementing automated skill validation** to enable true autonomous learning
3. **Adopting a hierarchical agent structure** to manage complexity as the system grows
4. **Strengthening end-to-end testing** to ensure reliability in production

### Path Forward

By following the phased implementation roadmap outlined in this document, the Kubani project can evolve from a well-designed automation tool into a truly intelligent, self-improving autonomous operations platform. The recommendations balance ambition with pragmatism, focusing first on foundational improvements that enable more advanced capabilities later.

The vision of a system that can autonomously learn new skills, adapt to changing conditions, and proactively prevent issues before they impact users is within reach. With the strong foundation already in place, the path to achieving this vision is clear.

---

## 9. References

[1] Wang, G., Xie, Y., Jiang, Y., Mandlekar, A., Xiao, C., Zhu, Y., Fan, L., & Anandkumar, A. (2023). *Voyager: An Open-Ended Embodied Agent with Large Language Models*. arXiv. https://voyager.minedojo.org/

[2] Maxim AI. (2025). *Building Production-Ready Multi-Agent Systems: Architecture Patterns and Operational Best Practices*. https://www.getmaxim.ai/articles/best-practices-for-building-production-ready-multi-agent-systems/

[3] Google Developers Blog. (2025). *Developer's guide to multi-agent patterns in ADK*. https://developers.googleblog.com/developers-guide-to-multi-agent-patterns-in-adk/

[4] Anthropic. (2025). *How we built our multi-agent research system*. https://www.anthropic.com/engineering/multi-agent-research-system

[5] Galileo AI. (2025). *Architectures for Multi-Agent Systems*. https://galileo.ai/blog/architectures-for-multi-agent-systems

---

**Document Version**: 1.0
**Last Updated**: January 6, 2026
**Next Review**: February 6, 2026

---

*This review was prepared by Manus AI based on analysis of the kubani repository's feature/federated-agent-architecture branch and research into multi-agent systems best practices.*
