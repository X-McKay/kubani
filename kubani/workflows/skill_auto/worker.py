"""Temporal worker for Skill Auto workflows."""

import asyncio
import logging
import os

from temporalio.client import Client
from temporalio.worker import Worker

from kubani.workflows.skill_auto.activities import (
    await_approval,
    check_promotion_overlap,
    detect_skill_overlap,
    generate_harder_tests,
    generate_test_cases,
    infer_skill_structure,
    load_existing_skills,
    load_iteration_history,
    promote_skill,
    read_file_content,
    revert_to_best_version,
    run_evaluation,
    run_improvement,
    save_iteration_result,
    send_notification,
    send_promotion_request,
    sync_registry,
    write_file_content,
    write_skill_files,
)
from kubani.workflows.skill_auto.promote import PromoteWorkflow
from kubani.workflows.skill_auto.workflow import SkillAutoWorkflow

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
    # - httpx: Used by SimpleLLMClient for LLM API calls
    # - pathlib: Used by workflow for reading skill files
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
            )
        ),
        activities=[
            # Phase 1-3: Core activities
            detect_skill_overlap,
            generate_test_cases,
            infer_skill_structure,
            load_existing_skills,
            run_evaluation,
            run_improvement,
            send_notification,
            write_skill_files,
            # File I/O activities (keeps I/O out of workflow)
            read_file_content,
            write_file_content,
            # Phase 4: Promotion activities
            await_approval,
            check_promotion_overlap,
            promote_skill,
            send_promotion_request,
            sync_registry,
            # Phase 5: Hardening activities
            generate_harder_tests,
            load_iteration_history,
            revert_to_best_version,
            save_iteration_result,
        ],
    )

    logger.info("Starting Skill Auto worker on queue: skill-development")

    try:
        await worker.run()
    except KeyboardInterrupt:
        logger.info("Shutting down worker...")


def main() -> None:
    """Entry point."""
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
