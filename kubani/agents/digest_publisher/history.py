"""
Digest History Tracker - Tracks featured content to avoid repetition.

Prevents the same papers, repos, or articles from being featured
repeatedly in consecutive digests.

Usage:
    tracker = DigestHistoryTracker(namespace="executive_digest")
    await tracker.initialize()

    # Check what's already been featured
    unseen_papers = await tracker.filter_unfeatured(
        paper_ids,
        content_type="paper"
    )

    # After publishing, mark as featured
    await tracker.mark_featured(featured_paper_ids, content_type="paper")
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class DigestHistoryTracker:
    """
    Redis-based history tracking for digest content.

    Tracks what papers, repos, and articles have been featured
    in recent digests to avoid repetition.

    TTLs are configured based on content type:
    - Papers: 30 days (research has longer relevance)
    - Repos: 14 days (tools can be re-featured after updates)
    - Articles: 7 days (news cycles faster)
    """

    # Default TTLs by content type
    DEFAULT_TTLS = {
        "paper": 30 * 24 * 3600,  # 30 days
        "repo": 14 * 24 * 3600,  # 14 days
        "article": 7 * 24 * 3600,  # 7 days
        "company": 7 * 24 * 3600,  # 7 days
    }

    def __init__(
        self,
        namespace: str = "digest_history",
        host: str | None = None,
        port: int | None = None,
        password: str | None = None,
        db: int = 0,
    ):
        self.namespace = namespace
        self.host = host or os.getenv("REDIS_HOST", "localhost")
        self.port = port or int(os.getenv("REDIS_PORT", "6379"))
        self.password = password or os.getenv("REDIS_PASSWORD") or None
        self.db = db

        self._client: Any = None
        self._initialized = False
        self._fallback_cache: dict[str, set[str]] = {
            "paper": set(),
            "repo": set(),
            "article": set(),
            "company": set(),
        }

    def _make_key(self, content_type: str, content_id: str) -> str:
        """Generate Redis key for content."""
        return f"{self.namespace}:{content_type}:{content_id}"

    async def initialize(self) -> bool:
        """
        Initialize Redis connection.

        Returns:
            True if Redis is available, False if falling back to in-memory.
        """
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
                f"DigestHistoryTracker[{self.namespace}]: Connected to Redis at {self.host}:{self.port}"
            )
            return True

        except ImportError:
            logger.warning(
                f"DigestHistoryTracker[{self.namespace}]: redis package not installed, "
                "using in-memory fallback"
            )
            return False
        except Exception as e:
            logger.warning(
                f"DigestHistoryTracker[{self.namespace}]: Redis connection failed ({e}), "
                "using in-memory fallback"
            )
            return False

    async def is_featured(self, content_id: str, content_type: str = "paper") -> bool:
        """
        Check if content has been featured recently.

        Args:
            content_id: Unique identifier (arxiv_id, repo full_name, article url)
            content_type: Type of content ("paper", "repo", "article", "company")

        Returns:
            True if content was featured within its TTL window.
        """
        if self._initialized and self._client:
            try:
                key = self._make_key(content_type, content_id)
                return await self._client.exists(key) > 0
            except Exception as e:
                logger.warning(f"DigestHistoryTracker: Redis error in is_featured: {e}")

        return content_id in self._fallback_cache.get(content_type, set())

    async def mark_featured(
        self,
        content_ids: list[str],
        content_type: str = "paper",
        ttl_seconds: int | None = None,
    ) -> None:
        """
        Mark content as featured.

        Args:
            content_ids: List of identifiers to mark.
            content_type: Type of content.
            ttl_seconds: Optional TTL override (defaults to type-specific TTL).
        """
        if not content_ids:
            return

        ttl = ttl_seconds or self.DEFAULT_TTLS.get(content_type, 7 * 24 * 3600)

        if self._initialized and self._client:
            try:
                pipe = self._client.pipeline()
                for content_id in content_ids:
                    key = self._make_key(content_type, content_id)
                    pipe.setex(key, ttl, "1")
                await pipe.execute()
                logger.debug(
                    f"DigestHistoryTracker: Marked {len(content_ids)} {content_type}s as featured"
                )
                return
            except Exception as e:
                logger.warning(f"DigestHistoryTracker: Redis error in mark_featured: {e}")

        # Fallback to in-memory
        if content_type not in self._fallback_cache:
            self._fallback_cache[content_type] = set()
        self._fallback_cache[content_type].update(content_ids)

    async def filter_unfeatured(
        self,
        content_ids: list[str],
        content_type: str = "paper",
    ) -> list[str]:
        """
        Filter list to only unfeatured content.

        Args:
            content_ids: List of identifiers to check.
            content_type: Type of content.

        Returns:
            List of identifiers that have not been featured recently.
        """
        if not content_ids:
            return []

        if self._initialized and self._client:
            try:
                pipe = self._client.pipeline()
                for content_id in content_ids:
                    key = self._make_key(content_type, content_id)
                    pipe.exists(key)
                results = await pipe.execute()
                unfeatured = [
                    cid for cid, exists in zip(content_ids, results, strict=False) if not exists
                ]
                logger.debug(
                    f"DigestHistoryTracker: {len(unfeatured)}/{len(content_ids)} "
                    f"{content_type}s are unfeatured"
                )
                return unfeatured
            except Exception as e:
                logger.warning(f"DigestHistoryTracker: Redis error in filter_unfeatured: {e}")

        # Fallback
        cache = self._fallback_cache.get(content_type, set())
        return [cid for cid in content_ids if cid not in cache]

    async def get_featured_count(self, content_type: str = "paper") -> int:
        """
        Get count of recently featured content.

        Args:
            content_type: Type of content.

        Returns:
            Number of items currently tracked as featured.
        """
        if self._initialized and self._client:
            try:
                pattern = self._make_key(content_type, "*")
                count = 0
                async for _ in self._client.scan_iter(match=pattern, count=100):
                    count += 1
                return count
            except Exception as e:
                logger.warning(f"DigestHistoryTracker: Redis error in get_featured_count: {e}")

        return len(self._fallback_cache.get(content_type, set()))

    async def clear_history(self, content_type: str | None = None) -> int:
        """
        Clear featured history.

        Args:
            content_type: Type to clear (None = all types).

        Returns:
            Number of items cleared.
        """
        types_to_clear = [content_type] if content_type else list(self.DEFAULT_TTLS.keys())
        cleared = 0

        if self._initialized and self._client:
            try:
                for ctype in types_to_clear:
                    pattern = self._make_key(ctype, "*")
                    keys = []
                    async for key in self._client.scan_iter(match=pattern, count=100):
                        keys.append(key)

                    if keys:
                        await self._client.delete(*keys)
                        cleared += len(keys)

                logger.info(f"DigestHistoryTracker: Cleared {cleared} items")
                return cleared
            except Exception as e:
                logger.warning(f"DigestHistoryTracker: Redis error in clear_history: {e}")

        # Fallback
        for ctype in types_to_clear:
            if ctype in self._fallback_cache:
                cleared += len(self._fallback_cache[ctype])
                self._fallback_cache[ctype] = set()

        return cleared

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._client:
            await self._client.close()
            self._initialized = False


async def create_history_tracker(
    namespace: str = "digest_history",
) -> DigestHistoryTracker:
    """
    Create and initialize a history tracker.

    Args:
        namespace: Unique namespace for this tracker.

    Returns:
        Initialized DigestHistoryTracker.
    """
    tracker = DigestHistoryTracker(namespace=namespace)
    await tracker.initialize()
    return tracker
