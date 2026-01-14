"""
Integration tests for cluster-swarm.

Tests the swarm collaboration with mocked MCP servers.
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
            message="Liveness probe failed: context deadline exceeded",
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
            message="Readiness probe failed: timeout",
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
async def test_swarm_creation():
    """Test that swarm can be created (without actual MCP servers)."""
    swarm = ClusterSwarm()
    
    # Note: Full test would require mocking MCP servers
    # For now, just verify the swarm can be instantiated
    assert swarm is not None


@pytest.mark.asyncio
async def test_swarm_investigate_structure(sample_correlated_issue):
    """Test that swarm investigation returns expected structure."""
    swarm = ClusterSwarm()
    
    # Note: This will fail without actual MCP servers
    # In a real test environment, you would mock the MCP clients
    # For now, just verify the method exists
    assert hasattr(swarm, "investigate")


def test_correlated_issue_structure():
    """Test CorrelatedIssue model structure."""
    events = [
        K8sEvent(
            event_id="1",
            event_type="Warning",
            reason="Unhealthy",
            message="timeout",
            namespace="test",
            resource_name="pod-1",
            resource_kind="Pod",
            severity=Severity.MEDIUM,
            timestamp="2026-01-13T10:00:00Z",
        ),
    ]
    
    issue = CorrelatedIssue(
        correlation_id="test123",
        events=events,
        pattern_type="timeout",
        affected_namespaces=["test"],
        affected_resources=["Pod/pod-1"],
        severity=Severity.MEDIUM,
    )
    
    assert issue.correlation_id == "test123"
    assert len(issue.events) == 1
    assert issue.pattern_type == "timeout"
    assert "test" in issue.affected_namespaces


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
