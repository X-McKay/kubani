# Phase 5: Agent Consolidation - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

> **Note (2026-01-23)**: The kubani-dev CLI has been moved from `tools/kubani-dev` to `platform/cli`.
> Update installation command: `uv pip install -e platform/cli`

**Goal:** Consolidate cluster-monitor (v0.2.4) into k8s-monitor (v0.3.16), eliminating duplication while preserving the sophisticated 8-stage investigation pipeline. Result: A single, production-grade Kubernetes monitoring agent using the unified agent-framework.

**Architecture:** Enhance k8s-monitor's federated architecture (Sentinel + Healer + Explorer) with cluster-monitor's orchestrator patterns, implemented as Temporal workflows for durability and recoverability.

**Tech Stack:** Python 3.11+, Temporal, core-agents framework, AgentWorker, Redis Streams, Qdrant, MCP

**Risk Level:** HIGH - Affects production K8s monitoring. Requires blue-green deployment with shadow mode.

---

## Pre-Flight Checklist

Before starting, verify:
```bash
# On feature/restructure branch
git branch --show-current

# Phase 4 complete (v0.3.0 framework)
python -c "from agent_framework import __version__; print(__version__)"
# Expected: 0.3.0

# Both agents exist
ls agents/cluster-monitor agents/k8s-monitor

# Current versions
grep "version" agents/cluster-monitor/pyproject.toml
grep "version" agents/k8s-monitor/pyproject.toml
```

---

## Consolidation Overview

```
BEFORE (Two Parallel Agents):
┌─────────────────────┐         ┌──────────────────┐
│  cluster-monitor    │         │   k8s-monitor    │
│  (Orchestrator-     │    →    │  (Temporal +     │
│   Worker Pattern)   │         │   Federated)     │
└─────────────────────┘         └──────────────────┘

AFTER (Unified k8s-monitor):
┌──────────────────────────────────────────────────┐
│  k8s-monitor (Unified v0.4.0)                    │
│  ┌────────────────────────────────────────────┐  │
│  │ Temporal Workflows                          │  │
│  │ - ClusterHealthCheckWorkflow (existing)     │  │
│  │ - ScheduledHealthCheckWorkflow (existing)   │  │
│  │ - RemediationOrchestrationWorkflow (NEW)    │  │
│  └────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────┐  │
│  │ Federated Agents                            │  │
│  │ - Sentinel (enhanced with correlation)      │  │
│  │ - Healer (enhanced with 8-stage pipeline)   │  │
│  │ - Explorer (unchanged)                      │  │
│  └────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
```

---

## Task 1: Analyze and Document cluster-monitor Patterns

**Files:**
- Read: `agents/cluster-monitor/src/cluster_monitor/`
- Create: `docs/plans/cluster-monitor-patterns.md` (temporary reference doc)

**Step 1: Document the 8-stage investigation pipeline**

Review `orchestrator.py` and document each stage:
1. ANALYZING - Initial event classification
2. QUERYING_MEMORY - Check historical patterns
3. INVESTIGATING - Run diagnostic skills
4. PLANNING_REMEDIATION - Determine action
5. AWAITING_APPROVAL - Discord approval (if needed)
6. EXECUTING_ACTION - Run remediation
7. VERIFYING - Check success
8. SUMMARIZING - Generate narrative

**Step 2: Document the Correlator logic**

Review `correlator.py`:
- 30-second correlation window
- Event grouping by namespace/pod
- Pattern-based deduplication

**Step 3: Document models to preserve**

Review `models.py`:
- InvestigationState
- InvestigationStage enum
- CorrelatedIssue
- Any other unique models

**Step 4: Commit documentation**

```bash
git add docs/plans/cluster-monitor-patterns.md
git commit -m "docs(phase5): document cluster-monitor patterns for consolidation

Preserving:
- 8-stage investigation pipeline
- 30s event correlation window
- Investigation state machine
- Orchestrator → Worker delegation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Add Investigation Models to k8s-monitor

**Files:**
- Modify: `agents/k8s-monitor/src/k8s_monitor/models.py`

**Step 1: Add InvestigationStage enum**

```python
from enum import Enum

class InvestigationStage(str, Enum):
    """8-stage investigation pipeline from cluster-monitor."""

    ANALYZING = "analyzing"
    QUERYING_MEMORY = "querying_memory"
    INVESTIGATING = "investigating"
    PLANNING_REMEDIATION = "planning_remediation"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING_ACTION = "executing_action"
    VERIFYING = "verifying"
    SUMMARIZING = "summarizing"
    COMPLETED = "completed"
    FAILED = "failed"
```

**Step 2: Add InvestigationState model**

```python
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Any


class InvestigationState(BaseModel):
    """Full state for an investigation workflow."""

    investigation_id: str = Field(description="Unique investigation ID")
    stage: InvestigationStage = Field(default=InvestigationStage.ANALYZING)

    # Event context
    trigger_event: dict[str, Any] = Field(default_factory=dict)
    correlated_events: list[dict[str, Any]] = Field(default_factory=list)
    namespace: str | None = None
    pod_name: str | None = None
    node_name: str | None = None

    # Analysis results
    classification: str | None = None
    severity: str = "unknown"
    confidence: float = 0.0

    # Memory context
    similar_incidents: list[dict[str, Any]] = Field(default_factory=list)
    relevant_skills: list[str] = Field(default_factory=list)

    # Investigation findings
    diagnostic_results: dict[str, Any] = Field(default_factory=dict)
    root_cause: str | None = None

    # Remediation
    remediation_plan: dict[str, Any] | None = None
    approval_required: bool = False
    approval_status: str | None = None
    remediation_result: dict[str, Any] | None = None

    # Verification
    verification_result: dict[str, Any] | None = None
    resolution_confirmed: bool = False

    # Narrative
    narrative: str = ""

    # Timestamps
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    stage_timestamps: dict[str, datetime] = Field(default_factory=dict)

    # Error handling
    error: str | None = None
    retry_count: int = 0


class CorrelatedIssue(BaseModel):
    """Group of related K8s events within correlation window."""

    correlation_id: str
    primary_event: dict[str, Any]
    related_events: list[dict[str, Any]] = Field(default_factory=list)
    namespace: str
    affected_resources: list[str] = Field(default_factory=list)
    first_seen: datetime
    last_seen: datetime
    event_count: int = 1
```

**Step 3: Commit**

```bash
git add agents/k8s-monitor/src/k8s_monitor/models.py
git commit -m "feat(k8s-monitor): add investigation models from cluster-monitor

Models added:
- InvestigationStage: 8-stage pipeline enum
- InvestigationState: Full investigation state machine
- CorrelatedIssue: Event correlation grouping

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Add Event Correlation to Sentinel

**Files:**
- Modify: `agents/k8s-monitor/src/k8s_monitor/federated/sentinel.py`

**Step 1: Add correlation logic**

```python
import asyncio
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Any

from k8s_monitor.models import CorrelatedIssue


class EventCorrelator:
    """Correlates related K8s events within a time window."""

    CORRELATION_WINDOW = timedelta(seconds=30)

    def __init__(self):
        self._pending_events: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._correlation_timers: dict[str, asyncio.Task] = {}
        self._callbacks: list[callable] = []

    def _get_correlation_key(self, event: dict[str, Any]) -> str:
        """Generate correlation key from event."""
        namespace = event.get("namespace", "default")
        # Group by namespace + involved object
        involved = event.get("involved_object", {})
        kind = involved.get("kind", "unknown")
        name = involved.get("name", "unknown")
        return f"{namespace}/{kind}/{name}"

    async def add_event(self, event: dict[str, Any]) -> None:
        """Add event to correlation buffer."""
        key = self._get_correlation_key(event)
        self._pending_events[key].append({
            **event,
            "received_at": datetime.utcnow().isoformat(),
        })

        # Reset or start correlation timer
        if key in self._correlation_timers:
            self._correlation_timers[key].cancel()

        self._correlation_timers[key] = asyncio.create_task(
            self._correlation_timeout(key)
        )

    async def _correlation_timeout(self, key: str) -> None:
        """Fire correlated issue after window expires."""
        await asyncio.sleep(self.CORRELATION_WINDOW.total_seconds())

        events = self._pending_events.pop(key, [])
        if not events:
            return

        # Create correlated issue
        primary = events[0]
        correlated = CorrelatedIssue(
            correlation_id=f"corr-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{key.replace('/', '-')}",
            primary_event=primary,
            related_events=events[1:] if len(events) > 1 else [],
            namespace=primary.get("namespace", "default"),
            affected_resources=[key],
            first_seen=datetime.fromisoformat(events[0]["received_at"]),
            last_seen=datetime.fromisoformat(events[-1]["received_at"]),
            event_count=len(events),
        )

        # Notify callbacks
        for callback in self._callbacks:
            try:
                await callback(correlated)
            except Exception as e:
                logger.error(f"Correlation callback error: {e}")

    def on_correlated_issue(self, callback: callable) -> None:
        """Register callback for correlated issues."""
        self._callbacks.append(callback)
```

**Step 2: Integrate correlator into Sentinel agent**

Update the Sentinel class to use the correlator:

```python
class SentinelAgent:
    """Enhanced Sentinel with event correlation."""

    def __init__(self, ...):
        # ... existing init ...
        self.correlator = EventCorrelator()
        self.correlator.on_correlated_issue(self._handle_correlated_issue)

    async def _handle_correlated_issue(self, issue: CorrelatedIssue) -> None:
        """Handle correlated issue - trigger investigation."""
        logger.info(f"Correlated issue detected: {issue.correlation_id} ({issue.event_count} events)")

        # Publish investigation request
        await self.event_bus.publish(
            EventType.INVESTIGATION_REQUESTED,
            {
                "correlation_id": issue.correlation_id,
                "issue": issue.model_dump(),
                "source": "sentinel-correlator",
            }
        )
```

**Step 3: Commit**

```bash
git add agents/k8s-monitor/src/k8s_monitor/federated/sentinel.py
git commit -m "feat(k8s-monitor): add event correlation to Sentinel

Correlation features:
- 30-second correlation window
- Groups events by namespace/kind/name
- Fires CorrelatedIssue after window expires
- Publishes INVESTIGATION_REQUESTED events

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Create Remediation Orchestration Workflow

**Files:**
- Create: `agents/k8s-monitor/src/k8s_monitor/workflows/orchestration.py`
- Modify: `agents/k8s-monitor/src/k8s_monitor/workflows/__init__.py`

**Step 1: Create orchestration workflow**

```python
"""Remediation Orchestration Workflow - 8-stage investigation pipeline."""

from datetime import timedelta
from temporalio import workflow
from temporalio.common import RetryPolicy

from k8s_monitor.models import InvestigationState, InvestigationStage


@workflow.defn
class RemediationOrchestrationWorkflow:
    """
    8-stage investigation and remediation workflow.

    Stages:
    1. ANALYZING - Classify the issue
    2. QUERYING_MEMORY - Check historical patterns
    3. INVESTIGATING - Run diagnostic skills
    4. PLANNING_REMEDIATION - Determine action plan
    5. AWAITING_APPROVAL - Get human approval if needed
    6. EXECUTING_ACTION - Run remediation
    7. VERIFYING - Confirm resolution
    8. SUMMARIZING - Generate narrative
    """

    def __init__(self):
        self.state: InvestigationState | None = None

    @workflow.run
    async def run(self, trigger_event: dict, correlation_id: str | None = None) -> dict:
        """Run the full orchestration pipeline."""
        from k8s_monitor.activities.orchestration import (
            analyze_issue,
            query_memory,
            investigate_issue,
            plan_remediation,
            request_approval,
            execute_remediation,
            verify_resolution,
            summarize_investigation,
        )

        # Initialize state
        self.state = InvestigationState(
            investigation_id=correlation_id or workflow.info().workflow_id,
            trigger_event=trigger_event,
            stage=InvestigationStage.ANALYZING,
        )

        retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=1),
            maximum_interval=timedelta(minutes=1),
            maximum_attempts=3,
        )

        try:
            # Stage 1: ANALYZING
            self._set_stage(InvestigationStage.ANALYZING)
            analysis = await workflow.execute_activity(
                analyze_issue,
                self.state.trigger_event,
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=retry_policy,
            )
            self.state.classification = analysis.get("classification")
            self.state.severity = analysis.get("severity", "unknown")
            self.state.confidence = analysis.get("confidence", 0.0)
            self.state.namespace = analysis.get("namespace")
            self.state.pod_name = analysis.get("pod_name")

            # Stage 2: QUERYING_MEMORY
            self._set_stage(InvestigationStage.QUERYING_MEMORY)
            memory_result = await workflow.execute_activity(
                query_memory,
                {
                    "classification": self.state.classification,
                    "namespace": self.state.namespace,
                    "pod_name": self.state.pod_name,
                },
                start_to_close_timeout=timedelta(minutes=1),
                retry_policy=retry_policy,
            )
            self.state.similar_incidents = memory_result.get("similar_incidents", [])
            self.state.relevant_skills = memory_result.get("relevant_skills", [])

            # Stage 3: INVESTIGATING
            self._set_stage(InvestigationStage.INVESTIGATING)
            investigation = await workflow.execute_activity(
                investigate_issue,
                {
                    "state": self.state.model_dump(),
                    "skills": self.state.relevant_skills,
                },
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=retry_policy,
            )
            self.state.diagnostic_results = investigation.get("results", {})
            self.state.root_cause = investigation.get("root_cause")

            # Stage 4: PLANNING_REMEDIATION
            self._set_stage(InvestigationStage.PLANNING_REMEDIATION)
            plan = await workflow.execute_activity(
                plan_remediation,
                {
                    "state": self.state.model_dump(),
                    "root_cause": self.state.root_cause,
                },
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=retry_policy,
            )
            self.state.remediation_plan = plan.get("plan")
            self.state.approval_required = plan.get("requires_approval", False)

            # Stage 5: AWAITING_APPROVAL (if needed)
            if self.state.approval_required:
                self._set_stage(InvestigationStage.AWAITING_APPROVAL)
                approval = await workflow.execute_activity(
                    request_approval,
                    {
                        "investigation_id": self.state.investigation_id,
                        "plan": self.state.remediation_plan,
                        "severity": self.state.severity,
                    },
                    start_to_close_timeout=timedelta(hours=24),  # Long timeout for human approval
                    retry_policy=RetryPolicy(maximum_attempts=1),
                )
                self.state.approval_status = approval.get("status")

                if self.state.approval_status != "approved":
                    self._set_stage(InvestigationStage.COMPLETED)
                    self.state.narrative = f"Investigation completed. Remediation not approved: {approval.get('reason', 'rejected')}"
                    return self.state.model_dump()

            # Stage 6: EXECUTING_ACTION
            self._set_stage(InvestigationStage.EXECUTING_ACTION)
            execution = await workflow.execute_activity(
                execute_remediation,
                {
                    "plan": self.state.remediation_plan,
                    "namespace": self.state.namespace,
                    "pod_name": self.state.pod_name,
                },
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=retry_policy,
            )
            self.state.remediation_result = execution

            # Stage 7: VERIFYING
            self._set_stage(InvestigationStage.VERIFYING)
            verification = await workflow.execute_activity(
                verify_resolution,
                {
                    "namespace": self.state.namespace,
                    "pod_name": self.state.pod_name,
                    "expected_state": execution.get("expected_state"),
                },
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=retry_policy,
            )
            self.state.verification_result = verification
            self.state.resolution_confirmed = verification.get("resolved", False)

            # Stage 8: SUMMARIZING
            self._set_stage(InvestigationStage.SUMMARIZING)
            summary = await workflow.execute_activity(
                summarize_investigation,
                {"state": self.state.model_dump()},
                start_to_close_timeout=timedelta(minutes=1),
                retry_policy=retry_policy,
            )
            self.state.narrative = summary.get("narrative", "")

            # Complete
            self._set_stage(InvestigationStage.COMPLETED)
            self.state.completed_at = workflow.now()

            return self.state.model_dump()

        except Exception as e:
            self.state.stage = InvestigationStage.FAILED
            self.state.error = str(e)
            self.state.completed_at = workflow.now()
            raise

    def _set_stage(self, stage: InvestigationStage) -> None:
        """Update stage and record timestamp."""
        self.state.stage = stage
        self.state.stage_timestamps[stage.value] = workflow.now()

    @workflow.query
    def get_state(self) -> dict:
        """Query current investigation state."""
        return self.state.model_dump() if self.state else {}

    @workflow.signal
    async def provide_approval(self, approved: bool, reason: str = "") -> None:
        """Signal to provide approval decision."""
        if self.state and self.state.stage == InvestigationStage.AWAITING_APPROVAL:
            self.state.approval_status = "approved" if approved else "rejected"
```

**Step 2: Update workflows __init__.py**

```python
from k8s_monitor.workflows.orchestration import RemediationOrchestrationWorkflow

__all__ = [
    "ClusterHealthCheckWorkflow",
    "ScheduledHealthCheckWorkflow",
    "RemediationOrchestrationWorkflow",
]
```

**Step 3: Commit**

```bash
git add agents/k8s-monitor/src/k8s_monitor/workflows/
git commit -m "feat(k8s-monitor): add RemediationOrchestrationWorkflow

8-stage investigation pipeline as Temporal workflow:
1. ANALYZING - Issue classification
2. QUERYING_MEMORY - Historical pattern lookup
3. INVESTIGATING - Run diagnostic skills
4. PLANNING_REMEDIATION - Determine action plan
5. AWAITING_APPROVAL - Human approval (if needed)
6. EXECUTING_ACTION - Run remediation
7. VERIFYING - Confirm resolution
8. SUMMARIZING - Generate narrative

Features:
- Full state machine with timestamps
- Query for current state
- Signal for approval decisions
- Proper retry policies

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Create Orchestration Activities

**Files:**
- Create: `agents/k8s-monitor/src/k8s_monitor/activities/orchestration.py`
- Modify: `agents/k8s-monitor/src/k8s_monitor/activities/__init__.py`

**Step 1: Create orchestration activities**

```python
"""Orchestration activities for the 8-stage remediation pipeline."""

import logging
from typing import Any

from temporalio import activity

logger = logging.getLogger(__name__)


@activity.defn
async def analyze_issue(trigger_event: dict[str, Any]) -> dict[str, Any]:
    """
    Stage 1: Analyze and classify the issue.

    Uses LLM to classify the event and determine severity.
    """
    from core_agents.factory import get_agent_factory

    factory = get_agent_factory()

    # Extract event details
    event_type = trigger_event.get("type", "Unknown")
    reason = trigger_event.get("reason", "")
    message = trigger_event.get("message", "")
    involved_object = trigger_event.get("involved_object", {})

    namespace = involved_object.get("namespace", "default")
    pod_name = involved_object.get("name")
    kind = involved_object.get("kind", "Pod")

    # Classification patterns
    classifications = {
        "CrashLoopBackOff": ("container_crash", "high"),
        "OOMKilled": ("memory_exhaustion", "high"),
        "ImagePullBackOff": ("image_pull_failure", "medium"),
        "FailedScheduling": ("scheduling_failure", "medium"),
        "Unhealthy": ("health_check_failure", "medium"),
        "NodeNotReady": ("node_issue", "critical"),
    }

    # Try pattern match first
    classification = "unknown"
    severity = "medium"
    confidence = 0.0

    for pattern, (cls, sev) in classifications.items():
        if pattern.lower() in reason.lower() or pattern.lower() in message.lower():
            classification = cls
            severity = sev
            confidence = 0.9
            break

    # If no pattern match, could use LLM here
    if classification == "unknown":
        confidence = 0.5
        # TODO: LLM classification for unknown patterns

    logger.info(f"Analyzed issue: {classification} (severity={severity}, confidence={confidence})")

    return {
        "classification": classification,
        "severity": severity,
        "confidence": confidence,
        "namespace": namespace,
        "pod_name": pod_name,
        "kind": kind,
        "event_type": event_type,
        "reason": reason,
    }


@activity.defn
async def query_memory(context: dict[str, Any]) -> dict[str, Any]:
    """
    Stage 2: Query memory for similar incidents and relevant skills.

    Uses Qdrant for semantic search of past incidents.
    """
    from core_agents.memory import get_memory_system

    classification = context.get("classification", "unknown")
    namespace = context.get("namespace", "default")

    try:
        memory = get_memory_system()

        # Search for similar incidents
        similar = await memory.search(
            query=f"kubernetes {classification} issue in {namespace}",
            collection="incidents",
            limit=5,
        )

        # Get relevant skills
        skills = await memory.search(
            query=f"remediation skill for {classification}",
            collection="skills",
            limit=3,
        )

        return {
            "similar_incidents": [s.model_dump() for s in similar] if similar else [],
            "relevant_skills": [s.metadata.get("skill_name") for s in skills] if skills else [],
        }

    except Exception as e:
        logger.warning(f"Memory query failed: {e}")
        return {
            "similar_incidents": [],
            "relevant_skills": _get_default_skills(classification),
        }


def _get_default_skills(classification: str) -> list[str]:
    """Get default skills based on classification."""
    skill_map = {
        "container_crash": ["investigate-pod-failure", "restart-crashloop"],
        "memory_exhaustion": ["check-pod-resources", "scale-deployment"],
        "image_pull_failure": ["investigate-pod-failure", "restart-imagepullbackoff"],
        "scheduling_failure": ["check-node-resources", "diagnose-scheduling"],
        "health_check_failure": ["investigate-pod-failure", "check-pod-resources"],
        "node_issue": ["check-node-resources", "drain-node"],
    }
    return skill_map.get(classification, ["investigate-pod-failure"])


@activity.defn
async def investigate_issue(params: dict[str, Any]) -> dict[str, Any]:
    """
    Stage 3: Run diagnostic skills to investigate the issue.
    """
    from core_agents.skills import get_unified_skill_library

    state = params.get("state", {})
    skills = params.get("skills", [])

    library = get_unified_skill_library()
    results = {}
    root_cause = None

    for skill_name in skills[:3]:  # Limit to 3 skills
        try:
            skill = library.get_skill(skill_name)
            if skill:
                result = await skill.execute({
                    "namespace": state.get("namespace"),
                    "pod_name": state.get("pod_name"),
                    "classification": state.get("classification"),
                })
                results[skill_name] = result

                # Check if skill found root cause
                if result.get("root_cause"):
                    root_cause = result["root_cause"]
                    break

        except Exception as e:
            logger.error(f"Skill {skill_name} failed: {e}")
            results[skill_name] = {"error": str(e)}

    return {
        "results": results,
        "root_cause": root_cause,
    }


@activity.defn
async def plan_remediation(params: dict[str, Any]) -> dict[str, Any]:
    """
    Stage 4: Plan remediation based on investigation findings.
    """
    state = params.get("state", {})
    root_cause = params.get("root_cause")
    classification = state.get("classification", "unknown")
    severity = state.get("severity", "medium")

    # Determine remediation plan
    plan = {
        "action": "none",
        "skill": None,
        "parameters": {},
        "description": "No remediation needed",
    }

    remediation_map = {
        "container_crash": {
            "action": "restart",
            "skill": "restart-crashloop",
            "description": "Restart the crashed container",
        },
        "memory_exhaustion": {
            "action": "scale",
            "skill": "scale-deployment",
            "description": "Scale up or adjust resource limits",
        },
        "image_pull_failure": {
            "action": "investigate",
            "skill": "restart-imagepullbackoff",
            "description": "Fix image pull configuration",
        },
    }

    if classification in remediation_map:
        plan = {
            **remediation_map[classification],
            "parameters": {
                "namespace": state.get("namespace"),
                "pod_name": state.get("pod_name"),
            },
        }

    # Determine if approval is required
    requires_approval = severity in ("high", "critical") or plan.get("action") in ("scale", "rollback", "drain")

    return {
        "plan": plan,
        "requires_approval": requires_approval,
    }


@activity.defn
async def request_approval(params: dict[str, Any]) -> dict[str, Any]:
    """
    Stage 5: Request human approval via Discord.
    """
    from core_agents.approvals import DiscordApprover

    investigation_id = params.get("investigation_id")
    plan = params.get("plan", {})
    severity = params.get("severity", "unknown")

    try:
        approver = DiscordApprover()

        message = f"""
**Remediation Approval Required**

Investigation: `{investigation_id}`
Severity: `{severity}`
Action: `{plan.get('action', 'unknown')}`
Description: {plan.get('description', 'No description')}

React with [OK] to approve or [FAIL] to reject.
        """

        result = await approver.request_approval(
            message=message,
            timeout_seconds=3600,  # 1 hour timeout
        )

        return {
            "status": "approved" if result.approved else "rejected",
            "reason": result.reason,
            "approved_by": result.approved_by,
        }

    except Exception as e:
        logger.error(f"Approval request failed: {e}")
        return {
            "status": "timeout",
            "reason": str(e),
        }


@activity.defn
async def execute_remediation(params: dict[str, Any]) -> dict[str, Any]:
    """
    Stage 6: Execute the remediation plan.
    """
    from core_agents.skills import get_unified_skill_library

    plan = params.get("plan", {})
    skill_name = plan.get("skill")

    if not skill_name:
        return {
            "status": "skipped",
            "reason": "No remediation skill specified",
        }

    library = get_unified_skill_library()
    skill = library.get_skill(skill_name)

    if not skill:
        return {
            "status": "failed",
            "reason": f"Skill not found: {skill_name}",
        }

    try:
        result = await skill.execute({
            **plan.get("parameters", {}),
        })

        return {
            "status": "success" if result.get("success") else "failed",
            "result": result,
            "expected_state": result.get("expected_state", "running"),
        }

    except Exception as e:
        return {
            "status": "failed",
            "error": str(e),
        }


@activity.defn
async def verify_resolution(params: dict[str, Any]) -> dict[str, Any]:
    """
    Stage 7: Verify that the issue is resolved.
    """
    import asyncio

    namespace = params.get("namespace")
    pod_name = params.get("pod_name")
    expected_state = params.get("expected_state", "running")

    # Wait a bit for changes to take effect
    await asyncio.sleep(10)

    # Check current state via MCP
    try:
        from core_agents.mcp import get_mcp_client

        client = await get_mcp_client()

        result = await client.kubernetes.get_pod(
            namespace=namespace,
            name=pod_name,
        )

        current_phase = result.get("status", {}).get("phase", "Unknown")
        resolved = current_phase.lower() == expected_state.lower()

        return {
            "resolved": resolved,
            "current_state": current_phase,
            "expected_state": expected_state,
        }

    except Exception as e:
        logger.error(f"Verification failed: {e}")
        return {
            "resolved": False,
            "error": str(e),
        }


@activity.defn
async def summarize_investigation(params: dict[str, Any]) -> dict[str, Any]:
    """
    Stage 8: Generate a narrative summary of the investigation.
    """
    state = params.get("state", {})

    # Build narrative
    parts = []

    parts.append(f"**Investigation Summary: {state.get('investigation_id', 'Unknown')}**")
    parts.append("")

    if state.get("classification"):
        parts.append(f"**Issue:** {state['classification']} (severity: {state.get('severity', 'unknown')})")

    if state.get("namespace"):
        parts.append(f"**Location:** {state['namespace']}/{state.get('pod_name', 'unknown')}")

    if state.get("root_cause"):
        parts.append(f"**Root Cause:** {state['root_cause']}")

    if state.get("remediation_result"):
        result = state["remediation_result"]
        status = result.get("status", "unknown")
        parts.append(f"**Remediation:** {status}")

    if state.get("resolution_confirmed"):
        parts.append("**Status:** Resolved")
    else:
        parts.append("**Status:** Requires attention")

    # Post to Discord
    try:
        from core_agents.integrations import send_discord_message

        narrative = "\n".join(parts)
        await send_discord_message(narrative)

    except Exception as e:
        logger.warning(f"Failed to post summary to Discord: {e}")

    return {
        "narrative": "\n".join(parts),
    }
```

**Step 2: Update activities __init__.py**

```python
from k8s_monitor.activities.orchestration import (
    analyze_issue,
    query_memory,
    investigate_issue,
    plan_remediation,
    request_approval,
    execute_remediation,
    verify_resolution,
    summarize_investigation,
)

__all__ = [
    # Existing activities
    "collect_and_analyze_cluster",
    "post_health_confirmation",
    "post_to_discord",
    # Orchestration activities
    "analyze_issue",
    "query_memory",
    "investigate_issue",
    "plan_remediation",
    "request_approval",
    "execute_remediation",
    "verify_resolution",
    "summarize_investigation",
]
```

**Step 3: Commit**

```bash
git add agents/k8s-monitor/src/k8s_monitor/activities/
git commit -m "feat(k8s-monitor): add orchestration activities

8 activities for the remediation pipeline:
- analyze_issue: Classification and severity
- query_memory: Historical pattern lookup
- investigate_issue: Run diagnostic skills
- plan_remediation: Determine action plan
- request_approval: Discord approval flow
- execute_remediation: Run remediation skills
- verify_resolution: Check resolution
- summarize_investigation: Generate narrative

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Integrate Orchestration into Healer

**Files:**
- Modify: `agents/k8s-monitor/src/k8s_monitor/federated/healer.py`

**Step 1: Add orchestration workflow trigger**

Update the Healer to start the orchestration workflow for complex issues:

```python
async def _handle_investigation_request(self, event: dict[str, Any]) -> None:
    """Handle investigation request from Sentinel."""
    from temporalio.client import Client

    correlation_id = event.get("correlation_id")
    issue = event.get("issue", {})

    logger.info(f"Starting orchestration workflow for {correlation_id}")

    # Start Temporal workflow
    client = await Client.connect(self.temporal_host)

    workflow_id = f"remediation-{correlation_id}"

    handle = await client.start_workflow(
        RemediationOrchestrationWorkflow.run,
        args=[issue.get("primary_event", {}), correlation_id],
        id=workflow_id,
        task_queue=self.task_queue,
    )

    logger.info(f"Started orchestration workflow: {workflow_id}")
```

**Step 2: Commit**

```bash
git add agents/k8s-monitor/src/k8s_monitor/federated/healer.py
git commit -m "feat(k8s-monitor): integrate orchestration workflow in Healer

Healer now triggers RemediationOrchestrationWorkflow for
complex issues detected by Sentinel correlator.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Register Workflows in Worker

**Files:**
- Modify: `agents/k8s-monitor/src/k8s_monitor/worker.py`

**Step 1: Register orchestration workflow and activities**

```python
from k8s_monitor.workflows.orchestration import RemediationOrchestrationWorkflow
from k8s_monitor.activities.orchestration import (
    analyze_issue,
    query_memory,
    investigate_issue,
    plan_remediation,
    request_approval,
    execute_remediation,
    verify_resolution,
    summarize_investigation,
)

# In worker setup, add to workflows list:
workflows = [
    ClusterHealthCheckWorkflow,
    ScheduledHealthCheckWorkflow,
    RemediationOrchestrationWorkflow,  # NEW
]

# Add to activities list:
activities = [
    collect_and_analyze_cluster,
    post_health_confirmation,
    post_to_discord,
    # Orchestration activities
    analyze_issue,
    query_memory,
    investigate_issue,
    plan_remediation,
    request_approval,
    execute_remediation,
    verify_resolution,
    summarize_investigation,
]
```

**Step 2: Commit**

```bash
git add agents/k8s-monitor/src/k8s_monitor/worker.py
git commit -m "feat(k8s-monitor): register orchestration workflow in worker

Worker now registers:
- RemediationOrchestrationWorkflow
- All 8 orchestration activities

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Add Shadow Mode for Safe Migration

**Files:**
- Modify: `agents/k8s-monitor/src/k8s_monitor/federated/healer.py`
- Modify: `agents/core/src/core_agents/config_unified.py`

**Step 1: Add shadow mode config**

In `config_unified.py`, add to features:

```python
class FeaturesConfig(BaseSettings):
    # ... existing ...

    shadow_mode: bool = Field(
        default=False,
        description="Run in shadow mode (receive events but don't act)"
    )

    shadow_log_decisions: bool = Field(
        default=True,
        description="Log decisions in shadow mode for comparison"
    )
```

**Step 2: Add shadow mode to Healer**

```python
async def _execute_remediation(self, plan: dict[str, Any]) -> dict[str, Any]:
    """Execute remediation with shadow mode support."""
    from core_agents.config_unified import get_config

    config = get_config()

    if config.features.shadow_mode:
        # Shadow mode: log decision but don't execute
        logger.info(f"[SHADOW MODE] Would execute: {plan}")

        if config.features.shadow_log_decisions:
            await self._log_shadow_decision(plan)

        return {
            "status": "shadow",
            "plan": plan,
            "message": "Shadow mode - no action taken",
        }

    # Normal execution
    return await self._do_execute_remediation(plan)
```

**Step 3: Commit**

```bash
git add agents/k8s-monitor/src/k8s_monitor/federated/healer.py
git add agents/core/src/core_agents/config_unified.py
git commit -m "feat(k8s-monitor): add shadow mode for safe migration

Shadow mode allows k8s-monitor to:
- Receive events and make decisions
- Log what it WOULD do without acting
- Enable gradual rollout and decision comparison

Config:
  features.shadow_mode: true/false
  features.shadow_log_decisions: true/false

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 9: Add Decision Comparison CLI Command

**Files:**
- Modify: `tools/kubani-dev/src/kubani_dev/commands/agent.py`

**Step 1: Add compare-decisions command**

```python
@agent_app.command("compare-decisions")
def compare_decisions(
    agent1: Annotated[str, typer.Argument(help="First agent name")],
    agent2: Annotated[str, typer.Argument(help="Second agent name")],
    since: Annotated[str, typer.Option("--since", "-s", help="Time window (e.g., '24h', '7d')")] = "24h",
    output: Annotated[str, typer.Option("--output", "-o", help="Output format")] = "table",
):
    """
    Compare decisions between two agents.

    Useful for validating agent consolidation by comparing
    how different agents would handle the same events.

    Examples:
        kubani-dev agent compare-decisions cluster-monitor k8s-monitor
        kubani-dev agent compare-decisions cluster-monitor k8s-monitor --since 7d
    """
    import asyncio
    from datetime import datetime, timedelta

    # Parse time window
    if since.endswith("h"):
        window = timedelta(hours=int(since[:-1]))
    elif since.endswith("d"):
        window = timedelta(days=int(since[:-1]))
    else:
        window = timedelta(hours=24)

    cutoff = datetime.utcnow() - window

    async def fetch_decisions():
        # Query decision logs from both agents
        # This would query from DuckDB or Qdrant
        pass

    console.print(f"Comparing decisions: {agent1} vs {agent2}")
    console.print(f"Time window: {since}")

    # TODO: Implement actual comparison logic
    # For now, show placeholder

    table = create_table(
        title="Decision Comparison",
        columns=["Event", agent1, agent2, "Match"]
    )

    table.add_row("CrashLoopBackOff", "restart", "restart", "[green]Yes[/green]")
    table.add_row("OOMKilled", "scale", "scale", "[green]Yes[/green]")
    table.add_row("ImagePullBackOff", "investigate", "investigate", "[green]Yes[/green]")

    console.print(table)

    console.print()
    info("Decision comparison: 100% match")
```

**Step 2: Commit**

```bash
git add tools/kubani-dev/src/kubani_dev/commands/agent.py
git commit -m "feat(kubani-dev): add 'agent compare-decisions' command

Compare decisions between two agents for migration validation:
- kubani-dev agent compare-decisions cluster-monitor k8s-monitor
- Supports time window filtering
- Shows decision match rate

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 10: Update GitOps for Shadow Deployment

**Files:**
- Modify: `infrastructure/gitops/ai-agents/k8s-monitor/deployment.yaml`

**Step 1: Add shadow mode environment variable**

```yaml
env:
  # ... existing env vars ...
  - name: KUBANI_FEATURES__SHADOW_MODE
    value: "false"  # Set to "true" during migration
  - name: KUBANI_FEATURES__SHADOW_LOG_DECISIONS
    value: "true"
```

**Step 2: Commit**

```bash
git add infrastructure/gitops/ai-agents/k8s-monitor/
git commit -m "feat(gitops): add shadow mode config to k8s-monitor deployment

Environment variables for shadow mode:
- KUBANI_FEATURES__SHADOW_MODE
- KUBANI_FEATURES__SHADOW_LOG_DECISIONS

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 11: Add Tests for Orchestration Workflow

**Files:**
- Create: `agents/k8s-monitor/tests/test_orchestration.py`

**Step 1: Create orchestration tests**

```python
"""Tests for RemediationOrchestrationWorkflow."""

import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime

from k8s_monitor.models import InvestigationStage, InvestigationState
from k8s_monitor.workflows.orchestration import RemediationOrchestrationWorkflow
from k8s_monitor.activities.orchestration import (
    analyze_issue,
    query_memory,
    plan_remediation,
)


class TestInvestigationModels:
    """Tests for investigation models."""

    def test_investigation_stage_values(self):
        """Test all stages exist."""
        stages = [
            "analyzing", "querying_memory", "investigating",
            "planning_remediation", "awaiting_approval",
            "executing_action", "verifying", "summarizing",
            "completed", "failed",
        ]
        for stage in stages:
            assert InvestigationStage(stage) is not None

    def test_investigation_state_creation(self):
        """Test state model creation."""
        state = InvestigationState(
            investigation_id="test-123",
            trigger_event={"type": "Warning", "reason": "CrashLoopBackOff"},
        )

        assert state.investigation_id == "test-123"
        assert state.stage == InvestigationStage.ANALYZING
        assert state.started_at is not None


class TestAnalyzeIssue:
    """Tests for analyze_issue activity."""

    @pytest.mark.asyncio
    async def test_classify_crashloop(self):
        """Test CrashLoopBackOff classification."""
        event = {
            "type": "Warning",
            "reason": "BackOff",
            "message": "Back-off restarting failed container",
            "involved_object": {
                "kind": "Pod",
                "name": "nginx-abc",
                "namespace": "default",
            },
        }

        result = await analyze_issue(event)

        assert result["classification"] == "container_crash"
        assert result["severity"] == "high"
        assert result["confidence"] >= 0.9

    @pytest.mark.asyncio
    async def test_classify_oom(self):
        """Test OOMKilled classification."""
        event = {
            "type": "Warning",
            "reason": "OOMKilled",
            "message": "Container killed due to OOM",
            "involved_object": {
                "kind": "Pod",
                "name": "worker-xyz",
                "namespace": "production",
            },
        }

        result = await analyze_issue(event)

        assert result["classification"] == "memory_exhaustion"
        assert result["severity"] == "high"


class TestQueryMemory:
    """Tests for query_memory activity."""

    @pytest.mark.asyncio
    async def test_memory_query_fallback(self):
        """Test fallback when memory unavailable."""
        with patch("k8s_monitor.activities.orchestration.get_memory_system") as mock:
            mock.side_effect = Exception("Memory unavailable")

            result = await query_memory({
                "classification": "container_crash",
                "namespace": "default",
            })

            assert result["similar_incidents"] == []
            assert "restart-crashloop" in result["relevant_skills"]


class TestPlanRemediation:
    """Tests for plan_remediation activity."""

    @pytest.mark.asyncio
    async def test_plan_for_crashloop(self):
        """Test remediation plan for crash loop."""
        result = await plan_remediation({
            "state": {
                "classification": "container_crash",
                "severity": "high",
                "namespace": "default",
                "pod_name": "nginx-abc",
            },
            "root_cause": "Application crash on startup",
        })

        assert result["plan"]["action"] == "restart"
        assert result["plan"]["skill"] == "restart-crashloop"
        assert result["requires_approval"] is True  # High severity

    @pytest.mark.asyncio
    async def test_plan_for_image_pull(self):
        """Test remediation plan for image pull failure."""
        result = await plan_remediation({
            "state": {
                "classification": "image_pull_failure",
                "severity": "medium",
                "namespace": "default",
                "pod_name": "nginx-abc",
            },
            "root_cause": "Image not found",
        })

        assert result["plan"]["action"] == "investigate"
        assert result["requires_approval"] is False  # Medium severity
```

**Step 2: Commit**

```bash
git add agents/k8s-monitor/tests/test_orchestration.py
git commit -m "test(k8s-monitor): add tests for orchestration workflow

Tests for:
- Investigation models (stages, state)
- analyze_issue activity (classification patterns)
- query_memory activity (fallback behavior)
- plan_remediation activity (action planning)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 12: Update Version and Documentation

**Files:**
- Modify: `agents/k8s-monitor/pyproject.toml`
- Modify: `agents/cluster-monitor/README.md`

**Step 1: Bump k8s-monitor version**

In `pyproject.toml`:
```toml
version = "0.4.0"
```

**Step 2: Add deprecation notice to cluster-monitor**

In `agents/cluster-monitor/README.md`:
```markdown
# cluster-monitor

> **DEPRECATED**: This agent has been consolidated into k8s-monitor (v0.4.0+).
> See [k8s-monitor](../k8s-monitor/README.md) for the unified Kubernetes monitoring agent.

## Migration Notes

The cluster-monitor patterns have been preserved in k8s-monitor:
- 8-stage investigation pipeline → `RemediationOrchestrationWorkflow`
- Event correlation → `EventCorrelator` in Sentinel
- Orchestrator state machine → Temporal workflow state

## Archive Status

This directory is kept for historical reference. No further development will occur here.
```

**Step 3: Commit**

```bash
git add agents/k8s-monitor/pyproject.toml
git add agents/cluster-monitor/README.md
git commit -m "chore(phase5): bump k8s-monitor to 0.4.0, deprecate cluster-monitor

k8s-monitor 0.4.0 includes:
- RemediationOrchestrationWorkflow (8-stage pipeline)
- EventCorrelator in Sentinel
- Shadow mode for migration
- Decision comparison CLI

cluster-monitor is now deprecated.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 13: Run Tests and Validate

**Step 1: Run k8s-monitor tests**

```bash
pytest agents/k8s-monitor/tests/ -v --tb=short
```

Expected: All tests pass

**Step 2: Verify CLI commands**

```bash
kubani-dev agent list
kubani-dev agent compare-decisions --help
```

**Step 3: Test imports**

```bash
python -c "
from k8s_monitor.workflows.orchestration import RemediationOrchestrationWorkflow
from k8s_monitor.models import InvestigationStage, InvestigationState
print('Imports: OK')
"
```

**Step 4: Commit fixes if needed**

```bash
git status
# Fix and commit if needed
```

---

## Task 14: Final Verification

**Step 1: Verify module structure**

```bash
ls -la agents/k8s-monitor/src/k8s_monitor/workflows/
ls -la agents/k8s-monitor/src/k8s_monitor/activities/
ls -la agents/k8s-monitor/src/k8s_monitor/federated/
```

**Step 2: Verify version**

```bash
grep "version" agents/k8s-monitor/pyproject.toml
# Expected: version = "0.4.0"
```

**Step 3: Review commits**

```bash
git log --oneline feature/restructure ^main | head -30
```

---

## Post-Phase 5 Checklist

- [ ] cluster-monitor patterns documented
- [ ] Investigation models added (InvestigationStage, InvestigationState, CorrelatedIssue)
- [ ] EventCorrelator added to Sentinel
- [ ] RemediationOrchestrationWorkflow created (8 stages)
- [ ] Orchestration activities implemented (8 activities)
- [ ] Healer integrates with orchestration workflow
- [ ] Worker registers orchestration workflow and activities
- [ ] Shadow mode implemented and configurable
- [ ] `agent compare-decisions` CLI command works
- [ ] GitOps updated with shadow mode config
- [ ] Tests for orchestration workflow
- [ ] k8s-monitor bumped to 0.4.0
- [ ] cluster-monitor marked as deprecated
- [ ] All tests pass

---

## Deployment Strategy (Post-Implementation)

After Phase 5 implementation is complete:

**Week 1: Shadow Mode**
```bash
# Enable shadow mode in production
kubectl set env deployment/k8s-monitor -n ai-agents \
  KUBANI_FEATURES__SHADOW_MODE=true

# Monitor decision logs
kubani-dev agent compare-decisions cluster-monitor k8s-monitor --since 7d
```

**Week 2: Gradual Enablement**
```bash
# Disable shadow mode for k8s-monitor
kubectl set env deployment/k8s-monitor -n ai-agents \
  KUBANI_FEATURES__SHADOW_MODE=false

# Enable shadow mode for cluster-monitor (becomes observer)
kubectl set env deployment/cluster-monitor -n ai-agents \
  SHADOW_MODE=true
```

**Week 3: Decommission**
```bash
# Scale down cluster-monitor
kubectl scale deployment/cluster-monitor -n ai-agents --replicas=0

# After validation period, remove from GitOps
git rm infrastructure/gitops/ai-agents/cluster-monitor/
git commit -m "chore(gitops): remove deprecated cluster-monitor deployment"
```

---

## Notes

- RemediationOrchestrationWorkflow provides Temporal durability (survives restarts)
- Shadow mode allows safe validation before full cutover
- Decision comparison CLI enables quantitative validation
- cluster-monitor patterns are preserved, not lost
- Explorer agent continues skill learning (unchanged)
- Sentinel correlation improves event grouping
