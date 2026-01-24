"""Skill Auto workflow package."""

from kubani.workflows.skill_auto.activities import (
    detect_skill_overlap,
    generate_test_cases,
    infer_skill_structure,
    load_existing_skills,
    run_evaluation,
    run_improvement,
    send_notification,
    write_skill_files,
)
from kubani.workflows.skill_auto.models import (
    EvalMetrics,
    IterationResult,
    OverlapResult,
    SkillAutoInput,
    SkillAutoResult,
    SkillAutoState,
    SkillVersion,
    compute_score,
    is_plateau,
)

__all__ = [
    # Models
    "EvalMetrics",
    "IterationResult",
    "OverlapResult",
    "SkillAutoInput",
    "SkillAutoResult",
    "SkillAutoState",
    "SkillVersion",
    "compute_score",
    "is_plateau",
    # Activities
    "detect_skill_overlap",
    "generate_test_cases",
    "infer_skill_structure",
    "load_existing_skills",
    "run_evaluation",
    "run_improvement",
    "send_notification",
    "write_skill_files",
]
