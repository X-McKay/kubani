"""Tests for the orchestration workflow and activities."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from k8s_monitor.models import (
    CorrelatedIssue,
    InvestigationStage,
    InvestigationState,
    Severity,
)
from k8s_monitor.orchestration_activities import (
    analyze_issue,
    execute_remediation,
    investigate_issue,
    plan_remediation,
    query_memory,
    verify_remediation,
)

# =============================================================================
# Test Data Fixtures
# =============================================================================


@pytest.fixture
def sample_correlated_issue() -> dict:
    """Sample correlated issue data."""
    return {
        "correlation_id": "test-correlation-123",
        "primary_event": {
            "reason": "CrashLoopBackOff",
            "message": "Back-off restarting failed container",
            "namespace": "default",
            "name": "test-pod-abc123",
            "kind": "Pod",
            "type": "Warning",
        },
        "related_events": [],
        "namespace": "default",
        "severity": "high",
        "pattern_type": "crash_loop",
    }


@pytest.fixture
def sample_investigation_state() -> dict:
    """Sample investigation state after analysis."""
    return {
        "investigation_id": "inv-test-123",
        "stage": "investigating",
        "trigger_event": {
            "reason": "CrashLoopBackOff",
            "message": "Back-off restarting failed container",
            "namespace": "default",
            "name": "test-pod-abc123",
            "kind": "Pod",
        },
        "correlated_events": [],
        "namespace": "default",
        "pod_name": "test-pod-abc123",
        "classification": "crash_loop",
        "severity": "critical",
        "confidence": 0.95,
        "similar_incidents": [],
        "relevant_skills": ["restart-pod", "check-logs"],
    }


# =============================================================================
# Model Tests
# =============================================================================


class TestInvestigationState:
    """Tests for InvestigationState model."""

    def test_create_investigation_state(self) -> None:
        """Test creating an investigation state."""
        state = InvestigationState(
            investigation_id="test-123",
            trigger_event={"reason": "CrashLoopBackOff"},
            namespace="default",
        )

        assert state.investigation_id == "test-123"
        assert state.stage == InvestigationStage.ANALYZING
        assert state.namespace == "default"
        assert state.approval_required is False

    def test_investigation_state_serialization(self) -> None:
        """Test that state can be serialized and deserialized."""
        state = InvestigationState(
            investigation_id="test-123",
            trigger_event={"reason": "CrashLoopBackOff"},
            namespace="default",
            classification="crash_loop",
            severity="high",
        )

        data = state.model_dump(mode="json")
        restored = InvestigationState.model_validate(data)

        assert restored.investigation_id == state.investigation_id
        assert restored.classification == state.classification


class TestCorrelatedIssue:
    """Tests for CorrelatedIssue model."""

    def test_create_correlated_issue(self) -> None:
        """Test creating a correlated issue."""
        now = datetime.now(UTC)
        issue = CorrelatedIssue(
            correlation_id="corr-123",
            primary_event={"reason": "OOMKilled"},
            namespace="production",
            first_seen=now,
            last_seen=now,
            severity=Severity.CRITICAL,
        )

        assert issue.correlation_id == "corr-123"
        assert issue.severity == Severity.CRITICAL
        assert issue.event_count == 1


# =============================================================================
# Activity Tests
# =============================================================================


class TestAnalyzeIssue:
    """Tests for analyze_issue activity."""

    @pytest.mark.asyncio
    async def test_analyze_crash_loop(self, sample_correlated_issue: dict) -> None:
        """Analyze CrashLoopBackOff event."""
        state = {
            "investigation_id": "test-123",
            "trigger_event": sample_correlated_issue["primary_event"],
            "correlated_events": [],
            "namespace": "default",
            "severity": "medium",
        }

        result = await analyze_issue(state)

        assert result["classification"] == "crash_loop"
        assert result["severity"] == "critical"
        assert result["confidence"] >= 0.9

    @pytest.mark.asyncio
    async def test_analyze_oom_killed(self) -> None:
        """Analyze OOMKilled event."""
        state = {
            "investigation_id": "test-123",
            "trigger_event": {
                "reason": "OOMKilled",
                "message": "Container killed due to OOM",
                "namespace": "default",
                "name": "memory-hog",
                "kind": "Pod",
            },
            "correlated_events": [],
            "namespace": "default",
            "severity": "medium",
        }

        result = await analyze_issue(state)

        assert result["classification"] == "memory_exhaustion"
        assert result["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_analyze_unknown_reason(self) -> None:
        """Analyze unknown event reason."""
        state = {
            "investigation_id": "test-123",
            "trigger_event": {
                "reason": "SomeUnknownReason",
                "message": "Something happened",
                "namespace": "default",
                "name": "test-pod",
                "kind": "Pod",
            },
            "correlated_events": [],
            "namespace": "default",
            "severity": "low",
        }

        result = await analyze_issue(state)

        assert result["classification"] == "unknown_issue"
        assert result["confidence"] == 0.5

    @pytest.mark.asyncio
    async def test_confidence_boost_with_correlated_events(self) -> None:
        """Confidence should increase with correlated events."""
        state = {
            "investigation_id": "test-123",
            "trigger_event": {"reason": "CrashLoopBackOff"},
            "correlated_events": [
                {"reason": "BackOff"},
                {"reason": "BackOff"},
            ],
            "namespace": "default",
            "severity": "medium",
        }

        result = await analyze_issue(state)

        # Base confidence is 0.95, should be boosted
        assert result["confidence"] > 0.95
        assert result["event_count"] == 3


class TestQueryMemory:
    """Tests for query_memory activity."""

    @pytest.mark.asyncio
    async def test_query_memory_crash_loop(self, sample_investigation_state: dict) -> None:
        """Query memory for crash loop classification."""
        sample_investigation_state["classification"] = "crash_loop"

        result = await query_memory(sample_investigation_state)

        assert "relevant_skills" in result
        assert "restart-pod" in result["relevant_skills"]
        assert "check-logs" in result["relevant_skills"]

    @pytest.mark.asyncio
    async def test_query_memory_image_pull(self) -> None:
        """Query memory for image pull failure."""
        state = {
            "investigation_id": "test-123",
            "classification": "image_pull_failure",
            "namespace": "default",
        }

        result = await query_memory(state)

        assert "verify-image" in result["relevant_skills"]
        assert "check-registry" in result["relevant_skills"]

    @pytest.mark.asyncio
    async def test_query_memory_unknown_classification(self) -> None:
        """Query memory for unknown classification."""
        state = {
            "investigation_id": "test-123",
            "classification": "totally_unknown",
            "namespace": "default",
        }

        result = await query_memory(state)

        assert "generic-investigate" in result["relevant_skills"]


class TestPlanRemediation:
    """Tests for plan_remediation activity."""

    @pytest.mark.asyncio
    async def test_plan_crash_loop_remediation(self, sample_investigation_state: dict) -> None:
        """Plan remediation for crash loop."""
        result = await plan_remediation(sample_investigation_state)

        assert result["plan"]["action"] == "restart_pod"
        assert result["requires_approval"] is False

    @pytest.mark.asyncio
    async def test_plan_node_failure_requires_approval(self) -> None:
        """Node failure remediation should require approval."""
        state = {
            "investigation_id": "test-123",
            "classification": "node_failure",
            "severity": "critical",
            "namespace": "default",
            "pod_name": "test-pod",
        }

        result = await plan_remediation(state)

        assert result["plan"]["action"] == "escalate"
        assert result["requires_approval"] is True

    @pytest.mark.asyncio
    async def test_plan_image_pull_reports_config_issue(self) -> None:
        """Image pull failure should report config issue."""
        state = {
            "investigation_id": "test-123",
            "classification": "image_pull_failure",
            "severity": "high",
            "namespace": "default",
            "pod_name": "test-pod",
        }

        result = await plan_remediation(state)

        assert result["plan"]["action"] == "report_config_issue"
        assert result["requires_approval"] is False


class TestInvestigateIssue:
    """Tests for investigate_issue activity."""

    @pytest.mark.asyncio
    async def test_investigate_with_mcp_tools(self, sample_investigation_state: dict) -> None:
        """Investigate using MCP tools."""
        mock_mcp_result = {"success": True, "result": "pod is in CrashLoopBackOff"}

        with patch("k8s_monitor.mcp_tools.call_mcp_tool_async") as mock_mcp:
            mock_mcp.return_value = mock_mcp_result

            result = await investigate_issue(sample_investigation_state)

            assert "diagnostics" in result
            assert "root_cause" in result
            assert result["root_cause"] == "Application crash or startup failure"

    @pytest.mark.asyncio
    async def test_investigate_mcp_failure(self, sample_investigation_state: dict) -> None:
        """Investigation should handle MCP failure gracefully."""
        with patch("k8s_monitor.mcp_tools.call_mcp_tool_async") as mock_mcp:
            mock_mcp.side_effect = Exception("MCP connection failed")

            result = await investigate_issue(sample_investigation_state)

            # Should still return diagnostics with error
            assert "diagnostics" in result
            assert "error" in result["diagnostics"]


class TestExecuteRemediation:
    """Tests for execute_remediation activity."""

    @pytest.mark.asyncio
    async def test_execute_restart_pod(self) -> None:
        """Execute pod restart remediation."""
        state = {
            "investigation_id": "test-123",
            "remediation_plan": {
                "action": "restart_pod",
                "parameters": {"name": "test-pod", "namespace": "default"},
            },
        }

        mock_result = {"success": True, "result": "pod deleted"}

        with patch("k8s_monitor.mcp_tools.call_mcp_tool_async") as mock_mcp:
            mock_mcp.return_value = mock_result

            result = await execute_remediation(state)

            assert result["success"] is True
            assert result["action"] == "restart_pod"
            mock_mcp.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_report_config_issue(self) -> None:
        """Execute config issue report."""
        state = {
            "investigation_id": "test-123",
            "remediation_plan": {
                "action": "report_config_issue",
                "parameters": {"issue": "image_pull"},
            },
        }

        result = await execute_remediation(state)

        assert result["success"] is True
        assert "manual configuration change" in result["output"]

    @pytest.mark.asyncio
    async def test_execute_no_plan(self) -> None:
        """Execute with no remediation plan."""
        state = {
            "investigation_id": "test-123",
            "remediation_plan": None,
        }

        result = await execute_remediation(state)

        # Should handle gracefully
        assert result["action"] == "investigate"


class TestVerifyRemediation:
    """Tests for verify_remediation activity."""

    @pytest.mark.asyncio
    async def test_verify_pod_running(self) -> None:
        """Verify pod is running after remediation."""
        state = {
            "investigation_id": "test-123",
            "namespace": "default",
            "pod_name": "test-pod",
            "classification": "crash_loop",
        }

        mock_result = {
            "success": True,
            "result": "Status: Running, Conditions: Ready",
        }

        with patch("k8s_monitor.mcp_tools.call_mcp_tool_async") as mock_mcp:
            mock_mcp.return_value = mock_result

            result = await verify_remediation(state)

            assert result["resolved"] is True
            assert "Running and Ready" in result["reason"]

    @pytest.mark.asyncio
    async def test_verify_pod_replaced(self) -> None:
        """Verify when pod is replaced (deleted and recreated)."""
        state = {
            "investigation_id": "test-123",
            "namespace": "default",
            "pod_name": "test-pod-old",
            "classification": "crash_loop",
        }

        mock_result = {"success": False, "error": "Pod not found"}

        with patch("k8s_monitor.mcp_tools.call_mcp_tool_async") as mock_mcp:
            mock_mcp.return_value = mock_result

            result = await verify_remediation(state)

            # For crash_loop, pod replacement is expected
            assert result["resolved"] is True
            assert "replaced" in result["reason"].lower()


# =============================================================================
# Shadow Mode Tests
# =============================================================================


class TestShadowMode:
    """Tests for shadow mode functionality."""

    @pytest.mark.asyncio
    async def test_shadow_mode_disabled_by_default(self) -> None:
        """Shadow mode should be disabled by default."""
        with patch.dict("os.environ", {}, clear=True):
            # Re-import to reset the singleton
            import importlib

            import k8s_monitor.shadow_mode

            importlib.reload(k8s_monitor.shadow_mode)

            assert k8s_monitor.shadow_mode.SHADOW_MODE_ENABLED is False

    @pytest.mark.asyncio
    async def test_shadow_mode_enabled_via_env(self) -> None:
        """Shadow mode can be enabled via environment variable."""
        with patch.dict("os.environ", {"SHADOW_MODE_ENABLED": "true"}):
            import importlib

            import k8s_monitor.shadow_mode

            importlib.reload(k8s_monitor.shadow_mode)

            assert k8s_monitor.shadow_mode.SHADOW_MODE_ENABLED is True

    @pytest.mark.asyncio
    async def test_decision_logging_when_enabled(self) -> None:
        """Decisions should be logged when shadow mode is enabled."""
        from k8s_monitor.shadow_mode import DecisionType, ShadowModeManager

        manager = ShadowModeManager()
        manager._enabled = True

        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()
        mock_redis.zadd = AsyncMock()
        manager._redis = mock_redis

        event = {
            "namespace": "default",
            "kind": "Pod",
            "name": "test-pod",
            "reason": "CrashLoopBackOff",
        }

        decision_id = await manager.log_decision(
            DecisionType.CLASSIFICATION,
            event,
            {"severity": "critical", "category": "crash_loop"},
        )

        assert decision_id != ""
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_decision_not_logged_when_disabled(self) -> None:
        """Decisions should not be logged when shadow mode is disabled."""
        from k8s_monitor.shadow_mode import DecisionType, ShadowModeManager

        manager = ShadowModeManager()
        manager._enabled = False

        event = {"namespace": "default", "name": "test"}

        decision_id = await manager.log_decision(
            DecisionType.CLASSIFICATION,
            event,
            {"severity": "low"},
        )

        assert decision_id == ""
