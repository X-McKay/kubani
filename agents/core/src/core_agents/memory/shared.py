"""
Shared Memory System for Cross-Agent Knowledge.

Provides a unified interface for storing and retrieving knowledge across agents:
- Qdrant: Vector/semantic memory for similarity search
- Neo4j: Graph memory for relationships and reasoning
- Redis: Fast cache and pub/sub for real-time updates

This enables agents to:
- Share learnings and insights
- Query relevant knowledge before executing tasks
- Build on each other's experiences
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class MemoryScope(Enum):
    """Scope of memory entries."""

    GLOBAL = "global"  # Available to all agents
    AGENT = "agent"  # Specific to one agent
    DOMAIN = "domain"  # Specific to a domain (k8s, news, etc.)
    SESSION = "session"  # Temporary session memory


class MemoryType(Enum):
    """Types of memory entries."""

    KNOWLEDGE = "knowledge"  # Learned facts and insights
    SKILL = "skill"  # Skill definitions and usage patterns
    CONTEXT = "context"  # Contextual information
    PREFERENCE = "preference"  # User/system preferences
    HISTORY = "history"  # Historical interactions


@dataclass
class MemoryEntry:
    """A single memory entry."""

    id: str
    type: MemoryType
    scope: MemoryScope
    content: dict[str, Any]
    text: str  # Text representation for embedding
    embedding: list[float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    source_agent: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    access_count: int = 0
    ttl_seconds: int | None = None  # Time to live, None = permanent

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "type": self.type.value,
            "scope": self.scope.value,
            "content": self.content,
            "text": self.text,
            "metadata": self.metadata,
            "tags": self.tags,
            "source_agent": self.source_agent,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "access_count": self.access_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryEntry":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            type=MemoryType(data["type"]),
            scope=MemoryScope(data["scope"]),
            content=data["content"],
            text=data["text"],
            metadata=data.get("metadata", {}),
            tags=data.get("tags", []),
            source_agent=data.get("source_agent", ""),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            access_count=data.get("access_count", 0),
        )


@dataclass
class SearchResult:
    """Result from a memory search."""

    entry: MemoryEntry
    score: float  # Relevance score (0-1)
    source: str  # Which memory system found it


class QdrantMemory:
    """Vector memory using Qdrant."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6333,
        collection: str = "kubani_memory",
    ):
        self.host = host
        self.port = port
        self.collection = collection
        self._client = None

    async def connect(self) -> None:
        """Connect to Qdrant."""
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams

            self._client = QdrantClient(host=self.host, port=self.port)

            # Create collection if it doesn't exist
            collections = self._client.get_collections().collections
            if not any(c.name == self.collection for c in collections):
                self._client.create_collection(
                    collection_name=self.collection,
                    vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
                )
                logger.info(f"Created Qdrant collection: {self.collection}")

        except Exception as e:
            logger.warning(f"Failed to connect to Qdrant: {e}")

    async def store(self, entry: MemoryEntry) -> bool:
        """Store a memory entry."""
        if not self._client or not entry.embedding:
            return False

        try:
            from qdrant_client.models import PointStruct

            point = PointStruct(
                id=hash(entry.id) % (2**63),
                vector=entry.embedding,
                payload=entry.to_dict(),
            )

            self._client.upsert(
                collection_name=self.collection,
                points=[point],
            )
            return True

        except Exception as e:
            logger.warning(f"Failed to store in Qdrant: {e}")
            return False

    async def search(
        self,
        query_embedding: list[float],
        limit: int = 10,
        scope: MemoryScope | None = None,
        memory_type: MemoryType | None = None,
    ) -> list[SearchResult]:
        """Search for similar memories."""
        if not self._client:
            return []

        try:
            from qdrant_client.models import FieldCondition, Filter, MatchValue

            # Build filter
            conditions = []
            if scope:
                conditions.append(FieldCondition(key="scope", match=MatchValue(value=scope.value)))
            if memory_type:
                conditions.append(
                    FieldCondition(key="type", match=MatchValue(value=memory_type.value))
                )

            query_filter = Filter(must=conditions) if conditions else None

            results = self._client.search(
                collection_name=self.collection,
                query_vector=query_embedding,
                limit=limit,
                query_filter=query_filter,
            )

            return [
                SearchResult(
                    entry=MemoryEntry.from_dict(r.payload),
                    score=r.score,
                    source="qdrant",
                )
                for r in results
            ]

        except Exception as e:
            logger.warning(f"Qdrant search failed: {e}")
            return []


class Neo4jMemory:
    """Graph memory using Neo4j."""

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
        try:
            from neo4j import AsyncGraphDatabase

            self._driver = AsyncGraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password),
            )
            logger.info("Connected to Neo4j")

        except Exception as e:
            logger.warning(f"Failed to connect to Neo4j: {e}")

    async def close(self) -> None:
        """Close Neo4j connection."""
        if self._driver:
            await self._driver.close()

    async def store(self, entry: MemoryEntry) -> bool:
        """Store a memory entry as a graph node."""
        if not self._driver:
            return False

        try:
            async with self._driver.session() as session:
                await session.run(
                    """
                    MERGE (m:Memory {id: $id})
                    SET m.type = $type,
                        m.scope = $scope,
                        m.text = $text,
                        m.source_agent = $source_agent,
                        m.created_at = $created_at,
                        m.updated_at = $updated_at
                    """,
                    id=entry.id,
                    type=entry.type.value,
                    scope=entry.scope.value,
                    text=entry.text,
                    source_agent=entry.source_agent,
                    created_at=entry.created_at.isoformat(),
                    updated_at=entry.updated_at.isoformat(),
                )

                # Create relationships to tags
                for tag in entry.tags:
                    await session.run(
                        """
                        MERGE (t:Tag {name: $tag})
                        MERGE (m:Memory {id: $memory_id})
                        MERGE (m)-[:TAGGED]->(t)
                        """,
                        tag=tag,
                        memory_id=entry.id,
                    )

                # Create relationship to source agent
                if entry.source_agent:
                    await session.run(
                        """
                        MERGE (a:Agent {name: $agent})
                        MERGE (m:Memory {id: $memory_id})
                        MERGE (a)-[:CREATED]->(m)
                        """,
                        agent=entry.source_agent,
                        memory_id=entry.id,
                    )

            return True

        except Exception as e:
            logger.warning(f"Failed to store in Neo4j: {e}")
            return False

    async def find_related(
        self,
        entry_id: str,
        relationship: str = "RELATED_TO",
        limit: int = 10,
    ) -> list[MemoryEntry]:
        """Find memories related to a given entry."""
        if not self._driver:
            return []

        try:
            async with self._driver.session() as session:
                result = await session.run(
                    f"""
                    MATCH (m:Memory {{id: $id}})-[:{relationship}]-(related:Memory)
                    RETURN related
                    LIMIT $limit
                    """,
                    id=entry_id,
                    limit=limit,
                )

                entries = []
                async for record in result:
                    node = record["related"]
                    # Reconstruct entry from node properties
                    entries.append(
                        MemoryEntry(
                            id=node["id"],
                            type=MemoryType(node["type"]),
                            scope=MemoryScope(node["scope"]),
                            content={},
                            text=node["text"],
                            source_agent=node.get("source_agent", ""),
                        )
                    )

                return entries

        except Exception as e:
            logger.warning(f"Neo4j query failed: {e}")
            return []

    async def find_by_agent(
        self,
        agent_name: str,
        limit: int = 50,
    ) -> list[MemoryEntry]:
        """Find all memories created by an agent."""
        if not self._driver:
            return []

        try:
            async with self._driver.session() as session:
                result = await session.run(
                    """
                    MATCH (a:Agent {name: $agent})-[:CREATED]->(m:Memory)
                    RETURN m
                    ORDER BY m.created_at DESC
                    LIMIT $limit
                    """,
                    agent=agent_name,
                    limit=limit,
                )

                entries = []
                async for record in result:
                    node = record["m"]
                    entries.append(
                        MemoryEntry(
                            id=node["id"],
                            type=MemoryType(node["type"]),
                            scope=MemoryScope(node["scope"]),
                            content={},
                            text=node["text"],
                            source_agent=node.get("source_agent", ""),
                        )
                    )

                return entries

        except Exception as e:
            logger.warning(f"Neo4j query failed: {e}")
            return []

    async def create_relationship(
        self,
        from_id: str,
        to_id: str,
        relationship: str,
        properties: dict[str, Any] | None = None,
    ) -> bool:
        """Create a relationship between two memory entries."""
        if not self._driver:
            return False

        try:
            async with self._driver.session() as session:
                props_str = ""
                if properties:
                    props_str = " {" + ", ".join(f"{k}: ${k}" for k in properties) + "}"

                await session.run(
                    f"""
                    MATCH (a:Memory {{id: $from_id}})
                    MATCH (b:Memory {{id: $to_id}})
                    MERGE (a)-[r:{relationship}{props_str}]->(b)
                    """,
                    from_id=from_id,
                    to_id=to_id,
                    **(properties or {}),
                )

            return True

        except Exception as e:
            logger.warning(f"Failed to create relationship: {e}")
            return False


class RedisCache:
    """Fast cache using Redis."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
    ):
        self.host = host
        self.port = port
        self.db = db
        self._client = None

    async def connect(self) -> None:
        """Connect to Redis."""
        try:
            import redis.asyncio as redis

            self._client = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                decode_responses=True,
            )
            await self._client.ping()
            logger.info("Connected to Redis")

        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}")

    async def close(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.close()

    async def get(self, key: str) -> MemoryEntry | None:
        """Get a memory entry from cache."""
        if not self._client:
            return None

        try:
            data = await self._client.get(f"memory:{key}")
            if data:
                return MemoryEntry.from_dict(json.loads(data))
        except Exception as e:
            logger.warning(f"Redis get failed: {e}")

        return None

    async def set(
        self,
        entry: MemoryEntry,
        ttl_seconds: int | None = None,
    ) -> bool:
        """Set a memory entry in cache."""
        if not self._client:
            return False

        try:
            key = f"memory:{entry.id}"
            data = json.dumps(entry.to_dict())

            if ttl_seconds:
                await self._client.setex(key, ttl_seconds, data)
            else:
                await self._client.set(key, data)

            return True

        except Exception as e:
            logger.warning(f"Redis set failed: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete a memory entry from cache."""
        if not self._client:
            return False

        try:
            await self._client.delete(f"memory:{key}")
            return True
        except Exception as e:
            logger.warning(f"Redis delete failed: {e}")
            return False

    async def publish(self, channel: str, message: dict[str, Any]) -> bool:
        """Publish a message to a channel."""
        if not self._client:
            return False

        try:
            await self._client.publish(channel, json.dumps(message))
            return True
        except Exception as e:
            logger.warning(f"Redis publish failed: {e}")
            return False


class SharedMemory:
    """
    Unified shared memory system.

    Combines Qdrant, Neo4j, and Redis for comprehensive memory management.
    """

    def __init__(
        self,
        qdrant_host: str = "localhost",
        qdrant_port: int = 6333,
        neo4j_uri: str = "bolt://localhost:7687",
        neo4j_user: str = "neo4j",
        neo4j_password: str = "",
        redis_host: str = "localhost",
        redis_port: int = 6379,
        embeddings_api_url: str = "http://localhost:8001/v1",
    ):
        self.qdrant = QdrantMemory(qdrant_host, qdrant_port)
        self.neo4j = Neo4jMemory(neo4j_uri, neo4j_user, neo4j_password)
        self.redis = RedisCache(redis_host, redis_port)
        self.embeddings_api_url = embeddings_api_url

    async def connect(self) -> None:
        """Connect to all memory systems."""
        await asyncio.gather(
            self.qdrant.connect(),
            self.neo4j.connect(),
            self.redis.connect(),
        )

    async def close(self) -> None:
        """Close all connections."""
        await asyncio.gather(
            self.neo4j.close(),
            self.redis.close(),
        )

    async def store(
        self,
        entry: MemoryEntry,
        generate_embedding: bool = True,
    ) -> bool:
        """Store a memory entry in all relevant systems."""
        # Generate embedding if needed
        if generate_embedding and not entry.embedding:
            entry.embedding = await self._get_embedding(entry.text)

        # Store in all systems
        results = await asyncio.gather(
            self.qdrant.store(entry),
            self.neo4j.store(entry),
            self.redis.set(entry, entry.ttl_seconds),
            return_exceptions=True,
        )

        # Publish update event
        await self.redis.publish(
            "memory:updates",
            {
                "action": "store",
                "entry_id": entry.id,
                "type": entry.type.value,
                "source_agent": entry.source_agent,
            },
        )

        return any(r is True for r in results)

    async def search(
        self,
        query: str,
        limit: int = 10,
        scope: MemoryScope | None = None,
        memory_type: MemoryType | None = None,
    ) -> list[SearchResult]:
        """Search for relevant memories."""
        # Get query embedding
        embedding = await self._get_embedding(query)
        if not embedding:
            return []

        # Search Qdrant
        return await self.qdrant.search(
            query_embedding=embedding,
            limit=limit,
            scope=scope,
            memory_type=memory_type,
        )

    async def get(self, entry_id: str) -> MemoryEntry | None:
        """Get a specific memory entry."""
        # Try cache first
        entry = await self.redis.get(entry_id)
        if entry:
            entry.access_count += 1
            return entry

        # Would need to query Qdrant/Neo4j for full entry
        return None

    async def get_agent_knowledge(
        self,
        agent_name: str,
        limit: int = 50,
    ) -> list[MemoryEntry]:
        """Get all knowledge for an agent."""
        return await self.neo4j.find_by_agent(agent_name, limit)

    async def get_related(
        self,
        entry_id: str,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        """Get memories related to a given entry."""
        return await self.neo4j.find_related(entry_id, limit=limit)

    async def link(
        self,
        from_id: str,
        to_id: str,
        relationship: str = "RELATED_TO",
    ) -> bool:
        """Create a relationship between memories."""
        return await self.neo4j.create_relationship(from_id, to_id, relationship)

    async def _get_embedding(self, text: str) -> list[float]:
        """Get embedding for text."""
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.embeddings_api_url}/embeddings",
                    json={"input": text, "model": "BAAI/bge-large-en-v1.5"},
                    timeout=30.0,
                )
                if response.status_code == 200:
                    data = response.json()
                    return data["data"][0]["embedding"]
        except Exception as e:
            logger.warning(f"Failed to get embedding: {e}")

        return []


# Singleton instance
_shared_memory: SharedMemory | None = None


def get_shared_memory(**kwargs) -> SharedMemory:
    """Get or create the shared memory singleton."""
    global _shared_memory
    if _shared_memory is None:
        _shared_memory = SharedMemory(**kwargs)
    return _shared_memory
