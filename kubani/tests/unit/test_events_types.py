"""
Tests for Event type serialization and deserialization.
"""

from datetime import datetime

import pytest

from kubani.framework.events.types import Event, EventType


class TestEventSerialization:
    """Test Event.to_stream_data() and Event.from_stream_data()"""

    def test_to_stream_data_returns_all_string_values(self, event_factory):
        """All values in stream data must be strings for Redis"""
        event = event_factory(
            event_type=EventType.K8S_ISSUE_DETECTED,
            payload={"pod": "test-pod", "count": 5},
        )

        stream_data = event.to_stream_data()

        # All values must be strings
        assert all(isinstance(v, str) for v in stream_data.values())

    def test_to_stream_data_includes_required_fields(self, event_factory):
        """Stream data must include id, type, source, timestamp, payload"""
        event = event_factory()

        stream_data = event.to_stream_data()

        assert "id" in stream_data
        assert "type" in stream_data
        assert "source" in stream_data
        assert "timestamp" in stream_data
        assert "payload" in stream_data

    def test_serialization_roundtrip_preserves_data(self, event_factory):
        """Event -> stream_data -> Event should preserve all data"""
        original = event_factory(
            event_type=EventType.K8S_ISSUE_DETECTED,
            source="test-agent",
            payload={"pod": "test-pod", "namespace": "default"},
            correlation_id="corr-123",
        )

        # Serialize to stream data
        stream_data = original.to_stream_data()

        # Convert to bytes (as Redis would)
        stream_bytes = {k.encode(): v.encode() for k, v in stream_data.items()}

        # Deserialize back
        reconstructed = Event.from_stream_data(stream_bytes)

        # Verify all fields match
        assert reconstructed.id == original.id
        assert reconstructed.type == original.type
        assert reconstructed.source == original.source
        assert reconstructed.payload == original.payload
        assert reconstructed.correlation_id == original.correlation_id

    def test_from_stream_data_handles_missing_correlation_id(self):
        """from_stream_data should handle missing correlation_id gracefully"""
        stream_data = {
            b"id": b"test-123",
            b"type": b"k8s:issue_detected",
            b"source": b"test-agent",
            b"timestamp": datetime.utcnow().isoformat().encode(),
            b"payload": b"{}",
            b"correlation_id": b"",  # Empty string
        }

        event = Event.from_stream_data(stream_data)

        assert event.correlation_id is None

    def test_from_stream_data_raises_on_missing_type(self):
        """from_stream_data should raise ValueError if type is missing"""
        stream_data = {
            b"id": b"test-123",
            b"source": b"test-agent",
            b"timestamp": datetime.utcnow().isoformat().encode(),
            b"payload": b"{}",
        }

        with pytest.raises(ValueError, match="missing 'type'"):
            Event.from_stream_data(stream_data)

    def test_from_stream_data_raises_on_missing_source(self):
        """from_stream_data should raise ValueError if source is missing"""
        stream_data = {
            b"id": b"test-123",
            b"type": b"k8s:issue_detected",
            b"timestamp": datetime.utcnow().isoformat().encode(),
            b"payload": b"{}",
        }

        with pytest.raises(ValueError, match="missing 'source'"):
            Event.from_stream_data(stream_data)
