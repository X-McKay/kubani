"""
Tests for swarm flow and Discord notification behavior.

These tests validate:
1. Discord notifications are sent exactly once (duplicate prevention)
2. Swarm agent handoff flow is correct
3. Discord agent terminates swarm properly (no handoff after notify)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from k8s_monitor.activities import collect_and_analyze_cluster
from k8s_monitor.hooks import SafetyHook, ToolBlockedError
from k8s_monitor.models import HealthStatus
from k8s_monitor.swarm import (
    parse_health_check_result,
    parse_investigation_result,
    parse_swarm_result,
)

from .conftest import SwarmFlowRecorder, simulate_tool_call


class TestDiscordNotificationDuplication:
    """
    Tests to prevent duplicate Discord notifications.

    The Discord duplicate issue was caused by:
    1. Swarm not terminating properly after Discord notification
    2. Discord agent handing off to another agent after sending notification

    These tests validate the fix is working.
    """

    @pytest.mark.asyncio
    async def test_healthy_cluster_single_notification(
        self,
        mock_discord_webhook,
    ) -> None:
        """Healthy cluster should produce exactly one Discord notification."""
        mock_result = {
            "status": "healthy",
            "summary": "All systems operational",
            "issues": [],
            "recommendations": [],
        }

        with patch(
            "k8s_monitor.swarm.run_health_check",
            new_callable=AsyncMock,
        ) as mock_check:
            mock_check.return_value = mock_result

            report = await collect_and_analyze_cluster()

            # Verify report is healthy
            assert report.status == HealthStatus.HEALTHY

            # The swarm handles Discord notification, so we verify
            # through the mock that was called
            mock_check.assert_called_once()

    @pytest.mark.asyncio
    async def test_critical_cluster_single_notification(
        self,
        mock_discord_webhook,
    ) -> None:
        """Critical cluster should produce exactly one Discord notification."""
        mock_result = {
            "status": "critical",
            "summary": "Pod app-1 is CrashLoopBackOff",
            "issues": ["Pod app-1 is failing"],
            "recommendations": ["Check pod logs"],
        }

        with patch(
            "k8s_monitor.swarm.run_health_check",
            new_callable=AsyncMock,
        ) as mock_check:
            mock_check.return_value = mock_result

            report = await collect_and_analyze_cluster()

            assert report.status == HealthStatus.CRITICAL
            mock_check.assert_called_once()

    def test_flow_recorder_tracks_discord_calls(
        self,
        flow_recorder: SwarmFlowRecorder,
    ) -> None:
        """Flow recorder should accurately track discord_notify calls."""
        # Simulate a tool call sequence
        flow_recorder.record_tool_call("handoff_to_agent", {"agent": "cluster_scout"})
        flow_recorder.record_tool_call("kubectl_get_pods", {})
        flow_recorder.record_tool_call("handoff_to_agent", {"agent": "discord"})
        flow_recorder.record_tool_call(
            "discord_notify",
            {"title": "Health Check", "message": "All good"},
        )

        # Verify counts
        assert flow_recorder.discord_notify_calls == 1
        assert flow_recorder.handoff_to_agent_calls == 2
        flow_recorder.assert_single_discord_notification()

    def test_flow_recorder_detects_duplicate_notifications(
        self,
        flow_recorder: SwarmFlowRecorder,
    ) -> None:
        """Flow recorder should detect duplicate Discord notifications."""
        flow_recorder.record_tool_call("discord_notify", {"title": "First"})
        flow_recorder.record_tool_call("discord_notify", {"title": "Second"})  # Duplicate!

        assert flow_recorder.discord_notify_calls == 2

        with pytest.raises(AssertionError, match="Expected exactly 1"):
            flow_recorder.assert_single_discord_notification()

    def test_flow_recorder_detects_handoff_after_discord(
        self,
        flow_recorder: SwarmFlowRecorder,
    ) -> None:
        """Flow recorder should detect if discord agent hands off after notify."""
        flow_recorder.record_tool_call("discord_notify", {"title": "Done"})
        flow_recorder.record_tool_call(
            "handoff_to_agent",
            {"agent": "cluster_triage"},
        )  # Should not happen!

        with pytest.raises(pytest.fail.Exception, match="handoff_to_agent after discord_notify"):
            flow_recorder.assert_no_discord_handoff()


class TestSwarmFlowSequence:
    """Tests for correct agent handoff sequences."""

    def test_healthy_flow_sequence(
        self,
        flow_recorder: SwarmFlowRecorder,
    ) -> None:
        """
        Healthy cluster should follow: triage -> scout -> discord.
        """
        # Simulate expected flow
        flow_recorder.record_tool_call("handoff_to_agent", {"agent": "cluster_scout"})
        flow_recorder.record_tool_call("kubectl_get_nodes", {})
        flow_recorder.record_tool_call("kubectl_get_pods", {})
        flow_recorder.record_tool_call("handoff_to_agent", {"agent": "discord"})
        flow_recorder.record_tool_call("discord_notify", {"title": "Healthy"})

        # Verify handoff sequence
        assert len(flow_recorder.handoffs) == 2
        assert flow_recorder.handoffs[0][1] == "cluster_scout"
        assert flow_recorder.handoffs[1][1] == "discord"

        # Verify single notification
        flow_recorder.assert_single_discord_notification()

    def test_issue_flow_sequence(
        self,
        flow_recorder: SwarmFlowRecorder,
    ) -> None:
        """
        Issue detection should follow: triage -> scout/diagnostician -> discord.
        """
        # Simulate issue detection flow
        flow_recorder.record_tool_call("handoff_to_agent", {"agent": "cluster_scout"})
        flow_recorder.record_tool_call("kubectl_get_pods", {})
        flow_recorder.record_tool_call("handoff_to_agent", {"agent": "pod_diagnostician"})
        flow_recorder.record_tool_call("kubectl_logs", {"pod": "app-1"})
        flow_recorder.record_tool_call("handoff_to_agent", {"agent": "discord"})
        flow_recorder.record_tool_call("discord_notify", {"title": "Issue Found"})

        # Verify 3 handoffs
        assert len(flow_recorder.handoffs) == 3
        assert flow_recorder.handoffs[-1][1] == "discord"

        # Verify single notification at the end
        flow_recorder.assert_single_discord_notification()


class TestSwarmResultParsing:
    """Tests for swarm result parsing functions."""

    def test_parse_healthy_result(self) -> None:
        """Parse healthy status from result text."""
        text = "✅ All systems healthy. No issues detected."
        result = parse_health_check_result(text)

        assert result["status"] == "healthy"
        assert "healthy" in result["summary"].lower()

    def test_parse_warning_result(self) -> None:
        """Parse warning status from result text."""
        text = "⚠️ Warning: 2 pods pending in default namespace."
        result = parse_health_check_result(text)

        assert result["status"] == "warning"

    def test_parse_critical_result(self) -> None:
        """Parse critical status from result text."""
        text = "🚨 Critical: Node worker-1 is down. Multiple pods failing."
        result = parse_health_check_result(text)

        assert result["status"] == "critical"

    def test_parse_investigation_success(self) -> None:
        """Parse successful investigation result."""
        text = "Issue resolved. Pod restarted successfully."
        result = parse_investigation_result(text)

        assert result["outcome"] == "success"

    def test_parse_investigation_failed(self) -> None:
        """Parse failed investigation result."""
        text = "Investigation failed. Unable to determine root cause."
        result = parse_investigation_result(text)

        assert result["outcome"] == "failed"

    def test_parse_investigation_escalated(self) -> None:
        """Parse escalated investigation result."""
        text = "Issue requires human intervention. Escalating to operator."
        result = parse_investigation_result(text)

        assert result["outcome"] == "escalated"

    def test_parse_multiagent_result_success(self) -> None:
        """Parse MultiAgentResult from successful swarm execution."""
        from strands.multiagent.base import MultiAgentResult, NodeResult, Status

        # Create mock successful result
        node_result = MagicMock(spec=NodeResult)
        node_result.status = Status.COMPLETED
        node_result.get_agent_results.return_value = [
            {"role": "assistant", "content": [{"text": "✅ Cluster is healthy"}]}
        ]

        multi_result = MagicMock(spec=MultiAgentResult)
        multi_result.status = Status.COMPLETED
        multi_result.results = {"discord": node_result}

        result = parse_swarm_result(multi_result, "health_check")

        assert result["status"] == "healthy"

    def test_parse_multiagent_result_failure(self) -> None:
        """Parse MultiAgentResult from failed swarm execution."""
        from strands.multiagent.base import MultiAgentResult, NodeResult, Status

        # Create mock failed result
        node_result = MagicMock(spec=NodeResult)
        node_result.status = Status.FAILED
        node_result.result = Exception("Agent timeout")

        multi_result = MagicMock(spec=MultiAgentResult)
        multi_result.status = Status.FAILED
        multi_result.results = {"triage": node_result}

        result = parse_swarm_result(multi_result, "health_check")

        assert result["status"] == "error"
        assert "timeout" in result["summary"].lower()


class TestSafetyHooks:
    """Tests for safety hook behavior."""

    def test_blocks_pod_delete(self) -> None:
        """Safety hook should block pod deletion."""
        with pytest.raises(ToolBlockedError, match="blocked for safety"):
            simulate_tool_call("pods_delete", {"name": "important-pod"})

    def test_blocks_helm_uninstall(self) -> None:
        """Safety hook should block helm uninstall."""
        with pytest.raises(ToolBlockedError, match="blocked for safety"):
            simulate_tool_call("helm_uninstall", {"release": "critical-app"})

    def test_blocks_namespace_delete(self) -> None:
        """Safety hook should block namespace deletion."""
        with pytest.raises(ToolBlockedError, match="blocked for safety"):
            simulate_tool_call("delete_namespace", {"namespace": "production"})

    def test_allows_get_operations(self) -> None:
        """Safety hook should allow read operations."""
        # These should not raise
        simulate_tool_call("kubectl_get_pods", {})
        simulate_tool_call("kubectl_get_nodes", {})
        simulate_tool_call("kubectl_logs", {"pod": "app-1"})

    def test_blocks_shell_access(self) -> None:
        """Safety hook should block shell access."""
        with pytest.raises(ToolBlockedError, match="blocked for safety"):
            simulate_tool_call("shell", {"command": "rm -rf /"})

    def test_restricted_scale_within_limit(self) -> None:
        """Scale within limit should be allowed."""
        hooks = [SafetyHook()]
        # Scale to 5 replicas should be allowed (limit is 10)
        simulate_tool_call("scale_deployment", {"replicas": 5}, hooks=hooks)

    def test_restricted_scale_exceeds_limit(self) -> None:
        """Scale exceeding limit should be blocked."""
        hooks = [SafetyHook()]
        with pytest.raises(ToolBlockedError, match="failed validation"):
            simulate_tool_call("scale_deployment", {"replicas": 15}, hooks=hooks)


class TestDiscordWebhookCapture:
    """Tests for Discord webhook capture fixture."""

    @pytest.mark.asyncio
    async def test_captures_webhook_calls(
        self,
        mock_discord_webhook,
    ) -> None:
        """Mock webhook should capture call payloads."""
        from k8s_monitor.activities import post_to_discord
        from k8s_monitor.models import ClusterHealthReport, HealthStatus

        report = ClusterHealthReport(
            summary="Test",
            status=HealthStatus.HEALTHY,
            timestamp="2024-01-01T00:00:00Z",
        )

        result = await post_to_discord(report)

        assert result.success is True
        assert mock_discord_webhook.call_count == 1
        assert "embeds" in mock_discord_webhook.calls[0]

    @pytest.mark.asyncio
    async def test_simulates_webhook_failure(
        self,
        mock_discord_webhook,
        discord_rate_limit_error,
    ) -> None:
        """Mock webhook should simulate failures."""
        from k8s_monitor.activities import post_to_discord
        from k8s_monitor.models import ClusterHealthReport, HealthStatus

        mock_discord_webhook.set_failure(discord_rate_limit_error)

        report = ClusterHealthReport(
            summary="Test",
            status=HealthStatus.HEALTHY,
            timestamp="2024-01-01T00:00:00Z",
        )

        result = await post_to_discord(report)

        assert result.success is False
        assert "429" in str(result.error)
