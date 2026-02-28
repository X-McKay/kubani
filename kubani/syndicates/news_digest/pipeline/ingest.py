"""Shared ingest pipeline logic — the single source of truth.

This module contains the core ingest pipeline that is used by all three
source-specific workflows (RSS, arXiv, GitHub). The logic is written
against the ``PipelineContext`` protocol, so it is completely decoupled
from Temporal and can be tested locally with mock contexts.

The pipeline flow is:

    fetch → convert → dedup → store → trigger_analysis

Fetch and convert are handled together by ``ctx.fetch_documents()``,
since both are source-specific. Everything from dedup onward is generic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from kubani.syndicates.news_digest.models import make_dedup_key
from kubani.syndicates.news_digest.pipeline.context import PipelineContext


# =============================================================================
# Result Dataclass
# =============================================================================


@dataclass
class IngestResult:
    """Result of an ingest pipeline run.

    This is a source-agnostic result structure. The ``source_type``
    field indicates which source was ingested.
    """

    source_type: str = ""
    documents_collected: int = 0
    documents_new: int = 0
    documents_stored: int = 0
    success: bool = True
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary."""
        return {
            "source_type": self.source_type,
            "documents_collected": self.documents_collected,
            "documents_new": self.documents_new,
            "documents_stored": self.documents_stored,
            "success": self.success,
            "error": self.error,
            **self.extra,
        }


# =============================================================================
# Pipeline Logic
# =============================================================================


async def run_ingest_pipeline(
    ctx: PipelineContext,
    source_type: str,
    **fetch_kwargs: Any,
) -> IngestResult:
    """Execute the ingest pipeline for any source type.

    This function contains the complete ingest business logic. It is
    called by both the Temporal workflow (with a ``TemporalContext``)
    and the local runner (with a ``LocalContext``).

    Args:
        ctx: The pipeline context providing I/O and observability.
        source_type: One of "rss", "arxiv", "github".
        **fetch_kwargs: Source-specific fetch parameters passed through
            to ``ctx.fetch_documents()``.

    Returns:
        An ``IngestResult`` with collection statistics.
    """
    result = IngestResult(source_type=source_type)

    try:
        # =================================================================
        # Step 1: Fetch and convert documents
        # =================================================================
        ctx.set_status(f"Fetching {source_type} documents", phase="fetch")

        raw_docs = await ctx.fetch_documents(source_type, **fetch_kwargs)
        result.documents_collected = len(raw_docs)

        if not raw_docs:
            ctx.set_status(f"No {source_type} documents found", phase="complete")
            return result

        ctx.log_event(
            "documents_fetched",
            f"Fetched {len(raw_docs)} {source_type} documents",
        )

        # =================================================================
        # Step 2: Check for pause/cancel
        # =================================================================
        if await ctx.wait_if_paused():
            result.success = True
            return result

        # =================================================================
        # Step 3: Batch deduplication
        # =================================================================
        ctx.set_status(
            f"Checking {len(raw_docs)} documents for duplicates",
            phase="dedup",
        )

        # Build dedup key → document mapping
        key_to_doc: dict[str, dict[str, Any]] = {}
        for doc in raw_docs:
            key = make_dedup_key(doc["source_type"], doc["source_uri"])
            key_to_doc[key] = doc

        # Batch check
        duplicates = await ctx.check_duplicates(list(key_to_doc.keys()))

        # Filter to new documents only
        new_docs = [
            doc for key, doc in key_to_doc.items()
            if not duplicates.get(key, False)
        ]
        result.documents_new = len(new_docs)

        dup_count = len(raw_docs) - len(new_docs)
        ctx.log_event(
            "dedup_complete",
            f"{len(new_docs)} new, {dup_count} duplicates filtered",
        )

        if not new_docs:
            ctx.set_status(
                f"All {source_type} documents already seen",
                phase="complete",
            )
            return result

        # =================================================================
        # Step 4: Check for pause/cancel
        # =================================================================
        if await ctx.wait_if_paused():
            result.success = True
            return result

        # =================================================================
        # Step 5: Store new documents
        # =================================================================
        ctx.set_status(
            f"Storing {len(new_docs)} new documents",
            phase="store",
        )

        stored = await ctx.store_documents(new_docs)
        result.documents_stored = stored

        ctx.log_event("documents_stored", f"Stored {stored} documents")

        # =================================================================
        # Step 6: Trigger analysis (fire-and-forget)
        # =================================================================
        ctx.set_status(
            f"Triggering analysis for {len(new_docs)} documents",
            phase="trigger_analyze",
        )

        await ctx.trigger_analysis(new_docs, source_type)

        ctx.set_status(
            f"Stored {stored} new {source_type} documents",
            phase="complete",
        )
        return result

    except Exception as e:
        ctx.log_event("error", f"Ingest pipeline failed: {e}")
        result.success = False
        result.error = str(e)
        raise
