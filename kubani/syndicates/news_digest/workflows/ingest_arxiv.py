"""arXiv Paper Ingest Workflow.

Collects recent AI/ML papers from arXiv via the research-collector agent,
deduplicates by arXiv ID, and stores raw documents in Memory MCP.

Designed to run less frequently than RSS (every 2-4 hours) since arXiv
publishes new papers on a daily cycle.

This workflow delegates all business logic to ``run_ingest_pipeline``
via the Context Injection pattern. The workflow class itself is a thin
shell that provides Temporal-specific wiring.

Dedup strategy: arXiv ID is globally unique and stable, so we hash the
``arxiv:{id}`` URI for cache-based deduplication.
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
class ArxivIngestInput:
    """Input for an arXiv ingest run.

    Attributes:
        categories: arXiv categories to search (e.g., cs.AI, cs.LG).
        max_results: Maximum number of papers to fetch per run.
        correlation_id: Optional tracking ID.
    """

    categories: list[str] | None = None
    max_results: int = 30
    correlation_id: str | None = None


# =============================================================================
# Workflow
# =============================================================================


@workflow.defn
class ArxivIngestWorkflow(ObservableWorkflowMixin):
    """Ingest papers from arXiv.

    Pipeline:
    1. Call research-collector agent to fetch recent papers.
    2. Parse the agent response into paper dicts.
    3. Convert to RawDocument dicts.
    4. Batch-check dedup keys against Memory MCP cache.
    5. Store new documents and set dedup cache keys.
    6. Trigger analysis for new documents (fire-and-forget).

    All pipeline logic lives in ``run_ingest_pipeline``. This class
    provides the Temporal execution context and query handlers.
    """

    def __init__(self) -> None:
        self._init_observability("ArxivIngestWorkflow")
        self._stats: dict[str, Any] = {}

    @workflow.run
    async def run(self, input: ArxivIngestInput | None = None) -> dict[str, Any]:
        """Execute an arXiv ingest run."""
        if input is None:
            input = ArxivIngestInput()

        self._set_status(WorkflowStatus.RUNNING, "Starting arXiv ingest", phase="init")

        try:
            ctx = TemporalContext(workflow_mixin=self, source_type="arxiv")

            # Pass source-specific parameters through to fetch_documents
            fetch_kwargs: dict[str, Any] = {
                "max_results": input.max_results,
            }
            if input.categories:
                fetch_kwargs["categories"] = input.categories

            result = await run_ingest_pipeline(
                ctx,
                source_type="arxiv",
                **fetch_kwargs,
            )

            # Cache stats for query handler
            self._stats = result.to_dict()

            if result.success:
                self._set_status(
                    WorkflowStatus.COMPLETED,
                    f"Stored {result.documents_stored} new papers",
                )
            return result.to_dict()

        except Exception as e:
            self._set_status(WorkflowStatus.FAILED, f"arXiv ingest failed: {e}")
            raise

    @workflow.query
    def get_ingest_stats(self) -> dict[str, Any]:
        """Query current ingest statistics."""
        return self._stats
