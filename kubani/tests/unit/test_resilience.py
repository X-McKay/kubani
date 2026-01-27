"""
Tests for the resilience module: DedupService, RateLimiter, retry_with_backoff, run_with_semaphore.

Uses fakeredis for Redis testing.
"""

import asyncio

import pytest

from kubani.framework.resilience import (
    DedupConfig,
    DedupService,
    RateLimitConfig,
    RateLimiter,
    RetryConfig,
    content_hash,
    retry_with_backoff,
    run_with_semaphore,
)

# =============================================================================
# DedupService Tests
# =============================================================================


class TestDedupService:
    """Test DedupService functionality."""

    @pytest.fixture
    async def dedup_service(self):
        """Create a DedupService with in-memory fallback (no Redis)."""
        config = DedupConfig(ttl_seconds=3600, enabled=False)  # Disable Redis
        service = DedupService(namespace="test", config=config)
        await service.initialize()
        yield service
        await service.close()

    @pytest.mark.asyncio
    async def test_mark_and_check_seen(self, dedup_service):
        """Test marking an item as seen and checking it."""
        item_id = "article-123"

        # Should not be seen initially
        assert not await dedup_service.is_seen(item_id)

        # Mark as seen
        await dedup_service.mark_seen(item_id)

        # Should be seen now
        assert await dedup_service.is_seen(item_id)

    @pytest.mark.asyncio
    async def test_mark_seen_batch(self, dedup_service):
        """Test marking multiple items as seen."""
        item_ids = ["item-1", "item-2", "item-3"]

        # Mark all as seen
        await dedup_service.mark_seen_batch(item_ids)

        # All should be seen
        for item_id in item_ids:
            assert await dedup_service.is_seen(item_id)

    @pytest.mark.asyncio
    async def test_filter_unseen(self, dedup_service):
        """Test filtering to only unseen items."""
        # Mark some items as seen
        await dedup_service.mark_seen("seen-1")
        await dedup_service.mark_seen("seen-2")

        # Filter a mixed list
        all_items = ["seen-1", "unseen-1", "seen-2", "unseen-2"]
        unseen = await dedup_service.filter_unseen(all_items)

        assert set(unseen) == {"unseen-1", "unseen-2"}

    @pytest.mark.asyncio
    async def test_filter_unseen_empty_list(self, dedup_service):
        """Test filtering an empty list."""
        unseen = await dedup_service.filter_unseen([])
        assert unseen == []

    @pytest.mark.asyncio
    async def test_key_generation(self, dedup_service):
        """Test that keys are namespaced correctly."""
        key = dedup_service._make_key("article-123")
        assert key == "dedup:test:article-123"


class TestContentHash:
    """Test content_hash utility."""

    def test_content_hash_consistent(self):
        """Same content should produce same hash."""
        h1 = content_hash("Hello, World!")
        h2 = content_hash("Hello, World!")
        assert h1 == h2

    def test_content_hash_different_for_different_content(self):
        """Different content should produce different hashes."""
        h1 = content_hash("Hello, World!")
        h2 = content_hash("Goodbye, World!")
        assert h1 != h2

    def test_content_hash_is_16_chars(self):
        """Hash should be truncated to 16 characters."""
        h = content_hash("Test content")
        assert len(h) == 16


# =============================================================================
# RateLimiter Tests
# =============================================================================


class TestRateLimiter:
    """Test RateLimiter functionality."""

    @pytest.mark.asyncio
    async def test_burst_allows_immediate_requests(self):
        """Burst size should allow immediate requests."""
        config = RateLimitConfig(requests_per_second=1.0, burst_size=3)
        limiter = RateLimiter(config)

        # Should be able to make 3 requests immediately
        start = asyncio.get_event_loop().time()
        for _ in range(3):
            await limiter.acquire()
        elapsed = asyncio.get_event_loop().time() - start

        # Should complete quickly (allowing some margin for test overhead)
        assert elapsed < 0.5

    @pytest.mark.asyncio
    async def test_rate_limiting_delays_requests(self):
        """Requests beyond burst should be delayed."""
        config = RateLimitConfig(requests_per_second=10.0, burst_size=1)
        limiter = RateLimiter(config)

        # First request is immediate
        await limiter.acquire()

        # Second request should be delayed
        start = asyncio.get_event_loop().time()
        await limiter.acquire()
        elapsed = asyncio.get_event_loop().time() - start

        # Should have waited ~0.1 seconds (10 req/sec = 0.1 sec between)
        assert elapsed >= 0.05  # Allow some tolerance

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test rate limiter as context manager."""
        config = RateLimitConfig(requests_per_second=100.0, burst_size=1)
        limiter = RateLimiter(config)

        async with limiter:
            pass  # Should complete without error

    def test_rate_calculation_per_second(self):
        """Test rate calculation from requests_per_second."""
        config = RateLimitConfig(requests_per_second=10.0)
        limiter = RateLimiter(config)
        assert limiter._tokens_per_second == 10.0

    def test_rate_calculation_per_minute(self):
        """Test rate calculation from requests_per_minute."""
        config = RateLimitConfig(requests_per_minute=60.0)
        limiter = RateLimiter(config)
        assert limiter._tokens_per_second == 1.0

    def test_rate_calculation_per_hour(self):
        """Test rate calculation from requests_per_hour."""
        config = RateLimitConfig(requests_per_hour=3600.0)
        limiter = RateLimiter(config)
        assert limiter._tokens_per_second == 1.0

    def test_most_restrictive_rate_used(self):
        """When multiple rates specified, most restrictive should be used."""
        config = RateLimitConfig(
            requests_per_second=10.0,  # 10/sec
            requests_per_minute=30.0,  # 0.5/sec - most restrictive
        )
        limiter = RateLimiter(config)
        assert limiter._tokens_per_second == 0.5


# =============================================================================
# retry_with_backoff Tests
# =============================================================================


class TestRetryWithBackoff:
    """Test retry_with_backoff decorator."""

    @pytest.mark.asyncio
    async def test_successful_function_returns_immediately(self):
        """Successful function should return without retry."""
        call_count = 0

        @retry_with_backoff(max_attempts=3)
        async def successful_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await successful_func()

        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_failure(self):
        """Function should be retried on failure."""
        call_count = 0

        @retry_with_backoff(max_attempts=3, base_delay=0.01)
        async def failing_then_succeeding():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary error")
            return "success"

        result = await failing_then_succeeding()

        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_raises_after_max_attempts(self):
        """Should raise after max attempts exhausted."""
        call_count = 0

        @retry_with_backoff(max_attempts=2, base_delay=0.01)
        async def always_fails():
            nonlocal call_count
            call_count += 1
            raise ValueError("Permanent error")

        with pytest.raises(ValueError, match="Permanent error"):
            await always_fails()

        assert call_count == 2

    @pytest.mark.asyncio
    async def test_respects_retryable_exceptions(self):
        """Should only retry specified exception types."""
        call_count = 0

        @retry_with_backoff(
            max_attempts=3,
            base_delay=0.01,
            retryable_exceptions=(ValueError,),
        )
        async def raises_type_error():
            nonlocal call_count
            call_count += 1
            raise TypeError("Not retryable")

        with pytest.raises(TypeError):
            await raises_type_error()

        # Should not retry TypeError
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_config_object(self):
        """Should accept RetryConfig object."""
        call_count = 0
        config = RetryConfig(max_attempts=2, base_delay=0.01)

        @retry_with_backoff(config)
        async def func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Retry me")
            return "done"

        result = await func()
        assert result == "done"
        assert call_count == 2


# =============================================================================
# run_with_semaphore Tests
# =============================================================================


class TestRunWithSemaphore:
    """Test run_with_semaphore utility."""

    @pytest.mark.asyncio
    async def test_executes_all_tasks(self):
        """All tasks should be executed."""
        results = []

        async def task(n):
            results.append(n)
            return n * 2

        tasks = [lambda n=n: task(n) for n in range(5)]
        outputs = await run_with_semaphore(tasks, max_concurrent=2)

        assert len(outputs) == 5
        assert set(outputs) == {0, 2, 4, 6, 8}

    @pytest.mark.asyncio
    async def test_respects_concurrency_limit(self):
        """Should not exceed max_concurrent tasks at once."""
        concurrent_count = 0
        max_observed = 0

        async def task():
            nonlocal concurrent_count, max_observed
            concurrent_count += 1
            max_observed = max(max_observed, concurrent_count)
            await asyncio.sleep(0.05)
            concurrent_count -= 1
            return True

        tasks = [lambda: task() for _ in range(10)]
        await run_with_semaphore(tasks, max_concurrent=3)

        assert max_observed <= 3

    @pytest.mark.asyncio
    async def test_preserves_order(self):
        """Results should be in the same order as tasks."""

        async def task(n):
            await asyncio.sleep(0.01 * (5 - n))  # Reverse completion order
            return n

        tasks = [lambda n=n: task(n) for n in range(5)]
        outputs = await run_with_semaphore(tasks, max_concurrent=5)

        assert outputs == [0, 1, 2, 3, 4]

    @pytest.mark.asyncio
    async def test_return_exceptions_true(self):
        """With return_exceptions=True, exceptions are returned not raised."""

        async def task(n):
            if n == 2:
                raise ValueError("Error at 2")
            return n

        tasks = [lambda n=n: task(n) for n in range(5)]
        outputs = await run_with_semaphore(tasks, max_concurrent=3, return_exceptions=True)

        assert outputs[0] == 0
        assert outputs[1] == 1
        assert isinstance(outputs[2], ValueError)
        assert outputs[3] == 3
        assert outputs[4] == 4

    @pytest.mark.asyncio
    async def test_empty_tasks_list(self):
        """Empty task list should return empty list."""
        outputs = await run_with_semaphore([], max_concurrent=3)
        assert outputs == []
