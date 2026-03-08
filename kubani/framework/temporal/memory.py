"""Memory MCP integration for Temporal workflows.

This module provides Temporal activities for interacting with the Memory MCP server.
It enables syndicates to store and retrieve learnings, knowledge, articles, and trends
as part of their workflow execution.

Usage in workflows:
    from kubani.framework.temporal.memory import (
        store_learning_activity,
        query_learnings_activity,
        store_article_activity,
    )

    # Store a learning
    result = await workflow.execute_activity(
        store_learning_activity,
        args=["event-classifier", "pattern", "OOMKilled indicates memory pressure"],
        start_to_close_timeout=timedelta(seconds=30),
    )
"""

import hashlib
import logging
from datetime import datetime
from typing import Any

from temporalio import activity

logger = logging.getLogger(__name__)


def _url_hash(url: str) -> str:
    """Create a short hash of a URL for cache keys."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def _parse_iso_date(date_str: str | None) -> datetime | None:
    """Parse an ISO format date string safely.

    Handles:
    - Full ISO format with time (e.g., "2026-01-29T10:30:00")
    - Dates ending in "Z" (UTC)
    - Date-only format (e.g., "2026-01-29")
    - ISO format with microseconds
    - ISO format with timezone offset

    Args:
        date_str: ISO format date string, or None

    Returns:
        datetime object if parsing succeeds, None otherwise
    """
    if not date_str:
        return None

    try:
        # Handle Z suffix (UTC indicator)
        if date_str.endswith("Z"):
            date_str = date_str[:-1] + "+00:00"

        # Try parsing with fromisoformat (handles most ISO formats)
        return datetime.fromisoformat(date_str)
    except (ValueError, TypeError):
        pass

    # Try date-only format
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        pass

    return None


def _filter_articles_by_date(
    articles: list[dict[str, Any]],
    start_date: str | None,
    end_date: str | None,
) -> list[dict[str, Any]]:
    """Filter articles by date bounds.

    Articles are filtered based on their `metadata.published_at` field.
    Articles with missing or invalid dates are included (can't determine range).

    Args:
        articles: List of article dicts with metadata
        start_date: ISO format start date (filter out articles before this)
        end_date: ISO format end date (filter out articles after this)

    Returns:
        Filtered list of articles
    """
    if not start_date and not end_date:
        return articles

    start_dt = _parse_iso_date(start_date)
    end_dt = _parse_iso_date(end_date)

    filtered = []
    for article in articles:
        metadata = article.get("metadata", {})
        published_at = metadata.get("published_at") if metadata else None
        published_dt = _parse_iso_date(published_at)

        # Include articles with unparseable dates (can't determine range)
        if published_dt is None:
            filtered.append(article)
            continue

        # Filter by date bounds
        if start_dt and published_dt < start_dt:
            continue
        if end_dt and published_dt > end_dt:
            continue

        filtered.append(article)

    return filtered


# =============================================================================
# Memory Client Factory
# =============================================================================


def _get_memory_client():
    """Get a Memory MCP client.

    Creates a client that connects to the Memory MCP server.
    In production, this connects via the MCP protocol.
    """
    # Import lazily to avoid circular dependencies
    from kubani.framework.mcp import get_mcp_client

    return get_mcp_client()


# =============================================================================
# Learning Activities
# =============================================================================


@activity.defn
async def store_learning_activity(
    agent_id: str,
    learning_type: str,
    content: str,
    context: dict[str, Any] | None = None,
    confidence: float = 0.8,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Store a learning from an agent execution.

    Args:
        agent_id: ID of the agent that learned this
        learning_type: Type (pattern, anti_pattern, insight, fact)
        content: The learning content
        context: Optional context/metadata
        confidence: Confidence score 0-1
        tags: Optional tags

    Returns:
        Dict with learning_id and status
    """
    logger.info(f"store_learning_activity: Storing {learning_type} from {agent_id}")

    try:
        client = _get_memory_client()

        result = await client.memory.store_learning(
            agent_id=agent_id,
            learning_type=learning_type,
            content=content,
            context=context,
            confidence=confidence,
            tags=tags,
        )

        return {
            "success": True,
            "learning_id": result.get("learning_id"),
            "agent_id": agent_id,
            "learning_type": learning_type,
        }

    except Exception as e:
        logger.error(f"store_learning_activity: Failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@activity.defn
async def query_learnings_activity(
    query: str,
    agent_id: str | None = None,
    learning_type: str | None = None,
    min_confidence: float = 0.5,
    limit: int = 10,
) -> dict[str, Any]:
    """Query learnings using semantic search.

    Args:
        query: Natural language query
        agent_id: Filter by agent (optional)
        learning_type: Filter by type (optional)
        min_confidence: Minimum confidence threshold
        limit: Maximum results

    Returns:
        Dict with learnings list and count
    """
    logger.info(f"query_learnings_activity: Querying '{query}'")

    try:
        client = _get_memory_client()

        result = await client.memory.query_learnings(
            query=query,
            agent_id=agent_id,
            learning_type=learning_type,
            min_confidence=min_confidence,
            limit=limit,
        )

        learnings = result.get("learnings", [])
        return {
            "success": True,
            "learnings": [
                {
                    "learning_id": l.get("learning_id"),
                    "agent_id": l.get("agent_id"),
                    "learning_type": l.get("learning_type"),
                    "content": l.get("content"),
                    "confidence": l.get("confidence"),
                    "relevance_score": l.get("relevance_score"),
                }
                for l in learnings
            ],
            "count": result.get("count", len(learnings)),
        }

    except Exception as e:
        logger.error(f"query_learnings_activity: Failed: {e}")
        return {
            "success": False,
            "learnings": [],
            "count": 0,
            "error": str(e),
        }


# =============================================================================
# Knowledge Activities
# =============================================================================


@activity.defn
async def store_knowledge_activity(
    topic: str,
    content: str,
    source: str,
    related_topics: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Store domain knowledge with relationships.

    Args:
        topic: Knowledge topic path
        content: Knowledge content
        source: Source of knowledge
        related_topics: Related topic paths
        metadata: Optional metadata

    Returns:
        Dict with knowledge_id and status
    """
    logger.info(f"store_knowledge_activity: Storing knowledge for '{topic}'")

    try:
        client = _get_memory_client()

        result = await client.memory.store_knowledge(
            topic=topic,
            content=content,
            source=source,
            related_topics=related_topics,
            metadata=metadata,
        )

        return {
            "success": True,
            "knowledge_id": result.get("knowledge_id"),
            "topic": topic,
        }

    except Exception as e:
        logger.error(f"store_knowledge_activity: Failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@activity.defn
async def query_knowledge_activity(
    query: str,
    limit: int = 10,
) -> dict[str, Any]:
    """Query knowledge using semantic search.

    Args:
        query: Natural language query
        limit: Maximum results

    Returns:
        Dict with knowledge list
    """
    logger.info(f"query_knowledge_activity: Querying '{query}'")

    try:
        client = _get_memory_client()

        entries = await client.memory.query_knowledge(
            query=query,
            limit=limit,
        )

        # entries is a list of dicts from the MCP server
        if not isinstance(entries, list):
            entries = entries.get("entries", []) if isinstance(entries, dict) else []

        return {
            "success": True,
            "knowledge": [
                {
                    "knowledge_id": k.get("knowledge_id"),
                    "topic": k.get("topic"),
                    "content": k.get("content"),
                    "source": k.get("source"),
                    "relevance_score": k.get("relevance_score"),
                }
                for k in entries
            ],
            "count": len(entries),
        }

    except Exception as e:
        logger.error(f"query_knowledge_activity: Failed: {e}")
        return {
            "success": False,
            "knowledge": [],
            "count": 0,
            "error": str(e),
        }


# =============================================================================
# Article/News Activities
# =============================================================================


@activity.defn
async def store_article_activity(
    url: str,
    title: str,
    source: str,
    published_at: str | None = None,
    ai_summary: str = "",
    entities: list[str] | None = None,
    importance_score: int = 5,
    category: str = "general",
    content_hash: str = "",
    ttl_days: int = 14,
) -> dict[str, Any]:
    """Store a news article using generic Memory MCP tools.

    Strategy:
    1. Store article content as knowledge entry with topic="article:{url_hash}"
    2. Set cache key for URL deduplication

    Args:
        url: Article URL
        title: Article title
        source: Source name
        published_at: ISO format publication date
        ai_summary: AI-generated summary
        entities: Extracted entities/topics
        importance_score: Importance 1-10
        category: Article category
        content_hash: Hash for deduplication
        ttl_days: Days to retain

    Returns:
        Dict with article_id (knowledge_id) and status
    """
    logger.info(f"store_article_activity: Storing '{title}' from {source}")

    try:
        client = _get_memory_client()
        url_hash = _url_hash(url)

        # Build content string for knowledge storage
        content_parts = [f"# {title}", f"Source: {source}"]
        if published_at:
            content_parts.append(f"Published: {published_at}")
        if ai_summary:
            content_parts.append(f"\n{ai_summary}")
        content = "\n".join(content_parts)

        # Build metadata
        metadata = {
            "url": url,
            "source": source,
            "category": category,
            "importance_score": importance_score,
            "entities": entities or [],
        }
        if published_at:
            metadata["published_at"] = published_at
        if content_hash:
            metadata["content_hash"] = content_hash

        # Store as knowledge entry
        knowledge_result = await client.memory.store_knowledge(
            topic=f"article:{url_hash}",
            content=content,
            source=source,
            related_topics=[f"category:{category}"] + [f"entity:{e}" for e in (entities or [])[:5]],
            metadata=metadata,
        )

        # Set cache key for deduplication (TTL in seconds)
        await client.memory.cache_set(
            key=f"article:dedup:{url_hash}",
            value={"url": url, "stored_at": datetime.utcnow().isoformat()},
            ttl_seconds=ttl_days * 86400,
        )

        return {
            "success": True,
            "article_id": knowledge_result.get("knowledge_id"),
            "url": url,
        }

    except Exception as e:
        logger.error(f"store_article_activity: Failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@activity.defn
async def check_article_exists_activity(
    url: str | None = None,
    content_hash: str | None = None,
) -> dict[str, Any]:
    """Check if an article already exists using cache lookup.

    Args:
        url: Article URL to check
        content_hash: Content hash to check (unused in cache strategy)

    Returns:
        Dict with exists status
    """
    if not url:
        return {"success": True, "exists": False, "article_id": None}

    try:
        client = _get_memory_client()
        url_hash = _url_hash(url)

        result = await client.memory.cache_get(key=f"article:dedup:{url_hash}")

        exists = result.get("found", False)
        return {
            "success": True,
            "exists": exists,
            "article_id": f"article:{url_hash}" if exists else None,
        }

    except Exception as e:
        logger.error(f"check_article_exists_activity: Failed: {e}")
        return {
            "success": False,
            "exists": False,
            "error": str(e),
        }


@activity.defn
async def query_articles_activity(
    start_date: str | None = None,
    end_date: str | None = None,
    source: str | None = None,
    entity: str | None = None,
    category: str | None = None,
    min_importance: int = 0,
    limit: int = 100,
) -> dict[str, Any]:
    """Query stored articles using generic knowledge query with date filtering.

    Articles are post-filtered by their `published_at` metadata against the
    date bounds. Articles with missing or invalid dates are included (can't
    determine if they match the range).

    Args:
        start_date: ISO format start date (filter out articles before this)
        end_date: ISO format end date (filter out articles after this)
        source: Filter by source (used in query text)
        entity: Filter by entity (used in query text)
        category: Filter by category (used in query text)
        min_importance: Minimum importance score (post-filter)
        limit: Maximum results

    Returns:
        Dict with articles list
    """
    logger.info("query_articles_activity: Querying articles")

    try:
        client = _get_memory_client()

        # Build semantic query
        query_parts = ["news articles"]
        if source:
            query_parts.append(f"from {source}")
        if entity:
            query_parts.append(f"about {entity}")
        if category:
            query_parts.append(f"in {category} category")
        if start_date:
            query_parts.append(f"after {start_date}")

        query = " ".join(query_parts)

        # Query knowledge entries - over-fetch to account for date and importance filtering
        entries = await client.memory.query_knowledge(
            query=query,
            limit=limit * 3,
        )

        # Parse entries - they may come as list or dict with entries key
        if isinstance(entries, dict):
            entries = entries.get("entries", entries.get("knowledge", []))
        if not isinstance(entries, list):
            entries = []

        # Filter to only article entries
        article_entries = [e for e in entries if e.get("topic", "").startswith("article:")]

        # Apply date filtering
        article_entries = _filter_articles_by_date(article_entries, start_date, end_date)

        # Transform to article format and filter by importance
        articles = []
        for entry in article_entries:
            metadata = entry.get("metadata", {})
            importance = metadata.get("importance_score", 5)

            if importance < min_importance:
                continue

            articles.append(
                {
                    "article_id": entry.get("knowledge_id"),
                    "url": metadata.get("url", ""),
                    "title": entry.get("content", "").split("\n")[0].lstrip("# "),
                    "source": metadata.get("source", entry.get("source", "")),
                    "published_at": metadata.get("published_at"),
                    "category": metadata.get("category", "general"),
                    "importance_score": importance,
                    "entities": metadata.get("entities", []),
                }
            )

            if len(articles) >= limit:
                break

        return {
            "success": True,
            "articles": articles,
            "count": len(articles),
        }

    except Exception as e:
        logger.error(f"query_articles_activity: Failed: {e}")
        return {
            "success": False,
            "articles": [],
            "count": 0,
            "error": str(e),
        }


# =============================================================================
# Repo Activities
# =============================================================================


def _repo_url_hash(url: str) -> str:
    """Create a short hash of a repo URL for cache keys."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


@activity.defn
async def store_repo_activity(
    repo_url: str,
    name: str,
    description: str,
    stars: int,
    language: str | None = None,
    topics: list[str] | None = None,
    forks: int = 0,
    trending_score: float = 0.0,
    ttl_days: int = 14,
) -> dict[str, Any]:
    """Store a GitHub repository using generic Memory MCP tools.

    Args:
        repo_url: Full GitHub repository URL
        name: Repository name
        description: Repository description
        stars: Star count
        language: Primary programming language
        topics: List of repository topics
        forks: Fork count
        trending_score: Trending/popularity score
        ttl_days: Days to retain in cache for deduplication

    Returns:
        Dict with repo_id and status
    """
    logger.info(f"store_repo_activity: Storing '{name}' ({stars} stars)")

    try:
        client = _get_memory_client()
        url_hash = _repo_url_hash(repo_url)

        # Extract owner/repo from URL for topic
        repo_path = repo_url.replace("https://github.com/", "").rstrip("/")

        # Build content string
        content_parts = [
            f"# {name}",
            f"URL: {repo_url}",
            f"Stars: {stars} | Forks: {forks}",
        ]
        if language:
            content_parts.append(f"Language: {language}")
        if description:
            content_parts.append(f"\n{description}")

        content = "\n".join(content_parts)

        # Build metadata
        metadata = {
            "url": repo_url,
            "name": name,
            "stars": stars,
            "forks": forks,
            "language": language,
            "topics": topics or [],
            "trending_score": trending_score,
        }

        # Store as knowledge entry
        knowledge_result = await client.memory.store_knowledge(
            topic=f"repo:{repo_path}",
            content=content,
            source="github",
            related_topics=[f"topic:{t}" for t in (topics or [])[:5]],
            metadata=metadata,
        )

        # Set cache key for deduplication
        await client.memory.cache_set(
            key=f"repo:dedup:{url_hash}",
            value={"url": repo_url, "stored_at": datetime.utcnow().isoformat()},
            ttl_seconds=ttl_days * 86400,
        )

        return {
            "success": True,
            "repo_id": knowledge_result.get("knowledge_id"),
            "url": repo_url,
        }

    except Exception as e:
        logger.error(f"store_repo_activity: Failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@activity.defn
async def check_repo_exists_activity(
    repo_url: str,
) -> dict[str, Any]:
    """Check if a repository already exists using cache lookup.

    Args:
        repo_url: Repository URL to check

    Returns:
        Dict with exists status
    """
    if not repo_url:
        return {"success": True, "exists": False, "repo_id": None}

    try:
        client = _get_memory_client()
        url_hash = _repo_url_hash(repo_url)

        result = await client.memory.cache_get(key=f"repo:dedup:{url_hash}")

        exists = result.get("found", False)
        return {
            "success": True,
            "exists": exists,
            "repo_id": f"repo:{url_hash}" if exists else None,
        }

    except Exception as e:
        logger.error(f"check_repo_exists_activity: Failed: {e}")
        return {
            "success": False,
            "exists": False,
            "error": str(e),
        }


# =============================================================================
# Paper Activities
# =============================================================================


@activity.defn
async def store_paper_activity(
    arxiv_id: str,
    title: str,
    abstract: str,
    authors: list[str] | None = None,
    categories: list[str] | None = None,
    published_at: str | None = None,
    ttl_days: int = 14,
) -> dict[str, Any]:
    """Store an arXiv paper with deduplication.

    Args:
        arxiv_id: ArXiv paper ID (e.g., "2401.12345")
        title: Paper title
        abstract: Paper abstract
        authors: List of author names
        categories: ArXiv categories
        published_at: ISO format publication date
        ttl_days: Days to retain in cache for deduplication

    Returns:
        Dict with paper_id and status
    """
    logger.info(f"store_paper_activity: Storing '{title}' ({arxiv_id})")

    try:
        client = _get_memory_client()

        # Build content string
        content = f"{title}\n\n{abstract}"

        # Build metadata
        metadata = {
            "arxiv_id": arxiv_id,
            "authors": authors or [],
        }
        if published_at:
            metadata["published_at"] = published_at

        # Store as knowledge entry
        knowledge_result = await client.memory.store_knowledge(
            topic=f"research/arxiv/{arxiv_id}",
            content=content,
            source="arxiv",
            related_topics=categories or [],
            metadata=metadata,
        )

        # Set cache key for deduplication (TTL in seconds)
        await client.memory.cache_set(
            key=f"paper:dedup:{arxiv_id}",
            value={"arxiv_id": arxiv_id, "stored_at": datetime.utcnow().isoformat()},
            ttl_seconds=ttl_days * 86400,
        )

        return {
            "success": True,
            "paper_id": knowledge_result.get("knowledge_id"),
            "arxiv_id": arxiv_id,
        }

    except Exception as e:
        logger.error(f"store_paper_activity: Failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@activity.defn
async def check_paper_exists_activity(
    arxiv_id: str,
) -> dict[str, Any]:
    """Check if a paper already exists using cache lookup.

    Args:
        arxiv_id: ArXiv paper ID to check

    Returns:
        Dict with exists status
    """
    if not arxiv_id:
        return {"success": True, "exists": False, "paper_id": None}

    try:
        client = _get_memory_client()

        result = await client.memory.cache_get(key=f"paper:dedup:{arxiv_id}")

        exists = result.get("found", False)
        return {
            "success": True,
            "exists": exists,
            "paper_id": f"research/arxiv/{arxiv_id}" if exists else None,
        }

    except Exception as e:
        logger.error(f"check_paper_exists_activity: Failed: {e}")
        return {
            "success": False,
            "exists": False,
            "error": str(e),
        }


# =============================================================================
# Trend Activities
# =============================================================================


@activity.defn
async def store_trend_snapshot_activity(
    trends: list[dict[str, Any]],
    emerging_topics: list[str] | None = None,
    declining_topics: list[str] | None = None,
    total_articles: int = 0,
    ttl_days: int = 30,
) -> dict[str, Any]:
    """Store a trend snapshot using cache.

    Args:
        trends: List of trend dicts
        emerging_topics: Emerging topics
        declining_topics: Declining topics
        total_articles: Article count
        ttl_days: Days to retain

    Returns:
        Dict with snapshot_id
    """
    logger.info(f"store_trend_snapshot_activity: Storing {len(trends)} trends")

    try:
        client = _get_memory_client()

        # Use today's date as snapshot key
        snapshot_date = datetime.utcnow().strftime("%Y-%m-%d")

        snapshot = {
            "snapshot_date": snapshot_date,
            "trends": trends,
            "emerging_topics": emerging_topics or [],
            "declining_topics": declining_topics or [],
            "total_articles": total_articles,
            "created_at": datetime.utcnow().isoformat(),
        }

        # Store in cache with TTL
        await client.memory.cache_set(
            key=f"trend:snapshot:{snapshot_date}",
            value=snapshot,
            ttl_seconds=ttl_days * 86400,
        )

        # Also store as "latest" for easy retrieval
        await client.memory.cache_set(
            key="trend:snapshot:latest",
            value=snapshot,
            ttl_seconds=ttl_days * 86400,
        )

        return {
            "success": True,
            "snapshot_id": f"trend:snapshot:{snapshot_date}",
            "trends_count": len(trends),
        }

    except Exception as e:
        logger.error(f"store_trend_snapshot_activity: Failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@activity.defn
async def get_trend_snapshot_activity(
    date: str | None = None,
) -> dict[str, Any]:
    """Get a trend snapshot from cache.

    Args:
        date: ISO format date (YYYY-MM-DD) or None for latest

    Returns:
        Trend snapshot data
    """
    logger.info(f"get_trend_snapshot_activity: Getting snapshot for {date or 'latest'}")

    try:
        client = _get_memory_client()

        # Build cache key
        if date:
            cache_key = f"trend:snapshot:{date}"
        else:
            cache_key = "trend:snapshot:latest"

        result = await client.memory.cache_get(key=cache_key)

        if result.get("found") and result.get("value"):
            snapshot = result["value"]
            # Ensure snapshot has an ID
            if "snapshot_id" not in snapshot:
                snapshot["snapshot_id"] = cache_key
            return {
                "success": True,
                "snapshot": snapshot,
            }
        else:
            return {
                "success": True,
                "snapshot": None,
            }

    except Exception as e:
        logger.error(f"get_trend_snapshot_activity: Failed: {e}")
        return {
            "success": False,
            "snapshot": None,
            "error": str(e),
        }


# =============================================================================
# Cache Activities (for workflow state)
# =============================================================================


@activity.defn
async def cache_workflow_state_activity(
    workflow_id: str,
    state: dict[str, Any],
    ttl_hours: int = 24,
) -> dict[str, Any]:
    """Cache workflow state for recovery or inspection.

    Args:
        workflow_id: Workflow identifier
        state: State to cache
        ttl_hours: Hours to retain

    Returns:
        Success status
    """
    try:
        client = _get_memory_client()

        await client.memory.cache_set(
            key=f"workflow:state:{workflow_id}",
            value=state,
            ttl_seconds=ttl_hours * 3600,
        )

        return {
            "success": True,
            "workflow_id": workflow_id,
        }

    except Exception as e:
        logger.error(f"cache_workflow_state_activity: Failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@activity.defn
async def get_cached_workflow_state_activity(
    workflow_id: str,
) -> dict[str, Any]:
    """Get cached workflow state.

    Args:
        workflow_id: Workflow identifier

    Returns:
        Cached state or None
    """
    try:
        client = _get_memory_client()

        result = await client.memory.cache_get(
            key=f"workflow:state:{workflow_id}",
        )

        return {
            "success": True,
            "found": result.get("found", False),
            "state": result.get("value"),
        }

    except Exception as e:
        logger.error(f"get_cached_workflow_state_activity: Failed: {e}")
        return {
            "success": False,
            "found": False,
            "error": str(e),
        }


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Learning activities
    "store_learning_activity",
    "query_learnings_activity",
    # Knowledge activities
    "store_knowledge_activity",
    "query_knowledge_activity",
    # Article activities
    "store_article_activity",
    "check_article_exists_activity",
    "query_articles_activity",
    # Repo activities
    "store_repo_activity",
    "check_repo_exists_activity",
    # Trend activities
    "store_trend_snapshot_activity",
    "get_trend_snapshot_activity",
    # Cache activities
    "cache_workflow_state_activity",
    "get_cached_workflow_state_activity",
]
