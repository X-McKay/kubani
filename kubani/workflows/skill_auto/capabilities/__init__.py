"""Capability modules for skill_auto workflow.

Each capability module is self-contained with its prompts, logic, and a single public function.
Capabilities are pure business logic with no Temporal dependencies.

Note: Imports are added incrementally as modules are created.
"""

# Import modules as they are created
from .detect_skill_overlap import detect_skill_overlap
from .draft_skill import draft_skill
from .draft_test_cases import draft_test_cases, generate_harder_tests
from .evaluate_skill import (
    evaluate_skill,
    extract_failing_tests,
    format_evaluation_feedback,
    results_to_metrics,
)
from .improve_skill import improve_skill, revert_to_best_version
from .promote_skill import (
    await_approval,
    check_promotion_overlap,
    load_existing_skills,
    promote_skill,
    send_notification,
    send_promotion_request,
    sync_registry,
)

__all__ = [
    # Draft
    "draft_skill",
    # Test Cases
    "draft_test_cases",
    "generate_harder_tests",
    # Overlap Detection
    "detect_skill_overlap",
    # Evaluation
    "evaluate_skill",
    "results_to_metrics",
    "extract_failing_tests",
    "format_evaluation_feedback",
    # Improvement
    "improve_skill",
    "revert_to_best_version",
    # Promotion
    "promote_skill",
    "load_existing_skills",
    "check_promotion_overlap",
    "send_promotion_request",
    "await_approval",
    "sync_registry",
    "send_notification",
]
