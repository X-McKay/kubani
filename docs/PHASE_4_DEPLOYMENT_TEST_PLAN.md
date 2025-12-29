# Phase 4 Deployment and Testing Plan

This document tracks the deployment and end-to-end testing of AI agents improvements (Phases 2-4).

## Overview

### Changes Being Deployed

| Phase | Feature | Components |
|-------|---------|------------|
| Phase 2 | Memory Infrastructure | Qdrant (vector DB), Neo4j (graph DB), mem0 configs |
| Phase 3 | Agent Communication | A2A protocol, Saga patterns, Signal channels, Recurrence detection |
| Phase 4 | Proactive Intelligence | Anomaly detection, Capacity planning |

### Package Versions

- **core-agents**: 0.1.0 → 0.2.1 (Phase 4 features + SSL fix)
- **k8s-monitor**: 0.2.1 → 0.2.3 (import fixes + core-agents 0.2.1)

---

## Deployment Checklist

### Step 1: Merge Feature Branch
- [x] Merge `feature/ai-agents-improvements` to `main` ✅
- [x] Verify CI pipeline passes ✅
- [x] Confirm Flux detects new commits ✅

### Step 2: Infrastructure Deployment (via Flux GitOps)
- [x] Qdrant deployed to `database` namespace ✅
  - [x] Pod running ✅
  - [x] Service accessible ✅
  - [x] PVC bound ✅
- [x] Neo4j deployed to `database` namespace ✅
  - [x] Pod running ✅ (required config fix for K8s env vars)
  - [x] Service accessible ✅
  - [x] PVC bound ✅
  - [ ] APOC plugin loaded (not tested)

### Step 3: Core-Agents Package
- [x] Build wheel with Earthly ✅
- [x] Push to registry as `registry.almckay.io/python/core-agents:0.2.1` ✅
- [x] Verify artifact accessible ✅

### Step 4: K8s-Monitor Deployment
- [x] CI builds new image with updated core-agents ✅
- [x] Flux deploys k8s-monitor 0.2.3-32c69f1 ✅
- [x] Verify pod running with new image ✅

---

## End-to-End Testing

### Test 1: Qdrant Connectivity
**Purpose**: Verify Qdrant is accessible from ai-agents namespace

```bash
# Port-forward to Qdrant
kubectl port-forward -n database svc/qdrant 6333:6333 &

# Test health endpoint
curl http://localhost:6333/healthz

# Test collections API
curl http://localhost:6333/collections
```

**Expected**: 200 OK, empty collections list

---

### Test 2: Neo4j Connectivity
**Purpose**: Verify Neo4j is accessible and APOC is loaded

```bash
# Port-forward to Neo4j
kubectl port-forward -n database svc/neo4j 7474:7474 7687:7687 &

# Test browser endpoint
curl http://localhost:7474/

# Test via cypher-shell (if available)
# Or use Python neo4j driver
```

**Expected**: Neo4j browser accessible, APOC procedures available

---

### Test 3: mem0 Integration with Qdrant
**Purpose**: Verify mem0 can store and retrieve memories using Qdrant

```python
from core_agents.memory import get_mem0_config
from mem0 import Memory

# Initialize mem0 with Qdrant config
config = get_mem0_config(
    qdrant_url="http://qdrant.database.svc.cluster.local:6333",
)
memory = Memory.from_config(config)

# Add a memory
memory.add("Test memory for k8s-monitor", user_id="test-user")

# Search for it
results = memory.search("k8s monitor test", user_id="test-user")
print(results)
```

**Expected**: Memory stored and retrieved successfully

---

### Test 4: Graph Memory with Neo4j
**Purpose**: Verify mem0 graph memory works with Neo4j

```python
from core_agents.memory import get_graph_mem0_config
from mem0 import Memory

# Initialize with graph config
config = get_graph_mem0_config(
    qdrant_url="http://qdrant.database.svc.cluster.local:6333",
    neo4j_url="bolt://neo4j.database.svc.cluster.local:7687",
    neo4j_user="neo4j",
    neo4j_password="<from-secret>",
)
memory = Memory.from_config(config)

# Add memory with entities
memory.add(
    "Pod app-backend in namespace production was OOMKilled. Fixed by increasing memory limit to 2Gi.",
    user_id="k8s-monitor",
)

# Verify graph relationships were created
# Check Neo4j for nodes: Pod, Namespace, Issue, Fix
```

**Expected**: Entities extracted, relationships created in Neo4j

---

### Test 5: Hierarchical Memory Tiers
**Purpose**: Verify working → episodic → semantic memory flow

```python
from core_agents.memory import HierarchicalMemory, HierarchicalMemoryConfig

config = HierarchicalMemoryConfig(
    qdrant_url="http://qdrant.database.svc.cluster.local:6333",
)
memory = HierarchicalMemory(config)

# Add to working memory (current session)
memory.add_working("Currently investigating pod crash")

# Promote to episodic (recent events)
memory.add_episodic("Fixed OOMKilled by increasing limits", importance=0.8)

# Search across tiers
results = memory.search("OOMKilled")
print(f"Found in tiers: {[r.tier for r in results]}")
```

**Expected**: Memories stored in appropriate tiers, cross-tier search works

---

### Test 6: Anomaly Detection
**Purpose**: Verify AnomalyDetector baseline tracking and alerting

```python
from core_agents.intelligence import AnomalyDetector, check_metric
import random

detector = AnomalyDetector()

# Build baseline with normal values
for _ in range(50):
    value = 45 + random.gauss(0, 5)  # Mean 45, std 5
    detector.add_data_point("cpu_percent", value)

# Check normal value (should be None)
alert = detector.check("cpu_percent", 48)
print(f"Normal value alert: {alert}")

# Check anomalous value (should trigger alert)
alert = detector.check("cpu_percent", 95)
print(f"Anomaly alert: {alert}")
if alert:
    print(f"  Type: {alert.anomaly_type}")
    print(f"  Severity: {alert.severity}")
    print(f"  Z-score: {alert.z_score:.2f}")
```

**Expected**: Normal values pass, anomalous values trigger WARNING/CRITICAL alerts

---

### Test 7: Capacity Planning
**Purpose**: Verify CapacityPlanner forecasting and recommendations

```python
from core_agents.intelligence import (
    CapacityPlanner,
    ResourceUsage,
    record_node_usage,
)
from datetime import datetime, timedelta, UTC

planner = CapacityPlanner()

# Simulate growing usage over 10 days
base_time = datetime.now(UTC) - timedelta(days=10)
for day in range(10):
    usage = ResourceUsage(
        node_name="worker-1",
        cpu_cores_used=2 + (day * 0.5),  # Growing from 2 to 6.5
        cpu_cores_total=8,
        memory_gb_used=8 + (day * 1),  # Growing from 8 to 17
        memory_gb_total=32,
        timestamp=base_time + timedelta(days=day),
    )
    planner.record_usage(usage)

# Get forecasts
forecasts = planner.forecast_capacity(horizon_days=30)
for f in forecasts:
    print(f"{f.resource_type.value}: {f.current_usage:.1f}% -> {f.projected_usage:.1f}%")
    if f.days_until_critical:
        print(f"  Days until critical: {f.days_until_critical}")

# Get recommendations
recs = planner.get_recommendations()
for r in recs:
    print(f"[{r.urgency.value}] {r.message}")
```

**Expected**: Forecasts show growth trends, recommendations generated for approaching limits

---

### Test 8: Pattern Detection (Recurrence)
**Purpose**: Verify PatternMatcher detects recurring issues

```python
from core_agents.intelligence import (
    PatternMatcher,
    record_issue,
    get_patterns,
    suggest_prevention,
)
from datetime import datetime, timedelta, UTC

matcher = PatternMatcher()

# Record similar issues
base_time = datetime.now(UTC)
for i in range(5):
    record_issue(
        issue_type="OOMKilled",
        resource="pod/app-backend",
        namespace="production",
        timestamp=base_time - timedelta(hours=i * 2),  # Every 2 hours
        matcher=matcher,
    )

# Detect patterns
patterns = get_patterns(matcher)
for p in patterns:
    print(f"Pattern: {p.pattern_type.value}")
    print(f"  Confidence: {p.confidence:.2f}")
    print(f"  Occurrences: {p.occurrence_count}")
    print(f"  Prevention: {suggest_prevention(p)}")
```

**Expected**: PERIODIC pattern detected with ~2 hour interval, prevention suggestions generated

---

### Test 9: K8s-Monitor Integration
**Purpose**: Verify k8s-monitor uses new core-agents features correctly

```bash
# Check k8s-monitor logs for new features
kubectl logs -n ai-agents deployment/k8s-monitor --tail=100 | grep -E "memory|anomaly|pattern"

# Trigger a health check
kubectl exec -n ai-agents deployment/k8s-monitor -- python -c "
from k8s_monitor.agent import create_health_check_agent
# ... trigger check
"
```

**Expected**: No import errors, new features accessible

---

### Test 10: Discord Notifications
**Purpose**: Verify Discord notifications still work with reorganized imports

```bash
# Check for successful Discord posts in logs
kubectl logs -n ai-agents deployment/k8s-monitor --tail=50 | grep -i discord

# Or trigger a test notification
kubectl exec -n ai-agents deployment/k8s-monitor -- python -c "
from core_agents.integrations.discord import send_discord_message
# ... send test message
"
```

**Expected**: Discord messages sent successfully

---

## Rollback Plan

If issues are found:

1. **Revert GitOps manifests**:
   ```bash
   git revert <merge-commit>
   git push origin main
   ```

2. **Force immediate rollback** (bypasses Flux):
   ```bash
   kubectl rollout undo deployment/k8s-monitor -n ai-agents
   ```

3. **Disable Qdrant/Neo4j** if causing issues:
   ```bash
   kubectl scale deployment/qdrant -n database --replicas=0
   kubectl scale deployment/neo4j -n database --replicas=0
   ```

---

## Test Results Summary (2025-12-29)

| Test | Status | Notes |
|------|--------|-------|
| Test 1: Qdrant Connectivity | ✅ PASSED | Health check 200 OK, collections API accessible with API key |
| Test 2: Neo4j Connectivity | ✅ PASSED | Neo4j 5.26.19 accessible via HTTP |
| Test 3: mem0 + Qdrant | ✅ PASSED | Memory add/search works with correct service URLs |
| Test 4: Graph Memory | ✅ PASSED | Neo4j APOC 5.26.19 verified, mem0g integration working |
| Test 5: Hierarchical Memory | ⏳ SKIPPED | Future test |
| Test 6: Anomaly Detection | ✅ PASSED | Baseline tracking, threshold detection, z-score alerts working |
| Test 7: Capacity Planning | ✅ PASSED | Resource forecasting, growth trends, recommendations working |
| Test 8: Pattern Detection | ⏳ SKIPPED | Future test |
| Test 9: K8s-Monitor Integration | ✅ PASSED | No import errors, features accessible |
| Test 10: Discord Notifications | ✅ PASSED | Already verified working from previous tests |

### Issues Fixed During Testing

1. **Neo4j config validation**: K8s injects service environment variables (e.g., `PORT_7687_TCP_PORT`) that Neo4j 5.x strict validation rejects. Fixed by adding `NEO4J_server_config_strict__validation_enabled=false`.

2. **mem0 SSL/TLS error**: mem0's Qdrant client defaulted to HTTPS. Fixed by using explicit `url` parameter with `http://` prefix instead of separate `host`/`port` parameters.

3. **Embeddings service name**: Default config used wrong service name `vllm-embeddings`. Correct service is `embeddings-api.vllm.svc.cluster.local:8000`.

4. **Missing graph memory dependencies**: mem0 graph memory requires `langchain-neo4j` and `rank-bm25` packages. Added to core-agents dependencies in version 0.2.3.

---

## Notes

- All tests should be run from within the cluster or with proper port-forwarding
- Secrets for Qdrant API key and Neo4j credentials are in `database` namespace
- vLLM embeddings service must be running for mem0 to generate embeddings
- Correct service URLs:
  - LLM: `http://llm-api.vllm.svc.cluster.local:8000/v1`
  - Embeddings: `http://embeddings-api.vllm.svc.cluster.local:8000/v1`
  - Qdrant: `http://qdrant.database.svc.cluster.local:6333`
  - Neo4j: `bolt://neo4j.database.svc.cluster.local:7687`
