"""
Hierarchical memory system for AI agents.

Implements a three-tier memory architecture:
1. Working Memory - Current session context (in-memory, ephemeral)
2. Episodic Memory - Recent events with time decay (7-30 days, auto-expires)
3. Semantic Memory - Permanent patterns and best practices (never expires)

This mirrors human memory systems:
- Working memory is like short-term focus
- Episodic memory stores specific events that fade over time
- Semantic memory holds consolidated knowledge and patterns

Usage:
    from core_agents.hierarchical_memory import HierarchicalMemory
    from mem0 import Memory

    # Create memory with default configuration
    memory = HierarchicalMemory(agent_id="k8s-monitor")

    # Store in different tiers
    memory.add_working("Currently investigating pod crash in namespace prod")
    memory.add_episodic("Fixed OOMKilled in pod-abc by increasing memory limits")
    memory.add_semantic("OOMKilled errors typically require memory limit increases")

    # Search across tiers
    results = memory.search("OOMKilled pods")

    # Promote episodic to semantic when pattern is confirmed
    memory.promote_to_semantic(episodic_memory_id, "pattern confirmed after 5 occurrences")
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class MemoryTier(Enum):
    """Memory tier classification."""

    WORKING = "working"  # Current session, in-memory only
    EPISODIC = "episodic"  # Recent events, 7-30 day retention
    SEMANTIC = "semantic"  # Permanent patterns and knowledge


@dataclass
class WorkingMemoryItem:
    """A single item in working memory."""

    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class HierarchicalMemoryConfig:
    """Configuration for hierarchical memory system."""

    # Working memory settings
    working_memory_max_items: int = 20
    working_memory_ttl_seconds: int = 3600  # 1 hour

    # Episodic memory settings
    episodic_retention_days: int = 30
    episodic_collection_suffix: str = "_episodic"

    # Semantic memory settings
    semantic_collection_suffix: str = "_semantic"

    # Search settings
    search_limit_per_tier: int = 5
    include_working_in_search: bool = True


class HierarchicalMemory:
    """
    Three-tier hierarchical memory system.

    Provides working, episodic, and semantic memory tiers with different
    retention policies and search behavior.
    """

    def __init__(
        self,
        agent_id: str,
        mem0_config: dict[str, Any] | None = None,
        config: HierarchicalMemoryConfig | None = None,
    ):
        """
        Initialize hierarchical memory.

        Args:
            agent_id: Unique identifier for this agent's memory
            mem0_config: Configuration for mem0 (from get_mem0_config or get_graph_mem0_config)
            config: Hierarchical memory configuration
        """
        self.agent_id = agent_id
        self.config = config or HierarchicalMemoryConfig()
        self._mem0_config = mem0_config

        # Working memory is in-memory only
        self._working_memory: list[WorkingMemoryItem] = []

        # Lazy initialization of mem0 Memory
        self._episodic_memory: Any = None
        self._semantic_memory: Any = None

        logger.info(f"HierarchicalMemory initialized for agent: {agent_id}")

    def _get_episodic_memory(self) -> Any:
        """Get or create the episodic memory instance."""
        if self._episodic_memory is None:
            from mem0 import Memory

            config = self._get_mem0_config_for_tier(MemoryTier.EPISODIC)
            self._episodic_memory = Memory.from_config(config)
            logger.debug(f"Initialized episodic memory for {self.agent_id}")
        return self._episodic_memory

    def _get_semantic_memory(self) -> Any:
        """Get or create the semantic memory instance."""
        if self._semantic_memory is None:
            from mem0 import Memory

            config = self._get_mem0_config_for_tier(MemoryTier.SEMANTIC)
            self._semantic_memory = Memory.from_config(config)
            logger.debug(f"Initialized semantic memory for {self.agent_id}")
        return self._semantic_memory

    def _get_mem0_config_for_tier(self, tier: MemoryTier) -> dict[str, Any]:
        """Get mem0 config with tier-specific collection name."""
        if self._mem0_config is None:
            from core_agents.memory.config import get_mem0_config

            self._mem0_config = get_mem0_config()

        config = dict(self._mem0_config)

        # Modify collection name based on tier
        if "vector_store" in config and "config" in config["vector_store"]:
            vs_config = dict(config["vector_store"]["config"])
            base_collection = vs_config.get("collection_name", "mem0")

            if tier == MemoryTier.EPISODIC:
                vs_config["collection_name"] = (
                    f"{base_collection}{self.config.episodic_collection_suffix}"
                )
            elif tier == MemoryTier.SEMANTIC:
                vs_config["collection_name"] = (
                    f"{base_collection}{self.config.semantic_collection_suffix}"
                )

            config["vector_store"] = dict(config["vector_store"])
            config["vector_store"]["config"] = vs_config

        return config

    def _cleanup_working_memory(self) -> None:
        """Remove expired items from working memory."""
        cutoff = time.time() - self.config.working_memory_ttl_seconds
        self._working_memory = [item for item in self._working_memory if item.timestamp > cutoff]

        # Trim to max items
        if len(self._working_memory) > self.config.working_memory_max_items:
            self._working_memory = self._working_memory[-self.config.working_memory_max_items :]

    # -------------------------------------------------------------------------
    # Working Memory Operations
    # -------------------------------------------------------------------------

    def add_working(self, content: str, metadata: dict[str, Any] | None = None) -> None:
        """
        Add item to working memory.

        Working memory is ephemeral and only lasts for the current session.

        Args:
            content: The memory content
            metadata: Optional metadata to attach
        """
        self._cleanup_working_memory()
        item = WorkingMemoryItem(
            content=content,
            timestamp=time.time(),
            metadata=metadata or {},
        )
        self._working_memory.append(item)
        logger.debug(f"Added to working memory: {content[:50]}...")

    def get_working(self) -> list[WorkingMemoryItem]:
        """Get all current working memory items."""
        self._cleanup_working_memory()
        return list(self._working_memory)

    def clear_working(self) -> None:
        """Clear all working memory."""
        self._working_memory = []
        logger.debug("Cleared working memory")

    # -------------------------------------------------------------------------
    # Episodic Memory Operations
    # -------------------------------------------------------------------------

    def add_episodic(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
        user_id: str | None = None,
    ) -> str:
        """
        Add item to episodic memory.

        Episodic memories are stored in the vector database with a TTL.

        Args:
            content: The memory content
            metadata: Optional metadata to attach
            user_id: Optional user ID for multi-user scenarios

        Returns:
            Memory ID for later reference
        """
        memory = self._get_episodic_memory()

        # Add expiration timestamp to metadata
        meta = metadata or {}
        meta["tier"] = MemoryTier.EPISODIC.value
        meta["created_at"] = datetime.now(UTC).isoformat()
        meta["expires_at"] = (
            datetime.now(UTC) + timedelta(days=self.config.episodic_retention_days)
        ).isoformat()

        result = memory.add(
            content,
            user_id=user_id or self.agent_id,
            metadata=meta,
        )

        memory_id = result.get("id", "unknown") if isinstance(result, dict) else str(result)
        logger.debug(f"Added to episodic memory (id={memory_id}): {content[:50]}...")
        return memory_id

    def search_episodic(
        self,
        query: str,
        limit: int | None = None,
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Search episodic memory.

        Args:
            query: Search query
            limit: Max results to return
            user_id: Optional user ID filter

        Returns:
            List of matching memories
        """
        memory = self._get_episodic_memory()
        results = memory.search(
            query,
            user_id=user_id or self.agent_id,
            limit=limit or self.config.search_limit_per_tier,
        )
        return results if isinstance(results, list) else []

    # -------------------------------------------------------------------------
    # Semantic Memory Operations
    # -------------------------------------------------------------------------

    def add_semantic(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
        user_id: str | None = None,
    ) -> str:
        """
        Add item to semantic memory.

        Semantic memories are permanent knowledge that never expires.

        Args:
            content: The memory content (should be a pattern or principle)
            metadata: Optional metadata to attach
            user_id: Optional user ID for multi-user scenarios

        Returns:
            Memory ID for later reference
        """
        memory = self._get_semantic_memory()

        meta = metadata or {}
        meta["tier"] = MemoryTier.SEMANTIC.value
        meta["created_at"] = datetime.now(UTC).isoformat()
        meta["permanent"] = True

        result = memory.add(
            content,
            user_id=user_id or self.agent_id,
            metadata=meta,
        )

        memory_id = result.get("id", "unknown") if isinstance(result, dict) else str(result)
        logger.debug(f"Added to semantic memory (id={memory_id}): {content[:50]}...")
        return memory_id

    def search_semantic(
        self,
        query: str,
        limit: int | None = None,
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Search semantic memory.

        Args:
            query: Search query
            limit: Max results to return
            user_id: Optional user ID filter

        Returns:
            List of matching memories
        """
        memory = self._get_semantic_memory()
        results = memory.search(
            query,
            user_id=user_id or self.agent_id,
            limit=limit or self.config.search_limit_per_tier,
        )
        return results if isinstance(results, list) else []

    # -------------------------------------------------------------------------
    # Cross-Tier Operations
    # -------------------------------------------------------------------------

    def search(
        self,
        query: str,
        tiers: list[MemoryTier] | None = None,
        limit_per_tier: int | None = None,
        user_id: str | None = None,
    ) -> dict[MemoryTier, list[dict[str, Any]]]:
        """
        Search across multiple memory tiers.

        Args:
            query: Search query
            tiers: Which tiers to search (default: all)
            limit_per_tier: Max results per tier
            user_id: Optional user ID filter

        Returns:
            Dict mapping tier to list of results
        """
        if tiers is None:
            tiers = [MemoryTier.WORKING, MemoryTier.EPISODIC, MemoryTier.SEMANTIC]

        results: dict[MemoryTier, list[dict[str, Any]]] = {}
        limit = limit_per_tier or self.config.search_limit_per_tier

        for tier in tiers:
            if tier == MemoryTier.WORKING:
                if self.config.include_working_in_search:
                    # Simple substring match for working memory
                    self._cleanup_working_memory()
                    query_lower = query.lower()
                    matching = [
                        {"content": item.content, "metadata": item.metadata}
                        for item in self._working_memory
                        if query_lower in item.content.lower()
                    ]
                    results[tier] = matching[:limit]
            elif tier == MemoryTier.EPISODIC:
                results[tier] = self.search_episodic(query, limit, user_id)
            elif tier == MemoryTier.SEMANTIC:
                results[tier] = self.search_semantic(query, limit, user_id)

        return results

    def promote_to_semantic(
        self,
        episodic_memory_id: str,
        reason: str,
        user_id: str | None = None,
    ) -> str | None:
        """
        Promote an episodic memory to semantic (permanent) memory.

        Use this when a pattern has been confirmed across multiple events.

        Args:
            episodic_memory_id: ID of the episodic memory to promote
            reason: Why this is being promoted (e.g., "pattern confirmed 5 times")
            user_id: Optional user ID

        Returns:
            New semantic memory ID, or None if promotion failed
        """
        episodic = self._get_episodic_memory()

        # Get the episodic memory
        try:
            memories = episodic.get_all(user_id=user_id or self.agent_id)
            source_memory = None
            for mem in memories:
                if mem.get("id") == episodic_memory_id:
                    source_memory = mem
                    break

            if source_memory is None:
                logger.warning(f"Episodic memory {episodic_memory_id} not found")
                return None

            # Create semantic memory with provenance
            content = source_memory.get("memory", source_memory.get("content", ""))
            metadata = source_memory.get("metadata", {})
            metadata["promoted_from"] = episodic_memory_id
            metadata["promotion_reason"] = reason
            metadata["promoted_at"] = datetime.now(UTC).isoformat()

            semantic_id = self.add_semantic(content, metadata, user_id)
            logger.info(
                f"Promoted episodic {episodic_memory_id} to semantic {semantic_id}: {reason}"
            )
            return semantic_id

        except Exception as e:
            logger.error(f"Failed to promote memory {episodic_memory_id}: {e}")
            return None

    def get_context_summary(self, max_items: int = 10) -> str:
        """
        Get a summary of current memory context for LLM prompting.

        Returns a formatted string suitable for including in system prompts.

        Args:
            max_items: Maximum items to include from each tier

        Returns:
            Formatted context string
        """
        lines = []

        # Working memory
        working = self.get_working()[:max_items]
        if working:
            lines.append("## Current Session Context")
            for item in working:
                lines.append(f"- {item.content}")
            lines.append("")

        # Recent episodic (last few searches are cached, this is a simple implementation)
        # In production, you might want to pre-fetch relevant episodic memories

        # Semantic knowledge could be pre-loaded based on agent type

        return "\n".join(lines) if lines else "No current context."
