"""Tests for Kubernetes watch stream functionality."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from k8s_monitor.federated.sentinel import (
    K8sEvent,
    SentinelAgent,
    WatchMode,
)
from k8s_monitor.watch import (
    K8sWatchStream,
    WatchEvent,
    create_reason_filter,
    default_event_filter,
)


class TestWatchEvent:
    """Tests for WatchEvent dataclass."""

    def test_watch_event_creation(self):
        """Test creating a WatchEvent."""
        k8s_event = {
            "type": "Warning",
            "reason": "CrashLoopBackOff",
            "message": "Back-off restarting failed container",
            "involvedObject": {
                "kind": "Pod",
                "name": "test-pod",
                "namespace": "default",
            },
        }

        event = WatchEvent(
            event_type="MODIFIED",
            k8s_event=k8s_event,
            timestamp=datetime.now(UTC),
        )

        assert event.event_type == "MODIFIED"
        assert event.k8s_event["reason"] == "CrashLoopBackOff"


class TestEventFilters:
    """Tests for event filter functions."""

    def test_default_filter_passes_warning(self):
        """Test that default filter passes Warning events."""
        event = WatchEvent(
            event_type="ADDED",
            k8s_event={"type": "Warning", "reason": "Test"},
            timestamp=datetime.now(UTC),
        )
        assert default_event_filter(event) is True

    def test_default_filter_passes_error(self):
        """Test that default filter passes Error events."""
        event = WatchEvent(
            event_type="ADDED",
            k8s_event={"type": "Error", "reason": "Test"},
            timestamp=datetime.now(UTC),
        )
        assert default_event_filter(event) is True

    def test_default_filter_rejects_normal(self):
        """Test that default filter rejects Normal events."""
        event = WatchEvent(
            event_type="ADDED",
            k8s_event={"type": "Normal", "reason": "Scheduled"},
            timestamp=datetime.now(UTC),
        )
        assert default_event_filter(event) is False

    def test_reason_filter(self):
        """Test creating a reason-based filter."""
        reasons = {"CrashLoopBackOff", "OOMKilled"}
        filter_func = create_reason_filter(reasons)

        # Should pass matching reasons
        crash_event = WatchEvent(
            event_type="ADDED",
            k8s_event={"reason": "CrashLoopBackOff"},
            timestamp=datetime.now(UTC),
        )
        assert filter_func(crash_event) is True

        oom_event = WatchEvent(
            event_type="ADDED",
            k8s_event={"reason": "OOMKilled"},
            timestamp=datetime.now(UTC),
        )
        assert filter_func(oom_event) is True

        # Should reject non-matching reasons
        other_event = WatchEvent(
            event_type="ADDED",
            k8s_event={"reason": "Scheduled"},
            timestamp=datetime.now(UTC),
        )
        assert filter_func(other_event) is False


class TestK8sWatchStream:
    """Tests for K8sWatchStream class."""

    def test_init_defaults(self):
        """Test default initialization."""
        stream = K8sWatchStream()

        assert stream.initial_backoff == 1.0
        assert stream.max_backoff == 60.0
        assert stream.backoff_multiplier == 2.0
        assert stream._running is False

    def test_init_custom_values(self):
        """Test custom initialization."""
        stream = K8sWatchStream(
            initial_backoff=2.0,
            max_backoff=120.0,
            backoff_multiplier=3.0,
        )

        assert stream.initial_backoff == 2.0
        assert stream.max_backoff == 120.0
        assert stream.backoff_multiplier == 3.0

    def test_stop(self):
        """Test stopping the watch stream."""
        stream = K8sWatchStream()
        stream._running = True
        stream._watch = MagicMock()

        stream.stop()

        assert stream._running is False
        stream._watch.stop.assert_called_once()


class TestSentinelAgentWatchMode:
    """Tests for SentinelAgent watch mode support."""

    def test_init_default_watch_mode(self):
        """Test default watch mode is AUTO."""
        sentinel = SentinelAgent()
        assert sentinel.watch_mode == WatchMode.AUTO

    def test_init_explicit_watch_mode(self):
        """Test explicit watch mode setting."""
        sentinel = SentinelAgent(watch_mode=WatchMode.WATCH)
        assert sentinel.watch_mode == WatchMode.WATCH

        sentinel = SentinelAgent(watch_mode=WatchMode.POLL)
        assert sentinel.watch_mode == WatchMode.POLL

    def test_stop_with_watch_stream(self):
        """Test stopping sentinel with active watch stream."""
        sentinel = SentinelAgent()
        sentinel._running = True
        sentinel._watch_stream = MagicMock()

        sentinel.stop()

        assert sentinel._running is False
        sentinel._watch_stream.stop.assert_called_once()


class TestK8sEventParsing:
    """Tests for K8sEvent parsing from watch data."""

    def test_from_mcp_event_basic(self):
        """Test parsing a basic MCP event."""
        event_data = {
            "type": "Warning",
            "reason": "CrashLoopBackOff",
            "message": "Back-off restarting failed container",
            "involvedObject": {
                "kind": "Pod",
                "name": "test-pod",
                "namespace": "default",
            },
            "count": 5,
        }

        event = K8sEvent.from_mcp_event(event_data)

        assert event.type == "Warning"
        assert event.reason == "CrashLoopBackOff"
        assert event.message == "Back-off restarting failed container"
        assert event.namespace == "default"
        assert event.name == "test-pod"
        assert event.kind == "Pod"
        assert event.count == 5

    def test_from_mcp_event_missing_fields(self):
        """Test parsing event with missing optional fields."""
        event_data = {
            "type": "Normal",
            "reason": "Scheduled",
            "involvedObject": {},
        }

        event = K8sEvent.from_mcp_event(event_data)

        assert event.type == "Normal"
        assert event.reason == "Scheduled"
        assert event.message == ""
        assert event.namespace == "default"
        assert event.name == "unknown"
        assert event.kind == "Unknown"
        assert event.count == 1


class TestSentinelEventProcessing:
    """Tests for SentinelAgent event processing."""

    @pytest.fixture
    def sentinel_with_mocks(self):
        """Create a sentinel with mocked dependencies."""
        skill_library = AsyncMock()
        skill_library.search.return_value = []

        event_bus = AsyncMock()

        sentinel = SentinelAgent(
            skill_library=skill_library,
            event_bus=event_bus,
            watch_mode=WatchMode.POLL,
        )
        return sentinel

    @pytest.mark.asyncio
    async def test_process_watch_event_filters_normal(self, sentinel_with_mocks):
        """Test that Normal events are filtered out."""
        sentinel = sentinel_with_mocks

        watch_event = WatchEvent(
            event_type="ADDED",
            k8s_event={
                "type": "Normal",
                "reason": "Scheduled",
                "message": "Successfully assigned pod",
                "involvedObject": {
                    "kind": "Pod",
                    "name": "test-pod",
                    "namespace": "default",
                },
            },
            timestamp=datetime.now(UTC),
        )

        await sentinel._process_watch_event(watch_event)

        # Event bus should not have been called for Normal events
        sentinel._event_bus.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_watch_event_deduplication(self, sentinel_with_mocks):
        """Test that duplicate events are filtered out."""
        sentinel = sentinel_with_mocks

        watch_event = WatchEvent(
            event_type="MODIFIED",
            k8s_event={
                "type": "Warning",
                "reason": "CrashLoopBackOff",
                "message": "Back-off restarting failed container",
                "involvedObject": {
                    "kind": "Pod",
                    "name": "test-pod",
                    "namespace": "default",
                },
                "count": 1,
            },
            timestamp=datetime.now(UTC),
        )

        # Process the same event twice
        await sentinel._process_watch_event(watch_event)
        await sentinel._process_watch_event(watch_event)

        # Should only classify once (deduplication)
        assert sentinel._skill_library.search.call_count == 1


class TestWatchModeEnum:
    """Tests for WatchMode enum."""

    def test_watch_mode_values(self):
        """Test WatchMode enum values."""
        assert WatchMode.WATCH.value == "watch"
        assert WatchMode.POLL.value == "poll"
        assert WatchMode.AUTO.value == "auto"

    def test_watch_mode_is_string_enum(self):
        """Test WatchMode can be used as string."""
        assert str(WatchMode.WATCH) == "WatchMode.WATCH"
        assert WatchMode.WATCH == "watch"
