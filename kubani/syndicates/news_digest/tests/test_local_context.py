"""Tests for the LocalContext implementation.

These tests validate the LocalContext's behavior as a standalone
component, ensuring that:

- Default callables work correctly (no-ops)
- Custom callables are properly invoked
- Observability recording works (statuses, events)
- Inspection helpers return correct data
"""

from __future__ import annotations

import pytest
from typing import Any

from kubani.syndicates.news_digest.pipeline.contexts.local_context import LocalContext


# =============================================================================
# Tests: Default Behavior
# =============================================================================


class TestLocalContextDefaults:
    """Test LocalContext with default (no-op) callables."""

    @pytest.mark.asyncio
    async def test_default_fetch_returns_empty(self) -> None:
        """Default fetcher returns an empty list."""
        ctx = LocalContext(verbose=False)
        result = await ctx.fetch_documents("rss")
        assert result == []

    @pytest.mark.asyncio
    async def test_default_dedup_returns_all_new(self) -> None:
        """Default checker treats all keys as new."""
        ctx = LocalContext(verbose=False)
        result = await ctx.check_duplicates(["key1", "key2"])
        assert result == {"key1": False, "key2": False}

    @pytest.mark.asyncio
    async def test_default_store_returns_count(self) -> None:
        """Default storer returns the document count."""
        ctx = LocalContext(verbose=False)
        docs = [{"title": "doc1"}, {"title": "doc2"}]
        result = await ctx.store_documents(docs)
        assert result == 2

    @pytest.mark.asyncio
    async def test_default_trigger_is_noop(self) -> None:
        """Default trigger does not raise."""
        ctx = LocalContext(verbose=False)
        await ctx.trigger_analysis([{"title": "doc1"}], "rss")

    @pytest.mark.asyncio
    async def test_wait_if_paused_returns_false(self) -> None:
        """wait_if_paused always returns False."""
        ctx = LocalContext(verbose=False)
        result = await ctx.wait_if_paused()
        assert result is False


# =============================================================================
# Tests: Custom Callables
# =============================================================================


class TestLocalContextCustomCallables:
    """Test LocalContext with injected custom callables."""

    @pytest.mark.asyncio
    async def test_custom_fetcher(self) -> None:
        """Custom fetcher is called with correct args."""
        call_log: list[tuple[str, dict]] = []

        async def my_fetcher(source_type: str, **kwargs: Any) -> list[dict[str, Any]]:
            call_log.append((source_type, kwargs))
            return [{"title": "test"}]

        ctx = LocalContext(fetcher=my_fetcher, verbose=False)
        result = await ctx.fetch_documents("arxiv", max_results=10)

        assert result == [{"title": "test"}]
        assert len(call_log) == 1
        assert call_log[0] == ("arxiv", {"max_results": 10})

    @pytest.mark.asyncio
    async def test_custom_checker(self) -> None:
        """Custom duplicate checker is called with correct keys."""

        async def my_checker(keys: list[str]) -> dict[str, bool]:
            return {k: k == "dup_key" for k in keys}

        ctx = LocalContext(duplicate_checker=my_checker, verbose=False)
        result = await ctx.check_duplicates(["new_key", "dup_key"])

        assert result["new_key"] is False
        assert result["dup_key"] is True

    @pytest.mark.asyncio
    async def test_custom_storer(self) -> None:
        """Custom storer is called with the documents."""
        stored: list[dict] = []

        async def my_storer(docs: list[dict[str, Any]]) -> int:
            stored.extend(docs)
            return len(docs)

        ctx = LocalContext(storer=my_storer, verbose=False)
        result = await ctx.store_documents([{"title": "a"}, {"title": "b"}])

        assert result == 2
        assert len(stored) == 2


# =============================================================================
# Tests: Observability Recording
# =============================================================================


class TestLocalContextObservability:
    """Test that LocalContext records statuses and events."""

    def test_set_status_records(self) -> None:
        """set_status records entries with phase."""
        ctx = LocalContext(verbose=False)
        ctx.set_status("Fetching feeds", phase="fetch")
        ctx.set_status("Deduplicating", phase="dedup")

        assert len(ctx.statuses) == 2
        assert ctx.statuses[0]["phase"] == "fetch"
        assert ctx.statuses[0]["message"] == "Fetching feeds"
        assert ctx.statuses[1]["phase"] == "dedup"

    def test_log_event_records(self) -> None:
        """log_event records entries with kind and data."""
        ctx = LocalContext(verbose=False)
        ctx.log_event("feeds_fetched", "Got 10 articles", count=10)
        ctx.log_event("error", "Something failed")

        assert len(ctx.events) == 2
        assert ctx.events[0]["kind"] == "feeds_fetched"
        assert ctx.events[0]["data"] == {"count": 10}
        assert ctx.events[1]["kind"] == "error"

    def test_get_events_by_kind(self) -> None:
        """get_events_by_kind filters correctly."""
        ctx = LocalContext(verbose=False)
        ctx.log_event("info", "msg1")
        ctx.log_event("error", "msg2")
        ctx.log_event("info", "msg3")

        info_events = ctx.get_events_by_kind("info")
        assert len(info_events) == 2

        error_events = ctx.get_events_by_kind("error")
        assert len(error_events) == 1

    def test_events_and_statuses_are_copies(self) -> None:
        """Properties return copies, not references."""
        ctx = LocalContext(verbose=False)
        ctx.set_status("test")
        ctx.log_event("test", "msg")

        statuses = ctx.statuses
        events = ctx.events

        # Mutating the returned lists should not affect the context
        statuses.clear()
        events.clear()

        assert len(ctx.statuses) == 1
        assert len(ctx.events) == 1
