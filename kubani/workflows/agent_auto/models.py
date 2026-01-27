"""Data models for the Agent Auto workflow.

This module contains all data models, scoring functions, and decision logic
for the agent_auto workflow. Organized into sections:
- Dataclasses (evaluation, workflow state, results)
- Pydantic models (for LLM structured output)
- Scoring constants and functions
- Decision functions
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# =============================================================================
# Dataclasses (Core data containers)
# =============================================================================


@dataclass
class AgentEvalMetrics:
    """Evaluation metrics from an agent evaluation run."""

    objective_accuracy: float  # 0.0 - 1.0
    skill_precision: float  # 0.0 - 1.0
    skill_recall: float  # 0.0 - 1.0
    tests_passed: int
    tests_total: int
    latency_ms: float = 0.0


@dataclass
class AgentVersion:
    """A snapshot of an agent at a specific iteration."""

    prompt_content: str  # prompt.md content
    config_content: str  # config.yaml content
    metrics: AgentEvalMetrics
    iteration: int
    created_at: datetime | None = None


@dataclass
class AgentIterationResult:
    """Result of a single eval-improve iteration."""

    iteration: int
    metrics: AgentEvalMetrics
    score: float  # Composite score
    improved: bool  # Whether this iteration improved on best
    action: Literal["continue", "stop_success", "stop_plateau", "stop_cap", "stop_regression"]
    error: str | None = None


AgentAutoStatus = Literal[
    "pending",
    "drafting",
    "creating_skills",
    "writing_files",
    "improving",
    "publishing",
    "published",
    "failed",
    "finished_failed_to_meet_accuracy",
]


@dataclass
class AgentAutoInput:
    """Input for the AgentAutoWorkflow."""

    agent_name: str
    description: str
    test_cases: list["AgentTestCase"] = field(default_factory=list)
    max_iterations: int = 5
    target_accuracy: float = 0.80
    publish_options: dict[str, Any] = field(default_factory=dict)
    notify: bool = True
    notify_channel: str = "agent-notifications"
    # Child workflow configuration for skill creation
    child_skill_max_iterations: int = 3
    child_skill_target_accuracy: float = 0.70


@dataclass
class AgentAutoState:
    """Workflow state for AgentAutoWorkflow."""

    agent_name: str
    description: str
    status: AgentAutoStatus = "pending"
    agent_path: str | None = None
    test_cases: list["AgentTestCase"] = field(default_factory=list)
    eval_history: list["AgentEvaluationResult"] = field(default_factory=list)
    iteration: int = 0
    best_version: AgentVersion | None = None
    best_score: float = 0.0
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass
class AgentAutoResult:
    """Final result of the AgentAutoWorkflow."""

    success: bool
    agent_path: str | None
    final_accuracy: float | None
    iterations_completed: int
    status: AgentAutoStatus
    final_metrics: AgentEvalMetrics | None = None
    error: str | None = None


# =============================================================================
# Pydantic Models (for LLM structured output)
# =============================================================================


class AgentSpec(BaseModel):
    """Specification for the agent to be generated (LLM structured output)."""

    name: str = Field(description="Agent name in kebab-case")
    description: str = Field(description="What this agent does")
    required_skills: list[str] = Field(description="Skills the agent needs")
    config_patterns: dict[str, Any] = Field(description="Configuration patterns")


class AgentTestCase(BaseModel):
    """A single test case for evaluating an agent."""

    name: str = Field(description="Test case name")
    prompt: str = Field(description="The user prompt to send to the agent")
    expected_skills: list[str] = Field(description="Skills that should be invoked")
    expected_output: str = Field(description="Expected output text or pattern")


class AgentEvaluationResult(BaseModel):
    """The result of a single agent evaluation run."""

    objective_accuracy: float = Field(..., description="Overall score based on test case outcomes.")
    skill_precision: float = Field(..., description="Of the skills invoked, how many were correct?")
    skill_recall: float = Field(..., description="Of the skills required, how many were invoked?")
    invoked_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    extraneous_skills: list[str] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list, description="List of failed test case names.")


class ImprovementSuggestions(BaseModel):
    """Suggestions for how to improve an agent based on an evaluation."""

    prompt_clarifications: list[str] = Field(default_factory=list)
    skill_additions: list[str] = Field(default_factory=list)
    skill_removals: list[str] = Field(default_factory=list)
    config_changes: dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# Scoring Constants
# =============================================================================

ACCURACY_WEIGHT = 0.6
PRECISION_WEIGHT = 0.2
RECALL_WEIGHT = 0.2
PLATEAU_THRESHOLD = 0.02  # 2% improvement threshold
PLATEAU_WINDOW = 2  # Check last N iterations
REGRESSION_THRESHOLD = 0.20  # 20% drop triggers regression


# =============================================================================
# Scoring Functions
# =============================================================================


def compute_agent_score(metrics: AgentEvalMetrics) -> float:
    """
    Compute composite score from metrics.

    Score = accuracy * 0.6 + precision * 0.2 + recall * 0.2

    This balances overall accuracy with skill usage metrics.
    """
    accuracy_score = metrics.objective_accuracy * ACCURACY_WEIGHT
    precision_score = metrics.skill_precision * PRECISION_WEIGHT
    recall_score = metrics.skill_recall * RECALL_WEIGHT

    return accuracy_score + precision_score + recall_score


def is_plateau(
    history: list[AgentIterationResult],
    window: int = PLATEAU_WINDOW,
    threshold: float = PLATEAU_THRESHOLD,
) -> bool:
    """
    Detect if improvement has plateaued.

    Returns True if score improvement is < threshold for the last `window` iterations.
    """
    if len(history) < window + 1:
        return False

    recent = history[-(window + 1) :]

    for i in range(1, len(recent)):
        prev_score = recent[i - 1].score
        curr_score = recent[i].score

        if prev_score > 0:
            improvement = (curr_score - prev_score) / prev_score
            if improvement >= threshold:
                return False  # Found significant improvement

    return True  # All recent improvements below threshold


def detect_regression(
    history: list[AgentIterationResult],
    current_score: float,
    threshold: float = REGRESSION_THRESHOLD,
) -> dict[str, Any]:
    """
    Detect if current score represents a significant regression.

    A regression is detected when the current score drops more than
    threshold (default 20%) below the best historical score.
    """
    if not history:
        return {
            "is_regression": False,
            "drop_percentage": 0.0,
            "best_score": current_score,
            "best_iteration": 0,
        }

    best_result = max(history, key=lambda r: r.score)
    best_score = best_result.score
    best_iteration = best_result.iteration

    if best_score <= 0:
        return {
            "is_regression": False,
            "drop_percentage": 0.0,
            "best_score": best_score,
            "best_iteration": best_iteration,
        }

    drop = (best_score - current_score) / best_score
    drop_percentage = drop * 100

    return {
        "is_regression": drop > threshold,
        "drop_percentage": drop_percentage,
        "best_score": best_score,
        "best_iteration": best_iteration,
    }


# =============================================================================
# Decision Models
# =============================================================================


@dataclass
class IterationContext:
    """
    Data context required for making decisions about the iteration loop.

    This is a pure data container that captures all the information
    needed to decide whether to continue iterating.
    """

    current_iteration: int
    max_iterations: int
    best_score: float
    target_accuracy: float
    history: list[AgentIterationResult] = field(default_factory=list)
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


def should_continue_iteration(ctx: IterationContext) -> tuple[bool, str]:
    """
    Determines if the improvement loop should continue based on the provided context.

    This is a pure function with no side effects.

    Args:
        ctx: An IterationContext object containing all necessary data.

    Returns:
        A tuple containing:
        - bool: True to continue, False to stop
        - str: The reason for the decision
    """
    if ctx.is_cancelled:
        return False, "cancelled"

    if ctx.current_iteration >= ctx.max_iterations:
        return False, "max_iterations_reached"

    if ctx.best_score >= ctx.target_accuracy:
        return False, "target_accuracy_met"

    if len(ctx.history) >= 3 and is_plateau(ctx.history):
        return False, "score_plateaued"

    return True, "continue_improving"


def make_continue_decision(ctx: IterationContext) -> ContinueDecision:
    """
    Alternative interface that returns a structured decision object.
    """
    should_continue, reason = should_continue_iteration(ctx)
    return ContinueDecision(should_continue=should_continue, reason=reason)


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Dataclasses
    "AgentEvalMetrics",
    "AgentVersion",
    "AgentIterationResult",
    "AgentAutoInput",
    "AgentAutoState",
    "AgentAutoResult",
    "IterationContext",
    "ContinueDecision",
    # Pydantic Models
    "AgentSpec",
    "AgentTestCase",
    "AgentEvaluationResult",
    "ImprovementSuggestions",
    # Type aliases
    "AgentAutoStatus",
    # Constants
    "ACCURACY_WEIGHT",
    "PRECISION_WEIGHT",
    "RECALL_WEIGHT",
    "PLATEAU_THRESHOLD",
    "PLATEAU_WINDOW",
    "REGRESSION_THRESHOLD",
    # Scoring Functions
    "compute_agent_score",
    "is_plateau",
    "detect_regression",
    # Decision Functions
    "should_continue_iteration",
    "make_continue_decision",
]
