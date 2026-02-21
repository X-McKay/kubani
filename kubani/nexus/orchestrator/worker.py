"""Nexus Orchestrator Temporal Worker.

Entry point for the Nexus syndicate's Temporal worker. This worker
processes the NexusOrchestratorWorkflow and all its activities.

Usage:
    # Start the worker
    python -m kubani.nexus.orchestrator.worker

    # Or via the CLI
    kubani nexus worker
"""

from __future__ import annotations

import asyncio
import logging
import os

from temporalio.client import Client
from temporalio.worker import Worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Worker configuration
TEMPORAL_NAMESPACE = "nexus"
TASK_QUEUE = "nexus-orchestrator"


def get_temporal_settings() -> tuple[str, str]:
    """Get Temporal connection settings from environment.

    Returns:
        Tuple of (host, namespace).
    """
    host = os.environ.get("TEMPORAL_HOST", "localhost:7233")
    namespace = os.environ.get("TEMPORAL_NAMESPACE", TEMPORAL_NAMESPACE)
    return host, namespace


def get_activities() -> list:
    """Get all activities needed by the Nexus workflows."""
    from kubani.nexus.orchestrator.activities import (
        # Agentic loop activities (Pi-style)
        agentic_step,
        execute_tool,
        list_available_tools,
        # Legacy planning activities (kept for backward compatibility)
        execute_skill_activity,
        generate_response,
        plan_response,
        # Infrastructure activities
        log_action_activity,
        notify_discord_activity,
        persist_message,
        publish_response_activity,
        recall_memories_activity,
        store_memory_activity,
    )

    return [
        # Agentic loop
        agentic_step,
        execute_tool,
        list_available_tools,
        # Legacy
        plan_response,
        execute_skill_activity,
        generate_response,
        # Infrastructure
        persist_message,
        log_action_activity,
        publish_response_activity,
        recall_memories_activity,
        store_memory_activity,
        notify_discord_activity,
    ]


def get_workflows() -> list:
    """Get all workflows for the Nexus syndicate."""
    from kubani.nexus.orchestrator.workflow import NexusOrchestratorWorkflow

    return [NexusOrchestratorWorkflow]


async def run_worker() -> None:
    """Run the Nexus Orchestrator worker."""
    temporal_host, temporal_namespace = get_temporal_settings()

    logger.info(f"Connecting to Temporal at {temporal_host}")
    logger.info(f"Namespace: {temporal_namespace}")
    logger.info(f"Task queue: {TASK_QUEUE}")

    client = await Client.connect(
        temporal_host,
        namespace=temporal_namespace,
    )

    workflows = get_workflows()
    activities = get_activities()

    logger.info(
        f"Registering {len(workflows)} workflows: "
        f"{[w.__name__ for w in workflows]}"
    )
    logger.info(f"Registering {len(activities)} activities")

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=workflows,
        activities=activities,
    )

    logger.info("Starting Nexus Orchestrator worker...")

    try:
        await worker.run()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    finally:
        logger.info("Worker shutdown complete")


async def start_nexus_workflow(
    user_id: str = "default",
    conversation_id: str = "",
) -> str:
    """Start the Nexus orchestrator workflow.

    This is called once to initialize the always-on workflow.
    Subsequent interactions happen via signals.

    Args:
        user_id: The primary user for this Nexus instance.
        conversation_id: Initial conversation ID.

    Returns:
        The workflow ID.
    """
    temporal_host, temporal_namespace = get_temporal_settings()

    client = await Client.connect(
        temporal_host,
        namespace=temporal_namespace,
    )

    from kubani.nexus.orchestrator.workflow import NexusOrchestratorWorkflow

    workflow_id = f"nexus-{user_id}"

    handle = await client.start_workflow(
        NexusOrchestratorWorkflow.run,
        {
            "user_id": user_id,
            "conversation_id": conversation_id,
        },
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )

    logger.info(f"Started Nexus workflow: {workflow_id}")
    return workflow_id


def main() -> None:
    """CLI entry point."""
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
