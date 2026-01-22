"""
Shadow Mode for Safe Migration from cluster-monitor to k8s-monitor.

Shadow mode allows running both agents in parallel to compare their
decisions without affecting production. This enables:

1. Decision logging - Record what each agent would do
2. Comparison - Compare decisions between old and new approaches
3. Gradual cutover - Slowly shift traffic to new agent

Usage:
    # Enable shadow mode via environment variable
    SHADOW_MODE_ENABLED=true

    # k8s-monitor will:
    # 1. Process events normally (if not read-only)
    # 2. Log decisions to Redis for later comparison
    # 3. Emit metrics for decision divergence

    # cluster-monitor continues to run in parallel
    # A separate comparison tool analyzes decision logs
"""

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# Shadow mode configuration
SHADOW_MODE_ENABLED = os.getenv("SHADOW_MODE_ENABLED", "false").lower() == "true"
SHADOW_READ_ONLY = os.getenv("SHADOW_READ_ONLY", "false").lower() == "true"
SHADOW_LOG_TTL_HOURS = int(os.getenv("SHADOW_LOG_TTL_HOURS", "24"))

# Redis keys for shadow mode
SHADOW_KEY_PREFIX = "shadow:k8s-monitor:"
DECISION_LOG_KEY = f"{SHADOW_KEY_PREFIX}decisions"
COMPARISON_KEY = f"{SHADOW_KEY_PREFIX}comparisons"


class DecisionType(str, Enum):
    """Types of decisions that can be compared."""

    CLASSIFICATION = "classification"
    REMEDIATION_PLAN = "remediation_plan"
    REMEDIATION_ACTION = "remediation_action"
    INVESTIGATION_RESULT = "investigation_result"


@dataclass
class Decision:
    """A recorded decision for comparison."""

    decision_id: str
    decision_type: DecisionType
    agent: str  # "k8s-monitor" or "cluster-monitor"
    event_key: str  # Unique key for the triggering event
    timestamp: datetime
    decision: dict[str, Any]
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "decision_id": self.decision_id,
            "decision_type": self.decision_type.value,
            "agent": self.agent,
            "event_key": self.event_key,
            "timestamp": self.timestamp.isoformat(),
            "decision": self.decision,
            "context": self.context,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Decision":
        """Create from dictionary."""
        return cls(
            decision_id=data["decision_id"],
            decision_type=DecisionType(data["decision_type"]),
            agent=data["agent"],
            event_key=data["event_key"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            decision=data["decision"],
            context=data.get("context", {}),
        )


@dataclass
class DecisionComparison:
    """Comparison result between two decisions."""

    event_key: str
    decision_type: DecisionType
    k8s_monitor_decision: Decision | None
    cluster_monitor_decision: Decision | None
    match: bool
    differences: list[str] = field(default_factory=list)
    compared_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "event_key": self.event_key,
            "decision_type": self.decision_type.value,
            "k8s_monitor": self.k8s_monitor_decision.to_dict()
            if self.k8s_monitor_decision
            else None,
            "cluster_monitor": self.cluster_monitor_decision.to_dict()
            if self.cluster_monitor_decision
            else None,
            "match": self.match,
            "differences": self.differences,
            "compared_at": self.compared_at.isoformat(),
        }


class ShadowModeManager:
    """
    Manages shadow mode operations for safe migration.

    Responsibilities:
    - Log decisions from k8s-monitor
    - Compare with cluster-monitor decisions
    - Track decision divergence metrics
    """

    def __init__(self):
        self._redis: aioredis.Redis | None = None
        self._enabled = SHADOW_MODE_ENABLED
        self._read_only = SHADOW_READ_ONLY

    @property
    def enabled(self) -> bool:
        """Check if shadow mode is enabled."""
        return self._enabled

    @property
    def read_only(self) -> bool:
        """Check if shadow mode is read-only (no actual remediation)."""
        return self._read_only

    async def _ensure_redis(self) -> aioredis.Redis:
        """Ensure Redis connection is established."""
        if self._redis is None:
            redis_host = os.getenv("REDIS_HOST", "redis.almckay.io")
            redis_port = os.getenv("REDIS_PORT", "6379")
            redis_password = os.getenv("REDIS_PASSWORD", "")

            if redis_password:
                redis_url = f"redis://:{redis_password}@{redis_host}:{redis_port}"
            else:
                redis_url = f"redis://{redis_host}:{redis_port}"

            self._redis = aioredis.from_url(redis_url, decode_responses=True)

        return self._redis

    def _generate_event_key(self, event: dict[str, Any]) -> str:
        """Generate a unique key for an event for matching decisions."""
        # Use namespace/kind/name/reason as the matching key
        components = [
            event.get("namespace", "default"),
            event.get("kind", "Unknown"),
            event.get("name", "unknown"),
            event.get("reason", "unknown"),
        ]
        key_str = "/".join(components)
        # Add timestamp bucket (5-minute windows) for temporal matching
        timestamp = event.get("timestamp", datetime.now(UTC).isoformat())
        if isinstance(timestamp, str):
            try:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except ValueError:
                dt = datetime.now(UTC)
        else:
            dt = timestamp

        # 5-minute bucket
        bucket = dt.replace(second=0, microsecond=0)
        bucket = bucket.replace(minute=(bucket.minute // 5) * 5)

        return f"{key_str}:{bucket.isoformat()}"

    async def log_decision(
        self,
        decision_type: DecisionType,
        event: dict[str, Any],
        decision: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> str:
        """
        Log a decision made by k8s-monitor.

        Args:
            decision_type: Type of decision
            event: The triggering event
            decision: The decision made
            context: Additional context

        Returns:
            The decision ID
        """
        if not self._enabled:
            return ""

        redis = await self._ensure_redis()

        event_key = self._generate_event_key(event)
        decision_id = hashlib.sha256(
            f"k8s-monitor:{event_key}:{decision_type.value}:{datetime.now(UTC).isoformat()}".encode()
        ).hexdigest()[:16]

        record = Decision(
            decision_id=decision_id,
            decision_type=decision_type,
            agent="k8s-monitor",
            event_key=event_key,
            timestamp=datetime.now(UTC),
            decision=decision,
            context=context or {},
        )

        # Store in Redis hash by event_key for easy matching
        key = f"{DECISION_LOG_KEY}:{event_key}:k8s-monitor:{decision_type.value}"
        await redis.setex(
            key,
            SHADOW_LOG_TTL_HOURS * 3600,
            json.dumps(record.to_dict()),
        )

        logger.debug(f"Shadow mode: logged decision {decision_id} for {event_key}")

        # Also add to sorted set for time-based queries
        await redis.zadd(
            f"{DECISION_LOG_KEY}:timeline",
            {json.dumps(record.to_dict()): datetime.now(UTC).timestamp()},
        )

        return decision_id

    async def get_comparison(
        self,
        event_key: str,
        decision_type: DecisionType,
    ) -> DecisionComparison | None:
        """
        Compare decisions between k8s-monitor and cluster-monitor.

        Args:
            event_key: The event key to compare
            decision_type: Type of decision to compare

        Returns:
            DecisionComparison if both decisions exist, None otherwise
        """
        if not self._enabled:
            return None

        redis = await self._ensure_redis()

        # Get k8s-monitor decision
        k8s_key = f"{DECISION_LOG_KEY}:{event_key}:k8s-monitor:{decision_type.value}"
        k8s_data = await redis.get(k8s_key)
        k8s_decision = Decision.from_dict(json.loads(k8s_data)) if k8s_data else None

        # Get cluster-monitor decision
        cm_key = f"{DECISION_LOG_KEY}:{event_key}:cluster-monitor:{decision_type.value}"
        cm_data = await redis.get(cm_key)
        cm_decision = Decision.from_dict(json.loads(cm_data)) if cm_data else None

        if not k8s_decision and not cm_decision:
            return None

        # Compare decisions
        match, differences = self._compare_decisions(k8s_decision, cm_decision, decision_type)

        comparison = DecisionComparison(
            event_key=event_key,
            decision_type=decision_type,
            k8s_monitor_decision=k8s_decision,
            cluster_monitor_decision=cm_decision,
            match=match,
            differences=differences,
        )

        # Store comparison
        comp_key = f"{COMPARISON_KEY}:{event_key}:{decision_type.value}"
        await redis.setex(
            comp_key,
            SHADOW_LOG_TTL_HOURS * 3600,
            json.dumps(comparison.to_dict()),
        )

        return comparison

    def _compare_decisions(
        self,
        k8s_decision: Decision | None,
        cm_decision: Decision | None,
        decision_type: DecisionType,
    ) -> tuple[bool, list[str]]:
        """
        Compare two decisions and identify differences.

        Returns:
            Tuple of (match, differences)
        """
        differences = []

        if k8s_decision is None:
            differences.append("k8s-monitor: no decision")
            return False, differences

        if cm_decision is None:
            differences.append("cluster-monitor: no decision")
            return False, differences

        k8s = k8s_decision.decision
        cm = cm_decision.decision

        if decision_type == DecisionType.CLASSIFICATION:
            # Compare severity and category
            if k8s.get("severity") != cm.get("severity"):
                differences.append(
                    f"severity: k8s={k8s.get('severity')} vs cm={cm.get('severity')}"
                )
            if k8s.get("category") != cm.get("category"):
                differences.append(
                    f"category: k8s={k8s.get('category')} vs cm={cm.get('category')}"
                )

        elif decision_type == DecisionType.REMEDIATION_PLAN:
            # Compare action type
            if k8s.get("action") != cm.get("action"):
                differences.append(f"action: k8s={k8s.get('action')} vs cm={cm.get('action')}")
            if k8s.get("requires_approval") != cm.get("requires_approval"):
                differences.append(
                    f"requires_approval: k8s={k8s.get('requires_approval')} vs cm={cm.get('requires_approval')}"
                )

        elif decision_type == DecisionType.REMEDIATION_ACTION:
            # Compare actual action taken
            if k8s.get("action") != cm.get("action"):
                differences.append(f"action: k8s={k8s.get('action')} vs cm={cm.get('action')}")
            if k8s.get("success") != cm.get("success"):
                differences.append(f"success: k8s={k8s.get('success')} vs cm={cm.get('success')}")

        elif decision_type == DecisionType.INVESTIGATION_RESULT:
            # Compare root cause determination
            if k8s.get("root_cause") != cm.get("root_cause"):
                differences.append(
                    f"root_cause: k8s={k8s.get('root_cause')} vs cm={cm.get('root_cause')}"
                )

        return len(differences) == 0, differences

    async def get_divergence_stats(self, hours: int = 24) -> dict[str, Any]:
        """
        Get statistics on decision divergence.

        Args:
            hours: Number of hours to look back

        Returns:
            Dictionary with divergence statistics
        """
        if not self._enabled:
            return {"enabled": False}

        redis = await self._ensure_redis()

        # Get recent comparisons
        cutoff = datetime.now(UTC).timestamp() - (hours * 3600)

        # Count matches and mismatches by type
        stats = {
            "enabled": True,
            "read_only": self._read_only,
            "hours_analyzed": hours,
            "by_type": {},
            "total_comparisons": 0,
            "total_matches": 0,
            "match_rate": 0.0,
        }

        for decision_type in DecisionType:
            pattern = f"{COMPARISON_KEY}:*:{decision_type.value}"
            keys = []
            async for key in redis.scan_iter(match=pattern):
                keys.append(key)

            matches = 0
            mismatches = 0

            for key in keys:
                data = await redis.get(key)
                if data:
                    comparison = json.loads(data)
                    compared_at = datetime.fromisoformat(comparison["compared_at"])
                    if compared_at.timestamp() >= cutoff:
                        if comparison["match"]:
                            matches += 1
                        else:
                            mismatches += 1

            total = matches + mismatches
            stats["by_type"][decision_type.value] = {
                "matches": matches,
                "mismatches": mismatches,
                "total": total,
                "match_rate": matches / total if total > 0 else 0.0,
            }
            stats["total_comparisons"] += total
            stats["total_matches"] += matches

        if stats["total_comparisons"] > 0:
            stats["match_rate"] = stats["total_matches"] / stats["total_comparisons"]

        return stats


# Global shadow mode manager instance
_shadow_manager: ShadowModeManager | None = None


def get_shadow_manager() -> ShadowModeManager:
    """Get the global shadow mode manager instance."""
    global _shadow_manager
    if _shadow_manager is None:
        _shadow_manager = ShadowModeManager()
    return _shadow_manager


async def log_classification_decision(
    event: dict[str, Any],
    classification: dict[str, Any],
) -> str:
    """Convenience function to log a classification decision."""
    manager = get_shadow_manager()
    return await manager.log_decision(
        DecisionType.CLASSIFICATION,
        event,
        classification,
    )


async def log_remediation_plan(
    event: dict[str, Any],
    plan: dict[str, Any],
    investigation_context: dict[str, Any] | None = None,
) -> str:
    """Convenience function to log a remediation plan decision."""
    manager = get_shadow_manager()
    return await manager.log_decision(
        DecisionType.REMEDIATION_PLAN,
        event,
        plan,
        context=investigation_context,
    )


async def log_remediation_action(
    event: dict[str, Any],
    action: dict[str, Any],
) -> str:
    """Convenience function to log a remediation action decision."""
    manager = get_shadow_manager()
    return await manager.log_decision(
        DecisionType.REMEDIATION_ACTION,
        event,
        action,
    )


def is_shadow_read_only() -> bool:
    """Check if shadow mode is read-only (no actual remediation)."""
    return get_shadow_manager().read_only


def is_shadow_enabled() -> bool:
    """Check if shadow mode is enabled."""
    return get_shadow_manager().enabled
