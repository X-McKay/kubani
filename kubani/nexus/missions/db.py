"""Mission database operations.

Pure functions for reading and writing NexusMission and MissionRun records
to PostgreSQL. All functions accept an asyncpg pool and return plain dicts
or typed model instances, keeping them independently testable.

Table layout (see schema_missions.sql for DDL):
- nexus_missions: One row per mission.
- nexus_mission_runs: One row per execution run.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Type alias for asyncpg pool (avoid importing asyncpg at module level)
DBPool = Any


# =========================================================================
# Mission CRUD
# =========================================================================


async def create_mission(pool: DBPool, mission_dict: dict[str, Any]) -> str:
    """Insert a new mission record.

    Args:
        pool: asyncpg connection pool.
        mission_dict: Serialized NexusMission dict.

    Returns:
        The mission ID.
    """
    import json

    await pool.execute(
        """
        INSERT INTO nexus_missions (
            id, user_id, title, goal, schedule, status,
            mcp_policy, max_tool_calls, notify_on,
            next_run_at, run_count, created_at, updated_at
        ) VALUES (
            $1, $2, $3, $4, $5, $6,
            $7, $8, $9,
            $10, $11, $12, $13
        )
        """,
        mission_dict["id"],
        mission_dict["user_id"],
        mission_dict["title"],
        mission_dict["goal"],
        mission_dict["schedule"],
        mission_dict["status"],
        mission_dict.get("mcp_policy", "nexus"),
        mission_dict.get("max_tool_calls", 20),
        json.dumps(mission_dict.get("notify_on", ["anomaly", "error"])),
        mission_dict.get("next_run_at"),
        mission_dict.get("run_count", 0),
        mission_dict.get("created_at"),
        mission_dict.get("updated_at"),
    )
    return mission_dict["id"]


async def get_mission(pool: DBPool, mission_id: str) -> dict[str, Any] | None:
    """Fetch a single mission by ID.

    Args:
        pool: asyncpg connection pool.
        mission_id: The mission ID.

    Returns:
        Mission dict or None if not found.
    """
    row = await pool.fetchrow(
        "SELECT * FROM nexus_missions WHERE id = $1",
        mission_id,
    )
    return dict(row) if row else None


async def list_missions(
    pool: DBPool,
    user_id: str,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """List missions for a user, optionally filtered by status.

    Args:
        pool: asyncpg connection pool.
        user_id: The user whose missions to list.
        status: Optional status filter (e.g., "active").

    Returns:
        List of mission dicts ordered by created_at descending.
    """
    if status:
        rows = await pool.fetch(
            """
            SELECT * FROM nexus_missions
            WHERE user_id = $1 AND status = $2
            ORDER BY created_at DESC
            """,
            user_id,
            status,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT * FROM nexus_missions
            WHERE user_id = $1
            ORDER BY created_at DESC
            """,
            user_id,
        )
    return [dict(r) for r in rows]


async def update_mission_status(
    pool: DBPool,
    mission_id: str,
    status: str,
) -> None:
    """Update the status of a mission.

    Args:
        pool: asyncpg connection pool.
        mission_id: The mission ID.
        status: New status value.
    """
    await pool.execute(
        """
        UPDATE nexus_missions
        SET status = $1, updated_at = $2
        WHERE id = $3
        """,
        status,
        datetime.now(timezone.utc),
        mission_id,
    )


async def delete_mission(pool: DBPool, mission_id: str, user_id: str) -> bool:
    """Delete a mission (and its run history via CASCADE).

    Args:
        pool: asyncpg connection pool.
        mission_id: The mission ID.
        user_id: The owning user (safety check).

    Returns:
        True if a row was deleted, False if not found.
    """
    result = await pool.execute(
        "DELETE FROM nexus_missions WHERE id = $1 AND user_id = $2",
        mission_id,
        user_id,
    )
    return result == "DELETE 1"


async def get_due_missions(pool: DBPool) -> list[dict[str, Any]]:
    """Fetch all active missions whose next_run_at is in the past.

    Called by the heartbeat workflow to determine which missions to fire.

    Args:
        pool: asyncpg connection pool.

    Returns:
        List of mission dicts ready to execute.
    """
    rows = await pool.fetch(
        """
        SELECT * FROM nexus_missions
        WHERE status = 'active'
          AND (next_run_at IS NULL OR next_run_at <= $1)
        ORDER BY next_run_at ASC NULLS FIRST
        """,
        datetime.now(timezone.utc),
    )
    return [dict(r) for r in rows]


async def update_mission_after_run(
    pool: DBPool,
    mission_id: str,
    next_run_at: datetime,
) -> None:
    """Update last_run_at, next_run_at, and run_count after a mission fires.

    Args:
        pool: asyncpg connection pool.
        mission_id: The mission ID.
        next_run_at: The computed next execution time.
    """
    await pool.execute(
        """
        UPDATE nexus_missions
        SET last_run_at = $1,
            next_run_at = $2,
            run_count   = run_count + 1,
            updated_at  = $1
        WHERE id = $3
        """,
        datetime.now(timezone.utc),
        next_run_at,
        mission_id,
    )


# =========================================================================
# Mission Run CRUD
# =========================================================================


async def create_mission_run(
    pool: DBPool,
    run_dict: dict[str, Any],
) -> str:
    """Insert a new mission run record.

    Args:
        pool: asyncpg connection pool.
        run_dict: Serialized MissionRun dict.

    Returns:
        The run ID.
    """
    await pool.execute(
        """
        INSERT INTO nexus_mission_runs (
            id, mission_id, user_id, status,
            tool_calls_made, found_anomaly,
            notification_text, error_message,
            started_at
        ) VALUES (
            $1, $2, $3, $4,
            $5, $6,
            $7, $8,
            $9
        )
        """,
        run_dict["id"],
        run_dict["mission_id"],
        run_dict["user_id"],
        run_dict.get("status", "running"),
        run_dict.get("tool_calls_made", 0),
        run_dict.get("found_anomaly", False),
        run_dict.get("notification_text", ""),
        run_dict.get("error_message", ""),
        run_dict.get("started_at"),
    )
    return run_dict["id"]


async def complete_mission_run(
    pool: DBPool,
    run_id: str,
    status: str,
    tool_calls_made: int,
    found_anomaly: bool,
    notification_text: str,
    error_message: str,
    duration_ms: int,
) -> None:
    """Mark a mission run as complete with outcome details.

    Args:
        pool: asyncpg connection pool.
        run_id: The run ID.
        status: Final status (completed / failed / timed_out).
        tool_calls_made: Number of tool calls consumed.
        found_anomaly: Whether the agent flagged an anomaly.
        notification_text: Text sent to the user (empty if no notification).
        error_message: Error details (empty if successful).
        duration_ms: Wall-clock duration in milliseconds.
    """
    await pool.execute(
        """
        UPDATE nexus_mission_runs
        SET status            = $1,
            tool_calls_made   = $2,
            found_anomaly     = $3,
            notification_text = $4,
            error_message     = $5,
            completed_at      = $6,
            duration_ms       = $7
        WHERE id = $8
        """,
        status,
        tool_calls_made,
        found_anomaly,
        notification_text,
        error_message,
        datetime.now(timezone.utc),
        duration_ms,
        run_id,
    )


async def list_mission_runs(
    pool: DBPool,
    mission_id: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """List recent runs for a mission.

    Args:
        pool: asyncpg connection pool.
        mission_id: The mission ID.
        limit: Maximum number of runs to return.

    Returns:
        List of run dicts ordered by started_at descending.
    """
    rows = await pool.fetch(
        """
        SELECT * FROM nexus_mission_runs
        WHERE mission_id = $1
        ORDER BY started_at DESC
        LIMIT $2
        """,
        mission_id,
        limit,
    )
    return [dict(r) for r in rows]


async def get_stale_running_missions(
    pool: DBPool,
    stale_threshold_minutes: int = 30,
) -> list[dict[str, Any]]:
    """Find mission runs that are stuck in 'running' state.

    Used by the startup recovery process to detect crashed runs.

    Args:
        pool: asyncpg connection pool.
        stale_threshold_minutes: Runs older than this are considered stale.

    Returns:
        List of stale run dicts.
    """
    from datetime import timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=stale_threshold_minutes)
    rows = await pool.fetch(
        """
        SELECT r.*, m.user_id as mission_user_id
        FROM nexus_mission_runs r
        JOIN nexus_missions m ON r.mission_id = m.id
        WHERE r.status = 'running'
          AND r.started_at < $1
        """,
        cutoff,
    )
    return [dict(r) for r in rows]
