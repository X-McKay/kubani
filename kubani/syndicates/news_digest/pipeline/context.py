"""PipelineContext protocol — the core abstraction for Context Injection.

This protocol defines the contract between the pipeline logic and its
execution environment. Every method that performs I/O, observability,
or control flow is declared here.

Concrete implementations:
    - ``TemporalContext``: Uses Temporal activities, workflow signals,
      and the ObservableWorkflowMixin for full production behavior.
    - ``LocalContext``: Uses in-memory mocks and print-based logging
      for fast, standalone testing and iteration.

The pipeline logic (``ingest.py``) calls only these methods, never
Temporal APIs directly. This makes the logic fully testable without
a Temporal server.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


# =============================================================================
# PipelineContext Protocol
# =============================================================================


@runtime_checkable
class PipelineContext(Protocol):
    """Protocol defining all I/O and observability for the ingest pipeline.

    Every method here represents a side-effect boundary. The pipeline
    logic calls these methods; the concrete context decides *how* to
    execute them (Temporal activity, local mock, etc.).
    """

    # -------------------------------------------------------------------------
    # I/O: Fetching
    # -------------------------------------------------------------------------

    async def fetch_documents(
        self,
        source_type: str,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Fetch raw documents from a source and convert to RawDocument dicts.

        This method is source-specific: the context implementation
        knows how to fetch RSS feeds, arXiv papers, or GitHub repos,
        and converts them to ``RawDocument.to_dict()`` format.

        Args:
            source_type: One of "rss", "arxiv", "github".
            **kwargs: Source-specific parameters (e.g., categories, max_results).

        Returns:
            List of RawDocument dicts.
        """
        ...

    # -------------------------------------------------------------------------
    # I/O: Content Enrichment
    # -------------------------------------------------------------------------

    async def enrich_documents(
        self,
        documents: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Enrich documents by fetching full-text content from their URLs.

        For RSS documents with short content, this fetches the article
        page and extracts the main text. Documents from other sources
        (arXiv, GitHub) or those that already have substantial content
        are passed through unchanged.

        Args:
            documents: List of RawDocument dicts.

        Returns:
            List of RawDocument dicts with enriched content.
        """
        ...

    # -------------------------------------------------------------------------
    # I/O: Deduplication
    # -------------------------------------------------------------------------

    async def check_duplicates(
        self,
        dedup_keys: list[str],
    ) -> dict[str, bool]:
        """Batch-check dedup keys against the cache.

        Args:
            dedup_keys: List of dedup cache keys to check.

        Returns:
            Dict mapping each key to True (duplicate) or False (new).
        """
        ...

    # -------------------------------------------------------------------------
    # I/O: Storage
    # -------------------------------------------------------------------------

    async def store_documents(
        self,
        documents: list[dict[str, Any]],
    ) -> int:
        """Store a batch of RawDocument dicts.

        Args:
            documents: List of RawDocument dicts.

        Returns:
            Number of documents successfully stored.
        """
        ...

    # -------------------------------------------------------------------------
    # I/O: Trigger downstream
    # -------------------------------------------------------------------------

    async def trigger_analysis(
        self,
        documents: list[dict[str, Any]],
        source_type: str,
    ) -> None:
        """Trigger the analysis workflow for a batch of documents.

        This is fire-and-forget: the ingest pipeline does not wait
        for analysis to complete.

        Args:
            documents: List of RawDocument dicts to analyze.
            source_type: The source type for workflow ID naming.
        """
        ...

    # -------------------------------------------------------------------------
    # Observability
    # -------------------------------------------------------------------------

    def set_status(self, message: str, phase: str = "") -> None:
        """Report the current pipeline status.

        In Temporal, this calls ``_set_status`` on the workflow mixin.
        Locally, this prints to stdout or logs.

        Args:
            message: Human-readable status message.
            phase: Current pipeline phase (e.g., "fetch", "dedup").
        """
        ...

    def log_event(self, kind: str, message: str, **data: Any) -> None:
        """Log a structured event.

        In Temporal, this calls ``_log_event`` on the workflow mixin.
        Locally, this prints to stdout or logs.

        Args:
            kind: Event type (e.g., "feeds_fetched", "error").
            message: Event description.
            **data: Additional event data.
        """
        ...

    # -------------------------------------------------------------------------
    # Control Flow
    # -------------------------------------------------------------------------

    async def wait_if_paused(self) -> bool:
        """Check if the pipeline should pause, and wait if so.

        In Temporal, this delegates to ``_wait_if_paused`` which
        blocks on a signal. Locally, this is a no-op that returns False.

        Returns:
            True if the pipeline was cancelled while paused, False otherwise.
        """
        ...
