"""
Tests for remediation activities, workflows, and swarm parsing.
"""

import pytest

from k8s_monitor.activities import _extract_issues_from_summary
from k8s_monitor.models import (
    DiscordMessageType,
    FixAttempt,
    HealthStatus,
    Investigation,
    Issue,
    RemediationRecord,
    RemediationStatus,
)
from k8s_monitor.remediation_activities import (
    _build_escalation_embed,
    _build_fix_failed_embed,
    _build_fix_success_embed,
    _build_investigation_embed,
    _build_issue_detected_embed,
)
from k8s_monitor.swarm import (
    _parse_fix_result,
    _parse_investigation_result,
)


class TestSwarmParsing:
    """Test swarm result parsing functions."""

    def test_parse_investigation_simple(self):
        """Parse simple investigation result."""
        text = """ROOT_CAUSE: OOM killed
FINDINGS: Pod exceeded memory limits
PROPOSED_FIX: Increase memory limit
CONFIDENCE: 0.85"""
        result = _parse_investigation_result(text)
        assert result["root_cause"] == "OOM killed"
        assert "memory" in result["findings"].lower()
        assert result["confidence"] == 0.85

    def test_parse_investigation_missing_fields(self):
        """Parse investigation with missing fields."""
        text = "Some raw output without structured fields"
        result = _parse_investigation_result(text)
        assert result["root_cause"] == "See findings"
        assert result["confidence"] == 0.5

    def test_parse_fix_result_success(self):
        """Parse successful fix result."""
        text = """ACTION_TAKEN: Restarted pod
SUCCESS: true
RESULT: Pod now running
ERROR: none"""
        result = _parse_fix_result(text, 1)
        assert result["success"] is True
        assert "Restarted" in result["action_taken"]
        assert result["error_message"] is None

    def test_parse_fix_result_failure(self):
        """Parse failed fix result."""
        text = """ACTION_TAKEN: Tried to restart
SUCCESS: false
RESULT: Operation failed
ERROR: Pod not found"""
        result = _parse_fix_result(text, 2)
        assert result["success"] is False
        assert result["error_message"] == "Pod not found"
        assert result["attempt_number"] == 2


class TestExtractIssuesFromSummary:
    """Test issue extraction from health summaries."""

    def test_healthy_status_returns_empty(self):
        """Healthy status returns no issues."""
        issues = _extract_issues_from_summary("All pods running", HealthStatus.HEALTHY)
        assert issues == []

    def test_extracts_pod_issue(self):
        """Extract pod issue from summary."""
        summary = "`my-pod` (default) - *CrashLoopBackOff*"
        issues = _extract_issues_from_summary(summary, HealthStatus.CRITICAL)
        assert len(issues) == 1
        assert issues[0].resource_name == "my-pod"
        assert issues[0].namespace == "default"
        assert issues[0].severity == HealthStatus.CRITICAL

    def test_extracts_pending_issue(self):
        """Extract pending pod issue."""
        summary = "`pending-pod` (kube-system) - *Pending*"
        issues = _extract_issues_from_summary(summary, HealthStatus.WARNING)
        assert len(issues) == 1
        assert issues[0].resource_name == "pending-pod"
        assert issues[0].severity == HealthStatus.WARNING

    def test_skips_healthy_resources_in_pattern(self):
        """Skip resources with healthy status in pattern matching."""
        # Even when status is WARNING, specific Running/Ready resources aren't extracted as issues
        # But a generic issue is created since status != HEALTHY
        summary = "`healthy-pod` (default) - *Running*"
        issues = _extract_issues_from_summary(summary, HealthStatus.WARNING)
        # Generic issue created because status is WARNING
        assert len(issues) == 1
        assert issues[0].resource_type == "Cluster"  # Generic, not the specific pod

    def test_no_issues_when_healthy(self):
        """No issues created when status is HEALTHY."""
        summary = "`healthy-pod` (default) - *Running*"
        issues = _extract_issues_from_summary(summary, HealthStatus.HEALTHY)
        assert len(issues) == 0

    def test_extracts_issue_with_is_format(self):
        """Extract issue using 'is' format."""
        summary = "`svclb-traefik-dvqct` (kube-system) is **Pending**"
        issues = _extract_issues_from_summary(summary, HealthStatus.WARNING)
        assert len(issues) == 1
        assert issues[0].resource_name == "svclb-traefik-dvqct"
        assert issues[0].namespace == "kube-system"

    def test_extracts_issue_with_has_format(self):
        """Extract issue using 'has' format."""
        summary = "`prometheus-node-exporter-qhqcf` (monitoring) has **BackOff**"
        issues = _extract_issues_from_summary(summary, HealthStatus.WARNING)
        assert len(issues) == 1
        assert issues[0].resource_name == "prometheus-node-exporter-qhqcf"
        assert issues[0].severity == HealthStatus.CRITICAL  # BackOff is critical

    def test_extracts_issue_with_direct_format(self):
        """Extract issue using direct format without separator."""
        summary = "`svclb-traefik-dvqct` (kube-system) **Pending**"
        issues = _extract_issues_from_summary(summary, HealthStatus.WARNING)
        assert len(issues) == 1
        assert issues[0].resource_name == "svclb-traefik-dvqct"
        assert issues[0].namespace == "kube-system"

    def test_creates_generic_issue_if_none_extracted(self):
        """Create generic issue when pattern doesn't match."""
        summary = "Something is wrong but no specific pattern"
        issues = _extract_issues_from_summary(summary, HealthStatus.CRITICAL)
        assert len(issues) == 1
        assert issues[0].title == "Cluster health issue detected"
        assert issues[0].resource_type == "Cluster"


class TestModels:
    """Test Pydantic models for remediation."""

    def test_issue_model(self):
        """Test Issue model creation."""
        issue = Issue(
            id="test-123",
            title="Pod CrashLoopBackOff",
            description="Pod is crashing",
            severity=HealthStatus.CRITICAL,
            resource_type="Pod",
            resource_name="my-pod",
            namespace="default",
            detected_at="2024-01-01T00:00:00Z",
        )
        assert issue.id == "test-123"
        assert issue.severity == HealthStatus.CRITICAL

    def test_investigation_model(self):
        """Test Investigation model creation."""
        investigation = Investigation(
            issue_id="test-123",
            findings="Pod lacks resources",
            root_cause="OOM killed",
            proposed_fix="Increase memory limits",
            fix_command="kubectl patch...",
            confidence=0.8,
            investigated_at="2024-01-01T00:00:00Z",
        )
        assert investigation.confidence == 0.8
        assert investigation.root_cause == "OOM killed"

    def test_fix_attempt_model(self):
        """Test FixAttempt model creation."""
        fix = FixAttempt(
            attempt_number=1,
            action_taken="Restarted deployment",
            command_executed="kubectl rollout restart",
            result="Deployment restarted",
            success=True,
            attempted_at="2024-01-01T00:00:00Z",
        )
        assert fix.success is True
        assert fix.attempt_number == 1

    def test_remediation_record_model(self):
        """Test RemediationRecord model creation."""
        issue = Issue(
            id="test-123",
            title="Test issue",
            description="Description",
            severity=HealthStatus.WARNING,
            resource_type="Pod",
            resource_name="test-pod",
            namespace="default",
            detected_at="2024-01-01T00:00:00Z",
        )
        record = RemediationRecord(
            issue=issue,
            status=RemediationStatus.PENDING,
            started_at="2024-01-01T00:00:00Z",
        )
        assert record.current_attempt == 0
        assert record.can_retry is False  # Status is PENDING, not FAILED

    def test_remediation_record_can_retry(self):
        """Test can_retry property."""
        issue = Issue(
            id="test-123",
            title="Test issue",
            description="Description",
            severity=HealthStatus.WARNING,
            resource_type="Pod",
            resource_name="test-pod",
            namespace="default",
            detected_at="2024-01-01T00:00:00Z",
        )
        record = RemediationRecord(
            issue=issue,
            status=RemediationStatus.FAILED,
            started_at="2024-01-01T00:00:00Z",
        )
        assert record.can_retry is True

        # Add 3 fix attempts
        for i in range(3):
            record.fix_attempts.append(
                FixAttempt(
                    attempt_number=i + 1,
                    action_taken="Test",
                    command_executed="test",
                    result="Failed",
                    success=False,
                    attempted_at="2024-01-01T00:00:00Z",
                )
            )
        assert record.can_retry is False


class TestDiscordEmbeds:
    """Test Discord embed generation for remediation messages."""

    @pytest.fixture
    def sample_issue(self) -> Issue:
        """Create a sample issue for testing."""
        return Issue(
            id="test-123",
            title="Pod CrashLoopBackOff",
            description="Pod my-pod is crashing repeatedly",
            severity=HealthStatus.CRITICAL,
            resource_type="Pod",
            resource_name="my-pod",
            namespace="default",
            detected_at="2024-01-01T00:00:00Z",
        )

    def test_build_issue_detected_embed(self, sample_issue):
        """Test issue detected embed."""
        embed = _build_issue_detected_embed("emoji", 0xFF0000, sample_issue)
        assert "Issue Detected" in embed["title"]
        assert sample_issue.title in embed["description"]
        assert any(f["name"] == "Resource" for f in embed["fields"])

    def test_build_investigation_embed(self, sample_issue):
        """Test investigation complete embed."""
        investigation_dict = {
            "findings": "Pod running out of memory",
            "root_cause": "Memory limit too low",
            "proposed_fix": "Increase memory limit",
            "confidence": 0.85,
        }
        embed = _build_investigation_embed("emoji", 0x0000FF, sample_issue, investigation_dict)
        assert "Investigation Complete" in embed["title"]
        assert any(f["name"] == "Root Cause" for f in embed["fields"])

    def test_build_fix_success_embed(self, sample_issue):
        """Test fix success embed."""
        fix_dict = {
            "action_taken": "Restarted deployment",
            "result": "Deployment now healthy",
            "attempt_number": 1,
        }
        embed = _build_fix_success_embed("emoji", 0x00FF00, sample_issue, fix_dict)
        assert "Issue Resolved" in embed["title"]

    def test_build_fix_failed_embed(self, sample_issue):
        """Test fix failed embed."""
        fix_dict = {
            "action_taken": "Tried to restart",
            "error_message": "Deployment not found",
            "attempt_number": 1,
        }
        embed = _build_fix_failed_embed("emoji", 0xFF0000, sample_issue, fix_dict, None)
        assert "Fix Attempt Failed" in embed["title"]
        assert any(f["name"] == "Attempts Remaining" for f in embed["fields"])

    def test_build_escalation_embed(self, sample_issue):
        """Test escalation embed."""
        record_dict = {
            "fix_attempts": [
                {"action_taken": "Attempt 1", "error_message": "Error 1"},
                {"action_taken": "Attempt 2", "error_message": "Error 2"},
                {"action_taken": "Attempt 3", "error_message": "Error 3"},
            ]
        }
        embed = _build_escalation_embed("emoji", 0xFF0000, sample_issue, record_dict)
        assert "HUMAN INTERVENTION REQUIRED" in embed["title"]
        assert any(f["name"] == "Recommended Actions" for f in embed["fields"])


class TestDiscordMessageTypes:
    """Test Discord message type enum."""

    def test_all_message_types_exist(self):
        """Verify all expected message types exist."""
        assert DiscordMessageType.ISSUE_DETECTED
        assert DiscordMessageType.INVESTIGATION_COMPLETE
        assert DiscordMessageType.FIX_ATTEMPTED
        assert DiscordMessageType.FIX_SUCCESS
        assert DiscordMessageType.FIX_FAILED
        assert DiscordMessageType.ESCALATION
        assert DiscordMessageType.HEALTH_REPORT
