"""Tests for Temporal activities."""

import os
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from k8s_monitor.activities import (
    ClusterHealthReport,
    HealthStatus,
    collect_and_analyze_cluster,
    post_to_discord,
)


class TestCollectAndAnalyzeCluster:
    """Tests for the collect_and_analyze_cluster activity."""

    @pytest.mark.asyncio
    async def test_successful_analysis_healthy(self) -> None:
        """Successful analysis with healthy cluster."""
        with patch("k8s_monitor.activities.analyze_cluster") as mock_analyze:
            mock_analyze.return_value = "All nodes ready, all pods running fine"

            report = await collect_and_analyze_cluster()

            assert report.status == HealthStatus.HEALTHY
            assert "All nodes ready" in report.summary
            assert report.error is None
            mock_analyze.assert_called_once()

    @pytest.mark.asyncio
    async def test_successful_analysis_warning(self) -> None:
        """Analysis detecting warning conditions."""
        with patch("k8s_monitor.activities.analyze_cluster") as mock_analyze:
            mock_analyze.return_value = "Warning: 2 pods pending in default namespace"

            report = await collect_and_analyze_cluster()

            assert report.status == HealthStatus.WARNING
            assert "pending" in report.summary.lower()

    @pytest.mark.asyncio
    async def test_successful_analysis_critical(self) -> None:
        """Analysis detecting critical conditions."""
        with patch("k8s_monitor.activities.analyze_cluster") as mock_analyze:
            mock_analyze.return_value = "Critical: Node worker-1 is down, pods failed"

            report = await collect_and_analyze_cluster()

            assert report.status == HealthStatus.CRITICAL

    @pytest.mark.asyncio
    async def test_analysis_error_handling(self) -> None:
        """Errors during analysis should be caught and reported."""
        with patch("k8s_monitor.activities.analyze_cluster") as mock_analyze:
            mock_analyze.side_effect = Exception("Connection refused")

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
    async def test_missing_webhook_url(self, sample_report: ClusterHealthReport) -> None:
        """Should fail gracefully when webhook URL is not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Ensure DISCORD_WEBHOOK_URL is not set
            os.environ.pop("DISCORD_WEBHOOK_URL", None)

            result = await post_to_discord(sample_report)

            assert result.success is False
            assert "not set" in result.error.lower()  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_successful_post(self, sample_report: ClusterHealthReport) -> None:
        """Successful Discord post."""
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

            result = await post_to_discord(sample_report)

            assert result.success is True
            mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_http_error_handling(self, sample_report: ClusterHealthReport) -> None:
        """HTTP errors should be caught and reported."""
        with (
            patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "https://discord.com/webhook/test"}),
            patch("k8s_monitor.activities.httpx.AsyncClient") as mock_client_class,
        ):
            mock_client = AsyncMock()

            # Create a proper mock response for the error
            mock_request = httpx.Request("POST", "https://discord.com/webhook/test")
            mock_response = httpx.Response(429, request=mock_request)

            # Make post raise the exception directly
            mock_client.post = AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "Rate limited", request=mock_request, response=mock_response
                )
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await post_to_discord(sample_report)

            assert result.success is False
            assert "429" in result.error  # type: ignore[operator]

    @pytest.mark.asyncio
    async def test_network_error_handling(self, sample_report: ClusterHealthReport) -> None:
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

            result = await post_to_discord(sample_report)

            assert result.success is False
            assert "network" in result.error.lower()  # type: ignore[union-attr]

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

            mock_response = AsyncMock()
            mock_response.raise_for_status = AsyncMock()
            captured_payload = None

            async def capture_post(
                url: str, json: dict, _mock_response: AsyncMock = mock_response
            ) -> AsyncMock:
                nonlocal captured_payload
                captured_payload = json
                return _mock_response

            with (
                patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "https://discord.com/webhook/test"}),
                patch("httpx.AsyncClient") as mock_client_class,
            ):
                mock_client = AsyncMock()
                mock_client.post = capture_post
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client_class.return_value = mock_client

                await post_to_discord(report)

                assert captured_payload is not None
                assert captured_payload["embeds"][0]["color"] == expected_color
