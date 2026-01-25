"""Skill Auto workflow package."""

from .activities import (
    # Phase 4: Promotion activities
    await_approval,
    check_promotion_overlap,
    # Phase 1-3: Core activities
    detect_skill_overlap,
    # Phase 5: Hardening activities
    generate_harder_tests,
    generate_test_cases,
    infer_skill_structure,
    load_existing_skills,
    load_iteration_history,
    promote_skill,
    revert_to_best_version,
    run_evaluation,
    run_improvement,
    save_iteration_result,
    send_notification,
    send_promotion_request,
    sync_registry,
    write_skill_files,
)
from .models import (
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
from .promote import PromoteWorkflow
from .workflow import SkillAutoWorkflow

__all__ = [
    # Workflows
    "SkillAutoWorkflow",
    "PromoteWorkflow",
    # Models
    "EvalMetrics",
    "IterationResult",
    "OverlapResult",
    "PromoteWorkflowInput",
    "PromoteWorkflowResult",
    "SkillAutoInput",
    "SkillAutoResult",
    "SkillAutoState",
    "SkillOverlapError",
    "SkillVersion",
    "compute_score",
    "detect_regression",
    "is_plateau",
    # Phase 1-3: Core activities
    "detect_skill_overlap",
    "generate_test_cases",
    "infer_skill_structure",
    "load_existing_skills",
    "run_evaluation",
    "run_improvement",
    "send_notification",
    "write_skill_files",
    # Phase 4: Promotion activities
    "await_approval",
    "check_promotion_overlap",
    "promote_skill",
    "send_promotion_request",
    "sync_registry",
    # Phase 5: Hardening activities
    "generate_harder_tests",
    "load_iteration_history",
    "revert_to_best_version",
    "save_iteration_result",
]
