"""Data models for the Skill Auto workflow."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


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
