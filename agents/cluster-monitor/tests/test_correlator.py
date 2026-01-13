"""
Tests for the Correlator service.
"""

import pytest

from cluster_monitor.correlator import EventCorrelator
from cluster_monitor.models import K8sEvent, Severity


@pytest.fixture
def correlator():
    """Create a test correlator instance."""
    return EventCorrelator(window_seconds=5)


def test_extract_error_pattern_timeout():
    """Test timeout pattern extraction."""
    correlator = EventCorrelator()
    
    assert correlator._extract_error_pattern("context deadline exceeded") == "timeout"
    assert correlator._extract_error_pattern("connection timed out") == "timeout"
    assert correlator._extract_error_pattern("timeout waiting for response") == "timeout"


def test_extract_error_pattern_connection():
    """Test connection error pattern extraction."""
    correlator = EventCorrelator()
    
    assert correlator._extract_error_pattern("connection refused") == "connection_error"
    assert correlator._extract_error_pattern("connection reset by peer") == "connection_error"
    assert correlator._extract_error_pattern("no route to host") == "connection_error"


def test_extract_error_pattern_oom():
    """Test OOM pattern extraction."""
    correlator = EventCorrelator()
    
    assert correlator._extract_error_pattern("OOMKilled") == "oom"
    assert correlator._extract_error_pattern("out of memory") == "oom"


def test_generate_correlation_key():
    """Test correlation key generation."""
    correlator = EventCorrelator()
    
    event1 = K8sEvent(
        event_id="1",
        event_type="Warning",
        reason="Unhealthy",
        message="context deadline exceeded",
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
        message="timeout waiting for response",
        namespace="auth",
        resource_name="pod-2",
        resource_kind="Pod",
        severity=Severity.MEDIUM,
        timestamp="2026-01-13T10:00:05Z",
    )
    
    # Both should have the same correlation key (timeout + auth namespace)
    key1 = correlator._generate_correlation_key(event1)
    key2 = correlator._generate_correlation_key(event2)
    
    assert key1 == key2
    assert key1 == "timeout:auth"


def test_should_process_immediately_critical():
    """Test immediate processing for critical events."""
    correlator = EventCorrelator()
    
    critical_event = K8sEvent(
        event_id="1",
        event_type="Error",
        reason="OOMKilled",
        message="Container killed due to OOM",
        namespace="prod",
        resource_name="pod-1",
        resource_kind="Pod",
        severity=Severity.CRITICAL,
        timestamp="2026-01-13T10:00:00Z",
    )
    
    assert correlator._should_process_immediately(critical_event) is True


def test_should_process_immediately_normal():
    """Test buffering for normal events."""
    correlator = EventCorrelator()
    
    normal_event = K8sEvent(
        event_id="1",
        event_type="Warning",
        reason="Unhealthy",
        message="Liveness probe failed",
        namespace="dev",
        resource_name="pod-1",
        resource_kind="Pod",
        severity=Severity.MEDIUM,
        timestamp="2026-01-13T10:00:00Z",
    )
    
    assert correlator._should_process_immediately(normal_event) is False
