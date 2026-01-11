"""Tests for enhanced Temporal activities."""

import os
from unittest.mock import patch

import pytest

from k8s_monitor.activities import (
    collect_and_analyze_cluster,
    post_health_confirmation,
    post_to_discord,
)
from k8s_monitor.models import ClusterHealthReport, HealthStatus


class TestPostHealthConfirmation:
    """Tests for the post_health_confirmation activity."""

    @pytest.fixture
    def healthy_report(self) -> ClusterHealthReport:
        """Create a healthy cluster report for testing."""
        return ClusterHealthReport(
            summary="All systems operational",
            status=HealthStatus.HEALTHY,
            timestamp="2024-01-15T10:00:00Z",
        )

    @pytest.mark.asyncio
    async def test_missing_mcp_config(self, healthy_report: ClusterHealthReport) -> None:
        """Should fail gracefully when Discord MCP is not configured."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("DISCORD_MCP_URL", None)

            result = await post_health_confirmation(healthy_report)

            assert result.success is False
            assert "not configured" in result.error.lower()

    @pytest.mark.asyncio
    async def test_successful_post(self, healthy_report: ClusterHealthReport) -> None:
        """Successful Discord post for healthy status via MCP."""
        captured_embed = None

        async def capture_send(**kwargs):
            nonlocal captured_embed
            captured_embed = kwargs.get("embed")
            return "123456789"

        with (
            patch.dict(os.environ, {"DISCORD_MCP_URL": "https://discord-mcp.example.com/mcp"}),
            patch("k8s_monitor.activities.send_discord_message", side_effect=capture_send),
        ):
            result = await post_health_confirmation(healthy_report)

            assert result.success is True
            assert captured_embed is not None
            assert "All Systems Operational" in captured_embed["title"]
            assert "✅" in captured_embed["title"]

    @pytest.mark.asyncio
    async def test_error_handling(self, healthy_report: ClusterHealthReport) -> None:
        """Errors should be caught and reported."""
        with (
            patch.dict(os.environ, {"DISCORD_MCP_URL": "https://discord-mcp.example.com/mcp"}),
            patch("k8s_monitor.activities.send_discord_message") as mock_send,
        ):
            mock_send.side_effect = Exception("MCP connection failed")

            result = await post_health_confirmation(healthy_report)

            assert result.success is False
            assert "MCP connection failed" in result.error

    @pytest.mark.asyncio
    async def test_no_message_id_returned(self, healthy_report: ClusterHealthReport) -> None:
        """Should handle case when no message ID is returned."""
        with (
            patch.dict(os.environ, {"DISCORD_MCP_URL": "https://discord-mcp.example.com/mcp"}),
            patch("k8s_monitor.activities.send_discord_message") as mock_send,
        ):
            mock_send.return_value = None

            result = await post_health_confirmation(healthy_report)

            assert result.success is False
            assert "No message ID" in result.error


class TestCollectAndAnalyzeClusterEnhanced:
    """Tests for enhanced collect_and_analyze_cluster activity."""

    @pytest.mark.asyncio
    async def test_successful_analysis_with_issues(self) -> None:
        """Successful analysis that detects issues."""
        mock_result = {
            "status": "critical",
            "summary": "Pod crashing in production",
            "issues": [
                "Pod app-backend is CrashLoopBackOff",
                "Node worker-1 is NotReady",
            ],
            "recommendations": ["Check pod logs", "Investigate node health"],
        }

        with patch("k8s_monitor.activities._run_health_check") as mock_check:
            mock_check.return_value = mock_result

            report = await collect_and_analyze_cluster()

            assert report.status == HealthStatus.CRITICAL
            assert "Pod crashing" in report.summary
            assert len(report.issues) == 2
            assert report.error is None
            mock_check.assert_called_once()

    @pytest.mark.asyncio
    async def test_successful_analysis_healthy(self) -> None:
        """Successful analysis with healthy cluster."""
        mock_result = {
            "status": "healthy",
            "summary": "All nodes and pods are healthy",
            "issues": [],
            "recommendations": [],
        }

        with patch("k8s_monitor.activities._run_health_check") as mock_check:
            mock_check.return_value = mock_result

            report = await collect_and_analyze_cluster()

            assert report.status == HealthStatus.HEALTHY
            assert "healthy" in report.summary.lower()
            assert len(report.issues) == 0
            assert report.error is None

    @pytest.mark.asyncio
    async def test_analysis_error_handling(self) -> None:
        """Errors during analysis should be caught and reported."""
        with patch("k8s_monitor.activities._run_health_check") as mock_check:
            mock_check.side_effect = Exception("Kubernetes API unavailable")

            report = await collect_and_analyze_cluster()

            assert report.status == HealthStatus.ERROR
            assert report.summary == ""
            assert "Kubernetes API unavailable" in report.error


class TestPostToDiscordEnhanced:
    """Tests for enhanced post_to_discord activity."""

    @pytest.fixture
    def critical_report(self) -> ClusterHealthReport:
        """Create a critical cluster report for testing."""
        return ClusterHealthReport(
            summary="**Status:** Critical\n\n**Issues:**\n- Pod crashing\n- Node down",
            status=HealthStatus.CRITICAL,
            timestamp="2024-01-15T10:00:00Z",
        )

    @pytest.mark.asyncio
    async def test_successful_post_critical(self, critical_report: ClusterHealthReport) -> None:
        """Successful Discord post for critical status via MCP."""
        captured_embed = None

        async def capture_send(**kwargs):
            nonlocal captured_embed
            captured_embed = kwargs.get("embed")
            return "123456789"

        with (
            patch.dict(os.environ, {"DISCORD_MCP_URL": "https://discord-mcp.example.com/mcp"}),
            patch("k8s_monitor.activities.send_discord_message", side_effect=capture_send),
        ):
            result = await post_to_discord(critical_report)

            assert result.success is True
            assert captured_embed is not None
            assert "🚨" in captured_embed["title"]
            assert captured_embed["color"] == 0xED4245  # Red

    @pytest.mark.asyncio
    async def test_post_with_error_field(self) -> None:
        """Post with error field should include error in embed."""
        error_report = ClusterHealthReport(
            summary="Analysis failed",
            status=HealthStatus.ERROR,
            timestamp="2024-01-15T10:00:00Z",
            error="Connection timeout",
        )

        captured_embed = None

        async def capture_send(**kwargs):
            nonlocal captured_embed
            captured_embed = kwargs.get("embed")
            return "123456789"

        with (
            patch.dict(os.environ, {"DISCORD_MCP_URL": "https://discord-mcp.example.com/mcp"}),
            patch("k8s_monitor.activities.send_discord_message", side_effect=capture_send),
        ):
            result = await post_to_discord(error_report)

            assert result.success is True
            assert captured_embed is not None
            assert "fields" in captured_embed
            assert any("Error" in field["name"] for field in captured_embed["fields"])
