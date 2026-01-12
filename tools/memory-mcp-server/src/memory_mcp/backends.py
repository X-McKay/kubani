"""
Memory MCP Server backend implementations.

Provides unified interfaces to Qdrant, Neo4j, and Redis.
"""

import json
import logging
from datetime import datetime
from typing import Any
from uuid import uuid4

from memory_mcp.models import KnowledgeEntry, LearningEntry, RelationshipResult

logger = logging.getLogger(__name__)


class VectorBackend:
    """Qdrant vector database backend for semantic search."""

    LEARNINGS_COLLECTION = "kubani_learnings"
    KNOWLEDGE_COLLECTION = "kubani_knowledge"
    VECTOR_SIZE = 1536  # OpenAI ada-002

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

        for collection in [self.LEARNINGS_COLLECTION, self.KNOWLEDGE_COLLECTION]:
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

        results = await self._client.search(
            collection_name=self.LEARNINGS_COLLECTION,
            query_vector=embedding,
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
            for r in results
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

        results = await self._client.search(
            collection_name=self.KNOWLEDGE_COLLECTION,
            query_vector=embedding,
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
            for r in results
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
