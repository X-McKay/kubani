"""
Pytest configuration and fixtures for E2E tests.

Provides:
- Cluster availability checks
- Test resource management
- Event capture fixtures
- Skip markers for different environments
"""

import contextlib
import os

import pytest
import pytest_asyncio

from tests.e2e.utils import (
    EventCapture,
    TestResourceManager,
    run_kubectl,
)


# Register E2E markers
def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "e2e: mark test as an end-to-end integration test",
    )
    config.addinivalue_line(
        "markers",
        "slow: mark test as slow (may take several minutes)",
    )
    config.addinivalue_line(
        "markers",
        "smoke: mark test as a smoke test (quick verification)",
    )
    config.addinivalue_line(
        "markers",
        "requires_agents: mark test as requiring running agents",
    )


def pytest_collection_modifyitems(config, items):
    """Add skip markers based on environment."""
    # Check if cluster is available
    cluster_available = _check_cluster_available()

    # Check if we should run E2E tests
    run_e2e = config.getoption("--e2e", default=False) or os.getenv("RUN_E2E_TESTS")

    for item in items:
        # Skip E2E tests if not explicitly enabled
        if "e2e" in item.keywords and not run_e2e:
            item.add_marker(
                pytest.mark.skip(reason="E2E tests disabled. Use --e2e flag or set RUN_E2E_TESTS=1")
            )
            continue

        # Skip if cluster not available
        if "e2e" in item.keywords and not cluster_available:
            item.add_marker(pytest.mark.skip(reason="Kubernetes cluster not available"))


def pytest_addoption(parser):
    """Add custom command line options."""
    parser.addoption(
        "--e2e",
        action="store_true",
        default=False,
        help="Run E2E integration tests",
    )
    parser.addoption(
        "--e2e-namespace",
        action="store",
        default="kubani-e2e-test",
        help="Namespace for E2E test resources",
    )
    parser.addoption(
        "--skip-slow",
        action="store_true",
        default=False,
        help="Skip slow E2E tests",
    )


def _check_cluster_available() -> bool:
    """Check if a Kubernetes cluster is available."""
    try:
        result = run_kubectl("cluster-info", check=False)
        return result.returncode == 0
    except Exception:
        return False


def _check_agents_running() -> bool:
    """Check if Kubani agents are running in the cluster."""
    try:
        result = run_kubectl(
            "get",
            "pods",
            "-n",
            "ai-agents",
            "-l",
            "app.kubernetes.io/part-of=kubani",
            "-o",
            "name",
            check=False,
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except Exception:
        return False


# --- Fixtures ---


@pytest.fixture(scope="session")
def cluster_available():
    """Check if cluster is available, skip if not."""
    if not _check_cluster_available():
        pytest.skip("Kubernetes cluster not available")
    return True


@pytest.fixture(scope="session")
def agents_running(cluster_available):
    """Check if agents are running, skip if not."""
    if not _check_agents_running():
        pytest.skip("Kubani agents not running in cluster")
    return True


@pytest.fixture(scope="session")
def e2e_namespace(request):
    """Get the E2E test namespace."""
    return request.config.getoption("--e2e-namespace")


@pytest_asyncio.fixture
async def test_resources(e2e_namespace):
    """
    Provide a test resource manager with automatic cleanup.

    Usage:
        async def test_something(test_resources):
            test_resources.create_pod("my-pod")
            # ... test ...
        # Pod automatically deleted after test
    """
    async with TestResourceManager(e2e_namespace) as manager:
        yield manager


@pytest_asyncio.fixture
async def event_capture():
    """
    Provide an event capture instance.

    Usage:
        async def test_events(event_capture):
            # Do something that triggers an event
            event = await event_capture.wait_for_event(
                "K8S_ISSUE_DETECTED",
                timeout=30
            )
    """
    redis_url = os.getenv("KUBANI_REDIS_URL", "redis://localhost:6379")

    async with EventCapture(redis_url) as capture:
        yield capture


@pytest.fixture
def kubectl():
    """Provide kubectl helper function."""
    return run_kubectl


# --- Test Data Fixtures ---


@pytest.fixture
def crashloop_pod_manifest():
    """Return a pod manifest that will crash loop."""
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": "crashloop-test",
            "labels": {"app": "crashloop-test"},
        },
        "spec": {
            "containers": [
                {
                    "name": "crasher",
                    "image": "busybox:latest",
                    "command": ["sh", "-c", "exit 1"],
                }
            ],
            "restartPolicy": "Always",
        },
    }


@pytest.fixture
def healthy_pod_manifest():
    """Return a healthy pod manifest."""
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": "healthy-test",
            "labels": {"app": "healthy-test"},
        },
        "spec": {
            "containers": [
                {
                    "name": "main",
                    "image": "busybox:latest",
                    "command": ["sleep", "3600"],
                }
            ],
            "restartPolicy": "Always",
        },
    }


@pytest.fixture
def oom_pod_manifest():
    """Return a pod manifest that will OOM."""
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": "oom-test",
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
                        "x = []; [x.extend([0]*10**7) for _ in range(1000)]",
                    ],
                    "resources": {
                        "limits": {"memory": "32Mi"},
                    },
                }
            ],
            "restartPolicy": "Never",
        },
    }


# --- Cleanup ---


@pytest.fixture(scope="session", autouse=True)
def cleanup_e2e_resources(request, e2e_namespace):
    """Clean up E2E resources after all tests."""
    yield

    # Cleanup after session
    if _check_cluster_available():
        with contextlib.suppress(Exception):
            run_kubectl(
                "delete",
                "namespace",
                e2e_namespace,
                "--ignore-not-found",
                "--wait=false",
                check=False,
            )
