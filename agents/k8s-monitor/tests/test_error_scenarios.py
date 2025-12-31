"""
Tests for error handling scenarios.

These tests validate graceful error handling for:
1. MCP connection failures
2. Kubernetes API errors
3. Discord webhook failures
4. LLM response errors
5. Swarm coordination errors
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from k8s_monitor.activities import (
    collect_and_analyze_cluster,
    post_health_confirmation,
    post_to_discord,
)
from k8s_monitor.models import ClusterHealthReport, HealthStatus
from k8s_monitor.swarm import parse_swarm_result, run_health_check


class TestMCPConnectionFailures:
    """Tests for MCP (kubernetes-mcp-server) connection failures."""

    @pytest.mark.asyncio
    async def test_mcp_timeout_graceful_handling(self) -> None:
        """Swarm should handle MCP connection timeout gracefully."""
        with patch(
            "k8s_monitor.swarm.create_k8s_monitor_swarm",
        ) as mock_create:
            # Simulate MCP timeout during swarm creation
            mock_create.side_effect = Exception("Failed to start MCP client: Connection timed out")

            result = await run_health_check()

            # Should return error status, not crash
            assert result["status"] == "error"
            assert "failed" in result["summary"].lower() or "mcp" in result["summary"].lower()

    @pytest.mark.asyncio
    async def test_mcp_connection_refused(self) -> None:
        """Handle MCP server connection refused."""
        with patch(
            "k8s_monitor.swarm.create_k8s_monitor_swarm",
        ) as mock_create:
            mock_create.side_effect = ConnectionRefusedError(
                "Cannot connect to kubernetes-mcp-server"
            )

            result = await run_health_check()

            assert result["status"] == "error"
            assert "issues" in result

    @pytest.mark.asyncio
    async def test_activity_handles_swarm_mcp_failure(self) -> None:
        """Activity should catch and report MCP failures from swarm."""
        with patch(
            "k8s_monitor.swarm.run_health_check",
            new_callable=AsyncMock,
        ) as mock_check:
            mock_check.side_effect = Exception("MCP client initialization failed")

            report = await collect_and_analyze_cluster()

            assert report.status == HealthStatus.ERROR
            assert report.error is not None
            assert "MCP" in report.error or "failed" in report.error.lower()


class TestKubernetesAPIErrors:
    """Tests for Kubernetes API error handling."""

    @pytest.mark.asyncio
    async def test_k8s_api_unavailable(self) -> None:
        """Handle Kubernetes API being unavailable."""
        with patch(
            "k8s_monitor.swarm.run_health_check",
            new_callable=AsyncMock,
        ) as mock_check:
            mock_check.side_effect = Exception(
                "Kubernetes API error: connection refused to apiserver"
            )

            report = await collect_and_analyze_cluster()

            assert report.status == HealthStatus.ERROR
            assert "connection" in report.error.lower() or "api" in report.error.lower()

    @pytest.mark.asyncio
    async def test_k8s_api_permission_denied(self) -> None:
        """Handle RBAC permission denied errors."""
        with patch(
            "k8s_monitor.swarm.run_health_check",
            new_callable=AsyncMock,
        ) as mock_check:
            mock_check.side_effect = Exception(
                "Forbidden: User 'system:serviceaccount:ai-agents:k8s-monitor' "
                "cannot list resource 'pods' in API group '' in the namespace 'kube-system'"
            )

            report = await collect_and_analyze_cluster()

            assert report.status == HealthStatus.ERROR
            assert "forbidden" in report.error.lower() or "permission" in report.error.lower()

    @pytest.mark.asyncio
    async def test_k8s_resource_not_found(self) -> None:
        """Handle resource not found errors."""
        mock_result = {
            "status": "error",
            "summary": "Resource not found: Pod 'missing-pod' not found in namespace 'default'",
            "issues": ["Resource not found"],
            "recommendations": ["Verify the resource exists"],
        }

        with patch(
            "k8s_monitor.swarm.run_health_check",
            new_callable=AsyncMock,
        ) as mock_check:
            mock_check.return_value = mock_result

            report = await collect_and_analyze_cluster()

            # Error status should be mapped correctly
            assert report.status == HealthStatus.ERROR or "not found" in report.summary.lower()


class TestDiscordWebhookFailures:
    """Tests for Discord webhook error handling."""

    @pytest.fixture
    def sample_report(self) -> ClusterHealthReport:
        """Create a sample report for testing."""
        return ClusterHealthReport(
            summary="Test report",
            status=HealthStatus.HEALTHY,
            timestamp="2024-01-01T00:00:00Z",
        )

    @pytest.mark.asyncio
    async def test_discord_rate_limited(self, sample_report: ClusterHealthReport) -> None:
        """Handle Discord rate limiting (429)."""
        with (
            patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "https://discord.test/webhook"}),
            patch("k8s_monitor.activities.httpx.AsyncClient") as mock_client_class,
        ):
            mock_client = AsyncMock()
            request = httpx.Request("POST", "https://discord.test/webhook")
            response = httpx.Response(429, request=request)
            mock_client.post = AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "Rate limited", request=request, response=response
                )
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await post_to_discord(sample_report)

            assert result.success is False
            assert "429" in result.error

    @pytest.mark.asyncio
    async def test_discord_webhook_invalid(self, sample_report: ClusterHealthReport) -> None:
        """Handle invalid webhook URL (404)."""
        with (
            patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "https://discord.test/invalid"}),
            patch("k8s_monitor.activities.httpx.AsyncClient") as mock_client_class,
        ):
            mock_client = AsyncMock()
            request = httpx.Request("POST", "https://discord.test/invalid")
            response = httpx.Response(404, request=request)
            mock_client.post = AsyncMock(
                side_effect=httpx.HTTPStatusError("Not found", request=request, response=response)
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await post_to_discord(sample_report)

            assert result.success is False
            assert "404" in result.error

    @pytest.mark.asyncio
    async def test_discord_network_timeout(self, sample_report: ClusterHealthReport) -> None:
        """Handle network timeout to Discord."""
        with (
            patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "https://discord.test/webhook"}),
            patch("httpx.AsyncClient") as mock_client_class,
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.ConnectTimeout("Connection timed out"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await post_to_discord(sample_report)

            assert result.success is False
            assert "network" in result.error.lower() or "timeout" in result.error.lower()

    @pytest.mark.asyncio
    async def test_discord_webhook_not_configured(self) -> None:
        """Handle missing webhook configuration."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("DISCORD_WEBHOOK_URL", None)

            report = ClusterHealthReport(
                summary="Test",
                status=HealthStatus.HEALTHY,
                timestamp="2024-01-01T00:00:00Z",
            )

            result = await post_to_discord(report)

            assert result.success is False
            assert "not set" in result.error.lower()

    @pytest.mark.asyncio
    async def test_health_confirmation_handles_error(self) -> None:
        """Health confirmation activity handles errors gracefully."""
        with (
            patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "https://discord.test/webhook"}),
            patch("k8s_monitor.activities.httpx.AsyncClient") as mock_client_class,
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection failed"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            report = ClusterHealthReport(
                summary="Test",
                status=HealthStatus.HEALTHY,
                timestamp="2024-01-01T00:00:00Z",
            )

            result = await post_health_confirmation(report)

            assert result.success is False


class TestLLMResponseErrors:
    """Tests for LLM response error handling."""

    @pytest.mark.asyncio
    async def test_malformed_llm_response(self) -> None:
        """Handle malformed LLM responses gracefully."""
        # Simulate swarm returning malformed data
        mock_result = {
            "status": None,  # Missing status
            "summary": "",  # Empty summary
        }

        with patch(
            "k8s_monitor.swarm.run_health_check",
            new_callable=AsyncMock,
        ) as mock_check:
            mock_check.return_value = mock_result

            report = await collect_and_analyze_cluster()

            # Should default to healthy if status is missing/invalid
            assert report.status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_llm_timeout(self) -> None:
        """Handle LLM generation timeout."""
        with patch(
            "k8s_monitor.swarm.run_health_check",
            new_callable=AsyncMock,
        ) as mock_check:
            mock_check.side_effect = TimeoutError("LLM generation timed out after 60s")

            report = await collect_and_analyze_cluster()

            assert report.status == HealthStatus.ERROR
            assert report.error is not None
            assert "timed out" in report.error.lower()

    def test_parse_empty_response(self) -> None:
        """Handle empty response from swarm."""
        result = parse_swarm_result("", "health_check")

        # Should still produce valid result structure
        assert "status" in result
        assert "summary" in result

    def test_parse_response_with_thinking_tags(self) -> None:
        """Thinking tags should be stripped from response."""
        text = """<think>
        Let me analyze the cluster status...
        I should check nodes first...
        </think>

        ✅ Cluster is healthy. All nodes ready."""

        from k8s_monitor.swarm import _extract_text_from_agent_result

        cleaned = _extract_text_from_agent_result(text)

        assert "<think>" not in cleaned
        assert "Let me analyze" not in cleaned
        assert "healthy" in cleaned.lower()


class TestSwarmCoordinationErrors:
    """Tests for swarm coordination error handling."""

    @pytest.mark.asyncio
    async def test_max_handoffs_exceeded(self) -> None:
        """Handle swarm exceeding max handoffs."""
        with patch(
            "k8s_monitor.swarm.create_k8s_monitor_swarm",
        ) as mock_create:
            mock_swarm = MagicMock()
            mock_swarm.side_effect = Exception(
                "Maximum handoffs (10) exceeded without reaching terminal state"
            )
            mock_create.return_value = mock_swarm

            result = await run_health_check()

            assert result["status"] == "error"
            assert "handoff" in result["summary"].lower() or "failed" in result["summary"].lower()

    @pytest.mark.asyncio
    async def test_agent_timeout(self) -> None:
        """Handle individual agent timeout."""
        with patch(
            "k8s_monitor.swarm.create_k8s_monitor_swarm",
        ) as mock_create:
            mock_swarm = MagicMock()
            mock_swarm.side_effect = TimeoutError("Agent 'pod_diagnostician' timed out after 120s")
            mock_create.return_value = mock_swarm

            result = await run_health_check()

            assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_repetitive_handoff_detection(self) -> None:
        """Handle repetitive handoff pattern detection."""
        with patch(
            "k8s_monitor.swarm.create_k8s_monitor_swarm",
        ) as mock_create:
            mock_swarm = MagicMock()
            mock_swarm.side_effect = Exception(
                "Repetitive handoff pattern detected: agents stuck in loop"
            )
            mock_create.return_value = mock_swarm

            result = await run_health_check()

            assert result["status"] == "error"
            assert "issues" in result


class TestErrorRecovery:
    """Tests for error recovery behavior."""

    @pytest.mark.asyncio
    async def test_partial_success_with_discord_failure(
        self,
        mock_discord_webhook,
    ) -> None:
        """Swarm success but Discord failure should be handled."""
        mock_discord_webhook.set_failure(httpx.ConnectError("Discord down"))

        mock_result = {
            "status": "healthy",
            "summary": "All systems good",
            "issues": [],
            "recommendations": [],
        }

        with patch(
            "k8s_monitor.swarm.run_health_check",
            new_callable=AsyncMock,
        ) as mock_check:
            mock_check.return_value = mock_result

            report = await collect_and_analyze_cluster()

            # Analysis should still succeed even if swarm's Discord call fails
            # (the swarm handles Discord internally)
            assert report.status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_error_result_has_recommendations(self) -> None:
        """Error results should include helpful recommendations."""
        with patch(
            "k8s_monitor.swarm.run_health_check",
            new_callable=AsyncMock,
        ) as mock_check:
            mock_check.side_effect = Exception("Something went wrong")

            result = await run_health_check()

            assert result["status"] == "error"
            assert "recommendations" in result
            assert len(result["recommendations"]) > 0


class TestErrorInjector:
    """Tests for the ErrorInjector utility."""

    def test_error_injector_always_fail(self, error_injector) -> None:
        """ErrorInjector should raise configured error."""
        error_injector.fail_on("mcp_connect", ConnectionError("Injected error"))

        with pytest.raises(ConnectionError, match="Injected error"):
            error_injector.check_and_raise("mcp_connect")

    def test_error_injector_nth_call(self, error_injector) -> None:
        """ErrorInjector should fail on nth call."""
        error_injector.fail_on_nth_call("api_call", 3, ValueError("Third call fails"))

        # First two calls succeed
        error_injector.check_and_raise("api_call")
        error_injector.check_and_raise("api_call")

        # Third call fails
        with pytest.raises(ValueError, match="Third call fails"):
            error_injector.check_and_raise("api_call")

    def test_error_injector_clear(self, error_injector) -> None:
        """ErrorInjector should be clearable."""
        error_injector.fail_on("test", RuntimeError("Should fail"))

        with pytest.raises(RuntimeError):
            error_injector.check_and_raise("test")

        error_injector.clear()

        # Should not raise after clear
        error_injector.check_and_raise("test")

    def test_error_injector_no_effect_on_unset_points(self, error_injector) -> None:
        """ErrorInjector should not affect unconfigured points."""
        # No errors configured, should not raise
        error_injector.check_and_raise("some_random_point")
        error_injector.check_and_raise("another_point")
