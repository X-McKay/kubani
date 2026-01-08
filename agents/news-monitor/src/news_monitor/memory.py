"""
Memory system for news monitor deduplication and trend tracking.

Uses:
- Redis for fast URL deduplication (O(1) lookup)
- mem0 with Qdrant + Neo4j for semantic similarity and graph-based trend tracking
"""

import hashlib
import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import redis
from mem0 import Memory

from news_monitor.memory_config import get_news_graph_mem0_config
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
REDIS_BREAKING_ALERTS_KEY = "news-monitor:breaking-alerts-sent"
REDIS_URL_TTL_DAYS = 7  # URLs expire after 7 days
REDIS_BREAKING_ALERT_TTL_HOURS = 48  # Breaking alerts expire after 48 hours


def _extract_entities_from_payload(payload: dict[str, Any]) -> list[str]:
    """
    Extract entities from a Qdrant payload.

    Supports two storage formats:
    1. New format: entities stored as comma-separated string in "entities" field
    2. Legacy format: entities embedded in "data" text as "Entities: X, Y, Z"

    Args:
        payload: Qdrant point payload

    Returns:
        List of entity strings (deduplicated, stripped)
    """
    entities: list[str] = []

    # Try new format first (comma-separated string in metadata)
    entities_str = payload.get("entities", "")
    if entities_str and isinstance(entities_str, str):
        entities = [e.strip() for e in entities_str.split(",") if e.strip()]

    # Fall back to legacy format (parse from "data" text field)
    if not entities:
        data = payload.get("data", "")
        if isinstance(data, str) and "Entities:" in data:
            try:
                # Extract the part after "Entities:" until newline
                entities_part = data.split("Entities:")[-1].split("\n")[0]
                entities = [e.strip() for e in entities_part.split(",") if e.strip()]
            except (IndexError, AttributeError):
                pass

    # Filter out very short entities (likely noise)
    entities = [e for e in entities if len(e) >= 2]

    return entities


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
    Build mem0 configuration with Qdrant + Neo4j graph memory.

    Uses core_agents.get_news_graph_mem0_config() which provides:
    - Qdrant for high-performance vector similarity search
    - Neo4j for graph-based entity/relationship tracking
    - vLLM for embeddings and LLM operations

    Environment variables:
        QDRANT_HOST: Qdrant host
        QDRANT_PORT: Qdrant port (default: 6333)
        QDRANT_COLLECTION: Collection name (default: news-monitor)
        NEO4J_URL: Neo4j bolt URL
        NEO4J_USERNAME: Neo4j username
        NEO4J_PASSWORD: Neo4j password
        VLLM_API_URL: vLLM API URL for LLM operations
        VLLM_MODEL: vLLM model name
        EMBEDDINGS_API_URL: Embeddings API URL
        EMBEDDINGS_MODEL: Embeddings model name
    """
    return get_news_graph_mem0_config(
        collection_name=os.environ.get("QDRANT_COLLECTION", "news-monitor"),
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


def _extract_search_results(results: Any) -> list[dict[str, Any]]:
    """
    Safely extract search results from mem0 response.

    mem0's search() can return different formats depending on version:
    - List of dicts: [{"memory": ..., "metadata": ..., "score": ...}, ...]
    - Wrapped response: {"results": [...]}
    - Other unexpected formats

    Args:
        results: Raw response from memory.search()

    Returns:
        List of result dicts, each with memory/metadata/score keys
    """
    if results is None:
        return []

    # If already a list, process each item
    if isinstance(results, list):
        extracted = []
        for item in results:
            if isinstance(item, dict):
                extracted.append(item)
            elif isinstance(item, str):
                # Some versions return just the memory text
                extracted.append({"memory": item, "metadata": {}, "score": 0})
            else:
                logger.debug(f"Unexpected result item type: {type(item)}")
        return extracted

    # If wrapped in a results key
    if isinstance(results, dict):
        if "results" in results:
            return _extract_search_results(results["results"])
        # Single result dict
        return [results]

    logger.warning(f"Unexpected search results type: {type(results)}")
    return []


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
        raw_results = memory.search(
            url,
            user_id="news-monitor-articles",
            limit=3,
        )

        for result in _extract_search_results(raw_results):
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


def has_breaking_alert_been_sent(url: str) -> bool | None:
    """
    Check if a breaking news alert has already been sent for this URL.

    Returns:
        True if alert was already sent
        False if alert has NOT been sent
        None if we cannot determine (Redis unavailable) - caller should fail-closed

    This function is designed for fail-closed behavior: if we can't verify
    whether an alert was sent, return None so the caller can skip the alert
    rather than risk duplicates.

    NOTE: For atomic check-and-claim, use try_claim_breaking_alert() instead.
    """
    redis_client = get_redis()
    if not redis_client:
        logger.warning("Redis unavailable - cannot verify breaking alert status")
        return None  # Signal that we cannot determine

    try:
        return redis_client.sismember(REDIS_BREAKING_ALERTS_KEY, url)
    except redis.RedisError as e:
        logger.warning(f"Redis error checking breaking alert: {e}")
        return None  # Signal that we cannot determine


def try_claim_breaking_alert(url: str) -> bool | None:
    """
    Atomically try to claim the right to send a breaking alert for this URL.

    Uses Redis SADD which is atomic - only one caller can successfully add
    a new element. This prevents race conditions where multiple workers
    check simultaneously and all see "not sent".

    Returns:
        True if we successfully claimed the alert (should publish)
        False if alert was already claimed by another worker (skip)
        None if we cannot determine (Redis unavailable) - caller should fail-closed

    This function is designed for fail-closed behavior: if we can't verify
    whether an alert was sent, return None so the caller can skip the alert
    rather than risk duplicates.
    """
    redis_client = get_redis()
    if not redis_client:
        logger.warning("Redis unavailable - cannot claim breaking alert")
        return None  # Signal that we cannot determine

    try:
        # SADD returns 1 if element was added (new), 0 if already existed
        # This is atomic - only one caller can "win" the race
        result = redis_client.sadd(REDIS_BREAKING_ALERTS_KEY, url)

        if result == 1:
            # We claimed it - set expiry on the set
            # (same article republished days later is worth alerting again)
            redis_client.expire(REDIS_BREAKING_ALERTS_KEY, REDIS_BREAKING_ALERT_TTL_HOURS * 3600)
            logger.debug(f"Claimed breaking alert for: {url}")
            return True
        else:
            logger.debug(f"Breaking alert already claimed for: {url}")
            return False

    except redis.RedisError as e:
        logger.warning(f"Redis error claiming breaking alert: {e}")
        return None  # Signal that we cannot determine


def mark_breaking_alert_sent(url: str) -> bool:
    """
    Mark that a breaking news alert has been sent for this URL.

    DEPRECATED: Use try_claim_breaking_alert() for atomic check-and-claim.
    This function is kept for backwards compatibility but has a race condition
    when used with has_breaking_alert_been_sent().

    Args:
        url: The article URL

    Returns:
        True if successfully marked, False otherwise
    """
    redis_client = get_redis()
    if not redis_client:
        logger.warning("Redis unavailable - cannot mark breaking alert as sent")
        return False

    try:
        redis_client.sadd(REDIS_BREAKING_ALERTS_KEY, url)
        # Set expiry - breaking alerts should expire after 48 hours
        # (same article republished days later is worth alerting again)
        redis_client.expire(REDIS_BREAKING_ALERTS_KEY, REDIS_BREAKING_ALERT_TTL_HOURS * 3600)
        logger.debug(f"Marked breaking alert sent for: {url}")
        return True
    except redis.RedisError as e:
        logger.warning(f"Redis error marking breaking alert sent: {e}")
        return False


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
        raw_results = memory.search(
            query,
            user_id="news-monitor-articles",
            limit=5,
        )

        for result in _extract_search_results(raw_results):
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

    Uses infer=False to skip mem0's built-in fact extraction, which can fail
    with vLLM/Qwen models. The graph store still extracts entities and
    relationships for trend tracking.

    Args:
        article: The processed article to store
        digest_id: Optional ID of the digest this was included in

    Returns:
        Memory ID if successful, None otherwise
    """
    try:
        memory = get_memory()

        # Build content for semantic search and graph extraction
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
            # Store entities as comma-separated string for Qdrant compatibility
            # (Qdrant payload fields must be scalar or array of scalars)
            "entities": ",".join(article.entities) if article.entities else "",
        }

        # Use infer=False to skip mem0's built-in fact extraction which fails
        # with vLLM/Qwen models (returns {} instead of {"facts": []}).
        # Graph store entity/relationship extraction still runs via separate LLM call.
        #
        # IMPORTANT: When infer=False, mem0 expects messages to be a list of dicts
        # with "role" and "content" keys, not a plain string.
        messages = [{"role": "user", "content": content}]
        result = memory.add(
            messages,
            user_id="news-monitor-articles",
            metadata=metadata,
            infer=False,
        )

        # Also mark URL in Redis for fast future lookups
        mark_url_seen(article.url)

        # Extract memory ID from result
        # With infer=False, mem0 returns {"results": [{"id": "...", ...}], "relations": ...}
        memory_id = None
        if isinstance(result, dict):
            results = result.get("results", [])
            if results and isinstance(results, list) and len(results) > 0:
                memory_id = results[0].get("id")

        logger.debug(f"Stored article in memory: {article.title[:50]}... (id={memory_id})")
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

        # Use infer=False for consistent behavior with store_article
        # IMPORTANT: When infer=False, mem0 expects messages as list of dicts
        messages = [{"role": "user", "content": content}]
        result = memory.add(
            messages,
            user_id="news-monitor-themes",
            metadata=metadata,
            infer=False,
        )

        # Extract memory ID from result
        # With infer=False, mem0 returns {"results": [{"id": "...", ...}], "relations": ...}
        memory_id = None
        if isinstance(result, dict):
            results = result.get("results", [])
            if results and isinstance(results, list) and len(results) > 0:
                memory_id = results[0].get("id")

        logger.debug(f"Stored theme in memory: {topic.topic} (id={memory_id})")
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

        raw_results = memory.search(
            query,
            user_id="news-monitor-themes",
            limit=50,
        )

        themes = []
        for result in _extract_search_results(raw_results):
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

        raw_results = memory.search(
            topic,
            user_id="news-monitor-articles",
            limit=100,
        )

        cutoff = datetime.utcnow() - timedelta(days=days)
        count = 0

        for result in _extract_search_results(raw_results):
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

        # Use infer=False for consistent behavior with store_article
        # IMPORTANT: When infer=False, mem0 expects messages as list of dicts
        messages = [{"role": "user", "content": content}]
        result = memory.add(
            messages,
            user_id="news-monitor-digests",
            metadata=metadata,
            infer=False,
        )

        # Extract memory ID from result
        # With infer=False, mem0 returns {"results": [{"id": "...", ...}], "relations": ...}
        memory_id = None
        if isinstance(result, dict):
            results = result.get("results", [])
            if results and isinstance(results, list) and len(results) > 0:
                memory_id = results[0].get("id")

        logger.info(f"Stored digest record: {digest_id} (id={memory_id})")
        return memory_id

    except Exception as e:
        logger.error(f"Failed to store digest record: {e}")
        return None


def query_articles_since(
    cutoff: datetime,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """
    Query articles from Qdrant that were processed after the cutoff time.

    Uses direct Qdrant client for fast retrieval without LLM calls.
    This is used by DigestGenerationWorkflow to query already-ingested
    articles for digest composition.

    Args:
        cutoff: Minimum processed_at timestamp
        limit: Maximum articles to return

    Returns:
        List of article dictionaries with all stored metadata
    """
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.http import models

        qdrant_host = os.environ.get("QDRANT_HOST", "qdrant.database.svc.cluster.local")
        qdrant_port = int(os.environ.get("QDRANT_PORT", "6333"))
        qdrant_api_key = os.environ.get("QDRANT_API_KEY")
        collection = os.environ.get("QDRANT_COLLECTION", "news-monitor")

        # Auto-detect HTTPS: use if port is 443 or QDRANT_USE_HTTPS is set
        use_https = (
            os.environ.get("QDRANT_USE_HTTPS", "").lower() in ("true", "1", "yes")
            or qdrant_port == 443
        )
        scheme = "https" if use_https else "http"

        # Connect to Qdrant directly (bypass mem0 for speed)
        client = QdrantClient(
            url=f"{scheme}://{qdrant_host}:{qdrant_port}",
            api_key=qdrant_api_key if qdrant_api_key else None,
        )

        # Filter by type="article" in Qdrant, then filter by date in Python
        # (Qdrant Range only works with numeric values, not ISO strings)
        # Note: mem0 stores metadata at top level of payload, not nested under "metadata"
        cutoff_iso = cutoff.isoformat()

        results = client.scroll(
            collection_name=collection,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="type",
                        match=models.MatchValue(value="article"),
                    ),
                ]
            ),
            limit=limit * 2,  # Fetch extra since we filter by date in Python
            with_payload=True,
            with_vectors=False,  # Don't need vectors for digest
        )

        articles = []
        for point in results[0]:  # scroll returns (points, next_offset)
            payload = point.payload or {}

            # Filter by processed_at >= cutoff in Python
            # (Qdrant Range only works with numeric values)
            processed_at_str = payload.get("processed_at", "")
            if processed_at_str:
                try:
                    # Parse ISO datetime string
                    processed_at_dt = datetime.fromisoformat(
                        processed_at_str.replace("Z", "+00:00")
                    )
                    # Make cutoff timezone-aware if processed_at is
                    cutoff_aware = cutoff
                    if processed_at_dt.tzinfo is not None and cutoff.tzinfo is None:
                        cutoff_aware = cutoff.replace(tzinfo=UTC)
                    elif processed_at_dt.tzinfo is None and cutoff.tzinfo is not None:
                        processed_at_dt = processed_at_dt.replace(tzinfo=UTC)

                    if processed_at_dt < cutoff_aware:
                        continue  # Skip articles older than cutoff
                except ValueError:
                    continue  # Skip if date parsing fails

            # Extract entities from payload
            # New articles have entities in metadata field (comma-separated string)
            # Legacy articles have entities in the "data" text field ("Entities: X, Y, Z")
            entities = _extract_entities_from_payload(payload)

            # mem0 stores metadata at top level of payload
            articles.append(
                {
                    "url": payload.get("url", ""),
                    "title": payload.get("title", ""),
                    "source": payload.get("source", ""),
                    "source_category": payload.get("category", "general"),
                    "published_at": payload.get("published_at"),
                    "original_summary": "",  # Not stored separately
                    "ai_summary": payload.get("data", ""),  # mem0 stores content in "data" field
                    "category": payload.get("category", "general"),
                    "entities": entities,
                    "importance_score": payload.get("importance_score", 5),
                    "is_breaking": False,  # Not relevant for digest
                    "content_hash": payload.get("content_hash", ""),
                    "processed_at": processed_at_str,
                }
            )

        # Sort by importance (descending) to prioritize high-value articles
        articles.sort(key=lambda a: a.get("importance_score", 0), reverse=True)

        # Limit to requested count after sorting
        articles = articles[:limit]

        logger.info(f"Queried {len(articles)} articles since {cutoff_iso}")
        return articles

    except Exception as e:
        logger.error(f"Failed to query articles from Qdrant: {e}")
        return []
