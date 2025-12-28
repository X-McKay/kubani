"""
Memory system for news monitor deduplication and trend tracking.

Uses:
- Redis for fast URL deduplication (O(1) lookup)
- mem0 with PostgreSQL + pgvector for semantic similarity and trend tracking
"""

import hashlib
import logging
import os
from datetime import datetime, timedelta
from typing import Any

import redis
from mem0 import Memory

from core_agents import get_mem0_config
from news_monitor.models import (
    ProcessedArticle,
    TrendingTopic,
    TrendStatus,
)

logger = logging.getLogger(__name__)

# Singleton instances
_memory_instance: Memory | None = None
_redis_client: redis.Redis | None = None

# Redis key prefix and TTL
REDIS_URL_SET_KEY = "news-monitor:seen-urls"
REDIS_URL_TTL_DAYS = 7  # URLs expire after 7 days


def get_redis() -> redis.Redis | None:
    """
    Get or create Redis client (singleton).

    Returns None if Redis is not configured or unavailable.
    """
    global _redis_client
    if _redis_client is None:
        redis_host = os.environ.get("REDIS_HOST", "redis.database.svc.cluster.local")
        redis_port = int(os.environ.get("REDIS_PORT", "6379"))
        redis_password = os.environ.get("REDIS_PASSWORD", "")

        try:
            _redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                password=redis_password if redis_password else None,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            # Test connection
            _redis_client.ping()
            logger.info(f"Connected to Redis at {redis_host}:{redis_port}")
        except redis.ConnectionError as e:
            logger.warning(f"Redis not available, falling back to mem0 only: {e}")
            _redis_client = None

    return _redis_client


def get_memory_config() -> dict[str, Any]:
    """
    Build mem0 configuration from environment variables.

    Uses core_agents.get_mem0_config() which handles vLLM embedder registration
    and provides standard configuration for vLLM-based embeddings.

    Environment variables:
        MEMORY_PG_HOST: PostgreSQL host
        MEMORY_PG_PORT: PostgreSQL port (default: 5432)
        MEMORY_PG_USER: PostgreSQL user
        MEMORY_PG_PASSWORD: PostgreSQL password
        MEMORY_PG_DATABASE: Database name
        VLLM_API_URL: vLLM API URL for LLM operations
        VLLM_MODEL: vLLM model name
        EMBEDDINGS_API_URL: Embeddings API URL
        EMBEDDINGS_MODEL: Embeddings model name
    """
    # Use core_agents utility which handles vLLM embedder registration
    # and provides standard configuration for vLLM-based embeddings
    return get_mem0_config(
        # Override defaults with news-monitor specific values
        pg_user=os.environ.get("MEMORY_PG_USER", "news_monitor"),
        pg_password=os.environ.get("MEMORY_PG_PASSWORD", "news-monitor-mem0-2024"),
        pg_database=os.environ.get("MEMORY_PG_DATABASE", "news_monitor_memory"),
    )


def get_memory() -> Memory:
    """Get or create the memory instance (singleton)."""
    global _memory_instance
    if _memory_instance is None:
        config = get_memory_config()
        logger.info("Initializing mem0 memory system for news-monitor")
        _memory_instance = Memory.from_config(config)
        logger.info("Memory system initialized successfully")
    return _memory_instance


def generate_content_hash(title: str, url: str) -> str:
    """
    Generate a hash for content deduplication.

    Combines title and URL to create a unique fingerprint.
    """
    normalized = f"{title.lower().strip()}:{url.lower().strip()}"
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def is_url_seen(url: str) -> bool:
    """
    Fast check if a URL has been seen before using Redis.

    O(1) lookup in Redis SET. Falls back to mem0 search if Redis unavailable.

    Args:
        url: The article URL to check

    Returns:
        True if URL has been seen before
    """
    # Try Redis first (fast O(1) lookup)
    redis_client = get_redis()
    if redis_client:
        try:
            return redis_client.sismember(REDIS_URL_SET_KEY, url)
        except redis.RedisError as e:
            logger.warning(f"Redis error checking URL: {e}")

    # Fallback to mem0 search (slower)
    try:
        memory = get_memory()
        results = memory.search(
            url,
            user_id="news-monitor-articles",
            limit=3,
        )

        for result in results:
            metadata = result.get("metadata", {})
            if metadata.get("url") == url:
                return True

        return False

    except Exception as e:
        logger.warning(f"Failed to check URL in memory: {e}")
        return False  # Err on the side of processing


def mark_url_seen(url: str) -> None:
    """
    Mark a URL as seen in Redis for fast future lookups.

    Args:
        url: The article URL to mark as seen
    """
    redis_client = get_redis()
    if redis_client:
        try:
            redis_client.sadd(REDIS_URL_SET_KEY, url)
            # Set expiry on the whole set periodically (refreshes TTL)
            redis_client.expire(REDIS_URL_SET_KEY, REDIS_URL_TTL_DAYS * 86400)
        except redis.RedisError as e:
            logger.warning(f"Redis error marking URL seen: {e}")


def is_duplicate_article(article: ProcessedArticle, similarity_threshold: float = 0.92) -> bool:
    """
    Check if an article is a duplicate of something we've already seen.

    Uses both exact URL matching and semantic similarity.

    Args:
        article: The article to check
        similarity_threshold: Cosine similarity threshold for semantic dedup

    Returns:
        True if this is a duplicate
    """
    try:
        memory = get_memory()

        # Search for similar articles
        query = f"{article.title} {article.ai_summary or article.original_summary}"
        results = memory.search(
            query,
            user_id="news-monitor-articles",
            limit=5,
        )

        for result in results:
            metadata = result.get("metadata", {})
            score = result.get("score", 0)

            # Exact URL match
            if metadata.get("url") == article.url:
                logger.debug(f"Duplicate found (exact URL): {article.url}")
                return True

            # High semantic similarity
            if score >= similarity_threshold:
                logger.debug(
                    f"Duplicate found (similarity {score:.2f}): {article.title} "
                    f"matches {metadata.get('title', 'unknown')}"
                )
                return True

        return False

    except Exception as e:
        logger.error(f"Failed to check for duplicates: {e}")
        return False  # Err on the side of including the article


def store_article(article: ProcessedArticle, digest_id: str | None = None) -> str | None:
    """
    Store an article in memory for future deduplication.

    Args:
        article: The processed article to store
        digest_id: Optional ID of the digest this was included in

    Returns:
        Memory ID if successful, None otherwise
    """
    try:
        memory = get_memory()

        content = f"""
Article: {article.title}
Source: {article.source}
Summary: {article.ai_summary or article.original_summary}
Category: {article.category.value}
Entities: {", ".join(article.entities)}
"""

        metadata = {
            "url": article.url,
            "content_hash": article.content_hash,
            "title": article.title,
            "source": article.source,
            "category": article.category.value,
            "importance_score": article.importance_score,
            "published_at": article.published_at.isoformat() if article.published_at else None,
            "processed_at": article.processed_at.isoformat(),
            "included_in_digest": digest_id,
            "type": "article",
        }

        result = memory.add(
            content,
            user_id="news-monitor-articles",
            metadata=metadata,
        )

        # Also mark URL in Redis for fast future lookups
        mark_url_seen(article.url)

        memory_id = result.get("id") if isinstance(result, dict) else None
        logger.debug(f"Stored article in memory: {article.title[:50]}...")
        return memory_id

    except Exception as e:
        logger.error(f"Failed to store article: {e}")
        return None


def store_theme(topic: TrendingTopic) -> str | None:
    """
    Store or update a theme in memory for trend tracking.

    Args:
        topic: The trending topic to store

    Returns:
        Memory ID if successful, None otherwise
    """
    try:
        memory = get_memory()

        content = f"""
Trending Topic: {topic.topic}
Status: {topic.status.value}
Article Count: {topic.article_count}
Sources: {", ".join(topic.sources)}
Momentum: {topic.momentum:.2f}
First Seen: {topic.first_seen.isoformat()}
Last Seen: {topic.last_seen.isoformat()}
"""

        metadata = {
            "topic": topic.topic,
            "status": topic.status.value,
            "article_count": topic.article_count,
            "momentum": topic.momentum,
            "first_seen": topic.first_seen.isoformat(),
            "last_seen": topic.last_seen.isoformat(),
            "type": "theme",
        }

        result = memory.add(
            content,
            user_id="news-monitor-themes",
            metadata=metadata,
        )

        memory_id = result.get("id") if isinstance(result, dict) else None
        logger.debug(f"Stored theme in memory: {topic.topic}")
        return memory_id

    except Exception as e:
        logger.error(f"Failed to store theme: {e}")
        return None


def get_recent_themes(days: int = 7) -> list[dict[str, Any]]:
    """
    Get themes from the past N days for trend analysis.

    Args:
        days: Number of days to look back

    Returns:
        List of theme records with their metadata
    """
    try:
        memory = get_memory()

        # Search for recent themes
        cutoff = datetime.utcnow() - timedelta(days=days)
        query = "trending topics themes AI news"

        results = memory.search(
            query,
            user_id="news-monitor-themes",
            limit=50,
        )

        themes = []
        for result in results:
            metadata = result.get("metadata", {})
            if metadata.get("type") != "theme":
                continue

            last_seen = metadata.get("last_seen")
            if last_seen:
                last_seen_dt = datetime.fromisoformat(last_seen)
                if last_seen_dt >= cutoff:
                    themes.append(
                        {
                            "content": result.get("memory", ""),
                            "metadata": metadata,
                        }
                    )

        return themes

    except Exception as e:
        logger.error(f"Failed to get recent themes: {e}")
        return []


def calculate_trend_status(
    topic: str,
    current_count: int,
    history: list[dict[str, Any]],
) -> TrendStatus:
    """
    Calculate the trend status for a topic based on history.

    Args:
        topic: The topic name
        current_count: Current article count for this digest
        history: Historical theme records from memory

    Returns:
        The appropriate TrendStatus
    """
    # Find historical data for this topic
    topic_history = [h for h in history if h.get("metadata", {}).get("topic") == topic]

    if not topic_history:
        # Never seen before
        if current_count >= 3:
            return TrendStatus.HOT  # Multiple sources = hot
        return TrendStatus.BREAKING

    # Calculate momentum (change in coverage)
    historical_counts = [h.get("metadata", {}).get("article_count", 0) for h in topic_history]
    avg_historical = sum(historical_counts) / len(historical_counts) if historical_counts else 0

    if current_count > avg_historical * 1.5:
        return TrendStatus.RISING
    elif current_count < avg_historical * 0.5:
        return TrendStatus.FADING
    else:
        return TrendStatus.ESTABLISHED


def get_article_count_for_topic(topic: str, days: int = 7) -> int:
    """
    Count how many articles we've seen on a topic in the past N days.

    Args:
        topic: The topic to search for
        days: Number of days to look back

    Returns:
        Count of related articles
    """
    try:
        memory = get_memory()

        results = memory.search(
            topic,
            user_id="news-monitor-articles",
            limit=100,
        )

        cutoff = datetime.utcnow() - timedelta(days=days)
        count = 0

        for result in results:
            metadata = result.get("metadata", {})
            processed_at = metadata.get("processed_at")
            if processed_at:
                processed_dt = datetime.fromisoformat(processed_at)
                if processed_dt >= cutoff:
                    count += 1

        return count

    except Exception as e:
        logger.error(f"Failed to count articles for topic: {e}")
        return 0


def store_digest_record(
    digest_id: str,
    article_urls: list[str],
    themes: list[str],
    discord_message_id: str | None = None,
) -> str | None:
    """
    Store a record of a published digest.

    Args:
        digest_id: Unique identifier for the digest
        article_urls: URLs of articles included
        themes: Themes covered in the digest
        discord_message_id: Discord message ID if published

    Returns:
        Memory ID if successful, None otherwise
    """
    try:
        memory = get_memory()

        content = f"""
News Digest: {digest_id}
Published: {datetime.utcnow().isoformat()}
Articles: {len(article_urls)}
Themes: {", ".join(themes)}
"""

        metadata = {
            "digest_id": digest_id,
            "published_at": datetime.utcnow().isoformat(),
            "article_count": len(article_urls),
            "article_urls": article_urls[:20],  # Limit stored URLs
            "themes": themes,
            "discord_message_id": discord_message_id,
            "type": "digest",
        }

        result = memory.add(
            content,
            user_id="news-monitor-digests",
            metadata=metadata,
        )

        memory_id = result.get("id") if isinstance(result, dict) else None
        logger.info(f"Stored digest record: {digest_id}")
        return memory_id

    except Exception as e:
        logger.error(f"Failed to store digest record: {e}")
        return None
