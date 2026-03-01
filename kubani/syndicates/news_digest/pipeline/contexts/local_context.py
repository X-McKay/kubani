"""LocalContext — PipelineContext implementation for standalone testing.

This context provides a fully functional pipeline execution environment
that does not require Temporal. It uses configurable callables for I/O
and prints status/events to stdout, making it ideal for:

- Local development and debugging
- Unit testing with mock data
- Iterating on pipeline logic in isolation
- Inspecting intermediate outputs at each stage

Usage::

    from kubani.syndicates.news_digest.pipeline.contexts.local_context import LocalContext
    from kubani.syndicates.news_digest.pipeline.ingest import run_ingest_pipeline

    ctx = LocalContext(
        fetcher=my_mock_fetcher,
        duplicate_checker=my_mock_checker,
        storer=my_mock_storer,
    )
    result = await run_ingest_pipeline(ctx, "rss")
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


# =============================================================================
# Type aliases for callables
# =============================================================================

FetcherFn = Callable[..., Awaitable[list[dict[str, Any]]]]
EnricherFn = Callable[[list[dict[str, Any]]], Awaitable[list[dict[str, Any]]]]
DuplicateCheckerFn = Callable[[list[str]], Awaitable[dict[str, bool]]]
StorerFn = Callable[[list[dict[str, Any]]], Awaitable[int]]
AnalysisTriggerFn = Callable[[list[dict[str, Any]], str], Awaitable[None]]


# =============================================================================
# Default no-op implementations
# =============================================================================


async def _default_fetcher(source_type: str, **kwargs: Any) -> list[dict[str, Any]]:
    """Default fetcher that returns an empty list."""
    logger.info(f"[LocalContext] fetch_documents({source_type}) → [] (no fetcher configured)")
    return []


async def _default_enricher(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Default enricher that passes documents through unchanged."""
    logger.info(f"[LocalContext] enrich_documents({len(documents)} docs) → pass-through")
    return documents


async def _default_duplicate_checker(dedup_keys: list[str]) -> dict[str, bool]:
    """Default checker that treats all documents as new."""
    logger.info(f"[LocalContext] check_duplicates({len(dedup_keys)} keys) → all new")
    return {key: False for key in dedup_keys}


async def _default_storer(documents: list[dict[str, Any]]) -> int:
    """Default storer that logs and returns the count."""
    logger.info(f"[LocalContext] store_documents({len(documents)} docs) → {len(documents)}")
    return len(documents)


async def _default_analysis_trigger(
    documents: list[dict[str, Any]], source_type: str
) -> None:
    """Default trigger that logs the action."""
    logger.info(
        f"[LocalContext] trigger_analysis({len(documents)} docs, {source_type}) → no-op"
    )


# =============================================================================
# LocalContext
# =============================================================================


class LocalContext:
    """PipelineContext for local testing and development.

    All I/O operations are delegated to injectable callables, which
    default to no-ops that log their invocations. This makes it easy
    to test the pipeline with mock data, or to plug in real local
    implementations for end-to-end testing.

    Args:
        fetcher: Async callable for fetching documents.
        enricher: Async callable for enriching documents with full-text content.
        duplicate_checker: Async callable for checking duplicates.
        storer: Async callable for storing documents.
        analysis_trigger: Async callable for triggering analysis.
        verbose: If True, print status and events to stdout.
    """

    def __init__(
        self,
        fetcher: FetcherFn | None = None,
        enricher: EnricherFn | None = None,
        duplicate_checker: DuplicateCheckerFn | None = None,
        storer: StorerFn | None = None,
        analysis_trigger: AnalysisTriggerFn | None = None,
        verbose: bool = True,
    ) -> None:
        self._fetcher = fetcher or _default_fetcher
        self._enricher = enricher or _default_enricher
        self._duplicate_checker = duplicate_checker or _default_duplicate_checker
        self._storer = storer or _default_storer
        self._analysis_trigger = analysis_trigger or _default_analysis_trigger
        self._verbose = verbose
        self._events: list[dict[str, Any]] = []
        self._statuses: list[dict[str, str]] = []

    # -------------------------------------------------------------------------
    # I/O: Fetching
    # -------------------------------------------------------------------------

    async def fetch_documents(
        self,
        source_type: str,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Delegate to the configured fetcher callable."""
        return await self._fetcher(source_type, **kwargs)

    # -------------------------------------------------------------------------
    # I/O: Content Enrichment
    # -------------------------------------------------------------------------

    async def enrich_documents(
        self,
        documents: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Delegate to the configured enricher callable."""
        return await self._enricher(documents)

    # -------------------------------------------------------------------------
    # I/O: Deduplication
    # -------------------------------------------------------------------------

    async def check_duplicates(
        self,
        dedup_keys: list[str],
    ) -> dict[str, bool]:
        """Delegate to the configured duplicate checker callable."""
        return await self._duplicate_checker(dedup_keys)

    # -------------------------------------------------------------------------
    # I/O: Storage
    # -------------------------------------------------------------------------

    async def store_documents(
        self,
        documents: list[dict[str, Any]],
    ) -> int:
        """Delegate to the configured storer callable."""
        return await self._storer(documents)

    # -------------------------------------------------------------------------
    # I/O: Trigger downstream
    # -------------------------------------------------------------------------

    async def trigger_analysis(
        self,
        documents: list[dict[str, Any]],
        source_type: str,
    ) -> None:
        """Delegate to the configured analysis trigger callable."""
        await self._analysis_trigger(documents, source_type)

    # -------------------------------------------------------------------------
    # Observability
    # -------------------------------------------------------------------------

    def set_status(self, message: str, phase: str = "") -> None:
        """Record status and optionally print to stdout."""
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "phase": phase,
            "message": message,
        }
        self._statuses.append(entry)
        if self._verbose:
            phase_tag = f"[{phase}] " if phase else ""
            print(f"  STATUS: {phase_tag}{message}")

    def log_event(self, kind: str, message: str, **data: Any) -> None:
        """Record event and optionally print to stdout."""
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "kind": kind,
            "message": message,
            "data": data,
        }
        self._events.append(entry)
        if self._verbose:
            extra = f" | {json.dumps(data)}" if data else ""
            print(f"  EVENT [{kind}]: {message}{extra}")

    # -------------------------------------------------------------------------
    # Control Flow
    # -------------------------------------------------------------------------

    async def wait_if_paused(self) -> bool:
        """Always returns False (never paused in local mode)."""
        return False

    # -------------------------------------------------------------------------
    # Inspection helpers (for tests and debugging)
    # -------------------------------------------------------------------------

    @property
    def events(self) -> list[dict[str, Any]]:
        """All recorded events."""
        return list(self._events)

    @property
    def statuses(self) -> list[dict[str, str]]:
        """All recorded status updates."""
        return list(self._statuses)

    def get_events_by_kind(self, kind: str) -> list[dict[str, Any]]:
        """Filter events by kind."""
        return [e for e in self._events if e["kind"] == kind]

    def print_summary(self) -> None:
        """Print a human-readable summary of the pipeline run."""
        print("\n" + "=" * 60)
        print("Pipeline Run Summary")
        print("=" * 60)
        print(f"\nStatus updates: {len(self._statuses)}")
        for s in self._statuses:
            phase_tag = f"[{s['phase']}] " if s.get('phase') else ""
            print(f"  {phase_tag}{s['message']}")
        print(f"\nEvents: {len(self._events)}")
        for e in self._events:
            print(f"  [{e['kind']}] {e['message']}")
        print("=" * 60)
