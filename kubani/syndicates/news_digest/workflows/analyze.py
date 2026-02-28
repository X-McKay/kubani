"""Document Analysis Workflow.

Processes raw documents through AI-powered analysis to extract entities,
classify topics, score importance, and establish graph relationships.

This workflow is triggered after each ingest run completes. It queries
for unanalyzed documents and processes them one at a time, storing the
enriched results back into Memory MCP with graph connections.

The analysis is idempotent: re-analyzing a document overwrites the
previous analysis rather than creating duplicates.
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
class AnalyzeInput:
    """Input for an analysis run.

    Attributes:
        documents: List of RawDocument dicts to analyze. If empty, the
            workflow will query Memory MCP for unanalyzed documents.
        max_documents: Maximum number of documents to analyze per run.
        correlation_id: Optional tracking ID.
    """

    documents: list[dict[str, Any]] | None = None
    max_documents: int = 50
    correlation_id: str | None = None


@dataclass
class AnalyzeResult:
    """Result of an analysis run.

    Attributes:
        documents_received: Number of documents received for analysis.
        documents_analyzed: Number of documents successfully analyzed.
        documents_stored: Number of analyzed documents stored.
        relationships_created: Total graph relationships created.
        success: Whether the workflow completed without fatal errors.
        error: Error message if the workflow failed.
    """

    documents_received: int = 0
    documents_analyzed: int = 0
    documents_stored: int = 0
    relationships_created: int = 0
    success: bool = True
    error: str | None = None


# =============================================================================
# Retry Policies
# =============================================================================

ANALYSIS_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=5),
    maximum_interval=timedelta(minutes=1),
    maximum_attempts=2,
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
class AnalyzeDocumentWorkflow(ObservableWorkflowMixin):
    """Analyze raw documents to extract entities, topics, and importance.

    Pipeline:
    1. Receive or query raw documents that need analysis.
    2. For each document, call the content-analyst agent via
       ``analyze_document_activity`` to extract structured metadata.
    3. Store each analyzed document with graph relationships via
       ``store_analyzed_document_activity``.

    The workflow processes documents sequentially to respect LLM rate limits
    and provide clear progress tracking. Each document analysis is independent,
    so a failure on one document does not block the rest.
    """

    def __init__(self) -> None:
        self._init_observability("AnalyzeDocumentWorkflow")
        self._result = AnalyzeResult()

    @workflow.run
    async def run(self, input: AnalyzeInput | None = None) -> dict[str, Any]:
        """Execute an analysis run."""
        if input is None:
            input = AnalyzeInput()

        self._set_status(WorkflowStatus.RUNNING, "Starting document analysis", phase="init")

        try:
            # Step 1: Get documents to analyze
            documents = input.documents or []
            self._result.documents_received = len(documents)

            if not documents:
                self._set_status(WorkflowStatus.COMPLETED, "No documents to analyze")
                return self._build_result()

            # Cap at max_documents
            if len(documents) > input.max_documents:
                documents = documents[: input.max_documents]
                self._result.documents_received = len(documents)
                self._log_event(
                    "documents_capped",
                    f"Capped to {input.max_documents} documents",
                )

            # Step 2: Analyze each document
            analyzed_docs = await self._analyze_documents(documents)
            self._result.documents_analyzed = len(analyzed_docs)

            if not analyzed_docs:
                self._set_status(WorkflowStatus.COMPLETED, "No documents were analyzable")
                return self._build_result()

            if await self._wait_if_paused():
                return self._build_result()

            # Step 3: Store analyzed documents with graph relationships
            stored, rels = await self._store_analyzed_documents(analyzed_docs)
            self._result.documents_stored = stored
            self._result.relationships_created = rels

            self._set_status(
                WorkflowStatus.COMPLETED,
                f"Analyzed {len(analyzed_docs)} documents, "
                f"stored {stored}, created {rels} relationships",
            )
            return self._build_result()

        except Exception as e:
            self._set_status(WorkflowStatus.FAILED, f"Analysis failed: {e}")
            self._result.success = False
            self._result.error = str(e)
            raise

    # =========================================================================
    # Pipeline Steps
    # =========================================================================

    async def _analyze_documents(
        self, documents: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Analyze each document using the content-analyst agent.

        Processes documents sequentially. Failures on individual documents
        are logged but do not stop the pipeline.

        Args:
            documents: List of RawDocument dicts.

        Returns:
            List of AnalyzedDocument dicts for successfully analyzed documents.
        """
        from kubani.syndicates.news_digest.activities import analyze_document_activity

        analyzed: list[dict[str, Any]] = []
        total = len(documents)

        for i, doc in enumerate(documents):
            if await self._wait_if_paused():
                break

            title = doc.get("title", "Unknown")[:60]
            self._set_status(
                WorkflowStatus.RUNNING,
                f"Analyzing document {i + 1}/{total}: {title}",
                phase="analyze",
                progress=((i + 1) / total) * 100,
            )

            try:
                result = await workflow.execute_activity(
                    analyze_document_activity,
                    args=[doc],
                    start_to_close_timeout=timedelta(minutes=3),
                    retry_policy=ANALYSIS_RETRY_POLICY,
                )

                analyzed_doc = result.get("analyzed_document", {})
                if analyzed_doc:
                    analyzed.append(analyzed_doc)

                if not result.get("success"):
                    self._log_event(
                        "analysis_partial",
                        f"Partial analysis for '{title}': {result.get('error', '')}",
                    )

            except Exception as e:
                self._log_event(
                    "analysis_error",
                    f"Failed to analyze '{title}': {e}",
                )

        self._log_event(
            "analysis_complete",
            f"Analyzed {len(analyzed)}/{total} documents",
        )
        return analyzed

    async def _store_analyzed_documents(
        self, documents: list[dict[str, Any]]
    ) -> tuple[int, int]:
        """Store analyzed documents with graph relationships.

        Args:
            documents: List of AnalyzedDocument dicts.

        Returns:
            Tuple of (stored_count, relationships_created).
        """
        from kubani.syndicates.news_digest.activities import store_analyzed_document_activity

        stored_count = 0
        total_rels = 0
        total = len(documents)

        for i, doc in enumerate(documents):
            title = doc.get("title", "Unknown")[:60]
            self._set_status(
                WorkflowStatus.RUNNING,
                f"Storing analyzed document {i + 1}/{total}: {title}",
                phase="store",
                progress=((i + 1) / total) * 100,
            )

            try:
                result = await workflow.execute_activity(
                    store_analyzed_document_activity,
                    args=[doc],
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=STORAGE_RETRY_POLICY,
                )

                if result.get("success"):
                    stored_count += 1
                    total_rels += result.get("relationships_created", 0)
                else:
                    self._log_event(
                        "store_error",
                        f"Failed to store '{title}': {result.get('error', '')}",
                    )

            except Exception as e:
                self._log_event("store_error", f"Failed to store '{title}': {e}")

        self._log_event(
            "storage_complete",
            f"Stored {stored_count}/{total} documents, {total_rels} relationships",
        )
        return stored_count, total_rels

    # =========================================================================
    # Result Building & Queries
    # =========================================================================

    def _build_result(self) -> dict[str, Any]:
        """Build the result dictionary."""
        return {
            "documents_received": self._result.documents_received,
            "documents_analyzed": self._result.documents_analyzed,
            "documents_stored": self._result.documents_stored,
            "relationships_created": self._result.relationships_created,
            "success": self._result.success,
            "error": self._result.error,
        }

    @workflow.query
    def get_analysis_stats(self) -> dict[str, Any]:
        """Query current analysis statistics."""
        return {
            "documents_received": self._result.documents_received,
            "documents_analyzed": self._result.documents_analyzed,
            "documents_stored": self._result.documents_stored,
            "relationships_created": self._result.relationships_created,
        }
