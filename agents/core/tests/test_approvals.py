"""Tests for the approval flow module."""

import pytest

from core_agents.approvals import (
    ApprovalRequest,
    ApprovalResult,
    ApprovalStatus,
    Approver,
)


class TestApprovalRequest:
    """Tests for ApprovalRequest schema."""

    def test_create_request(self):
        """Test creating a basic approval request."""
        request = ApprovalRequest(
            action="drain_node",
            resource="node/worker-1",
            reason="Node maintenance required",
        )

        assert request.action == "drain_node"
        assert request.resource == "node/worker-1"
        assert request.reason == "Node maintenance required"
        assert request.timeout_seconds == 300  # Default

    def test_request_with_skill(self):
        """Test approval request with skill context."""
        request = ApprovalRequest(
            action="scale_deployment",
            resource="deployment/my-app",
            reason="High load detected",
            skill_id="k8s-scale-deployment",
            agent="healer-agent",
            context={"current_replicas": 3, "target_replicas": 5},
        )

        assert request.skill_id == "k8s-scale-deployment"
        assert request.agent == "healer-agent"
        assert request.context["current_replicas"] == 3

    def test_format_discord_message(self):
        """Test formatting request for Discord."""
        request = ApprovalRequest(
            action="restart_pod",
            resource="pod/my-pod",
            reason="Pod is in CrashLoopBackOff",
            skill_id="k8s-restart-crashloop",
        )

        message = request.format_discord_message()

        assert "restart_pod" in message
        assert "pod/my-pod" in message
        assert "CrashLoopBackOff" in message
        assert "✅" in message
        assert "❌" in message


class TestApprovalResult:
    """Tests for ApprovalResult schema."""

    def test_approved_result(self):
        """Test creating an approved result."""
        request = ApprovalRequest(
            action="test_action",
            resource="test/resource",
            reason="Testing",
        )

        result = ApprovalResult.approved_result(request, responder="user123")

        assert result.status == ApprovalStatus.APPROVED
        assert result.approved is True
        assert result.responder == "user123"

    def test_rejected_result(self):
        """Test creating a rejected result."""
        request = ApprovalRequest(
            action="dangerous_action",
            resource="test/resource",
            reason="Testing",
        )

        result = ApprovalResult.rejected_result(request, responder="admin", reason="Too risky")

        assert result.status == ApprovalStatus.REJECTED
        assert result.approved is False
        assert result.responder == "admin"
        assert result.response_reason == "Too risky"

    def test_timeout_result(self):
        """Test creating a timeout result."""
        request = ApprovalRequest(
            action="slow_action",
            resource="test/resource",
            reason="Testing",
        )

        result = ApprovalResult.timeout_result(request)

        assert result.status == ApprovalStatus.TIMEOUT
        assert result.approved is False

    def test_error_result(self):
        """Test creating an error result."""
        request = ApprovalRequest(
            action="failed_action",
            resource="test/resource",
            reason="Testing",
        )

        result = ApprovalResult.error_result(request, "Connection failed")

        assert result.status == ApprovalStatus.ERROR
        assert result.approved is False
        assert result.response_reason == "Connection failed"


class TestApprovalStatus:
    """Tests for ApprovalStatus enum."""

    def test_all_statuses(self):
        """Test all approval statuses exist."""
        assert ApprovalStatus.PENDING
        assert ApprovalStatus.APPROVED
        assert ApprovalStatus.REJECTED
        assert ApprovalStatus.TIMEOUT
        assert ApprovalStatus.ERROR


class TestApproverBase:
    """Tests for Approver base class."""

    def test_approver_is_abstract(self):
        """Test that Approver cannot be instantiated directly."""
        with pytest.raises(TypeError):
            Approver()  # type: ignore

    def test_approver_requires_request_approval(self):
        """Test that subclasses must implement request_approval."""

        class IncompleteApprover(Approver):
            pass

        with pytest.raises(TypeError):
            IncompleteApprover()  # type: ignore
