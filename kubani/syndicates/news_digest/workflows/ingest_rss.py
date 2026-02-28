"""RSS Feed Ingest Workflow.

Collects articles from configured RSS feeds, deduplicates by URL hash,
and stores raw documents in Memory MCP. Designed to run on a frequent
schedule (every 15-30 minutes) since RSS feeds update often.

This workflow delegates all business logic to ``run_ingest_pipeline``
via the Context Injection pattern. The workflow class itself is a thin
shell that provides Temporal-specific wiring (context creation, status
mapping, query handlers).

Dedup strategy: SHA-256 hash of the article URL, checked via
batch cache lookup before storage.
"""

from dataclasses import dataclass
from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from kubani.framework.temporal.workflows import ObservableWorkflowMixin, WorkflowStatus
    from kubani.syndicates.news_digest.pipeline import run_ingest_pipeline
    from kubani.syndicates.news_digest.pipeline.contexts.temporal_context import (
        TemporalContext,
    )


# =============================================================================
# Input / Output
# =============================================================================


@dataclass
class RSSIngestInput:
    """Input for an RSS ingest run.

    Attributes:
        correlation_id: Optional tracking ID for observability.
    """

    correlation_id: str | None = None


# =============================================================================
# Workflow
# =============================================================================


@workflow.defn
class RSSIngestWorkflow(ObservableWorkflowMixin):
    """Ingest articles from RSS feeds.

    Pipeline:
    1. Fetch all configured RSS feeds via ``collect_feeds_activity``.
    2. Convert entries to ``RawDocument`` dicts.
    3. Batch-check dedup keys against Memory MCP cache.
    4. Store new documents and set dedup cache keys.
    5. Trigger analysis for new documents (fire-and-forget).

    All pipeline logic lives in ``run_ingest_pipeline``. This class
    provides the Temporal execution context and query handlers.

    Queries:
        get_status: Inherited from ObservableWorkflowMixin.
        get_ingest_stats: Returns current collection statistics.
    """

    def __init__(self) -> None:
        self._init_observability("RSSIngestWorkflow")
        self._stats: dict[str, Any] = {}

    @workflow.run
    async def run(self, input: RSSIngestInput | None = None) -> dict[str, Any]:
        """Execute an RSS ingest run.

        Args:
            input: Optional configuration. Defaults are used if omitted.

        Returns:
            IngestResult as a plain dict.
        """
        if input is None:
            input = RSSIngestInput()

        self._set_status(WorkflowStatus.RUNNING, "Starting RSS ingest", phase="init")

        try:
            ctx = TemporalContext(workflow_mixin=self, source_type="rss")
            result = await run_ingest_pipeline(ctx, source_type="rss")

            # Cache stats for query handler
            self._stats = result.to_dict()

            if result.success:
                self._set_status(
                    WorkflowStatus.COMPLETED,
                    f"Stored {result.documents_stored} new articles",
                )
            return result.to_dict()

        except Exception as e:
            self._set_status(WorkflowStatus.FAILED, f"RSS ingest failed: {e}")
            raise

    @workflow.query
    def get_ingest_stats(self) -> dict[str, Any]:
        """Query current ingest statistics."""
        return self._stats
