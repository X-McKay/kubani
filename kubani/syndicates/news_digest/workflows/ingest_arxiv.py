"""arXiv Paper Ingest Workflow.

Collects recent AI/ML papers from arXiv via the research-collector agent,
deduplicates by arXiv ID, and stores raw documents in Memory MCP.

Designed to run less frequently than RSS (every 2-4 hours) since arXiv
publishes new papers on a daily cycle.

Dedup strategy: arXiv ID is globally unique and stable, so we hash the
``arxiv:{id}`` URI for cache-based deduplication.
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from kubani.framework.temporal.workflows import ObservableWorkflowMixin, WorkflowStatus


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


@dataclass
class ArxivIngestResult:
    """Result of an arXiv ingest run.

    Attributes:
        papers_collected: Total papers returned by the agent.
        papers_new: Papers that passed deduplication.
        papers_stored: Papers successfully stored in Memory MCP.
        success: Whether the workflow completed without fatal errors.
        error: Error message if the workflow failed.
    """

    papers_collected: int = 0
    papers_new: int = 0
    papers_stored: int = 0
    success: bool = True
    error: str | None = None


# =============================================================================
# Retry Policies
# =============================================================================

AGENT_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=10),
    maximum_interval=timedelta(minutes=2),
    maximum_attempts=3,
    non_retryable_error_types=["RateLimitError"],
)

STORAGE_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=5),
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=2,
)


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
    """

    def __init__(self) -> None:
        self._init_observability("ArxivIngestWorkflow")
        self._result = ArxivIngestResult()

    @workflow.run
    async def run(self, input: ArxivIngestInput | None = None) -> dict[str, Any]:
        """Execute an arXiv ingest run."""
        if input is None:
            input = ArxivIngestInput()

        self._set_status(WorkflowStatus.RUNNING, "Starting arXiv ingest", phase="init")

        try:
            # Step 1: Fetch papers via agent
            papers = await self._fetch_papers(input)
            self._result.papers_collected = len(papers)

            if not papers:
                self._set_status(WorkflowStatus.COMPLETED, "No papers found")
                return self._build_result()

            if await self._wait_if_paused():
                return self._build_result()

            # Step 2: Convert to RawDocument dicts
            raw_docs = self._convert_to_raw_documents(papers)

            # Step 3: Batch dedup
            new_docs = await self._batch_dedup(raw_docs)
            self._result.papers_new = len(new_docs)

            if not new_docs:
                self._set_status(WorkflowStatus.COMPLETED, "All papers already seen")
                return self._build_result()

            if await self._wait_if_paused():
                return self._build_result()

            # Step 4: Store new documents
            stored = await self._store_documents(new_docs)
            self._result.papers_stored = stored

            # Step 5: Trigger analysis for new documents (fire-and-forget)
            await self._trigger_analysis(new_docs)

            self._set_status(
                WorkflowStatus.COMPLETED,
                f"Stored {stored} new papers",
            )
            return self._build_result()

        except Exception as e:
            self._set_status(WorkflowStatus.FAILED, f"arXiv ingest failed: {e}")
            self._result.success = False
            self._result.error = str(e)
            raise

    # =========================================================================
    # Pipeline Steps
    # =========================================================================

    async def _fetch_papers(self, input: ArxivIngestInput) -> list[dict[str, Any]]:
        """Fetch papers from arXiv via the research-collector agent."""
        from kubani.framework.temporal import run_agent_activity

        self._set_status(WorkflowStatus.RUNNING, "Fetching papers from arXiv", phase="fetch")

        categories = input.categories or ["cs.AI", "cs.LG", "cs.CL"]
        categories_str = ", ".join(categories)

        result = await workflow.execute_activity(
            run_agent_activity,
            args=[
                "research-collector",
                f"""Fetch the {input.max_results} most recent AI/ML papers from arXiv
in categories: {categories_str}.

Return ONLY a JSON array where each element has these fields:
- arxiv_id: string (e.g., "2601.12345")
- title: string
- authors: array of strings
- abstract: string (first 500 chars)
- categories: array of strings
- published_at: string (ISO date)""",
            ],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=AGENT_RETRY_POLICY,
        )

        if not result.get("success"):
            error = result.get("error", "Unknown error")
            self._log_event("error", f"Paper fetch failed: {error}")
            raise RuntimeError(f"Paper fetch failed: {error}")

        from kubani.syndicates.news_digest.models import parse_json_array_from_text

        papers = parse_json_array_from_text(result.get("result", ""))
        self._log_event("papers_fetched", f"Fetched {len(papers)} papers")
        return papers

    def _convert_to_raw_documents(self, papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert arXiv paper dicts to RawDocument dicts."""
        from kubani.syndicates.news_digest.models import raw_document_from_arxiv_paper

        docs = []
        for paper in papers:
            try:
                doc = raw_document_from_arxiv_paper(paper)
                docs.append(doc.to_dict())
            except Exception as e:
                self._log_event("warning", f"Failed to convert paper: {e}")
        return docs

    async def _batch_dedup(self, documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Filter out papers that have already been stored."""
        from kubani.syndicates.news_digest.activities import batch_check_duplicates_activity
        from kubani.syndicates.news_digest.models import make_dedup_key

        self._set_status(
            WorkflowStatus.RUNNING,
            f"Checking {len(documents)} papers for duplicates",
            phase="dedup",
        )

        key_to_doc: dict[str, dict[str, Any]] = {}
        for doc in documents:
            key = make_dedup_key(doc["source_type"], doc["source_uri"])
            key_to_doc[key] = doc

        result = await workflow.execute_activity(
            batch_check_duplicates_activity,
            args=[list(key_to_doc.keys())],
            start_to_close_timeout=timedelta(minutes=2),
            heartbeat_timeout=timedelta(seconds=30),
            retry_policy=STORAGE_RETRY_POLICY,
        )

        if not result.get("success"):
            self._log_event("warning", "Dedup check failed, passing all documents through")
            return documents

        duplicates = result.get("duplicates", {})
        new_docs = [doc for key, doc in key_to_doc.items() if not duplicates.get(key, False)]

        dup_count = len(documents) - len(new_docs)
        self._log_event("dedup_complete", f"{len(new_docs)} new, {dup_count} duplicates filtered")
        return new_docs

    async def _trigger_analysis(self, documents: list[dict[str, Any]]) -> None:
        """Start the AnalyzeDocumentWorkflow as a child workflow.

        Fire-and-forget: the ingest workflow does not wait for analysis.

        Args:
            documents: List of RawDocument dicts to analyze.
        """
        from kubani.syndicates.news_digest.workflows.analyze import (
            AnalyzeDocumentWorkflow,
            AnalyzeInput,
        )

        self._set_status(
            WorkflowStatus.RUNNING,
            f"Triggering analysis for {len(documents)} documents",
            phase="trigger_analyze",
        )

        try:
            run_id = workflow.info().run_id[:8]
            await workflow.start_child_workflow(
                AnalyzeDocumentWorkflow.run,
                args=[
                    AnalyzeInput(
                        documents=documents,
                        max_documents=len(documents),
                    )
                ],
                id=f"analyze-arxiv-{run_id}",
                task_queue=workflow.info().task_queue,
                parent_close_policy=workflow.ParentClosePolicy.ABANDON,
            )
            self._log_event(
                "analysis_triggered",
                f"Started analysis for {len(documents)} documents",
            )
        except Exception as e:
            self._log_event(
                "analysis_trigger_error",
                f"Failed to trigger analysis: {e}",
            )

    async def _store_documents(self, documents: list[dict[str, Any]]) -> int:
        """Store new raw documents in Memory MCP."""
        from kubani.syndicates.news_digest.activities import store_raw_documents_activity

        self._set_status(
            WorkflowStatus.RUNNING,
            f"Storing {len(documents)} new papers",
            phase="store",
        )

        result = await workflow.execute_activity(
            store_raw_documents_activity,
            args=[documents],
            start_to_close_timeout=timedelta(minutes=5),
            heartbeat_timeout=timedelta(seconds=30),
            retry_policy=STORAGE_RETRY_POLICY,
        )

        stored = result.get("stored_count", 0)
        self._log_event("documents_stored", f"Stored {stored} documents")
        return stored

    # =========================================================================
    # Result Building & Queries
    # =========================================================================

    def _build_result(self) -> dict[str, Any]:
        """Build the result dictionary."""
        return {
            "papers_collected": self._result.papers_collected,
            "papers_new": self._result.papers_new,
            "papers_stored": self._result.papers_stored,
            "success": self._result.success,
            "error": self._result.error,
        }

    @workflow.query
    def get_ingest_stats(self) -> dict[str, Any]:
        """Query current ingest statistics."""
        return {
            "papers_collected": self._result.papers_collected,
            "papers_new": self._result.papers_new,
            "papers_stored": self._result.papers_stored,
        }
