"""Data models for the Skill Auto workflow.

This module contains all data models, scoring functions, and decision logic
for the skill_auto workflow. Organized into sections:
- Dataclasses (evaluation, workflow state, results)
- Pydantic models (for LLM structured output)
- Exceptions
- Scoring constants and functions
- Decision functions
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


@dataclass
class EvalMetrics:
    """Evaluation metrics from a skill evaluation run."""

    accuracy: float  # 0.0 - 1.0
    latency_ms: float
    tests_passed: int
    tests_total: int
    critic_confidence: float  # 0.0 - 1.0
    tokens_prompt: int = 0
    tokens_completion: int = 0


@dataclass
class SkillVersion:
    """A snapshot of a skill at a specific iteration."""

    content: str  # SKILL.md content
    test_cases: str  # test_cases.yaml content
    metrics: EvalMetrics
    iteration: int
    created_at: datetime | None = None  # Set externally to avoid workflow determinism issues


@dataclass
class OverlapResult:
    """Result of skill overlap detection."""

    has_overlap: bool
    confidence: float  # 0.0 - 1.0
    overlapping_skills: list[str]
    reasoning: str
    recommendation: Literal["proceed", "merge", "abort"]


class SkillOverlapError(Exception):
    """Raised when attempting to promote a skill that overlaps with production skills."""

    def __init__(self, skill_name: str, overlapping: list[str], reasoning: str):
        self.skill_name = skill_name
        self.overlapping = overlapping
        self.reasoning = reasoning
        super().__init__(
            f"Cannot promote '{skill_name}': overlaps with {overlapping}. "
            f"Reason: {reasoning}. "
            "Consider merging or differentiating the skill."
        )


@dataclass
class IterationResult:
    """Result of a single eval-improve iteration."""

    iteration: int
    metrics: EvalMetrics
    score: float  # Composite score (accuracy + latency)
    improved: bool  # Whether this iteration improved on best
    action: Literal["continue", "stop_success", "stop_plateau", "stop_cap", "stop_regression"]
    error: str | None = None


@dataclass
class SkillAutoInput:
    """Input for the SkillAutoWorkflow."""

    description: str
    mode: Literal["create", "improve"] = "create"
    skill_path: str | None = None  # Required for improve mode
    seed_tests_path: str | None = None
    max_iterations: int = 5
    target_accuracy: float = 0.80
    review_each_iteration: bool = False
    skip_promotion: bool = False
    notify: bool = True
    notify_channel: str = "skill-notifications"
    allow_overlap: bool = False
    create_backups: bool = True  # Create backups before modifications
    max_backups: int = 3  # Maximum number of backup files to keep per file


@dataclass
class SkillAutoState:
    """Workflow state for SkillAutoWorkflow."""

    skill_path: str
    skill_name: str = ""
    iteration: int = 0
    history: list[IterationResult] = field(default_factory=list)
    best_version: SkillVersion | None = None
    best_score: float = 0.0
    status: Literal["running", "paused", "completed", "failed"] = "running"
    overlap_warning: OverlapResult | None = None
    error: str | None = None
    started_at: datetime | None = None  # Set externally to avoid workflow determinism issues
    completed_at: datetime | None = None
    # Current skill content (kept in state to avoid filesystem I/O in workflow)
    current_content: str = ""  # SKILL.md content
    current_tests: str = ""  # test_cases.yaml content


@dataclass
class SkillAutoResult:
    """Final result of the SkillAutoWorkflow."""

    success: bool
    skill_path: str
    final_metrics: EvalMetrics | None
    iterations_completed: int
    stop_reason: str
    promoted: bool = False
    error: str | None = None


@dataclass
class PromoteWorkflowInput:
    """Input for the PromoteWorkflow."""

    skill_path: str
    skill_name: str
    skill_description: str
    metrics: EvalMetrics | None = None
    iterations: int = 0
    allow_overlap: bool = False
    notify_channel: str = "skill-notifications"
    target_category: str = "general"
    skills_root: str = "kubani/skills"


@dataclass
class PromoteWorkflowResult:
    """Result of the PromoteWorkflow."""

    promoted: bool
    promoted_path: str | None = None
    approved_by: str | None = None
    rejected_by: str | None = None
    rejection_reason: str | None = None
    error: str | None = None
    synced_to_registry: bool = False


# =============================================================================
# Pydantic Models (for LLM structured output)
# =============================================================================


class InputParam(BaseModel):
    """Schema for a skill input parameter."""

    type: str = Field(description="Data type: string, number, boolean, array, object")
    description: str = Field(description="What this parameter is for")
    required: bool = Field(default=True, description="Whether this parameter is required")


class OutputField(BaseModel):
    """Schema for a skill output field."""

    type: str = Field(description="Data type: string, number, boolean, array, object")
    description: str = Field(description="What this output contains")


class SkillExample(BaseModel):
    """Schema for a skill example."""

    name: str = Field(description="Example name")
    description: str = Field(description="What this example demonstrates")
    input: dict[str, Any] = Field(description="Example input values")
    expected_output: dict[str, Any] = Field(description="Expected output values")


class SkillSpec(BaseModel):
    """Schema for inferred skill specification."""

    name: str = Field(description="Kebab-case skill name (e.g., 'analyze-logs')")
    description: str = Field(description="One-line description of the skill")
    inputs: dict[str, InputParam] = Field(description="Input parameters")
    outputs: dict[str, OutputField] = Field(description="Output fields")
    steps: list[str] = Field(description="Step-by-step instructions")
    error_handling: list[str] = Field(description="How to handle errors")
    examples: list[SkillExample] = Field(description="2-3 example use cases")


class OverlapAnalysis(BaseModel):
    """Schema for overlap detection analysis."""

    has_overlap: bool = Field(description="Whether significant overlap exists")
    confidence: float = Field(description="Confidence score 0.0-1.0")
    overlapping_skills: list[str] = Field(description="Names of overlapping skills")
    reasoning: str = Field(description="Explanation of the analysis")
    recommendation: str = Field(description="One of: proceed, merge, abort")


# =============================================================================
# Scoring Constants
# =============================================================================


# Constants for score calculation
ACCURACY_WEIGHT = 0.7
LATENCY_WEIGHT = 0.3
LATENCY_BASELINE_MS = 3000.0  # Normalize latency against this baseline
PLATEAU_THRESHOLD = 0.02  # 2% improvement threshold
PLATEAU_WINDOW = 2  # Check last N iterations


def compute_score(metrics: EvalMetrics) -> float:
    """
    Compute composite score from metrics.

    Score = accuracy * 0.7 + normalized_latency_score * 0.3

    Where normalized_latency_score = baseline / actual (capped at 1.0)
    Faster execution gets higher latency score.
    """
    # Accuracy component (0.0 - 1.0)
    accuracy_score = metrics.accuracy * ACCURACY_WEIGHT

    # Latency component - faster is better
    # Cap at 1.0 (can't score higher than baseline)
    latency_ratio = min(LATENCY_BASELINE_MS / max(metrics.latency_ms, 1.0), 1.0)
    latency_score = latency_ratio * LATENCY_WEIGHT

    return accuracy_score + latency_score


def is_plateau(
    history: list[IterationResult],
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


# Regression detection threshold
REGRESSION_THRESHOLD = 0.20  # 20% drop triggers regression


def detect_regression(
    history: list[IterationResult],
    current_score: float,
    threshold: float = REGRESSION_THRESHOLD,
) -> dict[str, any]:
    """
    Detect if current score represents a significant regression.

    A regression is detected when the current score drops more than
    threshold (default 20%) below the best historical score.

    Args:
        history: List of previous iteration results
        current_score: Score from the current iteration
        threshold: Percentage drop that triggers regression (0.0-1.0)

    Returns:
        Dict with:
            - is_regression: bool
            - drop_percentage: float (how much score dropped)
            - best_score: float (best score from history)
            - best_iteration: int (which iteration had best score)
    """
    if not history:
        return {
            "is_regression": False,
            "drop_percentage": 0.0,
            "best_score": current_score,
            "best_iteration": 0,
        }

    # Find best score in history
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

    # Calculate drop percentage
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


# =============================================================================
# Decision Functions
# =============================================================================


def should_continue_iteration(ctx: IterationContext) -> tuple[bool, str]:
    """
    Determines if the improvement loop should continue based on the provided context.

    This is a pure function with no side effects. It takes all necessary data
    as input and returns a decision without modifying any state.

    Args:
        ctx: An IterationContext object containing all necessary data for the decision.

    Returns:
        A tuple containing:
        - bool: True to continue, False to stop
        - str: The reason for the decision
    """
    # Check cancellation first (highest priority)
    if ctx.is_cancelled:
        return False, "cancelled"

    # Check if we've hit the iteration limit
    if ctx.current_iteration >= ctx.max_iterations:
        return False, "max_iterations_reached"

    # Check if we've met the target accuracy
    if ctx.best_score >= ctx.target_accuracy:
        return False, "target_accuracy_met"

    # Check for plateau (requires enough history)
    if len(ctx.history) >= 3 and is_plateau(ctx.history):
        return False, "score_plateaued"

    return True, "continue_improving"


def make_continue_decision(ctx: IterationContext) -> ContinueDecision:
    """
    Alternative interface that returns a structured decision object.

    This provides the same logic as should_continue_iteration but
    returns a typed dataclass instead of a tuple.

    Args:
        ctx: An IterationContext object containing all necessary data.

    Returns:
        ContinueDecision with should_continue and reason fields.
    """
    should_continue, reason = should_continue_iteration(ctx)
    return ContinueDecision(should_continue=should_continue, reason=reason)


# =============================================================================
# Overlap Result Helpers
# =============================================================================


def create_no_overlap_result(reason: str = "No existing skills to compare") -> OverlapResult:
    """Create an OverlapResult indicating no overlap."""
    return OverlapResult(
        has_overlap=False,
        confidence=1.0,
        overlapping_skills=[],
        reasoning=reason,
        recommendation="proceed",
    )


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Dataclasses
    "EvalMetrics",
    "SkillVersion",
    "OverlapResult",
    "IterationResult",
    "SkillAutoInput",
    "SkillAutoState",
    "SkillAutoResult",
    "PromoteWorkflowInput",
    "PromoteWorkflowResult",
    "IterationContext",
    "ContinueDecision",
    # Pydantic Models
    "InputParam",
    "OutputField",
    "SkillExample",
    "SkillSpec",
    "OverlapAnalysis",
    # Exceptions
    "SkillOverlapError",
    # Constants
    "ACCURACY_WEIGHT",
    "LATENCY_WEIGHT",
    "LATENCY_BASELINE_MS",
    "PLATEAU_THRESHOLD",
    "PLATEAU_WINDOW",
    "REGRESSION_THRESHOLD",
    # Scoring Functions
    "compute_score",
    "is_plateau",
    "detect_regression",
    # Decision Functions
    "should_continue_iteration",
    "make_continue_decision",
    # Helpers
    "create_no_overlap_result",
]
