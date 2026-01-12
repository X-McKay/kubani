"""
Skill library implementation.

Provides storage and semantic retrieval of skills using Qdrant.
Supports optional sync to centralized registry for cross-agent visibility.
"""

import asyncio
import logging
import os
import uuid
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from core_agents.skills.schema import Skill, SkillCategory, SkillDomain, SkillOutcome

if TYPE_CHECKING:
    from core_agents.registry import RegistryClient

logger = logging.getLogger(__name__)

# Namespace UUID for deterministic skill ID -> point ID mapping
# This ensures the same skill ID always maps to the same Qdrant point ID
SKILL_NAMESPACE = uuid.UUID("f47ac10b-58cc-4372-a567-0e02b2c3d479")


def skill_id_to_point_id(skill_id: str) -> str:
    """
    Convert a skill ID to a valid Qdrant point ID.

    Qdrant requires point IDs to be either integers or UUIDs.
    This function generates a deterministic UUID from the skill ID
    using uuid5 with a fixed namespace.

    Args:
        skill_id: The human-readable skill ID (e.g., "k8s-restart-crashloop")

    Returns:
        A valid UUID string for use as Qdrant point ID
    """
    return str(uuid.uuid5(SKILL_NAMESPACE, skill_id))


class SkillSearchResult(BaseModel):
    """Result from a skill search."""

    skill: Skill
    score: float  # Similarity score from vector search


class SkillLibrary(ABC):
    """
    Abstract interface for skill storage and retrieval.

    Implementations must provide:
    - Semantic search by query text
    - CRUD operations for skills
    - Outcome recording for learning
    """

    @abstractmethod
    async def add(self, skill: Skill) -> str:
        """
        Add a skill to the library.

        Returns the skill ID.
        """
        ...

    @abstractmethod
    async def get(self, skill_id: str) -> Skill | None:
        """Get a skill by ID."""
        ...

    @abstractmethod
    async def update(self, skill: Skill) -> None:
        """Update an existing skill."""
        ...

    @abstractmethod
    async def delete(self, skill_id: str) -> bool:
        """Delete a skill. Returns True if deleted, False if not found."""
        ...

    @abstractmethod
    async def search(
        self,
        query: str,
        domain: SkillDomain | None = None,
        category: SkillCategory | None = None,
        limit: int = 5,
        min_confidence: float = 0.0,
    ) -> list[SkillSearchResult]:
        """
        Search for skills matching a query.

        Uses semantic similarity on the skill's searchable text
        (name, description, preconditions, tags).

        Args:
            query: Natural language query
            domain: Filter by domain (k8s, news, etc.)
            category: Filter by category (diagnostic, remediation, etc.)
            limit: Maximum results to return
            min_confidence: Minimum confidence score for skills

        Returns:
            List of matching skills with similarity scores
        """
        ...

    @abstractmethod
    async def record_outcome(self, outcome: SkillOutcome) -> None:
        """
        Record an execution outcome for learning.

        Updates the skill's confidence based on success/failure.
        """
        ...

    @abstractmethod
    async def list_all(
        self,
        domain: SkillDomain | None = None,
        category: SkillCategory | None = None,
    ) -> list[Skill]:
        """List all skills, optionally filtered."""
        ...


class QdrantSkillLibrary(SkillLibrary):
    """
    Qdrant-based skill library implementation.

    Uses Qdrant for vector storage and semantic search.
    Embeddings are generated using the configured embedding model.

    Optionally syncs skill metadata to the centralized registry for
    cross-agent visibility and metrics tracking.
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        api_key: str | None = None,
        collection_name: str = "skills",
        embedding_url: str | None = None,
        embedding_model: str | None = None,
        embedding_dims: int | None = None,
        registry_client: "RegistryClient | None" = None,
        enable_registry_sync: bool = True,
    ):
        self.host = host or os.getenv("QDRANT_HOST", "localhost")
        self.port = port or int(os.getenv("QDRANT_PORT", "6333"))
        self.api_key = api_key or os.getenv("QDRANT_API_KEY")
        self.collection_name = collection_name
        self.embedding_url = embedding_url or os.getenv(
            "EMBEDDINGS_API_URL", "http://localhost:8001/v1"
        )
        self.embedding_model = embedding_model or os.getenv(
            "EMBEDDINGS_MODEL", "Qwen/Qwen3-Embedding-0.6B"
        )
        self.embedding_dims = embedding_dims or int(os.getenv("EMBEDDINGS_DIMS", "1024"))

        self._client: Any = None
        self._initialized = False
        self._registry_client = registry_client
        self._enable_registry_sync = enable_registry_sync

    async def _ensure_initialized(self) -> None:
        """Lazy initialization of Qdrant client and collection."""
        if self._initialized:
            return

        try:
            from qdrant_client import AsyncQdrantClient
            from qdrant_client.models import Distance, VectorParams

            # Auto-detect HTTPS: use if port is 443 or QDRANT_USE_HTTPS is set
            use_https = (
                os.getenv("QDRANT_USE_HTTPS", "").lower() in ("true", "1", "yes")
                or self.port == 443
            )
            scheme = "https" if use_https else "http"
            url = f"{scheme}://{self.host}:{self.port}"

            self._client = AsyncQdrantClient(
                url=url,
                api_key=self.api_key,
                check_compatibility=False,  # Suppress version mismatch warnings
            )

            # Check if collection exists, create if not
            collections = await self._client.get_collections()
            collection_names = [c.name for c in collections.collections]

            if self.collection_name not in collection_names:
                await self._client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.embedding_dims,
                        distance=Distance.COSINE,
                    ),
                )

            self._initialized = True

        except ImportError as err:
            raise ImportError(
                "qdrant-client is required for QdrantSkillLibrary. "
                "Install with: pip install qdrant-client"
            ) from err

    async def _get_embedding(self, text: str) -> list[float]:
        """Generate embedding for text using the configured model."""
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.embedding_url}/embeddings",
                json={"input": text, "model": self.embedding_model},
            )
            response.raise_for_status()
            data = response.json()
            return data["data"][0]["embedding"]

    def _sync_skill_to_registry(self, skill: Skill) -> None:
        """
        Sync skill metadata to registry (fire-and-forget).

        This spawns a background task that syncs skill metadata to the
        centralized registry. Failures are logged but don't affect the
        main skill operations.
        """
        if not self._enable_registry_sync or self._registry_client is None:
            return

        async def _do_sync() -> None:
            try:
                client = self._registry_client._ensure_client()
                await client.post(
                    "/api/v1/skills",
                    json={
                        "id": skill.id,
                        "name": skill.name,
                        "domain": skill.domain.value,
                        "category": skill.category.value,
                        "status": skill.status.value,
                        "confidence": skill.confidence,
                        "success_count": skill.success_count,
                        "failure_count": skill.failure_count,
                        "requires_approval": skill.requires_approval,
                    },
                )
                logger.debug("Synced skill %s to registry", skill.id)
            except Exception as e:
                logger.warning("Failed to sync skill %s to registry: %s", skill.id, e)

        # Fire and forget - don't await
        asyncio.create_task(_do_sync(), name=f"skill-sync-{skill.id}")

    def _sync_outcome_to_registry(self, skill_id: str, success: bool) -> None:
        """
        Sync skill outcome to registry (fire-and-forget).

        Updates the skill's success/failure counts in the registry.
        """
        if not self._enable_registry_sync or self._registry_client is None:
            return

        async def _do_sync() -> None:
            try:
                client = self._registry_client._ensure_client()
                await client.put(
                    f"/api/v1/skills/{skill_id}/outcome",
                    json={"success": success},
                )
                logger.debug("Synced outcome for skill %s to registry", skill_id)
            except Exception as e:
                logger.warning("Failed to sync outcome for skill %s to registry: %s", skill_id, e)

        # Fire and forget - don't await
        asyncio.create_task(_do_sync(), name=f"outcome-sync-{skill_id}")

    async def add(self, skill: Skill) -> str:
        """Add a skill to the library."""
        await self._ensure_initialized()

        from qdrant_client.models import PointStruct

        # Generate ID if not provided
        if not skill.id:
            skill.id = str(uuid.uuid4())

        # Convert skill ID to valid Qdrant point ID (UUID)
        point_id = skill_id_to_point_id(skill.id)

        # Generate embedding from searchable text
        embedding = await self._get_embedding(skill.get_searchable_text())

        # Store in Qdrant
        point = PointStruct(
            id=point_id,
            vector=embedding,
            payload=skill.model_dump(mode="json"),
        )

        await self._client.upsert(
            collection_name=self.collection_name,
            points=[point],
        )

        # Sync to registry (fire-and-forget)
        self._sync_skill_to_registry(skill)

        return skill.id

    async def get(self, skill_id: str) -> Skill | None:
        """Get a skill by ID."""
        await self._ensure_initialized()

        # Convert skill ID to Qdrant point ID
        point_id = skill_id_to_point_id(skill_id)

        results = await self._client.retrieve(
            collection_name=self.collection_name,
            ids=[point_id],
            with_payload=True,
        )

        if not results:
            return None

        return Skill.model_validate(results[0].payload)

    async def update(self, skill: Skill) -> None:
        """Update an existing skill."""
        await self._ensure_initialized()

        from qdrant_client.models import PointStruct

        # Convert skill ID to valid Qdrant point ID (UUID)
        point_id = skill_id_to_point_id(skill.id)

        # Re-generate embedding in case searchable text changed
        embedding = await self._get_embedding(skill.get_searchable_text())

        point = PointStruct(
            id=point_id,
            vector=embedding,
            payload=skill.model_dump(mode="json"),
        )

        await self._client.upsert(
            collection_name=self.collection_name,
            points=[point],
        )

        # Sync to registry (fire-and-forget)
        self._sync_skill_to_registry(skill)

    async def delete(self, skill_id: str) -> bool:
        """Delete a skill."""
        await self._ensure_initialized()

        from qdrant_client.models import PointIdsList

        # Check if exists first
        existing = await self.get(skill_id)
        if not existing:
            return False

        # Convert skill ID to valid Qdrant point ID (UUID)
        point_id = skill_id_to_point_id(skill_id)

        await self._client.delete(
            collection_name=self.collection_name,
            points_selector=PointIdsList(points=[point_id]),
        )

        return True

    async def search(
        self,
        query: str,
        domain: SkillDomain | None = None,
        category: SkillCategory | None = None,
        limit: int = 5,
        min_confidence: float = 0.0,
    ) -> list[SkillSearchResult]:
        """Search for skills matching a query."""
        await self._ensure_initialized()

        from qdrant_client.models import FieldCondition, Filter, MatchValue, Range

        # Generate query embedding
        query_embedding = await self._get_embedding(query)

        # Build filter conditions
        must_conditions = []

        if domain:
            must_conditions.append(
                FieldCondition(key="domain", match=MatchValue(value=domain.value))
            )

        if category:
            must_conditions.append(
                FieldCondition(key="category", match=MatchValue(value=category.value))
            )

        if min_confidence > 0:
            must_conditions.append(
                FieldCondition(key="confidence", range=Range(gte=min_confidence))
            )

        query_filter = Filter(must=must_conditions) if must_conditions else None

        # Search using query_points (qdrant-client 1.7+ API)
        response = await self._client.query_points(
            collection_name=self.collection_name,
            query=query_embedding,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
        results = response.points

        return [
            SkillSearchResult(
                skill=Skill.model_validate(result.payload),
                score=result.score,
            )
            for result in results
        ]

    async def record_outcome(self, outcome: SkillOutcome) -> None:
        """Record an execution outcome and update skill confidence."""
        skill = await self.get(outcome.skill_id)
        if not skill:
            return

        skill.record_outcome(outcome.success)
        await self.update(skill)

        # Also sync outcome directly (more efficient than full skill sync)
        self._sync_outcome_to_registry(outcome.skill_id, outcome.success)

    async def list_all(
        self,
        domain: SkillDomain | None = None,
        category: SkillCategory | None = None,
    ) -> list[Skill]:
        """List all skills, optionally filtered."""
        await self._ensure_initialized()

        from qdrant_client.models import FieldCondition, Filter, MatchValue

        # Build filter
        must_conditions = []

        if domain:
            must_conditions.append(
                FieldCondition(key="domain", match=MatchValue(value=domain.value))
            )

        if category:
            must_conditions.append(
                FieldCondition(key="category", match=MatchValue(value=category.value))
            )

        query_filter = Filter(must=must_conditions) if must_conditions else None

        # Scroll through all points
        skills = []
        offset = None

        while True:
            results, offset = await self._client.scroll(
                collection_name=self.collection_name,
                scroll_filter=query_filter,
                limit=100,
                offset=offset,
                with_payload=True,
            )

            skills.extend(Skill.model_validate(r.payload) for r in results)

            if offset is None:
                break

        return skills


# Singleton instance
_skill_library: SkillLibrary | None = None


async def get_skill_library(
    registry_client: "RegistryClient | None" = None,
    enable_registry_sync: bool | None = None,
) -> SkillLibrary:
    """
    Get the singleton skill library instance.

    Args:
        registry_client: Optional registry client for syncing skill metadata.
            If not provided, will attempt to create one from environment config.
        enable_registry_sync: Override for enabling/disabling registry sync.
            If None, uses KUBANI_REGISTRY_ENABLED env var (default: True).

    Returns:
        The singleton skill library instance.
    """
    global _skill_library

    if _skill_library is None:
        # Determine if registry sync should be enabled
        if enable_registry_sync is None:
            from core_agents.config_unified import get_config

            enable_registry_sync = is_registry_enabled()

        # Try to get registry client if sync is enabled and none provided
        actual_registry_client = registry_client
        if enable_registry_sync and actual_registry_client is None:
            try:
                from core_agents.config import get_config
                from core_agents.registry import RegistryClient

                config = get_config()
                actual_registry_client = RegistryClient(
                    base_url=config.registry_url,
                    timeout=config.registry_timeout,
                )
                await actual_registry_client.connect()
            except Exception as e:
                logger.warning("Failed to create registry client for skill sync: %s", e)
                actual_registry_client = None

        _skill_library = QdrantSkillLibrary(
            registry_client=actual_registry_client,
            enable_registry_sync=enable_registry_sync,
        )

    return _skill_library
