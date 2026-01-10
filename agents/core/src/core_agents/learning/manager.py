"""
Learning Manager - Core continuous learning functionality.

Manages the learning lifecycle:
1. Recording interactions
2. Extracting patterns
3. Updating skills
4. Persisting knowledge
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class LearningConfig:
    """Configuration for the learning system."""

    # Storage
    redis_url: str = ""
    persistence_enabled: bool = True

    # Learning parameters
    min_samples_for_pattern: int = 3
    pattern_confidence_threshold: float = 0.7
    max_patterns_per_agent: int = 100

    # Evolution
    evolution_enabled: bool = True
    evolution_interval_hours: int = 24

    # Cleanup
    interaction_retention_days: int = 30


@dataclass
class Interaction:
    """A recorded agent interaction."""

    id: str
    agent_id: str
    timestamp: datetime
    input_data: dict[str, Any]
    output_data: dict[str, Any]
    success: bool
    duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LearnedPattern:
    """A pattern learned from interactions."""

    id: str
    agent_id: str
    pattern_type: str
    input_pattern: dict[str, Any]
    output_pattern: dict[str, Any]
    confidence: float
    sample_count: int
    success_rate: float
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


class LearningManager:
    """
    Manages continuous learning for Kubani agents.

    Features:
    - Real-time interaction recording
    - Pattern extraction and refinement
    - Skill evolution suggestions
    - Knowledge persistence
    """

    def __init__(self, config: LearningConfig | None = None):
        self.config = config or LearningConfig(
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379")
        )
        self._redis = None
        self._patterns: dict[str, list[LearnedPattern]] = {}
        self._interactions_buffer: list[Interaction] = []
        self._lock = asyncio.Lock()

    async def _get_redis(self):
        """Get Redis client."""
        if self._redis is None and self.config.persistence_enabled:
            try:
                import redis.asyncio as aioredis

                self._redis = aioredis.from_url(
                    self.config.redis_url,
                    decode_responses=True,
                )
            except Exception as e:
                logger.warning(f"Failed to connect to Redis: {e}")
        return self._redis

    async def record_interaction(
        self,
        agent_id: str,
        input_data: dict[str, Any],
        output_data: dict[str, Any],
        success: bool,
        duration_ms: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> Interaction:
        """
        Record an agent interaction for learning.

        Args:
            agent_id: Agent identifier
            input_data: Input to the agent
            output_data: Output from the agent
            success: Whether the interaction was successful
            duration_ms: Duration in milliseconds
            metadata: Additional metadata

        Returns:
            The recorded Interaction
        """
        import uuid

        interaction = Interaction(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            timestamp=datetime.now(UTC),
            input_data=input_data,
            output_data=output_data,
            success=success,
            duration_ms=duration_ms,
            metadata=metadata or {},
        )

        async with self._lock:
            self._interactions_buffer.append(interaction)

            # Persist to Redis if enabled
            if self.config.persistence_enabled:
                await self._persist_interaction(interaction)

            # Trigger pattern extraction if buffer is large enough
            if len(self._interactions_buffer) >= self.config.min_samples_for_pattern:
                await self._extract_patterns(agent_id)

        return interaction

    async def _persist_interaction(self, interaction: Interaction) -> None:
        """Persist interaction to Redis."""
        redis = await self._get_redis()
        if not redis:
            return

        try:
            key = f"learning:interactions:{interaction.agent_id}"
            data = json.dumps(
                {
                    "id": interaction.id,
                    "timestamp": interaction.timestamp.isoformat(),
                    "input": interaction.input_data,
                    "output": interaction.output_data,
                    "success": interaction.success,
                    "duration_ms": interaction.duration_ms,
                    "metadata": interaction.metadata,
                }
            )

            await redis.lpush(key, data)

            # Trim to retention limit
            max_items = self.config.interaction_retention_days * 100  # Estimate
            await redis.ltrim(key, 0, max_items)

        except Exception as e:
            logger.warning(f"Failed to persist interaction: {e}")

    async def _extract_patterns(self, agent_id: str) -> list[LearnedPattern]:
        """Extract patterns from recent interactions."""
        # Get interactions for this agent
        agent_interactions = [i for i in self._interactions_buffer if i.agent_id == agent_id]

        if len(agent_interactions) < self.config.min_samples_for_pattern:
            return []

        # Group by input similarity
        patterns = await self._cluster_interactions(agent_interactions)

        # Store patterns
        if agent_id not in self._patterns:
            self._patterns[agent_id] = []

        for pattern in patterns:
            if pattern.confidence >= self.config.pattern_confidence_threshold:
                # Check if pattern already exists
                existing = next(
                    (p for p in self._patterns[agent_id] if self._patterns_match(p, pattern)),
                    None,
                )

                if existing:
                    # Update existing pattern
                    existing.sample_count += pattern.sample_count
                    existing.confidence = (existing.confidence + pattern.confidence) / 2
                    existing.updated_at = datetime.now(UTC)
                else:
                    # Add new pattern
                    self._patterns[agent_id].append(pattern)

                # Persist pattern
                await self._persist_pattern(pattern)

        # Limit patterns per agent
        if len(self._patterns[agent_id]) > self.config.max_patterns_per_agent:
            # Keep highest confidence patterns
            self._patterns[agent_id].sort(key=lambda p: p.confidence, reverse=True)
            self._patterns[agent_id] = self._patterns[agent_id][
                : self.config.max_patterns_per_agent
            ]

        return patterns

    async def _cluster_interactions(
        self,
        interactions: list[Interaction],
    ) -> list[LearnedPattern]:
        """Cluster interactions to find patterns."""
        import uuid

        # Simple clustering by input keys
        clusters: dict[str, list[Interaction]] = {}

        for interaction in interactions:
            # Create cluster key from input structure
            key = self._get_input_signature(interaction.input_data)
            if key not in clusters:
                clusters[key] = []
            clusters[key].append(interaction)

        patterns = []
        for key, cluster in clusters.items():
            if len(cluster) >= self.config.min_samples_for_pattern:
                # Calculate success rate
                successes = sum(1 for i in cluster if i.success)
                success_rate = successes / len(cluster)

                # Extract common patterns
                input_pattern = self._extract_common_pattern([i.input_data for i in cluster])
                output_pattern = self._extract_common_pattern(
                    [i.output_data for i in cluster if i.success]
                )

                pattern = LearnedPattern(
                    id=str(uuid.uuid4()),
                    agent_id=cluster[0].agent_id,
                    pattern_type="input_output",
                    input_pattern=input_pattern,
                    output_pattern=output_pattern,
                    confidence=success_rate,
                    sample_count=len(cluster),
                    success_rate=success_rate,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
                patterns.append(pattern)

        return patterns

    def _get_input_signature(self, input_data: dict[str, Any]) -> str:
        """Get a signature for input data structure."""
        # Use sorted keys as signature
        keys = sorted(input_data.keys())
        return ":".join(keys)

    def _extract_common_pattern(self, data_list: list[dict[str, Any]]) -> dict[str, Any]:
        """Extract common pattern from list of data dicts."""
        if not data_list:
            return {}

        # Find common keys
        common_keys = set(data_list[0].keys())
        for data in data_list[1:]:
            common_keys &= set(data.keys())

        # Extract common values or mark as variable
        pattern = {}
        for key in common_keys:
            values = [data.get(key) for data in data_list]
            unique_values = set(str(v) for v in values)

            if len(unique_values) == 1:
                # Constant value
                pattern[key] = values[0]
            else:
                # Variable value - store type
                pattern[key] = {"_type": type(values[0]).__name__, "_variable": True}

        return pattern

    def _patterns_match(self, p1: LearnedPattern, p2: LearnedPattern) -> bool:
        """Check if two patterns are similar enough to merge."""
        return (
            p1.agent_id == p2.agent_id
            and p1.pattern_type == p2.pattern_type
            and self._get_input_signature(p1.input_pattern)
            == self._get_input_signature(p2.input_pattern)
        )

    async def _persist_pattern(self, pattern: LearnedPattern) -> None:
        """Persist pattern to Redis."""
        redis = await self._get_redis()
        if not redis:
            return

        try:
            key = f"learning:patterns:{pattern.agent_id}"
            data = json.dumps(
                {
                    "id": pattern.id,
                    "pattern_type": pattern.pattern_type,
                    "input_pattern": pattern.input_pattern,
                    "output_pattern": pattern.output_pattern,
                    "confidence": pattern.confidence,
                    "sample_count": pattern.sample_count,
                    "success_rate": pattern.success_rate,
                    "created_at": pattern.created_at.isoformat(),
                    "updated_at": pattern.updated_at.isoformat(),
                }
            )

            await redis.hset(key, pattern.id, data)

        except Exception as e:
            logger.warning(f"Failed to persist pattern: {e}")

    async def get_patterns(self, agent_id: str) -> list[LearnedPattern]:
        """Get learned patterns for an agent."""
        # Return cached patterns
        if agent_id in self._patterns:
            return self._patterns[agent_id]

        # Try to load from Redis
        redis = await self._get_redis()
        if redis:
            try:
                key = f"learning:patterns:{agent_id}"
                data = await redis.hgetall(key)

                patterns = []
                for pattern_data in data.values():
                    p = json.loads(pattern_data)
                    patterns.append(
                        LearnedPattern(
                            id=p["id"],
                            agent_id=agent_id,
                            pattern_type=p["pattern_type"],
                            input_pattern=p["input_pattern"],
                            output_pattern=p["output_pattern"],
                            confidence=p["confidence"],
                            sample_count=p["sample_count"],
                            success_rate=p["success_rate"],
                            created_at=datetime.fromisoformat(p["created_at"]),
                            updated_at=datetime.fromisoformat(p["updated_at"]),
                        )
                    )

                self._patterns[agent_id] = patterns
                return patterns

            except Exception as e:
                logger.warning(f"Failed to load patterns: {e}")

        return []

    async def suggest_skill_improvements(
        self,
        agent_id: str,
    ) -> list[dict[str, Any]]:
        """
        Suggest skill improvements based on learned patterns.

        Returns suggestions for:
        - New skills to create
        - Existing skills to modify
        - Patterns to codify
        """
        patterns = await self.get_patterns(agent_id)
        suggestions = []

        for pattern in patterns:
            if pattern.confidence >= 0.8 and pattern.sample_count >= 5:
                suggestions.append(
                    {
                        "type": "new_skill",
                        "pattern_id": pattern.id,
                        "confidence": pattern.confidence,
                        "sample_count": pattern.sample_count,
                        "input_pattern": pattern.input_pattern,
                        "output_pattern": pattern.output_pattern,
                        "suggestion": f"Create skill for pattern with {pattern.success_rate:.0%} success rate",
                    }
                )

        return suggestions

    async def get_statistics(self, agent_id: str | None = None) -> dict[str, Any]:
        """Get learning statistics."""
        if agent_id:
            patterns = await self.get_patterns(agent_id)
            interactions = [i for i in self._interactions_buffer if i.agent_id == agent_id]
        else:
            patterns = []
            for p_list in self._patterns.values():
                patterns.extend(p_list)
            interactions = self._interactions_buffer

        return {
            "total_interactions": len(interactions),
            "total_patterns": len(patterns),
            "avg_confidence": (
                sum(p.confidence for p in patterns) / len(patterns) if patterns else 0
            ),
            "avg_success_rate": (
                sum(p.success_rate for p in patterns) / len(patterns) if patterns else 0
            ),
        }


# Singleton instance
_learning_manager: LearningManager | None = None


def get_learning_manager() -> LearningManager:
    """Get the global learning manager instance."""
    global _learning_manager
    if _learning_manager is None:
        _learning_manager = LearningManager()
    return _learning_manager
