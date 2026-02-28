"""GitHub Trending Repos Ingest Workflow.

Collects trending AI/ML repositories from GitHub via the research-collector
agent, deduplicates by repository URL, and stores raw documents in Memory MCP.

Designed to run infrequently (every 6-12 hours) since GitHub trending repos
change slowly and the signal is more about weekly momentum than hourly updates.

This workflow delegates all business logic to ``run_ingest_pipeline``
via the Context Injection pattern. The workflow class itself is a thin
shell that provides Temporal-specific wiring.

Dedup strategy: SHA-256 hash of the full repository URL, checked via
batch cache lookup. Repos that were already seen are skipped entirely.
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
class GitHubIngestInput:
    """Input for a GitHub ingest run.

    Attributes:
        max_results: Maximum number of repos to fetch.
        correlation_id: Optional tracking ID.
    """

    max_results: int = 20
    correlation_id: str | None = None


# =============================================================================
# Workflow
# =============================================================================


@workflow.defn
class GitHubIngestWorkflow(ObservableWorkflowMixin):
    """Ingest trending repos from GitHub.

    Pipeline:
    1. Call research-collector agent to fetch trending repos.
    2. Parse the agent response into repo dicts.
    3. Convert to RawDocument dicts.
    4. Batch-check dedup keys against Memory MCP cache.
    5. Store new documents and set dedup cache keys.
    6. Trigger analysis for new documents (fire-and-forget).

    All pipeline logic lives in ``run_ingest_pipeline``. This class
    provides the Temporal execution context and query handlers.
    """

    def __init__(self) -> None:
        self._init_observability("GitHubIngestWorkflow")
        self._stats: dict[str, Any] = {}

    @workflow.run
    async def run(self, input: GitHubIngestInput | None = None) -> dict[str, Any]:
        """Execute a GitHub ingest run."""
        if input is None:
            input = GitHubIngestInput()

        self._set_status(WorkflowStatus.RUNNING, "Starting GitHub ingest", phase="init")

        try:
            ctx = TemporalContext(workflow_mixin=self, source_type="github")

            result = await run_ingest_pipeline(
                ctx,
                source_type="github",
                max_results=input.max_results,
            )

            # Cache stats for query handler
            self._stats = result.to_dict()

            if result.success:
                self._set_status(
                    WorkflowStatus.COMPLETED,
                    f"Stored {result.documents_stored} new repos",
                )
            return result.to_dict()

        except Exception as e:
            self._set_status(WorkflowStatus.FAILED, f"GitHub ingest failed: {e}")
            raise

    @workflow.query
    def get_ingest_stats(self) -> dict[str, Any]:
        """Query current ingest statistics."""
        return self._stats
