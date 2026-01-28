"""Models for the Critic Agent."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4


class EvaluationCriteria(Enum):
    """Criteria for evaluating agent executions."""

    TASK_COMPLETION = "task_completion"  # Did the agent complete the task?
    EFFICIENCY = "efficiency"  # Was execution efficient (time, resources)?
    SAFETY = "safety"  # Were safety guidelines followed?
    QUALITY = "quality"  # Was the output high quality?


# Default weights for each criterion
DEFAULT_WEIGHTS: dict[EvaluationCriteria, float] = {
    EvaluationCriteria.TASK_COMPLETION: 0.35,
    EvaluationCriteria.EFFICIENCY: 0.20,
    EvaluationCriteria.SAFETY: 0.25,
    EvaluationCriteria.QUALITY: 0.20,
}


@dataclass
class CriticEvaluation:
    """Result of evaluating an agent execution."""

    # Identifiers
    evaluation_id: str = field(default_factory=lambda: str(uuid4()))
    execution_id: str = ""
    agent_id: str = ""
    task_description: str = ""

    # Scores (0.0 - 1.0)
    task_completion_score: float = 0.0
    efficiency_score: float = 0.0
    safety_score: float = 0.0
    quality_score: float = 0.0

    # Overall assessment
    success: bool = False
    failure_reason: str | None = None
    overall_score: float = 0.0

    # Analysis
    improvement_suggestions: list[str] = field(default_factory=list)
    identified_patterns: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)

    # Metadata
    confidence: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    evaluation_duration_ms: int = 0
    context: dict[str, Any] = field(default_factory=dict)

    def compute_overall_score(
        self, weights: dict[EvaluationCriteria, float] | None = None
    ) -> float:
        """Compute weighted overall score."""
        w = weights or DEFAULT_WEIGHTS
        self.overall_score = (
            self.task_completion_score * w[EvaluationCriteria.TASK_COMPLETION]
            + self.efficiency_score * w[EvaluationCriteria.EFFICIENCY]
            + self.safety_score * w[EvaluationCriteria.SAFETY]
            + self.quality_score * w[EvaluationCriteria.QUALITY]
        )
        return self.overall_score

    @property
    def has_improvement_opportunity(self) -> bool:
        """Check if there are improvement opportunities worth learning from."""
        return (
            len(self.improvement_suggestions) > 0
            or len(self.identified_patterns) > 0
            or (self.overall_score < 0.8 and not self.success)
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "evaluation_id": self.evaluation_id,
            "execution_id": self.execution_id,
            "agent_id": self.agent_id,
            "task_description": self.task_description,
            "scores": {
                "task_completion": self.task_completion_score,
                "efficiency": self.efficiency_score,
                "safety": self.safety_score,
                "quality": self.quality_score,
                "overall": self.overall_score,
            },
            "success": self.success,
            "failure_reason": self.failure_reason,
            "improvement_suggestions": self.improvement_suggestions,
            "identified_patterns": self.identified_patterns,
            "strengths": self.strengths,
            "weaknesses": self.weaknesses,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat(),
            "evaluation_duration_ms": self.evaluation_duration_ms,
            "context": self.context,
        }


@dataclass
class ExecutionRecord:
    """Record of an agent execution to be evaluated."""

    execution_id: str
    agent_id: str
    task_description: str
    start_time: datetime
    end_time: datetime | None = None

    # Execution details
    input_data: dict[str, Any] = field(default_factory=dict)
    output_data: dict[str, Any] = field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    # Outcome
    success: bool = False
    result_summary: str = ""

    # Metadata
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> int:
        """Calculate execution duration in milliseconds."""
        if self.end_time is None:
            return 0
        delta = self.end_time - self.start_time
        return int(delta.total_seconds() * 1000)
