"""
K8s Monitor Workflow.

Thin Temporal workflow shell that runs the coordinator agent. Triggered by:
1. Temporal Schedule (every 5 minutes)
2. Event bridge (K8S_ISSUE_DETECTED events)

The workflow delegates all work to run_coordinator_activity, which instantiates
and runs the K8sCoordinatorAgent.
"""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from kubani.syndicates.k8s_monitor.activities import run_coordinator_activity


@workflow.defn
class K8sMonitorWorkflow:
    """Runs a k8s monitoring cycle via the coordinator agent."""

    @workflow.run
    async def run(self, input_data: dict) -> dict:
        """Execute a single monitoring cycle.

        Args:
            input_data: Dict with keys:
                - trigger: "scheduled" or "event"
                - context: Optional event payload (for reactive triggers)

        Returns:
            Dict with keys:
                - success: bool
                - result: str (coordinator output summary)
        """
        trigger = input_data.get("trigger", "scheduled")
        workflow.logger.info(f"Starting k8s monitor cycle (trigger={trigger})")

        result = await workflow.execute_activity(
            run_coordinator_activity,
            args=[input_data],
            start_to_close_timeout=timedelta(minutes=10),
            heartbeat_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=5),
                maximum_interval=timedelta(minutes=2),
                maximum_attempts=2,
                non_retryable_error_types=["ValueError"],
            ),
        )

        workflow.logger.info(f"Monitor cycle complete (success={result.get('success')})")
        return result
