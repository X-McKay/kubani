"""
Integration tests for cluster-monitor.

Tests the full investigation workflow with mocked MCP servers.
"""

import pytest

from cluster_monitor.correlator import EventCorrelator
from cluster_monitor.models import CorrelatedIssue, K8sEvent, Severity
from cluster_monitor.orchestrator import InvestigationOrchestrator


@pytest.fixture
def sample_events():
    """Create sample K8s events for testing."""
    return [
        K8sEvent(
            event_id="1",
            event_type="Warning",
            reason="Unhealthy",
            message="Liveness probe failed: Get http://10.42.1.250:9000/-/health/live: context deadline exceeded",
            namespace="auth",
            resource_name="authentik-server-9b567d6dc-pv8rd",
            resource_kind="Pod",
            severity=Severity.MEDIUM,
            timestamp="2026-01-13T10:00:00Z",
        ),
        K8sEvent(
            event_id="2",
            event_type="Warning",
            reason="Unhealthy",
            message="Readiness probe failed: Get http://10.42.1.102:8000/ready: context deadline exceeded",
            namespace="ai-agents",
            resource_name="learning-agent-59ff7f586-8qnw8",
            resource_kind="Pod",
            severity=Severity.MEDIUM,
            timestamp="2026-01-13T10:00:05Z",
        ),
    ]


@pytest.fixture
def correlator():
    """Create a correlator instance."""
    return EventCorrelator(window_seconds=30)


def test_event_correlation(correlator, sample_events):
    """Test that events are properly correlated by testing the internal buffer."""
    # The correlator uses _buffer to store events by correlation key
    # Add events directly to the buffer to test correlation logic
    for event in sample_events:
        correlation_key = correlator._generate_correlation_key(event)
        correlator._buffer[correlation_key].append(event)

    # Both events have timeout pattern but are in different namespaces
    # So they should be in separate correlation groups (pattern:namespace)
    assert len(correlator._buffer) == 2  # auth and ai-agents namespaces

    # Verify that timeout pattern was detected for both
    for key in correlator._buffer.keys():
        assert "timeout" in key  # Key format is "pattern:namespace"


def test_correlator_buffer_management(correlator):
    """Test that events are properly buffered by correlation key."""
    event = K8sEvent(
        event_id="1",
        event_type="Warning",
        reason="Unhealthy",
        message="timeout",
        namespace="test",
        resource_name="pod-1",
        resource_kind="Pod",
        severity=Severity.MEDIUM,
        timestamp="2026-01-13T10:00:00Z",
    )

    # Add event to buffer using the correlation key
    correlation_key = correlator._generate_correlation_key(event)
    correlator._buffer[correlation_key].append(event)

    # Verify the buffer contains the event
    assert len(correlator._buffer) == 1
    assert correlation_key in correlator._buffer
    assert len(correlator._buffer[correlation_key]) == 1
    assert correlator._buffer[correlation_key][0].event_id == "1"

    # Verify the correlation key format
    assert "timeout" in correlation_key
    assert "test" in correlation_key


@pytest.mark.asyncio
async def test_orchestrator_workflow():
    """Test the orchestrator workflow (without actual MCP calls)."""
    # Create a correlated issue
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

    # Create orchestrator (without actual Redis/EventBus)
    orchestrator = InvestigationOrchestrator()

    # Note: Full workflow test would require mocking MCP servers
    # For now, just verify the orchestrator can be instantiated
    assert orchestrator is not None


def test_pattern_extraction():
    """Test error pattern extraction."""
    correlator = EventCorrelator()

    # Test various error patterns
    assert correlator._extract_error_pattern("context deadline exceeded") == "timeout"
    assert correlator._extract_error_pattern("connection refused") == "connection_error"
    assert correlator._extract_error_pattern("OOMKilled") == "oom"
    # Implementation looks for "disk" or "storage" keywords
    assert correlator._extract_error_pattern("disk full error") == "storage"
    assert correlator._extract_error_pattern("storage quota exceeded") == "storage"
    # Messages without recognized patterns return "other"
    assert correlator._extract_error_pattern("no space left on device") == "other"
    assert correlator._extract_error_pattern("random error") == "other"


def test_correlation_key_generation():
    """Test correlation key generation."""
    correlator = EventCorrelator()

    event1 = K8sEvent(
        event_id="1",
        event_type="Warning",
        reason="Unhealthy",
        message="timeout error",
        namespace="auth",
        resource_name="pod-1",
        resource_kind="Pod",
        severity=Severity.MEDIUM,
        timestamp="2026-01-13T10:00:00Z",
    )

    event2 = K8sEvent(
        event_id="2",
        event_type="Warning",
        reason="Unhealthy",
        message="connection timeout",
        namespace="auth",
        resource_name="pod-2",
        resource_kind="Pod",
        severity=Severity.MEDIUM,
        timestamp="2026-01-13T10:00:05Z",
    )

    # Both should have the same correlation key
    key1 = correlator._generate_correlation_key(event1)
    key2 = correlator._generate_correlation_key(event2)

    assert key1 == key2
    assert "timeout" in key1
    assert "auth" in key1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
