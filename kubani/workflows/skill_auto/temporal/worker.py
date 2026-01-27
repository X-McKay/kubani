"""Temporal worker for Skill Auto workflows."""

import asyncio
import logging
import os

from temporalio.client import Client
from temporalio.worker import Worker

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
from .workflow import SkillAutoWorkflow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def run_worker() -> None:
    """Run the Skill Auto workflow worker."""
    temporal_host = os.environ.get("TEMPORAL_HOST", "localhost:7233")
    temporal_namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")

    logger.info(f"Connecting to Temporal at {temporal_host}")

    client = await Client.connect(
        temporal_host,
        namespace=temporal_namespace,
    )

    # Configure sandbox to pass through modules used by workflow/activities
    from temporalio.worker.workflow_sandbox import (
        SandboxedWorkflowRunner,
        SandboxRestrictions,
    )

    worker = Worker(
        client,
        task_queue="skill-development",
        workflows=[
            SkillAutoWorkflow,
            PromoteWorkflow,
        ],
        workflow_runner=SandboxedWorkflowRunner(
            restrictions=SandboxRestrictions.default.with_passthrough_modules(
                "httpx",
                # Models module used by workflow decision logic
                "kubani.workflows.skill_auto.models",
            )
        ),
        activities=[
            # Skill Discovery
            detect_skill_overlap_activity,
            load_existing_skills_activity,
            # Skill Creation
            generate_test_cases_activity,
            infer_skill_structure_activity,
            write_skill_files_activity,
            # File I/O
            read_file_content_activity,
            write_file_content_activity,
            # Evaluation
            run_evaluation_activity,
            run_improvement_activity,
            # Notifications
            send_notification_activity,
            # Promotion
            await_approval_activity,
            check_promotion_overlap_activity,
            promote_skill_activity,
            send_promotion_request_activity,
            sync_registry_activity,
            # Hardening
            generate_harder_tests_activity,
            load_iteration_history_activity,
            revert_to_best_version_activity,
            save_iteration_result_activity,
        ],
    )

    logger.info("Starting Skill Auto worker on queue: skill-development")

    try:
        await worker.run()
    except KeyboardInterrupt:
        logger.info("Shutting down worker...")


def create_worker(client: Client, task_queue: str = "skill-development") -> Worker:
    """
    Create a Skill Auto worker with the given client.

    This is useful for testing or when you want more control over the worker lifecycle.

    Args:
        client: Temporal client
        task_queue: Task queue name (default: "skill-development")

    Returns:
        Configured Worker instance
    """
    from temporalio.worker.workflow_sandbox import (
        SandboxedWorkflowRunner,
        SandboxRestrictions,
    )

    return Worker(
        client,
        task_queue=task_queue,
        workflows=[
            SkillAutoWorkflow,
            PromoteWorkflow,
        ],
        workflow_runner=SandboxedWorkflowRunner(
            restrictions=SandboxRestrictions.default.with_passthrough_modules(
                "httpx",
                "kubani.workflows.skill_auto.models",
            )
        ),
        activities=[
            detect_skill_overlap_activity,
            load_existing_skills_activity,
            generate_test_cases_activity,
            infer_skill_structure_activity,
            write_skill_files_activity,
            read_file_content_activity,
            write_file_content_activity,
            run_evaluation_activity,
            run_improvement_activity,
            send_notification_activity,
            await_approval_activity,
            check_promotion_overlap_activity,
            promote_skill_activity,
            send_promotion_request_activity,
            sync_registry_activity,
            generate_harder_tests_activity,
            load_iteration_history_activity,
            revert_to_best_version_activity,
            save_iteration_result_activity,
        ],
    )


def main() -> None:
    """Entry point."""
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
