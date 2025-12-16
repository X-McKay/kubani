"""
Temporal workflows for automated issue remediation.

Implements the detect → investigate → fix → retry → escalate flow.
"""

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from k8s_monitor.models import (
        DiscordMessageType,
        Issue,
        RemediationRecord,
        RemediationStatus,
    )
    from k8s_monitor.remediation_activities import (
        attempt_fix_activity,
        investigate_issue_activity,
        post_remediation_discord,
        verify_issue_resolved,
    )


MAX_REMEDIATION_ATTEMPTS = 3


@workflow.defn
class IssueRemediationWorkflow:
    """
    Workflow that handles automated remediation of a detected issue.

    Flow:
    1. Post issue detection to Discord
    2. Investigate to understand the root cause
    3. Post investigation results to Discord
    4. Attempt fix
    5. Post fix results to Discord
    6. If failed, retry up to 3 times
    7. If all attempts fail, escalate to human
    """

    @workflow.run
    async def run(self, issue_dict: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the remediation workflow for an issue.

        Args:
            issue_dict: Dictionary representation of the Issue

        Returns:
            Dictionary with remediation results
        """
        # Reconstruct the Issue from dict (Temporal serialization)
        issue = Issue(**issue_dict)

        workflow.logger.info(f"Starting remediation workflow for issue: {issue.id}")

        # Initialize remediation record
        record = RemediationRecord(
            issue=issue,
            status=RemediationStatus.PENDING,
            started_at=workflow.now().isoformat(),
        )

        # Activity options
        activity_options = {
            "start_to_close_timeout": timedelta(minutes=5),
            "retry_policy": RetryPolicy(
                initial_interval=timedelta(seconds=10),
                backoff_coefficient=2.0,
                maximum_attempts=2,
            ),
        }

        discord_options = {
            "start_to_close_timeout": timedelta(minutes=1),
            "retry_policy": RetryPolicy(maximum_attempts=3),
        }

        # Step 1: Post issue detection to Discord
        workflow.logger.info("Posting issue detection to Discord")
        await workflow.execute_activity(
            post_remediation_discord,
            args=[
                DiscordMessageType.ISSUE_DETECTED.value,
                issue.model_dump(),
                None,  # No investigation yet
                None,  # No fix attempt yet
                None,  # No record yet
            ],
            **discord_options,
        )

        # Remediation loop (up to 3 attempts)
        for attempt in range(1, MAX_REMEDIATION_ATTEMPTS + 1):
            workflow.logger.info(f"Starting remediation attempt {attempt}/{MAX_REMEDIATION_ATTEMPTS}")

            # Step 2: Investigate the issue
            record.status = RemediationStatus.INVESTIGATING
            workflow.logger.info("Investigating issue")

            investigation_dict = await workflow.execute_activity(
                investigate_issue_activity,
                args=[issue.model_dump()],
                **activity_options,
            )
            record.investigations.append(investigation_dict)

            # Step 3: Post investigation results to Discord
            workflow.logger.info("Posting investigation results to Discord")
            await workflow.execute_activity(
                post_remediation_discord,
                args=[
                    DiscordMessageType.INVESTIGATION_COMPLETE.value,
                    issue.model_dump(),
                    investigation_dict,
                    None,
                    record.model_dump(),
                ],
                **discord_options,
            )

            # Step 4: Attempt the fix
            record.status = RemediationStatus.ATTEMPTING_FIX
            workflow.logger.info(f"Attempting fix (attempt {attempt})")

            fix_attempt_dict = await workflow.execute_activity(
                attempt_fix_activity,
                args=[issue.model_dump(), investigation_dict, attempt],
                **activity_options,
            )
            record.fix_attempts.append(fix_attempt_dict)

            # Step 5: Post fix attempt results to Discord
            if fix_attempt_dict.get("success"):
                workflow.logger.info("Fix succeeded!")
                record.status = RemediationStatus.SUCCESS
                record.final_outcome = "Issue resolved successfully"
                record.completed_at = workflow.now().isoformat()

                await workflow.execute_activity(
                    post_remediation_discord,
                    args=[
                        DiscordMessageType.FIX_SUCCESS.value,
                        issue.model_dump(),
                        investigation_dict,
                        fix_attempt_dict,
                        record.model_dump(),
                    ],
                    **discord_options,
                )

                return record.model_dump()

            # Fix failed
            workflow.logger.warning(f"Fix attempt {attempt} failed")
            record.status = RemediationStatus.FAILED

            await workflow.execute_activity(
                post_remediation_discord,
                args=[
                    DiscordMessageType.FIX_FAILED.value,
                    issue.model_dump(),
                    investigation_dict,
                    fix_attempt_dict,
                    record.model_dump(),
                ],
                **discord_options,
            )

            # Check if we have more attempts
            if attempt < MAX_REMEDIATION_ATTEMPTS:
                workflow.logger.info(f"Will retry. Attempts remaining: {MAX_REMEDIATION_ATTEMPTS - attempt}")
                # Brief pause before next attempt
                await workflow.sleep(timedelta(seconds=30))

        # All attempts exhausted - escalate to human
        workflow.logger.error("All remediation attempts failed. Escalating to human.")
        record.status = RemediationStatus.ESCALATED
        record.final_outcome = self._build_escalation_summary(record)
        record.completed_at = workflow.now().isoformat()

        await workflow.execute_activity(
            post_remediation_discord,
            args=[
                DiscordMessageType.ESCALATION.value,
                issue.model_dump(),
                record.investigations[-1] if record.investigations else None,
                record.fix_attempts[-1] if record.fix_attempts else None,
                record.model_dump(),
            ],
            **discord_options,
        )

        return record.model_dump()

    def _build_escalation_summary(self, record: RemediationRecord) -> str:
        """Build a summary of all attempts for escalation."""
        lines = [
            f"Issue: {record.issue.title}",
            f"Resource: {record.issue.resource_type}/{record.issue.resource_name}",
            f"Namespace: {record.issue.namespace}",
            "",
            "--- Attempted Fixes ---",
        ]

        for i, attempt in enumerate(record.fix_attempts, 1):
            lines.extend([
                f"Attempt {i}:",
                f"  Action: {attempt.get('action_taken', 'N/A')}",
                f"  Result: {attempt.get('result', 'N/A')}",
                f"  Error: {attempt.get('error_message', 'N/A')}",
                "",
            ])

        lines.append("Human intervention required.")
        return "\n".join(lines)


@workflow.defn
class HealthCheckWithRemediationWorkflow:
    """
    Extended health check workflow that triggers remediation for issues.

    1. Run health check
    2. If issues found, post to Discord
    3. For each issue, spawn a remediation child workflow
    """

    @workflow.run
    async def run(self) -> dict[str, Any]:
        """Execute health check with automatic remediation."""
        workflow.logger.info("Starting health check with remediation")

        activity_options = {
            "start_to_close_timeout": timedelta(minutes=5),
            "retry_policy": RetryPolicy(maximum_attempts=3),
        }

        # Import here to avoid circular imports
        with workflow.unsafe.imports_passed_through():
            from k8s_monitor.activities import collect_and_analyze_cluster, post_to_discord

        # Step 1: Collect and analyze cluster health
        workflow.logger.info("Running cluster analysis")
        report = await workflow.execute_activity(
            collect_and_analyze_cluster,
            **activity_options,
        )

        # Step 2: Post health report to Discord (only if issues)
        status = report.get("status", "healthy")
        issues = report.get("issues", [])

        if status in ("warning", "critical", "error"):
            workflow.logger.info(f"Issues detected: {len(issues)}")

            await workflow.execute_activity(
                post_to_discord,
                args=[report],
                start_to_close_timeout=timedelta(minutes=1),
            )

            # Step 3: Spawn remediation workflows for each issue
            remediation_results = []
            for issue_dict in issues:
                workflow.logger.info(f"Spawning remediation for issue: {issue_dict.get('id')}")

                try:
                    result = await workflow.execute_child_workflow(
                        IssueRemediationWorkflow.run,
                        args=[issue_dict],
                        id=f"remediate-{issue_dict.get('id', 'unknown')}-{workflow.now().timestamp()}",
                    )
                    remediation_results.append(result)
                except Exception as e:
                    workflow.logger.error(f"Remediation workflow failed: {e}")
                    remediation_results.append({"error": str(e)})

            return {
                "health_status": status,
                "issues_count": len(issues),
                "remediations": remediation_results,
            }

        else:
            workflow.logger.info("Cluster healthy, no remediation needed")
            return {
                "health_status": status,
                "issues_count": 0,
                "remediations": [],
            }


@workflow.defn
class ScheduledHealthCheckWithRemediationWorkflow:
    """
    Long-running workflow that schedules periodic health checks with auto-remediation.
    """

    @workflow.run
    async def run(self, interval_hours: int = 1) -> None:
        """
        Run scheduled health checks with remediation indefinitely.

        Args:
            interval_hours: Hours between health checks (default: 1).
        """
        workflow.logger.info(f"Starting scheduled health checks with remediation every {interval_hours} hour(s)")

        while True:
            workflow.logger.info("Triggering scheduled health check with remediation")

            try:
                await workflow.execute_child_workflow(
                    HealthCheckWithRemediationWorkflow.run,
                    id=f"health-check-remediate-{workflow.now().isoformat()}",
                )
            except Exception as e:
                workflow.logger.error(f"Health check with remediation failed: {e}")

            workflow.logger.info(f"Sleeping for {interval_hours} hour(s)")
            await workflow.sleep(timedelta(hours=interval_hours))
