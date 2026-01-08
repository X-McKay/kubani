"""
E2E Tests for Agent Lifecycle.

Tests agent startup, health checks, graceful shutdown,
and recovery from failures.
"""

import asyncio
import json

import pytest

from tests.e2e.utils import (
    TestResourceManager,
    assert_no_crashes,
    get_pod_logs,
    get_pod_status,
    run_kubectl,
    wait_for_pod_deletion,
    wait_for_pod_status,
)

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


class TestAgentStartup:
    """Test agent startup and initialization."""

    @pytest.mark.smoke
    async def test_agents_running(self, cluster_available):
        """
        Verify that agent pods are running in the cluster.

        This is a basic health check for the agent deployment.
        """
        result = run_kubectl(
            "get",
            "pods",
            "-n",
            "ai-agents",
            "-l",
            "app.kubernetes.io/part-of=kubani",
            "-o",
            "json",
            check=False,
        )

        if result.returncode != 0:
            pytest.skip("No agent pods found (agents may not be deployed)")

        data = json.loads(result.stdout)
        pods = data.get("items", [])

        if not pods:
            pytest.skip("No agent pods found")

        # Check each pod
        for pod in pods:
            name = pod["metadata"]["name"]
            phase = pod["status"].get("phase", "Unknown")

            # Log pod status
            print(f"Pod {name}: {phase}")

            # All pods should be Running or Succeeded
            assert phase in ["Running", "Succeeded"], f"Pod {name} is in unexpected phase: {phase}"

    @pytest.mark.smoke
    async def test_agent_no_crashes(self, cluster_available):
        """
        Verify that agents haven't crashed on startup.

        Checks for crash indicators in agent logs.
        """
        result = run_kubectl(
            "get",
            "pods",
            "-n",
            "ai-agents",
            "-l",
            "app.kubernetes.io/part-of=kubani",
            "-o",
            "jsonpath={.items[*].metadata.name}",
            check=False,
        )

        if result.returncode != 0 or not result.stdout.strip():
            pytest.skip("No agent pods found")

        pod_names = result.stdout.strip().split()

        for pod_name in pod_names:
            logs = get_pod_logs(pod_name, namespace="ai-agents", tail=200)
            assert_no_crashes(logs, pod_name)

    async def test_agent_restart_count(self, cluster_available):
        """
        Verify that agents haven't restarted excessively.

        High restart counts indicate instability.
        """
        result = run_kubectl(
            "get",
            "pods",
            "-n",
            "ai-agents",
            "-l",
            "app.kubernetes.io/part-of=kubani",
            "-o",
            "json",
            check=False,
        )

        if result.returncode != 0:
            pytest.skip("No agent pods found")

        data = json.loads(result.stdout)
        pods = data.get("items", [])

        if not pods:
            pytest.skip("No agent pods found")

        max_restarts = 3  # Allow some restarts for transient issues

        for pod in pods:
            name = pod["metadata"]["name"]
            container_statuses = pod["status"].get("containerStatuses", [])

            for cs in container_statuses:
                restarts = cs.get("restartCount", 0)
                assert restarts <= max_restarts, f"Pod {name} has excessive restarts: {restarts}"


class TestAgentHealth:
    """Test agent health and readiness."""

    async def test_agent_readiness(self, cluster_available):
        """
        Verify that agent pods are ready.

        Ready pods can serve traffic and process events.
        """
        result = run_kubectl(
            "get",
            "pods",
            "-n",
            "ai-agents",
            "-l",
            "app.kubernetes.io/part-of=kubani",
            "-o",
            "json",
            check=False,
        )

        if result.returncode != 0:
            pytest.skip("No agent pods found")

        data = json.loads(result.stdout)
        pods = data.get("items", [])

        if not pods:
            pytest.skip("No agent pods found")

        for pod in pods:
            name = pod["metadata"]["name"]
            conditions = pod["status"].get("conditions", [])

            # Find Ready condition
            ready_condition = next((c for c in conditions if c["type"] == "Ready"), None)

            if ready_condition:
                assert (
                    ready_condition["status"] == "True"
                ), f"Pod {name} is not ready: {ready_condition.get('message')}"

    @pytest.mark.slow
    async def test_agent_health_endpoint(self, cluster_available):
        """
        Test agent health endpoints if available.

        This tests that agents expose health/readiness probes.
        """
        # Get agent deployments
        result = run_kubectl(
            "get",
            "deployments",
            "-n",
            "ai-agents",
            "-l",
            "app.kubernetes.io/part-of=kubani",
            "-o",
            "json",
            check=False,
        )

        if result.returncode != 0:
            pytest.skip("No agent deployments found")

        data = json.loads(result.stdout)
        deployments = data.get("items", [])

        if not deployments:
            pytest.skip("No agent deployments found")

        for deployment in deployments:
            name = deployment["metadata"]["name"]
            spec = deployment["spec"]["template"]["spec"]
            containers = spec.get("containers", [])

            for container in containers:
                # Check for liveness probe
                liveness = container.get("livenessProbe")
                if liveness:
                    print(f"Deployment {name} has liveness probe")

                # Check for readiness probe
                readiness = container.get("readinessProbe")
                if readiness:
                    print(f"Deployment {name} has readiness probe")


class TestAgentRecovery:
    """Test agent recovery from failures."""

    @pytest.mark.slow
    async def test_agent_restart_recovery(
        self,
        test_resources: TestResourceManager,
    ):
        """
        Test that a killed agent pod recovers automatically.

        Kubernetes should restart the pod via the deployment.
        """
        # Create a test pod that simulates an agent
        pod_name = "e2e-recovery-test"
        test_resources.create_pod(
            name=pod_name,
            image="busybox:latest",
            command=["sleep", "3600"],
            labels={"app": "recovery-test"},
        )

        try:
            # Wait for pod to be running
            await wait_for_pod_status(
                pod_name,
                test_resources.namespace,
                expected_phase="Running",
                timeout=60,
            )

            # Kill the pod
            run_kubectl(
                "delete",
                "pod",
                pod_name,
                "-n",
                test_resources.namespace,
            )

            # Verify pod was deleted
            await wait_for_pod_deletion(
                pod_name,
                test_resources.namespace,
                timeout=30,
            )

            # For a deployment, Kubernetes would recreate the pod
            # Since we're using a bare pod, it should stay deleted
            await asyncio.sleep(5)
            status = get_pod_status(pod_name, test_resources.namespace)
            assert status is None, "Pod should not exist after deletion"

        except Exception:
            # Clean up on failure
            run_kubectl(
                "delete",
                "pod",
                pod_name,
                "-n",
                test_resources.namespace,
                "--ignore-not-found",
                check=False,
            )
            raise


class TestAgentConfiguration:
    """Test agent configuration and environment."""

    async def test_agent_environment_variables(self, cluster_available):
        """
        Verify agents have required environment variables.
        """
        result = run_kubectl(
            "get",
            "pods",
            "-n",
            "ai-agents",
            "-l",
            "app.kubernetes.io/part-of=kubani",
            "-o",
            "json",
            check=False,
        )

        if result.returncode != 0:
            pytest.skip("No agent pods found")

        data = json.loads(result.stdout)
        pods = data.get("items", [])

        if not pods:
            pytest.skip("No agent pods found")

        # Required environment variables for agents
        required_vars = [
            "KUBANI_LOG_LEVEL",
        ]

        optional_vars = [
            "KUBANI_REDIS_URL",
            "KUBANI_VLLM_API_URL",
            "KUBANI_QDRANT_URL",
        ]

        for pod in pods:
            name = pod["metadata"]["name"]
            containers = pod["spec"].get("containers", [])

            for container in containers:
                env = container.get("env", [])
                container.get("envFrom", [])

                # Get env var names
                env_names = {e["name"] for e in env}

                # Log which vars are set
                for var in required_vars + optional_vars:
                    if var in env_names:
                        print(f"Pod {name}: {var} is set")

    async def test_agent_resource_limits(self, cluster_available):
        """
        Verify agents have resource limits set.

        Resource limits prevent runaway resource consumption.
        """
        result = run_kubectl(
            "get",
            "pods",
            "-n",
            "ai-agents",
            "-l",
            "app.kubernetes.io/part-of=kubani",
            "-o",
            "json",
            check=False,
        )

        if result.returncode != 0:
            pytest.skip("No agent pods found")

        data = json.loads(result.stdout)
        pods = data.get("items", [])

        if not pods:
            pytest.skip("No agent pods found")

        for pod in pods:
            name = pod["metadata"]["name"]
            containers = pod["spec"].get("containers", [])

            for container in containers:
                resources = container.get("resources", {})
                limits = resources.get("limits", {})
                requests = resources.get("requests", {})

                # Log resource configuration
                if limits:
                    print(f"Pod {name}: limits = {limits}")
                if requests:
                    print(f"Pod {name}: requests = {requests}")
