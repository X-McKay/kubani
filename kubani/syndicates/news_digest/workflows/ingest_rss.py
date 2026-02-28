"""RSS Feed Ingest Workflow.

Collects articles from configured RSS feeds, deduplicates by URL hash,
and stores raw documents in Memory MCP. Designed to run on a frequent
schedule (every 15-30 minutes) since RSS feeds update often.

Dedup strategy: SHA-256 hash of the article URL, checked via
batch cache lookup before storage.
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
class RSSIngestInput:
    """Input for an RSS ingest run.

    Attributes:
        correlation_id: Optional tracking ID for observability.
    """

    correlation_id: str | None = None


@dataclass
class RSSIngestResult:
    """Result of an RSS ingest run.

    Attributes:
        feeds_fetched: Number of RSS feeds successfully fetched.
        articles_collected: Total articles found across all feeds.
        articles_new: Articles that passed deduplication.
        articles_stored: Articles successfully stored in Memory MCP.
        success: Whether the workflow completed without fatal errors.
        error: Error message if the workflow failed.
    """

    feeds_fetched: int = 0
    articles_collected: int = 0
    articles_new: int = 0
    articles_stored: int = 0
    success: bool = True
    error: str | None = None


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

    Queries:
        get_status: Inherited from ObservableWorkflowMixin.
        get_ingest_stats: Returns current collection statistics.
    """

    def __init__(self) -> None:
        self._init_observability("RSSIngestWorkflow")
        self._result = RSSIngestResult()

    @workflow.run
    async def run(self, input: RSSIngestInput | None = None) -> dict[str, Any]:
        """Execute an RSS ingest run.

        Args:
            input: Optional configuration. Defaults are used if omitted.

        Returns:
            RSSIngestResult as a plain dict.
        """
        if input is None:
            input = RSSIngestInput()

        self._set_status(WorkflowStatus.RUNNING, "Starting RSS ingest", phase="init")

        try:
            # Step 1: Fetch RSS feeds and convert to RawDocuments
            # (conversion is done in the activity to avoid sandbox restrictions)
            articles, raw_docs = await self._fetch_feeds()
            self._result.articles_collected = len(articles)

            if not articles:
                self._set_status(WorkflowStatus.COMPLETED, "No articles found")
                return self._build_result()

            # Step 2: Batch dedup
            new_docs = await self._batch_dedup(raw_docs)
            self._result.articles_new = len(new_docs)

            if not new_docs:
                self._set_status(WorkflowStatus.COMPLETED, "All articles already seen")
                return self._build_result()

            if await self._wait_if_paused():
                return self._build_result()

            # Step 3: Store new documents
            stored = await self._store_documents(new_docs)
            self._result.articles_stored = stored

            # Step 4: Trigger analysis for new documents (fire-and-forget)
            await self._trigger_analysis(new_docs)

            self._set_status(
                WorkflowStatus.COMPLETED,
                f"Stored {stored} new articles from {self._result.feeds_fetched} feeds",
            )
            return self._build_result()

        except Exception as e:
            self._set_status(WorkflowStatus.FAILED, f"RSS ingest failed: {e}")
            self._result.success = False
            self._result.error = str(e)
            raise

    # =========================================================================
    # Pipeline Steps
    # =========================================================================

    async def _fetch_feeds(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Fetch articles from all configured RSS feeds.

        Returns:
            Tuple of (articles, raw_documents). Raw documents are pre-converted
            in the activity to avoid Temporal sandbox restrictions.
        """
        from kubani.framework.temporal import collect_feeds_activity

        self._set_status(WorkflowStatus.RUNNING, "Fetching RSS feeds", phase="fetch")

        result = await workflow.execute_activity(
            collect_feeds_activity,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=FETCH_RETRY_POLICY,
        )

        if not result.get("success"):
            error = result.get("error", "Unknown error")
            self._log_event("error", f"Feed fetch failed: {error}")
            raise RuntimeError(f"Feed fetch failed: {error}")

        self._result.feeds_fetched = result.get("sources_fetched", 0)
        articles = result.get("articles", [])
        raw_documents = result.get("raw_documents", [])
        self._log_event(
            "feeds_fetched",
            f"Fetched {len(articles)} articles ({len(raw_documents)} docs) "
            f"from {self._result.feeds_fetched} feeds",
        )
        return articles, raw_documents

    async def _batch_dedup(self, documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Filter out documents that have already been stored.

        Uses batch cache lookup for efficiency instead of checking
        each document individually.

        Args:
            documents: List of RawDocument dicts.

        Returns:
            Filtered list containing only new documents.
        """
        from kubani.syndicates.news_digest.activities import batch_check_duplicates_activity
        from kubani.syndicates.news_digest.models import make_dedup_key

        self._set_status(
            WorkflowStatus.RUNNING,
            f"Checking {len(documents)} articles for duplicates",
            phase="dedup",
        )

        # Build dedup keys
        key_to_doc: dict[str, dict[str, Any]] = {}
        for doc in documents:
            key = make_dedup_key(doc["source_type"], doc["source_uri"])
            key_to_doc[key] = doc

        # Batch check
        result = await workflow.execute_activity(
            batch_check_duplicates_activity,
            args=[list(key_to_doc.keys())],
            start_to_close_timeout=timedelta(minutes=2),
            heartbeat_timeout=timedelta(seconds=30),
            retry_policy=STORAGE_RETRY_POLICY,
        )

        if not result.get("success"):
            # On dedup failure, pass all documents through (fail open)
            self._log_event("warning", "Dedup check failed, passing all documents through")
            return documents

        duplicates = result.get("duplicates", {})
        new_docs = [doc for key, doc in key_to_doc.items() if not duplicates.get(key, False)]

        dup_count = len(documents) - len(new_docs)
        self._log_event(
            "dedup_complete",
            f"{len(new_docs)} new, {dup_count} duplicates filtered",
        )
        return new_docs

    async def _trigger_analysis(self, documents: list[dict[str, Any]]) -> None:
        """Start the AnalyzeDocumentWorkflow as a child workflow.

        This is fire-and-forget: the ingest workflow does not wait for
        analysis to complete. The child workflow runs independently on
        the same task queue.

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
                id=f"analyze-rss-{run_id}",
                task_queue=workflow.info().task_queue,
                parent_close_policy=workflow.ParentClosePolicy.ABANDON,
            )
            self._log_event(
                "analysis_triggered",
                f"Started analysis for {len(documents)} documents",
            )
        except Exception as e:
            # Analysis trigger failure is non-fatal for ingest
            self._log_event(
                "analysis_trigger_error",
                f"Failed to trigger analysis: {e}",
            )

    async def _store_documents(self, documents: list[dict[str, Any]]) -> int:
        """Store new raw documents in Memory MCP.

        Args:
            documents: List of RawDocument dicts to store.

        Returns:
            Number of documents successfully stored.
        """
        from kubani.syndicates.news_digest.activities import store_raw_documents_activity

        self._set_status(
            WorkflowStatus.RUNNING,
            f"Storing {len(documents)} new articles",
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
            "feeds_fetched": self._result.feeds_fetched,
            "articles_collected": self._result.articles_collected,
            "articles_new": self._result.articles_new,
            "articles_stored": self._result.articles_stored,
            "success": self._result.success,
            "error": self._result.error,
        }

    @workflow.query
    def get_ingest_stats(self) -> dict[str, Any]:
        """Query current ingest statistics."""
        return {
            "feeds_fetched": self._result.feeds_fetched,
            "articles_collected": self._result.articles_collected,
            "articles_new": self._result.articles_new,
            "articles_stored": self._result.articles_stored,
        }
