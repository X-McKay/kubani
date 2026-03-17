"""
K8s Monitor Activities.

Contains the single activity that runs the coordinator agent within a
Temporal activity context. The coordinator handles all multi-agent dispatch
internally via its custom tools.
"""

import asyncio
import json
import logging
import time

from temporalio import activity

logger = logging.getLogger(__name__)


@activity.defn
async def run_coordinator_activity(input_data: dict) -> dict:
    """Run the k8s-coordinator agent for a monitoring cycle.

    This is the only activity in the k8s-monitor syndicate. The coordinator
    agent handles all dispatch to specialists internally via its custom tools
    (dispatch_diagnostics, dispatch_remediation, publish_results).

    Args:
        input_data: Dict with keys:
            - trigger: "scheduled" or "event"
            - context: Optional event payload for reactive triggers

    Returns:
        Dict with:
            - success: bool
            - result: str (coordinator output, truncated to 5000 chars)
            - trigger: str
            - duration_ms: int
    """
    from kubani.agents.k8s_coordinator import K8sCoordinatorAgent

    trigger = input_data.get("trigger", "scheduled")
    context = input_data.get("context", {})

    start = time.monotonic()

    # Build the input prompt for the coordinator
    prompt = f"Run cluster health check. Trigger: {trigger}."
    if context:
        # For reactive events, include the event payload
        prompt += f"\n\nEvent context:\n```json\n{json.dumps(context, indent=2)}\n```"
        prompt += "\n\nFocus your investigation on this specific event."

    activity.heartbeat(f"Starting coordinator (trigger={trigger})")

    # Background heartbeat to prevent Temporal from thinking the activity is stuck
    async def _heartbeat_loop():
        while True:
            await asyncio.sleep(30)
            activity.heartbeat("Coordinator still running...")

    heartbeat_task = asyncio.create_task(_heartbeat_loop())

    try:
        agent = K8sCoordinatorAgent()
        result = await agent.run(prompt)

        duration_ms = int((time.monotonic() - start) * 1000)
        activity.heartbeat("Coordinator completed")

        return {
            "success": True,
            "result": result[:5000],  # Truncate for Temporal history
            "trigger": trigger,
            "duration_ms": duration_ms,
        }
    except Exception as e:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.error(f"Coordinator failed: {e}", exc_info=True)
        return {
            "success": False,
            "result": str(e)[:2000],
            "trigger": trigger,
            "duration_ms": duration_ms,
        }
    finally:
        heartbeat_task.cancel()
