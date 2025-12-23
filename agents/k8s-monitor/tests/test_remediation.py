"""
Tests for remediation activities, workflows, and swarm parsing.
"""

import pytest

from core_agents.discord_utils import (
    format_escalation,
    format_fix_failure,
    format_fix_success,
    format_investigation_results,
    format_issue_detection,
)
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
from k8s_monitor.swarm import (
    _extract_swarm_output,
    _is_failed_status,
    _parse_fix_result,
    _parse_investigation_result,
)


class TestIsFailedStatus:
    """Test _is_failed_status helper function."""

    def test_none_returns_false(self):
        """None status should return False."""
        assert _is_failed_status(None) is False

    def test_string_failed_returns_true(self):
        """String 'failed' should return True."""
        assert _is_failed_status("failed") is True
        assert _is_failed_status("FAILED") is True
        assert _is_failed_status("Failed") is True

    def test_string_error_returns_true(self):
        """String 'error' should return True."""
        assert _is_failed_status("error") is True
        assert _is_failed_status("ERROR") is True

    def test_string_completed_returns_false(self):
        """String 'completed' should return False."""
        assert _is_failed_status("completed") is False
        assert _is_failed_status("COMPLETED") is False
        assert _is_failed_status("success") is False

    def test_enum_with_value_failed(self):
        """Enum with .value='failed' should return True."""
        mock_enum = type("Status", (), {"value": "failed"})()
        assert _is_failed_status(mock_enum) is True

    def test_enum_with_value_completed(self):
        """Enum with .value='completed' should return False."""
        mock_enum = type("Status", (), {"value": "completed"})()
        assert _is_failed_status(mock_enum) is False

    def test_enum_with_name_failed(self):
        """Enum with .name='FAILED' (no .value) should return True."""
        mock_enum = type("Status", (), {"name": "FAILED"})()
        assert _is_failed_status(mock_enum) is True


class MockNodeResult:
    """Mock NodeResult for testing SwarmResult extraction."""

    def __init__(self, result):
        self.result = result


class MockSwarmResult:
    """Mock SwarmResult for testing output extraction."""

    def __init__(self, results: dict, status_value: str = "completed"):
        self.results = results
        self.status = type("Status", (), {"value": status_value})()


class TestExtractSwarmOutput:
    """Test _extract_swarm_output function."""

    def test_string_input_returned_directly(self):
        """String input should be returned as-is."""
        result = _extract_swarm_output("Already a string")
        assert result == "Already a string"

    def test_extract_from_discord_notifier(self):
        """Should prioritize discord_notifier agent output."""
        mock_result = MockSwarmResult(
            {
                "cluster_triage": MockNodeResult("Triage output"),
                "cluster_scout": MockNodeResult("Scout findings"),
                "discord_notifier": MockNodeResult("Discord notification sent successfully"),
            }
        )
        result = _extract_swarm_output(mock_result)
        assert result == "Discord notification sent successfully"

    def test_extract_from_multiple_agents_without_discord(self):
        """Should collect outputs from all agents when discord_notifier is missing."""
        mock_result = MockSwarmResult(
            {
                "cluster_triage": MockNodeResult("Triage output"),
                "cluster_scout": MockNodeResult("Scout findings"),
            }
        )
        result = _extract_swarm_output(mock_result)
        assert "[cluster_triage]: Triage output" in result
        assert "[cluster_scout]: Scout findings" in result

    def test_extract_skips_exception_results(self):
        """Should skip exception results and use valid outputs."""
        mock_result = MockSwarmResult(
            {
                "cluster_triage": MockNodeResult(Exception("Model not found")),
                "cluster_scout": MockNodeResult("Scout findings"),
            }
        )
        result = _extract_swarm_output(mock_result)
        assert "[cluster_scout]: Scout findings" in result
        assert "Exception" not in result
        assert "Model not found" not in result

    def test_extract_failed_swarm_reports_error(self):
        """Should report error when swarm failed and all results are exceptions."""
        mock_result = MockSwarmResult(
            {"cluster_triage": MockNodeResult(Exception("Model not found"))},
            status_value="failed",
        )
        result = _extract_swarm_output(mock_result)
        assert "failed" in result.lower()
        assert "cluster_triage" in result
        assert "Model not found" in result

    def test_extract_skips_none_results(self):
        """Should skip None results."""
        mock_result = MockSwarmResult(
            {
                "cluster_triage": MockNodeResult(None),
                "cluster_scout": MockNodeResult("Scout findings"),
            }
        )
        result = _extract_swarm_output(mock_result)
        assert "[cluster_scout]: Scout findings" in result
        assert "cluster_triage" not in result

    def test_extract_empty_discord_notifier_falls_back(self):
        """Should fall back to other agents if discord_notifier result is empty."""
        mock_result = MockSwarmResult(
            {
                "cluster_triage": MockNodeResult("Triage output"),
                "discord_notifier": MockNodeResult(""),
            }
        )
        result = _extract_swarm_output(mock_result)
        assert "[cluster_triage]: Triage output" in result


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

    def test_format_issue_detection(self, sample_issue):
        """Test issue detected embed using core formatter."""
        embed = format_issue_detection(
            issue_title=sample_issue.title,
            resource_type=sample_issue.resource_type,
            resource_name=sample_issue.resource_name,
            namespace=sample_issue.namespace,
            severity=sample_issue.severity.value,
            description=sample_issue.description,
        )
        embed_dict = embed.to_dict()
        assert "Issue Detected" in embed_dict["title"]
        assert sample_issue.title in embed_dict["title"]

    def test_format_investigation_results(self, sample_issue):
        """Test investigation complete embed using core formatter."""
        embed = format_investigation_results(
            issue_title=sample_issue.title,
            root_cause="Memory limit too low",
            evidence=["Pod running out of memory"],
            proposed_fix="Increase memory limit",
            confidence=0.85,
        )
        embed_dict = embed.to_dict()
        assert "Investigation Complete" in embed_dict["title"]
        assert "Root Cause" in embed_dict["description"]

    def test_format_fix_success(self, sample_issue):
        """Test fix success embed using core formatter."""
        embed = format_fix_success(
            issue_title=sample_issue.title,
            fix_applied="Restarted deployment",
            result="Deployment now healthy",
            recurrence_count=1,
        )
        embed_dict = embed.to_dict()
        assert "Issue Resolved" in embed_dict["title"]

    def test_format_fix_failure(self, sample_issue):
        """Test fix failed embed using core formatter."""
        embed = format_fix_failure(
            issue_title=sample_issue.title,
            attempt_number=1,
            max_attempts=3,
            result="Deployment not found",
            next_action="Re-investigating...",
        )
        embed_dict = embed.to_dict()
        assert "Fix Attempt" in embed_dict["title"]
        assert "Failed" in embed_dict["title"]

    def test_format_escalation(self, sample_issue):
        """Test escalation embed using core formatter."""
        embed = format_escalation(
            issue_title=sample_issue.title,
            resource_type=sample_issue.resource_type,
            resource_name=sample_issue.resource_name,
            namespace=sample_issue.namespace,
            attempts=3,
            attempts_summary=["Attempt 1 → Error 1", "Attempt 2 → Error 2", "Attempt 3 → Error 3"],
            root_cause="Unknown",
            action_required=["Check logs", "Verify config"],
        )
        embed_dict = embed.to_dict()
        assert "URGENT" in embed_dict["title"]
        assert "Action Required" in embed_dict["description"]


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
