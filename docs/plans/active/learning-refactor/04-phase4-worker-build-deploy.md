# Phase 4: Worker, Build, Deploy, and Migration

**Depends on:** Phases 1-3 (all workflows, activities, and agents)
**Produces:** Worker entry point, pyproject.toml, Earthfile, deployment manifests, config updates

---

## 4.1 Worker Entry Point

Create `kubani/syndicates/learning_system/src/learning_system_syndicate/__init__.py`:

```python
"""Learning System Syndicate package."""
```

Create `kubani/syndicates/learning_system/src/learning_system_syndicate/worker.py`:

```python
"""Temporal worker entry point for the Learning System Syndicate.

Entry points:
- learning-system-worker: Runs the Temporal worker
- learning-system-schedules: Creates/manages Temporal schedules

Architecture:
    Four-stage pipeline:

    Stage 1 — Collect (hourly):
        CollectExecutionsWorkflow queries Temporal for recent workflow
        completions across all monitored namespaces.

    Stage 2 — Evaluate (triggered by Stage 1):
        EvaluateExecutionsWorkflow runs CriticAgent to score individual
        executions, then triggers ReflectWorkflow as a child workflow.

    Stage 3 — Reflect (triggered by Stage 2):
        ReflectWorkflow runs ReflectionAgent to synthesize cross-agent
        patterns and identify trends from critic evaluations.

    Stage 4 — Improve (daily):
        ImprovementWorkflow runs ImprovementAgent to propose actionable
        improvements to agent skills, prompts, and configurations.

Usage:
    # Start the worker
    learning-system-worker

    # Initialize schedules
    learning-system-schedules setup

    # List schedules
    learning-system-schedules list

    # Remove schedules
    learning-system-schedules teardown
"""

import asyncio
import logging
import os
import sys

from temporalio.client import Client
from temporalio.worker import Worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

TEMPORAL_NAMESPACE = "learning-system"
TASK_QUEUE = "learning-system"


def get_temporal_settings() -> tuple[str, str]:
    """Get Temporal connection settings from environment."""
    host = os.environ.get("TEMPORAL_HOST", "localhost:7233")
    namespace = os.environ.get("TEMPORAL_NAMESPACE", TEMPORAL_NAMESPACE)
    return host, namespace


# =============================================================================
# Registration
# =============================================================================


def get_workflows() -> list:
    """Get all workflows for this syndicate."""
    from kubani.syndicates.learning_system.workflows import (
        CollectExecutionsWorkflow,
        EvaluateExecutionsWorkflow,
        ImprovementWorkflow,
        ReflectWorkflow,
    )

    return [
        # Stage 1: Collect
        CollectExecutionsWorkflow,
        # Stage 2: Evaluate (Critic)
        EvaluateExecutionsWorkflow,
        # Stage 3: Reflect
        ReflectWorkflow,
        # Stage 4: Improve
        ImprovementWorkflow,
    ]


def get_activities() -> list:
    """Get all activities for this syndicate."""
    from kubani.syndicates.learning_system.activities import (
        check_seen_activity,
        list_recent_workflows_activity,
        get_workflow_detail_activity,
        mark_seen_activity,
        propose_improvements_activity,
        publish_proposals_activity,
        run_critic_activity,
        run_reflection_activity,
        store_records_activity,
    )

    return [
        # Stage 1: Collection
        list_recent_workflows_activity,
        get_workflow_detail_activity,
        check_seen_activity,
        mark_seen_activity,
        store_records_activity,
        # Stage 2: Evaluate (Critic)
        run_critic_activity,
        # Stage 3: Reflect
        run_reflection_activity,
        # Stage 4: Improvement
        propose_improvements_activity,
        publish_proposals_activity,
    ]


# =============================================================================
# Worker
# =============================================================================


async def run_worker() -> None:
    """Run the Learning System worker."""
    temporal_host, temporal_namespace = get_temporal_settings()

    logger.info(f"Connecting to Temporal at {temporal_host}")
    logger.info(f"Namespace: {temporal_namespace}, Task queue: {TASK_QUEUE}")

    client = await Client.connect(temporal_host, namespace=temporal_namespace)

    workflows = get_workflows()
    activities = get_activities()

    logger.info(f"Workflows: {[w.__name__ for w in workflows]}")
    logger.info(f"Activities: {len(activities)}")

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=workflows,
        activities=activities,
    )

    logger.info("Starting Learning System worker...")

    try:
        await worker.run()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    finally:
        logger.info("Worker shutdown complete")


# =============================================================================
# Schedule Management
# =============================================================================


async def setup_schedules() -> None:
    """Create Temporal schedules for the learning pipeline.

    Two schedules:
    1. Collection: Every hour (Stage 1)
    2. Improvement: Daily at 9 AM UTC (Stage 4)

    Stages 2-3 (Evaluate + Reflect) are NOT scheduled — they're triggered
    programmatically: Stage 1 triggers Stage 2 as a child workflow,
    and Stage 2 triggers Stage 3 as a child workflow (fire-and-forget).
    """
    from kubani.framework.temporal import (
        CRON_DAILY_MORNING,
        EVERY_HOUR,
        ScheduleConfig,
        setup_syndicate_schedules,
    )
    from kubani.syndicates.learning_system.workflows import (
        CollectExecutionsWorkflow,
        ImprovementWorkflow,
    )

    temporal_host, temporal_namespace = get_temporal_settings()
    client = await Client.connect(temporal_host, namespace=temporal_namespace)

    schedules = [
        # Stage 1: Collect — every hour
        ScheduleConfig(
            schedule_id="learning-collect-schedule",
            workflow_type=CollectExecutionsWorkflow,
            workflow_id_prefix="learning-collect",
            task_queue=TASK_QUEUE,
            workflow_input=None,  # Use defaults (all namespaces, 1h lookback)
            interval_minutes=EVERY_HOUR,
            memo={
                "syndicate": "learning-system",
                "stage": "collect",
                "description": "Collect recent workflow executions from all namespaces",
            },
        ),
        # Stage 3: Improve — daily at 9 AM UTC
        ScheduleConfig(
            schedule_id="learning-improve-schedule",
            workflow_type=ImprovementWorkflow,
            workflow_id_prefix="learning-improve",
            task_queue=TASK_QUEUE,
            workflow_input=None,  # Use defaults (24h lookback, 5 max proposals)
            cron_expression=CRON_DAILY_MORNING,
            memo={
                "syndicate": "learning-system",
                "stage": "improve",
                "description": "Propose improvements from reflection insights and critic evaluations",
            },
        ),
    ]

    results = await setup_syndicate_schedules("learning-system", schedules, client)
    for schedule_id, status in results.items():
        logger.info(f"Schedule {schedule_id}: {status}")

    logger.info("Schedule setup complete")


async def teardown_schedules() -> None:
    """Remove all Learning System schedules."""
    from kubani.framework.temporal import teardown_syndicate_schedules

    temporal_host, temporal_namespace = get_temporal_settings()
    client = await Client.connect(temporal_host, namespace=temporal_namespace)

    schedule_ids = [
        "learning-collect-schedule",
        "learning-improve-schedule",
    ]

    results = await teardown_syndicate_schedules(schedule_ids, client)
    for schedule_id, success in results.items():
        logger.info(f"Schedule {schedule_id}: {'removed' if success else 'not found'}")


async def list_schedules() -> None:
    """List current Learning System schedules."""
    from kubani.framework.temporal import get_schedule_info

    temporal_host, temporal_namespace = get_temporal_settings()
    client = await Client.connect(temporal_host, namespace=temporal_namespace)

    for schedule_id in ["learning-collect-schedule", "learning-improve-schedule"]:
        info = await get_schedule_info(schedule_id, client)
        if info:
            logger.info(f"\n{schedule_id}:")
            logger.info(f"  Paused: {info['paused']}")
            logger.info(f"  Actions: {info['num_actions']}")
            logger.info(f"  Next: {info['next_action_times']}")
        else:
            logger.info(f"\n{schedule_id}: Not found")


# =============================================================================
# CLI Entry Points
# =============================================================================


def main() -> None:
    """CLI entry point: learning-system-worker."""
    asyncio.run(run_worker())


def schedules() -> None:
    """CLI entry point: learning-system-schedules."""
    if len(sys.argv) < 2:
        print("Usage: learning-system-schedules <setup|teardown|list>")
        sys.exit(1)

    command = sys.argv[1]
    if command == "setup":
        asyncio.run(setup_schedules())
    elif command == "teardown":
        asyncio.run(teardown_schedules())
    elif command == "list":
        asyncio.run(list_schedules())
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
```

---

## 4.2 pyproject.toml

Create `kubani/syndicates/learning_system/pyproject.toml`:

```toml
[project]
name = "learning-system-syndicate"
version = "1.0.0"
description = "Continuous learning system for Kubani AI agents"
requires-python = ">=3.12"

dependencies = [
    "temporalio>=1.9.0",
    "httpx>=0.27.0",
]

[project.scripts]
learning-system-worker = "learning_system_syndicate.worker:main"
learning-system-schedules = "learning_system_syndicate.worker:schedules"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/learning_system_syndicate"]
```

---

## 4.3 Earthfile

Create `kubani/syndicates/learning_system/Earthfile`:

```dockerfile
VERSION 0.8
IMPORT ../.. AS kubani

# =============================================================================
# Base setup
# =============================================================================

setup:
    FROM python:3.12-slim
    WORKDIR /app

    # Install uv
    RUN pip install uv

    # Create non-root user
    RUN useradd --create-home --shell /bin/bash agent

    # Copy workspace pyproject.toml
    COPY ../../pyproject.toml ./pyproject.toml
    COPY ../../uv.lock ./uv.lock

    # Copy framework and agents
    COPY ../../kubani/framework ./kubani/framework
    COPY ../../kubani/agents/_base ./kubani/agents/_base
    COPY ../../kubani/agents/critic ./kubani/agents/critic
    COPY ../../kubani/agents/reflection ./kubani/agents/reflection
    COPY ../../kubani/agents/improvement_agent ./kubani/agents/improvement_agent

    # Copy this syndicate
    COPY ./src ./kubani/syndicates/learning_system/src
    COPY ./models.py ./kubani/syndicates/learning_system/models.py
    COPY ./activities.py ./kubani/syndicates/learning_system/activities.py
    COPY ./_mcp.py ./kubani/syndicates/learning_system/_mcp.py
    COPY ./pipeline ./kubani/syndicates/learning_system/pipeline
    COPY ./workflows ./kubani/syndicates/learning_system/workflows
    COPY ./config.yaml ./kubani/syndicates/learning_system/config.yaml
    COPY ./__init__.py ./kubani/syndicates/learning_system/__init__.py
    COPY ./pyproject.toml ./kubani/syndicates/learning_system/pyproject.toml

    # Copy config
    COPY ../../config ./config

    # Strip other syndicates from workspace members
    RUN sed -i '/k8s_monitor/d; /news_digest/d' pyproject.toml || true

    # Sync dependencies
    RUN uv sync --package learning-system-syndicate

# =============================================================================
# Test
# =============================================================================

test:
    FROM +setup
    COPY ./tests ./kubani/syndicates/learning_system/tests
    RUN uv run --package learning-system-syndicate pytest kubani/syndicates/learning_system/tests/ -v

# =============================================================================
# Docker image
# =============================================================================

docker:
    FROM +setup
    ARG VERSION=latest

    # Install production deps only
    RUN uv sync --package learning-system-syndicate --no-dev

    # Set ownership
    RUN chown -R agent:agent /app
    USER agent

    # Environment
    ENV KUBANI_ENVIRONMENT=production
    ENV KUBANI_CONFIG_DIR=/app/config
    ENV HOME=/app

    ENTRYPOINT ["/app/.venv/bin/learning-system-worker"]

    LABEL org.opencontainers.image.title="learning-system"
    LABEL org.opencontainers.image.description="Continuous learning system for Kubani AI agents"
    LABEL org.opencontainers.image.version="${VERSION}"

    SAVE IMAGE registry.almckay.io/learning-system:${VERSION}
    SAVE IMAGE registry.almckay.io/learning-system:latest

# =============================================================================
# Push
# =============================================================================

push:
    FROM +docker
    ARG VERSION=latest
    RUN --push echo "Pushing learning-system:${VERSION}"
```

---

## 4.4 Syndicate Config

Create `kubani/syndicates/learning_system/config.yaml`:

```yaml
name: learning-system
version: "1.0.0"
description: >
  Continuous learning system that monitors all agent workflow executions,
  evaluates quality, identifies patterns, and proposes improvements.

namespace: learning-system
task_queue: learning-system

agents:
  - critic
  - reflection
  - improvement-agent

# Temporal namespaces to monitor
monitored_namespaces:
  - k8s-monitor
  - news-digest
  - nexus
  - learning-system

# Stage 1: Collection schedule
collection:
  interval_minutes: 60
  hours_back: 1

# Stage 2: Evaluation (triggered by Stage 1, no schedule)
evaluation:
  max_batch_size: 50

# Stage 3: Reflection (triggered by Stage 2, no schedule)
reflection:
  min_evaluations: 5  # Minimum evaluations before synthesizing

# Stage 4: Improvement schedule
improvement:
  cron: "0 9 * * *"  # Daily at 9 AM UTC
  lookback_hours: 24
  max_proposals: 5
  auto_approve_threshold: 0.95

# Discord publishing
discord:
  enabled: true
  channel: kubani-learning

# Events this syndicate publishes
events:
  publish:
    - learning:collection_complete
    - learning:evaluation_complete
    - learning:reflection_complete
    - learning:improvement_proposed
```

---

## 4.5 Kubernetes Deployment

Update `infrastructure/gitops/apps/ai-agents/learning-agent/deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: learning-system
  namespace: ai-agents
  labels:
    app: learning-system
    component: worker
spec:
  replicas: 1
  selector:
    matchLabels:
      app: learning-system
  template:
    metadata:
      labels:
        app: learning-system
        component: worker
      annotations:
        # Restart on config changes
        configmap.reloader.stakater.com/reload: "model-config"
    spec:
      serviceAccountName: learning-system
      containers:
        - name: worker
          image: registry.almckay.io/learning-system:1.0.0
          imagePullPolicy: Always

          env:
            # Kubani
            - name: KUBANI_ENVIRONMENT
              value: "production"

            # Temporal
            - name: TEMPORAL_HOST
              value: "temporal-frontend.temporal.svc.cluster.local:7233"
            - name: TEMPORAL_NAMESPACE
              value: "learning-system"

            # LLM (for critic, reflection, and improvement agents)
            - name: LLM_API_URL
              value: "http://llm-api.vllm.svc.cluster.local:8000/v1"
            - name: LLM_MODEL
              valueFrom:
                configMapKeyRef:
                  name: model-config
                  key: LLM_MODEL_NAME

            # MCP Servers
            - name: MCP_TEMPORAL_URL
              value: "http://temporal-mcp-server.ai-agents.svc:8081"
            - name: MCP_MEMORY_URL
              value: "http://memory-mcp.ai-agents.svc:8083"
            - name: MCP_SKILLS_URL
              value: "http://skills-mcp.ai-agents.svc:8085"

            # Memory backends (for framework config)
            - name: QDRANT_HOST
              value: "qdrant.database.svc.cluster.local"
            - name: NEO4J_URI
              value: "bolt://neo4j.database.svc.cluster.local:7687"
            - name: REDIS_HOST
              valueFrom:
                secretKeyRef:
                  name: learning-system-secrets
                  key: redis-host
            - name: REDIS_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: learning-system-secrets
                  key: redis-password

            # Discord (for publishing proposals)
            - name: DISCORD_WEBHOOK_URL
              valueFrom:
                secretKeyRef:
                  name: learning-system-secrets
                  key: discord-webhook-url

            # Registry
            - name: KUBANI_REGISTRY_URL
              value: "http://metadata-registry.ai-agents.svc:8000"

          resources:
            requests:
              cpu: 100m
              memory: 256Mi
            limits:
              cpu: 500m
              memory: 1Gi

          livenessProbe:
            exec:
              command:
                - python3
                - -c
                - "from learning_system_syndicate.worker import get_workflows; assert len(get_workflows()) == 4"
            initialDelaySeconds: 30
            periodSeconds: 60
            failureThreshold: 3

          readinessProbe:
            exec:
              command:
                - python3
                - -c
                - "from learning_system_syndicate.worker import get_workflows, get_activities; assert len(get_workflows()) > 0"
            initialDelaySeconds: 15
            periodSeconds: 30
```

---

## 4.6 Config Updates

### config/default.yaml

Replace the existing `learning:` section:

```yaml
learning:
  enabled: true

  # Temporal namespaces to monitor
  monitored_namespaces:
    - k8s-monitor
    - news-digest
    - nexus
    - learning-system

  # Stage 1: Collection
  collection:
    interval_minutes: 60
    hours_back: 1

  # Stage 2: Evaluation / Critic (triggered by Stage 1, no schedule)
  evaluation:
    max_batch_size: 50

  # Stage 3: Reflection (triggered by Stage 2, no schedule)
  reflection:
    min_evaluations: 5

  # Stage 4: Improvement
  improvement:
    lookback_hours: 24
    max_proposals: 5
    auto_approve_threshold: 0.95

  # Discord
  discord:
    enabled: true
    channel: kubani-learning
```

### config/production.yaml

Replace the existing `learning:` section:

```yaml
learning:
  enabled: true
  improvement:
    auto_approve_threshold: 0.98  # Higher bar in production
    max_proposals: 3              # Fewer proposals to review
```

---

## 4.7 Temporal Namespace Setup

The learning system needs its own Temporal namespace. This is a one-time setup step:

```bash
# Create the namespace via Temporal CLI (or via temporal-mcp-server)
temporal operator namespace create learning-system

# Verify
temporal operator namespace describe learning-system
```

Or create via the Temporal MCP server if direct CLI isn't available.

---

## 4.8 Migration Plan

### Step 1: Deploy new system alongside old

1. Build and push the new container:
   ```bash
   cd kubani/syndicates/learning_system
   earthly +push --VERSION=1.0.0
   ```

2. Create the Temporal namespace:
   ```bash
   temporal operator namespace create learning-system
   ```

3. Update the GitOps deployment (deployment.yaml above).

4. Push to git, let Flux deploy.

5. Set up schedules:
   ```bash
   KUBECONFIG=/home/al/.kube/config kubectl exec -n ai-agents deploy/learning-system -- \
     learning-system-schedules setup
   ```

### Step 2: Validate new system

1. Check pod is running:
   ```bash
   KUBECONFIG=/home/al/.kube/config kubectl get pods -n ai-agents -l app=learning-system
   ```

2. Check logs for successful collection:
   ```bash
   KUBECONFIG=/home/al/.kube/config kubectl logs -n ai-agents deploy/learning-system --tail=50
   ```

3. Verify schedules are active:
   ```bash
   # Via Temporal MCP or UI
   temporal schedule list --namespace learning-system
   ```

4. Wait for first collection cycle (1 hour) and verify:
   - ExecutionRecords stored in Memory MCP
   - EvaluateExecutionsWorkflow triggered and completed (CriticAgent scored executions)
   - ReflectWorkflow triggered and completed (ReflectionAgent synthesized patterns)
   - CriticEvaluations and ReflectionInsights stored in Memory MCP

5. Wait for first improvement cycle (daily) or trigger manually:
   ```bash
   temporal workflow start --namespace learning-system \
     --task-queue learning-system \
     --type ImprovementWorkflow \
     --workflow-id learning-improve-manual
   ```

### Step 3: Remove old system

After confirming the new system works for at least a few days:

1. Delete old Temporal schedules (if any exist in the `default` namespace).

2. Remove old code:
   ```
   # Delete old agents
   rm -rf kubani/agents/critic/
   rm -rf kubani/agents/reflection/
   rm -rf kubani/agents/skill_synthesizer/

   # Delete old syndicate files
   rm kubani/syndicates/learning_system/syndicate.py
   rm kubani/syndicates/learning_system/events.py

   # Delete old base syndicate class (if no other syndicates use it)
   # Check first: grep -r "from kubani.syndicates._base" kubani/
   ```

3. Update `config/default.yaml` and `config/production.yaml` to remove deprecated fields:
   - Remove `critic_enabled`, `reflection_enabled`, `synthesizer_enabled`
   - Remove `critic_interval_minutes`, `reflection_interval_hours`
   - Remove `passive_monitoring` section

4. Update documentation:
   - `docs/architecture/core-concepts/learning-system.md` — Rewrite for new architecture
   - `.claude/skills/continuous-learning/SKILL.md` — Update for new commands
   - `docs/adr/003-voyager-learning-system.md` — Add "Superseded" note

5. Commit and push.

---

## 4.9 Complete File Inventory

### New Files (created in Phases 1-4)

```
kubani/syndicates/learning_system/
├── __init__.py                              # Update exports
├── _mcp.py                                  # MCP client helpers
├── activities.py                            # All 9 activities (5 collection + 2 evaluation/reflection + 2 improvement)
├── config.yaml                              # Syndicate manifest
├── models.py                                # 3 dataclasses + utilities
├── pyproject.toml                           # Package definition
├── Earthfile                                # Container build
├── pipeline/
│   ├── __init__.py                          # Export run_collection_pipeline
│   ├── context.py                           # LearningPipelineContext protocol
│   ├── collect.py                           # Collection pipeline logic
│   └── contexts/
│       ├── __init__.py
│       ├── temporal_context.py              # Production context
│       └── local_context.py                 # Test context
├── workflows/
│   ├── __init__.py                          # Export all 4 workflows
│   ├── collect.py                           # CollectExecutionsWorkflow
│   ├── evaluate.py                          # EvaluateExecutionsWorkflow (Critic)
│   ├── reflect.py                           # ReflectWorkflow (Reflection)
│   └── improve.py                           # ImprovementWorkflow
├── src/learning_system_syndicate/
│   ├── __init__.py
│   └── worker.py                            # Entry point + schedules
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_models.py
    ├── test_collect_pipeline.py
    ├── test_evaluate_workflow.py
    ├── test_reflect_workflow.py
    └── test_improve_workflow.py

kubani/agents/critic/
├── __init__.py
├── agent.py                                 # CriticAgent (KubaniAgent subclass, modernized)
├── config.yaml
└── prompt.md

kubani/agents/reflection/
├── __init__.py
├── agent.py                                 # ReflectionAgent (KubaniAgent subclass, modernized)
├── config.yaml
└── prompt.md

kubani/agents/improvement_agent/
├── __init__.py
├── agent.py
├── config.yaml
└── prompt.md
```

### Modified Files

```
config/default.yaml                          # Replace learning section
config/production.yaml                       # Replace learning section
infrastructure/gitops/apps/ai-agents/learning-agent/deployment.yaml
infrastructure/gitops/apps/ai-agents/learning-agent/kustomization.yaml
```

### Replaced Files (modernized in Phases 1-3)

```
kubani/agents/critic/                        # Replaced with modernized KubaniAgent subclass
kubani/agents/reflection/                    # Replaced with modernized KubaniAgent subclass
```

### Deleted Files (after validation)

```
kubani/agents/skill_synthesizer/             # Replaced by improvement_agent
kubani/syndicates/learning_system/syndicate.py  # Replaced by Temporal workflows
kubani/syndicates/learning_system/events.py     # Events now in activities
kubani/syndicates/_base/                        # No longer needed (if no other syndicates use it)
```

---

## 4.10 Final Verification Checklist

- [ ] **Worker starts:** `learning-system-worker` runs without errors
- [ ] **Schedules created:** Two schedules (collect hourly, improve daily)
- [ ] **Collection works:** ExecutionRecords stored from k8s-monitor + news-digest namespaces
- [ ] **Evaluation works:** CriticEvaluations created with scores and failure classifications
- [ ] **Reflection works:** ReflectionInsights created with cross-agent patterns and trends
- [ ] **Improvements work:** ProposedImprovements created and published to Discord
- [ ] **UI visible:** All 4 workflows appear in the Kubani UI Workflows page
- [ ] **Observable:** All workflows respond to `get_status` query
- [ ] **Tests pass:** All 5 test files pass (models, collect, evaluate, reflect, improve)
- [ ] **Container builds:** Earthfile `+docker` succeeds
- [ ] **Pod healthy:** Liveness and readiness probes pass
- [ ] **Old code removed:** Old Critic, Reflection, SkillSynthesizer agents deleted (replaced by modernized versions)
- [ ] **Config cleaned:** No deprecated learning config fields
- [ ] **Docs updated:** Architecture docs and skills reflect new 3-agent system
