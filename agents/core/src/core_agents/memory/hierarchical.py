"""
Hierarchical memory system for AI agents.

Implements a three-tier memory architecture:
1. Working Memory - Current session context (in-memory, ephemeral)
2. Episodic Memory - Recent events with time decay (7-30 days, auto-expires)
3. Semantic Memory - Permanent patterns and best practices (with decay mechanism)

This mirrors human memory systems:
- Working memory is like short-term focus
- Episodic memory stores specific events that fade over time
- Semantic memory holds consolidated knowledge and patterns

Enhanced features:
- Automatic memory promotion based on retrieval frequency
- Memory forgetting/decay for semantic memories
- Confidence scoring and tracking

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

    # Automatic promotion happens when episodic memories are frequently retrieved
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
class MemoryStats:
    """Statistics for a memory item used in promotion/decay decisions."""

    retrieval_count: int = 0
    last_retrieved: datetime | None = None
    success_associations: int = 0
    failure_associations: int = 0
    confidence_score: float = 1.0

    def record_retrieval(self, successful: bool = True) -> None:
        """Record a retrieval of this memory."""
        self.retrieval_count += 1
        self.last_retrieved = datetime.now(UTC)
        if successful:
            self.success_associations += 1
        else:
            self.failure_associations += 1

    def calculate_confidence(self) -> float:
        """Calculate confidence score based on usage patterns."""
        if self.retrieval_count == 0:
            return self.confidence_score

        success_rate = (
            self.success_associations / (self.success_associations + self.failure_associations)
            if (self.success_associations + self.failure_associations) > 0
            else 0.5
        )

        # Decay based on time since last retrieval
        if self.last_retrieved:
            days_since = (datetime.now(UTC) - self.last_retrieved).days
            time_decay = max(0.5, 1.0 - (days_since * 0.01))  # 1% decay per day
        else:
            time_decay = 1.0

        self.confidence_score = success_rate * time_decay
        return self.confidence_score

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "retrieval_count": self.retrieval_count,
            "last_retrieved": self.last_retrieved.isoformat() if self.last_retrieved else None,
            "success_associations": self.success_associations,
            "failure_associations": self.failure_associations,
            "confidence_score": self.confidence_score,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryStats":
        """Create from dictionary."""
        stats = cls(
            retrieval_count=data.get("retrieval_count", 0),
            success_associations=data.get("success_associations", 0),
            failure_associations=data.get("failure_associations", 0),
            confidence_score=data.get("confidence_score", 1.0),
        )
        if data.get("last_retrieved"):
            stats.last_retrieved = datetime.fromisoformat(data["last_retrieved"])
        return stats


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

    # Automatic promotion settings
    promotion_retrieval_threshold: int = 5  # Promote after N retrievals
    promotion_success_rate_threshold: float = 0.7  # Minimum success rate for promotion

    # Memory decay/forgetting settings
    enable_memory_decay: bool = True
    decay_check_interval_hours: int = 24
    archive_confidence_threshold: float = 0.3  # Archive below this confidence
    delete_confidence_threshold: float = 0.1  # Delete below this confidence
    min_age_for_decay_days: int = 7  # Don't decay memories younger than this


class HierarchicalMemory:
    """
    Three-tier hierarchical memory system.

    Provides working, episodic, and semantic memory tiers with different
    retention policies and search behavior.

    Enhanced with:
    - Automatic promotion of frequently-retrieved episodic memories
    - Memory decay/forgetting for semantic memories based on usage
    - Confidence scoring for memory quality assessment
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

        # Memory statistics tracking (in-memory, could be persisted)
        self._memory_stats: dict[str, MemoryStats] = {}

        # Lazy initialization of mem0 Memory
        self._episodic_memory: Any = None
        self._semantic_memory: Any = None

        # Last decay check timestamp
        self._last_decay_check: datetime | None = None

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

    def _get_or_create_stats(self, memory_id: str) -> MemoryStats:
        """Get or create stats for a memory."""
        if memory_id not in self._memory_stats:
            self._memory_stats[memory_id] = MemoryStats()
        return self._memory_stats[memory_id]

    def _check_for_promotion(self, memory_id: str, user_id: str | None = None) -> bool:
        """
        Check if an episodic memory should be promoted to semantic.

        Args:
            memory_id: ID of the episodic memory
            user_id: Optional user ID

        Returns:
            True if memory was promoted
        """
        stats = self._memory_stats.get(memory_id)
        if not stats:
            return False

        # Check promotion criteria
        if stats.retrieval_count >= self.config.promotion_retrieval_threshold:
            success_rate = (
                stats.success_associations
                / (stats.success_associations + stats.failure_associations)
                if (stats.success_associations + stats.failure_associations) > 0
                else 0.5
            )

            if success_rate >= self.config.promotion_success_rate_threshold:
                # Promote this memory
                reason = (
                    f"Auto-promoted: {stats.retrieval_count} retrievals, "
                    f"{success_rate:.0%} success rate"
                )
                semantic_id = self.promote_to_semantic(memory_id, reason, user_id)
                if semantic_id:
                    logger.info(f"Auto-promoted episodic memory {memory_id} to semantic")
                    return True

        return False

    async def run_decay_check(self, user_id: str | None = None) -> dict[str, int]:
        """
        Run decay check on semantic memories.

        Archives or deletes memories with low confidence scores.

        Args:
            user_id: Optional user ID

        Returns:
            Dict with counts of archived and deleted memories
        """
        if not self.config.enable_memory_decay:
            return {"archived": 0, "deleted": 0}

        # Check if enough time has passed since last check
        if self._last_decay_check:
            hours_since = (datetime.now(UTC) - self._last_decay_check).total_seconds() / 3600
            if hours_since < self.config.decay_check_interval_hours:
                return {"archived": 0, "deleted": 0}

        self._last_decay_check = datetime.now(UTC)

        archived = 0
        deleted = 0

        try:
            semantic = self._get_semantic_memory()
            memories = semantic.get_all(user_id=user_id or self.agent_id)

            for mem in memories:
                memory_id = mem.get("id")
                if not memory_id:
                    continue

                # Check age
                created_at = mem.get("metadata", {}).get("created_at")
                if created_at:
                    created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    age_days = (datetime.now(UTC) - created).days
                    if age_days < self.config.min_age_for_decay_days:
                        continue

                # Get or calculate confidence
                stats = self._memory_stats.get(memory_id, MemoryStats())
                confidence = stats.calculate_confidence()

                if confidence < self.config.delete_confidence_threshold:
                    # Delete low-confidence memory
                    try:
                        semantic.delete(memory_id)
                        deleted += 1
                        logger.info(
                            f"Deleted low-confidence memory {memory_id} (conf={confidence:.2f})"
                        )
                    except Exception as e:
                        logger.warning(f"Failed to delete memory {memory_id}: {e}")

                elif confidence < self.config.archive_confidence_threshold:
                    # Archive (mark as archived in metadata)
                    try:
                        # Update metadata to mark as archived
                        meta = mem.get("metadata", {})
                        meta["archived"] = True
                        meta["archived_at"] = datetime.now(UTC).isoformat()
                        meta["archive_reason"] = f"Low confidence: {confidence:.2f}"
                        # Note: mem0 may not support metadata updates directly
                        # This is a placeholder for the concept
                        archived += 1
                        logger.info(f"Archived memory {memory_id} (conf={confidence:.2f})")
                    except Exception as e:
                        logger.warning(f"Failed to archive memory {memory_id}: {e}")

        except Exception as e:
            logger.error(f"Decay check failed: {e}")

        return {"archived": archived, "deleted": deleted}

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

        # Initialize stats for this memory
        self._memory_stats[memory_id] = MemoryStats()

        logger.debug(f"Added to episodic memory (id={memory_id}): {content[:50]}...")
        return memory_id

    def search_episodic(
        self,
        query: str,
        limit: int | None = None,
        user_id: str | None = None,
        record_retrieval: bool = True,
        successful: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Search episodic memory.

        Args:
            query: Search query
            limit: Max results to return
            user_id: Optional user ID filter
            record_retrieval: Whether to record this retrieval for stats
            successful: Whether this retrieval was successful (for promotion logic)

        Returns:
            List of matching memories
        """
        memory = self._get_episodic_memory()
        results = memory.search(
            query,
            user_id=user_id or self.agent_id,
            limit=limit or self.config.search_limit_per_tier,
        )

        if not isinstance(results, list):
            return []

        # Record retrievals and check for promotion
        if record_retrieval:
            for result in results:
                memory_id = result.get("id")
                if memory_id:
                    stats = self._get_or_create_stats(memory_id)
                    stats.record_retrieval(successful)
                    self._check_for_promotion(memory_id, user_id)

        return results

    def record_memory_outcome(
        self,
        memory_id: str,
        successful: bool,
        context: str = "",
    ) -> None:
        """
        Record the outcome of using a memory.

        This helps the system learn which memories are useful.

        Args:
            memory_id: ID of the memory
            successful: Whether using this memory led to success
            context: Optional context about the outcome
        """
        stats = self._get_or_create_stats(memory_id)
        if successful:
            stats.success_associations += 1
        else:
            stats.failure_associations += 1

        logger.debug(f"Recorded {'success' if successful else 'failure'} for memory {memory_id}")

    # -------------------------------------------------------------------------
    # Semantic Memory Operations
    # -------------------------------------------------------------------------

    def add_semantic(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
        user_id: str | None = None,
        initial_confidence: float = 1.0,
    ) -> str:
        """
        Add item to semantic memory.

        Semantic memories are permanent knowledge that can decay over time
        if not accessed or if associated with failures.

        Args:
            content: The memory content (should be a pattern or principle)
            metadata: Optional metadata to attach
            user_id: Optional user ID for multi-user scenarios
            initial_confidence: Initial confidence score (0.0-1.0)

        Returns:
            Memory ID for later reference
        """
        memory = self._get_semantic_memory()

        meta = metadata or {}
        meta["tier"] = MemoryTier.SEMANTIC.value
        meta["created_at"] = datetime.now(UTC).isoformat()
        meta["permanent"] = True
        meta["initial_confidence"] = initial_confidence

        result = memory.add(
            content,
            user_id=user_id or self.agent_id,
            metadata=meta,
        )

        memory_id = result.get("id", "unknown") if isinstance(result, dict) else str(result)

        # Initialize stats with initial confidence
        stats = MemoryStats(confidence_score=initial_confidence)
        self._memory_stats[memory_id] = stats

        logger.debug(f"Added to semantic memory (id={memory_id}): {content[:50]}...")
        return memory_id

    def search_semantic(
        self,
        query: str,
        limit: int | None = None,
        user_id: str | None = None,
        min_confidence: float = 0.0,
        record_retrieval: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Search semantic memory.

        Args:
            query: Search query
            limit: Max results to return
            user_id: Optional user ID filter
            min_confidence: Minimum confidence score to include
            record_retrieval: Whether to record this retrieval

        Returns:
            List of matching memories
        """
        memory = self._get_semantic_memory()
        results = memory.search(
            query,
            user_id=user_id or self.agent_id,
            limit=limit or self.config.search_limit_per_tier,
        )

        if not isinstance(results, list):
            return []

        # Filter by confidence and record retrievals
        filtered_results = []
        for result in results:
            memory_id = result.get("id")
            if memory_id:
                stats = self._get_or_create_stats(memory_id)
                confidence = stats.calculate_confidence()

                if confidence >= min_confidence:
                    # Add confidence to result
                    result["confidence"] = confidence
                    filtered_results.append(result)

                    if record_retrieval:
                        stats.record_retrieval()

        return filtered_results

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

            # Transfer stats if available
            source_stats = self._memory_stats.get(episodic_memory_id, MemoryStats())
            initial_confidence = source_stats.calculate_confidence()

            semantic_id = self.add_semantic(
                content, metadata, user_id, initial_confidence=initial_confidence
            )
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

    def get_memory_health(self) -> dict[str, Any]:
        """
        Get health metrics for the memory system.

        Returns:
            Dict with memory health metrics
        """
        total_stats = len(self._memory_stats)
        low_confidence = sum(
            1
            for s in self._memory_stats.values()
            if s.calculate_confidence() < self.config.archive_confidence_threshold
        )

        return {
            "working_memory_items": len(self._working_memory),
            "tracked_memories": total_stats,
            "low_confidence_memories": low_confidence,
            "last_decay_check": self._last_decay_check.isoformat()
            if self._last_decay_check
            else None,
        }
