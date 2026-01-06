"""Tests for the event bus module."""

from datetime import datetime

from core_agents.events import Event, EventType


class TestEventSchema:
    """Tests for Event schema."""

    def test_create_event(self):
        """Test creating a basic event."""
        event = Event(
            id="test-123",
            type=EventType.K8S_ISSUE_DETECTED,
            source="test-agent",
            payload={"pod": "test-pod", "namespace": "default"},
        )

        assert event.id == "test-123"
        assert event.type == EventType.K8S_ISSUE_DETECTED
        assert event.source == "test-agent"
        assert event.payload["pod"] == "test-pod"

    def test_event_to_stream_data(self):
        """Test converting event to Redis Stream format."""
        event = Event(
            id="test-456",
            type=EventType.K8S_REMEDIATION_STARTED,
            source="healer",
            payload={"skill_id": "k8s-restart"},
            correlation_id="corr-123",
        )

        stream_data = event.to_stream_data()

        assert stream_data["id"] == "test-456"
        assert stream_data["type"] == "k8s:remediation_started"
        assert stream_data["source"] == "healer"
        assert "skill_id" in stream_data["payload"]
        assert stream_data["correlation_id"] == "corr-123"

    def test_event_from_stream_data(self):
        """Test parsing event from Redis Stream format."""
        stream_data = {
            b"id": b"test-789",
            b"type": b"k8s:issue_detected",
            b"source": b"sentinel",
            b"timestamp": b"2024-01-01T00:00:00",
            b"payload": b'{"pod": "my-pod"}',
            b"correlation_id": b"",
        }

        event = Event.from_stream_data(stream_data)

        assert event.id == "test-789"
        assert event.type == EventType.K8S_ISSUE_DETECTED
        assert event.source == "sentinel"
        assert event.payload["pod"] == "my-pod"
        assert event.correlation_id is None

    def test_event_default_timestamp(self):
        """Test that events get default timestamp."""
        event = Event(
            id="test",
            type=EventType.AGENT_STARTED,
            source="test",
        )

        assert event.timestamp is not None
        assert isinstance(event.timestamp, datetime)


class TestEventTypes:
    """Test event type enum."""

    def test_k8s_event_types(self):
        """Test K8s domain event types."""
        assert EventType.K8S_ISSUE_DETECTED.value == "k8s:issue_detected"
        assert EventType.K8S_REMEDIATION_STARTED.value == "k8s:remediation_started"
        assert EventType.K8S_REMEDIATION_COMPLETED.value == "k8s:remediation_completed"
        assert EventType.K8S_REMEDIATION_FAILED.value == "k8s:remediation_failed"

    def test_news_event_types(self):
        """Test News domain event types."""
        assert EventType.NEWS_ARTICLE_INGESTED.value == "news:article_ingested"
        assert EventType.NEWS_BREAKING_DETECTED.value == "news:breaking_detected"

    def test_system_event_types(self):
        """Test system event types."""
        assert EventType.SYSTEM_MCP_SERVER_REQUESTED.value == "system:mcp_server_requested"
        assert EventType.SYSTEM_APPROVAL_REQUESTED.value == "system:approval_requested"
