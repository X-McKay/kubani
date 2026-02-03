"""
Memory MCP Server implementation.

Provides a unified MCP interface for the Kubani shared memory system.
Combines Qdrant (vector), Neo4j (graph), and Redis (cache) into a single
high-level memory interface for agents and Claude Code.
"""

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any
from uuid import uuid4

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from memory_mcp.backends import CacheBackend, GraphBackend, VectorBackend
from memory_mcp.models import (
    KnowledgeEntry,
    KnowledgeResult,
    LearningResult,
    LearningsResult,
    MemoryAddResult,
    MemoryGetResult,
    MemoryLinkResult,
    MemoryObject,
    MemoryRelation,
    MemorySearchResult,
    MemorySeenResult,
    MemoryStats,
    RelationshipResult,
)

logger = logging.getLogger(__name__)

# Global backends
_vector_backend: VectorBackend | None = None
_graph_backend: GraphBackend | None = None
_cache_backend: CacheBackend | None = None


async def connect_backends() -> None:
    """Connect to all memory backends at server startup."""
    global _vector_backend, _graph_backend, _cache_backend

    logger.info("Connecting to memory backends...")

    # Vector backend (Qdrant)
    _vector_backend = VectorBackend(
        host=os.environ.get("QDRANT_HOST", "localhost"),
        port=int(os.environ.get("QDRANT_PORT", "6333")),
        api_key=os.environ.get("QDRANT_API_KEY"),
    )
    await _vector_backend.connect()

    # Graph backend (Neo4j)
    _graph_backend = GraphBackend(
        uri=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
        user=os.environ.get("NEO4J_USER", "neo4j"),
        password=os.environ.get("NEO4J_PASSWORD", ""),
    )
    await _graph_backend.connect()

    # Cache backend (Redis)
    _cache_backend = CacheBackend(
        host=os.environ.get("REDIS_HOST", "localhost"),
        port=int(os.environ.get("REDIS_PORT", "6379")),
        password=os.environ.get("REDIS_PASSWORD"),
    )
    await _cache_backend.connect()

    logger.info("All memory backends connected")


async def disconnect_backends() -> None:
    """Disconnect from all memory backends."""
    global _vector_backend, _graph_backend, _cache_backend

    if _vector_backend:
        await _vector_backend.disconnect()
        _vector_backend = None

    if _graph_backend:
        await _graph_backend.disconnect()
        _graph_backend = None

    if _cache_backend:
        await _cache_backend.disconnect()
        _cache_backend = None


def _check_backends() -> None:
    """Ensure all backends are connected."""
    if not all([_vector_backend, _graph_backend, _cache_backend]):
        raise RuntimeError(
            "Memory backends not initialized. "
            "Ensure connect_backends() was called at server startup."
        )


@asynccontextmanager
async def lifespan(server: FastMCP):
    """MCP session lifespan."""
    yield


def create_server() -> FastMCP:
    """Create and configure the Memory MCP server."""
    allowed_hosts_env = os.environ.get("MCP_ALLOWED_HOSTS", "")
    allowed_hosts = ["localhost:*", "127.0.0.1:*"]
    if allowed_hosts_env:
        allowed_hosts.extend(h.strip() for h in allowed_hosts_env.split(",") if h.strip())

    mcp = FastMCP(
        name="Memory MCP Server",
        instructions=(
            "Unified memory system for AI agents. "
            "Store and retrieve learnings, knowledge, and relationships. "
            "Combines vector search (Qdrant), graph relationships (Neo4j), "
            "and fast caching (Redis) into a single interface."
        ),
        lifespan=lifespan,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=allowed_hosts,
        ),
    )

    # =========================================================================
    # Generic Memory Tools (per skills-mcp-integration plan)
    # =========================================================================

    @mcp.tool()
    async def add(
        type: str,
        namespace: str,
        data: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        relations: list[dict[str, str]] | None = None,
    ) -> MemoryAddResult:
        """
        Store any object with optional relationships.

        Args:
            type: Object type (e.g., "document", "analysis", "trend", "event")
            namespace: Namespace for organization (e.g., "news/articles", "k8s/pods")
            data: The actual content/data to store
            metadata: Optional additional metadata (timestamps, source, etc.)
            relations: Optional list of relations to create, each with target_id and relation_type

        Returns:
            Created object info including ID and timestamp
        """
        _check_backends()

        object_id = str(uuid4())
        created_at = datetime.utcnow()

        # Store in vector database
        await _vector_backend.store_object(
            object_id=object_id,
            object_type=type,
            namespace=namespace,
            data=data,
            metadata=metadata or {},
            created_at=created_at,
        )

        # Create graph node
        await _graph_backend.create_memory_node(
            object_id=object_id,
            object_type=type,
            namespace=namespace,
        )

        # Create relations if provided
        relations_created = 0
        if relations:
            for rel in relations:
                target_id = rel.get("target_id")
                relation_type = rel.get("relation_type")
                if target_id and relation_type:
                    await _graph_backend.create_memory_relation(
                        source_id=object_id,
                        target_id=target_id,
                        relation_type=relation_type,
                    )
                    relations_created += 1

        return MemoryAddResult(
            id=object_id,
            type=type,
            namespace=namespace,
            created_at=created_at,
            relations_created=relations_created,
        )

    @mcp.tool()
    async def search(
        query: str,
        type: str | None = None,
        namespace: str | None = None,
        filters: dict[str, Any] | None = None,
        include_relations: bool = False,
        limit: int = 10,
    ) -> MemorySearchResult:
        """
        Semantic search for memory objects.

        Args:
            query: Natural language search query
            type: Filter by object type (optional)
            namespace: Filter by namespace (optional)
            filters: Additional field-level filters on data (optional)
            include_relations: Whether to include relations in results
            limit: Maximum results (default: 10)

        Returns:
            Matching objects ranked by relevance
        """
        _check_backends()

        objects = await _vector_backend.search_objects(
            query=query,
            object_type=type,
            namespace=namespace,
            filters=filters,
            limit=limit,
        )

        # Fetch relations if requested
        if include_relations:
            for obj in objects:
                obj.relations = await _graph_backend.get_object_relations(obj.id)

        return MemorySearchResult(
            results=objects,
            count=len(objects),
            total=len(objects),  # Could implement proper total count
            query=query,
        )

    @mcp.tool()
    async def get(
        id: str,
        include_relations: bool = False,
    ) -> MemoryGetResult:
        """
        Get a memory object by ID.

        Args:
            id: Object ID
            include_relations: Whether to include relations

        Returns:
            The object if found, or found=False
        """
        _check_backends()

        obj = await _vector_backend.get_object(id)

        if obj is None:
            return MemoryGetResult(found=False, object=None)

        # Fetch relations if requested
        if include_relations:
            obj.relations = await _graph_backend.get_object_relations(obj.id)

        return MemoryGetResult(found=True, object=obj)

    @mcp.tool()
    async def list_objects(
        type: str | None = None,
        namespace: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MemoryObject]:
        """
        List memory objects with optional filtering.

        Args:
            type: Filter by object type (optional)
            namespace: Filter by namespace (optional)
            limit: Maximum results (default: 100)
            offset: Number of results to skip (default: 0)

        Returns:
            List of memory objects
        """
        _check_backends()

        return await _vector_backend.list_objects(
            object_type=type,
            namespace=namespace,
            limit=limit,
            offset=offset,
        )

    @mcp.tool()
    async def link(
        source_id: str,
        target_id: str,
        relation_type: str,
    ) -> MemoryLinkResult:
        """
        Create a relationship between two memory objects.

        Args:
            source_id: Source object ID
            target_id: Target object ID
            relation_type: Type of relationship (e.g., "analyzed_from", "derived_from")

        Returns:
            Link creation result
        """
        _check_backends()

        created = await _graph_backend.create_memory_relation(
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
        )

        return MemoryLinkResult(
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            created=created,
        )

    @mcp.tool()
    async def check_seen(
        key: str,
        namespace: str,
    ) -> MemorySeenResult:
        """
        Check if a key has been seen (for deduplication).

        Args:
            key: The key to check (e.g., URL hash, content hash)
            namespace: Namespace for the check

        Returns:
            Whether the key was previously seen
        """
        _check_backends()

        seen = await _cache_backend.check_seen(key=key, namespace=namespace)

        return MemorySeenResult(
            key=key,
            namespace=namespace,
            seen=seen,
        )

    @mcp.tool()
    async def mark_seen(
        key: str,
        namespace: str,
        ttl_seconds: int | None = None,
    ) -> MemorySeenResult:
        """
        Mark a key as seen (for deduplication).

        Args:
            key: The key to mark (e.g., URL hash, content hash)
            namespace: Namespace for the mark
            ttl_seconds: Optional time-to-live in seconds

        Returns:
            Confirmation of marking
        """
        _check_backends()

        await _cache_backend.mark_seen(
            key=key,
            namespace=namespace,
            ttl_seconds=ttl_seconds,
        )

        return MemorySeenResult(
            key=key,
            namespace=namespace,
            seen=True,
        )

    # =========================================================================
    # Learning Tools (Vector-based semantic memory)
    # =========================================================================

    @mcp.tool()
    async def store_learning(
        agent_id: str,
        learning_type: str,
        content: str,
        context: dict[str, Any] | None = None,
        confidence: float = 0.8,
        tags: list[str] | None = None,
    ) -> LearningResult:
        """
        Store a learning from an agent execution.

        Args:
            agent_id: ID of the agent that learned this
            learning_type: Type of learning (pattern, anti_pattern, insight, fact)
            content: The learning content
            context: Optional context/metadata
            confidence: Confidence score 0-1 (default: 0.8)
            tags: Optional tags for categorization

        Returns:
            Stored learning with ID
        """
        _check_backends()

        learning_id = str(uuid4())
        timestamp = datetime.utcnow()

        # Store in vector database for semantic search
        await _vector_backend.store_learning(
            learning_id=learning_id,
            agent_id=agent_id,
            learning_type=learning_type,
            content=content,
            context=context or {},
            confidence=confidence,
            tags=tags or [],
            timestamp=timestamp,
        )

        # Create graph relationships
        await _graph_backend.create_learning_node(
            learning_id=learning_id,
            agent_id=agent_id,
            learning_type=learning_type,
            tags=tags or [],
        )

        # Cache for fast access
        await _cache_backend.cache_recent_learning(
            agent_id=agent_id,
            learning_id=learning_id,
        )

        return LearningResult(
            learning_id=learning_id,
            agent_id=agent_id,
            learning_type=learning_type,
            content=content,
            confidence=confidence,
            timestamp=timestamp,
        )

    @mcp.tool()
    async def query_learnings(
        query: str,
        agent_id: str | None = None,
        learning_type: str | None = None,
        min_confidence: float = 0.5,
        limit: int = 10,
    ) -> LearningsResult:
        """
        Query learnings using semantic search.

        Args:
            query: Natural language query
            agent_id: Filter by agent (optional)
            learning_type: Filter by type (optional)
            min_confidence: Minimum confidence threshold (default: 0.5)
            limit: Maximum results (default: 10)

        Returns:
            Matching learnings ranked by relevance
        """
        _check_backends()

        learnings = await _vector_backend.search_learnings(
            query=query,
            agent_id=agent_id,
            learning_type=learning_type,
            min_confidence=min_confidence,
            limit=limit,
        )

        return LearningsResult(
            learnings=learnings,
            count=len(learnings),
            query=query,
        )

    @mcp.tool()
    async def get_agent_learnings(
        agent_id: str,
        learning_type: str | None = None,
        limit: int = 20,
    ) -> LearningsResult:
        """
        Get recent learnings for a specific agent.

        Args:
            agent_id: Agent ID
            learning_type: Filter by type (optional)
            limit: Maximum results (default: 20)

        Returns:
            Agent's recent learnings
        """
        _check_backends()

        learnings = await _vector_backend.get_agent_learnings(
            agent_id=agent_id,
            learning_type=learning_type,
            limit=limit,
        )

        return LearningsResult(
            learnings=learnings,
            count=len(learnings),
            query=f"agent:{agent_id}",
        )

    # =========================================================================
    # Knowledge Tools (Graph-based structured knowledge)
    # =========================================================================

    @mcp.tool()
    async def store_knowledge(
        topic: str,
        content: str,
        source: str,
        related_topics: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> KnowledgeResult:
        """
        Store domain knowledge with relationships.

        Args:
            topic: Knowledge topic (e.g., "kubernetes/memory-management")
            content: Knowledge content
            source: Source of knowledge (agent, document, etc.)
            related_topics: Related topic paths
            metadata: Optional metadata

        Returns:
            Stored knowledge entry
        """
        _check_backends()

        knowledge_id = str(uuid4())
        timestamp = datetime.utcnow()

        # Store in vector database
        await _vector_backend.store_knowledge(
            knowledge_id=knowledge_id,
            topic=topic,
            content=content,
            source=source,
            metadata=metadata or {},
            timestamp=timestamp,
        )

        # Create graph node and relationships
        await _graph_backend.create_knowledge_node(
            knowledge_id=knowledge_id,
            topic=topic,
            source=source,
        )

        if related_topics:
            for related in related_topics:
                await _graph_backend.create_relationship(
                    from_topic=topic,
                    to_topic=related,
                    relationship_type="RELATED_TO",
                )

        return KnowledgeResult(
            knowledge_id=knowledge_id,
            topic=topic,
            content=content,
            source=source,
            timestamp=timestamp,
        )

    @mcp.tool()
    async def query_knowledge(
        query: str,
        topic_prefix: str | None = None,
        limit: int = 10,
    ) -> list[KnowledgeEntry]:
        """
        Query knowledge using semantic search.

        Args:
            query: Natural language query
            topic_prefix: Filter by topic prefix (e.g., "kubernetes/")
            limit: Maximum results (default: 10)

        Returns:
            Matching knowledge entries
        """
        _check_backends()

        return await _vector_backend.search_knowledge(
            query=query,
            topic_prefix=topic_prefix,
            limit=limit,
        )

    @mcp.tool()
    async def get_knowledge_graph(
        topic: str,
        depth: int = 2,
    ) -> dict[str, Any]:
        """
        Get the knowledge graph around a topic.

        Args:
            topic: Central topic
            depth: How many relationship hops (default: 2)

        Returns:
            Graph structure with nodes and edges
        """
        _check_backends()

        return await _graph_backend.get_subgraph(
            topic=topic,
            depth=depth,
        )

    @mcp.tool()
    async def find_related_topics(
        topic: str,
        relationship_type: str | None = None,
        limit: int = 10,
    ) -> list[str]:
        """
        Find topics related to a given topic.

        Args:
            topic: Source topic
            relationship_type: Filter by relationship type (optional)
            limit: Maximum results (default: 10)

        Returns:
            List of related topic paths
        """
        _check_backends()

        return await _graph_backend.get_related_topics(
            topic=topic,
            relationship_type=relationship_type,
            limit=limit,
        )

    # =========================================================================
    # Relationship Tools
    # =========================================================================

    @mcp.tool()
    async def create_relationship(
        from_entity: str,
        to_entity: str,
        relationship_type: str,
        properties: dict[str, Any] | None = None,
    ) -> RelationshipResult:
        """
        Create a relationship between entities.

        Args:
            from_entity: Source entity (topic, learning_id, agent_id)
            to_entity: Target entity
            relationship_type: Type of relationship (RELATED_TO, LEARNED_FROM, etc.)
            properties: Optional relationship properties

        Returns:
            Created relationship info
        """
        _check_backends()

        rel_id = await _graph_backend.create_relationship(
            from_topic=from_entity,
            to_topic=to_entity,
            relationship_type=relationship_type,
            properties=properties,
        )

        return RelationshipResult(
            relationship_id=rel_id,
            from_entity=from_entity,
            to_entity=to_entity,
            relationship_type=relationship_type,
        )

    @mcp.tool()
    async def get_entity_relationships(
        entity: str,
        direction: str = "both",
        relationship_type: str | None = None,
    ) -> list[RelationshipResult]:
        """
        Get all relationships for an entity.

        Args:
            entity: Entity identifier
            direction: "incoming", "outgoing", or "both" (default: both)
            relationship_type: Filter by type (optional)

        Returns:
            List of relationships
        """
        _check_backends()

        return await _graph_backend.get_relationships(
            entity=entity,
            direction=direction,
            relationship_type=relationship_type,
        )

    # =========================================================================
    # Cache Tools (Fast access patterns)
    # =========================================================================

    @mcp.tool()
    async def cache_set(
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
    ) -> dict[str, str]:
        """
        Set a value in the cache.

        Args:
            key: Cache key
            value: Value to cache (will be JSON serialized)
            ttl_seconds: Time-to-live in seconds (optional)

        Returns:
            Confirmation
        """
        _check_backends()

        await _cache_backend.set(key, value, ttl_seconds)

        return {
            "status": "cached",
            "key": key,
        }

    @mcp.tool()
    async def cache_get(
        key: str,
    ) -> dict[str, Any]:
        """
        Get a value from the cache.

        Args:
            key: Cache key

        Returns:
            Cached value or null if not found
        """
        _check_backends()

        value = await _cache_backend.get(key)

        return {
            "key": key,
            "value": value,
            "found": value is not None,
        }

    @mcp.tool()
    async def cache_delete(
        key: str,
    ) -> dict[str, str]:
        """
        Delete a value from the cache.

        Args:
            key: Cache key

        Returns:
            Confirmation
        """
        _check_backends()

        await _cache_backend.delete(key)

        return {
            "status": "deleted",
            "key": key,
        }

    # =========================================================================
    # Utility Tools
    # =========================================================================

    @mcp.tool()
    async def get_memory_stats() -> MemoryStats:
        """
        Get statistics about the memory system.

        Returns:
            Memory system statistics
        """
        _check_backends()

        vector_stats = await _vector_backend.get_stats()
        graph_stats = await _graph_backend.get_stats()
        cache_stats = await _cache_backend.get_stats()

        return MemoryStats(
            total_learnings=vector_stats.get("learnings_count", 0),
            total_knowledge=vector_stats.get("knowledge_count", 0),
            total_relationships=graph_stats.get("relationships_count", 0),
            cache_keys=cache_stats.get("keys_count", 0),
            agents_with_learnings=vector_stats.get("agents_count", 0),
        )

    @mcp.tool()
    async def consolidate_learnings(
        agent_id: str | None = None,
        min_occurrences: int = 3,
    ) -> dict[str, Any]:
        """
        Consolidate similar learnings into patterns.

        Args:
            agent_id: Filter by agent (optional)
            min_occurrences: Minimum similar learnings to consolidate (default: 3)

        Returns:
            Consolidation results
        """
        _check_backends()

        # Find clusters of similar learnings
        clusters = await _vector_backend.find_learning_clusters(
            agent_id=agent_id,
            min_cluster_size=min_occurrences,
        )

        consolidated = []
        for cluster in clusters:
            # Create a consolidated pattern
            pattern_id = str(uuid4())
            await _graph_backend.create_pattern_node(
                pattern_id=pattern_id,
                learning_ids=cluster["learning_ids"],
                summary=cluster["summary"],
            )
            consolidated.append(pattern_id)

        return {
            "clusters_found": len(clusters),
            "patterns_created": len(consolidated),
            "pattern_ids": consolidated,
        }

    # =========================================================================
    # News Article Storage Tools
    # =========================================================================

    @mcp.tool()
    async def store_article(
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
        """
        Store a news article for trend analysis.

        Args:
            url: Article URL (unique identifier)
            title: Article title
            source: Source name
            published_at: ISO format publication date
            ai_summary: AI-generated summary
            entities: Extracted entities/topics
            importance_score: Importance score 1-10
            category: Article category
            content_hash: Content hash for deduplication
            ttl_days: Days to retain article (default: 14)

        Returns:
            Stored article info
        """
        _check_backends()

        article_id = str(uuid4())
        timestamp = datetime.utcnow()

        # Parse published_at if provided
        pub_date = None
        if published_at:
            try:
                pub_date = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
            except Exception:
                pub_date = timestamp

        # Store in vector database for entity-based search
        await _vector_backend.store_article(
            article_id=article_id,
            url=url,
            title=title,
            source=source,
            published_at=pub_date,
            stored_at=timestamp,
            ai_summary=ai_summary,
            entities=entities or [],
            importance_score=importance_score,
            category=category,
            content_hash=content_hash,
        )

        # Cache for deduplication (short TTL for URL checks)
        await _cache_backend.set(
            f"article:url:{url}",
            article_id,
            ttl_seconds=ttl_days * 24 * 3600,
        )

        # Also cache content hash if provided
        if content_hash:
            await _cache_backend.set(
                f"article:hash:{content_hash}",
                article_id,
                ttl_seconds=ttl_days * 24 * 3600,
            )

        return {
            "article_id": article_id,
            "url": url,
            "title": title,
            "stored_at": timestamp.isoformat(),
        }

    @mcp.tool()
    async def query_articles(
        start_date: str | None = None,
        end_date: str | None = None,
        source: str | None = None,
        entity: str | None = None,
        category: str | None = None,
        min_importance: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Query stored articles.

        Args:
            start_date: ISO format start date
            end_date: ISO format end date
            source: Filter by source name
            entity: Filter by entity/topic
            category: Filter by category
            min_importance: Minimum importance score
            limit: Maximum results

        Returns:
            List of matching articles
        """
        _check_backends()

        # Parse dates
        start = None
        if start_date:
            try:
                start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            except Exception:
                pass

        end = None
        if end_date:
            try:
                end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            except Exception:
                pass

        articles = await _vector_backend.query_articles(
            start_date=start,
            end_date=end,
            source=source,
            entity=entity,
            category=category,
            min_importance=min_importance,
            limit=limit,
        )

        return articles

    @mcp.tool()
    async def check_article_exists(
        url: str | None = None,
        content_hash: str | None = None,
    ) -> dict[str, Any]:
        """
        Check if an article already exists (for deduplication).

        Args:
            url: Article URL to check
            content_hash: Content hash to check

        Returns:
            Existence status and article_id if found
        """
        _check_backends()

        article_id = None

        if url:
            result = await _cache_backend.get(f"article:url:{url}")
            if result:
                article_id = result

        if not article_id and content_hash:
            result = await _cache_backend.get(f"article:hash:{content_hash}")
            if result:
                article_id = result

        return {
            "exists": article_id is not None,
            "article_id": article_id,
        }

    @mcp.tool()
    async def get_entity_counts(
        start_date: str | None = None,
        end_date: str | None = None,
        min_count: int = 1,
        limit: int = 50,
    ) -> dict[str, int]:
        """
        Get entity mention counts for trend analysis.

        Args:
            start_date: ISO format start date
            end_date: ISO format end date
            min_count: Minimum mention count to include
            limit: Maximum entities to return

        Returns:
            Dict mapping entity -> mention count
        """
        _check_backends()

        # Parse dates
        start = None
        if start_date:
            try:
                start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            except Exception:
                pass

        end = None
        if end_date:
            try:
                end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            except Exception:
                pass

        return await _vector_backend.get_entity_counts(
            start_date=start,
            end_date=end,
            min_count=min_count,
            limit=limit,
        )

    # =========================================================================
    # Trend Snapshot Tools
    # =========================================================================

    @mcp.tool()
    async def store_trend_snapshot(
        snapshot_date: str,
        trends: list[dict[str, Any]],
        emerging_topics: list[str] | None = None,
        declining_topics: list[str] | None = None,
        total_articles: int = 0,
        ttl_days: int = 30,
    ) -> dict[str, Any]:
        """
        Store a trend snapshot for historical comparison.

        Args:
            snapshot_date: ISO format snapshot date
            trends: List of trend dicts with entity, velocity_class, etc.
            emerging_topics: List of emerging topic names
            declining_topics: List of declining topic names
            total_articles: Article count at snapshot time
            ttl_days: Days to retain snapshot (default: 30)

        Returns:
            Stored snapshot info
        """
        _check_backends()

        snapshot_id = str(uuid4())

        # Parse date
        try:
            snap_date = datetime.fromisoformat(snapshot_date.replace("Z", "+00:00"))
        except Exception:
            snap_date = datetime.utcnow()

        # Store in cache with TTL
        snapshot_data = {
            "snapshot_id": snapshot_id,
            "snapshot_date": snap_date.isoformat(),
            "trends": trends,
            "emerging_topics": emerging_topics or [],
            "declining_topics": declining_topics or [],
            "total_articles": total_articles,
        }

        await _cache_backend.set(
            f"trend:snapshot:{snap_date.strftime('%Y-%m-%d')}",
            snapshot_data,
            ttl_seconds=ttl_days * 24 * 3600,
        )

        # Also store latest reference
        await _cache_backend.set(
            "trend:latest",
            snapshot_id,
            ttl_seconds=ttl_days * 24 * 3600,
        )

        return {
            "snapshot_id": snapshot_id,
            "snapshot_date": snap_date.isoformat(),
            "trends_count": len(trends),
        }

    @mcp.tool()
    async def get_trend_snapshot(
        date: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Get a trend snapshot by date.

        Args:
            date: ISO format date (or None for latest)

        Returns:
            Trend snapshot data or None if not found
        """
        _check_backends()

        if date:
            try:
                snap_date = datetime.fromisoformat(date.replace("Z", "+00:00"))
                key = f"trend:snapshot:{snap_date.strftime('%Y-%m-%d')}"
            except Exception:
                return None
        else:
            # Get latest
            key = "trend:latest"
            snapshot_id = await _cache_backend.get(key)
            if not snapshot_id:
                return None

            # Find the actual snapshot by iterating recent dates
            for days_back in range(30):
                check_date = datetime.utcnow()
                from datetime import timedelta

                check_date = check_date - timedelta(days=days_back)
                key = f"trend:snapshot:{check_date.strftime('%Y-%m-%d')}"
                result = await _cache_backend.get(key)
                if result:
                    return result

            return None

        return await _cache_backend.get(key)

    return mcp


def main():
    """Entry point for the Memory MCP server."""
    import sys

    import anyio

    from memory_mcp.transport import TransportConfig, run_server_async

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr,
    )

    # Parse transport config from args
    config = TransportConfig.from_args()

    # Create the server
    mcp = create_server()

    # Run with connection management
    async def run_with_backends():
        try:
            await connect_backends()
            await run_server_async(mcp, config)
        finally:
            await disconnect_backends()

    anyio.run(run_with_backends)


# Alias for backward compatibility
run = main


if __name__ == "__main__":
    run()
