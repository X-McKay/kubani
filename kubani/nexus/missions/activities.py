"""Mission Temporal Activities.

These activities are registered alongside the existing orchestrator activities
and handle the data-layer operations needed by the heartbeat workflow and
the mission turn logic.

All activities are pure functions: they accept serializable dicts and return
serializable dicts, making them independently testable without Temporal.

Activities:
- get_due_missions_activity: Fetch missions ready to execute.
- update_mission_run_activity: Record that a mission was dispatched.
- create_mission_activity: Create a new mission.
- update_mission_status_activity: Pause / resume / delete a mission.
- list_missions_activity: List missions for a user.
- list_mission_runs_activity: List recent runs for a mission.
- recover_stale_runs_activity: Reset stuck 'running' runs on worker startup.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from temporalio import activity

logger = logging.getLogger(__name__)

_DB_URL_DEFAULT = "postgresql://kubani:kubani@localhost:5432/kubani_nexus"


def _db_url() -> str:
    return os.environ.get("NEXUS_DATABASE_URL", _DB_URL_DEFAULT)


# =========================================================================
# Heartbeat Workflow Activities
# =========================================================================


@activity.defn
async def get_due_missions_activity(input_data: dict[str, Any]) -> dict[str, Any]:
    """Fetch all active missions whose next_run_at is in the past.

    Called every minute by NexusHeartbeatWorkflow to determine which
    missions to dispatch.

    Args:
        input_data: Empty dict (no parameters needed).

    Returns:
        Dict with ``missions``: list of mission dicts.
    """
    from kubani.nexus.db import create_pool
    from kubani.nexus.missions.db import get_due_missions

    activity.heartbeat("Querying due missions")
    pool = await create_pool(_db_url())
    try:
        missions = await get_due_missions(pool)
        logger.info(f"Found {len(missions)} due mission(s)")
        return {"missions": missions}
    finally:
        await pool.close()


@activity.defn
async def update_mission_run_activity(input_data: dict[str, Any]) -> dict[str, Any]:
    """Record that a mission was dispatched and compute its next run time.

    Called by NexusHeartbeatWorkflow immediately after signalling the
    orchestrator workflow, so the mission is not re-dispatched on the
    next heartbeat tick.

    Args:
        input_data: Dict with:
            - mission_id: str
            - schedule: str (cron expression)

    Returns:
        Dict with ``next_run_at``: ISO 8601 string.
    """
    from kubani.nexus.db import create_pool
    from kubani.nexus.missions.db import update_mission_after_run
    from kubani.nexus.missions.scheduler import compute_next_run

    mission_id = input_data["mission_id"]
    schedule = input_data["schedule"]

    next_run_at = compute_next_run(schedule)
    pool = await create_pool(_db_url())
    try:
        await update_mission_after_run(pool, mission_id, next_run_at)
        logger.info(f"Mission {mission_id} next run: {next_run_at.isoformat()}")
        return {"next_run_at": next_run_at.isoformat()}
    finally:
        await pool.close()


# =========================================================================
# Mission Management Activities (used by mission management skills)
# =========================================================================


@activity.defn
async def create_mission_activity(input_data: dict[str, Any]) -> dict[str, Any]:
    """Create a new mission in the database.

    Args:
        input_data: Serialized NexusMission dict. Required fields:
            - user_id, title, goal
            Optional: schedule, mcp_policy, max_tool_calls, notify_on.

    Returns:
        Dict with ``mission_id`` and ``next_run_at``.
    """
    import uuid
    from datetime import datetime, timezone

    from kubani.nexus.db import create_pool
    from kubani.nexus.missions.db import create_mission
    from kubani.nexus.missions.scheduler import compute_next_run, is_valid_cron

    # Validate cron expression
    schedule = input_data.get("schedule", "0 * * * *")
    if not is_valid_cron(schedule):
        return {"error": f"Invalid cron expression: {schedule}"}

    mission_id = input_data.get("id") or f"mission-{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    next_run_at = compute_next_run(schedule)

    mission_dict = {
        "id": mission_id,
        "user_id": input_data["user_id"],
        "title": input_data["title"],
        "goal": input_data["goal"],
        "schedule": schedule,
        "status": "active",
        "mcp_policy": input_data.get("mcp_policy", "nexus"),
        "max_tool_calls": min(int(input_data.get("max_tool_calls", 20)), 50),
        "notify_on": input_data.get("notify_on", ["anomaly", "error"]),
        "next_run_at": next_run_at.isoformat(),
        "run_count": 0,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }

    pool = await create_pool(_db_url())
    try:
        await create_mission(pool, mission_dict)
        logger.info(f"Created mission {mission_id} for user {input_data['user_id']}")
        return {"mission_id": mission_id, "next_run_at": next_run_at.isoformat()}
    finally:
        await pool.close()


@activity.defn
async def update_mission_status_activity(input_data: dict[str, Any]) -> dict[str, Any]:
    """Update the status of a mission (pause / resume / complete).

    Args:
        input_data: Dict with:
            - mission_id: str
            - status: str (active / paused / completed)
            - user_id: str (for ownership verification)

    Returns:
        Dict with ``success``: bool.
    """
    from kubani.nexus.db import create_pool
    from kubani.nexus.missions.db import get_mission, update_mission_status

    mission_id = input_data["mission_id"]
    new_status = input_data["status"]
    user_id = input_data["user_id"]

    pool = await create_pool(_db_url())
    try:
        mission = await get_mission(pool, mission_id)
        if not mission:
            return {"success": False, "error": f"Mission {mission_id} not found"}
        if mission["user_id"] != user_id:
            return {"success": False, "error": "Permission denied"}

        await update_mission_status(pool, mission_id, new_status)
        logger.info(f"Mission {mission_id} status → {new_status}")
        return {"success": True}
    finally:
        await pool.close()


@activity.defn
async def delete_mission_activity(input_data: dict[str, Any]) -> dict[str, Any]:
    """Permanently delete a mission and its run history.

    Args:
        input_data: Dict with:
            - mission_id: str
            - user_id: str (for ownership verification)

    Returns:
        Dict with ``success``: bool.
    """
    from kubani.nexus.db import create_pool
    from kubani.nexus.missions.db import delete_mission

    mission_id = input_data["mission_id"]
    user_id = input_data["user_id"]

    pool = await create_pool(_db_url())
    try:
        deleted = await delete_mission(pool, mission_id, user_id)
        if deleted:
            logger.info(f"Deleted mission {mission_id}")
        else:
            logger.warning(f"Mission {mission_id} not found or permission denied")
        return {"success": deleted}
    finally:
        await pool.close()


@activity.defn
async def list_missions_activity(input_data: dict[str, Any]) -> dict[str, Any]:
    """List missions for a user.

    Args:
        input_data: Dict with:
            - user_id: str
            - status: str | None (optional filter)

    Returns:
        Dict with ``missions``: list of mission dicts.
    """
    from kubani.nexus.db import create_pool
    from kubani.nexus.missions.db import list_missions

    user_id = input_data["user_id"]
    status = input_data.get("status")

    pool = await create_pool(_db_url())
    try:
        missions = await list_missions(pool, user_id, status=status)
        return {"missions": missions}
    finally:
        await pool.close()


@activity.defn
async def list_mission_runs_activity(input_data: dict[str, Any]) -> dict[str, Any]:
    """List recent runs for a mission.

    Args:
        input_data: Dict with:
            - mission_id: str
            - limit: int (default 20)

    Returns:
        Dict with ``runs``: list of run dicts.
    """
    from kubani.nexus.db import create_pool
    from kubani.nexus.missions.db import list_mission_runs

    mission_id = input_data["mission_id"]
    limit = int(input_data.get("limit", 20))

    pool = await create_pool(_db_url())
    try:
        runs = await list_mission_runs(pool, mission_id, limit=limit)
        return {"runs": runs}
    finally:
        await pool.close()


@activity.defn
async def recover_stale_runs_activity(input_data: dict[str, Any]) -> dict[str, Any]:
    """Reset mission runs stuck in 'running' state after a worker crash.

    Called once on worker startup. Any run that has been in 'running'
    state for more than ``stale_threshold_minutes`` is marked as 'failed'
    with an appropriate error message.

    Args:
        input_data: Dict with:
            - stale_threshold_minutes: int (default 30)

    Returns:
        Dict with ``recovered``: int (number of runs reset).
    """
    from kubani.nexus.db import create_pool
    from kubani.nexus.missions.db import complete_mission_run, get_stale_running_missions

    threshold = int(input_data.get("stale_threshold_minutes", 30))
    pool = await create_pool(_db_url())
    try:
        stale_runs = await get_stale_running_missions(pool, threshold)
        for run in stale_runs:
            await complete_mission_run(
                pool,
                run_id=run["id"],
                status="failed",
                tool_calls_made=run.get("tool_calls_made", 0),
                found_anomaly=False,
                notification_text="",
                error_message="Run was interrupted by a worker restart.",
                duration_ms=0,
            )
            logger.warning(f"Recovered stale run {run['id']} for mission {run['mission_id']}")

        logger.info(f"Startup recovery: reset {len(stale_runs)} stale run(s)")
        return {"recovered": len(stale_runs)}
    finally:
        await pool.close()
