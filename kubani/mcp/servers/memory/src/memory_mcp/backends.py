"""
Memory MCP Server backend implementations.

Provides unified interfaces to Qdrant, Neo4j, and Redis.
"""

import json
import logging
import os
from datetime import datetime
from typing import Any
from uuid import uuid4

from memory_mcp.models import (
    KnowledgeEntry,
    LearningEntry,
    MemoryObject,
    MemoryRelation,
    RelationshipResult,
)

logger = logging.getLogger(__name__)


class VectorBackend:
    """Qdrant vector database backend for semantic search."""

    LEARNINGS_COLLECTION = "kubani_learnings"
    KNOWLEDGE_COLLECTION = "kubani_knowledge"
    ARTICLES_COLLECTION = "kubani_articles"
    VECTOR_SIZE = int(os.environ.get("EMBEDDING_VECTOR_SIZE", "1024"))  # Qwen3-Embedding-0.6B

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6333,
        api_key: str | None = None,
    ):
        self.host = host
        self.port = port
        self.api_key = api_key
        self._client = None
        self._embedder = None

    async def connect(self) -> None:
        """Connect to Qdrant."""
        from qdrant_client import AsyncQdrantClient
        from qdrant_client.models import Distance, VectorParams

        if self.api_key:
            self._client = AsyncQdrantClient(
                host=self.host,
                port=self.port,
                api_key=self.api_key,
                https=False,  # Internal cluster communication
                check_compatibility=False,  # Allow version mismatch
                timeout=60,  # Longer timeout for slow operations
            )
        else:
            self._client = AsyncQdrantClient(
                host=self.host,
                port=self.port,
                https=False,
                check_compatibility=False,  # Allow version mismatch
                timeout=60,  # Longer timeout for slow operations
            )

        # Ensure collections exist
        collections = await self._client.get_collections()
        collection_names = [c.name for c in collections.collections]

        for collection in [
            self.LEARNINGS_COLLECTION,
            self.KNOWLEDGE_COLLECTION,
            self.ARTICLES_COLLECTION,
        ]:
            if collection not in collection_names:
                await self._client.create_collection(
                    collection_name=collection,
                    vectors_config=VectorParams(
                        size=self.VECTOR_SIZE,
                        distance=Distance.COSINE,
                    ),
                )
                logger.info(f"Created collection: {collection}")

    async def disconnect(self) -> None:
        """Disconnect from Qdrant."""
        if self._client:
            await self._client.close()
            self._client = None

    async def _get_embedding(self, text: str) -> list[float]:
        """Get embedding for text using the configured embedder."""
        import os

        import httpx

        # Use the embeddings API
        api_url = os.environ.get("EMBEDDINGS_API_URL", "http://localhost:8001/v1")
        model = os.environ.get("EMBEDDINGS_MODEL", "text-embedding-ada-002")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{api_url}/embeddings",
                json={"input": text, "model": model},
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            return data["data"][0]["embedding"]

    async def store_learning(
        self,
        learning_id: str,
        agent_id: str,
        learning_type: str,
        content: str,
        context: dict[str, Any],
        confidence: float,
        tags: list[str],
        timestamp: datetime,
    ) -> None:
        """Store a learning in the vector database."""
        from qdrant_client.models import PointStruct

        embedding = await self._get_embedding(content)

        await self._client.upsert(
            collection_name=self.LEARNINGS_COLLECTION,
            points=[
                PointStruct(
                    id=learning_id,
                    vector=embedding,
                    payload={
                        "agent_id": agent_id,
                        "learning_type": learning_type,
                        "content": content,
                        "context": context,
                        "confidence": confidence,
                        "tags": tags,
                        "timestamp": timestamp.isoformat(),
                    },
                )
            ],
        )

    async def search_learnings(
        self,
        query: str,
        agent_id: str | None = None,
        learning_type: str | None = None,
        min_confidence: float = 0.5,
        limit: int = 10,
    ) -> list[LearningEntry]:
        """Search learnings using semantic similarity."""
        from qdrant_client.models import FieldCondition, Filter, MatchValue, Range

        embedding = await self._get_embedding(query)

        # Build filter
        must_conditions = [
            FieldCondition(
                key="confidence",
                range=Range(gte=min_confidence),
            )
        ]

        if agent_id:
            must_conditions.append(FieldCondition(key="agent_id", match=MatchValue(value=agent_id)))

        if learning_type:
            must_conditions.append(
                FieldCondition(key="learning_type", match=MatchValue(value=learning_type))
            )

        results = await self._client.query_points(
            collection_name=self.LEARNINGS_COLLECTION,
            query=embedding,
            limit=limit,
            query_filter=Filter(must=must_conditions) if must_conditions else None,
        )

        return [
            LearningEntry(
                learning_id=str(r.id),
                agent_id=r.payload["agent_id"],
                learning_type=r.payload["learning_type"],
                content=r.payload["content"],
                context=r.payload.get("context", {}),
                confidence=r.payload["confidence"],
                tags=r.payload.get("tags", []),
                timestamp=datetime.fromisoformat(r.payload["timestamp"]),
                relevance_score=r.score,
            )
            for r in results.points
        ]

    async def get_agent_learnings(
        self,
        agent_id: str,
        learning_type: str | None = None,
        limit: int = 20,
    ) -> list[LearningEntry]:
        """Get learnings for a specific agent."""
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        must_conditions = [FieldCondition(key="agent_id", match=MatchValue(value=agent_id))]

        if learning_type:
            must_conditions.append(
                FieldCondition(key="learning_type", match=MatchValue(value=learning_type))
            )

        records, _ = await self._client.scroll(
            collection_name=self.LEARNINGS_COLLECTION,
            limit=limit,
            scroll_filter=Filter(must=must_conditions),
            with_payload=True,
        )

        return [
            LearningEntry(
                learning_id=str(r.id),
                agent_id=r.payload["agent_id"],
                learning_type=r.payload["learning_type"],
                content=r.payload["content"],
                context=r.payload.get("context", {}),
                confidence=r.payload["confidence"],
                tags=r.payload.get("tags", []),
                timestamp=datetime.fromisoformat(r.payload["timestamp"]),
            )
            for r in records
        ]

    async def store_knowledge(
        self,
        knowledge_id: str,
        topic: str,
        content: str,
        source: str,
        metadata: dict[str, Any],
        timestamp: datetime,
    ) -> None:
        """Store knowledge in the vector database."""
        from qdrant_client.models import PointStruct

        embedding = await self._get_embedding(f"{topic}: {content}")

        await self._client.upsert(
            collection_name=self.KNOWLEDGE_COLLECTION,
            points=[
                PointStruct(
                    id=knowledge_id,
                    vector=embedding,
                    payload={
                        "topic": topic,
                        "content": content,
                        "source": source,
                        "metadata": metadata,
                        "timestamp": timestamp.isoformat(),
                    },
                )
            ],
        )

    async def search_knowledge(
        self,
        query: str,
        topic_prefix: str | None = None,
        limit: int = 10,
    ) -> list[KnowledgeEntry]:
        """Search knowledge using semantic similarity."""
        from qdrant_client.models import FieldCondition, Filter, MatchText

        embedding = await self._get_embedding(query)

        query_filter = None
        if topic_prefix:
            query_filter = Filter(
                must=[
                    FieldCondition(
                        key="topic",
                        match=MatchText(text=topic_prefix),
                    )
                ]
            )

        results = await self._client.query_points(
            collection_name=self.KNOWLEDGE_COLLECTION,
            query=embedding,
            limit=limit,
            query_filter=query_filter,
        )

        return [
            KnowledgeEntry(
                knowledge_id=str(r.id),
                topic=r.payload["topic"],
                content=r.payload["content"],
                source=r.payload["source"],
                metadata=r.payload.get("metadata", {}),
                timestamp=datetime.fromisoformat(r.payload["timestamp"]),
                relevance_score=r.score,
            )
            for r in results.points
        ]

    async def find_learning_clusters(
        self,
        agent_id: str | None = None,
        min_cluster_size: int = 3,
    ) -> list[dict[str, Any]]:
        """Find clusters of similar learnings."""
        # Simplified clustering - in production, use proper clustering
        _learnings = await self.get_agent_learnings(agent_id, limit=100) if agent_id else []
        # Return empty for now - full implementation would use clustering algorithm
        return []

    async def get_stats(self) -> dict[str, int]:
        """Get vector database statistics."""
        learnings_info = await self._client.get_collection(self.LEARNINGS_COLLECTION)
        knowledge_info = await self._client.get_collection(self.KNOWLEDGE_COLLECTION)

        return {
            "learnings_count": learnings_info.points_count or 0,
            "knowledge_count": knowledge_info.points_count or 0,
            "agents_count": 0,  # Would need aggregation query
        }

    # =========================================================================
    # Article Storage Methods
    # =========================================================================

    async def store_article(
        self,
        article_id: str,
        url: str,
        title: str,
        source: str,
        published_at: datetime | None,
        stored_at: datetime,
        ai_summary: str,
        entities: list[str],
        importance_score: int,
        category: str,
        content_hash: str,
    ) -> None:
        """Store an article in the vector database."""
        from qdrant_client.models import PointStruct

        # Create embedding from title + summary + entities
        text_for_embedding = f"{title}. {ai_summary}. {' '.join(entities)}"
        embedding = await self._get_embedding(text_for_embedding[:1000])

        await self._client.upsert(
            collection_name=self.ARTICLES_COLLECTION,
            points=[
                PointStruct(
                    id=article_id,
                    vector=embedding,
                    payload={
                        "url": url,
                        "title": title,
                        "source": source,
                        "published_at": published_at.isoformat() if published_at else None,
                        "stored_at": stored_at.isoformat(),
                        "ai_summary": ai_summary,
                        "entities": entities,
                        "importance_score": importance_score,
                        "category": category,
                        "content_hash": content_hash,
                    },
                )
            ],
        )

    async def query_articles(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        source: str | None = None,
        entity: str | None = None,
        category: str | None = None,
        min_importance: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query stored articles by various filters."""
        from qdrant_client.models import FieldCondition, Filter, MatchValue, Range

        must_conditions = []

        if min_importance > 0:
            must_conditions.append(
                FieldCondition(
                    key="importance_score",
                    range=Range(gte=min_importance),
                )
            )

        if source:
            must_conditions.append(FieldCondition(key="source", match=MatchValue(value=source)))

        if category:
            must_conditions.append(FieldCondition(key="category", match=MatchValue(value=category)))

        # Note: Date filtering requires indexed datetime field
        # For now, we filter in memory after fetching

        records, _ = await self._client.scroll(
            collection_name=self.ARTICLES_COLLECTION,
            limit=limit,
            scroll_filter=Filter(must=must_conditions) if must_conditions else None,
            with_payload=True,
        )

        articles = []
        for r in records:
            payload = r.payload

            # Apply date filtering in memory
            if start_date or end_date:
                stored_at_str = payload.get("stored_at")
                if stored_at_str:
                    try:
                        stored_at = datetime.fromisoformat(stored_at_str)
                        if start_date and stored_at < start_date:
                            continue
                        if end_date and stored_at > end_date:
                            continue
                    except Exception:
                        pass

            # Apply entity filter in memory (entities is a list)
            if entity:
                entities_list = payload.get("entities", [])
                if entity.lower() not in [e.lower() for e in entities_list]:
                    continue

            articles.append(
                {
                    "article_id": str(r.id),
                    "url": payload.get("url", ""),
                    "title": payload.get("title", ""),
                    "source": payload.get("source", ""),
                    "published_at": payload.get("published_at"),
                    "stored_at": payload.get("stored_at"),
                    "ai_summary": payload.get("ai_summary", ""),
                    "entities": payload.get("entities", []),
                    "importance_score": payload.get("importance_score", 5),
                    "category": payload.get("category", "general"),
                }
            )

        return articles

    async def get_entity_counts(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        min_count: int = 1,
        limit: int = 50,
    ) -> dict[str, int]:
        """Get entity mention counts from stored articles."""
        from collections import Counter

        # Query all articles in date range
        articles = await self.query_articles(
            start_date=start_date,
            end_date=end_date,
            limit=1000,  # Get more for accurate counting
        )

        # Count entities
        entity_counts: Counter = Counter()
        for article in articles:
            for entity in article.get("entities", []):
                entity_lower = entity.strip().lower()
                if len(entity_lower) >= 2:
                    entity_counts[entity_lower] += 1

        # Filter by min_count and limit
        filtered = {
            entity: count
            for entity, count in entity_counts.most_common(limit)
            if count >= min_count
        }

        return filtered

    # =========================================================================
    # Generic Memory Interface Methods
    # =========================================================================

    GENERIC_COLLECTION = "kubani_memory"

    async def ensure_generic_collection(self) -> None:
        """Ensure the generic memory collection exists."""
        from qdrant_client.models import Distance, VectorParams

        collections = await self._client.get_collections()
        collection_names = [c.name for c in collections.collections]

        if self.GENERIC_COLLECTION not in collection_names:
            await self._client.create_collection(
                collection_name=self.GENERIC_COLLECTION,
                vectors_config=VectorParams(
                    size=self.VECTOR_SIZE,
                    distance=Distance.COSINE,
                ),
            )
            logger.info(f"Created collection: {self.GENERIC_COLLECTION}")

    async def store_object(
        self,
        object_id: str,
        object_type: str,
        namespace: str,
        data: dict,
        metadata: dict,
        created_at: datetime,
    ) -> None:
        """Store a generic memory object in the vector database."""
        from qdrant_client.models import PointStruct

        await self.ensure_generic_collection()

        # Create text for embedding from data
        text_parts = []
        for key, value in data.items():
            if isinstance(value, str):
                text_parts.append(value)
            elif isinstance(value, list) and value and isinstance(value[0], str):
                text_parts.extend(value)
        text_for_embedding = " ".join(text_parts)[:2000] or f"{object_type} {namespace}"

        embedding = await self._get_embedding(text_for_embedding)

        await self._client.upsert(
            collection_name=self.GENERIC_COLLECTION,
            points=[
                PointStruct(
                    id=object_id,
                    vector=embedding,
                    payload={
                        "type": object_type,
                        "namespace": namespace,
                        "data": data,
                        "metadata": metadata,
                        "created_at": created_at.isoformat(),
                    },
                )
            ],
        )

    async def search_objects(
        self,
        query: str,
        object_type: str | None = None,
        namespace: str | None = None,
        filters: dict | None = None,
        limit: int = 10,
    ) -> list[MemoryObject]:
        """Search for memory objects using semantic similarity."""
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        await self.ensure_generic_collection()

        embedding = await self._get_embedding(query)

        # Build filter conditions
        must_conditions = []
        if object_type:
            must_conditions.append(
                FieldCondition(key="type", match=MatchValue(value=object_type))
            )
        if namespace:
            must_conditions.append(
                FieldCondition(key="namespace", match=MatchValue(value=namespace))
            )

        query_filter = Filter(must=must_conditions) if must_conditions else None

        results = await self._client.query_points(
            collection_name=self.GENERIC_COLLECTION,
            query=embedding,
            limit=limit,
            query_filter=query_filter,
        )

        objects = []
        for r in results.points:
            payload = r.payload

            # Apply custom filters in memory if provided
            if filters:
                skip = False
                for key, value in filters.items():
                    data_value = payload.get("data", {}).get(key)
                    if data_value != value:
                        skip = True
                        break
                if skip:
                    continue

            objects.append(
                MemoryObject(
                    id=str(r.id),
                    type=payload.get("type", ""),
                    namespace=payload.get("namespace", ""),
                    data=payload.get("data", {}),
                    metadata=payload.get("metadata", {}),
                    created_at=datetime.fromisoformat(payload.get("created_at", datetime.utcnow().isoformat())),
                    relations=[],  # Relations are fetched from graph backend
                    relevance_score=r.score,
                )
            )

        return objects

    async def get_object(self, object_id: str) -> MemoryObject | None:
        """Get a memory object by ID."""
        await self.ensure_generic_collection()

        try:
            results = await self._client.retrieve(
                collection_name=self.GENERIC_COLLECTION,
                ids=[object_id],
                with_payload=True,
            )

            if not results:
                return None

            r = results[0]
            payload = r.payload

            return MemoryObject(
                id=str(r.id),
                type=payload.get("type", ""),
                namespace=payload.get("namespace", ""),
                data=payload.get("data", {}),
                metadata=payload.get("metadata", {}),
                created_at=datetime.fromisoformat(payload.get("created_at", datetime.utcnow().isoformat())),
                relations=[],
            )
        except Exception:
            return None

    async def list_objects(
        self,
        object_type: str | None = None,
        namespace: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MemoryObject]:
        """List memory objects with optional filtering."""
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        await self.ensure_generic_collection()

        # Build filter conditions
        must_conditions = []
        if object_type:
            must_conditions.append(
                FieldCondition(key="type", match=MatchValue(value=object_type))
            )
        if namespace:
            must_conditions.append(
                FieldCondition(key="namespace", match=MatchValue(value=namespace))
            )

        scroll_filter = Filter(must=must_conditions) if must_conditions else None

        records, _ = await self._client.scroll(
            collection_name=self.GENERIC_COLLECTION,
            limit=limit,
            offset=offset,
            scroll_filter=scroll_filter,
            with_payload=True,
        )

        return [
            MemoryObject(
                id=str(r.id),
                type=r.payload.get("type", ""),
                namespace=r.payload.get("namespace", ""),
                data=r.payload.get("data", {}),
                metadata=r.payload.get("metadata", {}),
                created_at=datetime.fromisoformat(r.payload.get("created_at", datetime.utcnow().isoformat())),
                relations=[],
            )
            for r in records
        ]


class GraphBackend:
    """Neo4j graph database backend for relationships."""

    def __init__(
        self,
        uri: str = "bolt://localhost:7687",
        user: str = "neo4j",
        password: str = "",
    ):
        self.uri = uri
        self.user = user
        self.password = password
        self._driver = None

    async def connect(self) -> None:
        """Connect to Neo4j."""
        from neo4j import AsyncGraphDatabase

        self._driver = AsyncGraphDatabase.driver(
            self.uri,
            auth=(self.user, self.password) if self.password else None,
        )
        # Verify connection
        async with self._driver.session() as session:
            await session.run("RETURN 1")
        logger.info("Connected to Neo4j")

    async def disconnect(self) -> None:
        """Disconnect from Neo4j."""
        if self._driver:
            await self._driver.close()
            self._driver = None

    async def create_learning_node(
        self,
        learning_id: str,
        agent_id: str,
        learning_type: str,
        tags: list[str],
    ) -> None:
        """Create a learning node in the graph."""
        async with self._driver.session() as session:
            await session.run(
                """
                MERGE (l:Learning {id: $learning_id})
                SET l.agent_id = $agent_id, l.type = $learning_type, l.tags = $tags
                MERGE (a:Agent {id: $agent_id})
                MERGE (a)-[:LEARNED]->(l)
                """,
                learning_id=learning_id,
                agent_id=agent_id,
                learning_type=learning_type,
                tags=tags,
            )

    async def create_knowledge_node(
        self,
        knowledge_id: str,
        topic: str,
        source: str,
    ) -> None:
        """Create a knowledge node in the graph."""
        async with self._driver.session() as session:
            await session.run(
                """
                MERGE (k:Knowledge {id: $knowledge_id})
                SET k.topic = $topic, k.source = $source
                MERGE (t:Topic {path: $topic})
                MERGE (t)-[:CONTAINS]->(k)
                """,
                knowledge_id=knowledge_id,
                topic=topic,
                source=source,
            )

    async def create_relationship(
        self,
        from_topic: str,
        to_topic: str,
        relationship_type: str,
        properties: dict[str, Any] | None = None,
    ) -> str:
        """Create a relationship between entities."""
        rel_id = str(uuid4())
        async with self._driver.session() as session:
            await session.run(
                f"""
                MERGE (a {{path: $from_topic}})
                MERGE (b {{path: $to_topic}})
                MERGE (a)-[r:{relationship_type} {{id: $rel_id}}]->(b)
                SET r += $properties
                """,
                from_topic=from_topic,
                to_topic=to_topic,
                rel_id=rel_id,
                properties=properties or {},
            )
        return rel_id

    async def get_subgraph(
        self,
        topic: str,
        depth: int = 2,
    ) -> dict[str, Any]:
        """Get the subgraph around a topic."""
        async with self._driver.session() as session:
            result = await session.run(
                """
                MATCH path = (t:Topic {path: $topic})-[*1..$depth]-(related)
                RETURN path
                LIMIT 100
                """,
                topic=topic,
                depth=depth,
            )
            records = await result.data()

        # Simplified - return node/edge structure
        return {
            "center": topic,
            "depth": depth,
            "paths": len(records),
        }

    async def get_related_topics(
        self,
        topic: str,
        relationship_type: str | None = None,
        limit: int = 10,
    ) -> list[str]:
        """Get topics related to a given topic."""
        query = """
            MATCH (t:Topic {path: $topic})-[r]-(related:Topic)
            RETURN DISTINCT related.path as path
            LIMIT $limit
        """
        if relationship_type:
            query = f"""
                MATCH (t:Topic {{path: $topic}})-[r:{relationship_type}]-(related:Topic)
                RETURN DISTINCT related.path as path
                LIMIT $limit
            """

        async with self._driver.session() as session:
            result = await session.run(query, topic=topic, limit=limit)
            records = await result.data()

        return [r["path"] for r in records if r.get("path")]

    async def get_relationships(
        self,
        entity: str,
        direction: str = "both",
        relationship_type: str | None = None,
    ) -> list[RelationshipResult]:
        """Get relationships for an entity."""
        # Simplified query
        async with self._driver.session() as session:
            result = await session.run(
                """
                MATCH (n {path: $entity})-[r]-(m)
                RETURN type(r) as type, r.id as id, n.path as from, m.path as to
                LIMIT 50
                """,
                entity=entity,
            )
            records = await result.data()

        return [
            RelationshipResult(
                relationship_id=r.get("id", ""),
                from_entity=r.get("from", ""),
                to_entity=r.get("to", ""),
                relationship_type=r.get("type", ""),
            )
            for r in records
        ]

    async def create_pattern_node(
        self,
        pattern_id: str,
        learning_ids: list[str],
        summary: str,
    ) -> None:
        """Create a pattern node from consolidated learnings."""
        async with self._driver.session() as session:
            await session.run(
                """
                CREATE (p:Pattern {id: $pattern_id, summary: $summary})
                WITH p
                UNWIND $learning_ids as lid
                MATCH (l:Learning {id: lid})
                MERGE (l)-[:SUPPORTS]->(p)
                """,
                pattern_id=pattern_id,
                learning_ids=learning_ids,
                summary=summary,
            )

    async def get_stats(self) -> dict[str, int]:
        """Get graph database statistics."""
        async with self._driver.session() as session:
            result = await session.run(
                """
                MATCH ()-[r]->()
                RETURN count(r) as relationships
                """
            )
            data = await result.single()

        return {
            "relationships_count": data["relationships"] if data else 0,
        }

    # =========================================================================
    # Generic Memory Interface Methods
    # =========================================================================

    async def create_memory_node(
        self,
        object_id: str,
        object_type: str,
        namespace: str,
    ) -> None:
        """Create a memory object node in the graph."""
        async with self._driver.session() as session:
            await session.run(
                """
                MERGE (m:MemoryObject {id: $object_id})
                SET m.type = $object_type, m.namespace = $namespace
                """,
                object_id=object_id,
                object_type=object_type,
                namespace=namespace,
            )

    async def create_memory_relation(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
    ) -> bool:
        """Create a relation between two memory objects. Returns True if newly created."""
        async with self._driver.session() as session:
            # Check if relation already exists
            result = await session.run(
                f"""
                MATCH (s:MemoryObject {{id: $source_id}})-[r:{relation_type}]->(t:MemoryObject {{id: $target_id}})
                RETURN count(r) as count
                """,
                source_id=source_id,
                target_id=target_id,
            )
            data = await result.single()
            exists = data["count"] > 0 if data else False

            if not exists:
                await session.run(
                    f"""
                    MERGE (s:MemoryObject {{id: $source_id}})
                    MERGE (t:MemoryObject {{id: $target_id}})
                    MERGE (s)-[r:{relation_type}]->(t)
                    """,
                    source_id=source_id,
                    target_id=target_id,
                )

            return not exists

    async def get_object_relations(
        self,
        object_id: str,
        direction: str = "outgoing",
    ) -> list[MemoryRelation]:
        """Get relations for a memory object."""
        if direction == "outgoing":
            query = """
                MATCH (s:MemoryObject {id: $object_id})-[r]->(t:MemoryObject)
                RETURN t.id as target_id, type(r) as relation_type
            """
        elif direction == "incoming":
            query = """
                MATCH (s:MemoryObject)-[r]->(t:MemoryObject {id: $object_id})
                RETURN s.id as target_id, type(r) as relation_type
            """
        else:  # both
            query = """
                MATCH (s:MemoryObject {id: $object_id})-[r]-(t:MemoryObject)
                RETURN t.id as target_id, type(r) as relation_type
            """

        async with self._driver.session() as session:
            result = await session.run(query, object_id=object_id)
            records = await result.data()

        return [
            MemoryRelation(
                target_id=r["target_id"],
                relation_type=r["relation_type"],
            )
            for r in records
            if r.get("target_id")
        ]


class CacheBackend:
    """Redis cache backend for fast access."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        password: str | None = None,
    ):
        self.host = host
        self.port = port
        self.password = password
        self._client = None

    async def connect(self) -> None:
        """Connect to Redis."""
        import redis.asyncio as redis

        self._client = redis.Redis(
            host=self.host,
            port=self.port,
            password=self.password,
            decode_responses=True,
        )
        # Verify connection
        await self._client.ping()
        logger.info("Connected to Redis")

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self._client:
            await self._client.close()
            self._client = None

    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
    ) -> None:
        """Set a value in the cache."""
        serialized = json.dumps(value)
        if ttl_seconds:
            await self._client.setex(key, ttl_seconds, serialized)
        else:
            await self._client.set(key, serialized)

    async def get(self, key: str) -> Any | None:
        """Get a value from the cache."""
        value = await self._client.get(key)
        if value:
            return json.loads(value)
        return None

    async def delete(self, key: str) -> None:
        """Delete a value from the cache."""
        await self._client.delete(key)

    async def cache_recent_learning(
        self,
        agent_id: str,
        learning_id: str,
    ) -> None:
        """Cache a recent learning for an agent."""
        key = f"agent:{agent_id}:recent_learnings"
        await self._client.lpush(key, learning_id)
        await self._client.ltrim(key, 0, 99)  # Keep last 100

    async def get_stats(self) -> dict[str, int]:
        """Get cache statistics."""
        info = await self._client.info("keyspace")
        keys_count = 0
        for db_info in info.values():
            if isinstance(db_info, dict):
                keys_count += db_info.get("keys", 0)

        return {
            "keys_count": keys_count,
        }

    # =========================================================================
    # Deduplication Methods (for generic memory interface)
    # =========================================================================

    async def check_seen(self, key: str, namespace: str) -> bool:
        """Check if a key has been seen in the given namespace."""
        cache_key = f"seen:{namespace}:{key}"
        exists = await self._client.exists(cache_key)
        return exists > 0

    async def mark_seen(
        self,
        key: str,
        namespace: str,
        ttl_seconds: int | None = None,
    ) -> None:
        """Mark a key as seen in the given namespace."""
        cache_key = f"seen:{namespace}:{key}"
        if ttl_seconds:
            await self._client.setex(cache_key, ttl_seconds, "1")
        else:
            await self._client.set(cache_key, "1")
