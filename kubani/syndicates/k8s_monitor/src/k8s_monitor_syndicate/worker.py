"""Temporal worker entry point for K8s Monitor Syndicate.

Entry points:
- k8s-monitor-worker: Runs the Temporal worker + event bridge
- k8s-monitor-schedules: Creates/manages Temporal schedules

Architecture:
    Single K8sMonitorWorkflow triggered by:
    1. Temporal Schedule (every 5 minutes) — proactive health checks
    2. Event bridge (K8S_ISSUE_DETECTED) — reactive issue response

    The workflow runs a single activity (run_coordinator_activity) which
    instantiates K8sCoordinatorAgent. The coordinator dispatches to
    specialist agents (K8sDiagnosticsAgent, RemediatorAgent) via custom tools.
"""

import asyncio
import logging
import os
import sys

from temporalio.client import Client
from temporalio.worker import Worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

TEMPORAL_NAMESPACE = "k8s-monitor"
TASK_QUEUE = "k8s-monitor"
SCHEDULE_INTERVAL_MINUTES = 5


def get_temporal_settings() -> tuple[str, str]:
    """Get Temporal connection settings from environment."""
    host = os.environ.get("TEMPORAL_HOST", "localhost:7233")
    namespace = os.environ.get("TEMPORAL_NAMESPACE", TEMPORAL_NAMESPACE)
    return host, namespace


# =============================================================================
# Registration
# =============================================================================


def get_workflows() -> list:
    """Get all workflows for this syndicate."""
    from kubani.syndicates.k8s_monitor.workflows import K8sMonitorWorkflow

    return [K8sMonitorWorkflow]


def get_activities() -> list:
    """Get all activities for this syndicate."""
    from kubani.syndicates.k8s_monitor.activities import run_coordinator_activity

    return [run_coordinator_activity]


# =============================================================================
# Worker
# =============================================================================


async def run_worker() -> None:
    """Run the K8s Monitor worker and event bridge concurrently."""
    temporal_host, temporal_namespace = get_temporal_settings()

    logger.info(f"Connecting to Temporal at {temporal_host}")
    logger.info(f"Namespace: {temporal_namespace}, Task queue: {TASK_QUEUE}")

    client = await Client.connect(temporal_host, namespace=temporal_namespace)

    workflows = get_workflows()
    activities = get_activities()

    logger.info(f"Workflows: {[w.__name__ for w in workflows]}")
    logger.info(f"Activities: {len(activities)}")

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=workflows,
        activities=activities,
    )

    # Run worker and event bridge concurrently
    logger.info("Starting K8s Monitor worker + event bridge...")
    try:
        await asyncio.gather(
            worker.run(),
            _run_event_bridge(client),
        )
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    finally:
        logger.info("Worker shutdown complete")


# =============================================================================
# Event Bridge
# =============================================================================


async def _run_event_bridge(client: Client) -> None:
    """Bridge K8s events to K8sMonitorWorkflow.

    Listens for K8S_ISSUE_DETECTED events from the event bus and starts
    K8sMonitorWorkflow with the event payload as context.
    """
    try:
        from kubani.framework.events import EventType, get_event_bus
    except ImportError:
        logger.warning("Event bus not available, skipping event bridge")
        return

    from kubani.syndicates.k8s_monitor.workflows import K8sMonitorWorkflow

    try:
        event_bus = await get_event_bus()
    except Exception as e:
        logger.warning(f"Failed to connect to event bus: {e}")
        logger.info("Event bridge disabled — running schedule-only mode")
        # Keep the coroutine alive so asyncio.gather doesn't exit
        await asyncio.Event().wait()
        return

    logger.info("Event bridge started — listening for K8S_ISSUE_DETECTED")

    async for event in event_bus.subscribe(
        EventType.K8S_ISSUE_DETECTED,
        consumer_group="k8s-monitor-bridge",
        consumer_name="bridge",
    ):
        try:
            payload = event.payload
            k8s_event = payload.get("event", {})

            resource_name = k8s_event.get("name", "unknown")
            reason = k8s_event.get("reason", "Unknown")
            severity = k8s_event.get("severity", "warning")

            logger.info(f"Event received: {reason} on {resource_name} ({severity})")

            # Start a K8sMonitorWorkflow with the event context
            await client.start_workflow(
                K8sMonitorWorkflow.run,
                {
                    "trigger": "event",
                    "context": {
                        "event_id": event.id,
                        "resource_kind": k8s_event.get("kind", "Pod"),
                        "resource_name": resource_name,
                        "namespace": k8s_event.get("namespace", "default"),
                        "reason": reason,
                        "message": k8s_event.get("message", ""),
                        "severity": severity,
                    },
                },
                id=f"k8s-monitor-reactive-{event.id}",
                task_queue=TASK_QUEUE,
            )

            # Publish to UI activity feed for immediate visibility
            try:
                from kubani.framework.ui_events import publish_activity

                await publish_activity(
                    source="k8s-monitor",
                    event_type="alert",
                    title=f"K8s event: {reason} — {resource_name}",
                    content=(
                        f"**Resource:** {k8s_event.get('kind', 'Unknown')}/"
                        f"{resource_name} in `{k8s_event.get('namespace', 'default')}`\n\n"
                        f"**Reason:** {reason}\n\n"
                        f"**Message:** {k8s_event.get('message', 'No message')}\n\n"
                        f"*Investigating...*"
                    ),
                    severity="warning" if severity != "critical" else "error",
                    metadata={
                        "event_id": event.id,
                        "reason": reason,
                        "resource_name": resource_name,
                    },
                )
            except Exception:
                pass  # Best-effort UI publishing

        except Exception as e:
            logger.error(f"Error bridging event: {e}")


# =============================================================================
# Schedule Management
# =============================================================================


async def setup_schedules() -> None:
    """Create the 5-minute health check schedule."""
    from kubani.framework.temporal import (
        ScheduleConfig,
        setup_syndicate_schedules,
    )
    from kubani.syndicates.k8s_monitor.workflows import K8sMonitorWorkflow

    temporal_host, temporal_namespace = get_temporal_settings()
    client = await Client.connect(temporal_host, namespace=temporal_namespace)

    schedules = [
        ScheduleConfig(
            schedule_id="k8s-monitor-health-check",
            workflow_type=K8sMonitorWorkflow,
            workflow_id_prefix="k8s-monitor-scheduled",
            task_queue=TASK_QUEUE,
            workflow_input={"trigger": "scheduled"},
            interval_minutes=SCHEDULE_INTERVAL_MINUTES,
            memo={"syndicate": "k8s-monitor", "check_type": "health"},
        ),
    ]

    results = await setup_syndicate_schedules("k8s-monitor", schedules, client)
    for schedule_id, status in results.items():
        logger.info(f"Schedule {schedule_id}: {status}")


async def teardown_schedules() -> None:
    """Remove K8s Monitor schedules."""
    from kubani.framework.temporal import teardown_syndicate_schedules

    temporal_host, temporal_namespace = get_temporal_settings()
    client = await Client.connect(temporal_host, namespace=temporal_namespace)

    results = await teardown_syndicate_schedules(["k8s-monitor-health-check"], client)
    for schedule_id, success in results.items():
        logger.info(f"Schedule {schedule_id}: {'removed' if success else 'not found'}")


async def list_schedules() -> None:
    """List current K8s Monitor schedules."""
    from kubani.framework.temporal import get_schedule_info

    temporal_host, temporal_namespace = get_temporal_settings()
    client = await Client.connect(temporal_host, namespace=temporal_namespace)

    for schedule_id in ["k8s-monitor-health-check"]:
        info = await get_schedule_info(schedule_id, client)
        if info:
            logger.info(f"\n{schedule_id}:")
            logger.info(f"  Paused: {info['paused']}")
            logger.info(f"  Actions: {info['num_actions']}")
            logger.info(f"  Next: {info['next_action_times']}")
        else:
            logger.info(f"\n{schedule_id}: Not found")


# =============================================================================
# CLI Entry Points
# =============================================================================


def main():
    """CLI entry point: k8s-monitor-worker."""
    asyncio.run(run_worker())


def schedules():
    """CLI entry point: k8s-monitor-schedules."""
    if len(sys.argv) < 2:
        print("Usage: k8s-monitor-schedules <setup|teardown|list>")
        sys.exit(1)

    command = sys.argv[1]
    if command == "setup":
        asyncio.run(setup_schedules())
    elif command == "teardown":
        asyncio.run(teardown_schedules())
    elif command == "list":
        asyncio.run(list_schedules())
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
