"""Tests for Temporal activities."""

import os
from unittest.mock import patch

import pytest

from k8s_monitor.activities import (
    collect_and_analyze_cluster,
    post_to_discord,
)
from k8s_monitor.models import ClusterHealthReport, HealthStatus


class TestCollectAndAnalyzeCluster:
    """Tests for the collect_and_analyze_cluster activity."""

    @pytest.mark.asyncio
    async def test_successful_analysis_healthy(self) -> None:
        """Successful analysis with healthy cluster."""
        mock_result = {
            "status": "healthy",
            "summary": "All nodes ready, all pods running fine",
            "issues": [],
            "recommendations": [],
        }

        with patch("k8s_monitor.activities._run_health_check") as mock_check:
            mock_check.return_value = mock_result

            report = await collect_and_analyze_cluster()

            assert report.status == HealthStatus.HEALTHY
            assert "All nodes ready" in report.summary
            assert report.error is None
            mock_check.assert_called_once()

    @pytest.mark.asyncio
    async def test_successful_analysis_warning(self) -> None:
        """Analysis detecting warning conditions."""
        mock_result = {
            "status": "warning",
            "summary": "2 pods pending in default namespace",
            "issues": ["Pod pending-1 is Pending"],
            "recommendations": ["Check resource quotas"],
        }

        with patch("k8s_monitor.activities._run_health_check") as mock_check:
            mock_check.return_value = mock_result

            report = await collect_and_analyze_cluster()

            assert report.status == HealthStatus.WARNING
            assert "pending" in report.summary.lower()

    @pytest.mark.asyncio
    async def test_successful_analysis_critical(self) -> None:
        """Analysis detecting critical conditions."""
        mock_result = {
            "status": "critical",
            "summary": "Node worker-1 is down, pods failed",
            "issues": ["Node worker-1 NotReady", "Pod app-1 CrashLoopBackOff"],
            "recommendations": ["Investigate node health"],
        }

        with patch("k8s_monitor.activities._run_health_check") as mock_check:
            mock_check.return_value = mock_result

            report = await collect_and_analyze_cluster()

            assert report.status == HealthStatus.CRITICAL

    @pytest.mark.asyncio
    async def test_analysis_error_handling(self) -> None:
        """Errors during analysis should be caught and reported."""
        with patch("k8s_monitor.activities._run_health_check") as mock_check:
            mock_check.side_effect = Exception("Connection refused")

            report = await collect_and_analyze_cluster()

            assert report.status == HealthStatus.ERROR
            assert report.summary == ""
            assert "Connection refused" in report.error  # type: ignore[operator]


class TestPostToDiscord:
    """Tests for the post_to_discord activity."""

    @pytest.fixture
    def sample_report(self) -> ClusterHealthReport:
        """Create a sample health report for testing."""
        return ClusterHealthReport(
            summary="Test summary",
            status=HealthStatus.HEALTHY,
            timestamp="2024-01-01T00:00:00Z",
        )

    @pytest.mark.asyncio
    async def test_missing_mcp_config(self, sample_report: ClusterHealthReport) -> None:
        """Should fail gracefully when Discord MCP is not configured."""
        with patch.dict(os.environ, {}, clear=True):
            # Ensure DISCORD_MCP_URL is not set
            os.environ.pop("DISCORD_MCP_URL", None)

            result = await post_to_discord(sample_report)

            assert result.success is False
            assert "not configured" in result.error.lower()  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_successful_post(self, sample_report: ClusterHealthReport) -> None:
        """Successful Discord post via MCP."""
        with (
            patch.dict(os.environ, {"DISCORD_MCP_URL": "https://discord-mcp.example.com/mcp"}),
            patch("k8s_monitor.activities.send_discord_message") as mock_send,
        ):
            mock_send.return_value = "123456789"  # Message ID

            result = await post_to_discord(sample_report)

            assert result.success is True
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_error_handling(self, sample_report: ClusterHealthReport) -> None:
        """Errors should be caught and reported."""
        with (
            patch.dict(os.environ, {"DISCORD_MCP_URL": "https://discord-mcp.example.com/mcp"}),
            patch("k8s_monitor.activities.send_discord_message") as mock_send,
        ):
            mock_send.side_effect = Exception("MCP connection failed")

            result = await post_to_discord(sample_report)

            assert result.success is False
            assert "MCP connection failed" in result.error  # type: ignore[operator]

    @pytest.mark.asyncio
    async def test_no_message_id_returned(self, sample_report: ClusterHealthReport) -> None:
        """Should handle case when no message ID is returned."""
        with (
            patch.dict(os.environ, {"DISCORD_MCP_URL": "https://discord-mcp.example.com/mcp"}),
            patch("k8s_monitor.activities.send_discord_message") as mock_send,
        ):
            mock_send.return_value = None

            result = await post_to_discord(sample_report)

            assert result.success is False
            assert "No message ID" in result.error  # type: ignore[operator]

    @pytest.mark.asyncio
    async def test_embed_color_based_on_status(self) -> None:
        """Embed color should match the health status."""
        statuses_and_colors = [
            (HealthStatus.HEALTHY, 0x57F287),
            (HealthStatus.WARNING, 0xFEE75C),
            (HealthStatus.CRITICAL, 0xED4245),
            (HealthStatus.ERROR, 0x99AAB5),
        ]

        for status, expected_color in statuses_and_colors:
            report = ClusterHealthReport(
                summary="Test",
                status=status,
                timestamp="2024-01-01T00:00:00Z",
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
                await post_to_discord(report)

                assert captured_embed is not None
                assert captured_embed["color"] == expected_color
