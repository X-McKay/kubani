"""Temporal worker entry point for K8s Monitor Syndicate.

This module provides the main entry points for running the K8s Monitor:
- worker: Runs the Temporal worker that processes workflows
- schedules: Creates and manages Temporal schedules

The K8s Monitor uses two workflow patterns:
- K8sRemediationWorkflow: Deterministic remediation sequence (Workflow pattern)
- K8sInvestigationSwarm: Emergent investigation behavior (Swarm pattern)

Usage:
    # Start the worker
    k8s-monitor-worker

    # Initialize schedules (one-time setup)
    k8s-monitor-schedules

Architecture:
    The worker runs both workflows on the same task queue.
    K8sRemediationWorkflow handles routine issues with known remediation paths.
    K8sInvestigationSwarm handles complex issues requiring multi-agent investigation.
"""

import asyncio
import logging
import os
import sys

from temporalio.client import Client
from temporalio.worker import Worker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# =============================================================================
# Worker Configuration
# =============================================================================

TASK_QUEUE = "k8s-monitor"


def get_temporal_settings() -> tuple[str, str]:
    """Get Temporal connection settings from environment."""
    host = os.environ.get("TEMPORAL_HOST", "localhost:7233")
    namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")
    return host, namespace


# =============================================================================
# Activity Registration
# =============================================================================


def get_activities() -> list:
    """Get all activities needed by the workflows."""
    from kubani.framework.temporal import (
        cache_workflow_state_activity,
        check_article_exists_activity,
        classify_event_activity,
        get_cached_workflow_state_activity,
        get_swarm_context_activity,
        query_knowledge_activity,
        query_learnings_activity,
        remediate_issue_activity,
        run_agent_activity,
        run_agent_for_swarm_activity,
        store_knowledge_activity,
        store_learning_activity,
        update_swarm_context_activity,
    )

    return [
        # Core agent activities
        run_agent_activity,
        run_agent_for_swarm_activity,
        classify_event_activity,
        remediate_issue_activity,
        # Memory activities
        store_learning_activity,
        query_learnings_activity,
        store_knowledge_activity,
        query_knowledge_activity,
        check_article_exists_activity,
        # Swarm context activities
        get_swarm_context_activity,
        update_swarm_context_activity,
        # Cache activities
        cache_workflow_state_activity,
        get_cached_workflow_state_activity,
    ]


# =============================================================================
# Workflow Registration
# =============================================================================


def get_workflows() -> list:
    """Get all workflows for this syndicate."""
    from kubani.syndicates.k8s_monitor.workflows import (
        K8sInvestigationSwarm,
        K8sRemediationWorkflow,
    )

    return [
        K8sRemediationWorkflow,
        K8sInvestigationSwarm,
    ]


# =============================================================================
# Worker Entry Point
# =============================================================================


async def run_worker() -> None:
    """Run the K8s Monitor syndicate worker.

    This worker processes both K8sRemediationWorkflow and K8sInvestigationSwarm
    on the k8s-monitor task queue.
    """
    temporal_host, temporal_namespace = get_temporal_settings()

    logger.info(f"Connecting to Temporal at {temporal_host}")
    logger.info(f"Namespace: {temporal_namespace}")
    logger.info(f"Task queue: {TASK_QUEUE}")

    # Connect to Temporal
    client = await Client.connect(
        temporal_host,
        namespace=temporal_namespace,
    )

    # Get workflows and activities
    workflows = get_workflows()
    activities = get_activities()

    logger.info(f"Registering {len(workflows)} workflows: {[w.__name__ for w in workflows]}")
    logger.info(f"Registering {len(activities)} activities")

    # Create and run the worker
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=workflows,
        activities=activities,
    )

    logger.info("Starting K8s Monitor worker...")

    try:
        await worker.run()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    finally:
        logger.info("Worker shutdown complete")


# =============================================================================
# Schedule Management
# =============================================================================


async def setup_schedules() -> None:
    """Create Temporal schedules for the K8s Monitor workflows.

    Creates schedules for:
    1. health-check-schedule: Periodic cluster health checks
    """
    from kubani.framework.temporal import (
        EVERY_HOUR,
        ScheduleConfig,
        setup_syndicate_schedules,
    )
    from kubani.syndicates.k8s_monitor.workflows import K8sRemediationWorkflow

    temporal_host, temporal_namespace = get_temporal_settings()

    logger.info(f"Connecting to Temporal at {temporal_host}")

    client = await Client.connect(
        temporal_host,
        namespace=temporal_namespace,
    )

    # Define schedules
    # Note: Most K8s monitoring is event-driven, but we can schedule
    # periodic health checks as remediation workflows
    schedules = [
        # Periodic health check (runs remediation workflow with health-check input)
        ScheduleConfig(
            schedule_id="k8s-health-check-schedule",
            workflow_type=K8sRemediationWorkflow,
            workflow_id_prefix="k8s-health-check",
            task_queue=TASK_QUEUE,
            workflow_input={
                "event_id": "scheduled-health-check",
                "resource_kind": "Cluster",
                "resource_name": "health",
                "namespace": "kube-system",
                "reason": "ScheduledHealthCheck",
                "message": "Periodic cluster health verification",
                "severity": "info",
                "auto_remediate": False,  # Health checks don't auto-remediate
            },
            interval_minutes=EVERY_HOUR,
            memo={"syndicate": "k8s-monitor", "workflow": "health-check"},
        ),
    ]

    # Create schedules
    results = await setup_syndicate_schedules("k8s-monitor", schedules, client)

    for schedule_id, status in results.items():
        logger.info(f"Schedule {schedule_id}: {status}")

    logger.info("Schedule setup complete")


async def teardown_schedules() -> None:
    """Remove K8s Monitor schedules."""
    from kubani.framework.temporal import teardown_syndicate_schedules

    temporal_host, temporal_namespace = get_temporal_settings()

    client = await Client.connect(
        temporal_host,
        namespace=temporal_namespace,
    )

    schedule_ids = [
        "k8s-health-check-schedule",
    ]

    results = await teardown_syndicate_schedules(schedule_ids, client)

    for schedule_id, success in results.items():
        status = "removed" if success else "not found"
        logger.info(f"Schedule {schedule_id}: {status}")


async def list_schedules() -> None:
    """List current K8s Monitor schedules."""
    from kubani.framework.temporal import get_schedule_info

    temporal_host, temporal_namespace = get_temporal_settings()

    client = await Client.connect(
        temporal_host,
        namespace=temporal_namespace,
    )

    schedule_ids = [
        "k8s-health-check-schedule",
    ]

    for schedule_id in schedule_ids:
        info = await get_schedule_info(schedule_id, client)
        if info:
            logger.info(f"\n{schedule_id}:")
            logger.info(f"  Paused: {info['paused']}")
            logger.info(f"  Actions: {info['num_actions']}")
            logger.info(f"  Next: {info['next_action_times']}")
        else:
            logger.info(f"\n{schedule_id}: Not found")


# =============================================================================
# Event Bridge (for K8s events to Temporal workflows)
# =============================================================================


async def run_event_bridge() -> None:
    """Bridge K8s events to Temporal workflows.

    Listens for K8s events from the event bus and starts appropriate
    Temporal workflows:
    - Simple issues → K8sRemediationWorkflow
    - Complex issues → K8sInvestigationSwarm
    """
    from kubani.framework.events import EventType, get_event_bus
    from kubani.syndicates.k8s_monitor.workflows import (
        K8sInvestigationSwarm,
        K8sRemediationWorkflow,
    )

    temporal_host, temporal_namespace = get_temporal_settings()

    logger.info(f"Starting event bridge to Temporal at {temporal_host}")

    client = await Client.connect(
        temporal_host,
        namespace=temporal_namespace,
    )

    event_bus = await get_event_bus()

    # Subscribe to K8s issue events
    async for event in event_bus.subscribe(
        EventType.K8S_ISSUE_DETECTED,
        consumer_group="k8s-monitor-bridge",
        consumer_name="bridge",
    ):
        try:
            payload = event.payload
            k8s_event = payload.get("event", {})

            # Determine which workflow to use based on severity/complexity
            severity = k8s_event.get("severity", "warning")
            is_complex = _is_complex_issue(k8s_event)

            if is_complex:
                # Use investigation swarm for complex issues
                logger.info(f"Starting investigation swarm for {k8s_event.get('name')}")
                await client.start_workflow(
                    K8sInvestigationSwarm.run,
                    {
                        "trigger_event_id": event.id,
                        "resource_kind": k8s_event.get("kind", "Pod"),
                        "resource_name": k8s_event.get("name", "unknown"),
                        "namespace": k8s_event.get("namespace", "default"),
                        "symptoms": [k8s_event.get("reason", "Unknown")],
                        "priority": 2 if severity == "critical" else 3,
                    },
                    id=f"investigation-{event.id}",
                    task_queue=TASK_QUEUE,
                )
            else:
                # Use remediation workflow for simple issues
                logger.info(f"Starting remediation workflow for {k8s_event.get('name')}")
                await client.start_workflow(
                    K8sRemediationWorkflow.run,
                    {
                        "event_id": event.id,
                        "resource_kind": k8s_event.get("kind", "Pod"),
                        "resource_name": k8s_event.get("name", "unknown"),
                        "namespace": k8s_event.get("namespace", "default"),
                        "reason": k8s_event.get("reason", "Unknown"),
                        "message": k8s_event.get("message", ""),
                        "severity": severity,
                    },
                    id=f"remediation-{event.id}",
                    task_queue=TASK_QUEUE,
                )

        except Exception as e:
            logger.error(f"Error bridging event to workflow: {e}")


def _is_complex_issue(event: dict) -> bool:
    """Determine if an issue is complex enough for investigation swarm.

    Complex issues include:
    - Cascading failures (multiple related resources)
    - Unknown or unusual reasons
    - Critical severity
    - Repeated failures
    """
    reason = event.get("reason", "")
    severity = event.get("severity", "warning")
    message = event.get("message", "")

    # Complex patterns
    complex_reasons = [
        "NodeNotReady",
        "NetworkNotReady",
        "EvictionThresholdMet",
        "SystemOOM",
        "Rescheduled",  # Often indicates deeper issues
    ]

    # Check for complexity indicators
    if severity == "critical":
        return True
    if reason in complex_reasons:
        return True
    if "cascade" in message.lower() or "multiple" in message.lower():
        return True
    if event.get("count", 1) > 5:  # Repeated event
        return True

    return False


# =============================================================================
# CLI Entry Points
# =============================================================================


def main() -> None:
    """Main entry point for worker."""
    asyncio.run(run_worker())


def schedules() -> None:
    """Entry point for schedule management."""
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "setup":
            asyncio.run(setup_schedules())
        elif cmd == "teardown":
            asyncio.run(teardown_schedules())
        elif cmd == "list":
            asyncio.run(list_schedules())
        else:
            print(f"Unknown command: {cmd}")
            print("Usage: k8s-monitor-schedules [setup|teardown|list]")
            sys.exit(1)
    else:
        # Default to setup
        asyncio.run(setup_schedules())


def bridge() -> None:
    """Entry point for event bridge."""
    asyncio.run(run_event_bridge())


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "schedules":
            sys.argv = sys.argv[1:]  # Remove 'schedules' from args
            schedules()
        elif cmd == "bridge":
            bridge()
        else:
            main()
    else:
        main()
