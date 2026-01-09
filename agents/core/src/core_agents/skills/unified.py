"""
UnifiedSkillLibrary - bridges filesystem skills with Qdrant search.

Skills are authored as markdown (source of truth) and synced to Qdrant
for semantic search. This enables:
- Edit skills in markdown, no code changes
- Semantic search for skill matching
- Automatic sync on startup or file change
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import frontmatter

logger = logging.getLogger(__name__)

# Namespace UUID for deterministic skill path -> point ID mapping
SKILL_NAMESPACE = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")


def skill_path_to_point_id(skill_path: str) -> str:
    """
    Convert a skill path to a valid Qdrant point ID.

    Qdrant requires point IDs to be either integers or UUIDs.
    This function generates a deterministic UUID from the skill path.
    """
    return str(uuid.uuid5(SKILL_NAMESPACE, skill_path))


@dataclass
class AgentSkill:
    """Agent Skills format representation (markdown-based)."""

    name: str
    description: str
    path: Path
    metadata: dict[str, Any]
    body: str  # Full markdown body

    @property
    def id(self) -> str:
        """Generate stable ID from path (e.g., 'k8s/remediation/restart-crashloop')."""
        # Get path relative to skills directory
        # e.g., skills/k8s/remediation/restart-crashloop/SKILL.md -> k8s/remediation/restart-crashloop
        parts = self.path.parts
        # Find 'skills' in path and get everything after up to SKILL.md
        try:
            skills_idx = parts.index("skills")
            return "/".join(parts[skills_idx + 1 : -1])  # Exclude 'skills' and 'SKILL.md'
        except ValueError:
            # Fallback to parent directory name
            return self.path.parent.name

    def _get_meta(self, key: str, default: Any = None) -> Any:
        """Get metadata value, checking both top-level and nested 'metadata' key."""
        # First check top-level
        if key in self.metadata:
            return self.metadata[key]
        # Then check nested metadata
        nested = self.metadata.get("metadata", {})
        return nested.get(key, default)

    @property
    def domain(self) -> str:
        return self._get_meta("domain", "general")

    @property
    def category(self) -> str:
        return self._get_meta("category", "general")

    @property
    def requires_approval(self) -> bool:
        return self._get_meta("requires-approval", False)

    @property
    def confidence(self) -> float:
        return self._get_meta("confidence", 0.5)

    @property
    def mcp_servers(self) -> list[str]:
        return self._get_meta("mcp-servers", [])

    def get_searchable_text(self) -> str:
        """Text for embedding generation."""
        return f"{self.name} {self.description}"

    def get_preconditions(self) -> list[str]:
        """Extract preconditions from markdown body."""
        preconditions = []
        in_preconditions = False

        for line in self.body.split("\n"):
            if line.strip().startswith("## Preconditions"):
                in_preconditions = True
                continue
            if in_preconditions:
                if line.strip().startswith("##"):
                    break
                if line.strip().startswith("- "):
                    # Extract text after "- " or "- [ ] "
                    text = line.strip()[2:]
                    # Remove checkbox markers if present
                    if text.startswith("[ ] ") or text.startswith("[x] "):
                        text = text[4:]
                    if text:
                        preconditions.append(text)

        return preconditions

    def get_actions(self) -> list[dict[str, Any]]:
        """Extract actions with MCP tool references from markdown body."""
        actions = []
        in_actions = False
        current_action: dict[str, Any] = {}

        for line in self.body.split("\n"):
            if line.strip().startswith("## Actions"):
                in_actions = True
                continue
            if in_actions:
                if line.strip().startswith("## "):
                    break
                # Action header: ### 1. Action Name
                if line.strip().startswith("### "):
                    if current_action:
                        actions.append(current_action)
                    current_action = {
                        "description": line.strip().lstrip("# ").lstrip("0123456789. ")
                    }

        if current_action:
            actions.append(current_action)

        return actions

    def get_success_criteria(self) -> list[str]:
        """Extract success criteria from markdown body."""
        criteria = []
        in_criteria = False

        for line in self.body.split("\n"):
            if line.strip().startswith("## Success Criteria"):
                in_criteria = True
                continue
            if in_criteria:
                if line.strip().startswith("##"):
                    break
                if line.strip().startswith("- "):
                    text = line.strip()[2:]
                    # Remove checkbox markers if present
                    if text.startswith("[ ] ") or text.startswith("[x] "):
                        text = text[4:]
                    if text:
                        criteria.append(text)

        return criteria

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "path": str(self.path),
            "domain": self.domain,
            "category": self.category,
            "requires_approval": self.requires_approval,
            "confidence": self.confidence,
            "mcp_servers": self.mcp_servers,
            "preconditions": self.get_preconditions(),
            "success_criteria": self.get_success_criteria(),
        }


@dataclass
class SkillSearchResult:
    """Result from a skill search."""

    skill: AgentSkill
    score: float  # Similarity score from vector search


class UnifiedSkillLibrary:
    """
    Unified skill library that:
    1. Reads skills from filesystem (Agent Skills format)
    2. Indexes them in Qdrant for semantic search
    3. Provides search interface for agents

    Skills are authored as markdown files (source of truth) and synced
    to Qdrant for fast semantic retrieval.
    """

    def __init__(
        self,
        skills_dir: Path | str | None = None,
        qdrant_host: str | None = None,
        qdrant_port: int | None = None,
        qdrant_api_key: str | None = None,
        embedding_url: str | None = None,
        embedding_model: str | None = None,
        embedding_dims: int | None = None,
        collection_name: str = "agent_skills",
    ):
        # Skills directory - default to /skills in K8s, ./skills locally
        if skills_dir is None:
            skills_dir = Path(os.getenv("SKILLS_DIR", "skills"))
        self.skills_dir = Path(skills_dir)

        # Qdrant configuration
        self.qdrant_host = qdrant_host or os.getenv("QDRANT_HOST", "localhost")
        self.qdrant_port = qdrant_port or int(os.getenv("QDRANT_PORT", "6333"))
        self.qdrant_api_key = qdrant_api_key or os.getenv("QDRANT_API_KEY")
        self.collection_name = collection_name

        # Embedding configuration
        self.embedding_url = embedding_url or os.getenv(
            "EMBEDDINGS_API_URL", "http://localhost:8001/v1"
        )
        self.embedding_model = embedding_model or os.getenv(
            "EMBEDDINGS_MODEL", "Qwen/Qwen3-Embedding-0.6B"
        )
        self.embedding_dims = embedding_dims or int(os.getenv("EMBEDDINGS_DIMS", "1024"))

        # Cache for loaded skills
        self._skills_cache: dict[str, AgentSkill] = {}
        self._qdrant_client: Any = None
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        """Lazy initialization of Qdrant client and collection."""
        if self._initialized:
            return

        try:
            from qdrant_client import AsyncQdrantClient
            from qdrant_client.models import Distance, VectorParams

            # Auto-detect HTTPS
            use_https = (
                os.getenv("QDRANT_USE_HTTPS", "").lower() in ("true", "1", "yes")
                or self.qdrant_port == 443
            )
            scheme = "https" if use_https else "http"
            url = f"{scheme}://{self.qdrant_host}:{self.qdrant_port}"

            self._qdrant_client = AsyncQdrantClient(
                url=url,
                api_key=self.qdrant_api_key,
                check_compatibility=False,
            )

            # Check if collection exists, create if not
            collections = await self._qdrant_client.get_collections()
            collection_names = [c.name for c in collections.collections]

            if self.collection_name not in collection_names:
                await self._qdrant_client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.embedding_dims,
                        distance=Distance.COSINE,
                    ),
                )

            self._initialized = True
            logger.info("UnifiedSkillLibrary initialized with Qdrant at %s", url)

        except ImportError as err:
            raise ImportError(
                "qdrant-client is required for UnifiedSkillLibrary. "
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

    def _load_skill(self, path: Path) -> AgentSkill | None:
        """Load a SKILL.md file into AgentSkill."""
        try:
            post = frontmatter.load(path)
            metadata = dict(post.metadata) if post.metadata else {}

            return AgentSkill(
                name=metadata.get("name", path.parent.name),
                description=metadata.get("description", ""),
                path=path,
                metadata=metadata,
                body=post.content,
            )
        except Exception as e:
            logger.warning("Failed to load skill from %s: %s", path, e)
            return None

    async def _index_skill(self, skill: AgentSkill) -> None:
        """Add/update skill in Qdrant."""
        from qdrant_client.models import PointStruct

        embedding = await self._get_embedding(skill.get_searchable_text())

        point = PointStruct(
            id=skill_path_to_point_id(skill.id),
            vector=embedding,
            payload=skill.to_dict(),
        )

        await self._qdrant_client.upsert(
            collection_name=self.collection_name,
            points=[point],
        )

    async def sync(self) -> list[str]:
        """
        Sync filesystem skills to Qdrant.

        Scans the skills directory for SKILL.md files, loads them,
        and indexes them in Qdrant for semantic search.

        Returns:
            List of skill IDs that were added/updated.
        """
        await self._ensure_initialized()

        if not self.skills_dir.exists():
            logger.warning("Skills directory does not exist: %s", self.skills_dir)
            return []

        synced = []

        for skill_path in self.skills_dir.rglob("SKILL.md"):
            # Skip proposed skills
            if "proposed" in skill_path.parts:
                continue

            skill = self._load_skill(skill_path)
            if skill:
                try:
                    await self._index_skill(skill)
                    self._skills_cache[skill.id] = skill
                    synced.append(skill.id)
                    logger.debug("Synced skill: %s", skill.id)
                except Exception as e:
                    logger.warning("Failed to index skill %s: %s", skill.id, e)

        logger.info("Synced %d skills to Qdrant", len(synced))
        return synced

    async def search(
        self,
        query: str,
        domain: str | None = None,
        category: str | None = None,
        limit: int = 5,
        min_confidence: float = 0.0,
    ) -> list[SkillSearchResult]:
        """
        Semantic search for matching skills.

        Args:
            query: Natural language description of situation
            domain: Filter by domain (k8s, news, general)
            category: Filter by category (remediation, diagnostic, etc.)
            limit: Max results
            min_confidence: Minimum confidence score

        Returns:
            Matching skills sorted by relevance
        """
        await self._ensure_initialized()

        from qdrant_client.models import FieldCondition, Filter, MatchValue, Range

        # Generate query embedding
        embedding = await self._get_embedding(query)

        # Build filter conditions
        must_conditions = []

        if domain:
            must_conditions.append(FieldCondition(key="domain", match=MatchValue(value=domain)))

        if category:
            must_conditions.append(FieldCondition(key="category", match=MatchValue(value=category)))

        if min_confidence > 0:
            must_conditions.append(
                FieldCondition(key="confidence", range=Range(gte=min_confidence))
            )

        query_filter = Filter(must=must_conditions) if must_conditions else None

        # Search
        response = await self._qdrant_client.query_points(
            collection_name=self.collection_name,
            query=embedding,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )

        results = []
        for point in response.points:
            skill_id = point.payload["id"]

            # Get from cache or load from disk
            if skill_id in self._skills_cache:
                skill = self._skills_cache[skill_id]
            else:
                skill_path = Path(point.payload["path"])
                skill = self._load_skill(skill_path)
                if skill:
                    self._skills_cache[skill_id] = skill

            if skill:
                results.append(SkillSearchResult(skill=skill, score=point.score))

        return results

    async def get(self, skill_id: str) -> AgentSkill | None:
        """Get skill by ID."""
        # Check cache first
        if skill_id in self._skills_cache:
            return self._skills_cache[skill_id]

        # Search on disk
        for skill_path in self.skills_dir.rglob("SKILL.md"):
            skill = self._load_skill(skill_path)
            if skill and skill.id == skill_id:
                self._skills_cache[skill_id] = skill
                return skill

        return None

    async def get_body(self, skill_id: str) -> str | None:
        """Get full skill body (for loading into agent context)."""
        skill = await self.get(skill_id)
        return skill.body if skill else None

    async def list_all(
        self,
        domain: str | None = None,
        category: str | None = None,
    ) -> list[AgentSkill]:
        """List all skills, optionally filtered."""
        skills = []

        for skill_path in self.skills_dir.rglob("SKILL.md"):
            if "proposed" in skill_path.parts:
                continue

            skill = self._load_skill(skill_path)
            if skill:
                # Apply filters
                if domain and skill.domain != domain:
                    continue
                if category and skill.category != category:
                    continue
                skills.append(skill)

        return skills

    async def get_proposed_skills(self) -> list[AgentSkill]:
        """List skills in the proposed directory (awaiting review)."""
        proposed_dir = self.skills_dir / "proposed"
        if not proposed_dir.exists():
            return []

        skills = []
        for skill_path in proposed_dir.rglob("SKILL.md"):
            skill = self._load_skill(skill_path)
            if skill:
                skills.append(skill)

        return skills


# Singleton instance
_unified_library: UnifiedSkillLibrary | None = None


async def get_unified_skill_library(**kwargs: Any) -> UnifiedSkillLibrary:
    """Get the singleton unified skill library instance."""
    global _unified_library

    if _unified_library is None:
        _unified_library = UnifiedSkillLibrary(**kwargs)

    return _unified_library
