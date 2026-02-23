"""Nexus Orchestrator Temporal Worker.

Entry point for the Nexus syndicate's Temporal worker. This worker
processes the NexusOrchestratorWorkflow, NexusHeartbeatWorkflow, and all
their activities.

Usage:
    # Start the worker
    python -m kubani.nexus.orchestrator.worker

    # Or via the CLI
    kubani nexus worker

    # Register the heartbeat Temporal Schedule (run once on cluster setup)
    python -c "from kubani.nexus.orchestrator.worker import register_heartbeat_schedule; import asyncio; asyncio.run(register_heartbeat_schedule())"
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

# Temporal Schedule ID for the heartbeat workflow
HEARTBEAT_SCHEDULE_ID = "nexus-heartbeat"


def get_temporal_settings() -> tuple[str, str]:
    """Get Temporal connection settings from environment.

    Returns:
        Tuple of (host, namespace).
    """
    host = os.environ.get("TEMPORAL_HOST", "localhost:7233")
    namespace = os.environ.get("TEMPORAL_NAMESPACE", TEMPORAL_NAMESPACE)
    return host, namespace


def get_activities() -> list:
    """Get all activities needed by the Nexus workflows.

    Returns:
        List of all registered activity functions, including:
        - Agentic loop activities (run_agent_turn, run_mission_agent_turn)
        - Mission management activities (CRUD + heartbeat dispatch)
        - Legacy planning activities (backward compatibility)
        - Infrastructure activities (persist, publish, memory, discord)
    """
    from kubani.nexus.missions.activities import (
        create_mission_activity,
        delete_mission_activity,
        get_due_missions_activity,
        list_mission_runs_activity,
        list_missions_activity,
        recover_stale_runs_activity,
        update_mission_run_activity,
        update_mission_status_activity,
    )
    from kubani.nexus.orchestrator.activities import (
        # Agentic loop (Strands-based)
        run_agent_turn,
        run_mission_agent_turn,
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
        run_agent_turn,
        run_mission_agent_turn,
        # Mission management
        get_due_missions_activity,
        update_mission_run_activity,
        create_mission_activity,
        update_mission_status_activity,
        delete_mission_activity,
        list_missions_activity,
        list_mission_runs_activity,
        recover_stale_runs_activity,
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
    """Get all workflows for the Nexus syndicate.

    Returns:
        List of all registered workflow classes:
        - NexusOrchestratorWorkflow: the always-on user-facing agent
        - NexusHeartbeatWorkflow: the cron-driven mission dispatcher
    """
    from kubani.nexus.orchestrator.heartbeat_workflow import NexusHeartbeatWorkflow
    from kubani.nexus.orchestrator.workflow import NexusOrchestratorWorkflow

    return [NexusOrchestratorWorkflow, NexusHeartbeatWorkflow]


async def run_worker() -> None:
    """Run the Nexus Orchestrator worker.

    On startup, performs stale run recovery to reset any mission runs that
    were interrupted by a previous worker crash.
    """
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


async def register_heartbeat_schedule() -> None:
    """Register the NexusHeartbeatWorkflow as a Temporal Schedule.

    Creates a cron-based schedule that fires NexusHeartbeatWorkflow every
    minute. This is idempotent — safe to call multiple times.

    The schedule uses SKIP overlap policy: if a previous heartbeat tick is
    still running when the next minute arrives, the new tick is skipped.
    This prevents pile-up under load.

    Call this once during cluster setup or initial deployment.
    """
    from datetime import timedelta

    from temporalio.client import (
        Schedule,
        ScheduleActionStartWorkflow,
        ScheduleIntervalSpec,
        ScheduleOverlapPolicy,
        SchedulePolicy,
        ScheduleSpec,
        ScheduleState,
    )

    temporal_host, temporal_namespace = get_temporal_settings()
    client = await Client.connect(temporal_host, namespace=temporal_namespace)

    from kubani.nexus.orchestrator.heartbeat_workflow import NexusHeartbeatWorkflow

    # Check if schedule already exists (idempotency)
    try:
        handle = client.get_schedule_handle(HEARTBEAT_SCHEDULE_ID)
        await handle.describe()
        logger.info(
            f"Heartbeat schedule '{HEARTBEAT_SCHEDULE_ID}' already exists. "
            "No changes made."
        )
        return
    except Exception:
        pass  # Schedule does not exist yet — create it

    await client.create_schedule(
        HEARTBEAT_SCHEDULE_ID,
        Schedule(
            action=ScheduleActionStartWorkflow(
                NexusHeartbeatWorkflow.run,
                {},
                id=f"{HEARTBEAT_SCHEDULE_ID}-run",
                task_queue=TASK_QUEUE,
            ),
            spec=ScheduleSpec(
                intervals=[ScheduleIntervalSpec(every=timedelta(minutes=1))],
            ),
            policy=SchedulePolicy(
                overlap=ScheduleOverlapPolicy.SKIP,
            ),
            state=ScheduleState(
                note=(
                    "Fires NexusHeartbeatWorkflow every minute to dispatch "
                    "due NexusMissions to NexusOrchestratorWorkflow instances."
                ),
            ),
        ),
    )
    logger.info(
        f"Registered heartbeat schedule '{HEARTBEAT_SCHEDULE_ID}' "
        "(every 1 minute, SKIP overlap)"
    )


def main() -> None:
    """CLI entry point."""
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
