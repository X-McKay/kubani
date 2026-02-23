"""Nexus Heartbeat Workflow.

A lightweight Temporal workflow that runs on a cron schedule (every minute)
and dispatches due NexusMissions to the appropriate NexusOrchestratorWorkflow
instances via the ``proactive_mission`` signal.

Design principles:
- This workflow is a pure dispatcher. It does no agentic work itself.
- All actual mission execution happens inside NexusOrchestratorWorkflow,
  preserving the existing audit trail, isolation, and HITL guarantees.
- The workflow is idempotent: dispatching the same mission twice is safe
  because update_mission_run_activity advances next_run_at immediately
  after dispatch, preventing double-firing.
- Failures in individual mission dispatches are logged but do not abort
  the entire heartbeat run — other missions continue to be processed.

Temporal Schedule:
    Schedule ID : nexus-heartbeat
    Cron        : every minute (``* * * * *``)
    Overlap     : SKIP (if previous run is still active, skip this tick)
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    pass  # No non-deterministic imports needed at module level

logger = logging.getLogger(__name__)

# Fast retry for lightweight DB/infra activities
_INFRA_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=3,
)


@workflow.defn
class NexusHeartbeatWorkflow:
    """Cron-driven dispatcher that fires due NexusMissions.

    This workflow is registered as a Temporal Schedule with a one-minute
    cadence. On each tick it:

    1. Queries the database for active missions whose ``next_run_at`` is
       in the past (via ``get_due_missions_activity``).
    2. For each due mission, signals the owning user's
       ``NexusOrchestratorWorkflow`` with a ``proactive_mission`` signal.
    3. Immediately advances the mission's ``next_run_at`` so it is not
       re-dispatched on the next tick (via ``update_mission_run_activity``).

    The workflow is intentionally simple and fast. It should complete in
    well under 30 seconds even with many missions.
    """

    @workflow.run
    async def run(self, input_data: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute one heartbeat tick.

        Args:
            input_data: Unused. Present for Temporal schedule compatibility.

        Returns:
            Dict with ``dispatched``: int (number of missions signalled).
        """
        workflow.logger.info("NexusHeartbeatWorkflow: tick started")

        # Step 1: Fetch due missions
        due_result = await workflow.execute_activity(
            "get_due_missions_activity",
            args=[{}],
            start_to_close_timeout=timedelta(seconds=15),
            retry_policy=_INFRA_RETRY,
        )
        due_missions: list[dict[str, Any]] = due_result.get("missions", [])

        if not due_missions:
            workflow.logger.info("NexusHeartbeatWorkflow: no missions due")
            return {"dispatched": 0}

        workflow.logger.info(
            f"NexusHeartbeatWorkflow: dispatching {len(due_missions)} mission(s)"
        )

        dispatched = 0
        for mission in due_missions:
            mission_id = mission.get("id", "unknown")
            user_id = mission.get("user_id", "default")

            try:
                # Step 2: Signal the user's orchestrator workflow
                orchestrator_workflow_id = f"nexus-{user_id}"
                handle = workflow.get_external_workflow_handle(orchestrator_workflow_id)
                await handle.signal("proactive_mission", mission)
                workflow.logger.info(
                    f"Signalled {orchestrator_workflow_id} for mission {mission_id}"
                )

                # Step 3: Advance next_run_at so we don't re-dispatch
                await workflow.execute_activity(
                    "update_mission_run_activity",
                    args=[{
                        "mission_id": mission_id,
                        "schedule": mission.get("schedule", "0 * * * *"),
                    }],
                    start_to_close_timeout=timedelta(seconds=10),
                    retry_policy=_INFRA_RETRY,
                )

                dispatched += 1

            except Exception as exc:
                # Log but continue — a single failure must not block others
                workflow.logger.error(
                    f"Failed to dispatch mission {mission_id}: {exc}"
                )

        workflow.logger.info(
            f"NexusHeartbeatWorkflow: tick complete, dispatched={dispatched}"
        )
        return {"dispatched": dispatched}
