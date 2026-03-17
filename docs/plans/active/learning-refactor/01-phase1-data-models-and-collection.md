# Phase 1: Data Models and Collection Workflow

**Depends on:** Nothing (starting point)
**Produces:** `models.py`, `CollectExecutionsWorkflow`, collection activities, pipeline context

---

## 1.1 Data Models (`models.py`)

Create `kubani/syndicates/learning_system/models.py` with five core dataclasses and utility functions.

### ExecutionRecord

Represents a single workflow execution collected from Temporal. This is the raw data from Stage 1.

```python
"""
Learning System data models.

Five core models representing the learning pipeline stages:
1. ExecutionRecord — raw workflow execution from Temporal (Stage 1: Collect)
2. CriticEvaluation — individual execution scored by CriticAgent (Stage 2: Evaluate)
3. ReflectionInsight — cross-execution pattern from ReflectionAgent (Stage 3: Reflect)
4. ProposedImprovement — actionable improvement proposal (Stage 4: Improve)
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# =============================================================================
# Enums
# =============================================================================


class ExecutionStatus(str, Enum):
    """Temporal workflow execution status."""
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    TERMINATED = "terminated"


class ImprovementType(str, Enum):
    """Type of improvement proposal."""
    SKILL_NEW = "skill_new"           # Create a new skill
    SKILL_UPDATE = "skill_update"     # Modify an existing skill
    PROMPT_UPDATE = "prompt_update"   # Modify an agent prompt
    CONFIG_UPDATE = "config_update"   # Change agent/syndicate config
    ARCHITECTURE = "architecture"     # Structural change recommendation


class ImprovementStatus(str, Enum):
    """Lifecycle status of an improvement proposal."""
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    EXPIRED = "expired"


# =============================================================================
# Stage 1: ExecutionRecord
# =============================================================================


@dataclass
class ExecutionRecord:
    """A workflow execution collected from Temporal.

    Attributes:
        record_id: Unique ID for this record (deterministic from workflow_id + run_id).
        syndicate: Syndicate name (e.g., "k8s-monitor", "news-digest").
        workflow_type: Workflow class name (e.g., "K8sMonitorWorkflow").
        workflow_id: Temporal workflow ID.
        run_id: Temporal run ID.
        status: Execution outcome (completed, failed, etc.).
        started_at: When the workflow started.
        completed_at: When the workflow finished (None if still running).
        duration_ms: Execution duration in milliseconds.
        input_data: Workflow input (serialized).
        output_data: Workflow output (serialized, truncated to 5000 chars).
        error_message: Error message if failed.
        task_queue: Temporal task queue name.
        activity_count: Number of activities executed.
        collected_at: When this record was collected.
    """

    record_id: str
    syndicate: str
    workflow_type: str
    workflow_id: str
    run_id: str
    status: ExecutionStatus
    started_at: str  # ISO 8601
    completed_at: str | None
    duration_ms: int
    input_data: dict[str, Any] | None = None
    output_data: dict[str, Any] | None = None
    error_message: str | None = None
    task_queue: str = ""
    activity_count: int = 0
    collected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "record_id": self.record_id,
            "syndicate": self.syndicate,
            "workflow_type": self.workflow_type,
            "workflow_id": self.workflow_id,
            "run_id": self.run_id,
            "status": self.status.value,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "input_data": self.input_data,
            "output_data": self.output_data,
            "error_message": self.error_message,
            "task_queue": self.task_queue,
            "activity_count": self.activity_count,
            "collected_at": self.collected_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionRecord:
        """Create from dict."""
        return cls(
            record_id=data["record_id"],
            syndicate=data["syndicate"],
            workflow_type=data["workflow_type"],
            workflow_id=data["workflow_id"],
            run_id=data["run_id"],
            status=ExecutionStatus(data["status"]),
            started_at=data["started_at"],
            completed_at=data.get("completed_at"),
            duration_ms=data.get("duration_ms", 0),
            input_data=data.get("input_data"),
            output_data=data.get("output_data"),
            error_message=data.get("error_message"),
            task_queue=data.get("task_queue", ""),
            activity_count=data.get("activity_count", 0),
            collected_at=data.get("collected_at", ""),
        )


# =============================================================================
# Stage 2: CriticEvaluation
# =============================================================================


@dataclass
class CriticEvaluation:
    """A single execution evaluated by the CriticAgent.

    The Critic focuses on individual execution quality — did this specific
    workflow run accomplish its goal efficiently and correctly?

    Attributes:
        evaluation_id: Unique ID for this evaluation.
        record_id: Reference to the source ExecutionRecord.
        syndicate: Syndicate name (denormalized for querying).
        workflow_type: Workflow type (denormalized).
        status: Original execution status.
        duration_ms: Original duration.

        # Scores (0.0 to 1.0)
        overall_score: Composite quality score (weighted average).
        success_score: Did it accomplish its goal?
        efficiency_score: Was it fast / resource-efficient?
        quality_score: Was the output high quality?

        # Analysis
        summary: One-sentence summary of what happened.
        strengths: What went well in this specific execution.
        weaknesses: What went poorly in this specific execution.
        failure_category: If failed, category (timeout, mcp_error, llm_error, etc.).
        suggestions: Specific improvement suggestions for this execution type.

        evaluated_at: When this evaluation was created.
    """

    evaluation_id: str
    record_id: str
    syndicate: str
    workflow_type: str
    status: str
    duration_ms: int

    overall_score: float
    success_score: float
    efficiency_score: float
    quality_score: float

    summary: str
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    failure_category: str | None = None
    suggestions: list[str] = field(default_factory=list)

    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "evaluation_id": self.evaluation_id,
            "record_id": self.record_id,
            "syndicate": self.syndicate,
            "workflow_type": self.workflow_type,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "overall_score": self.overall_score,
            "success_score": self.success_score,
            "efficiency_score": self.efficiency_score,
            "quality_score": self.quality_score,
            "summary": self.summary,
            "strengths": self.strengths,
            "weaknesses": self.weaknesses,
            "failure_category": self.failure_category,
            "suggestions": self.suggestions,
            "evaluated_at": self.evaluated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CriticEvaluation:
        """Create from dict."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# =============================================================================
# Stage 3: ReflectionInsight
# =============================================================================


class InsightType(str, Enum):
    """Type of cross-execution insight identified by the ReflectionAgent."""
    PATTERN = "pattern"                  # Successful approach recurring across executions
    ANTI_PATTERN = "anti_pattern"        # Failure mode occurring repeatedly
    TREND = "trend"                      # Performance trending up or down over time
    SKILL_OPPORTUNITY = "skill_opportunity"  # Pattern suitable for codifying as a skill
    CROSS_AGENT = "cross_agent"          # Issue or pattern spanning multiple syndicates


@dataclass
class ReflectionInsight:
    """A cross-execution insight synthesized by the ReflectionAgent.

    The Reflection Agent operates on batches of CriticEvaluations, NOT
    individual executions. It looks for patterns, trends, and opportunities
    that only become visible when comparing across multiple evaluations.

    Attributes:
        insight_id: Unique ID for this insight.
        insight_type: Category of insight (pattern, anti_pattern, trend, etc.).
        title: Short descriptive title.
        description: Detailed explanation of the insight.
        affected_syndicates: Which syndicates this insight applies to.
        affected_workflow_types: Which workflow types are involved.
        evidence_ids: List of CriticEvaluation IDs that support this insight.
        occurrence_count: How many times this pattern was observed.
        confidence: How confident the agent is in this insight (0.0 to 1.0).
        impact: Estimated impact (low, medium, high, critical).
        suggested_action: What should be done about it.
        first_seen: When this pattern was first observed.
        last_seen: When this pattern was most recently observed.
        reflected_at: When this insight was created.
    """

    insight_id: str
    insight_type: InsightType
    title: str
    description: str
    affected_syndicates: list[str] = field(default_factory=list)
    affected_workflow_types: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    occurrence_count: int = 0
    confidence: float = 0.0
    impact: str = "medium"  # low, medium, high, critical
    suggested_action: str = ""
    first_seen: str = ""
    last_seen: str = ""
    reflected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "insight_id": self.insight_id,
            "insight_type": self.insight_type.value,
            "title": self.title,
            "description": self.description,
            "affected_syndicates": self.affected_syndicates,
            "affected_workflow_types": self.affected_workflow_types,
            "evidence_ids": self.evidence_ids,
            "occurrence_count": self.occurrence_count,
            "confidence": self.confidence,
            "impact": self.impact,
            "suggested_action": self.suggested_action,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "reflected_at": self.reflected_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReflectionInsight:
        """Create from dict."""
        d = dict(data)
        if "insight_type" in d:
            d["insight_type"] = InsightType(d["insight_type"])
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# =============================================================================
# Stage 3: ProposedImprovement
# =============================================================================


@dataclass
class ProposedImprovement:
    """An actionable improvement proposal from the ImprovementAgent.

    Attributes:
        proposal_id: Unique ID for this proposal.
        improvement_type: What kind of change (skill, prompt, config, architecture).
        target_agent: Which agent/syndicate this targets.
        title: Short title for the proposal.
        description: Detailed description of what to change and why.
        rationale: Evidence-based reasoning.
        evidence_ids: List of AnalyzedExecution analysis_ids that support this.
        confidence: How confident the agent is this will help (0.0 to 1.0).
        estimated_impact: Expected improvement description.

        # Content (the actual change)
        content: The proposed change content (skill markdown, prompt text, config YAML, etc.).
        target_file: File path the change applies to (if applicable).

        # Lifecycle
        status: Current proposal status.
        created_at: When proposed.
        resolved_at: When approved/rejected/expired.
        resolution_note: Why it was approved/rejected.
    """

    proposal_id: str
    improvement_type: ImprovementType
    target_agent: str
    title: str
    description: str
    rationale: str
    evidence_ids: list[str] = field(default_factory=list)
    confidence: float = 0.0
    estimated_impact: str = ""

    content: str = ""
    target_file: str = ""

    status: ImprovementStatus = ImprovementStatus.PROPOSED
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved_at: str | None = None
    resolution_note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "proposal_id": self.proposal_id,
            "improvement_type": self.improvement_type.value,
            "target_agent": self.target_agent,
            "title": self.title,
            "description": self.description,
            "rationale": self.rationale,
            "evidence_ids": self.evidence_ids,
            "confidence": self.confidence,
            "estimated_impact": self.estimated_impact,
            "content": self.content,
            "target_file": self.target_file,
            "status": self.status.value,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
            "resolution_note": self.resolution_note,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProposedImprovement:
        """Create from dict."""
        d = dict(data)
        if "improvement_type" in d:
            d["improvement_type"] = ImprovementType(d["improvement_type"])
        if "status" in d:
            d["status"] = ImprovementStatus(d["status"])
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# =============================================================================
# Utility Functions
# =============================================================================


def make_record_id(workflow_id: str, run_id: str) -> str:
    """Create a deterministic record ID from workflow + run IDs.

    This ensures the same execution always produces the same record_id,
    enabling idempotent collection (deduplication).

    >>> make_record_id("k8s-monitor-scheduled-2026-03-09T12:00:00Z", "abc123")
    'exec-<deterministic-uuid>'
    """
    seed = f"{workflow_id}:{run_id}"
    return f"exec-{uuid.uuid5(uuid.NAMESPACE_DNS, seed)}"


def make_evaluation_id(record_id: str) -> str:
    """Create a deterministic evaluation ID from a record ID.

    >>> make_evaluation_id("exec-12345")
    'eval-<deterministic-uuid>'
    """
    return f"eval-{uuid.uuid5(uuid.NAMESPACE_DNS, record_id)}"


def make_insight_id(title: str, insight_type: str) -> str:
    """Create a deterministic insight ID.

    >>> make_insight_id("MCP timeout recurring", "anti_pattern")
    'insight-<deterministic-uuid>'
    """
    seed = f"{title}:{insight_type}"
    return f"insight-{uuid.uuid5(uuid.NAMESPACE_DNS, seed)}"


def make_proposal_id(title: str, target: str) -> str:
    """Create a deterministic proposal ID.

    >>> make_proposal_id("Add timeout retry skill", "k8s-monitor")
    'proposal-<deterministic-uuid>'
    """
    seed = f"{title}:{target}"
    return f"proposal-{uuid.uuid5(uuid.NAMESPACE_DNS, seed)}"


def make_dedup_key(workflow_id: str, run_id: str) -> str:
    """Create a dedup cache key for an execution record.

    Used with Memory MCP's mark_seen/check_seen to avoid re-collecting
    the same execution.

    >>> make_dedup_key("k8s-monitor-scheduled-2026-03-09", "abc")
    'learning:exec:k8s-monitor-scheduled-2026-03-09:abc'
    """
    return f"learning:exec:{workflow_id}:{run_id}"


def infer_syndicate_from_task_queue(task_queue: str) -> str:
    """Infer syndicate name from Temporal task queue.

    >>> infer_syndicate_from_task_queue("k8s-monitor")
    'k8s-monitor'
    >>> infer_syndicate_from_task_queue("news-digest")
    'news-digest'
    >>> infer_syndicate_from_task_queue("unknown-queue")
    'unknown-queue'
    """
    return task_queue


def map_temporal_status(status_str: str) -> ExecutionStatus:
    """Map Temporal workflow status string to ExecutionStatus enum.

    The Temporal MCP server returns status as strings like "COMPLETED",
    "FAILED", "TIMED_OUT", etc.

    >>> map_temporal_status("COMPLETED")
    ExecutionStatus.COMPLETED
    >>> map_temporal_status("WORKFLOW_EXECUTION_STATUS_COMPLETED")
    ExecutionStatus.COMPLETED
    """
    normalized = status_str.upper()

    # Handle both short ("COMPLETED") and long ("WORKFLOW_EXECUTION_STATUS_COMPLETED") forms
    if "COMPLETED" in normalized:
        return ExecutionStatus.COMPLETED
    if "FAILED" in normalized:
        return ExecutionStatus.FAILED
    if "TIMED_OUT" in normalized or "TIMEOUT" in normalized:
        return ExecutionStatus.TIMED_OUT
    if "CANCELLED" in normalized or "CANCELED" in normalized:
        return ExecutionStatus.CANCELLED
    if "TERMINATED" in normalized:
        return ExecutionStatus.TERMINATED

    # Default to failed for unknown statuses
    return ExecutionStatus.FAILED
```

### Key Design Decisions

1. **Deterministic IDs** — `make_record_id()` uses UUID5 so re-collecting the same execution produces the same ID. This makes collection idempotent.
2. **Denormalized fields** — `CriticEvaluation` carries `syndicate` and `workflow_type` from the source record so queries don't need joins.
3. **Clear stage separation** — `CriticEvaluation` is per-execution (Critic's output), `ReflectionInsight` is cross-execution (Reflection's output). The Critic never looks across executions; the Reflection agent never scores individual runs.
4. **Simple enums** — `ExecutionStatus` maps from Temporal; `InsightType` classifies cross-execution patterns; `ImprovementType` covers actionable changes.
5. **`to_dict`/`from_dict`** — All models serialize cleanly for Temporal workflow I/O and Memory MCP storage.

---

## 1.2 Pipeline Context Protocol

Create `kubani/syndicates/learning_system/pipeline/context.py`:

```python
"""LearningPipelineContext protocol — context injection for the collection pipeline.

Concrete implementations:
    - TemporalContext: Uses Temporal activities for production.
    - LocalContext: Uses mock callables for testing.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LearningPipelineContext(Protocol):
    """Protocol for all I/O in the collection pipeline."""

    # -------------------------------------------------------------------------
    # I/O: Temporal Query
    # -------------------------------------------------------------------------

    async def list_recent_workflows(
        self,
        namespace: str,
        hours_back: int = 1,
    ) -> list[dict[str, Any]]:
        """List recent workflow executions from a Temporal namespace.

        Args:
            namespace: Temporal namespace to query (e.g., "k8s-monitor").
            hours_back: How far back to look.

        Returns:
            List of workflow summary dicts from Temporal MCP.
        """
        ...

    async def get_workflow_detail(
        self,
        workflow_id: str,
        namespace: str,
    ) -> dict[str, Any]:
        """Get detailed info about a specific workflow execution.

        Args:
            workflow_id: Temporal workflow ID.
            namespace: Temporal namespace.

        Returns:
            Workflow detail dict including input/output/history.
        """
        ...

    # -------------------------------------------------------------------------
    # I/O: Deduplication
    # -------------------------------------------------------------------------

    async def check_seen(
        self,
        dedup_keys: list[str],
    ) -> dict[str, bool]:
        """Check which execution records have already been collected.

        Args:
            dedup_keys: List of dedup cache keys.

        Returns:
            Dict mapping each key to True (already collected) or False (new).
        """
        ...

    async def mark_seen(
        self,
        dedup_keys: list[str],
        ttl_hours: int = 168,
    ) -> None:
        """Mark execution records as collected.

        Args:
            dedup_keys: Keys to mark.
            ttl_hours: How long to remember (default 7 days).
        """
        ...

    # -------------------------------------------------------------------------
    # I/O: Storage
    # -------------------------------------------------------------------------

    async def store_records(
        self,
        records: list[dict[str, Any]],
    ) -> int:
        """Store execution records in Memory MCP.

        Args:
            records: List of ExecutionRecord dicts.

        Returns:
            Number of records stored.
        """
        ...

    # -------------------------------------------------------------------------
    # I/O: Trigger downstream
    # -------------------------------------------------------------------------

    async def trigger_evaluation(
        self,
        record_ids: list[str],
    ) -> None:
        """Trigger evaluation workflow (Critic) for a batch of records.

        Fire-and-forget: collection does not wait for evaluation.

        Args:
            record_ids: List of ExecutionRecord IDs to evaluate.
        """
        ...

    # -------------------------------------------------------------------------
    # Observability
    # -------------------------------------------------------------------------

    def set_status(self, message: str, phase: str = "") -> None:
        """Report current pipeline status."""
        ...

    def log_event(self, kind: str, message: str, **data: Any) -> None:
        """Log a structured event."""
        ...
```

### TemporalContext Implementation

Create `kubani/syndicates/learning_system/pipeline/contexts/temporal_context.py`:

```python
"""Temporal-backed context for the learning collection pipeline."""

from __future__ import annotations

import logging
from typing import Any

from temporalio import workflow

logger = logging.getLogger(__name__)


class TemporalContext:
    """Production context using Temporal activities."""

    def __init__(self, workflow_mixin: Any) -> None:
        self._wf = workflow_mixin

    async def list_recent_workflows(
        self,
        namespace: str,
        hours_back: int = 1,
    ) -> list[dict[str, Any]]:
        from kubani.syndicates.learning_system.activities import (
            list_recent_workflows_activity,
        )

        return await workflow.execute_activity(
            list_recent_workflows_activity,
            {"namespace": namespace, "hours_back": hours_back},
            start_to_close_timeout=workflow.timedelta(minutes=5),
            retry_policy=workflow.RetryPolicy(
                maximum_attempts=2,
                initial_interval=workflow.timedelta(seconds=5),
            ),
        )

    async def get_workflow_detail(
        self,
        workflow_id: str,
        namespace: str,
    ) -> dict[str, Any]:
        from kubani.syndicates.learning_system.activities import (
            get_workflow_detail_activity,
        )

        return await workflow.execute_activity(
            get_workflow_detail_activity,
            {"workflow_id": workflow_id, "namespace": namespace},
            start_to_close_timeout=workflow.timedelta(minutes=2),
            retry_policy=workflow.RetryPolicy(
                maximum_attempts=2,
                initial_interval=workflow.timedelta(seconds=5),
            ),
        )

    async def check_seen(self, dedup_keys: list[str]) -> dict[str, bool]:
        from kubani.syndicates.learning_system.activities import (
            check_seen_activity,
        )

        return await workflow.execute_activity(
            check_seen_activity,
            {"dedup_keys": dedup_keys},
            start_to_close_timeout=workflow.timedelta(minutes=2),
        )

    async def mark_seen(self, dedup_keys: list[str], ttl_hours: int = 168) -> None:
        from kubani.syndicates.learning_system.activities import (
            mark_seen_activity,
        )

        await workflow.execute_activity(
            mark_seen_activity,
            {"dedup_keys": dedup_keys, "ttl_hours": ttl_hours},
            start_to_close_timeout=workflow.timedelta(minutes=2),
        )

    async def store_records(self, records: list[dict[str, Any]]) -> int:
        from kubani.syndicates.learning_system.activities import (
            store_records_activity,
        )

        result = await workflow.execute_activity(
            store_records_activity,
            {"records": records},
            start_to_close_timeout=workflow.timedelta(minutes=5),
        )
        return result.get("stored_count", 0)

    async def trigger_evaluation(self, record_ids: list[str]) -> None:
        from kubani.syndicates.learning_system.workflows.evaluate import (
            EvaluateExecutionsWorkflow,
        )

        await workflow.start_child_workflow(
            EvaluateExecutionsWorkflow.run,
            {"record_ids": record_ids},
            id=f"learning-evaluate-{workflow.now().strftime('%Y%m%dT%H%M%S')}",
        )

    def set_status(self, message: str, phase: str = "") -> None:
        if hasattr(self._wf, "_set_status"):
            from kubani.framework.temporal.workflows import WorkflowStatus
            self._wf._set_status(WorkflowStatus.RUNNING, message, phase=phase)

    def log_event(self, kind: str, message: str, **data: Any) -> None:
        if hasattr(self._wf, "_log_event"):
            self._wf._log_event(kind, message, **data)
```

### LocalContext Implementation

Create `kubani/syndicates/learning_system/pipeline/contexts/local_context.py`:

```python
"""Local mock context for testing the learning pipeline without services."""

from __future__ import annotations

import logging
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


class LocalContext:
    """Test context with injectable mock callables.

    Example:
        ctx = LocalContext(
            workflow_lister=my_mock_lister,
            detail_fetcher=my_mock_detail_fetcher,
        )
        result = await run_collection_pipeline(ctx, namespaces=["k8s-monitor"])
    """

    def __init__(
        self,
        workflow_lister: Callable[..., Awaitable[list[dict[str, Any]]]] | None = None,
        detail_fetcher: Callable[..., Awaitable[dict[str, Any]]] | None = None,
        seen_checker: Callable[..., Awaitable[dict[str, bool]]] | None = None,
        record_storer: Callable[..., Awaitable[int]] | None = None,
    ) -> None:
        self._workflow_lister = workflow_lister
        self._detail_fetcher = detail_fetcher
        self._seen_checker = seen_checker
        self._record_storer = record_storer
        self._stored: list[dict[str, Any]] = []
        self._seen_keys: set[str] = set()
        self._evaluation_triggered: list[list[str]] = []

    async def list_recent_workflows(
        self, namespace: str, hours_back: int = 1
    ) -> list[dict[str, Any]]:
        if self._workflow_lister:
            return await self._workflow_lister(namespace, hours_back)
        return []

    async def get_workflow_detail(
        self, workflow_id: str, namespace: str
    ) -> dict[str, Any]:
        if self._detail_fetcher:
            return await self._detail_fetcher(workflow_id, namespace)
        return {}

    async def check_seen(self, dedup_keys: list[str]) -> dict[str, bool]:
        if self._seen_checker:
            return await self._seen_checker(dedup_keys)
        return {k: k in self._seen_keys for k in dedup_keys}

    async def mark_seen(self, dedup_keys: list[str], ttl_hours: int = 168) -> None:
        self._seen_keys.update(dedup_keys)

    async def store_records(self, records: list[dict[str, Any]]) -> int:
        if self._record_storer:
            return await self._record_storer(records)
        self._stored.extend(records)
        return len(records)

    async def trigger_evaluation(self, record_ids: list[str]) -> None:
        self._evaluation_triggered.append(record_ids)
        logger.info(f"[LocalContext] Would trigger evaluation for {len(record_ids)} records")

    def set_status(self, message: str, phase: str = "") -> None:
        logger.info(f"[LocalContext] [{phase}] {message}")

    def log_event(self, kind: str, message: str, **data: Any) -> None:
        logger.info(f"[LocalContext] {kind}: {message} {data}")
```

---

## 1.3 Collection Pipeline Logic

Create `kubani/syndicates/learning_system/pipeline/__init__.py`:

```python
"""Learning system collection pipeline.

Exports the main pipeline function for use by workflows.
"""

from kubani.syndicates.learning_system.pipeline.collect import run_collection_pipeline

__all__ = ["run_collection_pipeline"]
```

Create `kubani/syndicates/learning_system/pipeline/collect.py`:

```python
"""Collection pipeline — pure logic, no Temporal imports.

This module implements the Stage 1 collection logic. It:
1. Queries Temporal for recent workflow executions across all monitored namespaces.
2. Deduplicates against previously collected records.
3. Converts Temporal workflow data to ExecutionRecord dicts.
4. Stores new records in Memory MCP.
5. Triggers Stage 2 (analysis) for the new batch.

All I/O is delegated to the LearningPipelineContext, making this
fully testable with LocalContext.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from kubani.syndicates.learning_system.models import (
    ExecutionRecord,
    ExecutionStatus,
    make_dedup_key,
    make_record_id,
    map_temporal_status,
    infer_syndicate_from_task_queue,
)

logger = logging.getLogger(__name__)

# Temporal namespaces to monitor (each syndicate runs in its own namespace)
MONITORED_NAMESPACES = [
    "k8s-monitor",
    "news-digest",
    "nexus",
    "learning-system",  # Monitor ourselves too
]


@dataclass
class CollectionResult:
    """Result of a collection pipeline run."""

    success: bool = True
    namespaces_queried: int = 0
    workflows_found: int = 0
    duplicates_skipped: int = 0
    records_stored: int = 0
    evaluation_triggered: bool = False
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "namespaces_queried": self.namespaces_queried,
            "workflows_found": self.workflows_found,
            "duplicates_skipped": self.duplicates_skipped,
            "records_stored": self.records_stored,
            "evaluation_triggered": self.evaluation_triggered,
            "errors": self.errors,
        }


async def run_collection_pipeline(
    ctx: Any,  # LearningPipelineContext
    namespaces: list[str] | None = None,
    hours_back: int = 1,
) -> CollectionResult:
    """Run the collection pipeline.

    Args:
        ctx: Pipeline context (Temporal or Local).
        namespaces: Temporal namespaces to query. Defaults to MONITORED_NAMESPACES.
        hours_back: How far back to look for executions.

    Returns:
        CollectionResult with statistics.
    """
    namespaces = namespaces or MONITORED_NAMESPACES
    result = CollectionResult()

    ctx.set_status("Starting collection", phase="init")

    # -------------------------------------------------------------------------
    # Step 1: Query all namespaces for recent workflow executions
    # -------------------------------------------------------------------------
    all_workflows: list[dict[str, Any]] = []

    for namespace in namespaces:
        ctx.set_status(f"Querying {namespace}", phase="fetch")
        try:
            workflows = await ctx.list_recent_workflows(namespace, hours_back)
            all_workflows.extend(
                {**w, "_namespace": namespace} for w in workflows
            )
            result.namespaces_queried += 1
            ctx.log_event("namespace_queried", f"{len(workflows)} workflows in {namespace}")
        except Exception as e:
            logger.warning(f"Failed to query namespace {namespace}: {e}")
            result.errors.append(f"{namespace}: {e}")

    result.workflows_found = len(all_workflows)

    if not all_workflows:
        ctx.set_status("No workflows found", phase="complete")
        return result

    # -------------------------------------------------------------------------
    # Step 2: Deduplicate against previously collected records
    # -------------------------------------------------------------------------
    ctx.set_status(f"Deduplicating {len(all_workflows)} workflows", phase="dedup")

    dedup_keys = {}
    for wf in all_workflows:
        wf_id = wf.get("workflow_id", wf.get("id", ""))
        run_id = wf.get("run_id", "")
        key = make_dedup_key(wf_id, run_id)
        dedup_keys[key] = wf

    seen = await ctx.check_seen(list(dedup_keys.keys()))
    new_workflows = [
        wf for key, wf in dedup_keys.items() if not seen.get(key, False)
    ]

    result.duplicates_skipped = len(all_workflows) - len(new_workflows)

    if not new_workflows:
        ctx.set_status("All workflows already collected", phase="complete")
        return result

    ctx.log_event("dedup_complete", f"{len(new_workflows)} new, {result.duplicates_skipped} skipped")

    # -------------------------------------------------------------------------
    # Step 3: Convert to ExecutionRecord dicts
    # -------------------------------------------------------------------------
    ctx.set_status(f"Converting {len(new_workflows)} workflows", phase="convert")

    records: list[dict[str, Any]] = []
    dedup_keys_to_mark: list[str] = []

    for wf in new_workflows:
        try:
            record = _workflow_to_record(wf)
            records.append(record.to_dict())
            dedup_keys_to_mark.append(
                make_dedup_key(wf.get("workflow_id", wf.get("id", "")), wf.get("run_id", ""))
            )
        except Exception as e:
            logger.warning(f"Failed to convert workflow: {e}")
            result.errors.append(f"convert: {e}")

    # -------------------------------------------------------------------------
    # Step 4: Store records and mark as seen
    # -------------------------------------------------------------------------
    ctx.set_status(f"Storing {len(records)} records", phase="store")

    stored = await ctx.store_records(records)
    result.records_stored = stored

    if dedup_keys_to_mark:
        await ctx.mark_seen(dedup_keys_to_mark)

    # -------------------------------------------------------------------------
    # Step 5: Trigger evaluation (Critic) for new records
    # -------------------------------------------------------------------------
    if records:
        ctx.set_status("Triggering evaluation", phase="trigger")
        record_ids = [r["record_id"] for r in records]
        try:
            await ctx.trigger_evaluation(record_ids)
            result.evaluation_triggered = True
        except Exception as e:
            logger.warning(f"Failed to trigger evaluation: {e}")
            result.errors.append(f"trigger: {e}")

    ctx.set_status(
        f"Collected {result.records_stored} new records from {result.namespaces_queried} namespaces",
        phase="complete",
    )
    return result


def _workflow_to_record(wf: dict[str, Any]) -> ExecutionRecord:
    """Convert a Temporal workflow summary dict to an ExecutionRecord.

    The Temporal MCP `list_workflows` tool returns dicts with fields like:
    - workflow_id, run_id, type/workflow_type, status
    - start_time, close_time, execution_time
    - task_queue, memo
    """
    wf_id = wf.get("workflow_id", wf.get("id", ""))
    run_id = wf.get("run_id", "")
    wf_type = wf.get("type", wf.get("workflow_type", "Unknown"))
    namespace = wf.get("_namespace", "default")
    task_queue = wf.get("task_queue", namespace)

    # Parse status
    raw_status = wf.get("status", "COMPLETED")
    status = map_temporal_status(str(raw_status))

    # Parse times
    started_at = wf.get("start_time", wf.get("started_at", ""))
    completed_at = wf.get("close_time", wf.get("completed_at"))

    # Calculate duration
    duration_ms = wf.get("duration_ms", wf.get("execution_time_ms", 0))
    if not duration_ms and wf.get("execution_time"):
        # execution_time might be in seconds
        try:
            duration_ms = int(float(wf["execution_time"]) * 1000)
        except (ValueError, TypeError):
            duration_ms = 0

    return ExecutionRecord(
        record_id=make_record_id(wf_id, run_id),
        syndicate=infer_syndicate_from_task_queue(task_queue),
        workflow_type=wf_type,
        workflow_id=wf_id,
        run_id=run_id,
        status=status,
        started_at=str(started_at),
        completed_at=str(completed_at) if completed_at else None,
        duration_ms=duration_ms,
        input_data=wf.get("input"),
        output_data=_truncate_output(wf.get("result", wf.get("output"))),
        error_message=wf.get("error", wf.get("failure", {}).get("message")) if status == ExecutionStatus.FAILED else None,
        task_queue=task_queue,
    )


def _truncate_output(output: Any, max_len: int = 5000) -> dict[str, Any] | None:
    """Truncate workflow output for storage."""
    if output is None:
        return None
    if isinstance(output, dict):
        s = str(output)
        if len(s) > max_len:
            return {"_truncated": True, "summary": s[:max_len]}
        return output
    return {"value": str(output)[:max_len]}
```

---

## 1.4 Collection Activities

Add to `kubani/syndicates/learning_system/activities.py`:

```python
"""
Learning System Activities.

Activities for the three-stage learning pipeline:
- Stage 1 (Collect): Query Temporal, store execution records
- Stage 2 (Analyze): Run LearningAnalystAgent (see Phase 2)
- Stage 3 (Improve): Run ImprovementAgent (see Phase 3)
"""

import logging
from typing import Any

from temporalio import activity

logger = logging.getLogger(__name__)


# =============================================================================
# Stage 1: Collection Activities
# =============================================================================


@activity.defn
async def list_recent_workflows_activity(input_data: dict) -> list[dict[str, Any]]:
    """Query Temporal MCP for recent workflow executions in a namespace.

    Args:
        input_data: Dict with keys:
            - namespace: Temporal namespace to query
            - hours_back: How far back to look (default 1)

    Returns:
        List of workflow summary dicts from Temporal MCP.
    """
    from kubani.syndicates.learning_system._mcp import get_temporal_mcp_client

    namespace = input_data["namespace"]
    hours_back = input_data.get("hours_back", 1)

    activity.heartbeat(f"Querying {namespace} for last {hours_back}h")

    try:
        client = get_temporal_mcp_client(namespace=namespace)
        # Use Temporal MCP list_workflows tool
        # Query for closed workflows in the time window
        result = await client.call_tool(
            "list_workflows",
            {
                "query": f"CloseTime > '{_hours_ago_iso(hours_back)}'",
                "limit": 100,
            },
        )
        workflows = result.get("workflows", [])
        logger.info(f"Found {len(workflows)} workflows in {namespace}")
        return workflows
    except Exception as e:
        logger.error(f"Failed to query {namespace}: {e}")
        return []


@activity.defn
async def get_workflow_detail_activity(input_data: dict) -> dict[str, Any]:
    """Get detailed info about a specific workflow execution.

    Args:
        input_data: Dict with keys:
            - workflow_id: Temporal workflow ID
            - namespace: Temporal namespace

    Returns:
        Workflow detail dict with history summary.
    """
    from kubani.syndicates.learning_system._mcp import get_temporal_mcp_client

    workflow_id = input_data["workflow_id"]
    namespace = input_data["namespace"]

    try:
        client = get_temporal_mcp_client(namespace=namespace)
        detail = await client.call_tool(
            "get_workflow",
            {"workflow_id": workflow_id},
        )
        return detail
    except Exception as e:
        logger.error(f"Failed to get workflow detail: {e}")
        return {}


@activity.defn
async def check_seen_activity(input_data: dict) -> dict[str, bool]:
    """Check which execution records have already been collected.

    Uses Memory MCP cache to check dedup keys.

    Args:
        input_data: Dict with key "dedup_keys" (list of strings).

    Returns:
        Dict mapping each key to True (seen) or False (new).
    """
    from kubani.syndicates.learning_system._mcp import get_memory_mcp_client

    keys = input_data["dedup_keys"]
    result: dict[str, bool] = {}

    try:
        client = get_memory_mcp_client()
        for key in keys:
            seen = await client.call_tool("check_seen", {"key": key, "namespace": "learning"})
            result[key] = seen.get("seen", False)
    except Exception as e:
        logger.warning(f"Dedup check failed, treating all as new: {e}")
        result = {k: False for k in keys}

    return result


@activity.defn
async def mark_seen_activity(input_data: dict) -> None:
    """Mark execution records as collected in the dedup cache.

    Args:
        input_data: Dict with keys:
            - dedup_keys: List of cache keys to mark
            - ttl_hours: TTL in hours (default 168 = 7 days)
    """
    from kubani.syndicates.learning_system._mcp import get_memory_mcp_client

    keys = input_data["dedup_keys"]
    ttl_hours = input_data.get("ttl_hours", 168)
    ttl_seconds = ttl_hours * 3600

    try:
        client = get_memory_mcp_client()
        for key in keys:
            await client.call_tool(
                "mark_seen",
                {"key": key, "namespace": "learning", "ttl_seconds": ttl_seconds},
            )
    except Exception as e:
        logger.warning(f"Failed to mark seen: {e}")


@activity.defn
async def store_records_activity(input_data: dict) -> dict[str, Any]:
    """Store execution records in Memory MCP.

    Args:
        input_data: Dict with key "records" (list of ExecutionRecord dicts).

    Returns:
        Dict with "stored_count" and "record_ids".
    """
    from kubani.syndicates.learning_system._mcp import get_memory_mcp_client

    records = input_data["records"]
    stored = 0
    record_ids = []

    try:
        client = get_memory_mcp_client()
        for record in records:
            await client.call_tool(
                "add",
                {
                    "type": "execution_record",
                    "namespace": "learning",
                    "data": record,
                    "metadata": {
                        "syndicate": record.get("syndicate", ""),
                        "workflow_type": record.get("workflow_type", ""),
                        "status": record.get("status", ""),
                    },
                },
            )
            stored += 1
            record_ids.append(record["record_id"])

        activity.heartbeat(f"Stored {stored}/{len(records)} records")
    except Exception as e:
        logger.error(f"Failed to store records: {e}")

    return {"stored_count": stored, "record_ids": record_ids}


# =============================================================================
# MCP Client Helper (shared across activities)
# =============================================================================


def _hours_ago_iso(hours: int) -> str:
    """Get ISO timestamp for N hours ago."""
    from datetime import datetime, timedelta, timezone

    dt = datetime.now(timezone.utc) - timedelta(hours=hours)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
```

### MCP Client Module

Create `kubani/syndicates/learning_system/_mcp.py`:

```python
"""MCP client helpers for learning system activities.

Provides factory functions for creating MCP SSE clients to:
- Temporal MCP server (for querying workflow executions)
- Memory MCP server (for storing/querying records)
- Skills MCP server (for checking existing skills)

These clients are used within Temporal activities (not workflows).
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class MCPToolClient:
    """Lightweight wrapper for calling MCP server tools via HTTP.

    Uses the MCP SSE client from the framework to call tools on
    MCP servers. Each activity creates its own client instance.
    """

    def __init__(self, base_url: str):
        self._base_url = base_url
        self._client = None

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call a tool on the MCP server.

        Uses httpx to call the MCP server's tool endpoint directly.
        This avoids the complexity of SSE client lifecycle management
        within short-lived Temporal activities.
        """
        import httpx

        url = f"{self._base_url}/call-tool"
        payload = {"name": tool_name, "arguments": arguments}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.json()

    async def close(self) -> None:
        """Close the client (no-op for HTTP client)."""
        pass


def get_temporal_mcp_client(namespace: str | None = None) -> MCPToolClient:
    """Get a Temporal MCP client.

    Args:
        namespace: Temporal namespace (used for routing if needed).

    Returns:
        MCPToolClient configured for the Temporal MCP server.
    """
    url = os.environ.get("MCP_TEMPORAL_URL", "http://temporal-mcp-server.ai-agents.svc:8081")
    return MCPToolClient(url)


def get_memory_mcp_client() -> MCPToolClient:
    """Get a Memory MCP client."""
    url = os.environ.get("MCP_MEMORY_URL", "http://memory-mcp.ai-agents.svc:8083")
    return MCPToolClient(url)


def get_skills_mcp_client() -> MCPToolClient:
    """Get a Skills MCP client."""
    url = os.environ.get("MCP_SKILLS_URL", "http://skills-mcp.ai-agents.svc:8085")
    return MCPToolClient(url)
```

**Important note on the MCP client approach:** The activities above use a lightweight HTTP wrapper (`MCPToolClient`) rather than the full Strands `MCPClient` with SSE transport. This is deliberate — Temporal activities are short-lived and creating/tearing down SSE connections for each activity invocation is wasteful. The MCP servers all expose HTTP endpoints that can be called directly.

If the MCP servers only support SSE (not direct HTTP tool calls), then the activities should use the framework's `get_mcp_client()` helper instead. Check the actual MCP server implementations to confirm which transport they support. If only SSE, replace `MCPToolClient` with:

```python
from kubani.framework.mcp import get_mcp_client

async with get_mcp_client() as client:
    result = await client.memory.check_seen(key=key, namespace="learning")
```

---

## 1.5 CollectExecutionsWorkflow

Create `kubani/syndicates/learning_system/workflows/collect.py`:

```python
"""Stage 1: Collect Executions Workflow.

Queries Temporal for recent workflow completions across all monitored
namespaces, deduplicates, and stores new ExecutionRecords.

Scheduled to run hourly. Triggers AnalyzeExecutionsWorkflow (Stage 2)
for each new batch.
"""

from dataclasses import dataclass
from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from kubani.framework.temporal.workflows import ObservableWorkflowMixin, WorkflowStatus
    from kubani.syndicates.learning_system.pipeline import run_collection_pipeline
    from kubani.syndicates.learning_system.pipeline.contexts.temporal_context import (
        TemporalContext,
    )


@dataclass
class CollectInput:
    """Input for the collection workflow.

    Attributes:
        namespaces: Optional override for which namespaces to query.
        hours_back: How far back to look (default 1 hour).
    """

    namespaces: list[str] | None = None
    hours_back: int = 1


@workflow.defn
class CollectExecutionsWorkflow(ObservableWorkflowMixin):
    """Collect recent workflow executions from Temporal.

    Pipeline:
    1. Query each monitored namespace for closed workflows.
    2. Deduplicate against previously collected records.
    3. Convert to ExecutionRecord and store in Memory MCP.
    4. Trigger analysis for new records (fire-and-forget).

    Queries:
        get_status: Inherited from ObservableWorkflowMixin.
        get_collection_stats: Returns current collection statistics.
    """

    def __init__(self) -> None:
        self._init_observability("CollectExecutionsWorkflow")
        self._stats: dict[str, Any] = {}

    @workflow.run
    async def run(self, input: CollectInput | None = None) -> dict[str, Any]:
        """Execute a collection run.

        Args:
            input: Optional configuration overrides.

        Returns:
            CollectionResult as a plain dict.
        """
        if input is None:
            input = CollectInput()

        self._set_status(WorkflowStatus.RUNNING, "Starting collection", phase="init")

        try:
            ctx = TemporalContext(workflow_mixin=self)
            result = await run_collection_pipeline(
                ctx,
                namespaces=input.namespaces,
                hours_back=input.hours_back,
            )

            self._stats = result.to_dict()

            if result.success:
                self._set_status(
                    WorkflowStatus.COMPLETED,
                    f"Collected {result.records_stored} new records "
                    f"from {result.namespaces_queried} namespaces",
                )
            return result.to_dict()

        except Exception as e:
            self._set_status(WorkflowStatus.FAILED, f"Collection failed: {e}")
            raise

    @workflow.query
    def get_collection_stats(self) -> dict[str, Any]:
        """Query current collection statistics."""
        return self._stats
```

---

## 1.6 Workflow Registration (`__init__.py`)

Create `kubani/syndicates/learning_system/workflows/__init__.py`:

```python
"""Learning System workflows.

Stage 1: CollectExecutionsWorkflow (hourly) — collects from Temporal
Stage 2: AnalyzeExecutionsWorkflow (triggered) — evaluates with LearningAnalystAgent
Stage 3: ImprovementWorkflow (daily) — proposes improvements with ImprovementAgent
"""

from kubani.syndicates.learning_system.workflows.collect import CollectExecutionsWorkflow

# Stage 2 and 3 added in Phase 2 and Phase 3
__all__ = [
    "CollectExecutionsWorkflow",
]
```

---

## 1.7 Tests

Create `kubani/syndicates/learning_system/tests/test_models.py`:

```python
"""Tests for learning system data models."""

from kubani.syndicates.learning_system.models import (
    AnalyzedExecution,
    ExecutionRecord,
    ExecutionStatus,
    ImprovementStatus,
    ImprovementType,
    ProposedImprovement,
    make_dedup_key,
    make_record_id,
    map_temporal_status,
)


def test_make_record_id_deterministic():
    """Same inputs always produce the same ID."""
    id1 = make_record_id("wf-123", "run-abc")
    id2 = make_record_id("wf-123", "run-abc")
    assert id1 == id2
    assert id1.startswith("exec-")


def test_make_record_id_different_inputs():
    """Different inputs produce different IDs."""
    id1 = make_record_id("wf-123", "run-abc")
    id2 = make_record_id("wf-456", "run-abc")
    assert id1 != id2


def test_make_dedup_key():
    key = make_dedup_key("wf-123", "run-abc")
    assert key == "learning:exec:wf-123:run-abc"


def test_map_temporal_status():
    assert map_temporal_status("COMPLETED") == ExecutionStatus.COMPLETED
    assert map_temporal_status("WORKFLOW_EXECUTION_STATUS_COMPLETED") == ExecutionStatus.COMPLETED
    assert map_temporal_status("FAILED") == ExecutionStatus.FAILED
    assert map_temporal_status("TIMED_OUT") == ExecutionStatus.TIMED_OUT
    assert map_temporal_status("CANCELLED") == ExecutionStatus.CANCELLED
    assert map_temporal_status("CANCELED") == ExecutionStatus.CANCELLED


def test_execution_record_roundtrip():
    record = ExecutionRecord(
        record_id="exec-123",
        syndicate="k8s-monitor",
        workflow_type="K8sMonitorWorkflow",
        workflow_id="wf-1",
        run_id="run-1",
        status=ExecutionStatus.COMPLETED,
        started_at="2026-03-09T12:00:00Z",
        completed_at="2026-03-09T12:01:00Z",
        duration_ms=60000,
    )
    d = record.to_dict()
    restored = ExecutionRecord.from_dict(d)
    assert restored.record_id == record.record_id
    assert restored.status == ExecutionStatus.COMPLETED


def test_proposed_improvement_roundtrip():
    proposal = ProposedImprovement(
        proposal_id="prop-1",
        improvement_type=ImprovementType.SKILL_NEW,
        target_agent="k8s-monitor",
        title="Add retry skill",
        description="New skill for retry logic",
        rationale="Failures observed 5 times",
        confidence=0.85,
    )
    d = proposal.to_dict()
    restored = ProposedImprovement.from_dict(d)
    assert restored.improvement_type == ImprovementType.SKILL_NEW
    assert restored.status == ImprovementStatus.PROPOSED
```

Create `kubani/syndicates/learning_system/tests/test_collect_pipeline.py`:

```python
"""Tests for the collection pipeline using LocalContext."""

import pytest

from kubani.syndicates.learning_system.pipeline.collect import (
    CollectionResult,
    run_collection_pipeline,
)
from kubani.syndicates.learning_system.pipeline.contexts.local_context import LocalContext


@pytest.fixture
def sample_workflows():
    """Sample workflow data as returned by Temporal MCP."""
    return [
        {
            "workflow_id": "k8s-monitor-scheduled-2026-03-09T12:00:00Z",
            "run_id": "run-abc-123",
            "type": "K8sMonitorWorkflow",
            "status": "COMPLETED",
            "start_time": "2026-03-09T12:00:00Z",
            "close_time": "2026-03-09T12:01:30Z",
            "execution_time": "90",
            "task_queue": "k8s-monitor",
        },
        {
            "workflow_id": "k8s-monitor-scheduled-2026-03-09T12:05:00Z",
            "run_id": "run-def-456",
            "type": "K8sMonitorWorkflow",
            "status": "FAILED",
            "start_time": "2026-03-09T12:05:00Z",
            "close_time": "2026-03-09T12:05:30Z",
            "execution_time": "30",
            "task_queue": "k8s-monitor",
            "failure": {"message": "MCP timeout"},
        },
    ]


@pytest.mark.asyncio
async def test_collection_pipeline_basic(sample_workflows):
    """Test basic collection with mock workflows."""

    async def mock_lister(namespace, hours_back):
        if namespace == "k8s-monitor":
            return sample_workflows
        return []

    ctx = LocalContext(workflow_lister=mock_lister)
    result = await run_collection_pipeline(
        ctx,
        namespaces=["k8s-monitor"],
        hours_back=1,
    )

    assert result.success
    assert result.workflows_found == 2
    assert result.records_stored == 2
    assert result.duplicates_skipped == 0
    assert len(ctx._stored) == 2


@pytest.mark.asyncio
async def test_collection_pipeline_dedup(sample_workflows):
    """Test that previously seen workflows are skipped."""

    async def mock_lister(namespace, hours_back):
        return sample_workflows

    ctx = LocalContext(workflow_lister=mock_lister)

    # First run: all new
    result1 = await run_collection_pipeline(ctx, namespaces=["k8s-monitor"])
    assert result1.records_stored == 2

    # Second run: all seen (mark_seen was called)
    result2 = await run_collection_pipeline(ctx, namespaces=["k8s-monitor"])
    assert result2.duplicates_skipped == 2
    assert result2.records_stored == 0


@pytest.mark.asyncio
async def test_collection_pipeline_empty():
    """Test collection when no workflows found."""
    ctx = LocalContext()
    result = await run_collection_pipeline(ctx, namespaces=["empty-namespace"])
    assert result.success
    assert result.workflows_found == 0
    assert result.records_stored == 0


@pytest.mark.asyncio
async def test_collection_triggers_evaluation(sample_workflows):
    """Test that evaluation is triggered for new records."""

    async def mock_lister(namespace, hours_back):
        return sample_workflows

    ctx = LocalContext(workflow_lister=mock_lister)
    result = await run_collection_pipeline(ctx, namespaces=["k8s-monitor"])

    assert result.evaluation_triggered
    assert len(ctx._evaluation_triggered) == 1
    assert len(ctx._evaluation_triggered[0]) == 2  # Two record IDs
```

---

## 1.8 Verification Checklist

After implementing Phase 1:

- [ ] `models.py` — All three dataclasses with `to_dict`/`from_dict`, all utility functions
- [ ] `pipeline/context.py` — `LearningPipelineContext` protocol with all methods
- [ ] `pipeline/contexts/temporal_context.py` — Production context wrapping activities
- [ ] `pipeline/contexts/local_context.py` — Test context with mock callables
- [ ] `pipeline/collect.py` — `run_collection_pipeline()` with 5-step pipeline
- [ ] `activities.py` — 5 collection activities (list, detail, check_seen, mark_seen, store)
- [ ] `_mcp.py` — MCP client factory functions
- [ ] `workflows/collect.py` — `CollectExecutionsWorkflow` with `ObservableWorkflowMixin`
- [ ] `tests/test_models.py` — Model roundtrip and utility function tests
- [ ] `tests/test_collect_pipeline.py` — Pipeline tests with LocalContext
- [ ] All tests pass: `pytest kubani/syndicates/learning_system/tests/`
