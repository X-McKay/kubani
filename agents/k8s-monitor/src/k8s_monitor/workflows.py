"""
Temporal workflows for the Kubernetes monitoring agent.

Workflows define the orchestration logic - what activities to run,
in what order, and how to handle failures.
"""

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

# Import activity stubs (not the actual implementations)
with workflow.unsafe.imports_passed_through():
    from k8s_monitor.activities import (
        ClusterHealthReport,
        HealthStatus,
        collect_and_analyze_cluster,
    )


@workflow.defn
class ClusterHealthCheckWorkflow:
    """
    Workflow that performs a cluster health check.

    This workflow:
    1. Collects and analyzes cluster health using the AI agent swarm
    2. The swarm's DiscordNotifierAgent handles posting results to Discord
    3. Triggers remediation workflows for any detected issues
    4. Handles retries and failures gracefully
    """

    @workflow.run
    async def run(self) -> dict[str, Any]:
        """
        Execute the cluster health check workflow.

        Returns:
            Dictionary with workflow results including status and any errors.
        """
        workflow.logger.info("Starting ClusterHealthCheckWorkflow")

        # Activity options with retry policy
        activity_options = {
            "start_to_close_timeout": timedelta(minutes=5),
            "retry_policy": RetryPolicy(
                initial_interval=timedelta(seconds=10),
                backoff_coefficient=2.0,
                maximum_interval=timedelta(minutes=1),
                maximum_attempts=3,
            ),
        }

        # Step 1: Collect and analyze cluster health
        # The swarm handles Discord notification internally via DiscordNotifierAgent
        workflow.logger.info("Running cluster analysis (swarm handles Discord notification)")
        report_data: dict = await workflow.execute_activity(
            collect_and_analyze_cluster,
            **activity_options,
        )
        # Temporal returns activities as dicts, convert to model
        report = ClusterHealthReport.model_validate(report_data)

        # Handle analysis errors
        if report.error and not report.summary:
            workflow.logger.error(f"Analysis failed: {report.error}")
            # Create a new report with error message (Pydantic models are immutable)
            report = ClusterHealthReport(
                summary=f"⚠️ **Analysis Error**\n\nFailed to analyze cluster: {report.error}",
                status=HealthStatus.ERROR,
                timestamp=report.timestamp,
                error=report.error,
            )

        # Build result summary
        result: dict[str, Any] = {
            "analysis_status": report.status.value,
            "discord_posted": True,  # Swarm handles Discord posting
            "timestamp": report.timestamp,
            "issues_detected": len(report.issues),
            "remediation_triggered": False,
        }

        # Step 2: Log detected issues (remediation handled by federated agents)
        # NOTE: IssueRemediationWorkflow was removed - Healer agent handles remediation
        # via skills-based architecture with event bus
        if report.status != HealthStatus.HEALTHY and report.issues:
            workflow.logger.info(
                f"Detected {len(report.issues)} issue(s) - "
                "federated Healer agent will handle remediation via event bus"
            )
            result["issues_logged"] = [
                {"issue_id": issue.id, "severity": issue.severity.value} for issue in report.issues
            ]

        workflow.logger.info(f"Workflow completed: {result}")
        return result


@workflow.defn
class ScheduledHealthCheckWorkflow:
    """
    Long-running workflow that schedules periodic health checks.

    This workflow runs continuously and triggers health checks
    at regular intervals (default: every hour).
    """

    @workflow.run
    async def run(self, interval_hours: int = 1) -> None:
        """
        Run scheduled health checks indefinitely.

        Args:
            interval_hours: Hours between health checks (default: 1).
        """
        workflow.logger.info(f"Starting scheduled health checks every {interval_hours} hour(s)")

        while True:
            # Run the health check as a child workflow
            workflow.logger.info("Triggering scheduled health check")

            try:
                await workflow.execute_child_workflow(
                    ClusterHealthCheckWorkflow.run,
                    id=f"health-check-{workflow.now().isoformat()}",
                )
            except Exception as e:
                workflow.logger.error(f"Health check failed: {e}")

            # Wait for the next interval
            workflow.logger.info(f"Sleeping for {interval_hours} hour(s)")
            await workflow.sleep(timedelta(hours=interval_hours))
