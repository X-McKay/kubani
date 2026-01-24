"""
Tests for RedisEventBus using fakeredis.
"""

import asyncio

import pytest

from framework.events.types import EventType


class TestEventBusPublish:
    """Test event publishing functionality"""

    @pytest.mark.asyncio
    async def test_publish_generates_unique_event_ids(self, fake_redis_event_bus):
        """Each published event should get a unique ID"""
        event_id_1 = await fake_redis_event_bus.publish(
            EventType.K8S_ISSUE_DETECTED, {"pod": "test-1"}, source="test-agent"
        )

        event_id_2 = await fake_redis_event_bus.publish(
            EventType.K8S_ISSUE_DETECTED, {"pod": "test-2"}, source="test-agent"
        )

        assert event_id_1 != event_id_2
        assert len(event_id_1) > 0
        assert len(event_id_2) > 0

    @pytest.mark.asyncio
    async def test_publish_adds_event_to_stream(self, fake_redis_event_bus):
        """Published events should be retrievable from the stream"""
        event_id = await fake_redis_event_bus.publish(
            EventType.K8S_ISSUE_DETECTED,
            {"pod": "test-pod", "namespace": "default"},
            source="test-agent",
        )

        # Get recent events
        recent = await fake_redis_event_bus.get_recent(count=10)

        # Should find our event
        event_ids = [e.id for e in recent]
        assert event_id in event_ids


class TestEventBusSubscribe:
    """Test event subscription functionality"""

    @pytest.mark.asyncio
    async def test_subscribe_filters_by_event_type(self, fake_redis_event_bus):
        """subscribe should only yield events of specified type"""
        # Subscribe to only K8S_ISSUE_DETECTED first
        received_types = []
        subscription = fake_redis_event_bus.subscribe(EventType.K8S_ISSUE_DETECTED)

        async def publish_events():
            """Publish events after subscription starts"""
            await asyncio.sleep(0.1)  # Let subscription start
            await fake_redis_event_bus.publish(
                EventType.K8S_ISSUE_DETECTED, {"pod": "test-1"}, source="test"
            )
            await fake_redis_event_bus.publish(
                EventType.K8S_REMEDIATION_STARTED, {"pod": "test-2"}, source="test"
            )
            await fake_redis_event_bus.publish(
                EventType.K8S_ISSUE_DETECTED, {"pod": "test-3"}, source="test"
            )

        # Start publishing in background
        publish_task = asyncio.create_task(publish_events())

        # Read a few events (with timeout)
        try:
            async with asyncio.timeout(2.0):
                async for event in subscription:
                    received_types.append(event.type)
                    if len(received_types) >= 2:
                        break
        except TimeoutError:
            pass
        finally:
            await publish_task

        # Should only receive K8S_ISSUE_DETECTED events
        assert len(received_types) > 0
        assert all(t == EventType.K8S_ISSUE_DETECTED for t in received_types)

    @pytest.mark.asyncio
    async def test_subscribe_receives_all_types_when_none_specified(self, fake_redis_event_bus):
        """subscribe with no filter should receive all event types"""
        # Subscribe to all types first
        received_types = []
        subscription = fake_redis_event_bus.subscribe()  # No filter

        async def publish_events():
            """Publish events after subscription starts"""
            await asyncio.sleep(0.1)  # Let subscription start
            await fake_redis_event_bus.publish(
                EventType.K8S_ISSUE_DETECTED, {"pod": "test-1"}, source="test"
            )
            await fake_redis_event_bus.publish(
                EventType.K8S_REMEDIATION_STARTED, {"pod": "test-2"}, source="test"
            )

        # Start publishing in background
        publish_task = asyncio.create_task(publish_events())

        try:
            async with asyncio.timeout(2.0):
                async for event in subscription:
                    received_types.append(event.type)
                    if len(received_types) >= 2:
                        break
        except TimeoutError:
            pass
        finally:
            await publish_task

        # Should receive multiple event types
        unique_types = set(received_types)
        assert len(unique_types) > 1


class TestEventBusGetRecent:
    """Test retrieving recent events"""

    @pytest.mark.asyncio
    async def test_get_recent_returns_events(self, fake_redis_event_bus):
        """get_recent should return published events"""
        # Publish some events
        await fake_redis_event_bus.publish(
            EventType.K8S_ISSUE_DETECTED, {"pod": "test-1"}, source="test"
        )
        await fake_redis_event_bus.publish(
            EventType.K8S_ISSUE_DETECTED, {"pod": "test-2"}, source="test"
        )

        # Get recent events
        recent = await fake_redis_event_bus.get_recent(count=10)

        assert len(recent) >= 2
        assert all(e.type == EventType.K8S_ISSUE_DETECTED for e in recent)

    @pytest.mark.asyncio
    async def test_get_recent_filters_by_event_type(self, fake_redis_event_bus):
        """get_recent should filter by event type"""
        # Publish different types
        await fake_redis_event_bus.publish(
            EventType.K8S_ISSUE_DETECTED, {"pod": "test-1"}, source="test"
        )
        await fake_redis_event_bus.publish(
            EventType.K8S_REMEDIATION_STARTED, {"pod": "test-2"}, source="test"
        )

        # Get only K8S_ISSUE_DETECTED
        recent = await fake_redis_event_bus.get_recent(
            event_type=EventType.K8S_ISSUE_DETECTED, count=10
        )

        assert all(e.type == EventType.K8S_ISSUE_DETECTED for e in recent)

    @pytest.mark.asyncio
    async def test_get_recent_limits_results(self, fake_redis_event_bus):
        """get_recent should respect count limit"""
        # Publish many events
        for i in range(10):
            await fake_redis_event_bus.publish(
                EventType.K8S_ISSUE_DETECTED, {"pod": f"test-{i}"}, source="test"
            )

        # Get only 3
        recent = await fake_redis_event_bus.get_recent(count=3)

        assert len(recent) <= 3
