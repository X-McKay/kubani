"""
Tests for the Cluster Swarm.
"""

import pytest

from cluster_swarm.models import CorrelatedIssue, K8sEvent, Severity, SwarmContext
from cluster_swarm.swarm import ClusterSwarm


@pytest.fixture
def sample_correlated_issue():
    """Create a sample correlated issue for testing."""
    events = [
        K8sEvent(
            event_id="1",
            event_type="Warning",
            reason="Unhealthy",
            message="context deadline exceeded",
            namespace="auth",
            resource_name="pod-1",
            resource_kind="Pod",
            severity=Severity.MEDIUM,
            timestamp="2026-01-13T10:00:00Z",
        ),
        K8sEvent(
            event_id="2",
            event_type="Warning",
            reason="Unhealthy",
            message="timeout waiting for response",
            namespace="auth",
            resource_name="pod-2",
            resource_kind="Pod",
            severity=Severity.MEDIUM,
            timestamp="2026-01-13T10:00:05Z",
        ),
    ]

    return CorrelatedIssue(
        correlation_id="test123",
        events=events,
        pattern_type="timeout",
        affected_namespaces=["auth"],
        affected_resources=["Pod/pod-1", "Pod/pod-2"],
        severity=Severity.MEDIUM,
    )


def test_swarm_context_creation(sample_correlated_issue):
    """Test SwarmContext creation from CorrelatedIssue."""
    context = SwarmContext(
        correlation_id=sample_correlated_issue.correlation_id,
        events=sample_correlated_issue.events,
        pattern_type=sample_correlated_issue.pattern_type,
        severity=sample_correlated_issue.severity,
    )

    assert context.correlation_id == "test123"
    assert len(context.events) == 2
    assert context.pattern_type == "timeout"
    assert context.severity == Severity.MEDIUM
    assert context.diagnostic_findings == {}
    assert context.past_incidents == []


def test_swarm_context_accumulation():
    """Test that SwarmContext accumulates findings."""
    context = SwarmContext(
        correlation_id="test123",
        events=[],
        pattern_type="timeout",
        severity=Severity.MEDIUM,
    )

    # Simulate findings accumulation
    context.diagnostic_findings["root_cause"] = "network issue"
    context.past_incidents.append({"timestamp": "2026-01-10", "resolution": "restart CNI"})
    context.remediation_plan = {"action": "restart CNI plugin"}

    assert context.diagnostic_findings["root_cause"] == "network issue"
    assert len(context.past_incidents) == 1
    assert context.remediation_plan["action"] == "restart CNI plugin"


@pytest.mark.asyncio
async def test_swarm_investigate_structure(sample_correlated_issue):
    """Test that swarm investigation returns expected structure.

    Note: This test requires MCP servers to be available. When they're not,
    the test verifies that the appropriate exception is raised. In a CI
    environment with MCP servers available, it would test the full flow.
    """
    from strands.types.exceptions import MCPClientInitializationError

    swarm = ClusterSwarm()

    # The swarm requires MCP servers to be available.
    # When MCP servers are not available (typical in unit tests),
    # MCPClientInitializationError is raised during swarm creation.
    try:
        result = await swarm.investigate(sample_correlated_issue)
        # If MCP servers are available, verify the result structure
        assert "correlation_id" in result
        assert result["correlation_id"] == "test123"
        assert "investigation_complete" in result
    except MCPClientInitializationError:
        # Expected when MCP servers are not available
        # This is acceptable behavior for unit tests
        pytest.skip("MCP servers not available - skipping integration test")
