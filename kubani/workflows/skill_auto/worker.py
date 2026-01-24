"""Temporal worker for Skill Auto workflows."""

import asyncio
import logging
import os

from temporalio.client import Client
from temporalio.worker import Worker

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

    worker = Worker(
        client,
        task_queue="skill-development",
        workflows=[SkillAutoWorkflow],
        activities=[
            detect_skill_overlap,
            generate_test_cases,
            infer_skill_structure,
            load_existing_skills,
            run_evaluation,
            run_improvement,
            send_notification,
            write_skill_files,
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
