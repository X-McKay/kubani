"""
E2E Test Utilities for Kubani.

Provides helper functions for:
- Capturing events from the Event Bus
- Waiting for specific events or conditions
- Managing test resources
- Interacting with the Kubernetes cluster
"""

import asyncio
import contextlib
import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


# --- Event Capture ---


@dataclass
class CapturedEvent:
    """An event captured from the Event Bus."""

    event_type: str
    payload: dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    stream_id: str | None = None

    def matches(self, filters: dict[str, Any] | None = None) -> bool:
        """Check if this event matches the given filters."""
        if filters is None:
            return True

        for key, expected in filters.items():
            actual = self.payload.get(key)
            if actual != expected:
                return False
        return True


class EventCapture:
    """
    Capture events from the Redis Event Bus for testing.

    Usage:
        async with EventCapture(redis_url) as capture:
            # Trigger some action
            await trigger_action()

            # Wait for event
            event = await capture.wait_for_event(
                event_type="HEALING_STARTED",
                filters={"resource_name": "test-pod"},
                timeout=30
            )
    """

    def __init__(self, redis_url: str | None = None):
        self.redis_url = redis_url or os.getenv("KUBANI_REDIS_URL", "redis://localhost:6379")
        self._redis = None
        self._captured: list[CapturedEvent] = []
        self._consumer_task: asyncio.Task | None = None
        self._running = False

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()

    async def start(self):
        """Start capturing events."""
        try:
            import redis.asyncio as redis
        except ImportError:
            logger.warning("redis package not installed, event capture disabled")
            return

        self._redis = redis.from_url(self.redis_url)
        self._running = True
        self._consumer_task = asyncio.create_task(self._consume_events())
        logger.info(f"Started event capture from {self.redis_url}")

    async def stop(self):
        """Stop capturing events."""
        self._running = False
        if self._consumer_task:
            self._consumer_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._consumer_task
        if self._redis:
            await self._redis.close()

    async def _consume_events(self):
        """Background task to consume events from Redis stream."""
        stream_name = os.getenv("KUBANI_EVENT_STREAM", "kubani:events")
        last_id = "$"  # Start from new messages

        while self._running:
            try:
                # Read from stream with blocking
                messages = await self._redis.xread(
                    {stream_name: last_id},
                    block=1000,  # 1 second timeout
                    count=10,
                )

                if messages:
                    for _stream, entries in messages:
                        for entry_id, data in entries:
                            last_id = entry_id

                            # Parse event
                            event_type = data.get(b"type", b"").decode()
                            payload_str = data.get(b"payload", b"{}").decode()

                            try:
                                payload = json.loads(payload_str)
                            except json.JSONDecodeError:
                                payload = {"raw": payload_str}

                            event = CapturedEvent(
                                event_type=event_type,
                                payload=payload,
                                stream_id=entry_id.decode()
                                if isinstance(entry_id, bytes)
                                else entry_id,
                            )
                            self._captured.append(event)
                            logger.debug(f"Captured event: {event_type}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Error consuming events: {e}")
                await asyncio.sleep(1)

    @property
    def events(self) -> list[CapturedEvent]:
        """Get all captured events."""
        return self._captured.copy()

    def clear(self):
        """Clear captured events."""
        self._captured.clear()

    async def wait_for_event(
        self,
        event_type: str,
        filters: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> CapturedEvent:
        """
        Wait for a specific event to be captured.

        Args:
            event_type: The event type to wait for
            filters: Optional payload filters
            timeout: Maximum time to wait in seconds

        Returns:
            The matching event

        Raises:
            TimeoutError: If event not found within timeout
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            # Check existing events
            for event in self._captured:
                if event.event_type == event_type and event.matches(filters):
                    return event

            await asyncio.sleep(0.5)

        raise TimeoutError(
            f"Event {event_type} not found within {timeout}s" f" (filters: {filters})"
        )


# --- Kubernetes Helpers ---


@dataclass
class PodStatus:
    """Status of a Kubernetes pod."""

    name: str
    namespace: str
    phase: str
    ready: bool
    restart_count: int = 0
    conditions: dict[str, bool] = field(default_factory=dict)


def run_kubectl(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a kubectl command."""
    kubeconfig = os.getenv("KUBECONFIG", os.path.expanduser("~/.kube/config"))
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig

    cmd = ["kubectl", *args]
    return subprocess.run(cmd, capture_output=True, text=True, check=check, env=env)


def get_pod_status(name: str, namespace: str = "default") -> PodStatus | None:
    """Get the status of a pod."""
    try:
        result = run_kubectl("get", "pod", name, "-n", namespace, "-o", "json")
        data = json.loads(result.stdout)

        # Extract conditions
        conditions = {}
        for cond in data.get("status", {}).get("conditions", []):
            conditions[cond["type"]] = cond["status"] == "True"

        # Get restart count
        restart_count = 0
        for cs in data.get("status", {}).get("containerStatuses", []):
            restart_count += cs.get("restartCount", 0)

        return PodStatus(
            name=name,
            namespace=namespace,
            phase=data.get("status", {}).get("phase", "Unknown"),
            ready=conditions.get("Ready", False),
            restart_count=restart_count,
            conditions=conditions,
        )

    except subprocess.CalledProcessError:
        return None


async def wait_for_pod_status(
    name: str,
    namespace: str = "default",
    expected_phase: str = "Running",
    expected_ready: bool = True,
    timeout: float = 120.0,
) -> PodStatus:
    """
    Wait for a pod to reach expected status.

    Args:
        name: Pod name
        namespace: Pod namespace
        expected_phase: Expected pod phase (Running, Succeeded, etc.)
        expected_ready: Whether pod should be ready
        timeout: Maximum time to wait

    Returns:
        Final pod status

    Raises:
        TimeoutError: If pod doesn't reach expected status
    """
    start_time = time.time()

    while time.time() - start_time < timeout:
        status = get_pod_status(name, namespace)

        if status:
            phase_ok = status.phase == expected_phase
            ready_ok = status.ready == expected_ready if expected_ready else True

            if phase_ok and ready_ok:
                return status

        await asyncio.sleep(2)

    raise TimeoutError(
        f"Pod {namespace}/{name} did not reach expected status "
        f"(phase={expected_phase}, ready={expected_ready}) within {timeout}s"
    )


async def wait_for_pod_deletion(
    name: str,
    namespace: str = "default",
    timeout: float = 60.0,
) -> bool:
    """Wait for a pod to be deleted."""
    start_time = time.time()

    while time.time() - start_time < timeout:
        status = get_pod_status(name, namespace)
        if status is None:
            return True
        await asyncio.sleep(2)

    return False


def create_test_pod(
    name: str,
    namespace: str = "default",
    image: str = "busybox:latest",
    command: list[str] | None = None,
    labels: dict[str, str] | None = None,
) -> bool:
    """Create a test pod."""
    manifest = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": name,
            "namespace": namespace,
            "labels": labels or {"app": "e2e-test"},
        },
        "spec": {
            "containers": [
                {
                    "name": "main",
                    "image": image,
                    "command": command or ["sleep", "3600"],
                }
            ],
            "restartPolicy": "Always",
        },
    }

    try:
        subprocess.run(
            ["kubectl", "apply", "-f", "-"],
            input=json.dumps(manifest),
            capture_output=True,
            text=True,
            check=True,
        )
        logger.info(f"Created pod {namespace}/{name}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to create pod: {e.stderr}")
        return False


def delete_test_pod(name: str, namespace: str = "default") -> bool:
    """Delete a test pod."""
    try:
        run_kubectl("delete", "pod", name, "-n", namespace, "--ignore-not-found")
        return True
    except subprocess.CalledProcessError:
        return False


def get_pod_logs(
    name: str,
    namespace: str = "default",
    tail: int = 100,
    container: str | None = None,
) -> str:
    """Get logs from a pod."""
    args = ["logs", name, "-n", namespace, f"--tail={tail}"]
    if container:
        args.extend(["-c", container])

    try:
        result = run_kubectl(*args)
        return result.stdout
    except subprocess.CalledProcessError:
        return ""


def get_events(
    namespace: str = "default",
    field_selector: str | None = None,
) -> list[dict[str, Any]]:
    """Get Kubernetes events."""
    args = ["get", "events", "-n", namespace, "-o", "json"]
    if field_selector:
        args.extend(["--field-selector", field_selector])

    try:
        result = run_kubectl(*args)
        data = json.loads(result.stdout)
        return data.get("items", [])
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return []


# --- Test Resource Management ---


class TestResourceManager:
    """
    Manage test resources with automatic cleanup.

    Usage:
        async with TestResourceManager("test-namespace") as manager:
            manager.create_pod("test-pod")
            # ... run tests ...
        # Resources automatically cleaned up
    """

    def __init__(self, namespace: str = "kubani-e2e-test"):
        self.namespace = namespace
        self._pods: list[str] = []
        self._deployments: list[str] = []
        self._services: list[str] = []

    async def __aenter__(self):
        await self.setup()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()

    async def setup(self):
        """Create test namespace if it doesn't exist."""
        try:
            run_kubectl("create", "namespace", self.namespace, check=False)
            logger.info(f"Created namespace {self.namespace}")
        except subprocess.CalledProcessError:
            pass  # Namespace may already exist

    async def cleanup(self):
        """Clean up all test resources."""
        logger.info(f"Cleaning up resources in {self.namespace}")

        # Delete pods
        for pod in self._pods:
            delete_test_pod(pod, self.namespace)

        # Delete deployments
        for deployment in self._deployments:
            run_kubectl(
                "delete",
                "deployment",
                deployment,
                "-n",
                self.namespace,
                "--ignore-not-found",
                check=False,
            )

        # Delete services
        for service in self._services:
            run_kubectl(
                "delete",
                "service",
                service,
                "-n",
                self.namespace,
                "--ignore-not-found",
                check=False,
            )

    def create_pod(
        self,
        name: str,
        image: str = "busybox:latest",
        command: list[str] | None = None,
        labels: dict[str, str] | None = None,
    ) -> bool:
        """Create a pod and track it for cleanup."""
        success = create_test_pod(
            name=name,
            namespace=self.namespace,
            image=image,
            command=command,
            labels=labels,
        )
        if success:
            self._pods.append(name)
        return success

    def create_crashloop_pod(self, name: str) -> bool:
        """Create a pod that will crash loop."""
        return self.create_pod(
            name=name,
            image="busybox:latest",
            command=["sh", "-c", "exit 1"],
            labels={"app": "crashloop-test"},
        )


# --- Assertion Helpers ---


async def assert_event_occurred(
    capture: EventCapture,
    event_type: str,
    filters: dict[str, Any] | None = None,
    timeout: float = 30.0,
    message: str = "",
) -> CapturedEvent:
    """Assert that an event occurred within timeout."""
    try:
        return await capture.wait_for_event(event_type, filters, timeout)
    except TimeoutError as e:
        raise AssertionError(f"{message or 'Expected event did not occur'}: {e}") from e


async def assert_pod_healthy(
    name: str,
    namespace: str = "default",
    timeout: float = 60.0,
) -> PodStatus:
    """Assert that a pod becomes healthy."""
    return await wait_for_pod_status(
        name=name,
        namespace=namespace,
        expected_phase="Running",
        expected_ready=True,
        timeout=timeout,
    )


def assert_no_crashes(logs: str, pod_name: str = ""):
    """Assert that logs don't contain crash indicators."""
    crash_indicators = [
        "panic:",
        "FATAL",
        "Traceback (most recent call last)",
        "segmentation fault",
        "core dumped",
    ]

    for indicator in crash_indicators:
        if indicator.lower() in logs.lower():
            raise AssertionError(f"Crash detected in {pod_name or 'logs'}: found '{indicator}'")
