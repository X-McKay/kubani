"""Nexus Missions subsystem.

Provides the data layer and scheduling utilities for NexusMissions —
the user-defined background goals that drive the continuously-running
Nexus agent loop.

Submodules:
- db: asyncpg-based CRUD operations for missions and mission runs.
- scheduler: Cron-based next-run computation using croniter.
"""

from .db import (
    complete_mission_run,
    create_mission,
    create_mission_run,
    delete_mission,
    get_due_missions,
    get_mission,
    get_stale_running_missions,
    list_mission_runs,
    list_missions,
    update_mission_after_run,
    update_mission_status,
)
from .scheduler import (
    SCHEDULE_DAILY_EVENING,
    SCHEDULE_DAILY_MORNING,
    SCHEDULE_EVERY_5_MIN,
    SCHEDULE_EVERY_6_HOURS,
    SCHEDULE_EVERY_15_MIN,
    SCHEDULE_EVERY_30_MIN,
    SCHEDULE_EVERY_HOUR,
    SCHEDULE_LABELS,
    SCHEDULE_TWICE_DAILY,
    SCHEDULE_WEEKLY_MONDAY,
    compute_next_run,
    describe_schedule,
    is_valid_cron,
)

__all__ = [
    # DB operations
    "complete_mission_run",
    "create_mission",
    "create_mission_run",
    "delete_mission",
    "get_due_missions",
    "get_mission",
    "get_stale_running_missions",
    "list_mission_runs",
    "list_missions",
    "update_mission_after_run",
    "update_mission_status",
    # Scheduler
    "SCHEDULE_DAILY_EVENING",
    "SCHEDULE_DAILY_MORNING",
    "SCHEDULE_EVERY_5_MIN",
    "SCHEDULE_EVERY_6_HOURS",
    "SCHEDULE_EVERY_15_MIN",
    "SCHEDULE_EVERY_30_MIN",
    "SCHEDULE_EVERY_HOUR",
    "SCHEDULE_LABELS",
    "SCHEDULE_TWICE_DAILY",
    "SCHEDULE_WEEKLY_MONDAY",
    "compute_next_run",
    "describe_schedule",
    "is_valid_cron",
]
