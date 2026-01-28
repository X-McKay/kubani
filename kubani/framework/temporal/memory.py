"""Memory MCP integration for Temporal workflows.

This module provides Temporal activities for interacting with the Memory MCP server.
It enables syndicates to store and retrieve learnings, knowledge, articles, and trends
as part of their workflow execution.

Usage in workflows:
    from kubani.framework.temporal.memory import (
        store_learning_activity,
        query_learnings_activity,
        store_article_activity,
        get_swarm_context_activity,
    )

    # Store a learning
    result = await workflow.execute_activity(
        store_learning_activity,
        args=["event-classifier", "pattern", "OOMKilled indicates memory pressure"],
        start_to_close_timeout=timedelta(seconds=30),
    )

    # Get context for a swarm task
    context = await workflow.execute_activity(
        get_swarm_context_activity,
        args=["incident-response", ["k8s", "networking"]],
        start_to_close_timeout=timedelta(minutes=1),
    )
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from temporalio import activity

logger = logging.getLogger(__name__)


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
# Context Types for Swarm Pattern
# =============================================================================


@dataclass
class SwarmContext:
    """Context provided to agents in a swarm.

    This bundles together relevant learnings, knowledge, and prior work
    to give agents the context they need for their tasks.

    Attributes:
        request_summary: Summary of the original request
        relevant_learnings: Learnings relevant to this task
        relevant_knowledge: Knowledge relevant to this task
        prior_work: Results from prior tasks in this swarm
        shared_state: Mutable state shared across agents
    """

    request_summary: str
    relevant_learnings: list[dict[str, Any]] = field(default_factory=list)
    relevant_knowledge: list[dict[str, Any]] = field(default_factory=list)
    prior_work: list[dict[str, Any]] = field(default_factory=list)
    shared_state: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "request_summary": self.request_summary,
            "relevant_learnings": self.relevant_learnings,
            "relevant_knowledge": self.relevant_knowledge,
            "prior_work": self.prior_work,
            "shared_state": self.shared_state,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SwarmContext":
        """Create from dictionary."""
        return cls(
            request_summary=data.get("request_summary", ""),
            relevant_learnings=data.get("relevant_learnings", []),
            relevant_knowledge=data.get("relevant_knowledge", []),
            prior_work=data.get("prior_work", []),
            shared_state=data.get("shared_state", {}),
        )


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
            "learning_id": result.learning_id,
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

        return {
            "success": True,
            "learnings": [
                {
                    "learning_id": l.learning_id,
                    "agent_id": l.agent_id,
                    "learning_type": l.learning_type,
                    "content": l.content,
                    "confidence": l.confidence,
                    "relevance_score": l.relevance_score,
                }
                for l in result.learnings
            ],
            "count": result.count,
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
            "knowledge_id": result.knowledge_id,
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
    topic_prefix: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Query knowledge using semantic search.

    Args:
        query: Natural language query
        topic_prefix: Filter by topic prefix
        limit: Maximum results

    Returns:
        Dict with knowledge list
    """
    logger.info(f"query_knowledge_activity: Querying '{query}'")

    try:
        client = _get_memory_client()

        entries = await client.memory.query_knowledge(
            query=query,
            topic_prefix=topic_prefix,
            limit=limit,
        )

        return {
            "success": True,
            "knowledge": [
                {
                    "knowledge_id": k.knowledge_id,
                    "topic": k.topic,
                    "content": k.content,
                    "source": k.source,
                    "relevance_score": k.relevance_score,
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
    """Store a news article.

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
        Dict with article_id and status
    """
    logger.info(f"store_article_activity: Storing '{title}' from {source}")

    try:
        client = _get_memory_client()

        result = await client.memory.store_article(
            url=url,
            title=title,
            source=source,
            published_at=published_at,
            ai_summary=ai_summary,
            entities=entities,
            importance_score=importance_score,
            category=category,
            content_hash=content_hash,
            ttl_days=ttl_days,
        )

        return {
            "success": True,
            "article_id": result["article_id"],
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
    """Check if an article already exists.

    Args:
        url: Article URL to check
        content_hash: Content hash to check

    Returns:
        Dict with exists status and article_id if found
    """
    try:
        client = _get_memory_client()

        result = await client.memory.check_article_exists(
            url=url,
            content_hash=content_hash,
        )

        return {
            "success": True,
            "exists": result["exists"],
            "article_id": result.get("article_id"),
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
    """Query stored articles.

    Args:
        start_date: ISO format start date
        end_date: ISO format end date
        source: Filter by source
        entity: Filter by entity
        category: Filter by category
        min_importance: Minimum importance score
        limit: Maximum results

    Returns:
        Dict with articles list
    """
    logger.info("query_articles_activity: Querying articles")

    try:
        client = _get_memory_client()

        articles = await client.memory.query_articles(
            start_date=start_date,
            end_date=end_date,
            source=source,
            entity=entity,
            category=category,
            min_importance=min_importance,
            limit=limit,
        )

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
    """Store a trend snapshot.

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

        result = await client.memory.store_trend_snapshot(
            snapshot_date=datetime.utcnow().isoformat(),
            trends=trends,
            emerging_topics=emerging_topics,
            declining_topics=declining_topics,
            total_articles=total_articles,
            ttl_days=ttl_days,
        )

        return {
            "success": True,
            "snapshot_id": result["snapshot_id"],
            "trends_count": result["trends_count"],
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
    """Get a trend snapshot.

    Args:
        date: ISO format date (or None for latest)

    Returns:
        Trend snapshot data
    """
    logger.info(f"get_trend_snapshot_activity: Getting snapshot for {date or 'latest'}")

    try:
        client = _get_memory_client()

        result = await client.memory.get_trend_snapshot(date=date)

        if result:
            return {
                "success": True,
                "snapshot": result,
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
# Swarm Context Activities
# =============================================================================


@activity.defn
async def get_swarm_context_activity(
    request_summary: str,
    topics: list[str],
    prior_work: list[dict[str, Any]] | None = None,
    max_learnings: int = 10,
    max_knowledge: int = 5,
) -> dict[str, Any]:
    """Build context for a swarm task.

    This activity queries relevant learnings and knowledge based on the
    request and topics, then bundles it into a SwarmContext for the agent.

    Args:
        request_summary: Summary of the original request
        topics: Topics to query for relevant context
        prior_work: Results from prior tasks in this swarm
        max_learnings: Maximum learnings to include
        max_knowledge: Maximum knowledge entries to include

    Returns:
        SwarmContext as dict
    """
    logger.info(f"get_swarm_context_activity: Building context for '{request_summary[:50]}...'")

    activity.heartbeat("Building swarm context")

    try:
        client = _get_memory_client()

        # Query learnings related to topics
        learnings = []
        for topic in topics[:3]:  # Limit to prevent too many queries
            result = await client.memory.query_learnings(
                query=topic,
                min_confidence=0.6,
                limit=max_learnings // len(topics) + 1,
            )
            for l in result.learnings:
                learnings.append(
                    {
                        "content": l.content,
                        "agent_id": l.agent_id,
                        "learning_type": l.learning_type,
                        "confidence": l.confidence,
                    }
                )

        # Deduplicate and limit
        seen_content = set()
        unique_learnings = []
        for l in learnings:
            if l["content"] not in seen_content:
                seen_content.add(l["content"])
                unique_learnings.append(l)
                if len(unique_learnings) >= max_learnings:
                    break

        # Query knowledge
        knowledge = []
        for topic in topics[:2]:  # Limit topics
            entries = await client.memory.query_knowledge(
                query=topic,
                limit=max_knowledge // len(topics) + 1,
            )
            for k in entries:
                knowledge.append(
                    {
                        "topic": k.topic,
                        "content": k.content,
                        "source": k.source,
                    }
                )

        # Deduplicate
        seen_topics = set()
        unique_knowledge = []
        for k in knowledge:
            if k["topic"] not in seen_topics:
                seen_topics.add(k["topic"])
                unique_knowledge.append(k)
                if len(unique_knowledge) >= max_knowledge:
                    break

        context = SwarmContext(
            request_summary=request_summary,
            relevant_learnings=unique_learnings,
            relevant_knowledge=unique_knowledge,
            prior_work=prior_work or [],
            shared_state={},
        )

        return context.to_dict()

    except Exception as e:
        logger.error(f"get_swarm_context_activity: Failed: {e}")
        # Return empty context on failure
        return SwarmContext(
            request_summary=request_summary,
            prior_work=prior_work or [],
        ).to_dict()


@activity.defn
async def update_swarm_context_activity(
    context: dict[str, Any],
    new_work: dict[str, Any],
    new_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Update swarm context with new work and state.

    Args:
        context: Current SwarmContext as dict
        new_work: New work result to add to prior_work
        new_state: New state values to merge into shared_state

    Returns:
        Updated SwarmContext as dict
    """
    swarm_context = SwarmContext.from_dict(context)

    # Add new work
    swarm_context.prior_work.append(new_work)

    # Merge new state
    if new_state:
        swarm_context.shared_state.update(new_state)

    return swarm_context.to_dict()


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
            "found": result["found"],
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
    # Context types
    "SwarmContext",
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
    # Trend activities
    "store_trend_snapshot_activity",
    "get_trend_snapshot_activity",
    # Swarm context activities
    "get_swarm_context_activity",
    "update_swarm_context_activity",
    # Cache activities
    "cache_workflow_state_activity",
    "get_cached_workflow_state_activity",
]
