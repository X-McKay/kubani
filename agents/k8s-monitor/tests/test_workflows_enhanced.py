"""Tests for enhanced Temporal workflows."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from k8s_monitor.models import ClusterHealthReport, HealthStatus, Issue
from k8s_monitor.workflows import ClusterHealthCheckWorkflow


class TestEnhancedClusterHealthCheckWorkflow:
    """Tests for the enhanced ClusterHealthCheckWorkflow."""

    @pytest.mark.asyncio
    async def test_healthy_cluster_posts_confirmation(self) -> None:
        """Healthy cluster should be handled by swarm (no separate Discord post)."""
        # Mock the workflow execution context
        workflow_instance = ClusterHealthCheckWorkflow()

        # Mock report data
        healthy_report = ClusterHealthReport(
            summary="All systems operational",
            status=HealthStatus.HEALTHY,
            timestamp=datetime.now(UTC).isoformat(),
            issues=[],
        )

        with (
            patch(
                "k8s_monitor.workflows.workflow.execute_activity",
                new_callable=AsyncMock,
            ) as mock_execute,
            patch("k8s_monitor.workflows.workflow.logger") as _mock_logger,
        ):
            # Only one activity call - collect_and_analyze_cluster
            # Discord notification is handled internally by the swarm's DiscordNotifierAgent
            mock_execute.return_value = healthy_report.model_dump()

            result = await workflow_instance.run()

            # Verify only health check activity was called (swarm handles Discord)
            assert mock_execute.call_count == 1

            # Verify result
            assert result["analysis_status"] == "healthy"
            assert result["discord_posted"] is True  # Swarm handles this
            assert result["issues_detected"] == 0
            assert result["remediation_triggered"] is False

    @pytest.mark.asyncio
    async def test_issues_detected_logs_for_healer(self) -> None:
        """Issues detected should be logged for federated Healer agent.

        Note: Remediation is handled by the federated Healer agent via event bus,
        not via child workflows. The workflow only logs detected issues.
        """
        workflow_instance = ClusterHealthCheckWorkflow()

        # Mock report with issues
        issue1 = Issue(
            id="issue-1",
            title="Pod CrashLoopBackOff",
            description="Pod is crashing",
            severity=HealthStatus.CRITICAL,
            resource_type="Pod",
            resource_name="app-backend",
            namespace="production",
            detected_at=datetime.now(UTC).isoformat(),
        )

        issue2 = Issue(
            id="issue-2",
            title="Node NotReady",
            description="Node is not ready",
            severity=HealthStatus.CRITICAL,
            resource_type="Node",
            resource_name="worker-1",
            namespace="default",
            detected_at=datetime.now(UTC).isoformat(),
        )

        unhealthy_report = ClusterHealthReport(
            summary="Critical issues detected",
            status=HealthStatus.CRITICAL,
            timestamp=datetime.now(UTC).isoformat(),
            issues=[issue1, issue2],
        )

        with (
            patch(
                "k8s_monitor.workflows.workflow.execute_activity",
                new_callable=AsyncMock,
            ) as mock_execute_activity,
            patch("k8s_monitor.workflows.workflow.logger") as _mock_logger,
        ):
            # Only one activity call - collect_and_analyze_cluster
            # Discord notification is handled by the swarm's DiscordNotifierAgent
            mock_execute_activity.return_value = unhealthy_report.model_dump()

            result = await workflow_instance.run()

            # Verify only health check activity was called (swarm handles Discord)
            assert mock_execute_activity.call_count == 1

            # Verify result - remediation is handled by federated Healer agent
            assert result["analysis_status"] == "critical"
            assert result["discord_posted"] is True  # Swarm handles this
            assert result["issues_detected"] == 2
            # Remediation is handled by federated agents, not workflow
            assert result["remediation_triggered"] is False

            # Verify issues were logged for Healer agent to pick up via event bus
            assert "issues_logged" in result
            assert len(result["issues_logged"]) == 2
            assert result["issues_logged"][0]["issue_id"] == "issue-1"
            assert result["issues_logged"][1]["issue_id"] == "issue-2"

    @pytest.mark.asyncio
    async def test_warning_status_logs_for_healer(self) -> None:
        """Warning status should log issues for federated Healer agent.

        Note: Remediation is handled by the federated Healer agent via event bus,
        not via child workflows.
        """
        workflow_instance = ClusterHealthCheckWorkflow()

        issue = Issue(
            id="issue-1",
            title="Pod Pending",
            description="Pod stuck in pending",
            severity=HealthStatus.WARNING,
            resource_type="Pod",
            resource_name="app-worker",
            namespace="production",
            detected_at=datetime.now(UTC).isoformat(),
        )

        warning_report = ClusterHealthReport(
            summary="Warning: Pod pending",
            status=HealthStatus.WARNING,
            timestamp=datetime.now(UTC).isoformat(),
            issues=[issue],
        )

        with (
            patch(
                "k8s_monitor.workflows.workflow.execute_activity",
                new_callable=AsyncMock,
            ) as mock_execute_activity,
            patch("k8s_monitor.workflows.workflow.logger") as _mock_logger,
        ):
            mock_execute_activity.return_value = warning_report.model_dump()

            result = await workflow_instance.run()

            # Verify issues were logged for Healer agent
            assert result["issues_detected"] == 1
            assert "issues_logged" in result
            assert len(result["issues_logged"]) == 1
            assert result["issues_logged"][0]["issue_id"] == "issue-1"
            # Remediation is handled by federated agents, not workflow
            assert result["remediation_triggered"] is False

    @pytest.mark.asyncio
    async def test_analysis_error_posts_to_discord(self) -> None:
        """Analysis errors should be posted to Discord."""
        workflow_instance = ClusterHealthCheckWorkflow()

        error_report = ClusterHealthReport(
            summary="",
            status=HealthStatus.ERROR,
            timestamp=datetime.now(UTC).isoformat(),
            error="Connection refused",
        )

        with (
            patch(
                "k8s_monitor.workflows.workflow.execute_activity",
                new_callable=AsyncMock,
            ) as mock_execute,
            patch("k8s_monitor.workflows.workflow.logger") as _mock_logger,
        ):
            mock_execute.side_effect = [
                error_report.model_dump(),
                {"success": True},
            ]

            result = await workflow_instance.run()

            # Verify error was posted to Discord
            assert result["analysis_status"] == "error"
            assert result["discord_posted"] is True
            assert result["remediation_triggered"] is False

    @pytest.mark.asyncio
    async def test_swarm_handles_discord_posting(self) -> None:
        """Workflow should trust swarm to handle Discord posting."""
        workflow_instance = ClusterHealthCheckWorkflow()

        healthy_report = ClusterHealthReport(
            summary="All systems operational",
            status=HealthStatus.HEALTHY,
            timestamp=datetime.now(UTC).isoformat(),
        )

        with (
            patch(
                "k8s_monitor.workflows.workflow.execute_activity",
                new_callable=AsyncMock,
            ) as mock_execute,
            patch("k8s_monitor.workflows.workflow.logger") as _mock_logger,
        ):
            # Only one activity call - the swarm handles Discord internally
            mock_execute.return_value = healthy_report.model_dump()

            result = await workflow_instance.run()

            # Workflow always reports discord_posted=True since swarm handles it
            assert result["discord_posted"] is True
            # No discord_error key since workflow doesn't track this anymore
            assert "discord_error" not in result

    @pytest.mark.asyncio
    async def test_critical_issues_include_severity_in_log(self) -> None:
        """Critical issues should include severity in the logged issues.

        Note: The federated Healer agent picks up issues from the event bus
        and handles remediation. The workflow just logs issues for visibility.
        """
        workflow_instance = ClusterHealthCheckWorkflow()

        issue = Issue(
            id="issue-1",
            title="Test Issue",
            description="Test",
            severity=HealthStatus.CRITICAL,
            resource_type="Pod",
            resource_name="test-pod",
            namespace="default",
            detected_at=datetime.now(UTC).isoformat(),
        )

        unhealthy_report = ClusterHealthReport(
            summary="Issues detected",
            status=HealthStatus.CRITICAL,
            timestamp=datetime.now(UTC).isoformat(),
            issues=[issue],
        )

        with (
            patch(
                "k8s_monitor.workflows.workflow.execute_activity",
                new_callable=AsyncMock,
            ) as mock_execute_activity,
            patch("k8s_monitor.workflows.workflow.logger") as _mock_logger,
        ):
            mock_execute_activity.return_value = unhealthy_report.model_dump()

            result = await workflow_instance.run()

            # Verify issues were logged with severity for Healer agent
            assert result["issues_detected"] == 1
            assert "issues_logged" in result
            assert len(result["issues_logged"]) == 1
            assert result["issues_logged"][0]["issue_id"] == "issue-1"
            assert result["issues_logged"][0]["severity"] == "critical"
            # Remediation is handled by federated agents asynchronously
            assert result["remediation_triggered"] is False
