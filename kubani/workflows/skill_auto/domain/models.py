"""Domain models for the skill_auto workflow.

This module contains pure data structures used for decision-making.
These models are framework-independent and can be used in unit tests
without any Temporal or external service dependencies.
"""

from dataclasses import dataclass, field
from typing import Literal

# Import existing models to re-export for convenience
from ..models import (
    ACCURACY_WEIGHT,
    LATENCY_BASELINE_MS,
    LATENCY_WEIGHT,
    PLATEAU_THRESHOLD,
    PLATEAU_WINDOW,
    REGRESSION_THRESHOLD,
    EvalMetrics,
    IterationResult,
    OverlapResult,
    PromoteWorkflowInput,
    PromoteWorkflowResult,
    SkillAutoInput,
    SkillAutoResult,
    SkillAutoState,
    SkillOverlapError,
    SkillVersion,
    compute_score,
    detect_regression,
    is_plateau,
)


@dataclass
class IterationContext:
    """
    Data context required for making decisions about the iteration loop.

    This is a pure data container that captures all the information
    needed to decide whether to continue iterating, without any
    references to workflow state or external services.
    """

    current_iteration: int
    max_iterations: int
    best_score: float
    target_accuracy: float
    history: list[IterationResult] = field(default_factory=list)
    is_cancelled: bool = False


@dataclass
class ContinueDecision:
    """Result of a continue/stop decision."""

    should_continue: bool
    reason: Literal[
        "continue_improving",
        "cancelled",
        "max_iterations_reached",
        "target_accuracy_met",
        "score_plateaued",
    ]


# Re-export all models for convenience
__all__ = [
    # New domain models
    "IterationContext",
    "ContinueDecision",
    # Re-exported from models.py
    "EvalMetrics",
    "IterationResult",
    "OverlapResult",
    "SkillAutoInput",
    "SkillAutoResult",
    "SkillAutoState",
    "SkillOverlapError",
    "SkillVersion",
    "PromoteWorkflowInput",
    "PromoteWorkflowResult",
    # Constants
    "ACCURACY_WEIGHT",
    "LATENCY_WEIGHT",
    "LATENCY_BASELINE_MS",
    "PLATEAU_THRESHOLD",
    "PLATEAU_WINDOW",
    "REGRESSION_THRESHOLD",
    # Functions
    "compute_score",
    "is_plateau",
    "detect_regression",
]
