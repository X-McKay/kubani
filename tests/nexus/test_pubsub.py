"""Tests for the Nexus Redis Pub/Sub module.

These tests run against a real Redis instance (Docker).
They validate publish/subscribe operations for agent responses
and system notifications.
"""

from __future__ import annotations

import asyncio
import json

import pytest
import pytest_asyncio

from kubani.nexus.pubsub import NexusPubSub


@pytest_asyncio.fixture
async def pubsub():
    """Create a NexusPubSub instance connected to the test Redis."""
    ps = NexusPubSub(redis_url="redis://localhost:6379")
    await ps.connect()
    yield ps
    await ps.close()


@pytest_asyncio.fixture
async def subscriber():
    """Create a second NexusPubSub instance for subscribing."""
    ps = NexusPubSub(redis_url="redis://localhost:6379")
    await ps.connect()
    yield ps
    await ps.close()


class TestPubSub:
    """Test Redis pub/sub operations."""

    @pytest.mark.asyncio
    async def test_publish_response(self, pubsub):
        """Test that publishing a response doesn't raise errors."""
        await pubsub.publish_response(
            "test-conv-1",
            {"text": "Hello from the agent", "conversation_id": "test-conv-1"},
        )

    @pytest.mark.asyncio
    async def test_publish_notification(self, pubsub):
        """Test that publishing a notification doesn't raise errors."""
        await pubsub.publish_notification(
            {"type": "skill_approved", "skill_name": "web/fetch-url"}
        )

    @pytest.mark.asyncio
    async def test_subscribe_receives_published_message(self, pubsub, subscriber):
        """Test that a subscriber receives a published message."""
        conversation_id = "test-conv-pubsub"
        received_messages = []

        async def collect_messages():
            async for msg in subscriber.subscribe_responses(conversation_id):
                received_messages.append(msg)
                break  # Only collect one message

        # Start subscriber in background
        sub_task = asyncio.create_task(collect_messages())

        # Give subscriber time to connect
        await asyncio.sleep(0.2)

        # Publish a message
        await pubsub.publish_response(
            conversation_id,
            {"text": "Test response", "conversation_id": conversation_id},
        )

        # Wait for subscriber to receive
        try:
            await asyncio.wait_for(sub_task, timeout=3.0)
        except asyncio.TimeoutError:
            sub_task.cancel()
            pytest.fail("Subscriber did not receive message within timeout")

        assert len(received_messages) == 1
        assert received_messages[0]["text"] == "Test response"

    @pytest.mark.asyncio
    async def test_subscribe_only_receives_own_channel(self, pubsub, subscriber):
        """Test that a subscriber only receives messages from its channel."""
        received_messages = []

        async def collect_messages():
            async for msg in subscriber.subscribe_responses("channel-A"):
                received_messages.append(msg)
                break

        sub_task = asyncio.create_task(collect_messages())
        await asyncio.sleep(0.2)

        # Publish to a different channel
        await pubsub.publish_response(
            "channel-B",
            {"text": "Wrong channel", "conversation_id": "channel-B"},
        )

        # Publish to the correct channel
        await pubsub.publish_response(
            "channel-A",
            {"text": "Right channel", "conversation_id": "channel-A"},
        )

        try:
            await asyncio.wait_for(sub_task, timeout=3.0)
        except asyncio.TimeoutError:
            sub_task.cancel()

        assert len(received_messages) == 1
        assert received_messages[0]["text"] == "Right channel"

    @pytest.mark.asyncio
    async def test_notification_subscribe(self, pubsub, subscriber):
        """Test subscribing to system notifications."""
        received = []

        async def collect():
            async for msg in subscriber.subscribe_notifications():
                received.append(msg)
                break

        sub_task = asyncio.create_task(collect())
        await asyncio.sleep(0.2)

        await pubsub.publish_notification(
            {"type": "test", "message": "Hello notifications"}
        )

        try:
            await asyncio.wait_for(sub_task, timeout=3.0)
        except asyncio.TimeoutError:
            sub_task.cancel()

        assert len(received) == 1
        assert received[0]["type"] == "test"
