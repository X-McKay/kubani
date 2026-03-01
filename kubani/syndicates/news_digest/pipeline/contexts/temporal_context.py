"""TemporalContext — PipelineContext implementation for Temporal workflows.

This context wraps Temporal activities and the ObservableWorkflowMixin
to provide full production behavior: batched activity calls, retry
policies, heartbeating, status reporting, pause/resume signals, and
child workflow triggering.

Usage inside a Temporal workflow::

    @workflow.defn
    class RSSIngestWorkflow(ObservableWorkflowMixin):
        @workflow.run
        async def run(self, input):
            ctx = TemporalContext(workflow_mixin=self, source_type="rss")
            return await run_ingest_pipeline(ctx, "rss")
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy


# =============================================================================
# Retry Policies
# =============================================================================

FETCH_RETRY_POLICY = RetryPolicy(
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

AGENT_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=10),
    maximum_interval=timedelta(minutes=2),
    maximum_attempts=3,
    non_retryable_error_types=["RateLimitError"],
)


# =============================================================================
# TemporalContext
# =============================================================================


class TemporalContext:
    """PipelineContext backed by Temporal activities and workflow APIs.

    This class holds a reference to the workflow's ``ObservableWorkflowMixin``
    instance (``self`` inside the workflow), giving it full access to
    ``_set_status``, ``_log_event``, ``_wait_if_paused``, and all Temporal
    workflow APIs (``workflow.execute_activity``, ``workflow.start_child_workflow``).

    Args:
        workflow_mixin: The workflow instance (``self`` from inside the
            ``@workflow.run`` method). Must be an ``ObservableWorkflowMixin``.
        source_type: The source type this context is configured for.
            Used to select the correct fetch strategy.
    """

    def __init__(self, workflow_mixin: Any, source_type: str) -> None:
        self._wf = workflow_mixin
        self._source_type = source_type

    # -------------------------------------------------------------------------
    # I/O: Fetching
    # -------------------------------------------------------------------------

    async def fetch_documents(
        self,
        source_type: str,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Fetch and convert documents using the appropriate Temporal activity.

        Each source type has its own fetch strategy:
        - RSS: calls ``collect_feeds_activity`` (direct RSS parsing).
        - arXiv: calls ``run_agent_activity`` with research-collector agent.
        - GitHub: calls ``run_agent_activity`` with research-collector agent.

        The conversion from raw source data to ``RawDocument.to_dict()``
        is handled within this method, since both fetching and conversion
        are source-specific concerns.
        """
        if source_type == "rss":
            return await self._fetch_rss()
        elif source_type == "arxiv":
            return await self._fetch_arxiv(**kwargs)
        elif source_type == "github":
            return await self._fetch_github(**kwargs)
        else:
            raise ValueError(f"Unknown source type: {source_type}")

    async def _fetch_rss(self) -> list[dict[str, Any]]:
        """Fetch RSS feeds via collect_feeds_activity."""
        from kubani.framework.temporal import collect_feeds_activity

        result = await workflow.execute_activity(
            collect_feeds_activity,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=FETCH_RETRY_POLICY,
        )

        if not result.get("success"):
            error = result.get("error", "Unknown error")
            raise RuntimeError(f"Feed fetch failed: {error}")

        sources_fetched = result.get("sources_fetched", 0)
        self._wf._log_event(
            "feeds_fetched",
            f"Fetched from {sources_fetched} feeds",
        )

        # collect_feeds_activity already converts to RawDocument dicts
        return result.get("raw_documents", [])

    async def _fetch_arxiv(self, **kwargs: Any) -> list[dict[str, Any]]:
        """Fetch arXiv papers via the research-collector agent."""
        from kubani.framework.temporal import run_agent_activity

        categories = kwargs.get("categories", ["cs.AI", "cs.LG", "cs.CL"])
        max_results = kwargs.get("max_results", 30)
        categories_str = ", ".join(categories)

        result = await workflow.execute_activity(
            run_agent_activity,
            args=[
                "research-collector",
                f"""Fetch the {max_results} most recent AI/ML papers from arXiv
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
            raise RuntimeError(f"arXiv fetch failed: {error}")

        from kubani.syndicates.news_digest.models import (
            parse_json_array_from_text,
            raw_document_from_arxiv_paper,
        )

        papers = parse_json_array_from_text(result.get("result", ""))
        self._wf._log_event("papers_fetched", f"Fetched {len(papers)} papers")

        # Convert to RawDocument dicts
        docs = []
        for paper in papers:
            try:
                doc = raw_document_from_arxiv_paper(paper)
                docs.append(doc.to_dict())
            except Exception as e:
                self._wf._log_event("warning", f"Failed to convert paper: {e}")
        return docs

    async def _fetch_github(self, **kwargs: Any) -> list[dict[str, Any]]:
        """Fetch trending GitHub repos via the research-collector agent."""
        from kubani.framework.temporal import run_agent_activity

        max_results = kwargs.get("max_results", 20)

        result = await workflow.execute_activity(
            run_agent_activity,
            args=[
                "research-collector",
                f"""Fetch the top {max_results} trending AI/ML repositories from GitHub.

Focus on repositories that are:
- Actively maintained and recently updated
- Related to AI, ML, LLMs, or data science
- Gaining significant traction (stars, forks)

Return ONLY a JSON array where each element has these fields:
- repo_url: string (full GitHub URL)
- name: string (repo name)
- description: string
- stars: integer
- language: string (primary language)
- topics: array of strings
- forks: integer
- trending_score: float (0.0 to 1.0, your estimate of trending momentum)""",
            ],
            start_to_close_timeout=timedelta(minutes=3),
            retry_policy=AGENT_RETRY_POLICY,
        )

        if not result.get("success"):
            error = result.get("error", "Unknown error")
            raise RuntimeError(f"GitHub fetch failed: {error}")

        from kubani.syndicates.news_digest.models import (
            parse_json_array_from_text,
            raw_document_from_github_repo,
        )

        repos = parse_json_array_from_text(result.get("result", ""))
        self._wf._log_event("repos_fetched", f"Fetched {len(repos)} repos")

        # Convert to RawDocument dicts
        docs = []
        for repo in repos:
            try:
                doc = raw_document_from_github_repo(repo)
                docs.append(doc.to_dict())
            except Exception as e:
                self._wf._log_event("warning", f"Failed to convert repo: {e}")
        return docs

    # -------------------------------------------------------------------------
    # I/O: Content Enrichment
    # -------------------------------------------------------------------------

    async def enrich_documents(
        self,
        documents: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Enrich documents with full-text content via fetch_article_content_activity."""
        from kubani.syndicates.news_digest.activities import fetch_article_content_activity

        result = await workflow.execute_activity(
            fetch_article_content_activity,
            args=[documents],
            start_to_close_timeout=timedelta(minutes=10),
            heartbeat_timeout=timedelta(seconds=60),
            retry_policy=FETCH_RETRY_POLICY,
        )

        enriched_count = result.get("enriched_count", 0)
        failed_count = result.get("failed_count", 0)
        self._wf._log_event(
            "enrichment_complete",
            f"Enriched {enriched_count} documents, {failed_count} failed",
        )

        return result.get("documents", documents)

    # -------------------------------------------------------------------------
    # I/O: Deduplication
    # -------------------------------------------------------------------------

    async def check_duplicates(
        self,
        dedup_keys: list[str],
    ) -> dict[str, bool]:
        """Batch-check dedup keys via batch_check_duplicates_activity."""
        from kubani.syndicates.news_digest.activities import batch_check_duplicates_activity

        result = await workflow.execute_activity(
            batch_check_duplicates_activity,
            args=[dedup_keys],
            start_to_close_timeout=timedelta(minutes=2),
            heartbeat_timeout=timedelta(seconds=30),
            retry_policy=STORAGE_RETRY_POLICY,
        )

        if not result.get("success"):
            # Fail open: on dedup failure, treat all as new
            self._wf._log_event(
                "warning",
                "Dedup check failed, treating all documents as new",
            )
            return {key: False for key in dedup_keys}

        return result.get("duplicates", {})

    # -------------------------------------------------------------------------
    # I/O: Storage
    # -------------------------------------------------------------------------

    async def store_documents(
        self,
        documents: list[dict[str, Any]],
    ) -> int:
        """Store documents via store_raw_documents_activity."""
        from kubani.syndicates.news_digest.activities import store_raw_documents_activity

        result = await workflow.execute_activity(
            store_raw_documents_activity,
            args=[documents],
            start_to_close_timeout=timedelta(minutes=5),
            heartbeat_timeout=timedelta(seconds=30),
            retry_policy=STORAGE_RETRY_POLICY,
        )

        return result.get("stored_count", 0)

    # -------------------------------------------------------------------------
    # I/O: Trigger downstream
    # -------------------------------------------------------------------------

    async def trigger_analysis(
        self,
        documents: list[dict[str, Any]],
        source_type: str,
    ) -> None:
        """Start AnalyzeDocumentWorkflow as a fire-and-forget child workflow."""
        from kubani.syndicates.news_digest.workflows.analyze import (
            AnalyzeDocumentWorkflow,
            AnalyzeInput,
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
                id=f"analyze-{source_type}-{run_id}",
                task_queue=workflow.info().task_queue,
                parent_close_policy=workflow.ParentClosePolicy.ABANDON,
            )
            self._wf._log_event(
                "analysis_triggered",
                f"Started analysis for {len(documents)} documents",
            )
        except Exception as e:
            # Analysis trigger failure is non-fatal for ingest
            self._wf._log_event(
                "analysis_trigger_error",
                f"Failed to trigger analysis: {e}",
            )

    # -------------------------------------------------------------------------
    # Observability
    # -------------------------------------------------------------------------

    def set_status(self, message: str, phase: str = "") -> None:
        """Delegate to the workflow mixin's _set_status."""
        with workflow.unsafe.imports_passed_through():
            from kubani.framework.temporal.workflows import WorkflowStatus

        self._wf._set_status(WorkflowStatus.RUNNING, message, phase=phase)

    def log_event(self, kind: str, message: str, **data: Any) -> None:
        """Delegate to the workflow mixin's _log_event."""
        self._wf._log_event(kind, message, **data)

    # -------------------------------------------------------------------------
    # Control Flow
    # -------------------------------------------------------------------------

    async def wait_if_paused(self) -> bool:
        """Delegate to the workflow mixin's _wait_if_paused."""
        return await self._wf._wait_if_paused()
