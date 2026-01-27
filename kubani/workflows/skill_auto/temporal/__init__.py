"""Temporal-specific code for skill_auto workflow.

Contains activities (thin wrappers around capabilities), workflows, and worker configuration.
"""

from .activities import (
    await_approval_activity,
    check_promotion_overlap_activity,
    detect_skill_overlap_activity,
    generate_harder_tests_activity,
    generate_test_cases_activity,
    infer_skill_structure_activity,
    load_existing_skills_activity,
    load_iteration_history_activity,
    promote_skill_activity,
    read_file_content_activity,
    revert_to_best_version_activity,
    run_evaluation_activity,
    run_improvement_activity,
    save_iteration_result_activity,
    send_notification_activity,
    send_promotion_request_activity,
    sync_registry_activity,
    write_file_content_activity,
    write_skill_files_activity,
)
from .promote import PromoteWorkflow
from .worker import create_worker
from .workflow import SkillAutoWorkflow

__all__ = [
    # Activities
    "infer_skill_structure_activity",
    "generate_test_cases_activity",
    "generate_harder_tests_activity",
    "detect_skill_overlap_activity",
    "check_promotion_overlap_activity",
    "run_evaluation_activity",
    "run_improvement_activity",
    "revert_to_best_version_activity",
    "promote_skill_activity",
    "load_existing_skills_activity",
    "send_promotion_request_activity",
    "await_approval_activity",
    "sync_registry_activity",
    "send_notification_activity",
    "read_file_content_activity",
    "write_file_content_activity",
    "write_skill_files_activity",
    "save_iteration_result_activity",
    "load_iteration_history_activity",
    # Workflows
    "SkillAutoWorkflow",
    "PromoteWorkflow",
    # Worker
    "create_worker",
]
