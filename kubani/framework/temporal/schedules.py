"""Temporal schedules infrastructure for Kubani syndicates.

This module provides utilities for creating and managing scheduled Temporal workflows.
It simplifies the common patterns used by syndicates like NewsCollection and NewsDigest.

Usage:
    from kubani.framework.temporal.schedules import (
        ScheduleConfig,
        create_schedule,
        get_schedule_client,
    )

    # Define schedule configuration
    config = ScheduleConfig(
        schedule_id="news-collection-schedule",
        workflow_type=NewsCollectionWorkflow,
        workflow_id_prefix="news-collection",
        task_queue="news-syndicate",
        interval_minutes=15,
        calendar_spec=None,  # Or use CalendarSpec for cron-like scheduling
    )

    # Create or update the schedule
    await create_schedule(config)
"""

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleAlreadyRunningError,
    ScheduleIntervalSpec,
    ScheduleOverlapPolicy,
    SchedulePolicy,
    ScheduleSpec,
    ScheduleState,
)

from kubani.framework.config import get_config

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration Types
# =============================================================================


@dataclass
class ScheduleConfig:
    """Configuration for a Temporal schedule.

    Attributes:
        schedule_id: Unique identifier for the schedule
        workflow_type: The workflow class to run
        workflow_id_prefix: Prefix for generated workflow IDs
        task_queue: Task queue for the workflow
        workflow_input: Input to pass to the workflow (must be serializable)
        interval_minutes: Run every N minutes (simple interval)
        cron_expression: Cron expression (alternative to interval)
        overlap_policy: What to do if previous run is still executing
        memo: Additional metadata to attach to schedule
        search_attributes: Search attributes for visibility
    """

    schedule_id: str
    workflow_type: type[Any]
    workflow_id_prefix: str
    task_queue: str
    workflow_input: Any = None
    interval_minutes: int | None = None
    cron_expression: str | None = None
    overlap_policy: ScheduleOverlapPolicy = ScheduleOverlapPolicy.SKIP
    memo: dict[str, Any] = field(default_factory=dict)
    search_attributes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate configuration."""
        if not self.interval_minutes and not self.cron_expression:
            raise ValueError("Either interval_minutes or cron_expression must be specified")
        if self.interval_minutes and self.cron_expression:
            raise ValueError("Cannot specify both interval_minutes and cron_expression")


# =============================================================================
# Predefined Schedule Patterns
# =============================================================================


# Common schedule intervals
EVERY_15_MINUTES = 15
EVERY_30_MINUTES = 30
EVERY_HOUR = 60
EVERY_6_HOURS = 360
TWICE_DAILY = None  # Use cron: "0 9,21 * * *" for 9 AM and 9 PM

# Cron expressions for common patterns
CRON_TWICE_DAILY_9AM_9PM = "0 9,21 * * *"
CRON_DAILY_MORNING = "0 9 * * *"
CRON_DAILY_EVENING = "0 18 * * *"
CRON_WEEKLY_MONDAY = "0 9 * * 1"


# =============================================================================
# Client Management
# =============================================================================


_schedule_client: Client | None = None


async def get_schedule_client() -> Client:
    """Get or create a Temporal client for schedule operations.

    Returns:
        Temporal Client instance
    """
    global _schedule_client

    if _schedule_client is None:
        config = get_config()
        _schedule_client = await Client.connect(
            config.temporal.host,
            namespace=config.temporal.namespace,
        )

    return _schedule_client


async def close_schedule_client() -> None:
    """Close the schedule client connection."""
    global _schedule_client
    if _schedule_client:
        await _schedule_client.close()
        _schedule_client = None


# =============================================================================
# Schedule Operations
# =============================================================================


async def create_schedule(
    config: ScheduleConfig,
    client: Client | None = None,
) -> str:
    """Create or update a Temporal schedule.

    If a schedule with the same ID already exists, it will be updated.

    Args:
        config: Schedule configuration
        client: Optional Temporal client (uses default if not provided)

    Returns:
        Schedule ID

    Example:
        config = ScheduleConfig(
            schedule_id="news-collection",
            workflow_type=NewsCollectionWorkflow,
            workflow_id_prefix="news-collect",
            task_queue="news-syndicate",
            interval_minutes=15,
        )
        schedule_id = await create_schedule(config)
    """
    if client is None:
        client = await get_schedule_client()

    # Build schedule spec
    if config.interval_minutes:
        spec = ScheduleSpec(
            intervals=[ScheduleIntervalSpec(every=timedelta(minutes=config.interval_minutes))]
        )
    else:
        # Parse cron expression
        spec = ScheduleSpec(cron_expressions=[config.cron_expression])

    # Build workflow action
    # Note: Temporal automatically appends a timestamp (-YYYY-MM-DDThh:mm:ssZ) to workflow IDs
    # for scheduled workflows, so we just use the prefix directly.
    action = ScheduleActionStartWorkflow(
        config.workflow_type.run,
        config.workflow_input,
        id=config.workflow_id_prefix,
        task_queue=config.task_queue,
        memo=config.memo,
    )

    # Build policy
    policy = SchedulePolicy(overlap=config.overlap_policy)

    # Create schedule
    schedule = Schedule(
        action=action,
        spec=spec,
        policy=policy,
        state=ScheduleState(note=f"Created by Kubani for {config.workflow_id_prefix}"),
    )

    try:
        handle = await client.create_schedule(
            config.schedule_id,
            schedule,
        )
        logger.info(f"Created schedule: {config.schedule_id}")
        return config.schedule_id

    except ScheduleAlreadyRunningError:
        # Update existing schedule
        handle = client.get_schedule_handle(config.schedule_id)
        await handle.update(lambda _: schedule)
        logger.info(f"Updated existing schedule: {config.schedule_id}")
        return config.schedule_id


async def delete_schedule(
    schedule_id: str,
    client: Client | None = None,
) -> bool:
    """Delete a Temporal schedule.

    Args:
        schedule_id: ID of schedule to delete
        client: Optional Temporal client

    Returns:
        True if deleted, False if not found
    """
    if client is None:
        client = await get_schedule_client()

    try:
        handle = client.get_schedule_handle(schedule_id)
        await handle.delete()
        logger.info(f"Deleted schedule: {schedule_id}")
        return True
    except Exception as e:
        logger.warning(f"Failed to delete schedule {schedule_id}: {e}")
        return False


async def pause_schedule(
    schedule_id: str,
    note: str = "Paused by Kubani",
    client: Client | None = None,
) -> bool:
    """Pause a Temporal schedule.

    Args:
        schedule_id: ID of schedule to pause
        note: Note to attach to the pause action
        client: Optional Temporal client

    Returns:
        True if paused successfully
    """
    if client is None:
        client = await get_schedule_client()

    try:
        handle = client.get_schedule_handle(schedule_id)
        await handle.pause(note=note)
        logger.info(f"Paused schedule: {schedule_id}")
        return True
    except Exception as e:
        logger.warning(f"Failed to pause schedule {schedule_id}: {e}")
        return False


async def resume_schedule(
    schedule_id: str,
    note: str = "Resumed by Kubani",
    client: Client | None = None,
) -> bool:
    """Resume a paused Temporal schedule.

    Args:
        schedule_id: ID of schedule to resume
        note: Note to attach to the resume action
        client: Optional Temporal client

    Returns:
        True if resumed successfully
    """
    if client is None:
        client = await get_schedule_client()

    try:
        handle = client.get_schedule_handle(schedule_id)
        await handle.unpause(note=note)
        logger.info(f"Resumed schedule: {schedule_id}")
        return True
    except Exception as e:
        logger.warning(f"Failed to resume schedule {schedule_id}: {e}")
        return False


async def trigger_schedule(
    schedule_id: str,
    overlap: ScheduleOverlapPolicy | None = None,
    client: Client | None = None,
) -> bool:
    """Manually trigger a scheduled workflow.

    Args:
        schedule_id: ID of schedule to trigger
        overlap: Override overlap policy for this trigger
        client: Optional Temporal client

    Returns:
        True if triggered successfully
    """
    if client is None:
        client = await get_schedule_client()

    try:
        handle = client.get_schedule_handle(schedule_id)
        await handle.trigger(overlap=overlap)
        logger.info(f"Triggered schedule: {schedule_id}")
        return True
    except Exception as e:
        logger.warning(f"Failed to trigger schedule {schedule_id}: {e}")
        return False


async def get_schedule_info(
    schedule_id: str,
    client: Client | None = None,
) -> dict[str, Any] | None:
    """Get information about a schedule.

    Args:
        schedule_id: ID of schedule
        client: Optional Temporal client

    Returns:
        Schedule info dict or None if not found
    """
    if client is None:
        client = await get_schedule_client()

    try:
        handle = client.get_schedule_handle(schedule_id)
        description = await handle.describe()

        return {
            "id": schedule_id,
            "paused": description.schedule.state.paused,
            "note": description.schedule.state.note,
            "num_actions": description.info.num_actions,
            "num_actions_skipped_overlap": description.info.num_actions_skipped_overlap,
            "recent_actions": [
                {
                    "scheduled_at": a.scheduled_at.isoformat() if a.scheduled_at else None,
                    "started_at": a.started_at.isoformat() if a.started_at else None,
                }
                for a in description.info.recent_actions[:5]
            ],
            "next_action_times": [t.isoformat() for t in description.info.next_action_times[:3]],
        }
    except Exception as e:
        logger.warning(f"Failed to get schedule info for {schedule_id}: {e}")
        return None


async def list_schedules(
    prefix: str | None = None,
    client: Client | None = None,
) -> list[dict[str, Any]]:
    """List all schedules, optionally filtered by prefix.

    Args:
        prefix: Optional prefix to filter schedule IDs
        client: Optional Temporal client

    Returns:
        List of schedule info dicts
    """
    if client is None:
        client = await get_schedule_client()

    schedules = []
    async for schedule in client.list_schedules():
        if prefix and not schedule.id.startswith(prefix):
            continue

        schedules.append(
            {
                "id": schedule.id,
                "paused": schedule.schedule.state.paused if schedule.schedule else False,
                "note": schedule.schedule.state.note if schedule.schedule else "",
            }
        )

    return schedules


# =============================================================================
# Syndicate Schedule Helpers
# =============================================================================


async def setup_syndicate_schedules(
    syndicate_name: str,
    schedules: list[ScheduleConfig],
    client: Client | None = None,
) -> dict[str, str]:
    """Set up all schedules for a syndicate.

    Creates or updates multiple schedules at once, handling errors gracefully.

    Args:
        syndicate_name: Name of the syndicate (for logging)
        schedules: List of schedule configurations
        client: Optional Temporal client

    Returns:
        Dict mapping schedule_id to status ("created", "updated", "error")
    """
    results = {}

    for config in schedules:
        try:
            await create_schedule(config, client)
            results[config.schedule_id] = "created"
        except ScheduleAlreadyRunningError:
            results[config.schedule_id] = "updated"
        except Exception as e:
            logger.error(f"Failed to create schedule {config.schedule_id}: {e}")
            results[config.schedule_id] = f"error: {e}"

    logger.info(f"Set up {len(schedules)} schedules for syndicate {syndicate_name}")
    return results


async def teardown_syndicate_schedules(
    schedule_ids: list[str],
    client: Client | None = None,
) -> dict[str, bool]:
    """Remove all schedules for a syndicate.

    Args:
        schedule_ids: List of schedule IDs to delete
        client: Optional Temporal client

    Returns:
        Dict mapping schedule_id to success status
    """
    results = {}

    for schedule_id in schedule_ids:
        results[schedule_id] = await delete_schedule(schedule_id, client)

    return results


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Configuration
    "ScheduleConfig",
    # Predefined patterns
    "EVERY_15_MINUTES",
    "EVERY_30_MINUTES",
    "EVERY_HOUR",
    "EVERY_6_HOURS",
    "TWICE_DAILY",
    "CRON_TWICE_DAILY_9AM_9PM",
    "CRON_DAILY_MORNING",
    "CRON_DAILY_EVENING",
    "CRON_WEEKLY_MONDAY",
    # Client management
    "get_schedule_client",
    "close_schedule_client",
    # Schedule operations
    "create_schedule",
    "delete_schedule",
    "pause_schedule",
    "resume_schedule",
    "trigger_schedule",
    "get_schedule_info",
    "list_schedules",
    # Syndicate helpers
    "setup_syndicate_schedules",
    "teardown_syndicate_schedules",
]
