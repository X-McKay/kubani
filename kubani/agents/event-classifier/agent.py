"""
Event Classifier Agent - Event classification by severity and category.

Classifies events using known patterns and LLM intelligence.
Can be used for any event stream (K8s events, logs, metrics, etc.)

Usage:
    from kubani.agents.event_classifier import EventClassifierAgent

    agent = EventClassifierAgent()
    classification = await agent.classify_event(event)
"""

import logging
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from kubani.agents._base import KubaniAgent

logger = logging.getLogger(__name__)


class ClassificationMethod(str, Enum):
    """Method used to classify an event."""

    PATTERN = "pattern"  # Matched known pattern
    LLM = "llm"  # Classified by LLM
    DEFAULT = "default"  # Default classification


class EventClassification(BaseModel):
    """Classification of a Kubernetes event."""

    severity: str = Field(description="low, medium, high, critical")
    is_actionable: bool = Field(description="Whether this needs remediation")
    category: str = Field(description="Event category")
    reason: str = Field(description="Why this classification was made")
    method: ClassificationMethod = Field(
        default=ClassificationMethod.PATTERN,
        description="How this classification was determined",
    )
    confidence: float = Field(
        default=1.0,
        description="Confidence in this classification (0.0-1.0)",
    )
    suggested_action: str = Field(
        default="",
        description="Suggested remediation action",
    )


@dataclass
class K8sEvent:
    """Kubernetes event from the cluster."""

    type: str  # Normal, Warning
    reason: str  # e.g., "CrashLoopBackOff"
    message: str
    namespace: str
    name: str  # Resource name
    kind: str  # Pod, Deployment, etc.
    first_timestamp: str | None = None
    last_timestamp: str | None = None
    count: int = 1

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "K8sEvent":
        """Create from dictionary."""
        involved_object = data.get("involvedObject", {})
        return cls(
            type=data.get("type", "Normal"),
            reason=data.get("reason", "Unknown"),
            message=data.get("message", ""),
            namespace=involved_object.get("namespace", "default"),
            name=involved_object.get("name", "unknown"),
            kind=involved_object.get("kind", "Unknown"),
            first_timestamp=data.get("firstTimestamp"),
            last_timestamp=data.get("lastTimestamp"),
            count=data.get("count", 1),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "type": self.type,
            "reason": self.reason,
            "message": self.message,
            "namespace": self.namespace,
            "name": self.name,
            "kind": self.kind,
            "first_timestamp": self.first_timestamp,
            "last_timestamp": self.last_timestamp,
            "count": self.count,
        }


class EventClassifierAgent(KubaniAgent):
    """
    Classifies events by severity and category.

    Uses a tiered classification approach:
    1. Known patterns (fast, high confidence)
    2. LLM classification (intelligent, for unknown patterns)
    3. Default classification (fallback)
    """

    AGENT_DIR = Path(__file__).parent

    def __init__(self, agent_dir: Path | None = None):
        """Initialize the Event Classifier agent."""
        super().__init__(agent_dir)

        # Load patterns from config
        self._patterns = self.config.get("patterns", {})
        self._benign_patterns = set(self.config.get("benign_patterns", []))
        self._ignored_resources = self.config.get("ignored_resources", [])

        # Classification statistics
        self._stats = {
            "pattern_matches": 0,
            "llm_classifications": 0,
            "default_classifications": 0,
        }

    def should_ignore_event(self, event: K8sEvent) -> bool:
        """Check if an event should be ignored."""
        # Skip normal events
        if event.type == "Normal":
            return True

        # Skip benign patterns
        if event.reason in self._benign_patterns:
            logger.debug(f"Skipping benign pattern: {event.reason}")
            return True

        # Skip ignored resources
        for pattern in self._ignored_resources:
            if re.search(pattern, event.name):
                logger.debug(f"Skipping ignored resource: {event.name}")
                return True

        return False

    async def classify_event(self, event: K8sEvent) -> EventClassification:
        """
        Classify a Kubernetes event.

        Args:
            event: The Kubernetes event to classify

        Returns:
            EventClassification with severity, category, and actionability
        """
        # Check known patterns first
        if event.reason in self._patterns:
            pattern = self._patterns[event.reason]
            self._stats["pattern_matches"] += 1
            severity = pattern.get("severity", "medium")

            return EventClassification(
                severity=severity,
                is_actionable=severity in ("high", "critical", "medium"),
                category=pattern.get("category", "other"),
                reason=f"Matched known pattern: {event.reason}",
                method=ClassificationMethod.PATTERN,
                confidence=1.0,
            )

        # Try LLM classification for unknown patterns
        if self.config.get("classifier", {}).get("enable_llm_classification", True):
            llm_result = await self._classify_with_llm(event)
            if llm_result:
                self._stats["llm_classifications"] += 1
                return llm_result

        # Default classification for Warning events
        self._stats["default_classifications"] += 1

        if event.type == "Warning":
            return EventClassification(
                severity="medium",
                is_actionable=True,
                category="warning",
                reason=f"Warning event: {event.reason}",
                method=ClassificationMethod.DEFAULT,
                confidence=0.5,
            )

        return EventClassification(
            severity="low",
            is_actionable=False,
            category="normal",
            reason="Normal event, no action needed",
            method=ClassificationMethod.DEFAULT,
            confidence=1.0,
        )

    async def _classify_with_llm(self, event: K8sEvent) -> EventClassification | None:
        """Classify an event using LLM."""
        import json

        prompt = f"""Classify this Kubernetes event:

Event Details:
- Type: {event.type}
- Reason: {event.reason}
- Message: {event.message}
- Resource: {event.kind}/{event.name} in namespace {event.namespace}
- Occurrence Count: {event.count}

Respond with JSON only."""

        try:
            result = await self.run(prompt)

            # Parse JSON from response
            json_start = result.find("{")
            json_end = result.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                data = json.loads(result[json_start:json_end])

                return EventClassification(
                    severity=data.get("severity", "medium"),
                    is_actionable=data.get("is_actionable", True),
                    category=data.get("category", "other"),
                    reason=data.get("reasoning", f"LLM classified: {event.reason}"),
                    method=ClassificationMethod.LLM,
                    confidence=0.8,
                    suggested_action=data.get("suggested_action", ""),
                )
        except Exception as e:
            logger.warning(f"LLM classification failed: {e}")

        return None

    def get_stats(self) -> dict[str, int]:
        """Get classification statistics."""
        return dict(self._stats)

    async def on_skill_complete(self, skill_name: str, result: dict[str, Any]) -> None:
        """Record skill outcomes for learning."""
        await self.record_outcome(skill_name, result)
