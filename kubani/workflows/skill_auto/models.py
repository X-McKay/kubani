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
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class OverlapResult:
    """Result of skill overlap detection."""

    has_overlap: bool
    confidence: float  # 0.0 - 1.0
    overlapping_skills: list[str]
    reasoning: str
    recommendation: Literal["proceed", "merge", "abort"]


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
    started_at: datetime = field(default_factory=datetime.now)
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
