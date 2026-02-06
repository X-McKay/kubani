"""Nexus Memory Client.

Provides a clean, async interface to the memory system. This client
abstracts away the underlying storage backends (Qdrant, PostgreSQL)
and presents a simple API for the Orchestrator activities.

The client can operate in two modes:
1. Direct mode: Connects directly to Qdrant for vector search.
2. MCP mode: Connects via the Memory MCP server (preferred in production).

Usage:
    from kubani.nexus.memory.client import MemoryClient

    client = MemoryClient()
    await client.initialize()

    # Store a memory
    await client.add("User prefers dark mode", user_id="user-1")

    # Search memories
    results = await client.search("UI preferences", user_id="user-1")

    # Get all memories for a user
    all_memories = await client.get_all(user_id="user-1")
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class MemoryClient:
    """Unified memory client for the Nexus agent.

    Supports both direct Qdrant access and MCP server access.
    Falls back gracefully if the memory system is unavailable.

    Attributes:
        mode: 'direct' or 'mcp' — how to access the memory system.
        qdrant_url: URL for direct Qdrant access.
        mcp_url: URL for the Memory MCP server.
    """

    def __init__(
        self,
        mode: str | None = None,
        qdrant_url: str | None = None,
        mcp_url: str | None = None,
    ) -> None:
        self.mode = mode or os.environ.get("MEMORY_MODE", "direct")
        self.qdrant_url = qdrant_url or os.environ.get(
            "QDRANT_URL", "http://localhost:6333"
        )
        self.mcp_url = mcp_url or os.environ.get(
            "MCP_MEMORY_URL", "http://localhost:8083"
        )
        self._qdrant_client: Any = None
        self._collection_name = "nexus_memory"
        self._embedding_dim = 1024  # Default for BGE-large

    async def initialize(self) -> None:
        """Initialize the memory client.

        Creates the Qdrant collection if it doesn't exist (direct mode).
        """
        if self.mode == "direct":
            await self._init_qdrant()
        logger.info(f"Memory client initialized in {self.mode} mode")

    async def _init_qdrant(self) -> None:
        """Initialize direct Qdrant connection."""
        from qdrant_client import AsyncQdrantClient
        from qdrant_client.models import Distance, VectorParams

        self._qdrant_client = AsyncQdrantClient(url=self.qdrant_url)

        # Create collection if it doesn't exist
        collections = await self._qdrant_client.get_collections()
        collection_names = [c.name for c in collections.collections]

        if self._collection_name not in collection_names:
            await self._qdrant_client.create_collection(
                collection_name=self._collection_name,
                vectors_config=VectorParams(
                    size=self._embedding_dim,
                    distance=Distance.COSINE,
                ),
            )
            logger.info(f"Created Qdrant collection: {self._collection_name}")

    async def add(
        self,
        content: str,
        user_id: str = "default",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Store a new memory.

        Args:
            content: The text content to store.
            user_id: The user this memory belongs to.
            metadata: Optional additional metadata.

        Returns:
            The ID of the stored memory.
        """
        if self.mode == "mcp":
            return await self._add_via_mcp(content, user_id, metadata)
        return await self._add_direct(content, user_id, metadata)

    async def _add_direct(
        self,
        content: str,
        user_id: str,
        metadata: dict[str, Any] | None,
    ) -> str:
        """Store a memory directly in Qdrant."""
        import uuid

        from qdrant_client.models import PointStruct

        embedding = await self._get_embedding(content)
        point_id = str(uuid.uuid4())

        payload = {
            "content": content,
            "user_id": user_id,
            **(metadata or {}),
        }

        await self._qdrant_client.upsert(
            collection_name=self._collection_name,
            points=[
                PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload=payload,
                )
            ],
        )

        logger.debug(f"Stored memory {point_id} for user {user_id}")
        return point_id

    async def _add_via_mcp(
        self,
        content: str,
        user_id: str,
        metadata: dict[str, Any] | None,
    ) -> str:
        """Store a memory via the Memory MCP server."""
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.mcp_url}/tools/add_memory",
                json={
                    "content": content,
                    "user_id": user_id,
                    "metadata": metadata or {},
                },
                timeout=10.0,
            )
            response.raise_for_status()
            return response.json().get("memory_id", "")

    async def search(
        self,
        query: str,
        user_id: str = "default",
        limit: int = 5,
    ) -> list[str]:
        """Search for relevant memories.

        Args:
            query: The search query text.
            user_id: Filter memories by user.
            limit: Maximum number of results.

        Returns:
            List of memory content strings, ordered by relevance.
        """
        if self.mode == "mcp":
            return await self._search_via_mcp(query, user_id, limit)
        return await self._search_direct(query, user_id, limit)

    async def _search_direct(
        self, query: str, user_id: str, limit: int
    ) -> list[str]:
        """Search memories directly in Qdrant."""
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        embedding = await self._get_embedding(query)

        results = await self._qdrant_client.search(
            collection_name=self._collection_name,
            query_vector=embedding,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="user_id",
                        match=MatchValue(value=user_id),
                    )
                ]
            ),
            limit=limit,
        )

        return [hit.payload.get("content", "") for hit in results]

    async def _search_via_mcp(
        self, query: str, user_id: str, limit: int
    ) -> list[str]:
        """Search memories via the Memory MCP server."""
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.mcp_url}/tools/search_memory",
                json={
                    "query": query,
                    "user_id": user_id,
                    "limit": limit,
                },
                timeout=10.0,
            )
            response.raise_for_status()
            return response.json().get("memories", [])

    async def get_all(
        self, user_id: str = "default", limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get all memories for a user.

        Args:
            user_id: The user to retrieve memories for.
            limit: Maximum number of memories.

        Returns:
            List of memory dicts with content and metadata.
        """
        if self.mode == "mcp":
            return await self._get_all_via_mcp(user_id, limit)
        return await self._get_all_direct(user_id, limit)

    async def _get_all_direct(
        self, user_id: str, limit: int
    ) -> list[dict[str, Any]]:
        """Get all memories directly from Qdrant."""
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        results, _ = await self._qdrant_client.scroll(
            collection_name=self._collection_name,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="user_id",
                        match=MatchValue(value=user_id),
                    )
                ]
            ),
            limit=limit,
        )

        return [
            {
                "id": str(point.id),
                "content": point.payload.get("content", ""),
                **{
                    k: v
                    for k, v in point.payload.items()
                    if k not in ("content", "user_id")
                },
            }
            for point in results
        ]

    async def _get_all_via_mcp(
        self, user_id: str, limit: int
    ) -> list[dict[str, Any]]:
        """Get all memories via the Memory MCP server."""
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.mcp_url}/tools/get_all_memories",
                json={"user_id": user_id, "limit": limit},
                timeout=10.0,
            )
            response.raise_for_status()
            return response.json().get("memories", [])

    async def delete(self, memory_id: str) -> bool:
        """Delete a specific memory.

        Args:
            memory_id: The ID of the memory to delete.

        Returns:
            True if the memory was deleted.
        """
        if self.mode == "direct":
            await self._qdrant_client.delete(
                collection_name=self._collection_name,
                points_selector=[memory_id],
            )
            return True
        else:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.mcp_url}/tools/delete_memory",
                    json={"memory_id": memory_id},
                    timeout=10.0,
                )
                return response.status_code == 200

    async def _get_embedding(self, text: str) -> list[float]:
        """Get an embedding vector for the given text.

        Uses the configured embeddings API (vLLM or OpenAI-compatible).

        Args:
            text: The text to embed.

        Returns:
            Embedding vector as a list of floats.
        """
        import httpx

        embeddings_url = os.environ.get(
            "EMBEDDINGS_API_URL", "http://localhost:8001/v1"
        )
        embeddings_model = os.environ.get(
            "EMBEDDINGS_MODEL", "BAAI/bge-large-en-v1.5"
        )

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{embeddings_url}/embeddings",
                json={
                    "model": embeddings_model,
                    "input": text,
                },
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            return data["data"][0]["embedding"]
