"""Tests for Discord utilities and formatting functions."""

from core_agents.integrations.discord import (
    Colors,
    StatusEmoji,
    format_escalation,
    format_fix_attempt,
    format_fix_failure,
    format_fix_success,
    format_health_confirmation,
    format_investigation_results,
    format_issue_detection,
)


class TestDiscordFormatting:
    """Tests for Discord message formatting utilities."""

    def test_format_health_confirmation(self) -> None:
        """Test health confirmation formatting."""
        embed = format_health_confirmation(
            summary="All nodes, pods, and deployments are healthy.",
            timestamp="2024-01-15T10:00:00Z",
            additional_info={"nodes": 3, "pods": 42},
        )

        assert (
            embed.title == f"{StatusEmoji.HEALTHY} Cluster Health Check - All Systems Operational"
        )
        assert "All nodes, pods, and deployments are healthy" in embed.description
        assert "**Nodes:** 3" in embed.description
        assert "**Pods:** 42" in embed.description
        assert embed.color == Colors.SUCCESS
        assert embed.footer == "Kubani K8s Monitor"
        assert embed.timestamp == "2024-01-15T10:00:00Z"

    def test_format_health_confirmation_without_additional_info(self) -> None:
        """Test health confirmation without additional info."""
        embed = format_health_confirmation(
            summary="Cluster is healthy.",
            timestamp="2024-01-15T10:00:00Z",
        )

        assert "Cluster is healthy" in embed.description
        assert "**Nodes:**" not in embed.description

    def test_format_issue_detection_critical(self) -> None:
        """Test issue detection formatting for critical severity."""
        embed = format_issue_detection(
            issue_title="Pod CrashLoopBackOff",
            resource_type="Pod",
            resource_name="app-backend",
            namespace="production",
            severity="critical",
            description="Container is crashing repeatedly",
            timestamp="2024-01-15T10:00:00Z",
        )

        assert StatusEmoji.CRITICAL in embed.title
        assert "Pod CrashLoopBackOff" in embed.title
        assert "**Resource:** Pod/app-backend" in embed.description
        assert "**Namespace:** production" in embed.description
        assert "**Severity:** Critical" in embed.description
        assert "Container is crashing repeatedly" in embed.description
        assert "Starting automated investigation" in embed.description
        assert embed.color == Colors.ERROR

    def test_format_issue_detection_warning(self) -> None:
        """Test issue detection formatting for warning severity."""
        embed = format_issue_detection(
            issue_title="Pod Pending",
            resource_type="Pod",
            resource_name="app-worker",
            namespace="default",
            severity="warning",
        )

        assert StatusEmoji.WARNING in embed.title
        assert embed.color == Colors.WARNING

    def test_format_investigation_results(self) -> None:
        """Test investigation results formatting."""
        embed = format_investigation_results(
            issue_title="Pod CrashLoopBackOff",
            root_cause="OOMKilled - container exceeded memory limit",
            evidence=[
                "Last exit code: 137 (OOM)",
                "Memory limit: 512Mi",
                "Memory usage: 580Mi peak",
            ],
            similar_issues_count=2,
            last_occurrence="3 days ago",
            proposed_fix="Increase memory limit to 1Gi",
            confidence=0.9,
            timestamp="2024-01-15T10:00:00Z",
        )

        assert StatusEmoji.INVESTIGATING in embed.title
        assert "Investigation Complete" in embed.title
        assert "**Root Cause:** OOMKilled" in embed.description
        assert "**Evidence:**" in embed.description
        assert "Last exit code: 137" in embed.description
        assert (
            "**Similar Issues:** Found 2 past occurrence(s) (last: 3 days ago)" in embed.description
        )
        assert "**Planned Remediation:** Increase memory limit to 1Gi" in embed.description
        assert "**Confidence:** 90%" in embed.description
        assert embed.color == Colors.INFO

    def test_format_investigation_results_no_similar_issues(self) -> None:
        """Test investigation results without similar issues."""
        embed = format_investigation_results(
            issue_title="New Issue",
            root_cause="Unknown",
            similar_issues_count=0,
        )

        assert "Similar Issues" not in embed.description

    def test_format_investigation_results_limits_evidence(self) -> None:
        """Test that evidence is limited to top 3 items."""
        embed = format_investigation_results(
            issue_title="Test",
            root_cause="Test",
            evidence=["Item 1", "Item 2", "Item 3", "Item 4", "Item 5"],
        )

        # Should only include first 3
        assert "Item 1" in embed.description
        assert "Item 2" in embed.description
        assert "Item 3" in embed.description
        assert "Item 4" not in embed.description

    def test_format_fix_attempt(self) -> None:
        """Test fix attempt formatting."""
        embed = format_fix_attempt(
            issue_title="Pod CrashLoopBackOff",
            attempt_number=1,
            max_attempts=3,
            action="Updating deployment memory limit",
            command='kubectl patch deployment app-backend -p \'{"spec":{"template":{"spec":{"containers":[{"name":"app","resources":{"limits":{"memory":"1Gi"}}}]}}}}\'',
            timestamp="2024-01-15T10:00:00Z",
        )

        assert StatusEmoji.FIXING in embed.title
        assert "Applying Fix (Attempt 1/3)" in embed.title
        assert "**Action:** Updating deployment memory limit" in embed.description
        assert "**Command:**" in embed.description
        assert "kubectl patch" in embed.description
        assert "Executing..." in embed.description
        assert embed.color == Colors.INFO

    def test_format_fix_attempt_truncates_long_command(self) -> None:
        """Test that long commands are truncated."""
        long_command = "kubectl " + "x" * 300

        embed = format_fix_attempt(
            issue_title="Test",
            attempt_number=1,
            max_attempts=3,
            action="Test action",
            command=long_command,
        )

        # Should be truncated with ellipsis
        assert "..." in embed.description
        assert len(embed.description) < len(long_command)

    def test_format_fix_success(self) -> None:
        """Test fix success formatting."""
        embed = format_fix_success(
            issue_title="Pod CrashLoopBackOff",
            fix_applied="Increased memory limit to 1Gi",
            result="Pod now running successfully",
            recurrence_count=1,
            timestamp="2024-01-15T10:00:00Z",
        )

        assert StatusEmoji.SUCCESS in embed.title
        assert "Issue Resolved" in embed.title
        assert "**Fix Applied:** Increased memory limit to 1Gi" in embed.description
        assert "**Result:** Pod now running successfully" in embed.description
        assert "Learning stored for future reference" in embed.description
        assert embed.color == Colors.SUCCESS

    def test_format_fix_success_with_recurrence_warning(self) -> None:
        """Test fix success with recurrence warning."""
        embed = format_fix_success(
            issue_title="Pod CrashLoopBackOff",
            fix_applied="Increased memory limit",
            result="Pod running",
            recurrence_count=3,
            recommendations=["Investigate memory leak", "Update base manifest"],
        )

        assert "This issue has occurred 3 times" in embed.description
        assert "Investigate memory leak" in embed.description
        assert "Update base manifest" in embed.description

    def test_format_fix_failure(self) -> None:
        """Test fix failure formatting."""
        embed = format_fix_failure(
            issue_title="Pod CrashLoopBackOff",
            attempt_number=1,
            max_attempts=3,
            result="Deployment updated but pod still crashing",
            next_action="Re-investigating with new context...",
            timestamp="2024-01-15T10:00:00Z",
        )

        assert StatusEmoji.FAILED in embed.title
        assert "Fix Attempt 1 Failed" in embed.title
        assert "**Result:** Deployment updated but pod still crashing" in embed.description
        assert "Re-investigating with new context..." in embed.description
        assert "Attempt 2/3 starting..." in embed.description
        assert embed.color == Colors.WARNING

    def test_format_fix_failure_last_attempt(self) -> None:
        """Test fix failure on last attempt."""
        embed = format_fix_failure(
            issue_title="Test",
            attempt_number=3,
            max_attempts=3,
            result="Failed",
        )

        # Should not show next attempt message
        assert "Attempt 4/3" not in embed.description

    def test_format_escalation(self) -> None:
        """Test escalation formatting."""
        embed = format_escalation(
            issue_title="Pod CrashLoopBackOff",
            resource_type="Pod",
            resource_name="app-backend",
            namespace="production",
            attempts=3,
            attempts_summary=[
                "Increased memory limit → Pod still crashing",
                "Rolled back to previous version → Image pull failed",
                "Restarted with debug mode → Container won't start",
            ],
            root_cause="Likely configuration issue in new deployment",
            action_required=[
                "Check application logs",
                "Verify configuration changes",
                "Consider rollback to known good state",
            ],
            timestamp="2024-01-15T10:00:00Z",
        )

        assert StatusEmoji.ESCALATION in embed.title
        assert "URGENT: Automated Remediation Failed" in embed.title
        assert "**Issue:** Pod CrashLoopBackOff (Pod/app-backend)" in embed.description
        assert "**Namespace:** production" in embed.description
        assert "**Attempts:** 3/3 failed" in embed.description
        assert "**What was tried:**" in embed.description
        assert "1. Increased memory limit → Pod still crashing" in embed.description
        assert "2. Rolled back to previous version → Image pull failed" in embed.description
        assert "3. Restarted with debug mode → Container won't start" in embed.description
        assert "**Root Cause:** Likely configuration issue" in embed.description
        assert "**Action Required:** Manual investigation needed" in embed.description
        assert "- Check application logs" in embed.description
        assert "- Verify configuration changes" in embed.description
        assert "- Consider rollback to known good state" in embed.description
        assert embed.color == Colors.ERROR

    def test_format_escalation_without_root_cause(self) -> None:
        """Test escalation without root cause."""
        embed = format_escalation(
            issue_title="Test",
            resource_type="Pod",
            resource_name="test",
            namespace="default",
            attempts=3,
            attempts_summary=["Attempt 1 failed"],
            action_required=["Manual fix needed"],
        )

        assert "**Root Cause:**" not in embed.description

    def test_format_escalation_without_action_required(self) -> None:
        """Test escalation without action required."""
        embed = format_escalation(
            issue_title="Test",
            resource_type="Pod",
            resource_name="test",
            namespace="default",
            attempts=3,
            attempts_summary=["Attempt 1 failed"],
        )

        assert "**Action Required:**" not in embed.description
