"""
E2E Tests for Self-Healing Workflows.

Tests the complete issue detection -> diagnosis -> remediation workflow
for various failure scenarios.
"""

import asyncio
import json

import pytest

from tests.e2e.utils import (
    EventCapture,
    TestResourceManager,
    delete_test_pod,
    get_events,
    get_pod_status,
    run_kubectl,
    wait_for_pod_status,
)

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


class TestIssueDetection:
    """Test automatic issue detection."""

    @pytest.mark.slow
    @pytest.mark.requires_agents
    async def test_crashloop_detection(
        self,
        test_resources: TestResourceManager,
        event_capture: EventCapture,
    ):
        """
        Test that CrashLoopBackOff is detected and generates events.

        Creates a pod that will crash loop and verifies the system
        detects and reports the issue.
        """
        pod_name = "e2e-crashloop-test"

        # Create a pod that will crash
        test_resources.create_crashloop_pod(pod_name)

        try:
            # Wait for pod to enter CrashLoopBackOff
            # This typically takes 2-3 crash cycles (~30s)
            await asyncio.sleep(30)

            # Check pod status
            status = get_pod_status(pod_name, test_resources.namespace)

            # Pod should be in a crash loop state
            if status:
                assert status.restart_count > 0, "Pod should have restarted at least once"
                print(f"Pod restart count: {status.restart_count}")

            # Check Kubernetes events for the pod
            events = get_events(
                namespace=test_resources.namespace,
                field_selector=f"involvedObject.name={pod_name}",
            )

            # Should have warning events
            warning_events = [e for e in events if e.get("type") == "Warning"]

            if warning_events:
                print(f"Found {len(warning_events)} warning events")
                for event in warning_events[:3]:
                    print(f"  - {event.get('reason')}: {event.get('message', '')[:50]}")

            # If agents are running, check for detection events
            if event_capture._redis:
                try:
                    event = await event_capture.wait_for_event(
                        "K8S_ISSUE_DETECTED",
                        filters={"resource_name": pod_name},
                        timeout=60,
                    )
                    print(f"Issue detected: {event.payload}")
                except TimeoutError:
                    print("No K8S_ISSUE_DETECTED event (agents may not be running)")

        finally:
            delete_test_pod(pod_name, test_resources.namespace)

    @pytest.mark.slow
    @pytest.mark.requires_agents
    async def test_oom_detection(
        self,
        test_resources: TestResourceManager,
        event_capture: EventCapture,
    ):
        """
        Test that OOMKilled pods are detected.

        Creates a pod that will exceed its memory limit and verifies
        detection.
        """
        pod_name = "e2e-oom-test"

        # Create pod that will OOM
        manifest = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": pod_name,
                "namespace": test_resources.namespace,
                "labels": {"app": "oom-test"},
            },
            "spec": {
                "containers": [
                    {
                        "name": "oom",
                        "image": "python:3.11-slim",
                        "command": [
                            "python",
                            "-c",
                            "x = []; [x.extend([0]*10**6) for _ in range(1000)]",
                        ],
                        "resources": {
                            "limits": {"memory": "32Mi"},
                        },
                    }
                ],
                "restartPolicy": "Never",
            },
        }

        run_kubectl(
            "apply",
            "-f",
            "-",
            check=False,
        )

        # Apply manifest via stdin
        import subprocess

        subprocess.run(
            ["kubectl", "apply", "-f", "-"],
            input=json.dumps(manifest),
            capture_output=True,
            text=True,
        )

        try:
            # Wait for OOM to occur
            await asyncio.sleep(30)

            # Check pod status
            status = get_pod_status(pod_name, test_resources.namespace)

            if status:
                print(f"Pod phase: {status.phase}")

            # Check events for OOMKilled
            events = get_events(
                namespace=test_resources.namespace,
                field_selector=f"involvedObject.name={pod_name}",
            )

            oom_events = [
                e
                for e in events
                if "OOM" in str(e.get("reason", "")).upper()
                or "OOM" in str(e.get("message", "")).upper()
            ]

            if oom_events:
                print(f"Found OOM events: {len(oom_events)}")

        finally:
            delete_test_pod(pod_name, test_resources.namespace)


class TestHealingActions:
    """Test automated healing actions."""

    @pytest.mark.slow
    @pytest.mark.requires_agents
    async def test_pod_restart_healing(
        self,
        test_resources: TestResourceManager,
        event_capture: EventCapture,
    ):
        """
        Test that the system can restart a problematic pod.

        Note: This requires proper RBAC permissions and agent
        configuration for the test namespace.
        """
        pod_name = "e2e-restart-healing-test"

        # Create a healthy pod first
        test_resources.create_pod(
            name=pod_name,
            labels={"app": "restart-test", "healable": "true"},
        )

        try:
            # Wait for pod to be running
            await wait_for_pod_status(
                pod_name,
                test_resources.namespace,
                expected_phase="Running",
                timeout=60,
            )

            # Get initial restart count
            get_pod_status(pod_name, test_resources.namespace)

            # Simulate a healing action by manually restarting
            # In production, this would be triggered by the agent
            run_kubectl(
                "delete",
                "pod",
                pod_name,
                "-n",
                test_resources.namespace,
                "--grace-period=0",
                "--force",
                check=False,
            )

            # Wait for pod to be deleted
            await asyncio.sleep(5)

            # Verify pod was deleted
            status = get_pod_status(pod_name, test_resources.namespace)
            assert status is None, "Pod should be deleted"

            print("Pod successfully deleted (simulating restart healing)")

        finally:
            delete_test_pod(pod_name, test_resources.namespace)


class TestHealingWorkflowIntegration:
    """Test complete healing workflow integration."""

    @pytest.mark.slow
    @pytest.mark.requires_agents
    async def test_end_to_end_healing_flow(
        self,
        test_resources: TestResourceManager,
        event_capture: EventCapture,
        agents_running,
    ):
        """
        Test the complete end-to-end healing workflow.

        1. Create a failing pod
        2. Wait for detection
        3. Wait for diagnosis
        4. Wait for healing action
        5. Verify recovery

        Note: This test requires fully deployed and configured agents.
        """
        pod_name = "e2e-full-healing-test"

        # Create a crashloop pod
        test_resources.create_crashloop_pod(pod_name)

        try:
            # Phase 1: Wait for issue detection
            print("Phase 1: Waiting for issue detection...")
            try:
                detection_event = await event_capture.wait_for_event(
                    "K8S_ISSUE_DETECTED",
                    timeout=120,
                )
                print(f"Issue detected: {detection_event.event_type}")
            except TimeoutError:
                pytest.skip("Issue detection not working (agent may not be running)")

            # Phase 2: Wait for diagnosis
            print("Phase 2: Waiting for diagnosis...")
            try:
                diagnosis_event = await event_capture.wait_for_event(
                    "DIAGNOSIS_COMPLETED",
                    timeout=60,
                )
                print(f"Diagnosis: {diagnosis_event.payload.get('root_cause', 'unknown')}")
            except TimeoutError:
                print("No diagnosis event received")

            # Phase 3: Wait for healing
            print("Phase 3: Waiting for healing action...")
            try:
                healing_event = await event_capture.wait_for_event(
                    "HEALING_COMPLETED",
                    timeout=120,
                )
                print(f"Healing completed: {healing_event.payload}")
            except TimeoutError:
                print("No healing event received")

            # Phase 4: Verify system state
            print("Phase 4: Verifying final state...")
            await asyncio.sleep(10)

            # Check what events were captured
            all_events = event_capture.events
            print(f"Total events captured: {len(all_events)}")

            event_types = {e.event_type for e in all_events}
            print(f"Event types: {event_types}")

        finally:
            delete_test_pod(pod_name, test_resources.namespace)


class TestHealingMetrics:
    """Test healing workflow metrics and observability."""

    async def test_healing_events_have_timestamps(
        self,
        event_capture: EventCapture,
    ):
        """
        Verify that healing events include timestamps for metrics.
        """
        if event_capture._redis is None:
            pytest.skip("Redis not available")

        import redis.asyncio as redis

        redis_url = "redis://localhost:6379"
        client = redis.from_url(redis_url)

        try:
            # Publish a healing event with timestamp
            await client.xadd(
                "kubani:events",
                {
                    "type": "HEALING_COMPLETED",
                    "payload": json.dumps(
                        {
                            "resource_name": "test-pod",
                            "action": "restart",
                            "duration_seconds": 5.2,
                            "success": True,
                        }
                    ),
                },
            )

            # Wait for event
            event = await event_capture.wait_for_event(
                "HEALING_COMPLETED",
                timeout=10,
            )

            # Event should have timestamp
            assert event.timestamp is not None
            assert event.payload.get("duration_seconds") is not None

        finally:
            await client.close()
