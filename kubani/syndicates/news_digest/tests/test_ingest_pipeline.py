"""Tests for the shared ingest pipeline logic.

These tests validate the core pipeline business logic using the
``LocalContext`` — no Temporal server required. They run instantly
and cover the full range of pipeline behaviors:

- Happy path: fetch → dedup → store → trigger
- Empty fetch: no documents found
- All duplicates: everything filtered out
- Partial duplicates: some new, some filtered
- Fetch failure: error propagation
- Store failure: error propagation
- Pause/cancel: early exit

Each test constructs a ``LocalContext`` with specific mock callables,
runs ``run_ingest_pipeline``, and asserts on the result and recorded
events/statuses.
"""

from __future__ import annotations

import pytest
from typing import Any

from kubani.syndicates.news_digest.models import (
    make_dedup_key,
    raw_document_from_arxiv_paper,
    raw_document_from_github_repo,
    raw_document_from_rss_entry,
)
from kubani.syndicates.news_digest.pipeline import IngestResult, run_ingest_pipeline
from kubani.syndicates.news_digest.pipeline.contexts.local_context import LocalContext


# =============================================================================
# Test Fixtures
# =============================================================================


def _make_rss_docs(count: int = 3) -> list[dict[str, Any]]:
    """Create a list of mock RSS RawDocument dicts."""
    entries = [
        {
            "title": f"Article {i}: AI Breakthrough #{i}",
            "url": f"https://example.com/article-{i}",
            "source": "TestFeed",
            "published_date": "2026-02-28T10:00:00Z",
            "summary": f"Summary of article {i}.",
            "author": f"Author {i}",
            "source_category": "ai_labs",
        }
        for i in range(count)
    ]
    return [raw_document_from_rss_entry(e).to_dict() for e in entries]


def _make_arxiv_docs(count: int = 2) -> list[dict[str, Any]]:
    """Create a list of mock arXiv RawDocument dicts."""
    papers = [
        {
            "arxiv_id": f"2602.{i:05d}",
            "title": f"Paper {i}: Scaling Laws",
            "authors": [f"Author {i}"],
            "abstract": f"Abstract of paper {i}.",
            "categories": ["cs.AI"],
            "published_at": "2026-02-28",
        }
        for i in range(count)
    ]
    return [raw_document_from_arxiv_paper(p).to_dict() for p in papers]


def _make_github_docs(count: int = 2) -> list[dict[str, Any]]:
    """Create a list of mock GitHub RawDocument dicts."""
    repos = [
        {
            "repo_url": f"https://github.com/example/repo-{i}",
            "name": f"repo-{i}",
            "description": f"Description of repo {i}",
            "stars": 1000 * (i + 1),
            "language": "Python",
            "topics": ["ai"],
            "forks": 100 * (i + 1),
            "trending_score": 0.5 + i * 0.1,
        }
        for i in range(count)
    ]
    return [raw_document_from_github_repo(r).to_dict() for r in repos]


# =============================================================================
# Helper: Build a LocalContext with specific behavior
# =============================================================================


def _build_context(
    docs: list[dict[str, Any]] | None = None,
    duplicate_keys: set[str] | None = None,
    fetch_error: str | None = None,
    store_error: str | None = None,
    store_count: int | None = None,
    paused: bool = False,
) -> LocalContext:
    """Build a LocalContext with configurable mock behavior."""

    async def fetcher(source_type: str, **kwargs: Any) -> list[dict[str, Any]]:
        if fetch_error:
            raise RuntimeError(fetch_error)
        return docs or []

    async def checker(dedup_keys: list[str]) -> dict[str, bool]:
        dup_set = duplicate_keys or set()
        return {key: key in dup_set for key in dedup_keys}

    async def storer(documents: list[dict[str, Any]]) -> int:
        if store_error:
            raise RuntimeError(store_error)
        if store_count is not None:
            return store_count
        return len(documents)

    triggered: list[tuple[int, str]] = []

    async def trigger(documents: list[dict[str, Any]], source_type: str) -> None:
        triggered.append((len(documents), source_type))

    async def enricher(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return documents  # Pass-through by default

    ctx = LocalContext(
        fetcher=fetcher,
        enricher=enricher,
        duplicate_checker=checker,
        storer=storer,
        analysis_trigger=trigger,
        verbose=False,
    )
    ctx._triggered = triggered  # type: ignore[attr-defined]

    if paused:
        # Override wait_if_paused to simulate cancellation
        async def _paused() -> bool:
            return True

        ctx.wait_if_paused = _paused  # type: ignore[assignment]

    return ctx


# =============================================================================
# Tests: RSS Source
# =============================================================================


class TestRSSIngestPipeline:
    """Test the ingest pipeline with RSS source data."""

    @pytest.mark.asyncio
    async def test_happy_path(self) -> None:
        """Full pipeline: 3 articles fetched, 0 duplicates, 3 stored."""
        docs = _make_rss_docs(3)
        ctx = _build_context(docs=docs)

        result = await run_ingest_pipeline(ctx, "rss")

        assert result.success is True
        assert result.source_type == "rss"
        assert result.documents_collected == 3
        assert result.documents_new == 3
        assert result.documents_stored == 3
        assert result.error is None

        # Verify analysis was triggered
        assert len(ctx._triggered) == 1  # type: ignore[attr-defined]
        assert ctx._triggered[0] == (3, "rss")  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_empty_fetch(self) -> None:
        """No articles found — pipeline exits early."""
        ctx = _build_context(docs=[])

        result = await run_ingest_pipeline(ctx, "rss")

        assert result.success is True
        assert result.documents_collected == 0
        assert result.documents_new == 0
        assert result.documents_stored == 0

        # No analysis should be triggered
        assert len(ctx._triggered) == 0  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_all_duplicates(self) -> None:
        """All articles are duplicates — nothing stored."""
        docs = _make_rss_docs(3)
        dup_keys = {
            make_dedup_key(doc["source_type"], doc["source_uri"])
            for doc in docs
        }
        ctx = _build_context(docs=docs, duplicate_keys=dup_keys)

        result = await run_ingest_pipeline(ctx, "rss")

        assert result.success is True
        assert result.documents_collected == 3
        assert result.documents_new == 0
        assert result.documents_stored == 0

        # No analysis should be triggered
        assert len(ctx._triggered) == 0  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_partial_duplicates(self) -> None:
        """2 of 3 articles are duplicates — only 1 stored."""
        docs = _make_rss_docs(3)
        # Mark first two as duplicates
        dup_keys = {
            make_dedup_key(docs[0]["source_type"], docs[0]["source_uri"]),
            make_dedup_key(docs[1]["source_type"], docs[1]["source_uri"]),
        }
        ctx = _build_context(docs=docs, duplicate_keys=dup_keys)

        result = await run_ingest_pipeline(ctx, "rss")

        assert result.success is True
        assert result.documents_collected == 3
        assert result.documents_new == 1
        assert result.documents_stored == 1

    @pytest.mark.asyncio
    async def test_fetch_failure(self) -> None:
        """Fetch raises an error — pipeline fails."""
        ctx = _build_context(fetch_error="Connection timeout")

        with pytest.raises(RuntimeError, match="Connection timeout"):
            await run_ingest_pipeline(ctx, "rss")

    @pytest.mark.asyncio
    async def test_store_failure(self) -> None:
        """Store raises an error — pipeline fails."""
        docs = _make_rss_docs(2)
        ctx = _build_context(docs=docs, store_error="Storage unavailable")

        with pytest.raises(RuntimeError, match="Storage unavailable"):
            await run_ingest_pipeline(ctx, "rss")

    @pytest.mark.asyncio
    async def test_paused_before_dedup(self) -> None:
        """Pipeline is paused/cancelled before dedup — exits early."""
        docs = _make_rss_docs(3)
        ctx = _build_context(docs=docs, paused=True)

        result = await run_ingest_pipeline(ctx, "rss")

        assert result.success is True
        assert result.documents_collected == 3
        # Pipeline exited before dedup, so no new/stored counts
        assert result.documents_new == 0
        assert result.documents_stored == 0


# =============================================================================
# Tests: arXiv Source
# =============================================================================


class TestArxivIngestPipeline:
    """Test the ingest pipeline with arXiv source data."""

    @pytest.mark.asyncio
    async def test_happy_path(self) -> None:
        """Full pipeline with arXiv papers."""
        docs = _make_arxiv_docs(2)
        ctx = _build_context(docs=docs)

        result = await run_ingest_pipeline(ctx, "arxiv")

        assert result.success is True
        assert result.source_type == "arxiv"
        assert result.documents_collected == 2
        assert result.documents_new == 2
        assert result.documents_stored == 2

    @pytest.mark.asyncio
    async def test_with_duplicates(self) -> None:
        """One arXiv paper is a duplicate."""
        docs = _make_arxiv_docs(2)
        dup_keys = {
            make_dedup_key(docs[0]["source_type"], docs[0]["source_uri"]),
        }
        ctx = _build_context(docs=docs, duplicate_keys=dup_keys)

        result = await run_ingest_pipeline(ctx, "arxiv")

        assert result.documents_collected == 2
        assert result.documents_new == 1
        assert result.documents_stored == 1


# =============================================================================
# Tests: GitHub Source
# =============================================================================


class TestGitHubIngestPipeline:
    """Test the ingest pipeline with GitHub source data."""

    @pytest.mark.asyncio
    async def test_happy_path(self) -> None:
        """Full pipeline with GitHub repos."""
        docs = _make_github_docs(2)
        ctx = _build_context(docs=docs)

        result = await run_ingest_pipeline(ctx, "github")

        assert result.success is True
        assert result.source_type == "github"
        assert result.documents_collected == 2
        assert result.documents_new == 2
        assert result.documents_stored == 2

    @pytest.mark.asyncio
    async def test_with_duplicates(self) -> None:
        """One GitHub repo is a duplicate."""
        docs = _make_github_docs(2)
        dup_keys = {
            make_dedup_key(docs[0]["source_type"], docs[0]["source_uri"]),
        }
        ctx = _build_context(docs=docs, duplicate_keys=dup_keys)

        result = await run_ingest_pipeline(ctx, "github")

        assert result.documents_collected == 2
        assert result.documents_new == 1
        assert result.documents_stored == 1


# =============================================================================
# Tests: Observability
# =============================================================================


class TestPipelineObservability:
    """Test that the pipeline correctly reports status and events."""

    @pytest.mark.asyncio
    async def test_status_phases(self) -> None:
        """Pipeline reports status for each phase."""
        docs = _make_rss_docs(2)
        ctx = _build_context(docs=docs)
        # Enable verbose to capture statuses
        ctx._verbose = False

        result = await run_ingest_pipeline(ctx, "rss")

        phases = [s["phase"] for s in ctx.statuses]
        assert "fetch" in phases
        assert "enrich" in phases
        assert "dedup" in phases
        assert "store" in phases
        assert "trigger_analyze" in phases
        assert "complete" in phases

    @pytest.mark.asyncio
    async def test_events_logged(self) -> None:
        """Pipeline logs structured events."""
        docs = _make_rss_docs(2)
        ctx = _build_context(docs=docs)
        ctx._verbose = False

        result = await run_ingest_pipeline(ctx, "rss")

        event_kinds = [e["kind"] for e in ctx.events]
        assert "documents_fetched" in event_kinds
        assert "documents_enriched" in event_kinds
        assert "dedup_complete" in event_kinds
        assert "documents_stored" in event_kinds

    @pytest.mark.asyncio
    async def test_empty_fetch_status(self) -> None:
        """Empty fetch reports completion status."""
        ctx = _build_context(docs=[])
        ctx._verbose = False

        result = await run_ingest_pipeline(ctx, "rss")

        phases = [s["phase"] for s in ctx.statuses]
        assert "fetch" in phases
        assert "complete" in phases
        # Should NOT have dedup/store phases
        assert "dedup" not in phases
        assert "store" not in phases


# =============================================================================
# Tests: IngestResult
# =============================================================================


class TestIngestResult:
    """Test the IngestResult dataclass."""

    def test_to_dict(self) -> None:
        """IngestResult serializes correctly."""
        result = IngestResult(
            source_type="rss",
            documents_collected=10,
            documents_new=7,
            documents_stored=7,
            success=True,
        )
        d = result.to_dict()
        assert d["source_type"] == "rss"
        assert d["documents_collected"] == 10
        assert d["documents_new"] == 7
        assert d["documents_stored"] == 7
        assert d["success"] is True
        assert d["error"] is None

    def test_to_dict_with_extra(self) -> None:
        """IngestResult includes extra fields."""
        result = IngestResult(
            source_type="rss",
            extra={"feeds_fetched": 5},
        )
        d = result.to_dict()
        assert d["feeds_fetched"] == 5

    def test_default_values(self) -> None:
        """IngestResult has sensible defaults."""
        result = IngestResult()
        assert result.source_type == ""
        assert result.documents_collected == 0
        assert result.success is True
        assert result.error is None
