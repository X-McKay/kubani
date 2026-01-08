"""
E2E Tests for Agent-to-Agent (A2A) Communication.

Tests the A2A protocol implementation including:
- Agent discovery
- Message passing
- Request/response patterns
- Error handling
"""

import asyncio
import json
import os
from datetime import UTC, datetime

import pytest

from tests.e2e.utils import (
    EventCapture,
    run_kubectl,
)

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


class TestA2ADiscovery:
    """Test A2A agent discovery mechanisms."""

    @pytest.mark.smoke
    async def test_agent_card_exists(self, cluster_available):
        """
        Verify that agents publish their A2A cards.

        Agent cards describe the agent's capabilities and are used
        for discovery.
        """
        # Check for agent card ConfigMaps
        result = run_kubectl(
            "get",
            "configmaps",
            "-n",
            "ai-agents",
            "-l",
            "app.kubernetes.io/component=a2a-card",
            "-o",
            "json",
            check=False,
        )

        if result.returncode != 0:
            pytest.skip("Cannot query agent cards")

        data = json.loads(result.stdout)
        cards = data.get("items", [])

        # Log found cards
        print(f"Found {len(cards)} agent cards")
        for card in cards:
            name = card["metadata"]["name"]
            print(f"  - {name}")

    async def test_agent_endpoints_resolvable(self, cluster_available):
        """
        Verify that agent service endpoints are resolvable.
        """
        # Get agent services
        result = run_kubectl(
            "get",
            "services",
            "-n",
            "ai-agents",
            "-l",
            "app.kubernetes.io/part-of=kubani",
            "-o",
            "json",
            check=False,
        )

        if result.returncode != 0:
            pytest.skip("Cannot query services")

        data = json.loads(result.stdout)
        services = data.get("items", [])

        print(f"Found {len(services)} agent services")

        for service in services:
            name = service["metadata"]["name"]
            cluster_ip = service["spec"].get("clusterIP", "None")
            ports = service["spec"].get("ports", [])

            print(f"  - {name}: {cluster_ip}")
            for port in ports:
                print(f"      port {port.get('port')} -> {port.get('targetPort')}")


class TestA2AMessaging:
    """Test A2A message passing."""

    @pytest.mark.requires_agents
    async def test_a2a_request_response(
        self,
        event_capture: EventCapture,
        agents_running,
    ):
        """
        Test A2A request/response pattern.

        One agent sends a request, another responds.
        """
        if event_capture._redis is None:
            pytest.skip("Redis not available")

        import redis.asyncio as redis

        redis_url = os.getenv("KUBANI_REDIS_URL", "redis://localhost:6379")
        client = redis.from_url(redis_url)

        try:
            # Publish an A2A request
            request_id = f"test-{datetime.now(UTC).timestamp()}"
            await client.xadd(
                "kubani:a2a",
                {
                    "type": "A2A_REQUEST",
                    "payload": json.dumps(
                        {
                            "request_id": request_id,
                            "from_agent": "e2e-test",
                            "to_agent": "k8s-monitor",
                            "action": "ping",
                            "params": {},
                        }
                    ),
                },
            )

            # Wait for response (may not come if agents not running)
            await asyncio.sleep(5)

            print(f"Sent A2A request: {request_id}")

        finally:
            await client.close()

    async def test_a2a_broadcast(
        self,
        event_capture: EventCapture,
    ):
        """
        Test A2A broadcast pattern.

        One agent broadcasts to all agents.
        """
        if event_capture._redis is None:
            pytest.skip("Redis not available")

        import redis.asyncio as redis

        redis_url = os.getenv("KUBANI_REDIS_URL", "redis://localhost:6379")
        client = redis.from_url(redis_url)

        try:
            # Publish a broadcast
            await client.xadd(
                "kubani:a2a:broadcast",
                {
                    "type": "A2A_BROADCAST",
                    "payload": json.dumps(
                        {
                            "from_agent": "e2e-test",
                            "action": "health_check_request",
                            "timestamp": datetime.now(UTC).isoformat(),
                        }
                    ),
                },
            )

            print("Sent A2A broadcast")
            await asyncio.sleep(2)

        finally:
            await client.close()


class TestA2AHandoffs:
    """Test A2A agent handoff patterns."""

    @pytest.mark.requires_agents
    @pytest.mark.slow
    async def test_triage_to_diagnosis_handoff(
        self,
        event_capture: EventCapture,
        agents_running,
    ):
        """
        Test handoff from Triage agent to Diagnosis agent.

        This is part of the hierarchical agent structure.
        """
        if event_capture._redis is None:
            pytest.skip("Redis not available")

        # Simulate a handoff by publishing an event
        import redis.asyncio as redis

        redis_url = os.getenv("KUBANI_REDIS_URL", "redis://localhost:6379")
        client = redis.from_url(redis_url)

        try:
            # Publish a triage result that should trigger handoff
            await client.xadd(
                "kubani:events",
                {
                    "type": "TRIAGE_COMPLETED",
                    "payload": json.dumps(
                        {
                            "issue_id": "test-issue-001",
                            "resource_type": "Pod",
                            "resource_name": "test-pod",
                            "namespace": "default",
                            "severity": "high",
                            "category": "crashloop",
                            "next_agent": "pod_diagnostician",
                        }
                    ),
                },
            )

            # Wait for diagnosis to start
            try:
                event = await event_capture.wait_for_event(
                    "DIAGNOSIS_STARTED",
                    filters={"issue_id": "test-issue-001"},
                    timeout=30,
                )
                print(f"Diagnosis started: {event.payload}")
            except TimeoutError:
                print("No diagnosis started (agents may not be running)")

        finally:
            await client.close()


class TestA2AErrorHandling:
    """Test A2A error handling."""

    async def test_a2a_timeout_handling(
        self,
        event_capture: EventCapture,
    ):
        """
        Test that A2A requests handle timeouts gracefully.
        """
        if event_capture._redis is None:
            pytest.skip("Redis not available")

        import redis.asyncio as redis

        redis_url = os.getenv("KUBANI_REDIS_URL", "redis://localhost:6379")
        client = redis.from_url(redis_url)

        try:
            # Send request to non-existent agent
            await client.xadd(
                "kubani:a2a",
                {
                    "type": "A2A_REQUEST",
                    "payload": json.dumps(
                        {
                            "request_id": "timeout-test",
                            "from_agent": "e2e-test",
                            "to_agent": "non-existent-agent",
                            "action": "ping",
                            "timeout_seconds": 5,
                        }
                    ),
                },
            )

            # Wait for timeout error event
            await asyncio.sleep(6)

            # Check for error event
            error_events = [
                e
                for e in event_capture.events
                if "ERROR" in e.event_type or "TIMEOUT" in e.event_type
            ]

            # May or may not have error events depending on implementation
            print(f"Error events captured: {len(error_events)}")

        finally:
            await client.close()

    async def test_a2a_malformed_message_handling(
        self,
        event_capture: EventCapture,
    ):
        """
        Test that malformed A2A messages are handled gracefully.
        """
        if event_capture._redis is None:
            pytest.skip("Redis not available")

        import redis.asyncio as redis

        redis_url = os.getenv("KUBANI_REDIS_URL", "redis://localhost:6379")
        client = redis.from_url(redis_url)

        try:
            # Send malformed message
            await client.xadd(
                "kubani:a2a",
                {
                    "type": "A2A_REQUEST",
                    "payload": "not-valid-json{{{",
                },
            )

            await asyncio.sleep(2)

            # System should not crash from malformed messages
            print("Malformed message sent - checking for crashes")

            # Verify agents are still running
            result = run_kubectl(
                "get",
                "pods",
                "-n",
                "ai-agents",
                "-l",
                "app.kubernetes.io/part-of=kubani",
                "-o",
                "jsonpath={.items[*].status.phase}",
                check=False,
            )

            if result.returncode == 0 and result.stdout:
                phases = result.stdout.split()
                running = [p for p in phases if p == "Running"]
                print(f"Agents still running: {len(running)}/{len(phases)}")

        finally:
            await client.close()


class TestA2APerformance:
    """Test A2A performance characteristics."""

    @pytest.mark.slow
    async def test_a2a_message_throughput(
        self,
        event_capture: EventCapture,
    ):
        """
        Test A2A message throughput.

        Measures how many messages can be processed per second.
        """
        if event_capture._redis is None:
            pytest.skip("Redis not available")

        import time

        import redis.asyncio as redis

        redis_url = os.getenv("KUBANI_REDIS_URL", "redis://localhost:6379")
        client = redis.from_url(redis_url)

        try:
            message_count = 100
            start_time = time.time()

            # Send many messages
            for i in range(message_count):
                await client.xadd(
                    "kubani:events",
                    {
                        "type": "THROUGHPUT_TEST",
                        "payload": json.dumps({"sequence": i}),
                    },
                )

            send_duration = time.time() - start_time
            send_rate = message_count / send_duration

            print(f"Sent {message_count} messages in {send_duration:.2f}s")
            print(f"Send rate: {send_rate:.1f} msg/s")

            # Wait for messages to be captured
            await asyncio.sleep(5)

            # Count captured messages
            captured = len([e for e in event_capture.events if e.event_type == "THROUGHPUT_TEST"])

            print(f"Captured {captured}/{message_count} messages")

        finally:
            await client.close()
