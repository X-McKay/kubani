"""Tests for enhanced Temporal activities."""

import os
from unittest.mock import AsyncMock, patch

import httpx
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
    async def test_missing_webhook_url(self, healthy_report: ClusterHealthReport) -> None:
        """Should fail gracefully when webhook URL is not set."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("DISCORD_WEBHOOK_URL", None)

            result = await post_health_confirmation(healthy_report)

            assert result.success is False
            assert "not set" in result.error.lower()

    @pytest.mark.asyncio
    async def test_successful_post(self, healthy_report: ClusterHealthReport) -> None:
        """Successful Discord post for healthy status."""
        mock_response = AsyncMock()
        mock_response.raise_for_status = AsyncMock()

        with (
            patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "https://discord.com/webhook/test"}),
            patch("httpx.AsyncClient") as mock_client_class,
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await post_health_confirmation(healthy_report)

            assert result.success is True
            mock_client.post.assert_called_once()

            # Verify the payload contains health confirmation
            call_args = mock_client.post.call_args
            payload = call_args[1]["json"]
            assert payload["username"] == "Kubani K8s Monitor"
            assert len(payload["embeds"]) == 1
            embed = payload["embeds"][0]
            assert "All Systems Operational" in embed["title"]
            assert "✅" in embed["title"]

    @pytest.mark.asyncio
    async def test_http_error_handling(self, healthy_report: ClusterHealthReport) -> None:
        """HTTP errors should be caught and reported."""
        with (
            patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "https://discord.com/webhook/test"}),
            patch("k8s_monitor.activities.httpx.AsyncClient") as mock_client_class,
        ):
            mock_client = AsyncMock()

            mock_request = httpx.Request("POST", "https://discord.com/webhook/test")
            mock_response = httpx.Response(429, request=mock_request)

            mock_client.post = AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "Rate limited", request=mock_request, response=mock_response
                )
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await post_health_confirmation(healthy_report)

            assert result.success is False
            assert "429" in result.error

    @pytest.mark.asyncio
    async def test_network_error_handling(self, healthy_report: ClusterHealthReport) -> None:
        """Network errors should be caught and reported."""
        with (
            patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "https://discord.com/webhook/test"}),
            patch("httpx.AsyncClient") as mock_client_class,
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(
                side_effect=httpx.RequestError("Connection failed", request=AsyncMock())
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await post_health_confirmation(healthy_report)

            assert result.success is False
            assert "network" in result.error.lower()


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

        with patch("k8s_monitor.swarm.run_health_check", new_callable=AsyncMock) as mock_check:
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

        with patch("k8s_monitor.swarm.run_health_check", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = mock_result

            report = await collect_and_analyze_cluster()

            assert report.status == HealthStatus.HEALTHY
            assert "healthy" in report.summary.lower()
            assert len(report.issues) == 0
            assert report.error is None

    @pytest.mark.asyncio
    async def test_analysis_error_handling(self) -> None:
        """Errors during analysis should be caught and reported."""
        with patch("k8s_monitor.swarm.run_health_check", new_callable=AsyncMock) as mock_check:
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
        """Successful Discord post for critical status."""
        mock_response = AsyncMock()
        mock_response.raise_for_status = AsyncMock()

        with (
            patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "https://discord.com/webhook/test"}),
            patch("httpx.AsyncClient") as mock_client_class,
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await post_to_discord(critical_report)

            assert result.success is True
            mock_client.post.assert_called_once()

            # Verify the payload contains critical status
            call_args = mock_client.post.call_args
            payload = call_args[1]["json"]
            embed = payload["embeds"][0]
            assert "🚨" in embed["title"]
            assert embed["color"] == 0xED4245  # Red

    @pytest.mark.asyncio
    async def test_post_with_error_field(self) -> None:
        """Post with error field should include error in embed."""
        error_report = ClusterHealthReport(
            summary="Analysis failed",
            status=HealthStatus.ERROR,
            timestamp="2024-01-15T10:00:00Z",
            error="Connection timeout",
        )

        mock_response = AsyncMock()
        mock_response.raise_for_status = AsyncMock()

        with (
            patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "https://discord.com/webhook/test"}),
            patch("httpx.AsyncClient") as mock_client_class,
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await post_to_discord(error_report)

            assert result.success is True

            # Verify error field is included
            call_args = mock_client.post.call_args
            payload = call_args[1]["json"]
            embed = payload["embeds"][0]
            assert "fields" in embed
            assert any("Error" in field["name"] for field in embed["fields"])
