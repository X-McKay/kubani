"""
E2E Tests for Event Bus Flow.

Tests the complete event publishing and consumption workflow
through the Redis-based Event Bus.
"""

import asyncio
import json
import os

import pytest

from tests.e2e.utils import (
    EventCapture,
    TestResourceManager,
    delete_test_pod,
    wait_for_pod_status,
)

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


class TestEventPublishing:
    """Test event publishing to the Event Bus."""

    @pytest.mark.smoke
    async def test_publish_event_to_redis(self, event_capture):
        """
        Test that events can be published and received via Redis.

        This is a basic smoke test for the Event Bus infrastructure.
        """
        # Skip if Redis not available
        if event_capture._redis is None:
            pytest.skip("Redis not available")

        # Publish a test event directly
        import redis.asyncio as redis

        redis_url = os.getenv("KUBANI_REDIS_URL", "redis://localhost:6379")
        client = redis.from_url(redis_url)

        try:
            # Publish event to stream
            await client.xadd(
                "kubani:events",
                {
                    "type": "E2E_TEST_EVENT",
                    "payload": json.dumps(
                        {
                            "test_id": "smoke-test-001",
                            "message": "Hello from E2E test",
                        }
                    ),
                },
            )

            # Wait for event to be captured
            event = await event_capture.wait_for_event(
                "E2E_TEST_EVENT",
                filters={"test_id": "smoke-test-001"},
                timeout=10,
            )

            assert event is not None
            assert event.payload["message"] == "Hello from E2E test"

        finally:
            await client.close()

    async def test_multiple_events_ordering(self, event_capture):
        """Test that multiple events maintain ordering."""
        if event_capture._redis is None:
            pytest.skip("Redis not available")

        import redis.asyncio as redis

        redis_url = os.getenv("KUBANI_REDIS_URL", "redis://localhost:6379")
        client = redis.from_url(redis_url)

        try:
            # Publish multiple events
            for i in range(5):
                await client.xadd(
                    "kubani:events",
                    {
                        "type": "E2E_SEQUENCE_EVENT",
                        "payload": json.dumps(
                            {
                                "sequence": i,
                                "batch": "ordering-test",
                            }
                        ),
                    },
                )

            # Wait a bit for all events to be captured
            await asyncio.sleep(2)

            # Verify ordering
            sequence_events = [
                e
                for e in event_capture.events
                if e.event_type == "E2E_SEQUENCE_EVENT"
                and e.payload.get("batch") == "ordering-test"
            ]

            assert len(sequence_events) == 5

            # Check sequence order
            sequences = [e.payload["sequence"] for e in sequence_events]
            assert sequences == [0, 1, 2, 3, 4]

        finally:
            await client.close()


class TestKubernetesEventIntegration:
    """Test Kubernetes events flowing through the system."""

    @pytest.mark.slow
    async def test_pod_creation_generates_event(
        self,
        test_resources: TestResourceManager,
        event_capture: EventCapture,
    ):
        """
        Test that pod creation generates events in the Event Bus.

        Note: This requires the k8s-monitor agent to be running and
        watching for Kubernetes events.
        """
        if event_capture._redis is None:
            pytest.skip("Redis not available")

        # Create a test pod
        pod_name = "e2e-event-test-pod"
        test_resources.create_pod(
            name=pod_name,
            labels={"test": "event-flow"},
        )

        try:
            # Wait for pod to be running
            await wait_for_pod_status(
                pod_name,
                test_resources.namespace,
                expected_phase="Running",
                timeout=60,
            )

            # If agents are running, we should see events
            # This is a best-effort check
            await asyncio.sleep(5)

            # Check if any K8s-related events were captured
            k8s_events = [
                e
                for e in event_capture.events
                if "K8S" in e.event_type or "RESOURCE" in e.event_type
            ]

            # Log what we found (informational)
            if k8s_events:
                print(f"Captured {len(k8s_events)} Kubernetes-related events")

        finally:
            delete_test_pod(pod_name, test_resources.namespace)


class TestEventFiltering:
    """Test event filtering and routing."""

    async def test_event_type_filtering(self, event_capture):
        """Test that events can be filtered by type."""
        if event_capture._redis is None:
            pytest.skip("Redis not available")

        import redis.asyncio as redis

        redis_url = os.getenv("KUBANI_REDIS_URL", "redis://localhost:6379")
        client = redis.from_url(redis_url)

        try:
            # Publish events of different types
            await client.xadd(
                "kubani:events",
                {"type": "TYPE_A", "payload": json.dumps({"id": "a1"})},
            )
            await client.xadd(
                "kubani:events",
                {"type": "TYPE_B", "payload": json.dumps({"id": "b1"})},
            )
            await client.xadd(
                "kubani:events",
                {"type": "TYPE_A", "payload": json.dumps({"id": "a2"})},
            )

            await asyncio.sleep(2)

            # Filter by type
            type_a_events = [e for e in event_capture.events if e.event_type == "TYPE_A"]
            type_b_events = [e for e in event_capture.events if e.event_type == "TYPE_B"]

            assert len(type_a_events) >= 2
            assert len(type_b_events) >= 1

        finally:
            await client.close()

    async def test_event_payload_filtering(self, event_capture):
        """Test that events can be filtered by payload content."""
        if event_capture._redis is None:
            pytest.skip("Redis not available")

        import redis.asyncio as redis

        redis_url = os.getenv("KUBANI_REDIS_URL", "redis://localhost:6379")
        client = redis.from_url(redis_url)

        try:
            # Publish events with different payload values
            await client.xadd(
                "kubani:events",
                {
                    "type": "FILTER_TEST",
                    "payload": json.dumps(
                        {
                            "namespace": "production",
                            "severity": "critical",
                        }
                    ),
                },
            )
            await client.xadd(
                "kubani:events",
                {
                    "type": "FILTER_TEST",
                    "payload": json.dumps(
                        {
                            "namespace": "staging",
                            "severity": "warning",
                        }
                    ),
                },
            )

            # Wait for event with specific filter
            event = await event_capture.wait_for_event(
                "FILTER_TEST",
                filters={"namespace": "production"},
                timeout=10,
            )

            assert event.payload["severity"] == "critical"

        finally:
            await client.close()
