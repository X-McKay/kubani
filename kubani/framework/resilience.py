"""
Resilience primitives for Kubani agents.

Provides core utilities for building resilient agents:
- DedupService: Redis-based deduplication with TTL
- RateLimiter: Token bucket rate limiting for external APIs
- retry_with_backoff: Async retry decorator with exponential backoff
- run_with_semaphore: Helper for parallel execution with concurrency limit

All features degrade gracefully if Redis is unavailable.
"""

import asyncio
import hashlib
import logging
import os
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, ParamSpec, TypeVar

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


# =============================================================================
# Deduplication Service
# =============================================================================


@dataclass
class DedupConfig:
    """Configuration for deduplication service."""

    ttl_seconds: int = 7 * 24 * 3600  # 7 days default
    key_prefix: str = "dedup"
    enabled: bool = True


class DedupService:
    """
    Redis-based deduplication service with TTL.

    Tracks seen items by key with automatic expiration. Falls back to
    in-memory tracking if Redis is unavailable.

    Usage:
        dedup = DedupService(namespace="feed_collector")
        await dedup.initialize()

        if not await dedup.is_seen(article.url):
            await dedup.mark_seen(article.url)
            # Process article...
    """

    def __init__(
        self,
        namespace: str,
        config: DedupConfig | None = None,
        host: str | None = None,
        port: int | None = None,
        password: str | None = None,
        db: int = 0,
    ):
        self.namespace = namespace
        self.config = config or DedupConfig()
        self.host = host or os.getenv("REDIS_HOST", "localhost")
        self.port = port or int(os.getenv("REDIS_PORT", "6379"))
        self.password = password or os.getenv("REDIS_PASSWORD") or None
        self.db = db

        self._client: Any = None
        self._initialized = False
        self._fallback_cache: set[str] = set()

    def _make_key(self, item_id: str) -> str:
        """Generate Redis key for an item."""
        return f"{self.config.key_prefix}:{self.namespace}:{item_id}"

    async def initialize(self) -> bool:
        """
        Initialize Redis connection.

        Returns:
            True if Redis is available, False if falling back to in-memory.
        """
        if not self.config.enabled:
            logger.info(f"DedupService[{self.namespace}]: Disabled, using in-memory fallback")
            return False

        try:
            import redis.asyncio as redis

            self._client = redis.Redis(
                host=self.host,
                port=self.port,
                password=self.password,
                db=self.db,
                decode_responses=True,
            )
            await self._client.ping()
            self._initialized = True
            logger.info(
                f"DedupService[{self.namespace}]: Connected to Redis at {self.host}:{self.port}"
            )
            return True

        except ImportError:
            logger.warning(
                f"DedupService[{self.namespace}]: redis package not installed, using in-memory fallback"
            )
            return False
        except Exception as e:
            logger.warning(
                f"DedupService[{self.namespace}]: Redis connection failed ({e}), using in-memory fallback"
            )
            return False

    async def is_seen(self, item_id: str) -> bool:
        """
        Check if an item has been seen.

        Args:
            item_id: Unique identifier for the item (URL, hash, etc.)

        Returns:
            True if the item has been seen within the TTL window.
        """
        if self._initialized and self._client:
            try:
                key = self._make_key(item_id)
                return await self._client.exists(key) > 0
            except Exception as e:
                logger.warning(f"DedupService[{self.namespace}]: Redis error in is_seen: {e}")
                # Fall through to in-memory check

        return item_id in self._fallback_cache

    async def mark_seen(self, item_id: str, ttl_seconds: int | None = None) -> None:
        """
        Mark an item as seen.

        Args:
            item_id: Unique identifier for the item.
            ttl_seconds: Optional override for TTL (defaults to config).
        """
        ttl = ttl_seconds or self.config.ttl_seconds

        if self._initialized and self._client:
            try:
                key = self._make_key(item_id)
                await self._client.setex(key, ttl, "1")
                return
            except Exception as e:
                logger.warning(f"DedupService[{self.namespace}]: Redis error in mark_seen: {e}")
                # Fall through to in-memory

        self._fallback_cache.add(item_id)

    async def mark_seen_batch(self, item_ids: list[str], ttl_seconds: int | None = None) -> None:
        """
        Mark multiple items as seen in a single operation.

        Args:
            item_ids: List of unique identifiers.
            ttl_seconds: Optional override for TTL.
        """
        if not item_ids:
            return

        ttl = ttl_seconds or self.config.ttl_seconds

        if self._initialized and self._client:
            try:
                pipe = self._client.pipeline()
                for item_id in item_ids:
                    key = self._make_key(item_id)
                    pipe.setex(key, ttl, "1")
                await pipe.execute()
                return
            except Exception as e:
                logger.warning(
                    f"DedupService[{self.namespace}]: Redis error in mark_seen_batch: {e}"
                )

        # Fallback to in-memory
        self._fallback_cache.update(item_ids)

    async def filter_unseen(self, item_ids: list[str]) -> list[str]:
        """
        Filter a list to only unseen items.

        Args:
            item_ids: List of identifiers to check.

        Returns:
            List of identifiers that have not been seen.
        """
        if not item_ids:
            return []

        if self._initialized and self._client:
            try:
                pipe = self._client.pipeline()
                for item_id in item_ids:
                    key = self._make_key(item_id)
                    pipe.exists(key)
                results = await pipe.execute()
                return [item_id for item_id, exists in zip(item_ids, results, strict=False) if not exists]
            except Exception as e:
                logger.warning(f"DedupService[{self.namespace}]: Redis error in filter_unseen: {e}")

        # Fallback to in-memory
        return [item_id for item_id in item_ids if item_id not in self._fallback_cache]

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._client:
            await self._client.close()
            self._initialized = False


def content_hash(content: str) -> str:
    """Generate a hash from content for deduplication."""
    return hashlib.sha256(content.encode()).hexdigest()[:16]


# =============================================================================
# Rate Limiter
# =============================================================================


@dataclass
class RateLimitConfig:
    """Configuration for rate limiter."""

    requests_per_second: float | None = None
    requests_per_minute: float | None = None
    requests_per_hour: float | None = None
    burst_size: int = 1  # Allow this many requests immediately


class RateLimiter:
    """
    Token bucket rate limiter for external API calls.

    Supports multiple rate specifications (per second, minute, hour).
    Uses the most restrictive limit when multiple are specified.

    Usage:
        limiter = RateLimiter(RateLimitConfig(requests_per_hour=60))

        async with limiter:
            await call_api()

        # Or without context manager:
        await limiter.acquire()
        await call_api()
    """

    def __init__(self, config: RateLimitConfig):
        self.config = config
        self._tokens: float = config.burst_size
        self._last_update: float = time.monotonic()
        self._lock = asyncio.Lock()

        # Calculate tokens per second from the most restrictive limit
        self._tokens_per_second = self._calculate_rate()

    def _calculate_rate(self) -> float:
        """Calculate effective tokens per second from config."""
        rates = []

        if self.config.requests_per_second:
            rates.append(self.config.requests_per_second)
        if self.config.requests_per_minute:
            rates.append(self.config.requests_per_minute / 60.0)
        if self.config.requests_per_hour:
            rates.append(self.config.requests_per_hour / 3600.0)

        if not rates:
            return float("inf")  # No limit

        return min(rates)

    async def acquire(self, tokens: int = 1) -> None:
        """
        Acquire tokens, waiting if necessary.

        Args:
            tokens: Number of tokens to acquire (default 1).
        """
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self._last_update
                self._last_update = now

                # Add tokens based on elapsed time
                self._tokens = min(
                    self.config.burst_size,
                    self._tokens + elapsed * self._tokens_per_second,
                )

                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return

                # Calculate wait time
                needed = tokens - self._tokens
                wait_time = needed / self._tokens_per_second

                # Release lock while waiting
                self._lock.release()
                try:
                    await asyncio.sleep(wait_time)
                finally:
                    await self._lock.acquire()

    async def __aenter__(self) -> "RateLimiter":
        await self.acquire()
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass


# Pre-configured rate limiters for common APIs
GITHUB_RATE_LIMIT = RateLimitConfig(requests_per_hour=60, burst_size=5)
ARXIV_RATE_LIMIT = RateLimitConfig(requests_per_second=1 / 3, burst_size=1)  # 3 second delay


# =============================================================================
# Retry with Backoff
# =============================================================================


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    retryable_exceptions: tuple[type[Exception], ...] = field(default_factory=lambda: (Exception,))


def retry_with_backoff(
    config: RetryConfig | None = None,
    *,
    max_attempts: int | None = None,
    base_delay: float | None = None,
    retryable_exceptions: tuple[type[Exception], ...] | None = None,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """
    Decorator for async functions with exponential backoff retry.

    Can be used with a config object or individual parameters:

        @retry_with_backoff(max_attempts=3, base_delay=1.0)
        async def fetch_data():
            ...

        @retry_with_backoff(RetryConfig(max_attempts=5))
        async def fetch_data():
            ...
    """
    if config is None:
        config = RetryConfig()

    # Override config with explicit parameters
    if max_attempts is not None:
        config = RetryConfig(
            max_attempts=max_attempts,
            base_delay=config.base_delay,
            max_delay=config.max_delay,
            exponential_base=config.exponential_base,
            jitter=config.jitter,
            retryable_exceptions=config.retryable_exceptions,
        )
    if base_delay is not None:
        config = RetryConfig(
            max_attempts=config.max_attempts,
            base_delay=base_delay,
            max_delay=config.max_delay,
            exponential_base=config.exponential_base,
            jitter=config.jitter,
            retryable_exceptions=config.retryable_exceptions,
        )
    if retryable_exceptions is not None:
        config = RetryConfig(
            max_attempts=config.max_attempts,
            base_delay=config.base_delay,
            max_delay=config.max_delay,
            exponential_base=config.exponential_base,
            jitter=config.jitter,
            retryable_exceptions=retryable_exceptions,
        )

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_exception: Exception | None = None

            for attempt in range(config.max_attempts):
                try:
                    return await func(*args, **kwargs)
                except config.retryable_exceptions as e:
                    last_exception = e

                    if attempt == config.max_attempts - 1:
                        logger.warning(
                            f"Retry exhausted for {func.__name__} after {config.max_attempts} attempts: {e}"
                        )
                        raise

                    # Calculate delay with exponential backoff
                    delay = min(
                        config.base_delay * (config.exponential_base**attempt),
                        config.max_delay,
                    )

                    # Add jitter to prevent thundering herd
                    if config.jitter:
                        delay *= 0.5 + random.random()

                    logger.debug(
                        f"Retry {attempt + 1}/{config.max_attempts} for {func.__name__} "
                        f"after {delay:.2f}s: {e}"
                    )
                    await asyncio.sleep(delay)

            # Should not reach here, but satisfy type checker
            if last_exception:
                raise last_exception
            raise RuntimeError("Retry logic error")

        return wrapper

    return decorator


# =============================================================================
# Parallel Execution Helper
# =============================================================================


async def run_with_semaphore(
    tasks: list[Callable[[], Awaitable[T]]],
    max_concurrent: int,
    *,
    return_exceptions: bool = False,
) -> list[T | BaseException]:
    """
    Run async callables with limited concurrency.

    Args:
        tasks: List of async callables (zero-argument functions returning awaitables).
        max_concurrent: Maximum number of concurrent tasks.
        return_exceptions: If True, exceptions are returned instead of raised.

    Returns:
        List of results in the same order as tasks.

    Usage:
        async def analyze(article):
            return await llm.analyze(article)

        results = await run_with_semaphore(
            [lambda a=a: analyze(a) for a in articles],
            max_concurrent=4,
        )
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    results: list[T | BaseException] = []

    async def run_task(
        index: int, task: Callable[[], Awaitable[T]]
    ) -> tuple[int, T | BaseException]:
        async with semaphore:
            try:
                result = await task()
                return (index, result)
            except Exception as e:
                if return_exceptions:
                    return (index, e)
                raise

    # Create tasks with indices to preserve order
    coros = [run_task(i, task) for i, task in enumerate(tasks)]

    # Run all tasks
    completed = await asyncio.gather(*coros, return_exceptions=return_exceptions)

    # Sort by index and extract results
    if return_exceptions:
        # Handle case where gather itself caught exceptions
        sorted_results: list[tuple[int, T | BaseException]] = []
        for item in completed:
            if isinstance(item, BaseException):
                # This happens if return_exceptions=True and the task raised
                # We can't know the index, so this is a gather-level error
                raise item
            sorted_results.append(item)
        sorted_results.sort(key=lambda x: x[0])
        results = [r[1] for r in sorted_results]
    else:
        sorted_results = sorted(completed, key=lambda x: x[0])  # type: ignore
        results = [r[1] for r in sorted_results]

    return results


# =============================================================================
# Convenience Functions
# =============================================================================


async def create_dedup_service(
    namespace: str,
    ttl_days: int = 7,
    enabled: bool = True,
) -> DedupService:
    """
    Create and initialize a deduplication service.

    Args:
        namespace: Unique namespace for this service (e.g., "feed_collector").
        ttl_days: How long to remember seen items.
        enabled: Whether to enable Redis (False = in-memory only).

    Returns:
        Initialized DedupService.
    """
    config = DedupConfig(
        ttl_seconds=ttl_days * 24 * 3600,
        enabled=enabled,
    )
    service = DedupService(namespace=namespace, config=config)
    await service.initialize()
    return service
