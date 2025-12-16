"""Tests for Pydantic models and health status logic."""

import pytest
from pydantic import ValidationError

from k8s_monitor.activities import (
    ClusterHealthReport,
    DiscordPostResult,
    HealthStatus,
    _determine_status,
)


class TestHealthStatus:
    """Tests for the HealthStatus enum."""

    def test_health_status_values(self) -> None:
        """Verify all expected status values exist."""
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.WARNING.value == "warning"
        assert HealthStatus.CRITICAL.value == "critical"
        assert HealthStatus.ERROR.value == "error"

    def test_health_status_is_string_enum(self) -> None:
        """Verify HealthStatus behaves as a string enum."""
        assert str(HealthStatus.HEALTHY) == "HealthStatus.HEALTHY"
        assert HealthStatus.HEALTHY == "healthy"


class TestDetermineStatus:
    """Tests for the _determine_status function."""

    @pytest.mark.parametrize(
        "summary,expected",
        [
            ("All systems healthy and running", HealthStatus.HEALTHY),
            ("Cluster is in good condition", HealthStatus.HEALTHY),
            ("Status: OK, no issues found", HealthStatus.HEALTHY),
        ],
    )
    def test_healthy_status(self, summary: str, expected: HealthStatus) -> None:
        """Healthy summaries should return HEALTHY status."""
        assert _determine_status(summary) == expected

    @pytest.mark.parametrize(
        "summary,expected",
        [
            ("Warning: Pod is pending", HealthStatus.WARNING),
            ("Node degraded performance", HealthStatus.WARNING),
            ("Some pods are pending scheduling", HealthStatus.WARNING),
            ("Node status: NotReady", HealthStatus.WARNING),
            ("Unhealthy deployment found", HealthStatus.WARNING),
        ],
    )
    def test_warning_status(self, summary: str, expected: HealthStatus) -> None:
        """Warning keywords should return WARNING status."""
        assert _determine_status(summary) == expected

    @pytest.mark.parametrize(
        "summary,expected",
        [
            ("Critical: Node is down", HealthStatus.CRITICAL),
            ("Error: Failed to schedule pod", HealthStatus.CRITICAL),
            ("Pod in CrashLoopBackOff", HealthStatus.CRITICAL),
            ("Deployment failed", HealthStatus.CRITICAL),
            ("Node down, cluster degraded", HealthStatus.CRITICAL),
        ],
    )
    def test_critical_status(self, summary: str, expected: HealthStatus) -> None:
        """Critical keywords should return CRITICAL status."""
        assert _determine_status(summary) == expected

    def test_critical_takes_precedence_over_warning(self) -> None:
        """When both critical and warning keywords present, CRITICAL wins."""
        summary = "Warning: Pod pending, Critical node down"
        assert _determine_status(summary) == HealthStatus.CRITICAL

    def test_case_insensitive(self) -> None:
        """Status detection should be case insensitive."""
        assert _determine_status("WARNING detected") == HealthStatus.WARNING
        assert _determine_status("CRITICAL failure") == HealthStatus.CRITICAL


class TestClusterHealthReport:
    """Tests for the ClusterHealthReport Pydantic model."""

    def test_valid_report(self) -> None:
        """Valid report creation should succeed."""
        report = ClusterHealthReport(
            summary="All systems operational",
            status=HealthStatus.HEALTHY,
            timestamp="2024-01-01T00:00:00Z",
        )
        assert report.summary == "All systems operational"
        assert report.status == HealthStatus.HEALTHY
        assert report.error is None

    def test_report_with_error(self) -> None:
        """Report with error field should work."""
        report = ClusterHealthReport(
            summary="",
            status=HealthStatus.ERROR,
            timestamp="2024-01-01T00:00:00Z",
            error="Failed to connect to cluster",
        )
        assert report.error == "Failed to connect to cluster"

    def test_report_is_immutable(self) -> None:
        """Report should be immutable (frozen)."""
        report = ClusterHealthReport(
            summary="Test",
            status=HealthStatus.HEALTHY,
            timestamp="2024-01-01T00:00:00Z",
        )
        with pytest.raises(ValidationError):
            report.summary = "Modified"  # type: ignore[misc]

    def test_report_requires_all_fields(self) -> None:
        """Report should require summary, status, and timestamp."""
        with pytest.raises(ValidationError):
            ClusterHealthReport(summary="Test")  # type: ignore[call-arg]


class TestDiscordPostResult:
    """Tests for the DiscordPostResult Pydantic model."""

    def test_successful_result(self) -> None:
        """Successful result creation."""
        result = DiscordPostResult(success=True, message_id="12345")
        assert result.success is True
        assert result.message_id == "12345"
        assert result.error is None

    def test_failed_result(self) -> None:
        """Failed result with error message."""
        result = DiscordPostResult(success=False, error="Connection timeout")
        assert result.success is False
        assert result.error == "Connection timeout"

    def test_minimal_result(self) -> None:
        """Minimal result with just success flag."""
        result = DiscordPostResult(success=True)
        assert result.success is True
        assert result.message_id is None
        assert result.error is None
