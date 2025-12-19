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
        DiscordPostResult,
        HealthStatus,
        collect_and_analyze_cluster,
        post_health_confirmation,
        post_to_discord,
    )
    from k8s_monitor.models import Issue


@workflow.defn
class ClusterHealthCheckWorkflow:
    """
    Workflow that performs a cluster health check and posts results to Discord.

    This workflow:
    1. Collects and analyzes cluster health using the AI agent
    2. Posts results to Discord (always - brief confirmation if healthy, detailed if issues)
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
        workflow.logger.info("Running cluster analysis")
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

        # Step 2: Always post to Discord (different messages for healthy vs issues)
        result: dict[str, Any] = {
            "analysis_status": report.status.value,
            "discord_posted": False,
            "timestamp": report.timestamp,
            "issues_detected": len(report.issues),
            "remediation_triggered": False,
        }

        discord_options = {
            "start_to_close_timeout": timedelta(minutes=1),
            "retry_policy": RetryPolicy(
                initial_interval=timedelta(seconds=5),
                maximum_attempts=3,
            ),
        }

        if report.status == HealthStatus.HEALTHY:
            # Post brief confirmation for healthy status
            workflow.logger.info("Cluster is healthy, posting brief confirmation")
            discord_result_data: dict = await workflow.execute_activity(
                post_health_confirmation,
                report,
                **discord_options,
            )
            discord_result = DiscordPostResult.model_validate(discord_result_data)
            result["discord_posted"] = discord_result.success
            if discord_result.error:
                result["discord_error"] = discord_result.error

        else:
            # Post detailed issue report for non-healthy statuses
            workflow.logger.info(f"Status is {report.status.value}, posting detailed report")
            discord_result_data = await workflow.execute_activity(
                post_to_discord,
                report,
                **discord_options,
            )
            discord_result = DiscordPostResult.model_validate(discord_result_data)
            result["discord_posted"] = discord_result.success
            if discord_result.error:
                result["discord_error"] = discord_result.error

            # Step 3: Trigger remediation workflows for detected issues
            if report.issues:
                workflow.logger.info(f"Triggering remediation for {len(report.issues)} issue(s)")
                result["remediation_triggered"] = True
                result["remediation_workflows"] = []

                for issue in report.issues:
                    try:
                        # Start remediation as a child workflow (non-blocking)
                        workflow_id = f"remediation-{issue.id}-{workflow.now().isoformat()}"
                        workflow.logger.info(f"Starting remediation workflow: {workflow_id}")

                        # Execute child workflow (will run independently)
                        await workflow.execute_child_workflow(
                            "IssueRemediationWorkflow",
                            issue.model_dump(),
                            id=workflow_id,
                            task_queue="k8s-monitor",
                        )

                        result["remediation_workflows"].append(
                            {
                                "issue_id": issue.id,
                                "workflow_id": workflow_id,
                                "status": "started",
                            }
                        )

                    except Exception as e:
                        workflow.logger.error(
                            f"Failed to start remediation for issue {issue.id}: {e}"
                        )
                        result["remediation_workflows"].append(
                            {
                                "issue_id": issue.id,
                                "status": "failed_to_start",
                                "error": str(e),
                            }
                        )

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
